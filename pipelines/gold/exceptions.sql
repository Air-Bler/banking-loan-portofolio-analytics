-- Gold | fact_dq_exception (the Exceptions report page and the /exceptions API) | Owner: P2a
-- Grain: one record that fails one quality rule, from silver_quarantine.
-- A business date outside the calendar (for example year 2036) gets a NULL date key.

CREATE OR REFRESH MATERIALIZED VIEW fact_dq_exception
COMMENT 'Grain: one record failing one quality rule. Current state of silver_quarantine'
AS
WITH calendar AS (
    SELECT MIN(date) AS first_day, MAX(date) AS last_day FROM dim_date
)
SELECT
    xxhash64(q.entity, q.record_key, q.rule_id) AS exception_key,
    q.rule_id,
    q.dq_dimension,
    q.action,
    q.description,
    q.resolution,
    q.entity,
    q.record_key,
    COALESCE(b.branch_key, -1) AS branch_key,
    CASE
        WHEN q.business_date BETWEEN c.first_day AND c.last_day
            THEN CAST(DATE_FORMAT(q.business_date, 'yyyyMMdd') AS INT)
    END AS business_date_key,
    q.record_payload,
    q.source_batch_id,
    q.source_file,
    q.received_at,
    q.processed_at AS detected_at
FROM silver_quarantine q
CROSS JOIN calendar c
LEFT JOIN dim_branch b ON q.branch_code = b.branch_code AND b.branch_key <> -1;
