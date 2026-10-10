# PROJECT_OVERVIEW.md

# Team 2 --- Banking Loan Portfolio Analytics

## End-to-End AI & Data Engineering Capstone Project

> **Purpose of this file**
>
> This document is the high-level project map for the entire Team 2
> repository. It explains **what the project is, why it exists, what
> must be built, how the components connect, what is mandatory, what is
> optional, and the recommended implementation order**.
>
> Any coding assistant working in this repository should read this file
> first for project context, then read `DATA.md` (the authoritative final
> synthetic-dataset specification and data contract) and, for the rationale
> behind the data design, `DATA_DESIGN_DECISIONS.md`, and then the relevant
> implementation files for the current phase.
>
> The official capstone specification is the source of truth for
> mandatory requirements. Project-specific enhancements described here
> must not replace or delay the mandatory baseline.

------------------------------------------------------------------------

# 1. Executive Summary

Team 2 is building an **end-to-end enterprise banking data and analytics
platform** for a synthetic loan portfolio.

The business problem is:

> A bank needs a governed view of loan applications, approvals, risk
> bands, customer affordability, repayments and portfolio performance,
> while avoiding unnecessary exposure of customer-level detail.

The project begins with heterogeneous raw source files and ends with a
governed analytical and AI-enabled solution:

``` text
Synthetic Banking Sources
        ↓
Azure Databricks — Bronze
        ↓
Azure Databricks — Silver
        ↓
Azure Databricks — Gold
        ↓
Microsoft Fabric Semantic Model
        ↓
Power BI Analytics
        ↓
FastAPI Analytical Services
        ↓
LangChain Core AI Assistant
        ↓
Azure Security + CI/CD + Monitoring
```

After the mandatory baseline works end to end, the project also adds a
custom enhancement:

``` text
Historical Gold / curated behavioral data
        ↓
Leakage-safe ML feature engineering
        ↓
90-day 30+ DPD early-warning model
        ↓
Governed prediction output
        ↓
Predictive portfolio analytics
```

The final product is therefore not merely a dashboard and not merely an
ML model. It is a **production-minded analytical platform**
demonstrating:

-   data engineering;
-   data quality;
-   dimensional modeling;
-   analytics;
-   Power BI;
-   REST APIs;
-   LLM tool calling;
-   Azure security;
-   CI/CD;
-   testing and monitoring;
-   optional predictive ML.

------------------------------------------------------------------------

# 2. Official Capstone Goal

The common assignment requires each team to design, implement and
demonstrate an end-to-end enterprise data and analytics solution.

The official progression is:

``` text
Discover
→ Engineer
→ Model
→ Analyze
→ Validate
→ Demonstrate
```

Translated into this project:

``` text
Understand the banking problem and KPIs
→ generate/receive realistic source data
→ ingest raw data into Bronze
→ clean/conform it in Silver
→ build banking facts/dimensions in Gold
→ expose governed measures through Fabric
→ build Power BI
→ expose analytical services through FastAPI
→ connect an LLM only to approved tools
→ secure/deploy/test the system
→ demonstrate the full lineage end to end
```

The project must demonstrate both:

``` text
engineering quality
+
business value
```

A visually attractive dashboard cannot compensate for an incomplete
pipeline, and a technically correct pipeline must still produce
understandable business analytics.

------------------------------------------------------------------------

# 3. Team 2 Business Domain

## Banking Loan Portfolio Analytics

The platform should answer questions such as:

``` text
How many loan applications are being submitted?
How much money is being requested?
What percentage is approved?
How long do decisions take?
Which applications require manual review?
How affordable are loans relative to borrower income/debt?
How does portfolio performance differ by product, branch and segment?
How much balance remains outstanding?
Where is delinquency concentrated?
What exceptions require investigation?
```

The enhanced predictive layer later adds:

``` text
Which currently performing loans show elevated risk of reaching 30+ DPD
within the next 90 days?
```

The predictive layer is an analytical early-warning enhancement. It is
**not** an automated loan approval/denial engine and must not take
consequential lending actions.

------------------------------------------------------------------------

# 4. Source Data

The four official Team 2 sources are:

``` text
customers.csv
loan_applications.csv
repayments.csv
transactions.json
```

The project additionally uses reference/context data:

``` text
branches.csv
products.csv
macroeconomic_monthly.csv
```

Current design:

``` text
12 branches
5 lending products
10 years of detailed history: 2016-01-01 through 2025-12-31
```

