# LLM.md --- BankEasy Gold Layer & LangChain Analytics Assistant Specification

## Purpose

This document is the implementation brief for Claude Code. Read the
existing repository before changing code, preserve the current project
structure and conventions, and implement the smallest clean solution
that satisfies the LangChain Core requirement below.

If a required implementation detail cannot be determined safely from the
repository, configuration, or this document, **ask the user before
inventing it**. In particular, do not guess Databricks
catalog/schema/warehouse connection details, Azure OpenAI deployment
names, credentials, or existing API conventions.

The immediate task is the **LLM analytics assistant**, not the ML
feature and not the Power BI report itself.

------------------------------------------------------------------------

# 1. Overall project architecture

The project is a banking loan portfolio analytics platform.

High-level flow:

``` text
Source data
    |
    v
Data Lake / Databricks Volume
    - 4 source batches
    |
    v
BRONZE
    - 7 raw tables
    - raw/source-oriented records
    - audit columns
    |
    v
SILVER
    - cleaned and standardized data
    - deduplicated data
    - 36 data-quality rules
    - checked/clean outputs
    - invalid/problematic records may be quarantined
    |
    v
GOLD
    - star-schema dimensions and facts
    - KPI/aggregate tables
    - DQ exception fact
    - macroeconomic monthly data
    - knowledge graph nodes and edges
    |
    +-----------------------------+------------------------------+
    |                             |                              |
    v                             v                              v
SQL Warehouse / semantic     Future ML scoring            LLM analytics layer
serving layer                                              (current task)
    |                                                            |
    +-----------------------+                                    |
                            |                                    |
                            v                                    v
                    Power BI report                    LangChain Core tools
                            |                                    |
                            +------------------+-----------------+
                                               |
                                               v
                                      Azure App Service
                                      FastAPI + frontend
                                               |
                                               v
                                      Bank staff users
                              (branch managers / risk analytics)
```

Power BI and the LLM should be consumers of the same governed
Gold/semantic data, so a KPI returned by the assistant should be
consistent with the KPI shown in BI.

The planned application layer is an Azure App Service containing a
frontend/FastAPI application and an LLM assistant. The LLM assistant
uses LangChain Core, calls approved analytical tools over Gold data, and
uses an Azure OpenAI chat model.

The LLM must **not** be given unrestricted database access or
unrestricted LLM-generated SQL.

------------------------------------------------------------------------

# 2. Gold layer: conceptual model

The Gold layer contains several types of analytical assets:

``` text
GOLD
|
+-- Dimensions
|   +-- dim_product
|   +-- dim_branch
|   +-- dim_customer_segment
|   +-- dim_application_status
|   +-- dim_risk_band
|   +-- dim_date
|
+-- Facts
|   +-- fact_loan_application
|   +-- fact_repayment
|   +-- fact_dq_exception
|
+-- KPI / aggregate tables
|   +-- kpi_portfolio_summary
|   +-- kpi_portfolio_monthly
|   +-- kpi_open_installment_ageing
|
+-- Context
|   +-- macro_monthly
|
+-- Knowledge Graph
    +-- kg_nodes
    +-- kg_edges
```

The dimensions describe business entities/categories. Facts contain
events/observations at a defined grain. KPI tables contain
pre-aggregated business measures. Knowledge Graph tables represent
entities as nodes and relationships as edges.

------------------------------------------------------------------------

# 3. Gold table schemas

## 3.1 `dim_product`

**Purpose:** Product dimension. Describes the bank's loan products and
their configured amount, term and base-rate ranges.

**Grain:** One row per product.

  -----------------------------------------------------------------------
  Column                  Type                    Meaning
  ----------------------- ----------------------- -----------------------
  `product_key`           LONG                    Surrogate/key value
                                                  used to join facts to
                                                  the product dimension.

  `product_code`          STRING                  Business product code,
                                                  e.g. `AUT-NEW`,
                                                  `MTG-FIX`, `PL-STD`.

  `product_name`          STRING                  Human-readable product
                                                  name.

  `product_family`        STRING                  Product family/category
                                                  such as Auto, Mortgage,
                                                  Consumer or Business.

  `min_amount`            DECIMAL                 Minimum configured loan
                                                  amount for the product.

  `max_amount`            DECIMAL                 Maximum configured loan
                                                  amount.

  `min_term_months`       INT                     Minimum term in months.

  `max_term_months`       INT                     Maximum term in months.

  `base_rate`             DECIMAL                 Base interest rate
                                                  associated with the
                                                  product.
  -----------------------------------------------------------------------

Known examples include New Car Loan, Fixed-rate Mortgage, Green Home
Upgrade Loan, Personal Loan and SME Working Capital.

------------------------------------------------------------------------

## 3.2 `dim_branch`

