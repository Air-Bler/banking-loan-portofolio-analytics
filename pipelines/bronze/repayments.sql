-- Bronze | repayments.csv (loan servicing: one row per installment version) | Owner: P1
-- Lands every row of every delivery unchanged (all columns as text, defects included) and adds the
-- audit columns the brief asks for: source file, ingestion time, batch id, source-system key,
-- record hash, load status. Auto Loader remembers which files it has read, so a re-run never
-- loads a file twice. If your catalog, schema or volume differ, change the path in read_files below.

CREATE OR REFRESH STREAMING TABLE bronze_repayments
COMMENT 'repayments.csv rows from every delivery batch, unchanged, plus audit columns'
AS
SELECT
    repayment_id, application_id, installment_number, due_date, principal_due, interest_due,
    total_due, payment_date, principal_paid, interest_paid, total_paid, payment_status,
    days_past_due, currency, updated_at,
    _rescued_data,
    'loan_servicing' AS source_system,
    repayment_id AS source_key,
    _metadata.file_path AS source_file,
    _metadata.file_modification_time AS source_file_modified_at,
    regexp_extract(_metadata.file_path, 'batch_[0-9]+', 0) AS batch_id,
    current_timestamp() AS ingest_ts,
    sha2(to_json(struct(
        repayment_id, application_id, installment_number, due_date, principal_due, interest_due,
        total_due, payment_date, principal_paid, interest_paid, total_paid, payment_status,
        days_past_due, currency, updated_at
    )), 256) AS record_hash,
    CASE WHEN _rescued_data IS NULL THEN 'OK' ELSE 'RESCUED' END AS load_status
FROM STREAM read_files(
    '/Volumes/data2026acc123456/team2/raw_data/loans/batch_*/repayments.csv',
    format => 'csv',
    header => true,
    schema => '
        repayment_id STRING, application_id STRING, installment_number STRING, due_date STRING,
        principal_due STRING, interest_due STRING, total_due STRING, payment_date STRING,
        principal_paid STRING, interest_paid STRING, total_paid STRING, payment_status STRING,
        days_past_due STRING, currency STRING, updated_at STRING
    ',
    rescuedDataColumn => '_rescued_data'
);
