-- Bronze | loan_applications.csv (loan origination system) | Owner: P1
-- Lands every row of every delivery unchanged (all columns as text, defects included) and adds the
-- audit columns the brief asks for: source file, ingestion time, batch id, source-system key,
-- record hash, load status. Auto Loader remembers which files it has read, so a re-run never
-- loads a file twice. If your catalog, schema or volume differ, change the path in read_files below.

CREATE OR REFRESH STREAMING TABLE bronze_loan_applications
COMMENT 'loan_applications.csv rows from every delivery batch, unchanged, plus audit columns'
AS
SELECT
    application_id, customer_id, branch_code, product_code, application_date, decision_date,
    status, requested_amount, approved_amount, currency, term_months, interest_rate, risk_score,
    monthly_debt, annual_income_at_application, employment_status_at_application,
    declared_monthly_expenses, consent_flag, manual_review, updated_at, channel,
    _rescued_data,
    'loan_origination' AS source_system,
    application_id AS source_key,
    _metadata.file_path AS source_file,
    _metadata.file_modification_time AS source_file_modified_at,
    regexp_extract(_metadata.file_path, 'batch_[0-9]+', 0) AS batch_id,
    current_timestamp() AS ingest_ts,
    sha2(to_json(struct(
        application_id, customer_id, branch_code, product_code, application_date, decision_date,
        status, requested_amount, approved_amount, currency, term_months, interest_rate,
        risk_score, monthly_debt, annual_income_at_application, employment_status_at_application,
        declared_monthly_expenses, consent_flag, manual_review, updated_at, channel
    )), 256) AS record_hash,
    CASE WHEN _rescued_data IS NULL THEN 'OK' ELSE 'RESCUED' END AS load_status
FROM STREAM read_files(
    '/Volumes/data2026acc123456/team2/raw_data/loans/batch_*/loan_applications.csv',
    format => 'csv',
    header => true,
    schema => '
        application_id STRING, customer_id STRING, branch_code STRING, product_code STRING,
        application_date STRING, decision_date STRING, status STRING, requested_amount STRING,
        approved_amount STRING, currency STRING, term_months STRING, interest_rate STRING,
        risk_score STRING, monthly_debt STRING, annual_income_at_application STRING,
        employment_status_at_application STRING, declared_monthly_expenses STRING,
        consent_flag STRING, manual_review STRING, updated_at STRING, channel STRING
    ',
    rescuedDataColumn => '_rescued_data'
);
