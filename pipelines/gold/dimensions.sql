-- Gold | dimensions | Owner: P2a
-- Every dimension has an Unknown member with key -1: a fact row whose code is missing or not found
-- points to it, so no fact row is ever lost and totals always reconcile.
-- Keys are xxhash64(code): the same code always gets the same key, on every rebuild.
-- No personal data in Gold: customers appear only as a segment and a hashed key in the fact.

CREATE OR REFRESH MATERIALIZED VIEW dim_branch
COMMENT 'Bank branches; region is the row-level security boundary in Power BI. Key -1 = Unknown branch'
AS
SELECT xxhash64(branch_code) AS branch_key, branch_code, branch_name, city, region, opened_date
FROM silver_branches
UNION ALL
SELECT CAST(-1 AS BIGINT), 'UNKNOWN', 'Unknown branch', 'Unknown', 'Unknown', CAST(NULL AS DATE);


CREATE OR REFRESH MATERIALIZED VIEW dim_product
COMMENT 'Loan products. Key -1 = Unknown product'
AS
SELECT
    xxhash64(product_code) AS product_key, product_code, product_name, product_family,
    min_amount, max_amount, min_term_months, max_term_months, base_rate
FROM silver_products
UNION ALL
SELECT
    CAST(-1 AS BIGINT), 'UNKNOWN', 'Unknown product', 'Unknown',
    CAST(NULL AS DECIMAL(14,2)), CAST(NULL AS DECIMAL(14,2)), CAST(NULL AS INT), CAST(NULL AS INT),
    CAST(NULL AS DECIMAL(6,4));


CREATE OR REFRESH MATERIALIZED VIEW dim_customer_segment
COMMENT 'Customer segments (current segment of the customer). Key -1 = customer or segment unknown'
AS
SELECT xxhash64(segment_code) AS customer_segment_key, segment_code, segment_name, description
FROM VALUES
    ('MASS',     'Mass retail',    'Everyday banking customers'),
    ('AFFLUENT', 'Affluent',       'Customers with higher income and savings'),
    ('PREMIER',  'Premier',        'Premium relationship-managed customers'),
    ('SME',      'Small business', 'Sole traders and small companies')
    AS s(segment_code, segment_name, description)
UNION ALL
SELECT CAST(-1 AS BIGINT), 'UNKNOWN', 'Unknown segment', 'Customer not found or segment missing';


CREATE OR REFRESH MATERIALIZED VIEW dim_risk_band
COMMENT 'Credit risk bands by application risk score (higher = safer). Key -1 = score missing or outside 300-850'
AS
SELECT xxhash64(risk_band_code) AS risk_band_key, risk_band_code, risk_band_name, min_score, max_score, sort_order
FROM VALUES
    ('A', 'Excellent (800-850)', 800, 850, 1),
    ('B', 'Very good (740-799)', 740, 799, 2),
    ('C', 'Good (670-739)',      670, 739, 3),
    ('D', 'Fair (580-669)',      580, 669, 4),
    ('E', 'Poor (300-579)',      300, 579, 5)
    AS r(risk_band_code, risk_band_name, min_score, max_score, sort_order)
UNION ALL
SELECT CAST(-1 AS BIGINT), 'U', 'Unknown (score missing or out of range)', CAST(NULL AS INT), CAST(NULL AS INT), 9;


CREATE OR REFRESH MATERIALIZED VIEW dim_application_status
COMMENT 'Application status with the flags the funnel and approval rate use. Key -1 = Unknown'
AS
SELECT xxhash64(status_code) AS status_key, status_code, status_name, is_final, is_decided, is_approved, sort_order
FROM VALUES
    ('SUBMITTED',    'Submitted, not decided yet', 0, 0, 0, 1),
    ('UNDER_REVIEW', 'Under review',               0, 0, 0, 2),
    ('APPROVED',     'Approved',                   1, 1, 1, 3),
    ('REJECTED',     'Rejected',                   1, 1, 0, 4),
    ('WITHDRAWN',    'Withdrawn by customer',      1, 0, 0, 5)
    AS s(status_code, status_name, is_final, is_decided, is_approved, sort_order)
UNION ALL
SELECT CAST(-1 AS BIGINT), 'UNKNOWN', 'Unknown status', 0, 0, 0, 9;
