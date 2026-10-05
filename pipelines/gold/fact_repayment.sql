-- Gold | fact_repayment | Owner: P2a
-- Grain: one scheduled installment (current version), with what was paid against it.
-- Dimension keys come from its loan. Open installments get an ageing bucket by days past due.

CREATE OR REFRESH MATERIALIZED VIEW fact_repayment
CLUSTER BY (due_date_key)
COMMENT 'Grain: one scheduled installment with its payment outcome. Dimension keys come from its loan'
AS
SELECT
    r.repayment_id,
    r.application_id,
    r.installment_number,
    CAST(DATE_FORMAT(r.due_date, 'yyyyMMdd') AS INT) AS due_date_key,
    CAST(DATE_FORMAT(r.payment_date, 'yyyyMMdd') AS INT) AS payment_date_key,
    f.branch_key,
    f.product_key,
    f.customer_segment_key,
    f.risk_band_key,
    r.principal_due,
    r.interest_due,
    r.total_due,
    r.principal_paid,
    r.interest_paid,
    r.total_paid,
    CAST(r.total_due - r.total_paid AS DECIMAL(14,2)) AS amount_unpaid,
    r.payment_status,
    r.days_past_due,
    r.is_open,
    CASE WHEN r.is_open = 1 AND r.days_past_due >= 30 THEN 1 ELSE 0 END AS is_open_30plus,
    CASE
        WHEN r.is_open = 0 THEN 'Settled'
        WHEN r.days_past_due < 30 THEN '0-29'
        WHEN r.days_past_due < 60 THEN '30-59'
        WHEN r.days_past_due < 90 THEN '60-89'
        WHEN r.days_past_due < 180 THEN '90-179'
        WHEN r.days_past_due <= 365 THEN '180-365'
        ELSE '365+'
    END AS ageing_bucket,
    CASE WHEN r.dq_flags IS NULL THEN 0 ELSE SIZE(SPLIT(r.dq_flags, ',')) END AS dq_flag_count,
    r.batch_id AS source_batch_id,
    r.source_file
FROM silver_repayments r
JOIN fact_loan_application f ON r.application_id = f.application_id;
