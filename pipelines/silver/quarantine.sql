-- Silver | quality rules and quarantine | Owner: P1
-- silver_dq_rules:   one row per rule: what it checks, what happens, who fixes it
-- silver_quarantine: one row per record and failed rule, with reason, source file and processing time.
--   REJECT = the record is kept out of Silver.
--   FLAG   = the record is loaded (the bad value is recomputed or shown as Unknown) and also listed here.
--   Rebuilt on every run, so it always shows what is still wrong now.
-- Recoverable formatting problems are fixed in the *_clean tables and are not rules: two date formats,
-- whitespace and case, phone formats, euro spellings, event-type spellings, decimal commas.
-- Exact duplicate rows are removed by "newest version wins" and are not rules either.

CREATE OR REFRESH MATERIALIZED VIEW silver_dq_rules
COMMENT 'Data-quality rule catalogue'
AS
SELECT *
FROM VALUES
    ('CUS-01', 'customers', 'validity', 'FLAG', 'Birth date missing or impossible (under 18 or over 110)',
     'CRM corrects the birth date'),
    ('CUS-02', 'customers', 'completeness', 'FLAG', 'Segment missing or unknown',
     'CRM assigns the segment; reported as Unknown segment until then'),
    ('CUS-03', 'customers', 'completeness', 'FLAG', 'Annual income missing or not positive',
     'CRM captures the declared income'),
    ('CUS-04', 'customers', 'validity', 'FLAG', 'E-mail missing or malformed',
     'Branch confirms the e-mail with the customer'),
    ('CUS-05', 'customers', 'uniqueness', 'FLAG', 'E-mail shared with another customer',
     'Branch confirms which customer owns the e-mail'),
    ('CUS-06', 'customers', 'validity', 'FLAG', 'Phone missing or not a valid Greek number',
     'Branch confirms the phone number with the customer'),
    ('APP-01', 'loan_applications', 'completeness', 'REJECT', 'Customer id missing',
     'Origination system resends the application with the customer id'),
    ('APP-02', 'loan_applications', 'completeness', 'REJECT', 'Customer consent missing',
     'Branch captures the signed consent and resends the application'),
    ('APP-03', 'loan_applications', 'completeness', 'REJECT', 'Application status missing',
     'Origination system resends the current status'),
    ('APP-04', 'loan_applications', 'validity', 'REJECT', 'Unknown application status',
     'Map the status to the agreed code list and resend'),
    ('APP-05', 'loan_applications', 'validity', 'REJECT', 'Inconsistent amounts (not positive, approved above requested, approved amount on a non-approved application)',
     'Credit operations correct the amounts'),
    ('APP-06', 'loan_applications', 'validity', 'REJECT', 'Requested amount outside the product limits',
     'Credit operations correct the amount or the product'),
    ('APP-07', 'loan_applications', 'validity', 'REJECT', 'Impossible dates (decision before application, future or unreadable date)',
     'Correct the dates in the origination system'),
    ('APP-08', 'loan_applications', 'uniqueness', 'REJECT', 'Duplicate application delivered under another id',
     'Branch confirms the duplicate and cancels it at source'),
    ('APP-09', 'loan_applications', 'validity', 'REJECT', 'Currency is not EUR',
     'Origination system resends the application in EUR'),
    ('APP-10', 'loan_applications', 'validity', 'FLAG', 'Risk score missing or outside 300-850',
     'Risk team re-scores the application; risk band Unknown until then'),
    ('APP-11', 'loan_applications', 'integrity', 'FLAG', 'Customer not found in the customer master',
     'CRM delivers the customer; segment Unknown until then'),
    ('APP-12', 'loan_applications', 'integrity', 'FLAG', 'Branch or product code not in reference data',
     'Reference-data owner adds the code or the branch corrects it'),
    ('REP-01', 'repayments', 'integrity', 'REJECT', 'Orphan installment: its application was never delivered',
     'Loan servicing corrects the application id'),
    ('REP-02', 'repayments', 'integrity', 'REJECT', 'Installment whose application is quarantined or not approved',
     'Released automatically when the application is corrected'),
    ('REP-03', 'repayments', 'uniqueness', 'REJECT', 'Second installment row with the same loan and installment number',
     'Loan servicing removes the duplicate installment'),
    ('REP-04', 'repayments', 'validity', 'REJECT', 'Negative amount',
     'Loan servicing corrects the amount'),
    ('REP-05', 'repayments', 'validity', 'REJECT', 'Impossible or unreadable payment date (after the record was written, before the loan decision, more than a month before the due date, or missing on a settled installment)',
     'Loan servicing corrects the payment date'),
    ('REP-06', 'repayments', 'validity', 'REJECT', 'Currency is not EUR',
     'Loan servicing resends the installment in EUR'),
    ('REP-07', 'repayments', 'consistency', 'FLAG', 'Total due is not principal plus interest (total recomputed)',
     'Loan servicing corrects the total'),
    ('REP-08', 'repayments', 'consistency', 'FLAG', 'Status or days past due contradict the amounts and dates (recomputed)',
     'Loan servicing corrects the status calculation'),
    ('TRX-00', 'transactions', 'validity', 'REJECT', 'Event line is not valid JSON',
     'Source system resends the event'),
    ('TRX-01', 'transactions', 'validity', 'REJECT', 'Unknown event type',
     'Source system maps the event to a known type'),
    ('TRX-02', 'transactions', 'completeness', 'REJECT', 'Required field missing (id, customer, time, amount, currency or account)',
     'Source system resends the complete event'),
    ('TRX-03', 'transactions', 'validity', 'REJECT', 'Impossible event time (unreadable, before 2016 or in the future)',
     'Source system corrects the timestamp'),
    ('TRX-04', 'transactions', 'validity', 'REJECT', 'Amount not a positive number',
     'Source system corrects the amount'),
    ('TRX-05', 'transactions', 'validity', 'REJECT', 'Currency is not EUR',
     'Source system resends the event in EUR'),
    ('TRX-06', 'transactions', 'integrity', 'REJECT', 'Customer not found in the customer master',
     'Source system corrects the customer id'),
    ('TRX-07', 'transactions', 'integrity', 'REJECT', 'Loan repayment for an installment that was never delivered',
     'Core banking corrects the installment reference'),
    ('TRX-08', 'transactions', 'integrity', 'REJECT', 'Loan repayment whose application differs from the loan of the installment',
     'Core banking corrects the application reference'),
    ('TRX-09', 'transactions', 'integrity', 'REJECT', 'Loan repayment for an installment that is quarantined',
     'Released automatically when the installment is corrected'),
    ('MAC-01', 'macroeconomic_monthly', 'completeness', 'FLAG', 'Consumer confidence index missing (optional indicator)',
     'Economics team fills the indicator')