The synthetic universe is intentionally much larger than the
assignment's minimum 10,000 transactional/event records so that:

-   BI is meaningful;
-   data-quality issues are visible;
-   longitudinal borrower histories exist;
-   repeat borrowing exists;
-   repayment deterioration/recovery can be modeled;
-   the optional ML extension has enough mature observations.

Detailed source-generation rules and the final dataset contract are defined in:

``` text
DATA.md
```

The rationale behind the data design is in `DATA_DESIGN_DECISIONS.md`.
Do not duplicate or contradict those detailed rules here.

------------------------------------------------------------------------

# 5. Core Source Relationships

Conceptually:

``` text
customers
   │
   ├──< loan_applications >── branches
   │          │
   │          └────────────── products
   │
   ├──< transactions
   │
   └── loan applications that become loans
                  │
                  └──< repayments

macroeconomic_monthly
   └── contextual time-based enrichment
```

Important distinction:

``` text
customer master state
≠
application-time financial snapshot
```

A customer's current income or employment may change later.

Historical applications must preserve the information known at
application time, including fields such as:

``` text
annual_income_at_application
employment_status_at_application
declared_monthly_expenses
monthly_debt
```

This is necessary for historical correctness and future leakage-safe ML.

------------------------------------------------------------------------

# 6. Synthetic Data Philosophy

The source generator must create a **coherent banking world**, not
unrelated random rows.

The intended causal flow is:

``` text
customer characteristics
+
economic environment
+
existing financial obligations
+
loan application
        ↓
underwriting decision
        ↓
approved loan
        ↓
scheduled repayment obligations
        ↓
real financial behavior over time
        ↓
on-time / late / partial / missed payments
        ↓
healthy performance / temporary stress / recovery / delinquency
```

The generator may internally use latent financial-stress variables to
produce realistic behavior, but those hidden variables must never be
exported as ML features or business data.

Delinquency must contain signal but must **not** be a trivial
deterministic function of risk score or DTI.

------------------------------------------------------------------------

# 7. Source Delivery / Incremental Ingestion Scenario

The project simulates four source deliveries:

``` text
batch_001 — historical baseline through 2025-09-30
batch_002 — October 2025 delivery
batch_003 — November 2025 delivery
batch_004 — December 2025 delivery
```

Later batches should contain realistic examples of:

``` text
new records
late-arriving records
corrected records
```

A batch is an ingestion/delivery concept, not necessarily the same as
business event date.

Example:

``` text
event date       = 2025-09-29
delivery batch   = batch_002 (October)
```

This allows the project to demonstrate:

-   incremental ingestion;
-   lineage;
-   late-arriving data;
-   correction handling;
-   idempotent reruns.

------------------------------------------------------------------------

# 8. Deliberate Dirty Data

The raw source data intentionally contain controlled quality problems.

Important:

``` text
bad business outcome ≠ bad data
```

Examples of valid adverse behavior:

``` text
high DTI
rejection
late repayment
partial repayment
missed repayment
30+ DPD
declining cash flow
```

These must remain valid observations.

Examples of actual data-quality defects include:

``` text
missing consent/status
duplicate application
impossible dates
inconsistent amounts
orphan repayment
out-of-range risk score
malformed contact data
invalid references
duplicate transaction event
```

The dirty-data design exists specifically so the Silver layer can
demonstrate measurable detection, remediation and quarantine.

------------------------------------------------------------------------

# 9. Target Architecture

The target architecture is:

``` text
┌──────────────────────────────────────────────┐
│                 SOURCE LAYER                 │
│ CSV / JSON / reference / contextual data     │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│            DATABRICKS — BRONZE               │
│ Raw append-only Delta + ingestion metadata   │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│            DATABRICKS — SILVER               │
│ Validated / standardized / deduplicated      │
│ conformed data + quarantine                  │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│             DATABRICKS — GOLD                │
│ Star schema / facts / dimensions / measures  │
└───────────────┬───────────────────┬──────────┘
                │                   │
                ▼                   ▼
┌────────────────────────┐  ┌───────────────────┐
│ Microsoft Fabric       │  │ FastAPI           │
│ Semantic Model         │  │ Analytical API    │
└────────────┬───────────┘  └─────────┬─────────┘
             │                        │
             ▼                        ▼
┌────────────────────────┐  ┌───────────────────┐
│ Power BI               │  │ LangChain Core    │
│ Reports / Drillthrough │  │ Approved tools    │
└────────────────────────┘  └───────────────────┘

Cross-cutting:
Azure IAM • Key Vault • configuration • logs • tests • CI/CD • monitoring
```