**Purpose:** Branch dimension.

**Grain:** One row per branch.

  Column          Type     Meaning
  --------------- -------- ---------------------------------------
  `branch_key`    LONG     Key used to join facts to the branch.
  `branch_code`   STRING   Business branch code, e.g. `BR001`.
  `branch_name`   STRING   Human-readable branch name.
  `city`          STRING   Branch city.
  `region`        STRING   Geographic region.
  `opened_date`   DATE     Date on which the branch opened.

Examples include Syntagma (Athens, Attica), Piraeus Port, Kifisia,
Glyfada and Aristotelous.

------------------------------------------------------------------------

## 3.3 `dim_customer_segment`

**Purpose:** Customer segmentation dimension.

**Grain:** One row per customer segment.

  Column                   Type     Meaning
  ------------------------ -------- -----------------------------
  `customer_segment_key`   LONG     Key used by facts.
  `segment_code`           STRING   Segment code.
  `segment_name`           STRING   Human-readable segment.
  `description`            STRING   Description of the segment.

Known values: - `MASS` - Mass retail - everyday banking customers. -
`AFFLUENT` - customers with higher income and savings. - `PREMIER` -
premium relationship-managed customers. - `SME` - sole traders and small
companies. - `UNKNOWN` - customer missing/not found or segment missing.

------------------------------------------------------------------------

## 3.4 `dim_application_status`

**Purpose:** Application status dimension. Also contains useful status
flags for analytics.

**Grain:** One row per application status.

  --------------------------------------------------------------------------
  Column                  Type                    Meaning
  ----------------------- ----------------------- --------------------------
  `status_key`            LONG                    Key used by
                                                  `fact_loan_application`.

  `status_code`           STRING                  Status code.

  `status_name`           STRING                  Human-readable status
                                                  description.

  `is_final`              INT                     1 if the status is final.

  `is_decided`            INT                     1 if the application has
                                                  received a lending
                                                  decision.

  `is_approved`           INT                     1 if the status represents
                                                  approval.

  `sort_order`            INT                     Display/business ordering.
  --------------------------------------------------------------------------

Known statuses: - `SUBMITTED` - `UNDER_REVIEW` - `APPROVED` -
`REJECTED` - `WITHDRAWN` - `UNKNOWN`

------------------------------------------------------------------------

## 3.5 `dim_risk_band`

**Purpose:** Maps risk scores to ordered credit-risk bands.

**Grain:** One row per risk band.

  Column             Type     Meaning
  ------------------ -------- --------------------------------------
  `risk_band_key`    LONG     Key used by facts.
  `risk_band_code`   STRING   Risk band code (`A`-`E`, `U`).
  `risk_band_name`   STRING   Human-readable band and score range.
  `min_score`        INT      Minimum risk score for the band.
  `max_score`        INT      Maximum risk score for the band.
  `sort_order`       INT      Business/display ordering.

Known mapping: - A: Excellent (800-850) - B: Very good (740-799) - C:
Good (670-739) - D: Fair (580-669) - E: Poor (300-579) - U: Unknown /
missing / out of range

------------------------------------------------------------------------

## 3.6 `dim_date`

**Purpose:** Calendar dimension used for time-based analysis.

**Grain:** One row per calendar date.

The schema output supplied by the user contained duplicated/conflicting
metadata lines for some fields (`date_key`, `date`/`calendar_date`,
`year`, `quarter`, `month`). The actual sample query returned the
following canonical columns, which should be treated as the current
observed table shape unless repository/Databricks inspection proves
otherwise:

  Column           Type     Meaning
  ---------------- -------- -------------------------------------
  `date_key`       INT      Date key in `YYYYMMDD` form.
  `date`           DATE     Calendar date.
  `year`           INT      Calendar year.
  `quarter`        INT      Quarter number 1-4.
  `quarter_name`   STRING   Label such as `Q1`.
  `month`          INT      Month number 1-12.
  `month_name`     STRING   Month name.
  `year_month`     STRING   Year-month label such as `2016-01`.
  `month_key`      INT      Monthly key in `YYYYMM` form.
  `day_of_week`    INT      Numeric weekday representation.
  `day_name`       STRING   Weekday name.
  `is_weekend`     INT      Weekend flag.

**Important:** Facts contain several date roles. For example,
applications have application and decision dates, while repayments have
due and payment dates. Do not assume that one date relationship means
all date roles.

------------------------------------------------------------------------

# 4. Fact tables

## 4.1 `fact_loan_application`

**Purpose:** Central loan-application fact. Contains application
attributes, decision information and later portfolio/delinquency state.

