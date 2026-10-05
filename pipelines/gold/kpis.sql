-- Gold | KPI views and refresh info | Owner: P2a (definitions agreed with P2b and P3)
-- The 8 governed KPIs, defined once. Power BI DAX and the API must return the same numbers.
--   Approval rate        approved / (approved + rejected); withdrawn and undecided excluded
--   Avg decision time    days from application to decision, approved + rejected only
--   DTI band             monthly_debt / (annual_income_at_application / 12): <20%, 20-35%, 35-50%, >50%
--   Delinquency rate     active loans with an open installment 30+ days past due / active loans
--   Outstanding balance  approved amount - principal paid, approved loans, at the as-of date
--
--   kpi_portfolio_monthly        additive parts by application month, branch and product
--   kpi_portfolio_summary        the 8 KPIs for the whole portfolio, one row (the validation baseline)
--   kpi_open_installment_ageing  open installments and unpaid amount by days-past-due bucket
--   refresh_info                 as-of date and refresh time for the report's last-refresh card

CREATE OR REFRESH MATERIALIZED VIEW kpi_portfolio_monthly
COMMENT 'Additive KPI parts by application month, branch and product (sum the parts, then divide)'
AS
SELECT
    CAST(application_date_key / 100 AS INT) AS month_key,
    branch_key,
    product_key,
    COUNT(*) AS applications,
    SUM(requested_amount) AS requested_amount,
    SUM(is_decided) AS decided_applications,
    SUM(is_approved) AS approved_applications,
    SUM(CASE WHEN is_decided = 1 THEN decision_days END) AS decision_days_total,
    SUM(is_manual_review) AS manual_reviews,
    COUNT(dti_ratio) AS applications_with_dti,
    COUNT_IF(dti_ratio >= 0.35) AS high_dti_applications,
    SUM(is_active_loan) AS active_loans,
    SUM(is_delinquent_30) AS delinquent_loans_30,
    SUM(outstanding_balance) AS outstanding_balance
FROM fact_loan_application
GROUP BY CAST(application_date_key / 100 AS INT), branch_key, product_key;


CREATE OR REFRESH MATERIALIZED VIEW kpi_portfolio_summary
COMMENT 'The 8 governed KPIs for the whole portfolio. Power BI and the API must show these values'
AS
SELECT
    COUNT(*) AS applications,
    SUM(requested_amount) AS requested_amount,
    ROUND(TRY_DIVIDE(SUM(is_approved), SUM(is_decided)), 4) AS approval_rate,
    ROUND(AVG(CASE WHEN is_decided = 1 THEN decision_days END), 3) AS avg_decision_days,
    ROUND(TRY_DIVIDE(COUNT_IF(dti_band = '1. Below 20%'), COUNT(dti_ratio)), 4) AS dti_share_below_20,
    ROUND(TRY_DIVIDE(COUNT_IF(dti_band = '2. 20-35%'), COUNT(dti_ratio)), 4) AS dti_share_20_35,
    ROUND(TRY_DIVIDE(COUNT_IF(dti_band = '3. 35-50%'), COUNT(dti_ratio)), 4) AS dti_share_35_50,
    ROUND(TRY_DIVIDE(COUNT_IF(dti_band = '4. Above 50%'), COUNT(dti_ratio)), 4) AS dti_share_above_50,
    ROUND(TRY_DIVIDE(SUM(is_delinquent_30), SUM(is_active_loan)), 4) AS delinquency_rate_30,
    SUM(outstanding_balance) AS outstanding_balance,
    ROUND(AVG(is_manual_review), 4) AS manual_review_rate
FROM fact_loan_application;


CREATE OR REFRESH MATERIALIZED VIEW kpi_open_installment_ageing
COMMENT 'Open (partial or missed) installments by days past due at the as-of date; they are never written off'
AS
SELECT
    ageing_bucket,
    COUNT(*) AS open_installments,
    COUNT(DISTINCT application_id) AS loans,
    SUM(amount_unpaid) AS amount_unpaid
FROM fact_repayment
WHERE is_open = 1
GROUP BY ageing_bucket;


CREATE OR REFRESH MATERIALIZED VIEW refresh_info
COMMENT 'One row: data complete up to as_of_date, refreshed at refreshed_at, batches loaded'
AS
SELECT
    MAX(application_date) AS as_of_date,
    current_timestamp() AS refreshed_at,
    array_join(array_sort(collect_set(batch_id)), ', ') AS batches_loaded
FROM silver_loan_applications;
