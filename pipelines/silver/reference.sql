-- Silver | branches, products and monthly macro data (reference data) | Owner: P1
-- Typed and trimmed. If a key is delivered more than once, the newest delivery wins
-- (macroeconomic_monthly.csv contains one month twice in batch_001).

CREATE OR REFRESH MATERIALIZED VIEW silver_branches
COMMENT 'Bank branches, one row per branch_code'
AS
SELECT * EXCEPT (rn)
FROM (
    SELECT
        UPPER(TRIM(branch_code)) AS branch_code,
        TRIM(branch_name) AS branch_name,
        TRIM(city) AS city,
        TRIM(region) AS region,
        CAST(TRY_TO_TIMESTAMP(TRIM(opened_date), 'yyyy-MM-dd') AS DATE) AS opened_date,
        batch_id,
        source_file,
        ROW_NUMBER() OVER (PARTITION BY UPPER(TRIM(branch_code)) ORDER BY batch_id DESC, ingest_ts DESC) AS rn
    FROM bronze_branches
)
WHERE rn = 1;


CREATE OR REFRESH MATERIALIZED VIEW silver_products
COMMENT 'Loan products with their allowed amount and term ranges, one row per product_code'
AS
SELECT * EXCEPT (rn)
FROM (
    SELECT
        UPPER(TRIM(product_code)) AS product_code,
        TRIM(product_name) AS product_name,
        TRIM(product_family) AS product_family,
        TRY_CAST(TRIM(min_amount) AS DECIMAL(14,2)) AS min_amount,
        TRY_CAST(TRIM(max_amount) AS DECIMAL(14,2)) AS max_amount,
        TRY_CAST(TRIM(min_term_months) AS INT) AS min_term_months,
        TRY_CAST(TRIM(max_term_months) AS INT) AS max_term_months,
        TRY_CAST(TRIM(base_rate) AS DECIMAL(6,4)) AS base_rate,
        batch_id,
        source_file,
        ROW_NUMBER() OVER (PARTITION BY UPPER(TRIM(product_code)) ORDER BY batch_id DESC, ingest_ts DESC) AS rn
    FROM bronze_products
)
WHERE rn = 1;


CREATE OR REFRESH MATERIALIZED VIEW silver_macro_monthly (
    CONSTRAINT mac_01_confidence_present EXPECT (NOT array_contains(failed_rules, 'MAC-01'))
)
COMMENT 'Monthly economic context (synthetic, Greece-like), one row per month; rates in percent'
AS
SELECT
    * EXCEPT (rn),
    filter(array(
        CASE WHEN consumer_confidence_index IS NULL THEN 'MAC-01' END
    ), r -> r IS NOT NULL) AS failed_rules
FROM (
    SELECT
        TRIM(month) AS month,
        CAST(REPLACE(TRIM(month), '-', '') AS INT) AS month_key,
        TRY_CAST(TRIM(inflation_rate) AS DECIMAL(6,2)) AS inflation_rate,
        TRY_CAST(TRIM(unemployment_rate) AS DECIMAL(6,2)) AS unemployment_rate,
        TRY_CAST(TRIM(reference_rate) AS DECIMAL(6,2)) AS reference_rate,
        TRY_CAST(TRIM(consumer_confidence_index) AS DECIMAL(6,1)) AS consumer_confidence_index,
        batch_id,
        source_file,
        ingest_ts,
        ROW_NUMBER() OVER (PARTITION BY TRIM(month) ORDER BY batch_id DESC, ingest_ts DESC) AS rn
    FROM bronze_macroeconomic_monthly
)
WHERE rn = 1;