Optional predictive extension:

``` text
Silver/Gold historical data
        ↓
as-of feature engineering
        ↓
monthly eligible-loan snapshots
        ↓
temporal train / validation / test
        ↓
ML model
        ↓
fact_loan_risk_prediction
        ↓
Predictive Power BI / optional API tool
```

------------------------------------------------------------------------

# 10. Phase 0 --- Repository and Project Foundation

Before building pipeline logic:

1.  Establish a clean repository structure.
2.  Keep secrets out of Git.
3.  Create `.env.example` only with placeholder variable names.
4.  Define environment/configuration conventions.
5.  Establish dependency management and reproducibility.
6.  Add README/project documentation.
7.  Define source contracts and data dictionary.
8.  Keep architecture decisions documented.
9.  Use Git branches / pull requests for material work.
10. Keep mandatory baseline and optional enhancements clearly separated.

The repository should make it obvious where to find:

``` text
source-generation code
data contracts
Databricks code
tests
API
LangChain
ML
CI/CD
documentation
```

------------------------------------------------------------------------

# 11. Phase 1 --- Generate the Synthetic Banking Data

Build the complete synthetic banking universe according to `DATA.md`
(already implemented and frozen as generator `data-generator-v1`).

High-level sequence:

``` text
1. validate branches/products
2. generate macroeconomic context
3. generate customers
4. generate longitudinal customer histories
5. generate applications
6. make application decisions
7. create approved loans
8. create repayment schedules
9. simulate financial behavior
10. create actual repayment outcomes
11. generate transaction events
12. validate clean truth
13. inject controlled dirty data
14. create late/corrected records
15. export four source batches
16. generate validation report
```

Do not train the final ML model during this phase.

------------------------------------------------------------------------

# 12. Phase 2 --- Bronze Layer

## Purpose

Bronze preserves the source representation and establishes traceability.

Bronze is **not** where business cleaning occurs.

For each relevant source, create parameterized ingestion logic for CSV
and JSON.

Expected Bronze tables correspond broadly to:

``` text
bronze_customers
bronze_loan_applications
bronze_repayments
bronze_transactions
bronze_branches
bronze_products
bronze_macroeconomic_monthly
```

Exact catalog/schema naming should follow the team's agreed Databricks
convention.

## Required ingestion metadata

Add fields such as:

``` text
ingestion_timestamp
batch_id
source_filename
record_hash
load_status
```

Also preserve source-system/business keys.

## Bronze must demonstrate

``` text
schema validation
controlled schema-drift handling
incremental ingestion
idempotent reruns
input/written/rejected counts
duration
failure logging
source-to-record traceability
```

Acceptance concept:

> Any downstream record should be traceable back to the source file and
> ingestion batch, and rerunning a failed/already processed batch must
> not create uncontrolled duplicates.

------------------------------------------------------------------------

# 13. Phase 3 --- Silver Layer

## Purpose

Silver turns raw source records into trusted, conformed analytical data.

Required work includes:

``` text
type standardization
date standardization
code normalization
currency/unit normalization
deduplication
domain validation
referential-integrity validation
JSON flattening
reference-data enrichment
late-arriving handling
corrected-record handling
```

## Data-quality dimensions

Implement measurable rules for:

``` text
completeness
validity
uniqueness
referential integrity
```

## Quarantine

Invalid records should not simply disappear.

Create quarantine outputs containing at least:

``` text
record identifier
source
failed rule
reason
processing timestamp
```

The project should be able to show examples of dirty Bronze records
being either:

``` text
standardized/fixed when safely recoverable
or
quarantined when analytically unsafe
```

Silver should preserve genuine adverse banking behavior.

A borrower being delinquent is not a Silver error.

------------------------------------------------------------------------

# 14. Phase 4 --- Gold Dimensional Model

## Official Team 2 facts

``` text
fact_loan_application
fact_repayment
```

## Official Team 2 dimensions

``` text
dim_date
dim_customer_segment
dim_product
dim_branch
dim_risk_band
dim_application_status
```

Additional dimensions may be added only when they improve the model
without unnecessary complexity.

## Grain

The grain must be explicit.

### `fact_loan_application`

``` text
one row per loan application
```

