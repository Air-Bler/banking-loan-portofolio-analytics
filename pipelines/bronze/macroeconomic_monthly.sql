-- Bronze | macroeconomic_monthly.csv (monthly economic context) | Owner: P1
-- Lands every row of every delivery unchanged (all columns as text, defects included) and adds the
-- audit columns the brief asks for: source file, ingestion time, batch id, source-system key,
-- record hash, load status. Auto Loader remembers which files it has read, so a re-run never
-- loads a file twice. If your catalog, schema or volume differ, change the path in read_files below.

CREATE OR REFRESH STREAMING TABLE bronze_macroeconomic_monthly
COMMENT 'macroeconomic_monthly.csv rows from every delivery batch, unchanged, plus audit columns'
AS
SELECT
    month, inflation_rate, unemployment_rate, reference_rate, consumer_confidence_index,
    _rescued_data,
    'macro_feed' AS source_system,
    month AS source_key,
    _metadata.file_path AS source_file,
    _metadata.file_modification_time AS source_file_modified_at,
    regexp_extract(_metadata.file_path, 'batch_[0-9]+', 0) AS batch_id,
    current_timestamp() AS ingest_ts,
    sha2(to_json(struct(
        month, inflation_rate, unemployment_rate, reference_rate, consumer_confidence_index
    )), 256) AS record_hash,
    CASE WHEN _rescued_data IS NULL THEN 'OK' ELSE 'RESCUED' END AS load_status
FROM STREAM read_files(
    '/Volumes/data2026acc123456/team2/raw_data/loans/batch_*/macroeconomic_monthly.csv',
    format => 'csv',
    header => true,
    schema => '
        month STRING, inflation_rate STRING, unemployment_rate STRING, reference_rate STRING,
        consumer_confidence_index STRING
    ',
    rescuedDataColumn => '_rescued_data'
);
