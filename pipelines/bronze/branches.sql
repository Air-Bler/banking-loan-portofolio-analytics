-- Bronze | branches.csv (reference data, delivered once in batch_001) | Owner: P1
-- Lands every row of every delivery unchanged (all columns as text, defects included) and adds the
-- audit columns the brief asks for: source file, ingestion time, batch id, source-system key,
-- record hash, load status. Auto Loader remembers which files it has read, so a re-run never
-- loads a file twice. If your catalog, schema or volume differ, change the path in read_files below.

CREATE OR REFRESH STREAMING TABLE bronze_branches
COMMENT 'branches.csv rows from every delivery batch, unchanged, plus audit columns'
AS
SELECT
    branch_code, branch_name, city, region, opened_date,
    _rescued_data,
    'reference_data' AS source_system,
    branch_code AS source_key,
    _metadata.file_path AS source_file,
    _metadata.file_modification_time AS source_file_modified_at,
    regexp_extract(_metadata.file_path, 'batch_[0-9]+', 0) AS batch_id,
    current_timestamp() AS ingest_ts,
    sha2(to_json(struct(
        branch_code, branch_name, city, region, opened_date
    )), 256) AS record_hash,
    CASE WHEN _rescued_data IS NULL THEN 'OK' ELSE 'RESCUED' END AS load_status
FROM STREAM read_files(
    '/Volumes/data2026acc123456/team2/raw_data/loans/batch_*/branches.csv',
    format => 'csv',
    header => true,
    schema => '
        branch_code STRING, branch_name STRING, city STRING, region STRING, opened_date STRING
    ',
    rescuedDataColumn => '_rescued_data'
);