AS rules(rule_id, entity, dq_dimension, action, description, resolution);


CREATE OR REFRESH MATERIALIZED VIEW silver_quarantine
COMMENT 'One row per record and failed rule: reason, action, resolution, source file and processing time'
AS
WITH failures AS (
    SELECT
        explode(failed_rules) AS rule_id, 'customers' AS entity, customer_id AS record_key,
        CAST(NULL AS STRING) AS branch_code, CAST(created_at AS DATE) AS business_date,
        to_json(struct(customer_id, date_of_birth, segment_code, annual_income, email, phone_raw)) AS record_payload,
        batch_id, source_file, ingest_ts
    FROM silver_customers_current

    UNION ALL

    SELECT
        explode(failed_rules), 'loan_applications', application_id, branch_code, application_date,
        to_json(struct(application_id, customer_id, branch_code, product_code, status, application_date,
                       decision_date_raw, requested_amount, approved_amount, currency, risk_score, consent_flag)),
        batch_id, source_file, ingest_ts
    FROM silver_loan_applications_checked

    UNION ALL

    SELECT
        explode(failed_rules), 'repayments', repayment_id, CAST(NULL AS STRING), due_date,
        to_json(struct(repayment_id, application_id, installment_number, due_date, principal_due, interest_due,
                       total_due_delivered, payment_date_raw, total_paid, payment_status_delivered,
                       days_past_due_delivered, currency)),
        batch_id, source_file, ingest_ts
    FROM silver_repayments_checked

    UNION ALL

    SELECT
        explode(failed_rules), 'transactions', event_id, CAST(NULL AS STRING), event_date,
        to_json(struct(event_id, event_type_raw, event_time_raw, customer_id, application_id, repayment_id,
                       amount_raw, currency)),
        batch_id, source_file, ingest_ts
    FROM silver_transactions_checked

    UNION ALL

    SELECT
        'TRX-00', 'transactions', source_key, CAST(NULL AS STRING), CAST(NULL AS DATE), raw_json,
        batch_id, source_file, ingest_ts
    FROM bronze_transactions
    WHERE load_status = 'CORRUPT'

    UNION ALL

    SELECT
        explode(failed_rules), 'macroeconomic_monthly', month, CAST(NULL AS STRING), CAST(NULL AS DATE),
        to_json(struct(month, consumer_confidence_index)),
        batch_id, source_file, ingest_ts
    FROM silver_macro_monthly
)
SELECT
    f.rule_id,
    r.dq_dimension,
    r.action,
    r.description,
    r.resolution,
    f.entity,
    f.record_key,
    f.branch_code,
    f.business_date,
    f.record_payload,
    f.batch_id AS source_batch_id,
    f.source_file,
    f.ingest_ts AS received_at,
    current_timestamp() AS processed_at
FROM failures f
JOIN silver_dq_rules r ON f.rule_id = r.rule_id;