### `fact_repayment`

``` text
one row per defined repayment analytical event/installment grain
```

The exact implementation must remain consistent with the source
repayment design and be documented.

## Gold requirements

Implement:

``` text
surrogate keys where appropriate
unknown dimension members
business-ready measures/status logic
optimized Delta layout
Silver→Gold reconciliation
table/column documentation
```

Do not place inconsistent business logic independently inside Power BI
visuals.

Gold should be the reusable governed analytical foundation.

------------------------------------------------------------------------

# 15. Core Banking KPIs

The mandatory KPIs are:

``` text
1. Applications
2. Requested Amount
3. Approval Rate
4. Average Decision Time
5. Debt-to-Income Band
6. Delinquency Rate
7. Outstanding Balance
8. Manual-Review Rate
```

Each KPI must have a documented definition.

Examples of questions that must be resolved explicitly:

``` text
What statuses belong in the approval-rate denominator?
What exactly defines delinquency?
At what reporting date is outstanding balance measured?
How are withdrawn applications treated?
How are missing/quarantined records treated?
How is DTI calculated?
```

Definitions must be consistent across:

``` text
Gold
Fabric
Power BI
FastAPI
LangChain answers
```

------------------------------------------------------------------------

# 16. Phase 5 --- Microsoft Fabric Semantic Model

Connect Fabric to the curated Gold model using the agreed access
pattern.

The semantic layer should hide technical implementation details and
expose understandable banking terminology.

Required:

``` text
relationships
hierarchies
formats
descriptions
proper date table
dedicated measures table
validated filter direction
```

Create at least **8 explicit DAX measures**, including examples of:

``` text
volume
rate/ratio
trend
exception
```

The eight mandatory Team 2 KPIs are a natural core, but additional DAX
measures may be needed for richer analysis.

Implement Row-Level Security where relevant to branch/region ownership.

Validate semantic totals against Gold.

------------------------------------------------------------------------

# 17. Phase 6 --- Power BI

Required report structure must include at least three pages, while Team
2's assigned design suggests:

``` text
1. Portfolio Overview
2. Application Funnel
3. Risk & Affordability
4. Branch / Product Drill-through
5. Exceptions
```

## Portfolio Overview

Possible content:

``` text
applications
requested amount
approval rate
outstanding balance
delinquency rate
trend over time
portfolio mix
```

## Application Funnel

Possible flow:

``` text
submitted
→ reviewed/manual review
→ approved/rejected/withdrawn
```

Analyze decision times and approval behavior.

## Risk & Affordability

Analyze:

``` text
risk bands
DTI bands
loan-to-income / affordability
delinquency
customer segment
product
```

## Branch / Product Drill-through

Enable drill-through from portfolio totals to:

``` text
region
branch
product family
product
```

## Exceptions

Surface analytically important exceptions such as:

``` text
delinquent loans
high DTI
manual-review cases
quality exceptions where appropriate
```

Reports should include:

``` text
filters
tooltips
accessible titles
clear units
last-refresh indicator
```

------------------------------------------------------------------------

# 18. Phase 7 --- FastAPI

Build a validated REST integration layer.

Required minimum endpoints:

``` text
GET  /health
POST /analytics/query
POST /assistant/query
+ one Team-2-specific domain endpoint
```

Possible domain endpoint:

``` text
GET /portfolio/summary
```

or another clearly useful banking endpoint.

Use:

``` text
FastAPI
Pydantic request/response models
validation
consistent exceptions/errors
OpenAPI/Swagger
correlation IDs
structured logs
```

Provide executable request examples or a Postman collection.

## Security

During development, an agreed API-key mechanism may be used.

The deployed design should document stronger bearer/JWT/OAuth2-style
authentication as appropriate.

Never expose secrets in logs or Git.

------------------------------------------------------------------------

# 19. Phase 8 --- LangChain Core AI Assistant

The AI assistant is an interface over **approved analytical
capabilities**.

It must not:

``` text
query arbitrary raw data without governance
invent metrics
fabricate values
bypass the semantic/Gold analytical layer
approve/reject loans
change customer data
take consequential lending actions
```

Required:

``` text
system messages
human messages
AI messages
tool messages
prompt templates
structured output
typed tools
tool-call validation
error handling
```

At least two typed tools are required:

``` text
Tool 1:
retrieve a KPI / aggregate

Tool 2:
retrieve filtered detail or metadata
```

Possible examples:

