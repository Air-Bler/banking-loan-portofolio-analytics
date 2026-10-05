-- Silver | transactions (payment and cash-flow events from transactions.json) | Owner: P1
-- Parses the raw JSON, flattens the nested account, payment and source objects and standardises:
--   event type spelling ('Loan Repayment', 'LOAN-REPAYMENT', 'LOAN_REPAYMNT' -> LOAN_REPAYMENT)
--   amount with a decimal comma ('594,09' -> 594.09), currency spellings ('eur', 'EURO', '€' -> EUR)
--   event time with 'Z' or a +02:00/+03:00 offset -> UTC
-- Events have no version field: for the same event_id the later delivery batch wins.
-- LOAN_REPAYMENT events must point to a known installment of the same loan (TRX-07 to TRX-09).
-- Set the pipeline configuration spark.sql.session.timeZone = UTC (see README).

CREATE OR REFRESH STREAMING TABLE silver_transactions_clean
COMMENT 'Flattened and standardised transaction events, every delivered line that is valid JSON'
AS
WITH parsed AS (
    SELECT
        from_json(
            raw_json,
            'event_id STRING, event_type STRING, event_time STRING, customer_id STRING,
             account STRUCT<loan_account: STRING, application_id: STRING, repayment_id: STRING, current_account: STRING>,
             payment STRUCT<amount: STRING, currency: STRING, channel: STRING, direction: STRING>,
             source STRUCT<system: STRING, version: STRING>'
        ) AS e,
        batch_id,
        source_file,
        ingest_ts,
        record_hash
    FROM STREAM(bronze_transactions)
    WHERE load_status = 'OK'
),
standardised AS (
    SELECT
        *,
        UPPER(REGEXP_REPLACE(TRIM(e.event_type), '[^A-Za-z]+', '_')) AS event_type_norm
    FROM parsed
)
SELECT
    UPPER(TRIM(e.event_id)) AS event_id,
    -- match the spelling to the closest of the 8 event types (at most 2 letters different)
    CASE
        WHEN LEVENSHTEIN(event_type_norm, 'LOAN_REPAYMENT') <= 2 THEN 'LOAN_REPAYMENT'
        WHEN LEVENSHTEIN(event_type_norm, 'SALARY_CREDIT') <= 2 THEN 'SALARY_CREDIT'
        WHEN LEVENSHTEIN(event_type_norm, 'ACCOUNT_CREDIT') <= 2 THEN 'ACCOUNT_CREDIT'
        WHEN LEVENSHTEIN(event_type_norm, 'CARD_PAYMENT') <= 2 THEN 'CARD_PAYMENT'
        WHEN LEVENSHTEIN(event_type_norm, 'DIRECT_DEBIT') <= 2 THEN 'DIRECT_DEBIT'
        WHEN LEVENSHTEIN(event_type_norm, 'CASH_WITHDRAWAL') <= 2 THEN 'CASH_WITHDRAWAL'
        WHEN LEVENSHTEIN(event_type_norm, 'BANK_TRANSFER_IN') <= 1 THEN 'BANK_TRANSFER_IN'
        WHEN LEVENSHTEIN(event_type_norm, 'BANK_TRANSFER_OUT') <= 1 THEN 'BANK_TRANSFER_OUT'
        ELSE event_type_norm
    END AS event_type,
    e.event_type AS event_type_raw,
    NULLIF(TRIM(e.event_time), '') AS event_time_raw,
    TRY_TO_TIMESTAMP(TRIM(e.event_time)) AS event_ts_utc,
    CAST(FROM_UTC_TIMESTAMP(TRY_TO_TIMESTAMP(TRIM(e.event_time)), 'Europe/Athens') AS DATE) AS event_date,
    NULLIF(UPPER(TRIM(e.customer_id)), '') AS customer_id,
    NULLIF(UPPER(TRIM(e.account.loan_account)), '') AS loan_account,
    NULLIF(UPPER(TRIM(e.account.application_id)), '') AS application_id,
    NULLIF(UPPER(TRIM(e.account.repayment_id)), '') AS repayment_id,
    NULLIF(UPPER(TRIM(e.account.current_account)), '') AS current_account,
    NULLIF(TRIM(e.payment.amount), '') AS amount_raw,
    TRY_CAST(REPLACE(TRIM(e.payment.amount), ',', '.') AS DECIMAL(14,2)) AS amount,
    CASE WHEN UPPER(TRIM(e.payment.currency)) IN ('EUR', 'EURO', '€') THEN 'EUR'
         ELSE NULLIF(UPPER(TRIM(e.payment.currency)), '') END AS currency,
    NULLIF(UPPER(TRIM(e.payment.channel)), '') AS channel,
    NULLIF(UPPER(TRIM(e.payment.direction)), '') AS direction,
    e.source.system AS source_system,
    e.source.version AS source_version,
    batch_id,
    source_file,
    ingest_ts,
    record_hash
FROM standardised;


