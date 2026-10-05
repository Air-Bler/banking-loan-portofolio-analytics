-- Silver | repayment installments | Owner: P1
-- An installment is delivered again when it changes (for example overdue, then settled); the version
-- with the greatest updated_at is current (ties: the later batch).
-- Status and days past due are recomputed from the amounts and dates, so a contradictory value in
-- the source is corrected (and flagged, rule REP-08):
--   settled (total_paid >= total_due): ON_TIME if paid on or before the due date, else LATE;
--                                       days past due = payment_date - due_date (at least 0)
--   open: PARTIAL if something was paid, else MISSED; days past due = snapshot date - due_date
--         (the snapshot date is the date of updated_at: 2025-12-31 after the last batch)
-- total_due is recomputed as principal_due + interest_due (a wrong total is flagged, rule REP-07).

CREATE OR REFRESH STREAMING TABLE silver_repayments_clean
COMMENT 'Typed installment rows, every delivered version, with recomputed total, status and days past due'
AS
WITH typed AS (
    SELECT
        UPPER(TRIM(repayment_id)) AS repayment_id,
        UPPER(TRIM(application_id)) AS application_id,
        TRY_CAST(TRIM(installment_number) AS INT) AS installment_number,
        CAST(TRY_TO_TIMESTAMP(TRIM(due_date), 'yyyy-MM-dd') AS DATE) AS due_date,
        TRY_CAST(TRIM(principal_due) AS DECIMAL(14,2)) AS principal_due,
        TRY_CAST(TRIM(interest_due) AS DECIMAL(14,2)) AS interest_due,
        TRY_CAST(TRIM(total_due) AS DECIMAL(14,2)) AS total_due_delivered,
        CAST(TRY_TO_TIMESTAMP(TRIM(payment_date), 'yyyy-MM-dd') AS DATE) AS payment_date,
        NULLIF(TRIM(payment_date), '') AS payment_date_raw,              -- to spot a date that cannot be read
        COALESCE(TRY_CAST(TRIM(principal_paid) AS DECIMAL(14,2)), 0) AS principal_paid,
        COALESCE(TRY_CAST(TRIM(interest_paid) AS DECIMAL(14,2)), 0) AS interest_paid,
        COALESCE(TRY_CAST(TRIM(total_paid) AS DECIMAL(14,2)), 0) AS total_paid,
        NULLIF(UPPER(TRIM(payment_status)), '') AS payment_status_delivered,
        TRY_CAST(TRIM(days_past_due) AS INT) AS days_past_due_delivered,
        CASE WHEN UPPER(TRIM(currency)) IN ('EUR', 'EURO', '€') THEN 'EUR'
             ELSE NULLIF(UPPER(TRIM(currency)), '') END AS currency,
        TRY_TO_TIMESTAMP(TRIM(updated_at)) AS updated_at,
        batch_id,
        source_file,
        ingest_ts,
        record_hash
    FROM STREAM(bronze_repayments)
),
derived AS (
    SELECT
        *,
        CAST(principal_due + interest_due AS DECIMAL(14,2)) AS total_due,
        CASE WHEN total_paid >= principal_due + interest_due THEN 1 ELSE 0 END AS is_settled
    FROM typed
)
SELECT
    *,
    CASE
        WHEN is_settled = 1 AND payment_date <= due_date THEN 'ON_TIME'
        WHEN is_settled = 1 THEN 'LATE'
        WHEN total_paid > 0 THEN 'PARTIAL'
        ELSE 'MISSED'
    END AS payment_status,
    CASE
        WHEN is_settled = 1 THEN GREATEST(DATEDIFF(payment_date, due_date), 0)
        ELSE GREATEST(DATEDIFF(CAST(updated_at AS DATE), due_date), 0)
    END AS days_past_due,
    1 - is_settled AS is_open
FROM derived;


