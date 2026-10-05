# Team 2 pipeline SQL for the official dataset (databank)

This is one Lakeflow Declarative Pipeline in SQL, with the same structure as the class template, rewritten for the official Team 2 data:
- 4 delivery batches covering 2016–2025
- 7 source files, 1,097,081 records
- 45 kinds of planted defects

Databricks reads every `.sql` file in the three folders and works out the order on its own.

```
pipelines/
├── bronze/   P1   one streaming table per source file (7)
├── silver/   P1   standardisation, newest version wins, 36 quality rules, quarantine
└── gold/     P2a  6 dimensions, 2 facts, macro table, exceptions, reconciliation, KPIs, graph (bonus)
```

## Tested result

The SQL was run in local Spark 4 over the real files, first batch_001 alone and then all four batches, using `tests/data/run_pipeline_sql_locally.py`. Results:

- **Planted defects.** Every planted defect listed in `quality_injection_manifest.csv` was accounted for:
  - most were caught by the intended rule;
  - recoverable formatting problems were fixed in standardisation;
  - the rest had been replaced by a correct later delivery.
- **No false positives.** No rule fired on a record that has no planted defect.
- **Reconciliation:** passes.
- **KPIs** after all four batches are close to the dataset's clean-truth KPIs (from `generation_report.json`):
  - The ratios are within 0.4%, except delinquency (−2.1%).
  - Counts and amounts are about 3% lower, because defective applications are quarantined instead of counted.

The local test cannot run the parts that only exist in Databricks: `read_files`, Auto Loader, `AUTO CDC` and expectations. Those are written to the Databricks documentation, but the first real run is their actual test.

## Set it up in Databricks

1. **Upload the data.** In Catalog, open the volume `data2026acc123456.crm.crmfolder` and create a folder `loans`. Upload the four folders from `data/landing/` into it, keeping their names: `/Volumes/data2026acc123456/crm/crmfolder/loans/batch_001/customers.csv`, and so on.
   - Or by script: `pip install databricks-sdk`, `databricks auth login --host <workspace-url>`, then `python scripts/upload_data.py --landing data/landing`. Add `--start --wait` to run the pipeline after the upload, or `--each-batch` for the incremental demo (upload a batch, run, wait, next batch). Files already uploaded are skipped.
   - Do **not** upload `data/generated_metadata/`. It is for checking only; the data guide says the manifest must not be ingested.
   - If your catalog, schema or volume differ, change the path in the 7 files in `bronze/`.
2. **Create a schema for the tables:** `CREATE SCHEMA IF NOT EXISTS data2026acc123456.loans;`
3. **Create the pipeline.** Go to Jobs & Pipelines, then Create, then ETL pipeline.
   - Name: `team2-loan-pipeline`
   - Default catalog `data2026acc123456`, default schema `loans`
   - Source code: the `pipelines/` folder from the repo (Databricks Git folder)
   - Settings, Configuration: `spark.sql.session.timeZone` = `UTC`
   - Compute: serverless
4. **Run it**, choosing one of two ways:
   - **Demo the incremental load:** upload `batch_001` and click Start. Then upload `batch_002`, `batch_003` and `batch_004` one at a time, clicking Start after each upload. Auto Loader reads only the new files each time.
   - **Load everything:** upload all four batches and click Start once. The final tables are the same either way.
5. Use Full refresh only when the Bronze code changes. It reloads every file from scratch.

## Check the results

```sql
-- 1. Quarantine count per rule: compare with the table below
SELECT rule_id, action, COUNT(*) AS records FROM data2026acc123456.loans.silver_quarantine GROUP BY ALL ORDER BY rule_id;
-- 2. Reconciliation: every row PASS (otherwise the update has already failed)
SELECT * FROM data2026acc123456.loans.reconciliation;
-- 3. The KPIs: compare with the table below
SELECT * FROM data2026acc123456.loans.kpi_portfolio_summary;
-- 4. Open installments by days past due
SELECT * FROM data2026acc123456.loans.kpi_open_installment_ageing ORDER BY ageing_bucket;
-- 5. Expectation results per rule, from the event log (quality evidence for the brief)
SELECT timestamp, details:flow_progress.data_quality.expectations AS expectations
FROM event_log('<pipeline-id>')
WHERE event_type = 'flow_progress' AND details:flow_progress.data_quality IS NOT NULL
ORDER BY timestamp DESC;
```

| Silver table | After batch_001 | After all 4 batches |
|---|---|---|
| silver_customers_current | 14,683 | 15,000 |
| silver_loan_applications | 27,568 | 29,000 |
| silver_repayments | 334,147 | 351,654 |
| silver_transactions | 604,430 | 632,880 |
| silver_macro_monthly | 117 | 120 |

