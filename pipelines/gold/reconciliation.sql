-- Gold | Silver-to-Gold reconciliation | Owner: P2a
-- Compares row counts and money totals between Silver and Gold on every run.
-- The expectation is ON VIOLATION FAIL UPDATE: if any check fails, the pipeline update fails and the
-- team is e-mailed, so a wrong number never reaches the report unnoticed.

CREATE OR REFRESH MATERIALIZED VIEW reconciliation (
    CONSTRAINT all_checks_pass EXPECT (status = 'PASS') ON VIOLATION FAIL UPDATE
)
COMMENT 'Silver-to-Gold reconciliation; any FAIL fails the pipeline update'
AS
WITH checks AS (
    SELECT 'Applications: rows' AS check_name,
           CAST((SELECT COUNT(*) FROM silver_loan_applications) AS DOUBLE) AS silver_value,
           CAST((SELECT COUNT(*) FROM fact_loan_application) AS DOUBLE) AS gold_value
    UNION ALL
    SELECT 'Applications: requested amount',
           CAST((SELECT SUM(requested_amount) FROM silver_loan_applications) AS DOUBLE),
           CAST((SELECT SUM(requested_amount) FROM fact_loan_application) AS DOUBLE)
    UNION ALL
    SELECT 'Applications: approved amount',
           CAST((SELECT SUM(approved_amount) FROM silver_loan_applications) AS DOUBLE),
           CAST((SELECT SUM(approved_amount) FROM fact_loan_application) AS DOUBLE)
    UNION ALL
    SELECT 'Installments: rows',
           CAST((SELECT COUNT(*) FROM silver_repayments) AS DOUBLE),
           CAST((SELECT COUNT(*) FROM fact_repayment) AS DOUBLE)
    UNION ALL
    SELECT 'Installments: total due',
           CAST((SELECT SUM(total_due) FROM silver_repayments) AS DOUBLE),
           CAST((SELECT SUM(total_due) FROM fact_repayment) AS DOUBLE)
    UNION ALL
    SELECT 'Installments: total paid',
           CAST((SELECT SUM(total_paid) FROM silver_repayments) AS DOUBLE),
           CAST((SELECT SUM(total_paid) FROM fact_repayment) AS DOUBLE)
    UNION ALL
    SELECT 'Exceptions: rows = quarantine rows',
           CAST((SELECT COUNT(*) FROM silver_quarantine) AS DOUBLE),
           CAST((SELECT COUNT(*) FROM fact_dq_exception) AS DOUBLE)
    UNION ALL
    SELECT 'Applications: rows with a NULL dimension key',
           CAST(0 AS DOUBLE),
           CAST((SELECT COUNT(*) FROM fact_loan_application
                 WHERE branch_key IS NULL OR product_key IS NULL OR customer_segment_key IS NULL
                    OR risk_band_key IS NULL OR status_key IS NULL OR application_date_key IS NULL) AS DOUBLE)
    UNION ALL
    SELECT 'Loans: outstanding balance above approved amount',
           CAST(0 AS DOUBLE),
           CAST((SELECT COUNT(*) FROM fact_loan_application WHERE outstanding_balance > approved_amount) AS DOUBLE)
)
SELECT
    check_name,
    silver_value,
    gold_value,
    CASE WHEN ABS(COALESCE(silver_value, 0) - COALESCE(gold_value, 0)) < 0.005 THEN 'PASS' ELSE 'FAIL' END AS status,
    current_timestamp() AS checked_at
FROM checks;