**Grain:** One row per loan application.

  ----------------------------------------------------------------------------------------
  Column                               Type                    Meaning
  ------------------------------------ ----------------------- ---------------------------
  `application_id`                     STRING                  Loan application
                                                               identifier.

  `customer_key`                       STRING                  Customer key/identifier
                                                               used by the analytical
                                                               model.

  `application_date_key`               INT                     Application date; joins to
                                                               `dim_date.date_key`.

  `decision_date_key`                  INT                     Decision date; joins to
                                                               `dim_date.date_key` when
                                                               present.

  `branch_key`                         LONG                    Joins to `dim_branch`.

  `product_key`                        LONG                    Joins to `dim_product`.

  `customer_segment_key`               LONG                    Joins to
                                                               `dim_customer_segment`.

  `risk_band_key`                      LONG                    Joins to `dim_risk_band`.

  `status_key`                         LONG                    Joins to
                                                               `dim_application_status`.

  `channel`                            STRING                  Application channel,
                                                               e.g. BRANCH, ONLINE,
                                                               MOBILE.

  `employment_status_at_application`   STRING                  Employment status at
                                                               application time.

  `requested_amount`                   DECIMAL                 Amount requested by
                                                               applicant.

  `approved_amount`                    DECIMAL                 Amount approved; may be
                                                               null for non-approved
                                                               applications.

  `term_months`                        INT                     Requested/loan term in
                                                               months.

  `interest_rate`                      DECIMAL                 Interest rate where
                                                               applicable; may be null for
                                                               rejected/non-loan cases.

  `risk_score`                         INT                     Numeric credit/risk score.

  `monthly_debt`                       DECIMAL                 Monthly debt amount at
                                                               application time.

  `annual_income_at_application`       DECIMAL                 Annual income recorded at
                                                               application.

  `declared_monthly_expenses`          DECIMAL                 Declared monthly expenses.

  `dti_ratio`                          DECIMAL                 Debt-to-income ratio.

  `dti_band`                           STRING                  Categorized DTI band,
                                                               e.g. below 20%, 20-35%,
                                                               35-50%, above 50%.

  `decision_days`                      INT                     Number of days between
                                                               application and decision.

  `is_decided`                         INT                     1 if a decision exists.

  `is_approved`                        INT                     1 if approved.

  `is_manual_review`                   INT                     1 if manual review was
                                                               used.

  `is_paid_off`                        INT                     1 if the resulting loan has
                                                               been paid off.

  `is_active_loan`                     INT                     1 if an active loan exists.

  `outstanding_balance`                DECIMAL                 Current/derived outstanding
                                                               balance.

  `max_open_days_past_due`             INT                     Maximum days past due among
                                                               open obligations.

  `is_delinquent_30`                   INT                     30+ day delinquency
                                                               indicator.

  `delinquency_bucket`                 STRING                  Delinquency categorization.

  `dq_flag_count`                      INT                     Number of DQ flags
                                                               associated with the record.

  `source_batch_id`                    STRING                  Source ingestion batch
                                                               identifier.

  `source_file`                        STRING                  Source file path for
                                                               lineage.
  ----------------------------------------------------------------------------------------

This table is a core analytical source for application volume, requested
amount, approval/decision analytics, product/branch/segment/risk
analysis, outstanding balances and loan delinquency measures.

------------------------------------------------------------------------

## 4.2 `fact_repayment`

**Purpose:** Repayment/installment fact.

**Grain:** One row per repayment/installment record, not one row per
loan.

  ------------------------------------------------------------------------
  Column                   Type                    Meaning
  ------------------------ ----------------------- -----------------------
  `repayment_id`           STRING                  Repayment record
                                                   identifier.

  `application_id`         STRING                  Related loan
                                                   application identifier.

  `installment_number`     INT                     Installment sequence
                                                   number.

  `due_date_key`           INT                     Due date; date key.

  `payment_date_key`       INT                     Actual payment date
                                                   key; null if unpaid.

  `branch_key`             LONG                    Branch dimension key.

  `product_key`            LONG                    Product dimension key.

  `customer_segment_key`   LONG                    Customer segment key.

  `risk_band_key`          LONG                    Risk band key.

  `principal_due`          DECIMAL                 Principal expected for
                                                   the installment.

  `interest_due`           DECIMAL                 Interest expected.

  `total_due`              DECIMAL                 Total amount due.

  `principal_paid`         DECIMAL                 Principal actually
                                                   paid.

  `interest_paid`          DECIMAL                 Interest actually paid.

  `total_paid`             DECIMAL                 Total actually paid.

  `amount_unpaid`          DECIMAL                 Remaining unpaid
                                                   amount.

  `payment_status`         STRING                  Payment state,
                                                   e.g. ON_TIME or MISSED.

  `days_past_due`          INT                     Days late.

  `is_open`                INT                     Open installment
                                                   indicator.

  `is_open_30plus`         INT                     Open and 30+ days past
                                                   due indicator.

  `ageing_bucket`          STRING                  Ageing category such as
                                                   Settled, 0-29, 30-59,
                                                   etc.

  `dq_flag_count`          INT                     Number of DQ flags.

  `source_batch_id`        STRING                  Source batch.

  `source_file`            STRING                  Source lineage file.
  ------------------------------------------------------------------------