``` text
get_portfolio_kpis(...)
get_branch_performance(...)
get_product_metrics(...)
get_metric_definition(...)
```

A response should distinguish:

``` text
answer
evidence
filters
source/measure
limitations
```

The assistant should be auditable: a question triggers an approved tool
call, the tool retrieves governed evidence, and the LLM explains that
evidence.

------------------------------------------------------------------------

# 20. Phase 9 --- Azure Foundation and Security

Document and implement the Azure foundation needed for the integration
components.

Cover:

``` text
Azure account/subscription boundary
Resource Group
IAM
least privilege
runtime identity
Storage
Compute
Networking
Key Vault
environment separation
```

Secrets must live outside source control.

Provide:

``` text
Azure resource inventory
environment/architecture diagram
responsibility/configuration notes
```

The design should distinguish at least development and target/release
environments where practical.

------------------------------------------------------------------------

# 21. Phase 10 --- CI/CD

Use:

``` text
GitHub Actions
or
Azure DevOps Pipelines
```

The pipeline definition must be versioned.

Required triggers:

``` text
pull request
main branch
```

Required logical jobs:

``` text
lint
test
build
deploy
```

Build the API/container as a reproducible artifact where applicable.

Use secret stores, environments and approvals.

Document:

``` text
rollback
configuration promotion
deployment approval evidence
failure behavior
```

A controlled source change should trigger quality gates automatically.

------------------------------------------------------------------------

# 22. Phase 11 --- Testing, Reconciliation and Observability

Testing is not a final afterthought.

Implement tests throughout the project.

## Source-generation tests

``` text
schema
relationships
temporal consistency
distribution checks
reproducibility
DQ injection
```

## Bronze tests

``` text
schema validation
metadata presence
idempotency
batch counts
```

## Silver tests

``` text
DQ rules
deduplication
referential integrity
quarantine
correction handling
```

## Gold tests

``` text
grain uniqueness
surrogate-key behavior
unknown members
Silver→Gold reconciliation
critical monetary totals
```

## API tests

``` text
request validation
success responses
error responses
authentication
health/readiness
```

## LangChain tests

``` text
tool schema
tool arguments
grounding
out-of-scope requests
tool failure
structured output
```

## ML tests, later

``` text
snapshot correctness
feature cutoff correctness
target-window correctness
right-censoring
leakage checks
prediction schema
```

Also retain logs/evidence suitable for the final demonstration.

------------------------------------------------------------------------

# 23. Optional Enhancement --- Predictive Portfolio Early-Warning ML

This is a custom project enhancement and must be implemented **after the
mandatory baseline works**.

## Business question

For an active approved/originated loan that is currently performing at
date `t`:

> What is the probability that the loan reaches **30+ Days Past Due
> within the next 90 days**?

This transforms the project from only:

``` text
descriptive analytics
"What happened?"
```

and:

``` text
diagnostic analytics
"Where and why did it happen?"
```

to also:

``` text
predictive analytics
"Where is future portfolio risk emerging?"
```

------------------------------------------------------------------------

# 24. ML Unit of Analysis

Recommended ML grain:

``` text
one active performing loan
×
one monthly snapshot date
```

For snapshot date `t`:

``` text
features = information available on or before t

target = 1
if the loan reaches 30+ DPD during (t, t + 90 days]

otherwise target = 0
```

Loans already 30+ DPD at the snapshot are not early-warning candidates.

Snapshots without a complete 90-day future window are right-censored and
excluded from supervised target creation.

------------------------------------------------------------------------

# 25. ML Feature Families

Possible feature families:

## Origination / credit

``` text
risk score
DTI
loan-to-income
payment burden
approved amount
term
interest rate
product
```

## Customer history

``` text
customer tenure
new/existing customer
previous applications
previous loans
completed loans
previous delinquency
active-loan count
total exposure
```

## Repayment behavior

``` text
recent late count
missed count
partial-payment count
average/max DPD
payment ratio
recent deterioration
recovery behavior
```

## Cash flow

``` text
salary/inflow level
recent inflow change
net cash flow
outflow pressure
cash-flow volatility
transaction-activity change
```

## Context

``` text
branch
product
segment
macroeconomic conditions
```

Every feature must be computed **as of the snapshot date**.

------------------------------------------------------------------------

# 26. ML Leakage Rules

Never use future information.

A snapshot at `t` must not use:

