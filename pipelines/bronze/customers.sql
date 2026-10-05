-- Bronze | customers.csv (CRM customer master; a customer is re-delivered when details change) | Owner: P1
-- Lands every row of every delivery unchanged (all columns as text, defects included) and adds the
-- audit columns the brief asks for: source file, ingestion time, batch id, source-system key,
-- record hash, load status. Auto Loader remembers which files it has read, so a re-run never
-- loads a file twice. If your catalog, schema or volume differ, change the path in read_files below.

CREATE OR REFRESH STREAMING TABLE bronze_customers
COMMENT 'customers.csv rows from every delivery batch, unchanged, plus audit columns'
AS
SELECT
    customer_id, first_name, last_name, email, phone, date_of_birth, segment, annual_income,
    household_id, employment_status, employment_start_date, created_at, updated_at,
    _rescued_data,
    'crm' AS source_system,
    customer_id AS source_key,
    _metadata.file_path AS source_file,
    _metadata.file_modification_time AS source_file_modified_at,
    regexp_extract(_metadata.file_path, 'batch_[0-9]+', 0) AS batch_id,
    current_timestamp() AS ingest_ts,
    sha2(to_json(struct(
        customer_id, first_name, last_name, email, phone, date_of_birth, segment, annual_income,
        household_id, employment_status, employment_start_date, created_at, updated_at
    )), 256) AS record_hash,
    CASE WHEN _rescued_data IS NULL THEN 'OK' ELSE 'RESCUED' END AS load_status
FROM STREAM read_files(
    '/Volumes/data2026acc123456/team2/raw_data/loans/batch_*/customers.csv',
    format => 'csv',
    header => true,
    schema => '
        customer_id STRING, first_name STRING, last_name STRING, email STRING, phone STRING,
        date_of_birth STRING, segment STRING, annual_income STRING, household_id STRING,
        employment_status STRING, employment_start_date STRING, created_at STRING,
        updated_at STRING
    ',
    rescuedDataColumn => '_rescued_data'
);