This table supports repayment performance, overdue/ageing, collections
and delinquency analysis.

------------------------------------------------------------------------

## 4.3 `fact_dq_exception`

**Purpose:** Auditable record of data-quality exceptions detected by the
pipeline.

**Grain:** One row per detected DQ exception.

  -----------------------------------------------------------------------
  Column                  Type                    Meaning
  ----------------------- ----------------------- -----------------------
  `exception_key`         LONG                    Exception key.

  `rule_id`               STRING                  DQ rule identifier,
                                                  e.g. `CUS-04`.

  `dq_dimension`          STRING                  DQ dimension,
                                                  e.g. validity.

  `action`                STRING                  Action associated with
                                                  the rule, e.g. FLAG.

  `description`           STRING                  Human-readable
                                                  description of the
                                                  issue.

  `resolution`            STRING                  Recommended/defined
                                                  resolution.

  `entity`                STRING                  Entity/table affected,
                                                  e.g. customers.

  `record_key`            STRING                  Key of the affected
                                                  business record.

  `branch_key`            LONG                    Branch key when
                                                  relevant; may use
                                                  unknown sentinel.

  `business_date_key`     INT                     Business date key where
                                                  available.

  `record_payload`        STRING                  Serialized record
                                                  context/payload. Treat
                                                  as potentially
                                                  sensitive detail; do
                                                  not expose unrestricted
                                                  payloads through the
                                                  LLM.

  `source_batch_id`       STRING                  Batch in which the
                                                  issue appeared.

  `source_file`           STRING                  Source file lineage.

  `received_at`           TIMESTAMP               Source/record receipt
                                                  timestamp.

  `detected_at`           TIMESTAMP               DQ detection timestamp.
  -----------------------------------------------------------------------

Example observed issue: `CUS-04`, validity,
`E-mail missing or malformed`, with a defined branch follow-up
resolution.

------------------------------------------------------------------------

# 5. KPI / aggregate tables

## 5.1 `kpi_portfolio_summary`

**Purpose:** Single-row portfolio-level summary containing headline
KPIs.

**Observed grain:** One row for the whole portfolio.

  -----------------------------------------------------------------------
  Column                  Type                    Meaning
  ----------------------- ----------------------- -----------------------
  `applications`          LONG                    Total application
                                                  count.

  `requested_amount`      DECIMAL                 Total requested amount.

  `approval_rate`         DOUBLE                  Approval rate as a
                                                  fraction.

  `avg_decision_days`     DOUBLE                  Average decision time
                                                  in days.

  `dti_share_below_20`    DOUBLE                  Share of applications
                                                  in DTI below 20%.

  `dti_share_20_35`       DOUBLE                  Share in 20-35%.

  `dti_share_35_50`       DOUBLE                  Share in 35-50%.

  `dti_share_above_50`    DOUBLE                  Share above 50%.

  `delinquency_rate_30`   DOUBLE                  30+ day delinquency
                                                  rate.

  `outstanding_balance`   DECIMAL                 Total outstanding
                                                  balance.

  `manual_review_rate`    DOUBLE                  Manual-review rate.
  -----------------------------------------------------------------------

Observed values at the time of inspection: - applications: 29,000 -
requested amount: 827,594,990.00 - approval rate: 0.4419 (44.19%) -
average decision days: 4.445 - DTI shares: 0.6352 / 0.207 / 0.12 /
0.0377 - delinquency rate 30: 0.1178 (11.78%) - outstanding balance:
129,992,400.62 - manual review rate: 0.1782 (17.82%)

These are sample/current observed values, not constants to hard-code.

------------------------------------------------------------------------

## 5.2 `kpi_portfolio_monthly`

**Purpose:** Pre-aggregated monthly portfolio analytics by month, branch
and product.

**Grain:** `month_key x branch_key x product_key` (based on the supplied
schema and intended model; verify in code/data if needed).

  -------------------------------------------------------------------------
  Column                    Type                    Meaning
  ------------------------- ----------------------- -----------------------
  `month_key`               INT                     Month key (`YYYYMM`).

  `branch_key`              LONG                    Branch key.

  `product_key`             LONG                    Product key.

  `applications`            LONG                    Application count.

  `requested_amount`        DECIMAL                 Total requested amount.

  `decided_applications`    LONG                    Count of decided
                                                    applications.

  `approved_applications`   LONG                    Count approved.

  `decision_days_total`     LONG                    Sum of decision days;
                                                    can support weighted
                                                    average decision time
                                                    when divided by the
                                                    appropriate count.

  `manual_reviews`          LONG                    Count requiring manual
                                                    review.

  `applications_with_dti`   LONG                    Applications with DTI
                                                    available.

  `high_dti_applications`   LONG                    Count classified as
                                                    high DTI.

  `active_loans`            LONG                    Active-loan count.

  `delinquent_loans_30`     LONG                    30+ day delinquent-loan
                                                    count.

  `outstanding_balance`     DECIMAL                 Outstanding balance
                                                    aggregate.
  -------------------------------------------------------------------------

