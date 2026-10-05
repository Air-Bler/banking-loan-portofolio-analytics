-- Gold | dim_date | Owner: P2a
-- A continuous calendar (every day, no gaps) from 1 January of the first application year to
-- 31 December of the last (2016-2025). Power BI needs this to mark it as the date table and for
-- time intelligence such as previous month. (The class template built it only from dates that
-- appear in the fact, which leaves gaps.)

CREATE OR REFRESH MATERIALIZED VIEW dim_date
COMMENT 'Calendar, one row per day, no gaps. Mark as date table in Power BI on column date'
AS
WITH bounds AS (
    SELECT
        MAKE_DATE(YEAR(MIN(application_date)), 1, 1) AS first_day,
        MAKE_DATE(YEAR(MAX(application_date)), 12, 31) AS last_day
    FROM silver_loan_applications
),
days AS (
    SELECT explode(sequence(first_day, last_day, INTERVAL 1 DAY)) AS d
    FROM bounds
)
SELECT
    CAST(DATE_FORMAT(d, 'yyyyMMdd') AS INT) AS date_key,
    d AS date,
    YEAR(d) AS year,
    QUARTER(d) AS quarter,
    CONCAT('Q', QUARTER(d)) AS quarter_name,
    MONTH(d) AS month,
    DATE_FORMAT(d, 'MMMM') AS month_name,
    DATE_FORMAT(d, 'yyyy-MM') AS year_month,
    YEAR(d) * 100 + MONTH(d) AS month_key,
    DAYOFWEEK(d) AS day_of_week,                       -- 1 = Sunday ... 7 = Saturday
    DATE_FORMAT(d, 'EEEE') AS day_name,
    CASE WHEN DAYOFWEEK(d) IN (1, 7) THEN 1 ELSE 0 END AS is_weekend
FROM days;
