-- Gold | fact_loan_application | Owner: P2a
-- Grain: one loan application (newest valid version).
-- Loan state at the as-of date, from its valid installments:
--   outstanding balance = approved amount - principal paid (never below 0)
--   paid off            = the final installment (number = term) exists and no installment is open
--   active loan         = approved and not paid off (a matured loan with unpaid installments stays active)
--   delinquent 30+      = active and at least one open installment 30 or more days past due
-- Open installments are never written off, so delinquency is also shown by ageing bucket.
-- customer_key is a one-way hash of the customer id: no personal data in Gold.

CREATE OR REFRESH MATERIALIZED VIEW fact_loan_application
CLUSTER BY (application_date_key)
COMMENT 'Grain: one loan application (newest valid version). Balance and delinquency at the as-of date'
AS
WITH per_loan AS (
    SELECT
        application_id,
        SUM(principal_paid) AS principal_repaid,
        MAX(installment_number) AS last_installment_number,
        SUM(is_open) AS open_installments,
        MAX(CASE WHEN is_open = 1 THEN days_past_due ELSE 0 END) AS max_open_days_past_due
    FROM silver_repayments
    GROUP BY application_id
),
loans AS (
    SELECT
        a.*,
        COALESCE(l.max_open_days_past_due, 0) AS max_open_days_past_due,
        CASE
            WHEN a.status = 'APPROVED'
                 AND COALESCE(l.last_installment_number, 0) >= a.term_months
                 AND COALESCE(l.open_installments, 0) = 0 THEN 1
            ELSE 0
        END AS is_paid_off,
        CASE
            WHEN a.status = 'APPROVED'
                THEN GREATEST(a.approved_amount - COALESCE(l.principal_repaid, 0), 0)
            ELSE 0
        END AS outstanding,
        CASE
            WHEN a.risk_score BETWEEN 800 AND 850 THEN 'A'
            WHEN a.risk_score BETWEEN 740 AND 799 THEN 'B'
            WHEN a.risk_score BETWEEN 670 AND 739 THEN 'C'
            WHEN a.risk_score BETWEEN 580 AND 669 THEN 'D'
            WHEN a.risk_score BETWEEN 300 AND 579 THEN 'E'
        END AS risk_band_code
    FROM silver_loan_applications a
    LEFT JOIN per_loan l ON a.application_id = l.application_id
),
states AS (
    SELECT
        *,
        CASE WHEN status = 'APPROVED' AND is_paid_off = 0 THEN 1 ELSE 0 END AS is_active_loan
    FROM loans
)
SELECT
    s.application_id,
    SUBSTRING(SHA2(s.customer_id, 256), 1, 16) AS customer_key,
    CAST(DATE_FORMAT(s.application_date, 'yyyyMMdd') AS INT) AS application_date_key,
    CAST(DATE_FORMAT(s.decision_date, 'yyyyMMdd') AS INT) AS decision_date_key,
    COALESCE(b.branch_key, -1) AS branch_key,
    COALESCE(p.product_key, -1) AS product_key,
    COALESCE(sg.customer_segment_key, -1) AS customer_segment_key,
    COALESCE(r.risk_band_key, -1) AS risk_band_key,
    COALESCE(st.status_key, -1) AS status_key,
    s.channel,
    s.employment_status_at_application,
    s.requested_amount,
    s.approved_amount,
    s.term_months,
    s.interest_rate,
    s.risk_score,
    s.monthly_debt,
    s.annual_income_at_application,
    s.declared_monthly_expenses,
    s.dti_ratio,
    CASE
        WHEN s.dti_ratio IS NULL THEN 'Unknown'
        WHEN s.dti_ratio < 0.20 THEN '1. Below 20%'
        WHEN s.dti_ratio < 0.35 THEN '2. 20-35%'
        WHEN s.dti_ratio <= 0.50 THEN '3. 35-50%'
        ELSE '4. Above 50%'
    END AS dti_band,
    CASE WHEN s.status IN ('APPROVED', 'REJECTED') AND s.decision_date IS NOT NULL
         THEN DATEDIFF(s.decision_date, s.application_date) END AS decision_days,
    CASE WHEN s.status IN ('APPROVED', 'REJECTED') THEN 1 ELSE 0 END AS is_decided,
    CASE WHEN s.status = 'APPROVED' THEN 1 ELSE 0 END AS is_approved,
    s.is_manual_review,
    s.is_paid_off,
    s.is_active_loan,
    CAST(s.outstanding AS DECIMAL(14,2)) AS outstanding_balance,
    s.max_open_days_past_due,
    CASE WHEN s.is_active_loan = 1 AND s.max_open_days_past_due >= 30 THEN 1 ELSE 0 END AS is_delinquent_30,
    CASE
        WHEN s.is_active_loan = 0 THEN 'Not active'
        WHEN s.max_open_days_past_due < 30 THEN '0-29'
        WHEN s.max_open_days_past_due < 60 THEN '30-59'
        WHEN s.max_open_days_past_due < 90 THEN '60-89'
        WHEN s.max_open_days_past_due < 180 THEN '90-179'
        WHEN s.max_open_days_past_due <= 365 THEN '180-365'
        ELSE '365+'
    END AS delinquency_bucket,
    CASE WHEN s.dq_flags IS NULL THEN 0 ELSE SIZE(SPLIT(s.dq_flags, ',')) END AS dq_flag_count,
    s.batch_id AS source_batch_id,
    s.source_file
FROM states s
LEFT JOIN dim_branch b ON s.branch_code = b.branch_code AND b.branch_key <> -1
LEFT JOIN dim_product p ON s.product_code = p.product_code AND p.product_key <> -1
LEFT JOIN dim_customer_segment sg ON s.segment_code = sg.segment_code AND sg.customer_segment_key <> -1
LEFT JOIN dim_risk_band r ON s.risk_band_code = r.risk_band_code AND r.risk_band_key <> -1
LEFT JOIN dim_application_status st ON s.status = st.status_code AND st.status_key <> -1;
