-- Bronze | products.csv (reference data, delivered once in batch_001) | Owner: P1
-- Lands every row of every delivery unchanged (all columns as text, defects included) and adds the
-- audit columns the brief asks for: source file, ingestion time, batch id, source-system key,
-- record hash, load status. Auto Loader remembers which files it has read, so a re-run never
-- loads a file twice. If your catalog, schema or volume differ, change the path in read_files below.

CREATE OR REFRESH STREAMING TABLE bronze_products
COMMENT 'products.csv rows from every delivery batch, unchanged, plus audit columns'
AS
SELECT
    product_code, product_name, product_family, min_amount, max_amount, min_term_months,
    max_term_months, base_rate,
    _rescued_data,
    'reference_data' AS source_system,
    product_code AS source_key,
    _metadata.file_path AS source_file,
    _metadata.file_modification_time AS source_file_modified_at,
    regexp_extract(_metadata.file_path, 'batch_[0-9]+', 0) AS batch_id,
    current_timestamp() AS ingest_ts,
    sha2(to_json(struct(
        product_code, product_name, product_family, min_amount, max_amount, min_term_months,
        max_term_months, base_rate
    )), 256) AS record_hash,
    CASE WHEN _rescued_data IS NULL THEN 'OK' ELSE 'RESCUED' END AS load_status
FROM STREAM read_files(
    '/Volumes/data2026acc123456/team2/raw_data/loans/batch_*/products.csv',
    format => 'csv',
    header => true,
    schema => '
        product_code STRING, product_name STRING, product_family STRING, min_amount STRING,
        max_amount STRING, min_term_months STRING, max_term_months STRING, base_rate STRING
    ',
    rescuedDataColumn => '_rescued_data'
);