Derived measures can be computed safely from these approved aggregates,
e.g. approval rate = approved / decided, where denominator handling is
explicit.

No sample rows were supplied for this table in the current brief, so do
not invent values.

------------------------------------------------------------------------

## 5.3 `kpi_open_installment_ageing`

**Purpose:** Aggregate view of currently open installments by ageing
bucket.

**Grain:** One row per ageing bucket.

  Column                Type      Meaning
  --------------------- --------- ------------------------------
  `ageing_bucket`       STRING    Delinquency/ageing bucket.
  `open_installments`   LONG      Number of open installments.
  `loans`               LONG      Number of loans represented.
  `amount_unpaid`       DECIMAL   Total unpaid amount.

Observed rows: - 365+: 1,232 open installments, 734 loans, 456,522.48
unpaid. - 180-365: 75, 59, 26,962.37. - 90-179: 30, 27, 20,510.58. -
60-89: 12, 12, 5,446.13. - 30-59: 25, 25, 12,571.03. - 0-29: 48, 48,
25,805.52.

These values are observations, not hard-coded application logic.

------------------------------------------------------------------------

# 6. Macroeconomic context

## `macro_monthly`

**Purpose:** Monthly macroeconomic context that can be joined by
`month_key`.

**Grain:** One row per month.

  Column                        Type      Meaning
  ----------------------------- --------- ----------------------------
  `month_key`                   INT       `YYYYMM` month key.
  `month_start`                 DATE      First date of the month.
  `inflation_rate`              DECIMAL   Inflation rate.
  `unemployment_rate`           DECIMAL   Unemployment rate.
  `reference_rate`              DECIMAL   Reference interest rate.
  `consumer_confidence_index`   DECIMAL   Consumer confidence index.

This table is contextual. Do not claim causal relationships between
macro indicators and portfolio outcomes merely from correlated trends.

------------------------------------------------------------------------

# 7. Knowledge Graph tables

## 7.1 `kg_nodes`

**Purpose:** Represents graph entities/nodes.

  -----------------------------------------------------------------------
  Column                  Type                    Meaning
  ----------------------- ----------------------- -----------------------
  `node_id`               STRING                  Globally meaningful
                                                  graph node identifier,
                                                  usually namespaced,
                                                  e.g. `customer:<id>`.

  `node_type`             STRING                  Entity type,
                                                  e.g. `Customer`.

  `label`                 STRING                  Display label.

  `properties`            STRING                  Serialized properties,
                                                  currently JSON-like
                                                  string content.
  -----------------------------------------------------------------------

Observed customer example:

``` json
{
  "node_id": "customer:76b83a28bcb7e701",
  "node_type": "Customer",
  "label": "76b83a28bcb7e701",
  "properties": "{\"segment_code\":\"MASS\"}"
}
```

The sample only proves Customer nodes and their segment property. Do not
assume additional node types without inspecting data.

## 7.2 `kg_edges`

**Purpose:** Represents directed relationships between Knowledge Graph
nodes.

  Column           Type     Meaning
  ---------------- -------- --------------------
  `source_id`      STRING   Source node ID.
  `target_id`      STRING   Target node ID.
  `relationship`   STRING   Relationship type.

Observed relationship:

``` text
customer:<id> --MEMBER_OF--> household:<id>
```

The supplied samples show `MEMBER_OF` relationships from customers to
households. Do not invent other relationship types without inspecting
the data.

The Knowledge Graph is a separate Gold use case. It is not automatically
part of the first three LLM analytical tools unless a clearly scoped
metadata/detail use case is approved.

------------------------------------------------------------------------

# 8. Relationships / star schema

Primary known relationships:

``` text
dim_product.product_key
    1 ---- * fact_loan_application.product_key
    1 ---- * fact_repayment.product_key

dim_branch.branch_key
    1 ---- * fact_loan_application.branch_key
    1 ---- * fact_repayment.branch_key
    1 ---- * fact_dq_exception.branch_key   (when meaningful)

dim_customer_segment.customer_segment_key
    1 ---- * fact_loan_application.customer_segment_key
    1 ---- * fact_repayment.customer_segment_key

dim_risk_band.risk_band_key
    1 ---- * fact_loan_application.risk_band_key
    1 ---- * fact_repayment.risk_band_key

dim_application_status.status_key
    1 ---- * fact_loan_application.status_key

dim_date.date_key
    1 ---- * fact_loan_application.application_date_key
    1 ---- * fact_loan_application.decision_date_key
    1 ---- * fact_repayment.due_date_key
    1 ---- * fact_repayment.payment_date_key
    1 ---- * fact_dq_exception.business_date_key (when present)

fact_loan_application.application_id
    1 ---- * fact_repayment.application_id

dim_date.month_key / monthly semantic date
    ---- kpi_portfolio_monthly.month_key
    ---- macro_monthly.month_key
```

Be careful with multiple date roles. Application date, decision date,
due date and payment date have different semantics.

`kpi_portfolio_monthly` can be enriched using `dim_branch` and
`dim_product`.

Unknown/sentinel dimension keys such as `-1` exist. The implementation
must handle them without crashing or fabricating labels.

------------------------------------------------------------------------

# 9. Current task: LangChain Core analytics assistant

Implement the requirement:

> Build a small, auditable LLM integration using `langchain-core`. The
> LLM is an interface to approved analytical capabilities; it must not
> bypass the semantic model, fabricate data, or perform consequential
> business actions.

Required behavior: 1. Use system, human, AI and tool messages correctly.
2. Use prompt templates that define business context, evidence, response
format and limitations. 3. Define at least two typed tools and bind them
to the chat model. 4. Detect tool calls, validate arguments, execute
only approved functions, and append `ToolMessage` results. 5. Produce
structured output distinguishing: - answer - evidence - filters - source
and/or measure - limitations 6. Handle: - malformed tool arguments -
unsupported metrics/filters - unavailable data - database/tool errors -
out-of-scope requests 7. Provide a traceable execution path.

We want **three tools**.

------------------------------------------------------------------------

# 10. Tool 1: `get_portfolio_kpi`

## Goal

Retrieve an approved headline KPI/aggregate from Gold.

Example questions: - "What is the current approval rate?" - "How many
applications are in the portfolio?" - "What is the outstanding
balance?" - "What is the 30+ day delinquency rate?" - "What is the
average decision time?" - "What percentage of applications require
manual review?"

## Allowed measures

At minimum:

``` text
applications
requested_amount
approval_rate
avg_decision_days
dti_share_below_20
dti_share_20_35
dti_share_35_50
dti_share_above_50
delinquency_rate_30
outstanding_balance
manual_review_rate
```

Primary source: `kpi_portfolio_summary`.

Use a typed/Pydantic input model or an equivalently strict LangChain
typed tool. Prefer an enum/Literal for measure names rather than
arbitrary strings.

Conceptual input:

``` json
{
  "metric": "approval_rate"
}
```

Conceptual tool result:

``` json
{
  "metric": "approval_rate",
  "value": 0.4419,
  "display_value": "44.19%",
  "source": "kpi_portfolio_summary",
  "filters": {},
  "limitations": []
}
```

Do not hard-code `0.4419`; query the approved Gold source.

If a user requests an unsupported KPI such as profit, the tool/assistant
must say it is unavailable in the approved semantic layer rather than
estimating it.

------------------------------------------------------------------------

# 11. Tool 2: `get_portfolio_breakdown`

## Goal

Retrieve a safe filtered aggregate/breakdown using approved Gold
facts/dimensions or approved aggregate tables.

Example questions: - "How many applications are for Personal Loans?" -
"What is the approval rate for risk band D?" - "Compare application
volume by customer segment." - "How many applications came through
MOBILE?" - "Show requested amount by product." - "What is delinquency by
risk band?" - "What is the unpaid amount by ageing bucket?"

The LLM must **not generate arbitrary SQL**. It chooses typed arguments.
Application code maps those arguments to predefined query
builders/approved SQL.

Possible typed fields (adapt to existing code conventions):

``` text
metric:
    applications
    requested_amount
    decided_applications
    approved_applications
    approval_rate
    avg_decision_days
    manual_review_rate
    active_loans
    delinquent_loans_30
    delinquency_rate_30
    outstanding_balance
    open_installments
    loans
    amount_unpaid

group_by:
    month
    product
    product_family
    branch
    city
    region
    customer_segment
    risk_band
    application_status
    channel
    employment_status
    dti_band
    ageing_bucket

filters (all optional and validated):
    year / month or approved date range
    product_code/product_name
    branch_code/branch_name
    city
    region
    segment_code
    risk_band_code
    status_code
    channel
    employment_status
    dti_band
    ageing_bucket
```

Do not expose raw arbitrary column names, SQL fragments, table names or
operators from user input.