CREATE OR REFRESH MATERIALIZED VIEW silver_repayments_checked (
    CONSTRAINT rep_01_application_exists      EXPECT (NOT array_contains(failed_rules, 'REP-01')),
    CONSTRAINT rep_02_application_valid       EXPECT (NOT array_contains(failed_rules, 'REP-02')),
    CONSTRAINT rep_03_installment_unique      EXPECT (NOT array_contains(failed_rules, 'REP-03')),
    CONSTRAINT rep_04_amounts_not_negative    EXPECT (NOT array_contains(failed_rules, 'REP-04')),
    CONSTRAINT rep_05_payment_date_possible   EXPECT (NOT array_contains(failed_rules, 'REP-05')),
    CONSTRAINT rep_06_currency_eur            EXPECT (NOT array_contains(failed_rules, 'REP-06')),
    CONSTRAINT rep_07_total_adds_up           EXPECT (NOT array_contains(failed_rules, 'REP-07')),
    CONSTRAINT rep_08_status_consistent       EXPECT (NOT array_contains(failed_rules, 'REP-08'))
)
COMMENT 'Current version of every installment with the quality rules it fails'
AS
WITH latest AS (
    SELECT * EXCEPT (rn)
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY repayment_id
                ORDER BY updated_at DESC, batch_id DESC, ingest_ts DESC
            ) AS rn
        FROM silver_repayments_clean
    )
    WHERE rn = 1
),
enriched AS (
    SELECT
        l.*,
        a.application_id IS NOT NULL AS application_delivered,
        v.application_id IS NOT NULL AND v.status = 'APPROVED' AS application_valid,
        a.decision_date AS application_decision_date,
        -- REP-03: a second installment row with the same loan and installment number
        ROW_NUMBER() OVER (
            PARTITION BY l.application_id, l.installment_number
            ORDER BY l.repayment_id
        ) AS installment_rank
    FROM latest l
    LEFT JOIN (SELECT application_id, decision_date FROM silver_loan_applications_checked) a
        ON l.application_id = a.application_id
    LEFT JOIN (SELECT application_id, status FROM silver_loan_applications) v
        ON l.application_id = v.application_id
)
SELECT
    *,
    filter(array(
        CASE WHEN NOT application_delivered THEN 'REP-01' END,
        CASE WHEN application_delivered AND NOT application_valid THEN 'REP-02' END,
        CASE WHEN installment_rank > 1 THEN 'REP-03' END,
        CASE WHEN principal_due < 0 OR interest_due < 0 OR total_due_delivered < 0
                  OR principal_paid < 0 OR interest_paid < 0 OR total_paid < 0 THEN 'REP-04' END,
        CASE WHEN payment_date > CAST(updated_at AS DATE)
                  OR payment_date < application_decision_date
                  OR payment_date < DATE_SUB(due_date, 31)
                  OR (payment_date_raw IS NOT NULL AND payment_date IS NULL)
                  OR (is_settled = 1 AND payment_date IS NULL) THEN 'REP-05' END,
        CASE WHEN currency IS NULL OR currency <> 'EUR' THEN 'REP-06' END,
        CASE WHEN total_due_delivered IS NULL OR total_due_delivered <> total_due THEN 'REP-07' END,
        CASE WHEN payment_status_delivered IS NULL OR payment_status_delivered <> payment_status
                  OR days_past_due_delivered IS NULL OR days_past_due_delivered <> days_past_due THEN 'REP-08' END
    ), r -> r IS NOT NULL) AS failed_rules
FROM enriched;


CREATE OR REFRESH MATERIALIZED VIEW silver_repayments
COMMENT 'Valid installments of valid approved loans; status and days past due recomputed. dq_flags: REP-07, REP-08'
AS
SELECT
    * EXCEPT (failed_rules, application_delivered, application_valid, application_decision_date, installment_rank,
              total_due_delivered, payment_status_delivered, days_past_due_delivered, payment_date_raw),
    CASE WHEN size(failed_rules) > 0 THEN array_join(failed_rules, ',') END AS dq_flags
FROM silver_repayments_checked
-- REJECT rules: the row goes to the quarantine only
WHERE NOT exists(failed_rules, r -> r IN ('REP-01', 'REP-02', 'REP-03', 'REP-04', 'REP-05', 'REP-06'));
