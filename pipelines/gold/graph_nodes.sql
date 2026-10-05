-- Gold | knowledge graph nodes (5% bonus) | Owners: P2a builds, P3 queries
-- Node types: Customer, Household, Application, Branch, Product.
-- Customer and household ids are one-way hashes, the same hash as customer_key in the fact.

CREATE OR REFRESH MATERIALIZED VIEW kg_nodes
COMMENT 'Knowledge graph nodes: node_id = type:id'
AS
WITH current_customers AS (
    SELECT
        SUBSTRING(SHA2(customer_id, 256), 1, 16) AS customer_key,
        SUBSTRING(SHA2(household_id, 256), 1, 16) AS household_key,
        segment_code
    FROM silver_customers_current
)
SELECT CONCAT('customer:', customer_key) AS node_id, 'Customer' AS node_type, customer_key AS label,
       to_json(named_struct('segment_code', segment_code)) AS properties
FROM current_customers

UNION ALL

SELECT DISTINCT CONCAT('household:', household_key), 'Household', household_key, '{}'
FROM current_customers
WHERE household_key IS NOT NULL

UNION ALL

SELECT CONCAT('application:', f.application_id), 'Application', f.application_id,
       to_json(named_struct(
           'status_code', s.status_code,
           'requested_amount', f.requested_amount,
           'outstanding_balance', f.outstanding_balance,
           'max_open_days_past_due', f.max_open_days_past_due,
           'is_delinquent_30', f.is_delinquent_30))
FROM fact_loan_application f
JOIN dim_application_status s ON f.status_key = s.status_key

UNION ALL

SELECT CONCAT('branch:', branch_code), 'Branch', branch_name, to_json(named_struct('region', region))
FROM dim_branch
WHERE branch_key <> -1

UNION ALL

SELECT CONCAT('product:', product_code), 'Product', product_name,
       to_json(named_struct('product_family', product_family))
FROM dim_product
WHERE product_key <> -1;