CREATE OR REFRESH MATERIALIZED VIEW silver_transactions_checked (
    CONSTRAINT trx_01_event_type_known       EXPECT (NOT array_contains(failed_rules, 'TRX-01')),
    CONSTRAINT trx_02_required_fields        EXPECT (NOT array_contains(failed_rules, 'TRX-02')),
    CONSTRAINT trx_03_event_time_possible    EXPECT (NOT array_contains(failed_rules, 'TRX-03')),
    CONSTRAINT trx_04_amount_positive        EXPECT (NOT array_contains(failed_rules, 'TRX-04')),
    CONSTRAINT trx_05_currency_eur           EXPECT (NOT array_contains(failed_rules, 'TRX-05')),
    CONSTRAINT trx_06_customer_known         EXPECT (NOT array_contains(failed_rules, 'TRX-06')),
    CONSTRAINT trx_07_installment_known      EXPECT (NOT array_contains(failed_rules, 'TRX-07')),
    CONSTRAINT trx_08_same_loan              EXPECT (NOT array_contains(failed_rules, 'TRX-08')),
    CONSTRAINT trx_09_installment_valid      EXPECT (NOT array_contains(failed_rules, 'TRX-09'))
)
COMMENT 'One row per event (later batch wins, duplicates removed) with the quality rules it fails'
AS
WITH latest AS (
    SELECT * EXCEPT (rn)
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY batch_id DESC, ingest_ts DESC) AS rn
        FROM silver_transactions_clean
    )
    WHERE rn = 1
),
enriched AS (
    SELECT
        t.*,
        t.event_type = 'LOAN_REPAYMENT' AS is_loan_repayment,
        c.customer_id IS NOT NULL AS customer_found,
        r.repayment_id IS NOT NULL AS installment_found,
        r.application_id AS installment_application_id,
        NOT array_contains(r.failed_rules, 'REP-01') AS installment_loan_known,
        v.repayment_id IS NOT NULL AS installment_valid
    FROM latest t
    LEFT JOIN (SELECT customer_id FROM silver_customers_current) c ON t.customer_id = c.customer_id
    LEFT JOIN (SELECT repayment_id, application_id, failed_rules FROM silver_repayments_checked) r ON t.repayment_id = r.repayment_id
    LEFT JOIN (SELECT repayment_id FROM silver_repayments) v ON t.repayment_id = v.repayment_id
)
SELECT
    *,
    filter(array(
        CASE WHEN event_type NOT IN ('LOAN_REPAYMENT', 'SALARY_CREDIT', 'ACCOUNT_CREDIT', 'CARD_PAYMENT', 'DIRECT_DEBIT',
                                     'CASH_WITHDRAWAL', 'BANK_TRANSFER_IN', 'BANK_TRANSFER_OUT')
                  OR event_type IS NULL THEN 'TRX-01' END,
        CASE WHEN event_id IS NULL OR customer_id IS NULL OR event_time_raw IS NULL
                  OR amount_raw IS NULL OR currency IS NULL
                  OR (is_loan_repayment AND (loan_account IS NULL OR application_id IS NULL OR repayment_id IS NULL))
                  OR (NOT is_loan_repayment AND current_account IS NULL) THEN 'TRX-02' END,
        CASE WHEN event_time_raw IS NOT NULL
                  AND (event_ts_utc IS NULL OR event_ts_utc < TIMESTAMP '2016-01-01 00:00:00'
                       OR event_ts_utc > CURRENT_TIMESTAMP()) THEN 'TRX-03' END,
        CASE WHEN amount_raw IS NOT NULL AND (amount IS NULL OR amount <= 0) THEN 'TRX-04' END,
        CASE WHEN currency IS NOT NULL AND currency <> 'EUR' THEN 'TRX-05' END,
        CASE WHEN customer_id IS NOT NULL AND NOT customer_found THEN 'TRX-06' END,
        CASE WHEN is_loan_repayment AND repayment_id IS NOT NULL AND NOT installment_found THEN 'TRX-07' END,
        -- compared only when the installment's own loan reference is sound (not an orphan, REP-01)
        CASE WHEN is_loan_repayment AND installment_found AND installment_loan_known AND application_id IS NOT NULL
                  AND application_id <> installment_application_id THEN 'TRX-08' END,
        CASE WHEN is_loan_repayment AND installment_found AND NOT installment_valid THEN 'TRX-09' END
    ), r -> r IS NOT NULL) AS failed_rules
FROM enriched;


CREATE OR REFRESH MATERIALIZED VIEW silver_transactions
COMMENT 'Valid transaction events of all 8 types; LOAN_REPAYMENT events point to a valid installment of the same loan'
AS
SELECT * EXCEPT (failed_rules, is_loan_repayment, customer_found, installment_found, installment_application_id,
                 installment_loan_known, installment_valid, event_type_raw, event_time_raw, amount_raw)
FROM silver_transactions_checked
WHERE size(failed_rules) = 0;
