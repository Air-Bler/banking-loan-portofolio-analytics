-- Silver | loan applications | Owner: P1
-- 1. silver_loan_applications_clean    every delivered version, typed and standardised (streaming)
-- 2. silver_loan_applications_checked  newest version per application + every quality rule it fails
-- 3. silver_loan_applications          applications that pass every REJECT rule (FLAG rules keep the row)
--
-- Newest version wins (step 2): exact re-sent rows, late-arriving records and corrections collapse to
-- one row per application_id (greatest updated_at, ties: the later batch). Steps 2 and 3 are recomputed
-- on every run, so a corrected record leaves the quarantine by itself, and so do its repayments.
-- DTI uses the application-time snapshot: monthly_debt / (annual_income_at_application / 12).

CREATE OR REFRESH STREAMING TABLE silver_loan_applications_clean
COMMENT 'Typed and standardised loan applications, every delivered version'
AS
SELECT
    UPPER(TRIM(application_id)) AS application_id,
    NULLIF(UPPER(TRIM(customer_id)), '') AS customer_id,
    NULLIF(UPPER(TRIM(branch_code)), '') AS branch_code,
    NULLIF(UPPER(TRIM(product_code)), '') AS product_code,
    -- two date formats: YYYY-MM-DD and DD/MM/YYYY
    COALESCE(
        CAST(TRY_TO_TIMESTAMP(TRIM(application_date), 'yyyy-MM-dd') AS DATE),
        CAST(TRY_TO_TIMESTAMP(TRIM(application_date), 'dd/MM/yyyy') AS DATE)
    ) AS application_date,
    COALESCE(
        CAST(TRY_TO_TIMESTAMP(TRIM(decision_date), 'yyyy-MM-dd') AS DATE),
        CAST(TRY_TO_TIMESTAMP(TRIM(decision_date), 'dd/MM/yyyy') AS DATE)
    ) AS decision_date,
    NULLIF(TRIM(decision_date), '') AS decision_date_raw,          -- to spot a decision date that cannot be read
    NULLIF(UPPER(TRIM(status)), '') AS status,
    TRY_CAST(TRIM(requested_amount) AS DECIMAL(14,2)) AS requested_amount,
    TRY_CAST(TRIM(approved_amount) AS DECIMAL(14,2)) AS approved_amount,
    -- unambiguous spellings of the euro become EUR; anything else fails rule APP-09
    CASE WHEN UPPER(TRIM(currency)) IN ('EUR', 'EURO', '€') THEN 'EUR'
         ELSE NULLIF(UPPER(TRIM(currency)), '') END AS currency,
    TRY_CAST(TRIM(term_months) AS INT) AS term_months,
    TRY_CAST(TRIM(interest_rate) AS DECIMAL(6,4)) AS interest_rate,
    TRY_CAST(TRIM(risk_score) AS INT) AS risk_score,
    TRY_CAST(TRIM(monthly_debt) AS DECIMAL(14,2)) AS monthly_debt,
    TRY_CAST(TRIM(annual_income_at_application) AS DECIMAL(14,2)) AS annual_income_at_application,
    NULLIF(UPPER(TRIM(employment_status_at_application)), '') AS employment_status_at_application,
    TRY_CAST(TRIM(declared_monthly_expenses) AS DECIMAL(14,2)) AS declared_monthly_expenses,
    NULLIF(UPPER(TRIM(consent_flag)), '') AS consent_flag,
    CASE WHEN UPPER(TRIM(manual_review)) = 'Y' THEN 1 ELSE 0 END AS is_manual_review,
    TRY_TO_TIMESTAMP(TRIM(updated_at)) AS updated_at,
    NULLIF(UPPER(TRIM(channel)), '') AS channel,
    batch_id,
    source_file,
    ingest_ts,
    record_hash
FROM STREAM(bronze_loan_applications);