``` text
future repayment status
future transactions
future DPD
future customer attributes
final loan outcome
hidden generator stress
hidden future delinquency probability
```

Historical application features must use the values captured at
application time.

This is a non-negotiable requirement.

------------------------------------------------------------------------

# 27. ML Development Strategy

Use a temporal split rather than a random row split.

Recommended sequence:

``` text
1. construct monthly snapshots
2. define eligible population
3. create 90-day target
4. remove right-censored snapshots
5. temporal train/validation/test split
6. establish simple baseline
7. train Logistic Regression
8. evaluate
9. train one nonlinear tree-based model
10. compare using validation data
11. select model
12. evaluate once on held-out test
13. assess calibration
14. create risk tiers
15. publish governed predictions
```

Candidate nonlinear model:

``` text
XGBoost
LightGBM
or Random Forest
```

Do not add many models merely for quantity.

------------------------------------------------------------------------

# 28. ML Metrics

Because delinquency is imbalanced, accuracy alone is insufficient.

Evaluate:

``` text
ROC-AUC
PR-AUC
precision
recall
F1
confusion matrix
Brier score / probability calibration
```

Also report:

``` text
number of positives
class prevalence
time period
eligible population
```

Do not optimize for an artificially impressive score.

The synthetic generator is deliberately designed so that risk score
alone does not perfectly predict future delinquency.

------------------------------------------------------------------------

# 29. Governed Prediction Output

The final model should publish a governed analytical prediction table
such as:

``` text
fact_loan_risk_prediction
```

Possible fields:

``` text
snapshot_date
application_id / loan identifier
delinquency_probability_90d
risk_tier
outstanding_balance
probability_weighted_exposure
model_version
optional top drivers
scored_at
```

Do not expose hidden generator variables.

------------------------------------------------------------------------

# 30. Predictive Power BI Extension

Once predictions exist, extend portfolio analytics with measures such
as:

``` text
High/Critical Risk Loans
High-Risk Outstanding Exposure
Portfolio Exposure at Risk %
Probability-Weighted Exposure
Newly At-Risk Loans
Risk Migration
```

Analyze predictive risk by:

``` text
branch
product
customer segment
new vs existing customer
single vs multiple active loans
time
```

Allow drill-through:

``` text
portfolio
→ branch/product/segment
→ loan
```

Important:

``` text
probability-weighted exposure
≠
regulatory Expected Loss
```

Do not label it as Expected Loss unless a proper PD/LGD/EAD framework is
actually implemented.

------------------------------------------------------------------------

# 31. Optional ML API / LangChain Integration

Only after the prediction table is stable, optional API/tool
capabilities may expose governed predictive analytics.

Examples:

``` text
get_high_risk_portfolio_summary(...)
get_risk_migration(...)
get_prediction_for_loan(...)
```

The LLM should explain model output and limitations.

It must not:

``` text
approve a loan
deny a loan
change a credit limit
automatically contact a customer
take collections action
```

------------------------------------------------------------------------

# 32. ML Model Card

Create a model card documenting:

``` text
purpose
target
eligible population
feature cutoff
training/validation/test periods
algorithms
metrics
class prevalence
calibration
limitations
synthetic-data nature
model version
intended use
prohibited use
```

State clearly:

``` text
educational capstone
synthetic data
non-production model
not for automated lending decisions
```

------------------------------------------------------------------------

# 33. Optional Bonus --- Knowledge Graph

The official assignment offers a **5% bonus challenge**:

> Build a simple Knowledge Graph from the team's domain and expose one
> graph-based query through the AI assistant.

This is optional.

Do not implement it until:

``` text
mandatory end-to-end baseline is complete
```

If implemented, keep the graph small and useful rather than building a
complex graph platform for its own sake.

------------------------------------------------------------------------

# 34. Recommended End-to-End Implementation Order

Follow this order unless a team dependency requires minor
parallelization:

``` text
PHASE 0
Repository / architecture / contracts

PHASE 1
Synthetic data generation

PHASE 2
Bronze ingestion

PHASE 3
Silver transformation + DQ + quarantine

PHASE 4
Gold dimensional model + reconciliation

PHASE 5
Fabric semantic model + DAX

PHASE 6
Power BI mandatory report

PHASE 7
FastAPI analytical layer

PHASE 8
LangChain approved tools + grounded assistant

PHASE 9
Azure security / resource design

PHASE 10
CI/CD + deployment

PHASE 11
Full testing / monitoring / documentation

BASELINE END-TO-END VALIDATION

PHASE 12 — OPTIONAL ENHANCEMENT
ML snapshots / features / labels

PHASE 13
ML training / evaluation / calibration

PHASE 14
Governed prediction table

PHASE 15
Predictive Power BI + optional predictive API/tool

PHASE 16 — OPTIONAL BONUS
Knowledge Graph

FINAL
End-to-end demo / presentation / Q&A preparation
```

