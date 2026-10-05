-- Silver | customers | Owner: P1
-- 1. silver_customers_clean    every delivered version, standardised (streaming, append only)
--      names title-cased, e-mail lower-cased, phone to +30XXXXXXXXXX, two birth-date formats read,
--      codes upper-cased and trimmed
-- 2. silver_customers          AUTO CDC keeps each customer's history (SCD type 2): a change of segment,
--      income or contact details closes the old row (__END_AT) and opens a new one
-- 3. silver_customers_current  the current version of each customer plus the quality rules it fails.
--      All customer rules are FLAG rules: the customer is kept, the bad value is shown as unknown.
-- Personal data stays in Silver (restricted); Gold holds none of it.

CREATE OR REFRESH STREAMING TABLE silver_customers_clean
COMMENT 'Standardised customer rows, every delivered version'
AS
WITH s AS (
    SELECT
        *,
        regexp_replace(COALESCE(phone, ''), '[^0-9]', '') AS phone_digits
    FROM STREAM(bronze_customers)
),
p AS (
    SELECT
        *,
        -- drop the country code: 0030XXXXXXXXXX or 30XXXXXXXXXX -> XXXXXXXXXX
        CASE
            WHEN phone_digits LIKE '0030%' THEN SUBSTRING(phone_digits, 5)
            WHEN phone_digits LIKE '30%' AND LENGTH(phone_digits) = 12 THEN SUBSTRING(phone_digits, 3)
            ELSE phone_digits
        END AS phone_national
    FROM s
)
SELECT
    UPPER(TRIM(customer_id)) AS customer_id,
    INITCAP(TRIM(first_name)) AS first_name,                          -- 'baka', 'ILIAS' -> Baka, Ilias
    INITCAP(TRIM(last_name)) AS last_name,
    NULLIF(LOWER(TRIM(email)), '') AS email,
    NULLIF(TRIM(phone), '') AS phone_raw,
    -- valid Greek number: mobile 69XXXXXXXX or landline 2XXXXXXXXX
    CASE WHEN phone_national RLIKE '^(69[0-9]{8}|2[0-9]{9})$' THEN CONCAT('+30', phone_national) END AS phone,
    COALESCE(
        CAST(TRY_TO_TIMESTAMP(TRIM(date_of_birth), 'yyyy-MM-dd') AS DATE),
        CAST(TRY_TO_TIMESTAMP(TRIM(date_of_birth), 'dd/MM/yyyy') AS DATE)
    ) AS date_of_birth,
    NULLIF(UPPER(TRIM(segment)), '') AS segment_code,                 -- ' MASS ', 'mass' -> MASS
    TRY_CAST(TRIM(annual_income) AS DECIMAL(14,2)) AS annual_income,
    NULLIF(UPPER(TRIM(household_id)), '') AS household_id,
    NULLIF(UPPER(TRIM(employment_status)), '') AS employment_status,
    CAST(TRY_TO_TIMESTAMP(TRIM(employment_start_date), 'yyyy-MM-dd') AS DATE) AS employment_start_date,
    TRY_TO_TIMESTAMP(TRIM(created_at)) AS created_at,
    TRY_TO_TIMESTAMP(TRIM(updated_at)) AS updated_at,
    batch_id,
    source_file,
    ingest_ts,
    record_hash
FROM p
WHERE NULLIF(TRIM(customer_id), '') IS NOT NULL;


CREATE OR REFRESH STREAMING TABLE silver_customers
COMMENT 'Customer history (SCD type 2). Current version: __END_AT IS NULL';

CREATE FLOW silver_customers_cdc
AS AUTO CDC INTO silver_customers
FROM STREAM(silver_customers_clean)
KEYS (customer_id)
SEQUENCE BY updated_at
STORED AS SCD TYPE 2;


CREATE OR REFRESH MATERIALIZED VIEW silver_customers_current (
    CONSTRAINT cus_01_birth_date_possible  EXPECT (NOT array_contains(failed_rules, 'CUS-01')),
    CONSTRAINT cus_02_segment_known        EXPECT (NOT array_contains(failed_rules, 'CUS-02')),
    CONSTRAINT cus_03_income_present       EXPECT (NOT array_contains(failed_rules, 'CUS-03')),
    CONSTRAINT cus_04_email_valid          EXPECT (NOT array_contains(failed_rules, 'CUS-04')),
    CONSTRAINT cus_05_email_not_shared     EXPECT (NOT array_contains(failed_rules, 'CUS-05')),
    CONSTRAINT cus_06_phone_valid          EXPECT (NOT array_contains(failed_rules, 'CUS-06'))
)
COMMENT 'Current version of every customer with the quality rules it fails (FLAG only: every customer is kept)'
AS
WITH current_rows AS (
    SELECT
        *,
        COUNT(*) OVER (PARTITION BY email) AS customers_with_this_email
    FROM silver_customers
    WHERE __END_AT IS NULL
)
SELECT
    * EXCEPT (customers_with_this_email, __START_AT, __END_AT),
    filter(array(
        CASE WHEN date_of_birth IS NULL
                  OR date_of_birth > ADD_MONTHS(CURRENT_DATE(), -12 * 18)
                  OR date_of_birth < ADD_MONTHS(CURRENT_DATE(), -12 * 110) THEN 'CUS-01' END,
        CASE WHEN segment_code IS NULL OR segment_code NOT IN ('MASS', 'AFFLUENT', 'PREMIER', 'SME') THEN 'CUS-02' END,
        CASE WHEN annual_income IS NULL OR annual_income <= 0 THEN 'CUS-03' END,
        CASE WHEN email IS NULL
                  OR NOT email RLIKE '^[a-z0-9._%+-]+@[a-z0-9-]+([.][a-z0-9-]+)*[.][a-z]{2,}$' THEN 'CUS-04' END,
        CASE WHEN email IS NOT NULL AND customers_with_this_email > 1 THEN 'CUS-05' END,
        CASE WHEN phone IS NULL THEN 'CUS-06' END
    ), r -> r IS NOT NULL) AS failed_rules
FROM current_rows;