CREATE OR REFRESH MATERIALIZED VIEW silver_loan_applications_checked (
    CONSTRAINT app_01_customer_id_present    EXPECT (NOT array_contains(failed_rules, 'APP-01')),
    CONSTRAINT app_02_consent_present        EXPECT (NOT array_contains(failed_rules, 'APP-02')),
    CONSTRAINT app_03_status_present         EXPECT (NOT array_contains(failed_rules, 'APP-03')),
    CONSTRAINT app_04_status_known           EXPECT (NOT array_contains(failed_rules, 'APP-04')),
    CONSTRAINT app_05_amounts_consistent     EXPECT (NOT array_contains(failed_rules, 'APP-05')),
    CONSTRAINT app_06_amount_within_product  EXPECT (NOT array_contains(failed_rules, 'APP-06')),
    CONSTRAINT app_07_dates_possible         EXPECT (NOT array_contains(failed_rules, 'APP-07')),
    CONSTRAINT app_08_not_duplicate          EXPECT (NOT array_contains(failed_rules, 'APP-08')),
    CONSTRAINT app_09_currency_eur           EXPECT (NOT array_contains(failed_rules, 'APP-09')),
    CONSTRAINT app_10_risk_score_in_range    EXPECT (NOT array_contains(failed_rules, 'APP-10')),
    CONSTRAINT app_11_customer_known         EXPECT (NOT array_contains(failed_rules, 'APP-11')),
    CONSTRAINT app_12_branch_product_known   EXPECT (NOT array_contains(failed_rules, 'APP-12'))
)
COMMENT 'Newest version of every application, enriched, with the list of quality rules it fails'
AS
WITH latest AS (
    SELECT * EXCEPT (rn)
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY application_id
                ORDER BY updated_at DESC, batch_id DESC, ingest_ts DESC
            ) AS rn
        FROM silver_loan_applications_clean
    )
    WHERE rn = 1
),
enriched AS (
    SELECT
        a.*,
        c.segment_code,
        b.region,
        p.product_family,
        p.min_amount AS product_min_amount,
        p.max_amount AS product_max_amount,
        -- debt-to-income at application time: existing monthly debt / monthly income
        ROUND(TRY_DIVIDE(a.monthly_debt, a.annual_income_at_application / 12), 4) AS dti_ratio,
        c.customer_id IS NOT NULL AS customer_found,
        b.branch_code IS NOT NULL AS branch_found,
        p.product_code IS NOT NULL AS product_found,
        -- APP-08: the same customer, product, date and amount delivered again under a new application id
        CASE
            WHEN a.customer_id IS NULL OR a.product_code IS NULL
                 OR a.application_date IS NULL OR a.requested_amount IS NULL THEN 1
            ELSE ROW_NUMBER() OVER (
                PARTITION BY a.customer_id, a.product_code, a.application_date, a.requested_amount
                ORDER BY a.application_id
            )
        END AS duplicate_rank
    FROM latest a
    LEFT JOIN silver_customers_current c ON a.customer_id = c.customer_id
    LEFT JOIN silver_branches b ON a.branch_code = b.branch_code
    LEFT JOIN silver_products p ON a.product_code = p.product_code
)
SELECT
    *,
    -- every rule the row fails (not only the first), so the count per rule is exact
    filter(array(
        CASE WHEN customer_id IS NULL THEN 'APP-01' END,
        CASE WHEN consent_flag IS NULL OR consent_flag NOT IN ('Y', 'N') THEN 'APP-02' END,
        CASE WHEN status IS NULL THEN 'APP-03' END,
        CASE WHEN status NOT IN ('SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'WITHDRAWN') THEN 'APP-04' END,
        CASE WHEN requested_amount IS NULL OR requested_amount <= 0
                  OR approved_amount <= 0
                  OR approved_amount > requested_amount
                  OR (status = 'APPROVED' AND approved_amount IS NULL)
                  OR (status <> 'APPROVED' AND approved_amount IS NOT NULL)
             THEN 'APP-05' END,
        CASE WHEN product_found AND requested_amount > 0
                  AND (requested_amount < product_min_amount OR requested_amount > product_max_amount)
             THEN 'APP-06' END,
        CASE WHEN application_date IS NULL OR application_date > CURRENT_DATE()
                  OR decision_date < application_date
                  OR (decision_date_raw IS NOT NULL AND decision_date IS NULL)
             THEN 'APP-07' END,
        CASE WHEN duplicate_rank > 1 THEN 'APP-08' END,
        CASE WHEN currency IS NULL OR currency <> 'EUR' THEN 'APP-09' END,
        CASE WHEN risk_score IS NULL OR risk_score NOT BETWEEN 300 AND 850 THEN 'APP-10' END,
        CASE WHEN customer_id IS NOT NULL AND NOT customer_found THEN 'APP-11' END,
        CASE WHEN NOT branch_found OR NOT product_found THEN 'APP-12' END
    ), r -> r IS NOT NULL) AS failed_rules
FROM enriched;


CREATE OR REFRESH MATERIALIZED VIEW silver_loan_applications
COMMENT 'Valid loan applications, newest version. dq_flags lists the FLAG rules a row fails (APP-10 to APP-12)'
AS
SELECT
    * EXCEPT (failed_rules, duplicate_rank, decision_date_raw, customer_found, branch_found, product_found,
              product_min_amount, product_max_amount),
    CASE WHEN size(failed_rules) > 0 THEN array_join(failed_rules, ',') END AS dq_flags
FROM silver_loan_applications_checked
-- REJECT rules: the row goes to the quarantine only
WHERE NOT exists(failed_rules, r -> r IN ('APP-01', 'APP-02', 'APP-03', 'APP-04', 'APP-05', 'APP-06',
                                          'APP-07', 'APP-08', 'APP-09'));