The mandatory baseline always has priority over optional work.

------------------------------------------------------------------------

# 35. Workstream View

The assignment's four main ownership areas can be understood as:

## Data Engineering

Owns primarily:

``` text
source contracts
Bronze
Silver
audit metadata
DQ
quarantine
Databricks jobs
```

## Analytics

Owns primarily:

``` text
Gold
dimensional model
Fabric
DAX
Power BI
reconciliation
```

## AI & API

Owns primarily:

``` text
LangChain Core
tools
structured output
FastAPI
Pydantic
API security
```

## Cloud & DevOps

Owns primarily:

``` text
Azure architecture
IAM
Key Vault
CI/CD
deployment
monitoring
integration tests
```

However, every participant must understand the complete solution.

The custom ML enhancement cuts across Data Engineering, Analytics and
AI.

------------------------------------------------------------------------

# 36. Mandatory Deliverables

The final submission must provide evidence for:

``` text
Business and data brief
Architecture and lineage
Databricks implementation
Quality evidence
Dimensional model
Fabric and Power BI
LangChain Core integration
FastAPI integration
Azure design
CI/CD pipeline
Testing and operations
Final presentation
```

The final presentation is:

``` text
15-minute demonstration
+
5-minute Q&A
```

Every participant should contribute.

------------------------------------------------------------------------

# 37. Documentation That Should Exist in the Repository

Recommended project documentation:

``` text
README.md
PROJECT_OVERVIEW.md
DATA.md
DATA_DESIGN_DECISIONS.md
docs/
├── business_and_data_brief.md
├── data_dictionary.md
├── source_to_target_mapping.md
├── architecture.md
├── data_quality_rules.md
├── dimensional_model.md
├── kpi_definitions.md
├── api.md
├── azure_design.md
├── ci_cd.md
├── testing_and_operations.md
├── ml_model_card.md              # when ML exists
└── known_limitations.md
```

Documentation hierarchy:

``` text
PROJECT_OVERVIEW.md       whole-project architecture, scope and roadmap
DATA.md                   authoritative final synthetic banking dataset specification / data contract
DATA_DESIGN_DECISIONS.md  concise rationale for the major data-design choices
data/generated_metadata/schema_dictionary.md   generated schema / field-level reference
data/generated_metadata/generation_config.json canonical generation configuration
data/generated_metadata/generation_report.json canonical realised generation / validation report
```

Do not create empty documentation merely to satisfy this tree. Create
each document when its content becomes real.

------------------------------------------------------------------------

# 38. Lineage Story the Final Demo Should Be Able to Tell

The team should be able to pick a banking metric or record and explain:

``` text
Where did it originate?
        ↓
Which source file/batch contained it?
        ↓
How was it stored in Bronze?
        ↓
Which Silver rules affected it?
        ↓
Was anything quarantined?
        ↓
How was it represented in Gold?
        ↓
Which semantic measure uses it?
        ↓
How does it appear in Power BI?
        ↓
Can FastAPI retrieve the governed result?
        ↓
Can LangChain call the approved tool and explain it?
```

For the optional ML extension:

``` text
Which historical observations existed at snapshot t?
        ↓
Which features were constructed?
        ↓
What future window created the target?
        ↓
Which model/version generated the probability?
        ↓
How was that prediction exposed in predictive BI?
```

This traceability is one of the strongest ways to demonstrate that the
project is truly end to end.

------------------------------------------------------------------------

# 39. Definition of Done --- Mandatory Baseline

The mandatory project is not done because individual notebooks run.

It is done when:

-   [ ] source data are documented and reproducible;
-   [ ] Bronze ingestion works for CSV and JSON;
-   [ ] lineage metadata are present;
-   [ ] reruns are idempotent;
-   [ ] Silver applies documented quality rules;
-   [ ] invalid records are traceably quarantined;
-   [ ] late/corrected records are handled;
-   [ ] Gold contains documented facts/dimensions;
-   [ ] Silver→Gold reconciliation passes;
-   [ ] all mandatory banking KPIs are reproducible;
-   [ ] Fabric semantic relationships/measures work;
-   [ ] Power BI provides required analysis and drill-through;
-   [ ] FastAPI exposes validated analytical services;
-   [ ] LangChain uses approved typed tools and grounded evidence;
-   [ ] Azure IAM/secrets/resource design is documented/applied;
-   [ ] CI/CD runs lint/test/build/deployment stages;
-   [ ] monitoring/logging/testing evidence exists;
-   [ ] the team can demonstrate an end-to-end refresh.

------------------------------------------------------------------------

# 40. Definition of Done --- ML Enhancement

The predictive extension is complete only when:

-   [ ] baseline capstone already works;
-   [ ] eligible monthly loan snapshots are correctly constructed;
-   [ ] target is 30+ DPD within the following 90 days;
-   [ ] currently delinquent loans are excluded from early-warning
    scoring;
-   [ ] incomplete future windows are right-censored;
-   [ ] all features obey as-of-time rules;
-   [ ] no hidden synthetic generator state is used;
-   [ ] temporal train/validation/test split is used;
-   [ ] baseline + Logistic Regression + one nonlinear model are
    evaluated;
-   [ ] imbalance-aware metrics are reported;
-   [ ] calibration is assessed;
-   [ ] predictions are stored with model version;
-   [ ] predictive BI uses governed prediction outputs;
-   [ ] limitations are documented in a model card;
-   [ ] the model is clearly presented as synthetic/educational and
    non-production.

------------------------------------------------------------------------

# 41. Scope-Control Rules

When making implementation decisions:

## Priority 1

``` text
Make the mandatory baseline correct and demonstrable.
```

## Priority 2

``` text
Make it reproducible, traceable and testable.
```

## Priority 3

``` text
Improve analytical/business value.
```

## Priority 4

``` text
Add the ML enhancement.
```

## Priority 5

``` text
Add optional bonus features.
```

Do not sacrifice a required component for an optional sophisticated
feature.

------------------------------------------------------------------------

# 42. Instructions for Coding Assistants

When working in this repository:

1.  Read `PROJECT_OVERVIEW.md` first.
2.  Read `DATA.md` before modifying synthetic-data generation (the
    generator is frozen as `data-generator-v1`; changes need an explicit,
    versioned decision).
3.  Inspect existing code before creating new architecture.
4.  Preserve agreed business definitions and schemas.
5.  Do not silently rename fields, tables, KPIs or statuses.
6.  Do not change the fixed 12 branches or 5 products without explicit
    instruction.
7.  Do not introduce real PII.
8.  Do not commit secrets.
9.  Do not expose latent synthetic-generator variables downstream.
10. Respect event time and prevent future-data leakage.
11. Keep raw/Bronze, validated/Silver and business/Gold responsibilities
    separate.
12. Add tests with implementation changes.
13. Prefer reusable modules over one-off notebooks/scripts where
    practical.
14. Preserve traceability and reproducibility.
15. Clearly distinguish mandatory capstone requirements from custom
    enhancements.
16. Do not start optional ML/Knowledge Graph work at the expense of an
    incomplete mandatory pipeline.
17. If a requirement is ambiguous, inspect project documentation before
    inventing a rule.
18. Record important architectural decisions.

------------------------------------------------------------------------

# 43. One-Sentence Project Description

> **Team 2 is building a production-minded synthetic banking analytics
> platform that transforms heterogeneous loan, repayment, customer and
> transaction data through governed Bronze--Silver--Gold Databricks
> layers into Fabric/Power BI analytics, secured FastAPI services and a
> tool-grounded LangChain assistant, with an optional leakage-safe ML
> extension for 90-day 30+ DPD portfolio early warning.**

------------------------------------------------------------------------

# 44. Final Mental Model

Think of the project as five connected layers of value:

``` text
1. TRUST THE DATA
   Sources → Bronze → Silver

2. ORGANIZE THE BUSINESS
   Silver → Gold dimensional model

3. UNDERSTAND THE PORTFOLIO
   Gold → Fabric → Power BI

4. ACCESS IT SAFELY
   Gold/Semantic → FastAPI → LangChain tools

5. ANTICIPATE FUTURE RISK
   Historical governed data → ML → predictive portfolio analytics
```

All five depend on the same principle:

> **Every important number, answer and prediction should be
> reproducible, time-correct, governed and traceable back to evidence.**