Choose the safest approved source for the requested aggregate: -
`kpi_portfolio_monthly` for supported monthly x branch x product
aggregates. - `fact_loan_application` + approved dimensions for
application breakdowns not available in KPI tables. - `fact_repayment` +
approved dimensions for repayment/ageing breakdowns. -
`kpi_open_installment_ageing` for direct ageing aggregates.

Explicitly protect denominators: - approval rate should use an approved
definition, normally approved applications / decided applications. -
delinquency rate must use the project's approved numerator/denominator
definition; inspect existing Gold-generation code before implementing if
definition is not already explicit. - avoid division by zero.

Return source table(s), measure definition and applied filters with the
result.

------------------------------------------------------------------------

# 12. Tool 3: `get_metadata`

## Goal

Return approved metadata/reference values, not arbitrary database
introspection.

Example questions: - "What loan products are available?" - "What are the
risk bands?" - "Which branches are in Athens?" - "What customer segments
exist?" - "What application statuses exist?"

Allowed metadata domains should be typed, e.g.:

``` text
products
branches
customer_segments
risk_bands
application_statuses
date_range
```

Approved sources: - `dim_product` - `dim_branch` -
`dim_customer_segment` - `dim_risk_band` - `dim_application_status` -
`dim_date`

Optional validated filters can include city, region, product family,
etc.

Do not return sensitive customer-level metadata. Do not expose raw
`record_payload` from DQ exceptions through a generic metadata tool.

Knowledge Graph metadata may be added later only if explicitly scoped.
If added, first inspect actual `node_type` and `relationship` values
rather than assuming them.

------------------------------------------------------------------------

# 13. Tool-call execution pattern

Use the LangChain Core message/tool pattern explicitly.

Conceptual flow:

``` text
SystemMessage
    |
HumanMessage(user question)
    |
chat_model.bind_tools([...]).invoke(messages)
    |
AIMessage
    |
    +-- no tool call --> safe response / out-of-scope response
    |
    +-- tool call(s)
            |
            v
      validate typed args
            |
            v
      execute approved Python function/query
            |
            v
      ToolMessage(tool_call_id=..., content=structured result)
            |
            v
      invoke model again with full message history
            |
            v
      final structured answer
```

Use the tool call ID correctly when constructing `ToolMessage`.

If the model emits multiple independent approved tool calls and the
existing application architecture supports it cleanly, they may be
executed independently. Correctness, validation and traceability are
more important than parallelism.

------------------------------------------------------------------------

# 14. System prompt requirements

The system prompt should make the assistant a **BankEasy analytical
assistant**, not a decision-making banking agent.

It should communicate at least:

-   Answer banking portfolio analytics questions using only approved
    tool evidence.
-   Do not fabricate values.
-   Do not claim access to data that tools did not return.
-   Do not issue arbitrary SQL.
-   Do not bypass the Gold/semantic layer.
-   Do not approve/reject loans or take consequential business actions.
-   Do not make individual credit decisions.
-   Distinguish facts from interpretations.
-   If evidence is unavailable, say so.
-   State applied filters.
-   Cite the source/measure used in the structured response.
-   Surface limitations where relevant.
-   Avoid exposing internal raw payloads or unnecessary customer-level
    information.
-   Treat tool errors as unavailable evidence, not an invitation to
    guess.

------------------------------------------------------------------------

# 15. Structured final output

Use a typed structured output model. Exact field types may be adapted to
the existing API, but preserve these concepts:

``` python
class AnalyticsResponse(BaseModel):
    answer: str
    evidence: list[...]
    filters: dict[str, ...]
    source: list[str] | str
    measure: str | None
    limitations: list[str]
```

A richer evidence object is preferable if it stays simple, e.g.:

``` python
class EvidenceItem(BaseModel):
    label: str
    value: str | int | float
    source: str
```

Example conceptual output:

``` json
{
  "answer": "The current portfolio approval rate is 44.19%.",
  "evidence": [
    {
      "label": "approval_rate",
      "value": "44.19%",
      "source": "kpi_portfolio_summary"
    }
  ],
  "filters": {},
  "source": ["kpi_portfolio_summary"],
  "measure": "approval_rate",
  "limitations": [
    "This is the current portfolio-level aggregate returned by the Gold KPI table."
  ]
}
```

Do not force the model to invent evidence text when the tool result can
provide the evidence deterministically.

------------------------------------------------------------------------

# 16. Auditing / traceability

The acceptance condition requires a traceable execution path.

Preserve or log enough information to reconstruct:

``` text
user question
-> model tool decision
-> tool name
-> validated arguments
-> approved source/query path
-> tool result or tool error
-> final response
```

Do not log secrets or unnecessarily sensitive payloads.

A small internal trace object can contain: - tool name - validated
args - source table(s) - execution status - row count if useful - error
category if failed

