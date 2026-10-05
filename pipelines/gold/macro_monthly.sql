-- Gold | macro_monthly | Owner: P2a
-- Monthly economic context, joined to the facts by month (application month, due month).
-- In Power BI relate it to dim_date on month_key (many dates to one month) or use it in tooltips.

CREATE OR REFRESH MATERIALIZED VIEW macro_monthly
COMMENT 'Monthly synthetic Greece-like economic indicators (rates in percent), one row per month_key yyyymm'
AS
SELECT
    month_key,
    TO_DATE(CONCAT(month, '-01')) AS month_start,
    inflation_rate,
    unemployment_rate,
    reference_rate,
    consumer_confidence_index
FROM silver_macro_monthly;