| KPI (`kpi_portfolio_summary`) | After batch_001 | After all 4 batches | Dataset clean truth |
|---|---|---|---|
| applications | 27,568 | 29,000 | 30,012 |
| requested_amount | 782,625,840 | 827,594,990 | 854,401,260 |
| approval_rate | 0.4450 | 0.4419 | 0.4433 |
| avg_decision_days | 4.447 | 4.445 | 4.448 |
| DTI share <20% / 20-35% / 35-50% / >50% | .6424 / .2051 / .1164 / .0361 | .6352 / .2070 / .1200 / .0377 | .6355 / .2072 / .1196 / .0378 |
| delinquency_rate_30 | 0.1175 | 0.1178 | 0.1203 |
| outstanding_balance | 126,777,297.69 | 129,992,400.62 | 131,934,040.91 |
| manual_review_rate | 0.1774 | 0.1782 | 0.1784 |

## Quality rules (36)

- **REJECT** keeps the record out of Silver.
- **FLAG** keeps the record, either recomputing the bad value or showing it as Unknown.
- Each rule has an expectation, so its pass and fail counts appear in the event log.

| Rule | Checks | Action | Catches (planted defect) | After batch_001 | After all 4 |
|---|---|---|---|---|---|
| CUS-01 | Birth date missing or impossible (under 18, over 110) | flag | impossible_dob | 19 | 18 |
| CUS-02 | Segment missing or unknown | flag | missing_segment | 60 | 56 |
| CUS-03 | Annual income missing or not positive | flag | missing_income | 49 | 57 |
| CUS-04 | E-mail missing or malformed | flag | missing_email, malformed_email | 221 | 216 |
| CUS-05 | E-mail shared with another customer (both are flagged) | flag | duplicate_contact_email | 108 | 110 |
| CUS-06 | Phone missing or not a valid Greek number | flag | missing_phone, invalid_phone | 107 | 114 |
| APP-01 | Customer id missing | reject | none planted | 0 | 0 |
| APP-02 | Consent missing | reject | missing_consent | 266 | 277 |
| APP-03 | Status missing | reject | missing_status | 157 | 163 |
| APP-04 | Unknown status | reject | none planted | 0 | 0 |
| APP-05 | Amounts inconsistent (not positive, approved above requested) | reject | approved_gt_requested, nonpositive_requested_amount | 200 | 212 |
| APP-06 | Requested amount outside the product limits | reject | requested_outside_product_range | 125 | 131 |
| APP-07 | Impossible dates (decision before application, future, unreadable) | reject | decision_before_application | 185 | 196 |
| APP-08 | Same application delivered under a new id | reject | duplicate_application_rekeyed | 110 | 114 |
| APP-09 | Currency not EUR (`XXX`, `EU`) | reject | invalid_currency | 32 | 33 |
| APP-10 | Risk score missing or outside 300-850 | flag | risk_score_out_of_range | 183 | 196 |
| APP-11 | Customer not in the customer master | flag | unknown_customer | 81 | 82 |
| APP-12 | Branch or product code unknown | flag | unknown_branch, unknown_product | 64 | 66 |
| REP-01 | Installment of an application never delivered | reject | orphan_application | 2,877 | 3,028 |
| REP-02 | Installment of a quarantined or non-approved application (cascade) | reject | follows the APP rules | 11,912 | 12,562 |
| REP-03 | Second row with the same loan and installment number | reject | duplicate_installment_number | 1,363 | 1,434 |
| REP-04 | Negative amount | reject | negative_amount | 1,352 | 1,423 |
| REP-05 | Impossible or unreadable payment date | reject | impossible_payment_date | 2,382 | 2,500 |
| REP-06 | Currency not EUR (`XXX`) | reject | invalid_currency | 271 | 293 |
| REP-07 | Total due is not principal + interest; recomputed | flag | amount_sum_inconsistent | 4,635 | 4,891 |
| REP-08 | Status or days past due contradict amounts and dates; recomputed | flag | dpd_status_inconsistent | 3,595 | 3,771 |
| TRX-00 | Line is not valid JSON | reject | malformed_json_line | 4 | 4 |
| TRX-01 | Unknown event type, after spelling is fixed | reject | none left after fixing | 0 | 0 |
| TRX-02 | Required field missing | reject | missing_required_nested | 4,481 | 4,685 |
| TRX-03 | Impossible time (unreadable, before 2016, future) | reject | impossible_timestamp | 2,234 | 2,341 |
| TRX-04 | Amount not a positive number | reject | invalid_amount (zero, negative, empty) | 2,224 | 2,335 |
| TRX-05 | Currency not EUR, after spelling is fixed | reject | none left after fixing | 0 | 0 |
| TRX-06 | Customer unknown | reject | unknown_reference (customer) | 1,271 | 1,320 |
| TRX-07 | Loan repayment for an installment never delivered | reject | unknown_reference (installment) | 1,747 | 1,802 |
| TRX-08 | Loan repayment whose application differs from the installment's loan | reject | wrong_reference_relationship | 1,464 | 1,545 |
| TRX-09 | Loan repayment for a quarantined installment (cascade) | reject | follows the REP rules | 19,172 | 20,219 |
| MAC-01 | Consumer confidence index missing | flag | missing_optional_indicator | 1 | 1 |

