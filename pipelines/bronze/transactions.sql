-- Bronze | transactions.json (payment and cash-flow events, JSON Lines) | Owner: P1
-- Each line is kept exactly as delivered, as raw JSON text; Silver parses and flattens it.
-- A line that is not valid JSON (the 4 truncated lines) is kept here with load_status = 'CORRUPT',
-- never reaches Silver, and is listed in the quarantine as rule TRX-00.
-- If your catalog, schema or volume differ, change the path in read_files below.

CREATE OR REFRESH STREAMING TABLE bronze_transactions
COMMENT 'transactions.json lines from every delivery batch, unchanged as raw JSON text, plus audit columns'
AS
SELECT
    value AS raw_json,
    'core_banking' AS source_system,
    NULLIF(regexp_extract(value, '"event_id": *"([^"]*)"', 1), '') AS source_key,   -- also works on a broken line
    _metadata.file_path AS source_file,
    _metadata.file_modification_time AS source_file_modified_at,
    regexp_extract(_metadata.file_path, 'batch_[0-9]+', 0) AS batch_id,
    current_timestamp() AS ingest_ts,
    sha2(value, 256) AS record_hash,
    CASE WHEN try_parse_json(value) IS NULL THEN 'CORRUPT' ELSE 'OK' END AS load_status
FROM STREAM read_files(
    '/Volumes/data2026acc123456/team2/raw_data/loans/batch_*/transactions.json',
    format => 'text'
);
