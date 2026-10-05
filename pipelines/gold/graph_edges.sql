-- Gold | knowledge graph edges (5% bonus) | Owners: P2a builds, P3 queries
-- Customer -MEMBER_OF-> Household, Customer -APPLIED_FOR-> Application,
-- Application -AT_BRANCH-> Branch, Application -FOR_PRODUCT-> Product.
-- Answers "household exposure of application X": application <- customer -> household <- customers -> applications.

CREATE OR REFRESH MATERIALIZED VIEW kg_edges
COMMENT 'Knowledge graph edges: source_id, target_id, relationship'
AS
WITH current_customers AS (
    SELECT
        SUBSTRING(SHA2(customer_id, 256), 1, 16) AS customer_key,
        SUBSTRING(SHA2(household_id, 256), 1, 16) AS household_key
    FROM silver_customers_current
)
SELECT CONCAT('customer:', customer_key) AS source_id, CONCAT('household:', household_key) AS target_id,
       'MEMBER_OF' AS relationship
FROM current_customers
WHERE household_key IS NOT NULL

UNION ALL

SELECT CONCAT('customer:', f.customer_key), CONCAT('application:', f.application_id), 'APPLIED_FOR'
FROM fact_loan_application f
JOIN current_customers c ON f.customer_key = c.customer_key

UNION ALL

SELECT CONCAT('application:', f.application_id), CONCAT('branch:', b.branch_code), 'AT_BRANCH'
FROM fact_loan_application f
JOIN dim_branch b ON f.branch_key = b.branch_key
WHERE f.branch_key <> -1

UNION ALL

SELECT CONCAT('application:', f.application_id), CONCAT('product:', p.product_code), 'FOR_PRODUCT'
FROM fact_loan_application f
JOIN dim_product p ON f.product_key = p.product_key
WHERE f.product_key <> -1;