Prefer deterministic application-side tracing over asking the LLM to
narrate hidden reasoning.

------------------------------------------------------------------------

# 17. Error and scope handling

Implement explicit handling for:

### Invalid/malformed tool arguments

Validation error; do not execute the query.

### Unsupported metric

Example: `profit` is not present in the supplied Gold KPI model. Return
a clear unsupported/unavailable result.

### Unsupported filter/value

Validate fields and, where appropriate, validate dimension values
against approved metadata.

### Empty result

Say that no matching Gold data was found for the filters. Do not convert
an empty result into zero unless the metric definition explicitly
permits that interpretation.

### Databricks/tool failure

Return a safe tool error to the model. The final answer must state that
the data could not be retrieved.

### Out-of-scope request

Examples: - "Approve this customer." - "Reject this application." -
"Change the interest rate." - "Delete this customer." - unrestricted
database mutation. The assistant must refuse the action while optionally
explaining the analytics it can provide.

### Unknown factual request

Do not answer from model memory when the answer is supposed to come from
BankEasy data.

------------------------------------------------------------------------

# 18. Data access constraints

1.  Read from Gold/semantic sources only for this assistant unless an
    existing repository abstraction explicitly defines otherwise.
2.  No unrestricted text-to-SQL.
3.  No user-supplied SQL.
4.  No write/update/delete operations.
5.  Parameterize or safely construct all approved queries.
6.  Keep database credentials in environment/config/secret mechanisms
    already used by the project; never commit secrets.
7.  Reuse the repository's existing Databricks connection/data-access
    abstraction if one exists.
8.  If no connection abstraction exists, inspect the project first and
    ask the user for missing required connection information rather than
    inventing it.
9.  Keep tool functions independently testable without requiring the LLM
    for their business logic.

------------------------------------------------------------------------

# 19. Suggested implementation structure

Do **not** blindly create these paths if the repository already has a
different structure. Inspect first and adapt.

Conceptually:

``` text
src/
  ...
  llm/
    models.py          # Pydantic request/response models
    prompts.py         # system/prompt templates
    tools.py           # typed LangChain tools
    service.py         # tool-call loop / assistant orchestration
    repository.py      # approved Gold queries/data access, if needed
    errors.py          # domain/tool error types, if useful

tests/
  ...
  test_llm_tools.py
  test_llm_service.py
```

Keep SQL/data access separate from LLM orchestration where practical.

------------------------------------------------------------------------

# 20. Minimum tests / demonstration cases

At minimum demonstrate/test:

1.  **KPI success**
    -   "What is the current approval rate?"
    -   calls `get_portfolio_kpi`
    -   result grounded in `kpi_portfolio_summary`.
2.  **Metadata success**
    -   "What risk bands are available?"
    -   calls `get_metadata`
    -   returns A-E/U from `dim_risk_band`.
3.  **Filtered aggregate success**
    -   "What is the approval rate for risk band D?"
    -   calls `get_portfolio_breakdown`
    -   uses approved fact/dimension logic.
4.  **Unsupported metric**
    -   "What is our profit?"
    -   no fabricated value.
5.  **Out-of-scope consequential action**
    -   "Approve application LAxxxx."
    -   no business action.
6.  **Malformed tool arguments**
    -   validation prevents execution.
7.  **Tool/database failure**
    -   final response clearly states evidence is unavailable.
8.  **No matching data**
    -   safe empty-result behavior.

------------------------------------------------------------------------

# 21. Acceptance target

The implementation is complete when a user question can:

``` text
question
  -> LLM selects an approved typed tool
  -> arguments are validated
  -> approved Gold/semantic query executes
  -> result returns as ToolMessage
  -> LLM produces structured evidence-based answer
  -> source, measure, filters and limitations are visible
  -> execution is traceable
```

The implementation must satisfy this without allowing the LLM to bypass
the semantic model, fabricate BankEasy data, issue unrestricted SQL, or
perform consequential banking actions.

------------------------------------------------------------------------

# 22. Before coding

Claude Code should first:

1.  Inspect the repository structure and existing
    FastAPI/API/data-access code.
2.  Inspect `pyproject.toml`/lockfile to see which LangChain, Pydantic,
    Databricks and Azure/OpenAI packages already exist.
3.  Find the existing Databricks/SQL Warehouse connection pattern.
4.  Find Gold table creation code/SQL, especially KPI definitions,
    before duplicating business logic.
5.  Confirm the catalog/schema/table qualification required at runtime.
6.  Reuse existing settings/environment conventions.
7.  Then propose the minimal files/changes needed.
8.  If any required connection/model configuration cannot be inferred
    safely, ask the user before implementation.

Do not modify the Power BI or ML portions as part of this task unless
needed for a shared interface and explicitly approved.