Notes on the counts:
- **Rules fire on the current version only.** A defect that a later batch delivers correctly drops out, so a count can fall between runs.
- **Overlaps.** REP-07 and REP-08 also fire on rows that are already rejected for a negative amount or an impossible payment date.
- **Cascades.** REP-02 and TRX-09 are large because rejecting an approved application also rejects all its installments and payments. They release automatically once the parent is corrected.

**Fixed in standardisation, not rules:**
- dates written DD/MM/YYYY;
- whitespace and case in names, codes and segments;
- phone formats such as `(69) 47409472` or `+30 697 027 1415`, converted to `+30XXXXXXXXXX`;
- euro spellings `eur`, `EURO`, `€` and `EUR `;
- event-type spellings such as `Loan Repayment`, `LOAN-REPAYMENT` and `LOAN_REPAYMNT`;
- decimal commas such as `594,09`.

**Removed by "newest version wins":** exact duplicate rows and events, late-arriving records and corrections.
- customers, applications and repayments: the greatest `updated_at` wins, ties go to the later batch;
- transactions: the later batch wins.

## KPI conventions

These are set in `gold/kpis.sql`. They follow the dataset documentation, and Power BI and the API must use the same ones.

- **Approval rate:** approved / (approved + rejected). Withdrawn and undecided applications are excluded.
- **Average decision time:** days from application to decision, over approved and rejected applications.
- **DTI:** `monthly_debt / (annual_income_at_application / 12)`, using the income at application time, not the current income. Bands: <20%, 20-35%, 35-50%, >50%.
- **Outstanding balance:** approved amount minus principal paid, over approved loans, at the as-of date.
- **Paid off:** the final installment (number = term) exists and no installment is open.
- **Active loan:** approved and not paid off.
- **Delinquency rate (30+):** active loans with an open installment 30 or more days past due, divided by active loans. Open installments are never written off, so most delinquency is old unresolved debt. Show `kpi_open_installment_ageing` and `delinquency_bucket` (30-59, 60-89, 90-179, 180-365, 365+) next to it. **The team should confirm this convention**, because the data guide leaves it open.
- **Risk bands:** A 800-850, B 740-799, C 670-739, D 580-669, E 300-579, matching the dataset report.

## Tables

| Layer | Tables |
|---|---|
| Bronze | `bronze_customers`, `bronze_branches`, `bronze_products`, `bronze_loan_applications`, `bronze_repayments`, `bronze_macroeconomic_monthly`. Each is the delivered CSV rows as text, plus `source_system`, `source_key`, `source_file`, `batch_id`, `ingest_ts`, `record_hash` and `load_status`. Also `bronze_transactions`: each JSON line as raw text; broken lines have `load_status = 'CORRUPT'` |
| Silver | `silver_*_clean` (streaming, every version, standardised) · `silver_customers` (AUTO CDC history, SCD type 2) · `silver_customers_current` · `silver_*_checked` (newest version plus `failed_rules`) · `silver_loan_applications`, `silver_repayments`, `silver_transactions` (valid rows; `dq_flags` lists any flags) · `silver_branches`, `silver_products`, `silver_macro_monthly` · `silver_dq_rules`, `silver_quarantine` |
| Gold | `dim_date` (2016-2025, no gaps), `dim_branch`, `dim_product`, `dim_customer_segment`, `dim_risk_band`, `dim_application_status` (each with an Unknown -1 row) · `fact_loan_application`, `fact_repayment` · `macro_monthly` · `fact_dq_exception` · `reconciliation` (a failed check fails the update) · `kpi_portfolio_monthly`, `kpi_portfolio_summary`, `kpi_open_installment_ageing`, `refresh_info` · `kg_nodes`, `kg_edges` (bonus) |

Silver keeps personal data (names, e-mail, phone, birth date), standardised, because the data guide asks for it. Gold has none: customers appear only as a segment and a hashed `customer_key`.

## Local check

```
pip install pyspark==4.0.1 pandas pyarrow        # needs Java 17 or 21
python tests/data/run_pipeline_sql_locally.py --pipelines pipelines --landing data/landing --metadata data/generated_metadata
```

It runs the SQL over batch_001 and then over all four batches, and prints the counts above. It ends with `ALL CHECKS PASS` when:
- every planted defect is caught, fixed or superseded;
- no rule fires on a clean record;
- the reconciliation passes.

A run takes a few minutes on a laptop. The output folder `tests/data/.check_output/` is about 1 GB and belongs in `.gitignore`.

## Known limitations

- `customer_key` is an unsalted SHA-256 of the customer id. In production, add a secret salt from Key Vault.
- The payment events of an installment do not always add up to its `total_paid`, because some events are quarantined. Gold therefore uses the installment rows for payments, and the events are kept in `silver_transactions` for cash-flow analysis.
- Gold is fully recomputed on each run, which takes seconds on Databricks for about 1 million rows.
