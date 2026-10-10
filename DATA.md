# DATA.md --- Team 2 Synthetic Banking Source Data: Final Specification (v1, FROZEN)

> **Status: FROZEN (generator tag `data-generator-v1`, seed 42).**
>
> This document is the authoritative specification of the **final** synthetic source
> dataset for Team 2 (Banking Loan Portfolio Analytics). It began life as the implementation
> brief for the generator and has been updated **in place** so that it now describes what the
> frozen generator actually produces.
>
> Convention used throughout:
>
> * **Design target** = what the brief asked for.
> * **Final realised value** = what the frozen generator produced (read from
>   `data/generated_metadata/generation_report.json`, `generation_config.json` and
>   `schema_dictionary.md`). Where the two differ, both are shown.
>
> Historical note: early drafts of this specification were titled `CLAUDE.md`; no file of that name exists.
> The rationale behind the major choices is in `DATA_DESIGN_DECISIONS.md`.

## 0. Mission and authority

This file is the authoritative specification of the **source-data layer** of Team 2 of the
AI & Data Capstone Project: **Banking Loan Portfolio Analytics**.

The generator that implements it lives in `src/team2_project/generation/` and is frozen.
It must not be changed without an explicit, versioned decision. If any repository file
conflicts with this specification, this file wins unless the user explicitly decides otherwise.

The generator does **not** train the final ML model. It produces a coherent, realistic,
longitudinal synthetic banking world that supports, without redesigning the sources:

1.  Databricks Bronze ingestion;
2.  Silver validation, standardization, deduplication and quarantine;
3.  Gold dimensional modeling;
4.  the mandatory Team 2 KPIs and Power BI;
5.  FastAPI and LangChain analytical tools;
6.  the optional ML-based **Predictive Portfolio Early-Warning System**.

The capstone baseline remains the priority; the ML extension uses the same governed data.

## 0A. Final realised dataset summary

All values below are read from the final canonical `generation_report.json` (seed 42).

### Scale (clean truth versus delivered)

| Source | Clean truth | Delivered rows (all batches, incl. defects/versions) |
|---|---:|---:|
| customers.csv | 15,000 customers | 17,740 |
| loan_applications.csv | 30,012 applications | 30,337 |
| repayments.csv | 371,260 instalments | 376,072 |
| transactions.json | 666,818 events | 672,794 |
| macroeconomic_monthly.csv | 120 months | 121 |
| branches.csv / products.csv | 12 / 5 | 12 / 5 |
| **Total delivered rows** | | **1,097,081** |

Clean truth is the internally consistent world *before* defects, late arrivals and
re-deliveries. Delivered rows are what the four batches actually contain.
`repayment_versions_delivered` = 372,850 (an instalment can be delivered more than once, see section 57).

### Delivered rows per batch

| File | batch_001 | batch_002 | batch_003 | batch_004 |
|---|---:|---:|---:|---:|
| branches.csv | 12 | - | - | - |
| products.csv | 5 | - | - | - |
| customers.csv | 14,683 | 1,012 | 997 | 1,048 |
| loan_applications.csv | 28,712 | 557 | 477 | 591 |
| repayments.csv | 355,324 | 6,830 | 6,388 | 7,530 |
| macroeconomic_monthly.csv | 118 | 1 | 1 | 1 |
| transactions.json | 640,538 | 12,025 | 10,353 | 9,878 |

### Portfolio and behaviour

| Metric | Final realised value |
|---|---|
| Date range of applications / events | 2016-01-01 .. 2025-12-31 (every calendar year 2016-2025 populated) |
| Approved loans | 12,572 (5,525 paid off, 416 matured but unresolved, 7,047 open in total) |
| Application status | APPROVED 12,572, REJECTED 15,789, WITHDRAWN 1,567, SUBMITTED 44, UNDER_REVIEW 40 |
| Approval rate (APPROVED / (APPROVED + REJECTED)) | 44.33% |
| Manual-review rate | 17.84% |
| Average decision time (approved + rejected) | 4.45 days |
| **Strict mature-loan eventual 30+ DPD prevalence** | **11.53% (1,191 / 10,333)**; all approved loans 9.72% |
| **90-day forward snapshot positive rate (quarterly generator diagnostic)** | **1.19% (1,330 positives / 112,175 labelled snapshots)**; test period 1.08% (588 positives) |
| Cash-flow coverage (borrowers with >= 12 non-loan events) | 61.4% (any non-loan event: 95.1%) |
| Overall delivered-row defect rate | 4.25% |
| Diagnostic AUC: risk score only (loan level / snapshot test) | 0.620 / 0.595 |
| Diagnostic AUC: origination only | 0.656 |
| Diagnostic AUC: origination + behaviour | 0.868 |
| Recovery cases (late/partial/missed then 3 consecutive on-time) | 7,448 loans; 576 after a 30+ DPD instalment |
| Customers with several loans / overlapping loans | 3,329 / 2,459 |

### Data quality, late and corrected records (delivered)

| Source | Rows affected by an injected defect | Share of delivered rows |
|---|---:|---:|
| customers.csv | 1,017 | 5.73% |
| loan_applications.csv | 1,747 | 5.76% |
| repayments.csv | 17,894 | 4.76% |
| transactions.json | 26,020 | 3.87% |
| macroeconomic_monthly.csv | 2 | 1.65% |
| branches.csv | 0 | 0.00% |
| products.csv | 0 | 0.00% |

Late-arriving records: customers 16, applications 21, transactions 23.
Corrected records (wrong value delivered first, right value later): customers 93, applications 113, transactions 252.

### Design targets that differ from, or need interpretation against, the realised values

| Design target | Final realised | Comment |
|---|---|---|
| 200k-350k repayment rows (soft) | 371,260 | About 6% above the soft upper bound. Natural loan terms and recent-weighted origination produced it; the count was not clipped (section 6). Reported as an advisory, not a failure. |
| Macro defects 0-1% | 1.65% | Two defects in 121 delivered rows (one duplicate month, one missing optional indicator). |
| 30+ DPD 8-12% | 11.53% (loan level) | Met at loan level. The snapshot-level 90-day rate is a different quantity (section 66). |

### Verification status of the frozen version

41/41 clean-truth consistency checks; 40/40 mandatory acceptance checks (one advisory: repayment rows);
23/23 tests; same-seed reproducibility (26/26 files identical); cross-process `PYTHONHASHSEED`
determinism; latest-wins reconstruction equals clean truth; no forbidden/latent field in any delivered file.

------------------------------------------------------------------------

# 1. Official Team 2 requirements that the generated data must support

The official Team 2 business case is **Banking Loan Portfolio
Analytics**.

The mandatory source domains are:

``` text
customers.csv
loan_applications.csv
repayments.csv
transactions.json
```

This project additionally uses:

``` text
branches.csv
products.csv
macroeconomic_monthly.csv
```

The required analytical grains are:

``` text
one loan application
and, separately,
one scheduled or actual repayment transaction
```

The required Team 2 KPIs are:

``` text
Applications
Requested Amount
Approval Rate
Average Decision Time
Debt-to-Income Band
Delinquency Rate
Outstanding Balance
Manual-Review Rate
```

The priority Team 2 data-quality problems that must be demonstrable are:

``` text
missing consent/status
inconsistent amounts
impossible dates
duplicate applications
orphan repayments
out-of-range risk scores
```

The generated sources must also support:

``` text
Portfolio overview
Application funnel
Risk and affordability
Branch/product drill-through
Exceptions
```

The common capstone architecture requires raw CSV/JSON sources, Bronze
ingestion metadata, idempotent reruns, incremental loading or justified
refresh behavior, Silver quality rules/quarantine, Gold dimensional
analytics, and documented handling of late-arriving and corrected
records.

------------------------------------------------------------------------

# 2. Non-negotiable design principle

Do **not** generate independent random tables.

Generate a single coherent banking universe in chronological order.

Required causal/temporal structure:

``` text
reference data
    ↓
macroeconomic environment
    ↓
customers enter the bank over time
    ↓
customer financial state evolves
    ↓
customers submit applications
    ↓
applications are reviewed/approved/rejected/withdrawn
    ↓
approved applications create loan accounts
    ↓
repayment schedules are created
    ↓
cash-flow activity occurs over time
    ↓
scheduled installments become actual payment outcomes
    ↓
some customers remain healthy
some experience temporary stress and recover
some deteriorate gradually
a minority reach 30+ DPD
    ↓
controlled source-data defects are injected
    ↓
files are delivered in ingestion batches
```

A customer must have a **history**, not merely a row.

------------------------------------------------------------------------

# 3. Generate clean truth first, dirty source second

This rule is mandatory.

## Phase A --- clean internal truth

First generate an internally consistent clean banking universe.

All:

-   temporal relationships;
-   primary/foreign keys;
-   application decisions;
-   loan schedules;
-   payments;
-   customer histories;
-   transaction histories;
-   delinquency behavior

must make sense before defects are introduced.

## Phase B --- controlled source defects

Only after the clean universe passes validation, create source-quality
defects.

This makes it possible to know:

``` text
what is genuine adverse business behavior
vs
what is bad source data
```

Do not mix these concepts.

## Implementation of the two phases

Phase A produces in-memory clean-truth tables (`tables.py`). Before any defect exists they must pass
**41 consistency checks** (`validate.py`, `validate_clean`): key uniqueness, foreign keys, temporal order,
amount/term/product ranges, status coherence, amortisation (scheduled principal equals the approved amount),
payment-event reconciliation, DPD coherence, loan-state invariants and absence of forbidden columns.
Phase B (`batches.py`, `defects.py`) builds the delivered copies and injects defects. Only delivered
copies are exported; clean truth never leaves the generator. The development-only manifest records
every deliberate defect so that the clean value and the delivered value are both known.

------------------------------------------------------------------------

# 4. Final source datasets

Generate:

``` text
branches.csv
products.csv
customers.csv
loan_applications.csv
repayments.csv
macroeconomic_monthly.csv
transactions.json
```

This is:

``` text
6 CSV sources
1 semi-structured JSON event source
```

JSON Lines may be used internally/exported as `.json` if the existing
project convention expects that filename, but preserve a clearly
documented event-record structure.

Do not create raw business sources such as:

``` text
ml_features.csv
delinquency_labels.csv
risk_predictions.csv
future_default.csv
hidden_stress.csv
```

Those are downstream analytical artifacts.

**Final form of the sources:** `transactions.json` is **JSON Lines** (one event per line, UTF-8). Every other
source is a UTF-8 CSV with a header row. Reference files (`branches.csv`, `products.csv`) are delivered in batch_001
only; the remaining files are delivered in all four batches (section 59).

------------------------------------------------------------------------

# 5. Historical horizon

## Final decision

Generate **10 complete calendar years**:

``` text
2016-01-01 through 2025-12-31
```

This is intentional.

The 10-year horizon should provide enough history for:

-   customer tenure;
-   repeat applications;
-   paid-off (fully settled) loans;
-   prior delinquency;
-   recovery;
-   multiple simultaneous loans;
-   long-running mortgages;
-   changing economic/rate environments;
-   temporal ML development;
-   enough mature loans with future observation windows.

## Do not start all customers in 2016

Customers must enter throughout the decade.

Some may already have a banking relationship before 2016.

Example:

``` text
customer_created_at = 2013-07-12
first generated detailed application = 2017-02-08
```

This is acceptable.

## Why branch opening dates may be older

The existing branch master may contain branches opened in the
1990s/2000s.

That does **not** require generating detailed transactions back to the
branch opening date.

Branch opening history is reference/master data.

Detailed analytical event generation begins in 2016.

**Final realised:** application dates run from 2016-01-01 to 2025-12-31;
every calendar year 2016-2025 has applications, transaction events and due instalments
(applications per year: 2016: 997, 2017: 1,456, 2018: 1,788, 2019: 2,192, 2020: 2,421, 2021: 3,195, 2022: 3,718, 2023: 4,219, 2024: 4,746, 2025: 5,280).
Activity extends to the last day of the horizon (latest application 2025-12-31, latest event
2025-12-31, latest instalment due date 2025-12-25). Origination volume grows over the decade
(growth weighting plus a COVID-period dip in spring 2020); customers enter every year 2008-2025 and
4,602 of 15,000 customers (30.7%) pre-date 2016.

------------------------------------------------------------------------

# 6. Dataset size

Storage is not the limiting constraint. The dataset must be large enough to produce meaningful BI,
longitudinal behavior and a later ML dataset, without manufacturing meaningless volume.

## Design targets (approximate, not quotas)

``` text
customers                         ~15,000
loan applications                 ~30,000-40,000
repayment/installment rows        ~200,000-350,000   (soft)
transaction events                ~400,000-700,000
macroeconomic monthly rows        120
branches                          12
products                          5
total raw volume                  roughly 650,000-1,100,000 records/events
```

Natural counts are preferred to round numbers; valid rows must never be duplicated just to raise volume.

## Final realised values

| Item | Design target | Final realised (clean truth) | In range? |
|---|---|---:|---|
| customers | ~15,000 | 15,000 | yes |
| loan applications | 30,000-40,000 | 30,012 | yes |
| repayment instalments | 200,000-350,000 (soft) | 371,260 | **no: about 6% above (advisory)** |
| transaction events | 400,000-700,000 | 666,818 | yes |
| macro months | 120 | 120 | yes |
| delivered rows, all sources and batches | 650,000-1,100,000 | 1,097,081 | yes (just inside the upper bound) |

**Why repayment rows exceed the soft target.** One row exists per scheduled instalment that has fallen due by
2025-12-31. With about 12,572 approved loans, a median of 27 due instalments per loan
(95th percentile 60) and a ten-year history in which mortgages and long consumer loans accrue many instalments, the count
arises naturally. It was deliberately **not** clipped, because shortening terms, dropping approved loans or truncating schedules would
distort loan histories that the Silver/Gold/ML phases depend on.

------------------------------------------------------------------------

# 7. branches.csv

## Final decision

Use exactly the **existing 12 branches**.

Do not expand to 16, 20, 30 or 40 unless the user later explicitly
changes this decision.

Preserve the current branch master and codes.

Expected schema:

``` text
branch_code
branch_name
city
region
opened_date
```

Existing branches currently provide enough branch/regional variation for
the project.

The 12-branch design is sufficient for:

-   branch KPIs;
-   regional comparisons;
-   branch/product drill-through;
-   application volume;
-   approval-rate comparisons;
-   delinquency comparisons;
-   predictive-risk aggregation.

Do not create branch-specific delinquency rules.

Branch may affect operational patterns such as application
volume/product mix, but branch itself should not be a hidden
deterministic risk label.

`branch_code` must remain stable, unique and clean.

**Final realised:** the existing 12 branches (BR001-BR012; regions Attica, Central Macedonia, Crete, Thessaly, Western Greece) are
delivered unchanged in batch_001. Branches only shape application volume and channel mix (catchment weight and a digital-propensity index);
there is no branch-specific risk rule. Application volume by branch ranges from 1,236 (BR008) to 4,616 (BR001); the loan-level 30+ DPD prevalence
across branches stays within 9.5%-12.8% (no hidden branch effect).

------------------------------------------------------------------------

# 8. products.csv

## Final decision

Use exactly the **existing 5 products**.

Do not add products unless the user later explicitly changes this
decision.

The current catalogue contains distinct lending profiles such as:

``` text
Personal Loan
Green Home Upgrade Loan
New Car Loan
Fixed-rate Mortgage
SME Working Capital
```

Preserve the current product codes and reference values.

Expected schema:

``` text
product_code
product_name
product_family
min_amount
max_amount
min_term_months
max_term_months
base_rate
```

The five products are enough to produce meaningful variation in:

-   amount;
-   term;
-   borrower profile;
-   pricing;
-   payment burden;
-   repayment duration.

`product_code` must remain stable, unique and clean.

**Final realised:** the existing 5 products (PL-STD, PL-GRN, AUT-NEW, MTG-FIX, SME-WCL) are delivered unchanged in batch_001.
Application mix: PL-STD 49.0%, AUT-NEW 24.1%, SME-WCL 10.0%, PL-GRN 10.0%, MTG-FIX 7.0%. Eventual 30+ DPD prevalence differs by product
(AUT-NEW 13.3%, MTG-FIX 22.1%, PL-GRN 12.9%, PL-STD 9.3%, SME-WCL 16.4%) because of the interacting loan, borrower and exposure
characteristics, not because any product is hard-wired to delinquency.

------------------------------------------------------------------------

# 9. macroeconomic_monthly.csv

This is a **monthly economic-context source**, not customer data and not
an ML label.

Generate one row per calendar month from:

``` text
2016-01 through 2025-12
```

Total:

``` text
120 rows
```

Recommended schema:

``` text
month
inflation_rate
unemployment_rate
reference_rate
consumer_confidence_index
```

If another macro variable is added, it must have a clear purpose.

## Purpose

The banking portfolio should not behave as if the external economy were
identical for ten years.

This source allows:

-   interest-rate environment to change over time;
-   application pricing to change over time;
-   household/business financial pressure to vary;
-   the hidden stress simulation to respond moderately to the economy;
-   later ML snapshots to use contemporaneous economic context;
-   BI to compare portfolio behavior across economic periods.

## Influence rule

Macro conditions must have a **moderate probabilistic effect**, not a
deterministic effect.

Never implement:

``` text
inflation > threshold → delinquent
```

Instead:

``` text
macro pressure
+ customer vulnerability
+ debt burden
+ cash-flow deterioration
+ idiosyncratic shocks
→ change in stress probability
```

A financially resilient customer may remain healthy in a difficult
period.

A vulnerable highly leveraged customer may become more likely to
deteriorate.

## Historical shape

The series should be calibrated to plausible Greek/Euro-area historical
patterns for 2016--2025.

Do not create unrealistic extreme cycles merely to strengthen ML signal.

If actual public historical values are used, document their source
separately.

If synthetic calibrated values are used, clearly label them as
synthetic.

## Final implementation

* Anchored interpolation plus small AR(1) noise: Greek-like unemployment (about 24.6% in 2016 to about 8.5% in 2025), inflation (negative around
  2016/2020, peaking above 12% in late 2022), an ECB-style reference-rate step path (0% until mid-2022, up to 4.5% in 2023-24, 2.15% by mid-2025) and a
  synthetic 0-100 consumer-confidence index. All values are **synthetic and approximate** and are labelled so.
* `reference_rate` passes through to product pricing (section 31). An **internal standardised macro-pressure score** (not exported) moderately
  shifts the hidden financial-stress process (section 45); it never deterministically causes delinquency.
* **Publication-lag limitation.** Each month's values are keyed to the calendar month with no publication lag, and the reference rate applies for the
  whole month of a change (a mid-month move applies from the first day of that month). The later ML phase **must lag monthly macro features**
  appropriately to avoid publication-time leakage.
* Delivery: batch_001 carries 2016-01..2025-09; batches 002-004 carry October, November and December 2025 respectively. One duplicated month and one
  missing optional indicator are deliberate defects (section 55).

------------------------------------------------------------------------

# 10. Primary identifiers

Use stable IDs.

Primary identifiers:

``` text
branches.branch_code
products.product_code
customers.customer_id
loan_applications.application_id
repayments.repayment_id
transactions.event_id
```

Canonical primary IDs must:

-   be unique;
-   be non-null;
-   remain stable.

Do **not** deliberately corrupt primary IDs to create DQ examples.

Controlled foreign-key defects may be injected later.

**Final formats:** `customer_id` CU000001.., `application_id` LA000001.. (chronological by application date), `repayment_id` RP0000001.. (by
application then instalment number), `event_id` EV000000001.. (chronological by event time). Related references: loan account `LN` + the application
number, current account `AC` + the customer number, household `HH` + 6 digits. Primary identifiers of existing records are never corrupted. The only
new identifiers created by defects are the intentionally re-keyed duplicate applications and duplicate-installment repayment rows, which are logged
in the manifest.

------------------------------------------------------------------------

# 11. customers.csv schema

Required fields:

``` text
customer_id
first_name
last_name
email
phone
date_of_birth
segment
annual_income
household_id
employment_status
employment_start_date
created_at
updated_at
```

Optional only if useful:

``` text
residence_region
```

Do not add protected/sensitive demographic fields merely for ML.

------------------------------------------------------------------------

# 12. Customer names

Target approximately:

``` text
85–90% Greek-name pool
10–15% international-name pool
```

Use sufficiently large name pools so repeated combinations do not look
artificial.

Names must **not** influence:

-   approval;
-   risk score;
-   delinquency;
-   stress.

Do not use nationality/name as a risk proxy.

**Final realised:** 87.6% of first names are from the Greek pool (design target 85-90%). Households share a surname
(feminine forms for Greek women).

------------------------------------------------------------------------

# 13. Emails

Emails do not follow a single Faker template. Seven provider domains are used with these final weights:
gmail.com 0.46, hotmail.com 0.12, outlook.com 0.10, yahoo.com 0.10, yahoo.gr 0.10, icloud.com 0.08, proton.me 0.04
(yahoo.com and yahoo.gr are intentionally different domains).

Eleven local-part patterns are used:

``` text
firstname.lastname
firstinitial.lastname
lastname.firstname
firstnameYYYY (birth year)
initials_number
first-last
nickname (first name only)
firstname-lastinitial+number
handle+number (a plausible handle unrelated to the legal name)
lastname.firstinitial
firstnamelastname
```

Examples: `g.papadopoulos@gmail.com`, `giannis1987@hotmail.com`, `papadopoulos.g@outlook.com`, `maria-k23@gmail.com`, `gp_91@yahoo.com`,
`bluewave84@gmail.com`. Not every valid email visibly corresponds to the legal name. Clean emails are unique.

Controlled dirty examples (section 51): missing email, whitespace, malformed address, duplicate contact email, unusual casing, malformed domain.
**Final realised:** 1.63% of delivered customer rows have a missing or invalid email.

------------------------------------------------------------------------

# 14. Phone numbers

Generate plausible Greek phone values with source-format variation.

Valid examples may look like:

``` text
69XXXXXXXX
+3069XXXXXXXX
003069XXXXXXXX
210XXXXXXX
+30210XXXXXXX
```

Controlled defects may include:

-   spaces/hyphens;
-   missing values;
-   invalid prefix;
-   too few digits;
-   stray characters.

The later Silver layer should standardize valid variants.

**Final realised:** formats are mixed as designed (plain 69X, +3069X, 003069X mobiles; 210X/other-area landlines, with and without +30).
1.68% of delivered customer rows have a non-standard or missing phone.

------------------------------------------------------------------------

# 15. Date of birth

Generate adult customers using a realistic non-uniform age distribution.

Do not make age uniform.

Include:

-   younger adults;
-   a large working-age population;
-   older customers.

Product/term combinations should remain plausible.

For example, very long mortgage terms should not routinely extend to
implausible ages.

Age should not deterministically decide approval or delinquency.

**Final realised age distribution at 2025-12-31:** median 49, 5th-95th percentile 28-72,
maximum 87 (mixture of a young-adult group, a large working-age group and an older group). Loan terms are capped so that a
loan generally ends by about age 75 (mortgage applicants are 25-62); a small number of non-mortgage loans still end after age 80 (section 86).

------------------------------------------------------------------------

# 16. Customer segments

Preserve the project's existing segment vocabulary if already
established.

Preferred existing-style vocabulary:

``` text
MASS
AFFLUENT
PREMIER
SME
```

If the current repository uses slightly different names, preserve them
consistently rather than creating unnecessary renaming work.

Segments should correlate moderately with income/product behavior, but
not perfectly.

**Final realised:** MASS 69.2%, AFFLUENT 20.8%, SME 6.0%, PREMIER 4.0%. Segment is related to income and self-employment but not deterministically.

------------------------------------------------------------------------

# 17. Employment status

Use a realistic controlled vocabulary such as:

``` text
EMPLOYED
SELF_EMPLOYED
RETIRED
UNEMPLOYED
STUDENT
OTHER
```

Not every status needs equal frequency.

Employment status should influence income distribution and income
stability probabilistically.

It must not directly determine delinquency.

**Final realised:** EMPLOYED 62.5%, SELF_EMPLOYED 12.9%, RETIRED 12.2%, UNEMPLOYED 5.3%, OTHER 5.1%, STUDENT 2.0%. Employment evolves through yearly state-change events (14,110 customers have at least one change event).

------------------------------------------------------------------------

# 18. Annual income --- required generation behavior

Do **not** generate annual income from a uniform distribution.

Bad:

``` python
annual_income = random.uniform(10000, 120000)
```

This makes high incomes unrealistically common.

## Right-skewed income

Generate a right-skewed distribution.

Conceptually:

``` text
many customers          low-to-middle incomes
fewer customers         upper-middle incomes
much fewer customers    high incomes
small minority          high-income tail
```

Illustrative---not hard---shape:

``` text
many:          ~€15k–€35k
fewer:         ~€35k–€60k
much fewer:    ~€60k–€100k
small tail:    >€100k
```

Use a log-normal distribution, mixture distribution, or equivalent
realistic mechanism.

## Conditional income

Income should depend moderately on coherent attributes.

Examples:

``` text
EMPLOYED:
    narrower working-income distribution

SELF_EMPLOYED:
    wider variance; both low and high outcomes

RETIRED:
    different distribution

UNEMPLOYED:
    lower declared income on average, not necessarily zero

SME segment:
    broader distribution
```

Income may also correlate moderately with:

-   age/life stage;
-   employment tenure;
-   customer segment.

Do not make these relationships deterministic.

## Values should not look machine-rounded

Avoid every value ending in:

``` text
000
500
```

Use values such as:

``` text
18,430
22,760
31,180
47,860
68,540
112,300
```

**Final realised (current annual income):** median EUR 22,110, 25th-75th percentile EUR 14,230-34,982, 95th percentile EUR 68,251,
99th percentile EUR 124,792; 1.8% earn more than EUR 100,000 and 2.0% end in 000/500. Incomes are log-normal by employment
status with age and SME multipliers, rounded to 10 EUR, and evolve yearly with inflation-linked growth.

------------------------------------------------------------------------

# 19. Customer histories

Generate longitudinal customer histories.

Examples:

## Healthy repeat borrower

``` text
2016 customer already exists
2017 personal loan approved
2017–2019 healthy payments
2019 loan completed
2022 auto loan approved
2022–2025 healthy payments
```

## Gradual deterioration

``` text
stable customer
loan approved
payments initially on time
cash inflows weaken
5-day late payment
12-day late payment
partial payment
eventual 30+ DPD
```

## Temporary stress and recovery

``` text
healthy
temporary income/cash-flow shock
late
partial
recovers
returns to on-time payments
```

## Multiple active loans but healthy

``` text
mortgage
+
small personal loan
+
stable income
→ remains performing
```

## Good origination profile, later shock

``` text
good risk score
reasonable affordability
approved
later idiosyncratic shock
cash-flow deterioration
eventual delinquency
```

These should emerge probabilistically, not as five hard-coded templates
repeated across customers.

**Final realised:** 3,329 customers have more than one approved loan; 2,459 have overlapping loans;
5,525 loans were fully paid off; 576 loans recovered to three consecutive on-time payments after a 30+ DPD instalment;
98 customers took a later loan after an *already observable* 30+ DPD event. All paths emerge from the
stochastic simulation (section 45), not from fixed templates.

------------------------------------------------------------------------

# 20. household_id

Allow some customers to share a household.

Not every customer must have a shared household.

This provides realistic relationships without using household identity
as a direct delinquency rule.

`household_id` may be null for customers where the source does not
contain such information, if this is part of the intended design.

**Final realised:** 42.1% of customers share a household with at least one other customer; 7.2% have no household (null).

------------------------------------------------------------------------

# 21. loan_applications.csv schema

Required fields:

``` text
application_id
customer_id
branch_code
product_code
application_date
decision_date
status
requested_amount
approved_amount
currency
term_months
interest_rate
risk_score
monthly_debt
annual_income_at_application
employment_status_at_application
declared_monthly_expenses
consent_flag
manual_review
updated_at
channel
```

The three application-time snapshot fields are **required**:

``` text
annual_income_at_application
employment_status_at_application
declared_monthly_expenses
```

------------------------------------------------------------------------

# 22. Why application-time snapshots are mandatory

`customers.csv` may represent the customer's latest/current master
state.

A customer's financial situation can change over ten years.

Example:

``` text
2018:
income = €22,000
employment = EMPLOYED
expenses = €1,000/month
application submitted

2025:
income = €43,000
employment = SELF_EMPLOYED
```

The 2018 application must preserve what the bank knew **in 2018**.

Therefore:

``` text
annual_income_at_application = 22000
employment_status_at_application = EMPLOYED
declared_monthly_expenses = 1000
```

must remain attached to the 2018 application even if the customer's
current master record later changes.

This is necessary for:

-   historical underwriting analysis;
-   DTI/affordability calculation;
-   correct BI;
-   reproducible historical decisions;
-   leakage-safe ML.

Never use a 2025 customer value to explain a 2018 application.

**Final realised:** for 23,999 of 30,012 applications the application-time income differs from the
customer's current (2025) income, which is exactly the situation the snapshot fields protect against.

------------------------------------------------------------------------

# 23. monthly_debt and affordability

`monthly_debt` is the **existing monthly debt obligation known at application time, excluding the requested loan**. It is the sum of:

1.  an **external-obligation component**: a customer-specific share (zero for about 38% of customers) of the monthly income known at that date,
    with small noise;
2.  the **scheduled instalment** of every loan of this bank whose contractual schedule is **running** on the application date
    (including approved loans not yet disbursed);
3.  for every loan of this bank whose schedule has **ended** (maturity or early termination) but that is **not observably paid off** by the
    application date: **`min(last scheduled instalment, outstanding principal as of the application date)`**.

Component 3 is a **synthetic proxy for the monthly burden of unresolved post-schedule debt**. Unresolved debt never expires (there is no write-off
or closure model); it leaves the calculation only when it is observably paid off. The outstanding principal is reconstructed **strictly as of the
application date** (approved principal minus principal received on or before that date, interest-first allocation); payments dated later are never used.
The identical convention is used by the hidden financial-stress process (section 45), so underwriting and borrower behaviour agree.

``` text
monthly_income = annual_income_at_application / 12
DTI            = monthly_debt / monthly_income
```

`declared_monthly_expenses` is declared recurring living/business expenses, separate from debt payments; it supports richer affordability measures.
DTI is derived from the stored fields and is never independently randomized. DTI bands used in reporting: <20%, 20-35%, 35-50%, >50%.

**Final realised:** DTI median 0.13, 95th percentile 0.48; bands <20% 63.5%, 20-35% 20.7%, 35-50% 12.0%, >50% 3.8%. 785 applications carried a post-schedule unresolved-loan contribution; for 369 of them the outstanding-principal cap reduced the contribution below the scheduled instalment.

------------------------------------------------------------------------

# 24. Applications per customer

Customers may have:

-   zero applications;
-   one application;
-   multiple applications over the decade;
-   rejected then later approved applications;
-   completed loan followed by another;
-   simultaneous active loans.

Use a long-tailed distribution.

Most customers should have relatively few applications.

A minority may have several.

Do not force an unrealistically high number of applications per customer
just to hit row-count targets.

If application volume is too low, adjust customer count/application
propensity carefully rather than giving almost everyone many loans.

**Final implementation:** the number of applications per customer is Poisson with a gamma-distributed frailty (long tail), zero by design for 12% of customers (deposit-only; many other customers also end with no application in their exposure window), and
**deliberately capped at 8 per customer** as a synthetic-generation safeguard. **Final realised:** 8,961 customers applied at least once and
6,039 never did; the distribution is 1: 2,656, 2: 1,754, 3: 1,208, 4: 847, 5: 606, 6: 485, 7: 344, 8: 1,061 applications. The visible spike at 8 (1,061 of 8,961 applicants, about 12%) is a known artifact of the cap
and was not recalibrated (section 86). Applications by the same customer are at least 7 days apart.

------------------------------------------------------------------------

# 25. Application dates

Temporal rules:

``` text
customer.created_at <= application_date
branch.opened_date <= application_date
application_date <= decision_date
application_date <= updated_at
```

Except for deliberately injected source-quality defects.

Customers cannot apply before they exist in the bank's source history.

All four temporal rules hold in the clean truth (verified by the clean-truth checks). Deliberate violations exist only as delivered defects (section 52).

------------------------------------------------------------------------

# 26. Application statuses

Final vocabulary:

``` text
APPROVED     final
REJECTED     final
WITHDRAWN    final (withdrawn by the customer before a decision; decision_date = withdrawal date;
             a minority of withdrawals carry consent_flag = N)
SUBMITTED    not final - undecided at the end of the horizon, manual_review = N
UNDER_REVIEW not final - undecided at the end of the horizon, manual_review = Y
```

`SUBMITTED` / `UNDER_REVIEW` appear only for applications whose decision would fall after 2025-12-31; they have a null `decision_date`, no approved amount
and no rate. **An application row is written when it is decided**: `updated_at` is the decision time, and the row first appears in the batch that contains
that moment (an application submitted on 20 September and decided on 3 October is first delivered in batch_002). Undecided applications are written at their
submission time.

KPI conventions: Approval Rate = APPROVED / (APPROVED + REJECTED); WITHDRAWN and undecided applications are excluded from that denominator. Average Decision Time
uses APPROVED + REJECTED. Clean truth contains no contradictory status/decision combinations.

**Final realised:** APPROVED 12,572, REJECTED 15,789, WITHDRAWN 1,567, SUBMITTED 44, UNDER_REVIEW 40.

------------------------------------------------------------------------

# 27. Approval logic

Approval must be probabilistic and plausible.

It may depend on combinations of:

-   risk score;
-   DTI;
-   affordability;
-   requested amount relative to income;
-   product;
-   prior repayment history;
-   previous delinquency;
-   current active-loan exposure;
-   manual review;
-   controlled business randomness.

Do not create one deterministic rule such as:

``` text
risk_score >= 660 → approved
```

Threshold-like tendencies may exist, but there must be overlap and
counterexamples.

**Final implementation:** a logistic approval probability combines the risk score, the post-loan payment-to-income ratio, loan-to-income relative to a product-specific soft cap, employment-status penalties, observable prior 30+ DPD events (as of the application date), the number of loans in debt, and a product offset; the draw is then random. **Final realised approval rate by risk band:** 300-579: 6.8%, 580-669: 28.9%, 670-739: 51.1%, 740-799: 68.0%, 800-850: 78.5% (steep but never 0% or 100%, so counterexamples exist).

------------------------------------------------------------------------

# 28. Manual review

Manual review should be meaningful.

It may become more likely for:

-   borderline affordability;
-   borderline risk;
-   larger loans;
-   complex products;
-   inconsistent/borderline but still valid applications.

Manual review should generally increase decision time.

Do not make manual review identical to rejection.

Some manually reviewed applications should be approved and some
rejected.

**Final realised:** manual-review rate 17.8%; manual-review outcomes: APPROVED 37.9%, REJECTED 53.2%, WITHDRAWN 8.2%.
Manual review is more likely for borderline decisions, large loans and mortgage/SME products, and adds human-judgement noise to the decision.

------------------------------------------------------------------------

# 29. Decision time

Generate realistic decision-time variation.

Decision time may depend on:

-   product complexity;
-   channel;
-   manual review;
-   controlled operational variation.

Simple consumer applications may generally be faster.

Mortgage/SME/manual-review cases may generally take longer.

The required KPI:

``` text
Average Decision Time
```

must be meaningful.

**Final realised decision time (APPROVED + REJECTED):** median 2 days, 95th percentile 19, maximum 194;
mean by product AUT-NEW 2.4, MTG-FIX 26.1, PL-GRN 3.4, PL-STD 1.3, SME-WCL 11.6 days; manual review 13.2 days versus 2.6 days without. Decision dates are not business-day adjusted (section 86).

------------------------------------------------------------------------

# 30. Product amount and term rules

Clean valid applications should normally respect:

``` text
products.min_amount <= requested_amount <= products.max_amount
products.min_term_months <= term_months <= products.max_term_months
```

Controlled violations may later be injected as DQ defects.

Approved amount rules in clean truth:

``` text
approved_amount > 0 for approved loans
approved_amount <= requested_amount
```

Allow some partial approvals.

Rejected/withdrawn applications normally have no approved amount.

------------------------------------------------------------------------

# 31. Interest rates

Do not copy `products.base_rate` unchanged to every application.

Actual originated interest rate should depend on:

``` text
product pricing profile
+ macro/reference-rate environment at application time
+ risk adjustment
+ term adjustment
+ small controlled pricing noise
```

Rates must remain plausible for product and historical period.

Do not make interest rate a disguised target variable.

**Final pricing formula** (per approved application): `base_rate(product) + pass_through(product) x reference_rate(month) - 1.2% per +100 risk-score points (around 670) + term adjustment + noise`, clipped to 2%-22%.
Pass-through: PL-STD 0.60, PL-GRN 0.55, AUT-NEW 0.65, MTG-FIX 0.40, SME-WCL 0.70. **Final realised mean rates:** PL-STD 8.24% (2016) to 10.77% (2024); MTG-FIX 3.03% to 4.66%.

------------------------------------------------------------------------

# 32. Risk score

Use a documented bounded scale.

Recommended:

``` text
300–850
```

Generate a non-uniform realistic distribution.

Risk score should be informative for:

-   approval;
-   later repayment risk;

but it must **not** determine either outcome perfectly.

A small number of out-of-range values may be introduced later as
deliberate DQ defects.

**Final implementation:** the score combines a customer-level credit-quality trait (the same latent resilience that influences stress, with weight below 1), tenure, DTI, prior observable 30+ DPD events, previously *paid-off* loans (as of the application date) and
independent noise, clipped to 300-850. **Final realised:** median 685, 5th-95th percentile 541-813; about 1.7% of scores sit at the 850 ceiling.

------------------------------------------------------------------------

# 33. repayments.csv --- final schema

The original schedule-only schema is insufficient.

Use one row per **scheduled installment**.

Required fields:

``` text
repayment_id
application_id
installment_number
due_date
principal_due
interest_due
total_due
payment_date
principal_paid
interest_paid
total_paid
payment_status
days_past_due
currency
updated_at
```

**Final scope:** only instalments whose `due_date` is on or before 2025-12-31 exist (no future schedule is materialised); instalment numbers are contiguous from 1 for every loan; `repayment_id` is stable across versions of the same instalment.

------------------------------------------------------------------------

# 34. Meaning of repayment fields

Scheduled obligation:

``` text
principal_due, interest_due, total_due        (annuity amortisation on the scheduled balance; the final instalment absorbs rounding)
```

Actual outcome:

``` text
payment_date, principal_paid, interest_paid, total_paid
```

Performance:

``` text
payment_status, days_past_due
```

Final status vocabulary (an instalment is either **settled** or **open**):

| Status | State | Meaning |
|---|---|---|
| ON_TIME | settled | fully paid on or before `due_date` |
| LATE | settled | fully paid after `due_date`; `payment_date` is the final settlement date |
| PARTIAL | open | some but not all of `total_due` received so far; `payment_date` is the date of the last partial payment |
| MISSED | open | nothing received so far; `payment_date` is null |

A partially paid instalment that is later completed is delivered as `LATE` (final), and its individual payments are visible as separate events in
`transactions.json`. An open instalment is never written off.

Allocation of received money is **interest first**: for every payment, principal received = `max(0, cumulative paid - interest_due)` minus principal already counted.

------------------------------------------------------------------------

# 35. Why actual repayment fields are required

Without actual-payment information, the project cannot robustly derive:

-   late payments;
-   partial payments;
-   missed payments;
-   delinquency;
-   payment ratios;
-   repayment deterioration;
-   recovery;
-   30+ DPD outcomes.

The scheduled fields answer:

``` text
"What should have been paid?"
```

The actual fields answer:

``` text
"What was actually paid and when?"
```

Both are required.

------------------------------------------------------------------------

# 36. Partial payments

`repayments.csv` remains one row per scheduled installment.

If an installment is paid through multiple partial transactions:

``` text
transactions.json
```

contains the individual payment events.

`repayments.csv` contains the aggregate resulting state for that
scheduled installment.

Example:

``` text
due = €420
payment event 1 = €150
payment event 2 = €270
```

The repayment row may show:

``` text
total_due = 420
total_paid = 420
payment_date = final settlement date
payment_status = LATE or appropriate final state
days_past_due = based on final/defined settlement logic
```

Document the exact convention.

**Final convention:** a split payment produces one `LOAN_REPAYMENT` event per payment (two events at most in the final data) and **one** repayment row carrying the aggregate. The aggregate row shows
`total_paid` = the sum of the events, `payment_date` = the final settlement date (settled) or the last partial payment date (open), and a status as defined in section 34.

------------------------------------------------------------------------

# 37. Days Past Due (DPD)

DPD is internally coherent.

* **Settled instalment:** `days_past_due = max(0, payment_date - due_date)`.
* **Open instalment (PARTIAL / MISSED):** `days_past_due = delivery cutoff date - due_date`, where the cutoff is the date stored in `updated_at`
  (the month-end snapshot at 23:xx, or 2025-12-31 in the final snapshot).
* An instalment **reaches 30+ DPD on `due_date + 30`** and stays 30+ DPD until fully settled. A settled instalment counts as a 30+ DPD event if
  `payment_date - due_date >= 30`. This observable date is used for prior-delinquency (section 38) and for the ML target (section 69).
* **Versions.** An open instalment is delivered at the first batch cutoff on or after its due date (2025-09-30 for anything already overdue then) and again in the final batch (DPD at 2025-12-31); when it
  settles, a final version with a later `updated_at` is delivered. Open rows are never written off, so very old unresolved instalments have very large DPD
  (final maximum 3,394 days). Use the ageing buckets in section 70B rather than a single threshold.
* The final 2025-12-31 DPD must **never** be used as a historical feature for an earlier ML snapshot; features are reconstructed as of the snapshot date from `due_date` and `payment_date`.

**Final realised (settled instalments):** median DPD 0, 95th percentile 2, 99th percentile 13, maximum 99; 3,081 instalments are 30+ DPD in their final state.

------------------------------------------------------------------------

# 38. Delinquency concept

The project's early-warning event is:

``` text
A currently active, performing loan reaches 30+ DPD within the following 90 days.
```

This is a project early-warning target, not a regulatory default definition. Three **distinct** quantities must never be confused:

| Quantity | Definition | Final realised |
|---|---|---:|
| Loan-level eventual 30+ DPD prevalence | share of **mature** approved loans (first instalment due at least 12 months before 2025-12-31) that ever reach 30+ DPD | 11.53% (1,191 / 10,333) |
| Snapshot-level 90-day forward rate | share of performing loan x snapshot rows that reach 30+ DPD in (t, t+90 days] | 1.19% (1,330 positives, quarterly diagnostic snapshots) |
| Provisional currently-delinquent share | loans with an open instalment at 30+ DPD at 2025-12-31 / loans not paid off | 12.03% (dominated by very old unresolved debt) |

The original brief's "8-12% of eligible loans" is the **loan-level** quantity. The snapshot-level rate is much lower because most loans spend most quarters healthy; the two are
different questions and are not forced to match (see `DATA_DESIGN_DECISIONS.md`).

------------------------------------------------------------------------

# 39. Repayment behavior must be longitudinal

Payment behavior must not be independent installment-by-installment
random noise.

Examples of plausible paths:

``` text
ON_TIME
ON_TIME
5 days late
12 days late
PARTIAL
30+ DPD
```

and:

``` text
ON_TIME
8 days late
PARTIAL
ON_TIME
ON_TIME
```

Both deterioration and recovery must exist.

A customer may also remain healthy for an entire loan.

**Final realised:** 7,448 loans show a late/partial/missed instalment followed by three consecutive on-time instalments, and 576 of those recoveries follow a 30+ DPD instalment. Behaviour is driven by a persistent monthly stress level, not by independent per-instalment noise (section 45).

------------------------------------------------------------------------

# 40. transactions.json

JSON Lines: one nested event per line.

``` json
{
  "event_id": "EV000123456",
  "event_type": "LOAN_REPAYMENT",
  "event_time": "2024-03-05T09:14:22Z",
  "customer_id": "CU001234",
  "account": {
    "loan_account": "LN004567",
    "application_id": "LA004567",
    "repayment_id": "RP0123456"
  },
  "payment": {
    "amount": 285.54,
    "currency": "EUR",
    "channel": "DIRECT_DEBIT",
    "direction": "DEBIT"
  },
  "source": { "system": "core-banking", "version": "2.4" }
}
```

Amounts are positive decimal EUR (not minor units); `direction` gives the sign. `event_time` is an ISO timestamp: about 85% in UTC (`Z`) and 15% with the
Athens offset (+02:00 winter / +03:00 summer, DST-aware) so that Silver must normalise time zones.

Required and optional fields by event type:

| Event type | account block | payment.channel | payment.direction | source.system |
|---|---|---|---|---|
| LOAN_REPAYMENT | `loan_account`, `application_id`, `repayment_id` (all required) | DIRECT_DEBIT, STANDING_ORDER, ONLINE, MOBILE, BRANCH | DEBIT | core-banking |
| SALARY_CREDIT | `current_account` | PAYROLL | CREDIT | payroll-gw |
| ACCOUNT_CREDIT | `current_account` | PENSION, TRANSFER, BENEFIT | CREDIT | core-banking |
| CARD_PAYMENT | `current_account` | POS | DEBIT | card-switch |
| DIRECT_DEBIT | `current_account` | DIRECT_DEBIT | DEBIT | payments-hub |
| CASH_WITHDRAWAL | `current_account` | ATM | DEBIT | atm-network |
| BANK_TRANSFER_IN | `current_account` | ONLINE, TRANSFER | CREDIT | payments-hub |
| BANK_TRANSFER_OUT | `current_account` | ONLINE | DEBIT | payments-hub |

`payment.amount` and `payment.currency` are required for every event; `source.version` is 2.1 (before 2021), 2.3 (2021-2023) or 2.4 (2024 onwards).
Optional fields are omitted rather than written as null.

`transactions.json` carries **no separate version or update timestamp**. When the same `event_id` is delivered more than once, the **later delivery
batch wins** when reconstructing source state; batch order is the only correction-ordering mechanism (a corrected event may carry the same `source.version`).

------------------------------------------------------------------------

# 41. Transaction event types

Eight event types exist: `LOAN_REPAYMENT`, `SALARY_CREDIT`, `ACCOUNT_CREDIT`, `CARD_PAYMENT`, `DIRECT_DEBIT`, `CASH_WITHDRAWAL`, `BANK_TRANSFER_IN`, `BANK_TRANSFER_OUT`.
Not every customer has every type.

**`CARD_PAYMENT` is an aggregated card-spend/payment activity event** (a handful per active month, typical value several hundred EUR), **not an individual point-of-sale transaction**.
This keeps the event volume proportionate while preserving the cash-flow signal; per-purchase POS data is out of scope (section 86).

**Final realised:** LOAN_REPAYMENT 384,750, SALARY_CREDIT 107,890, CARD_PAYMENT 49,130, ACCOUNT_CREDIT 43,715, DIRECT_DEBIT 42,417, CASH_WITHDRAWAL 14,343, BANK_TRANSFER_IN 12,400, BANK_TRANSFER_OUT 12,173.

------------------------------------------------------------------------

# 42. Cash-flow coverage

Design target: meaningful non-loan cash-flow history for approximately **60-80% of approved-loan borrowers**; the rest may be sparse-history, new to the bank, or
customers whose primary activity occurs elsewhere. Missing internal cash-flow history is never treated as risky by the generator.

**Final implementation.** For a customer designated as having rich cash-flow history (roughly 54-72% of customers before the borrower filter, depending on tenure and employment), non-loan
events are generated for the months from **3 months before to 21 months after each loan disbursement** (the union over the customer's loans) and never before the customer exists.
Other borrowers receive only a few scattered events. Customers with no approved loan have no non-loan events.

**Final realised:** 61.4% of borrowers have at least 12 non-loan events (the coverage measure used in the acceptance check);
95.1% have at least one; salary credits are present for 63.9% of employed borrowers.
The windowed design (rather than monthly activity across the whole decade) keeps the transaction volume inside the target range.

------------------------------------------------------------------------

# 43. Transaction behavior

Transaction frequency and amount should depend probabilistically on:

-   income;
-   employment;
-   customer activity;
-   time;
-   financial stress;
-   product/loan activity where appropriate.

Salary credits for employed customers should generally be periodic, but
may:

-   vary modestly;
-   occur on slightly different dates;
-   weaken/disappear during some genuine stress events.

Card/direct-debit/outflow activity should be plausible relative to
income and customer behavior.

Do not generate every customer with an identical monthly transaction
template.

Salary credits are monthly for employed customers (customer-specific day, small variation) and **weaken or disappear during genuine income shocks**; pensions, self-employed receipts, benefits and transfers follow
the employment status; spending events scale with income and a customer-specific spend ratio and activity heterogeneity. Cash-flow dips precede stress effects by about one month, so they carry genuine leading signal.
**Final realised amounts (median):** SALARY_CREDIT EUR 1,775, CARD_PAYMENT EUR 511, DIRECT_DEBIT EUR 167, CASH_WITHDRAWAL EUR 97, LOAN_REPAYMENT EUR 286.

------------------------------------------------------------------------

# 44. Currency

The valid business portfolio should primarily use:

``` text
EUR
```

Do not create unnecessary multi-currency complexity.

Invalid currency codes may appear only as controlled DQ defects.

------------------------------------------------------------------------

# 45. Hidden financial-state simulation

The generator uses latent variables to create coherent behavior. They exist **only inside the simulator**:

``` text
financial_resilience   (customer trait; related to income, employment stability and noise)
shock_susceptibility
monthly stress level (and its persistent AR(1) noise)
income shocks (onset, duration, amplitude, ordinary vs major)
macro-pressure score (internal, standardised)
payment pressure
```

**Absolute rule (verified by tests on the delivered files):** latent variables are never exported into raw business sources, Gold or ML features, and no
column named `future_delinquency`, `will_default`, `future_default`, `latent_default_probability`, `hidden_stress`, `future_income_drop`, `future_payment_status` (or similar)
exists. The ML target must be derived from subsequent *observable* repayment history.

## Final mechanism (exact coefficients are in `histories.py` / `config.py`)

1.  **Monthly stress** for a customer who has loans or is about to apply:
    `stress = intercept(-0.35) - 0.8 x resilience + 0.9 x payment-burden term + 0.30 x macro pressure + 0.22 x (extra concurrently running loans) + 0.4 x (recent observable 30+ DPD events) + AR(1) noise + shock term`.
    The payment-burden term is monthly debt service divided by monthly income (clipped); debt service uses **the same convention as underwriting** (section 23): running
    loans contribute their scheduled instalment, ended-but-unresolved loans contribute `min(instalment, outstanding principal as of the month start)`.
2.  **Shocks** occur with a base monthly probability of 1.0%, scaled by susceptibility, macro pressure and employment status. The income hit is **immediately visible in cash flow**
    (salary reduced or absent); the effect on payment behavior is **lagged by one month**, so cash-flow deterioration is a genuine leading signal. 30% of shocks are *major* (abrupt, strongly
    raising stress) so that delinquency can occur without earlier lateness.
3.  **Installment outcome** from `u = stress + noise(sd 0.9)`: below 2.5 the instalment is paid on or slightly before its due date (about 3% have a trivial 1-4 day delay and 4% are paid in two payments);
    2.5-3.8: a delay of up to 28 days; above that: a mix of long delays (up to 75 days), partial payments and missed instalments, each with a probability of later cure.
    Macro conditions only shift the stress moderately; resilient customers stay healthy in bad periods and vulnerable, highly leveraged ones deteriorate more often.
4.  **Termination.** After 3 consecutive unresolved instalments (never settled, or settled 45 or more days late) the contractual schedule stops (DEFAULTED / early-terminated). The remaining principal stays outstanding;
    nothing is written off (section 70A).
5.  The risk score reflects resilience only partly (weight below 1) and also depends on DTI, tenure and observable history, so it is informative but never decisive.

Branch, product, name and age never carry a hidden risk rule.

------------------------------------------------------------------------

# 46. Counterexamples and anti-triviality

The dataset contains meaningful overlap: predictive signal is neither a deterministic rule nor pure noise.

**Final realised counterexample counts (mature loans, loan level):**

| Counterexample | Count |
|---|---:|
| good risk score(>=720) and 30plus | 428 |
| weak risk score(<600) and never 30plus | 271 |
| high dti(>45%) and never 30plus | 41 |
| low dti(<20%) and 30plus | 826 |
| recovery cases after 30plus then 3 ontime | 576 |
| new customer(<1y) and never 30plus | 2,104 |
| long term customer(>6y) and 30plus | 501 |
| customers with multiple loans all healthy | 2,814 |

Eventual 30+ DPD rate by risk band: 300-579: 30.5%, 580-669: 16.8%, 670-739: 12.2%, 740-799: 8.3%, 800-850: 5.4%.
Risk score is useful but not dominant; no single origination variable nearly solves future delinquency (section 67).

------------------------------------------------------------------------

# 47. ML readiness

Do **not** implement the final ML model in this phase.

However, the raw sources must later allow construction of:

``` text
one active performing loan × one monthly snapshot
```

with backward-looking features.

The data must support derivation of:

## Application/credit features

``` text
risk score
DTI
loan-to-income
payment burden
approved/requested amount
term
interest rate
product
```

## Customer-history features

``` text
customer tenure
new/existing customer
previous applications
previous loans
paid-off loans
previous delinquency
active-loan count
total exposure
```

## Repayment features

``` text
late-payment count
missed-payment count
partial-payment count
average/max DPD
payment ratio
recent deterioration
recovery
```

## Cash-flow features

``` text
salary/inflow level
recent inflow change
net cash flow
outflow pressure
cash-flow volatility
transaction-activity change
```

## Context features

``` text
product
branch
segment
macro environment
```

**Final status.** The raw sources allow all feature families listed above to be reconstructed as of a snapshot date from `application` snapshots, `due_date`/`payment_date` history, payment events and transaction events (verified by the quarterly diagnostics in section 67).
The *production* ML phase will build **monthly** loan-level snapshots; the quarterly snapshots in the generation report are a generator diagnostic only. The ML phase must use **temporal** train/validation/test splits (never random row splits) and must lag monthly macro features.

------------------------------------------------------------------------

# 48. Leakage guardrails

All historical features must use only information available as of the
relevant date.

Examples:

A 2019 application uses:

``` text
annual_income_at_application from 2019
employment_status_at_application from 2019
declared_monthly_expenses from 2019
```

not the customer's 2025 values.

A December 2023 ML snapshot cannot use:

``` text
2024 repayment outcomes
2024 transactions
2025 customer updates
future DPD
```

The generator may know the future internally, but the exported records
must preserve event time correctly.

**Final verification.** The generator's underwriting uses only information dated on or before the application date (observable prior 30+ DPD events, paid-off loans, outstanding principal, income/employment snapshots); the as-of `monthly_debt` and outstanding-principal logic are recomputed independently from exported data in the test suite. Corrections delivered later never alter earlier decisions or snapshots.

------------------------------------------------------------------------

# 49. Dirty-data strategy

## Design targets

``` text
4-5% of source records overall contain at least one deliberately injected quality issue
customers ~4-6%   applications ~4-6%   repayments ~3-5%   transactions ~2-4%
branches 0-1%     products 0-1%        macro 0-1%
```

Rates are not forced to be equal across sources. Most defective records contain one defect.

## Final realised values

| Source | Delivered rows | Distinct defective records | Share |
|---|---:|---:|---:|
| customers.csv | 17,740 | 1,017 | 5.73% |
| loan_applications.csv | 30,337 | 1,747 | 5.76% |
| repayments.csv | 376,072 | 17,894 | 4.76% |
| transactions.json | 672,794 | 26,020 | 3.87% |
| macroeconomic_monthly.csv | 121 | 2 | 1.65% |
| branches.csv | 12 | 0 | 0.00% |
| products.csv | 5 | 0 | 0.00% |
| **Overall** | **1,097,081** | | **4.25%** |

Each defect type draws distinct rows (an injected defect never overlaps another injected defect on the same record); late-arriving flags can coincide with a defect. The macro rate (two rows of
121) is slightly above the 0-1% design range because the source is tiny.

------------------------------------------------------------------------

# 50. Valid business behavior is not dirty data

These are valid observations:

``` text
low income
high DTI
loan rejection
late payment
partial payment
missed payment
30+ DPD
multiple loans
declining cash flow
```

Do not quarantine them simply because they are undesirable outcomes.

Dirty data means the record itself violates source/domain expectations.

------------------------------------------------------------------------

# 51. Customer DQ defects

Final catalogue with realised counts (primary key `customer_id` is never corrupted):

| Rule | Delivered defects | What is changed in the delivered copy |
|---|---:|---|
| `date_format_variation` | 103 | date of birth written DD/MM/YYYY (recoverable) |
| `duplicate_contact_email` | 72 | email copied from another customer |
| `impossible_dob` | 20 | future or pre-1900 date of birth |
| `invalid_phone` | 82 | invalid prefix, too few digits or stray characters |
| `malformed_email` | 103 | no `@`, comma in domain, trailing `@`, double `@`, truncated domain or a space |
| `missing_email` | 165 | email set to null |
| `missing_income` | 62 | annual_income set to null |
| `missing_phone` | 51 | phone set to null |
| `missing_segment` | 72 | segment set to null |
| `phone_format_issue` | 165 | valid number re-formatted with spaces, hyphens or parentheses (recoverable) |
| `whitespace_case` | 134 | padding or case change in name/email/segment/employment |

------------------------------------------------------------------------

# 52. Application DQ defects

The official Team 2 priority defects are all represented. Final catalogue with realised counts (`application_id` of existing applications is never corrupted; re-keyed duplicates are new ids):

| Rule | Delivered defects | What is changed in the delivered copy |
|---|---:|---|
| `approved_gt_requested` | 163 | approved amount 10-50% above the requested amount |
| `date_format_variation` | 130 | date written DD/MM/YYYY (recoverable) |
| `decision_before_application` | 196 | decision_date 1-20 days before application_date |
| `duplicate_application_rekeyed` | 114 | same business application re-delivered under a new, higher application_id |
| `exact_duplicate_row` | 98 | row replayed with the same application_id (about 30% replayed in the next batch) |
| `invalid_currency` | 82 | EURO, euro sign, eur, XXX or EU |
| `missing_consent` | 277 | consent_flag set to null |
| `missing_status` | 163 | status null or empty |
| `nonpositive_requested_amount` | 49 | negative or zero requested amount |
| `requested_outside_product_range` | 131 | requested amount far above the product maximum or below the minimum (non-approved rows) |
| `risk_score_out_of_range` | 196 | 0, 1000, 1200, -50, 9999, 250 or 900 |
| `unknown_branch` | 33 | BR099, BR000 or BR13 |
| `unknown_customer` | 82 | customer_id CU9xxxxx not in customers |
| `unknown_product` | 33 | XX-UNK, PL-XXX or MTG-VAR |

Frequencies differ by rule on purpose (section 49).

------------------------------------------------------------------------

# 53. Repayment DQ defects

Final catalogue with realised counts. Delinquency itself (late, partial, missed, 30+ DPD) is valid business behavior and is *not* a defect:

| Rule | Delivered defects | What is changed in the delivered copy |
|---|---:|---|
| `amount_sum_inconsistent` | 3,937 | total_due differs from principal_due + interest_due |
| `dpd_status_inconsistent` | 2,684 | days_past_due or status contradicts the other |
| `duplicate_installment_number` | 1,432 | same application and instalment number under a new repayment_id |
| `duplicate_repayment_row` | 1,790 | row replayed with the same repayment_id (about 30% in the next batch) |
| `impossible_payment_date` | 2,506 | payment_date 400-900 days before the due date or in 2031 |
| `invalid_currency` | 1,074 | EURO, euro sign, eur or XXX |
| `negative_amount` | 1,432 | negative paid/due amount |
| `orphan_application` | 3,042 | application_id LA9xxxxx that does not exist |

------------------------------------------------------------------------

# 54. Transaction DQ defects

Final catalogue with realised counts. Defects are record-level semantic problems that keep the file ingestible; a very small, controlled number of truncated (invalid JSON) lines exists so that Bronze can demonstrate safe rejection:

| Rule | Delivered defects | What is changed in the delivered copy |
|---|---:|---|
| `duplicate_event` | 5,724 | event replayed with the same event_id (about 30% in the next batch) |
| `impossible_timestamp` | 2,341 | 2031, 2099 or 1970 timestamp |
| `invalid_amount` | 3,382 | negative, zero or comma-decimal string amount |
| `malformed_currency` | 2,081 | eur, EURO, euro sign or trailing space |
| `malformed_event_type` | 3,122 | lower-case, spaced, hyphenated or misspelled event type |
| `malformed_json_line` | 4 | line truncated so it is not valid JSON (4 lines in total) |
| `missing_required_nested` | 4,683 | a required nested field (e.g. amount, currency, repayment_id) removed |
| `unknown_reference` | 3,122 | repayment_id RP9xxxxxx or customer_id CU9xxxxx that does not exist |
| `wrong_reference_relationship` | 1,561 | application_id replaced by another valid application |

------------------------------------------------------------------------

# 55. Macro DQ defects

The macro source is kept nearly clean:

| Rule | Delivered defects | What is changed in the delivered copy |
|---|---:|---|
| `duplicate_month` | 1 | one month delivered twice |
| `missing_optional_indicator` | 1 | consumer_confidence_index null for one month |

------------------------------------------------------------------------

# 56. Quality injection manifest

`data/generated_metadata/quality_injection_manifest.csv` is a **development-only** artefact: it is never a business source, must not be ingested as banking data, and must not be used for ML. It is excluded from Git
(regenerable).

Fields: `source_file, record_id, field, defect_type, original_value, injected_value, batch_id`.

Semantics of `original_value` / `injected_value`:

* ordinary defect types: `original_value` = the clean value, `injected_value` = the defective value delivered (`batch_id` = the batch containing it);
* `wrong_value_corrected_later`: `original_value` = the true value, `injected_value` = the **wrong** value delivered in that (earlier) batch;
* `correction_record`: `original_value` = the **wrong value being superseded**, `injected_value` = the **correct value** re-delivered in the later `batch_id`;
* `late_arriving_record`: `field` = `delivery`, `original_value` = the batch in which the record would naturally have appeared, `injected_value` = the batch in which it was actually delivered;
* duplicates: `injected_value` states `exact_duplicate_row` / `duplicate_of:<id>` / `same_installment_as:<id>`.

Late-arriving and correction records are logged here as well as quality defects, so the manifest verifies the whole delivery design. Entries were verified against the delivered files by the test suite.

------------------------------------------------------------------------

# 57. Four ingestion batches

The four batches are **not** ML train/validation/test splits. They simulate how files arrive from source systems over time.

| Batch | Recording window | Content |
|---|---|---|
| batch_001 | through 2025-09-30 | the large historical baseline plus the reference files |
| batch_002 | 2025-10-01 .. 2025-10-31 | newly recorded October data plus late-arriving and corrected records |
| batch_003 | 2025-11-01 .. 2025-11-30 | November |
| batch_004 | 2025-12-01 .. 2025-12-31 | December |

A record belongs to the batch in which it was **recorded**, not to its business date: `updated_at` for customers, applications and repayments, local event date for transactions.

## What is delivered, and how rows are versioned (final)

* **Customers** are delivered when created and again whenever their source attributes genuinely change (yearly income/employment events; contact changes for about 2% of customers in Oct-Dec 2025). A customer
  row carries the state as of the end of the batch.
* **Applications** are written once, when decided (section 26); undecided ones at submission.
* **Repayments**: a settled instalment is delivered once, in the batch containing its settlement posting. An instalment that is *open* at a batch cutoff (due, not yet fully paid) is delivered as an **open snapshot**
  stamped 23:xx on the cutoff date with `payment_status` PARTIAL/MISSED and DPD at that cutoff; when it later settles, a final version with a later `updated_at` is delivered. Instalments that are never settled are delivered
  at their first cutoff and once more in batch_004 (DPD at 2025-12-31). 371,260 instalments therefore produce 372,850 clean versions (up to four per instalment).
* **Transactions** are delivered once, in the batch of their event date, unless late-arriving, corrected or replayed.

## Late-arriving records (final)

Records with an older business date delivered in a later batch: customers 16 (created in the last 45 days of a window and not yet used by any application), applications 21
(decided in the last 14 days of a window), transactions 23 (non-loan events from the last 14 days of a window). Their `updated_at` is moved into the delivery window.

## Corrections (final)

A correction is a record whose earlier delivery carried a wrong value and whose later delivery carries the right one: customers 93 (e.g. an inflated annual_income later corrected; swapped phone digits; a wrong employment status),
applications 113 (`declared_monthly_expenses` or `monthly_debt`), transactions 252 (`payment.amount`). Application-time snapshot values of
*historical* applications are never changed by a customer update.

------------------------------------------------------------------------

# 58. Why four batches exist

The purpose is to demonstrate realistic ingestion behavior:

``` text
initial historical load
    ↓
monthly incremental load
    ↓
late-arriving records
    ↓
corrected records
    ↓
idempotent rerun behavior
```

Example late-arriving record:

``` text
business event date = 2025-09-29
source delivery batch = October batch
```

Example correction:

``` text
earlier source record:
annual_income = 32000

later correction:
annual_income = 30200
```

Bronze must later retain lineage and ingestion metadata.

Silver must later apply the documented correction/latest-record logic.

**Idempotency demonstration:** exact replays of defect rows (about 30% delivered in the next batch) and re-delivered open instalment snapshots exercise deduplication and latest-record logic.

------------------------------------------------------------------------

# 59. Batch directory structure

``` text
data/
└── landing/
    ├── batch_001/   branches.csv  products.csv  customers.csv  loan_applications.csv
    │                repayments.csv  transactions.json  macroeconomic_monthly.csv
    ├── batch_002/   customers.csv  loan_applications.csv  repayments.csv  transactions.json  macroeconomic_monthly.csv
    ├── batch_003/   (same five files)
    └── batch_004/   (same five files)
```

Reference masters (`branches.csv`, `products.csv`) are delivered in batch_001 only because no reference change is demonstrated. Row counts per file and batch are in section 0A and in
`schema_dictionary.md`.

------------------------------------------------------------------------

# 60. Batch semantics

A batch is an **ingestion delivery**, not a business-date partition; a later batch may legitimately contain an older business event. Three concepts are kept separate:

``` text
business/event time          application_date, decision_date, due_date, payment_date, event_time
source updated time          updated_at (customers, applications, repayments)
ingestion/delivery batch     the batch folder
```

**Reconstruction rule (verified).** To rebuild source state from the four deliveries: for customers, applications and repayments keep, per primary key, the record with the greatest `updated_at` (ties: the later batch);
for transactions, which have no update timestamp, keep the record from the **later batch** for the same `event_id`. Applied to records untouched by defects this reproduces the clean truth exactly.

------------------------------------------------------------------------

# 61. Idempotency readiness

The raw batches must support later testing that reprocessing the same
batch does not create uncontrolled duplicates.

Use stable source record identifiers and reproducible files.

Running the generator twice with the same seed/configuration should
produce identical source data.

**Final verification:** same code, config and seed give byte-identical files, in the same process and across processes with different `PYTHONHASHSEED` values (section 75).

------------------------------------------------------------------------

# 62. Reference files and batches

`branches.csv` and `products.csv` are stable reference/master sources.

Default:

``` text
deliver them with batch_001
```

Do not repeat them in every batch if no reference changes occur.

If a reference correction/change is deliberately demonstrated, deliver
only the appropriate changed record/update in a later batch and document
it.

------------------------------------------------------------------------

# 63. Customer updates across batches

A customer may appear in later deliveries when source attributes
genuinely change/correct.

Examples:

``` text
email changed
phone changed
employment changed
current annual income updated
source correction
```

Application-time snapshot values must remain unchanged for historical
applications.

Example:

``` text
customers.csv current annual income changes in 2025

but

2019 loan_application.annual_income_at_application
remains the 2019 value
```

**Final realised:** later batches contain roughly 1,000 customer rows each; most are genuine yearly income/employment updates, a few are new customers, contact changes or corrections. Historical applications keep their snapshot values.

------------------------------------------------------------------------

# 64. Macro delivery and time

`macroeconomic_monthly.csv` covers 120 months (2016-01 .. 2025-12): batch_001 delivers 2016-01..2025-09 (117 months plus one deliberately duplicated month, 118 rows), batches 002-004 deliver October, November and December 2025 (one row each).
The whole table is not repeated in every batch. See section 9 for the publication-lag limitation.

------------------------------------------------------------------------

# 65. Business behavior vs branch/product effects

Products may legitimately have different:

-   amounts;
-   terms;
-   pricing;
-   customer mix;
-   repayment burden.

Branches may have different:

-   volumes;
-   channel mix;
-   product mix;
-   customer mix.

However:

``` text
branch X must not secretly mean delinquent
product Y must not automatically mean delinquent
```

Risk should emerge from interacting borrower/loan/behavior/context
factors.

**Final check:** the eventual 30+ DPD rate across branches stays within about 9.5-12.8% (section 7) and differs by product only through loan, borrower and exposure characteristics; no branch or product is a hidden risk label.

------------------------------------------------------------------------

# 66. Delinquency prevalence

Two prevalence quantities are reported separately and must not be forced to match (section 38).

**Loan-level eventual 30+ DPD prevalence (the design's 8-12% target).**

* Numerator: approved loans with at least one instalment that reached 30+ DPD (section 37).
* **Denominator (strict, outcome-independent): approved loans whose first instalment fell due on or before 2024-12-31** (at least 12 months observable). A loan is never admitted to the denominator because it became delinquent.
  Rejected, withdrawn and undecided applications and loans with no due instalment are excluded.
* **Final realised: 11.53% = 1,191 / 10,333**; across all approved loans 9.72%.

**Snapshot-level 90-day forward rate** (section 69): 1.19% in the generator's quarterly diagnostic.

------------------------------------------------------------------------

# 67. Anti-triviality diagnostics

Diagnostics use **exported observable data only** (as-of reconstruction from application snapshots and repayment history). Final realised values:

| Diagnostic | Result |
|---|---|
| Loan-level AUC, risk score only | 0.620 |
| Loan-level AUC, DTI only | 0.586 |
| Snapshot AUC (test), risk score only | 0.595 |
| Snapshot AUC (test), DTI / loan-to-income only | 0.582 / 0.582 |
| Snapshot AUC (test), origination variables (logistic) | 0.656 |
| Snapshot AUC (test), origination + behaviour (logistic) | 0.868 |
| Snapshot AUC (test), behaviour only (logistic) | 0.859 |
| Strongest single behavioural feature (max DPD over the last 6 instalments) | 0.845 |

Eventual 30+ DPD rate by DTI band: 20-35%: 15.9% (n=1,730), 35-50%: 23.1% (n=376), <20%: 10.1% (n=8,214), >50%: 23.1% (n=13);
by customer tenure: 1-3y: 12.0%, 3-6y: 11.8%, <1y: 10.6%, >6y: 11.7%. Only 70 mature loans follow an already-observable 30+ DPD event of the same customer, so prior-delinquency rates
are statistically uninformative at this scale.

**Interpretation.** The risk score is useful but not dominant; repayment history is much stronger, which is realistic, partly for a mechanical reason: a loan that already has an overdue instalment under 30 days is close to crossing the 30-day line, whereas abrupt shocks can cause delinquency without earlier lateness. A single variable never "nearly solves" the target, but the ML phase must not treat currently overdue loans as independent evidence.

------------------------------------------------------------------------

# 68. Diagnostic ML is allowed only for validation

The generator contains a **diagnostic** only: a small numpy logistic regression on quarterly as-of snapshots to confirm that the data contain non-trivial signal. It is **not** the final ML implementation.

* Uses only exported observable variables, reconstructed as of the snapshot date; no leakage.
* **Temporal holdout**: train on snapshots up to 2022-12-31 (57,686 snapshots, 742 positives); test on snapshots from 2023-03-31 (54,489 snapshots, 588 positives, class balance 1.08%).
* Never scores the rows used for fitting.

The final predictive pipeline is implemented in a later phase.

------------------------------------------------------------------------

# 69. ML future target feasibility

For snapshot date `t` the future ML phase uses:

``` text
eligible population: approved loans, active (not paid off as of t), currently performing (no instalment 30+ DPD and unsettled as of t)
target = 1 if an instalment reaches 30+ DPD in (t, t + 90 days], else 0
```

**Right-censoring.** Snapshots with `t + 90 days > 2025-12-31` have an incomplete future window and are excluded from supervised target creation (labels are never fabricated). In the quarterly
diagnostic 5,968 snapshots were excluded this way. Loans whose schedule was terminated early (no further instalments) are not candidates.

**Quarterly versus monthly.** The generation report builds **quarterly** snapshots (112,175 labelled, 1,330 positives, 1.19%) purely as a cheap diagnostic. The capstone ML phase
will build **monthly** loan-level as-of snapshots, with twelve snapshots per year instead of four and temporal train/validation/test splits. No monthly-snapshot statistic is a frozen dataset KPI; the quarterly figures above are the canonical diagnostic.

**Why the two prevalences differ.** Loan-level eventual prevalence (11.53%) asks "does a loan ever reach 30+ DPD over its life?"; the forward rate (1.19%) asks "does it happen in the next 90 days given the loan is currently performing?". Most loan-quarters are healthy,
so the second is much smaller. They must not be forced to match.

------------------------------------------------------------------------

# 70. Outstanding balance

Outstanding principal of a loan at a date = **approved principal minus principal actually received on or before that date** (interest-first allocation, section 34). It is derivable from `approved_amount`, `principal_paid` and the payment dates.

* A loan that is paid off has zero outstanding principal. A loan whose contractual schedule has ended but that still has unpaid instalments **keeps positive outstanding principal** and remains open.
* An early-terminated loan (schedule stopped, section 45) keeps the *entire unscheduled remainder* as outstanding principal.
* Approved loans with no instalment due yet are counted at the full approved amount (disbursement date is not a source field).

**Final realised:** outstanding balance at 2025-12-31 is EUR 131,934,041; EUR 229,379 of it sits on 416 loans whose schedule ended unresolved.

------------------------------------------------------------------------

# 70A. Loan lifecycle states and unresolved debt

Final state definitions (at any date, computed only from information dated up to that date):

| State | Definition |
|---|---|
| ACTIVE / running | the contractual schedule is still running (the final scheduled instalment is in the future) |
| MATURED | the final contractual instalment (`installment_number = term_months`) exists; **maturity does not mean paid off** |
| DEFAULTED (early-terminated) | the schedule stopped after repeated unresolved instalments (section 45); the unscheduled remainder is outstanding |
| PAID_OFF | schedule complete **and** every instalment fully settled (no PARTIAL/MISSED row); the paid-off date is the last settlement date |
| open | any approved loan that is not PAID_OFF |

Rules:

* **Unresolved debt remains debt until it is observably settled.** There is no expiry: the obsolete idea that unresolved debt stops counting after a fixed period (for example 365 days) does not exist.
* After the schedule has ended, an unresolved loan contributes `min(last scheduled instalment, outstanding principal as of the date)` to `monthly_debt` (section 23) and to the hidden stress debt service. Before the schedule ends it contributes its scheduled instalment.
* Previously *paid-off* loans (as of the application date) count as completed history in underwriting; matured-but-unresolved loans do not.
* **There is no write-off, closure, collections or recovery subsystem.** Open instalments age indefinitely.

**Final realised state mix at 2025-12-31:** 12,572 approved loans: 5,525 paid off, 416 matured and unresolved, the rest running or early-terminated (7,047 open in total).
Invariants enforced by the clean-truth validation: a paid-off loan has zero outstanding principal and no open instalment; a matured-but-unresolved loan keeps positive outstanding principal. Enforced by the test suite: the as-of `monthly_debt` and outstanding-principal logic are recomputed independently from exported data, so no future payment enters an earlier balance and no unapproved loan contributes debt.

------------------------------------------------------------------------

# 70B. DPD ageing buckets (reporting readiness)

Because open instalments are never written off, a single "30+ DPD" share is dominated by very old unresolved debt. Open exposure must therefore be analysed in **DPD ageing buckets** (DPD at 2025-12-31 of PARTIAL/MISSED instalments):

| Bucket | Open instalments | Loans (by maximum open DPD) |
|---|---:|---:|
| 30-59 | 27 | 12 |
| 60-89 | 13 | 10 |
| 90-179 | 32 | 20 |
| 180-365 | 80 | 40 |
| 365+ | 1,307 | 766 |

(`365+` means more than 365 days.) The provisional share of loans with an open 30+ DPD instalment among loans not paid off is 12.03%, and most of it is in the `365+` bucket. **No universal "30-365 days" delinquency KPI is defined here;
the final delinquency KPI convention (for example active delinquency versus aged non-performing exposure) is set in the Gold / Power BI phase.**

------------------------------------------------------------------------

# 71. Mandatory KPI acceptance tests

Before accepting generation, prove that all mandatory Team 2 KPIs are
calculable:

``` text
Applications
Requested Amount
Approval Rate
Average Decision Time
Debt-to-Income Band
Delinquency Rate
Outstanding Balance
Manual-Review Rate
```

Also verify useful slicing by:

``` text
date
branch
region
product
product family
customer segment
risk band
application status
channel
new/existing customer
```

**Final realised mandatory KPI values** (generator report; definitions in `generation_report.json` -> `kpis.definitions`):

| KPI | Value |
|---|---|
| Applications | 30,012 |
| Requested Amount | EUR 854,401,260 |
| Approval Rate | 44.33% |
| Average Decision Time | 4.45 days |
| Debt-to-Income Band | <20% 63.5%, 20-35% 20.7%, 35-50% 12.0%, >50% 3.8% |
| Delinquency Rate (provisional, section 70B) | 12.03% |
| Outstanding Balance (2025-12-31) | EUR 131,934,041 |
| Manual-Review Rate | 17.84% |

All requested slicing dimensions (date, branch, region, product, product family, segment, risk band, status, channel, new/existing customer) are calculable.

------------------------------------------------------------------------

# 72. Data-quality acceptance tests

Verify at least:

``` text
missing consent/status exists in controlled quantity
inconsistent amount cases exist
impossible date cases exist
duplicate application cases exist
orphan repayment cases exist
out-of-range risk-score cases exist
```

Also report:

``` text
defect counts by source
defect counts by rule
percentage of source rows affected
```

**Final realised official defect families (delivered counts):** missing consent 277, missing status 163, inconsistent amounts 4,280,
impossible dates 5,063, duplicate applications 212, orphan repayments 3,042, out-of-range risk scores 196.
Defect counts by source and rule are in sections 51-55.

------------------------------------------------------------------------

# 73. Statistical validation report

Automatically produce a detailed generation report.

Include:

## Counts

``` text
rows/events per source
rows/events per batch
unique primary IDs
date ranges
```

## Customers

``` text
age quantiles
income quantiles
employment distribution
segment distribution
customer creation cohorts
email missing/invalid rate
phone issue rate
```

## Applications

``` text
applications per customer
application status distribution
approval rate
manual-review rate
decision-time quantiles
product mix
branch mix
channel mix
risk-score quantiles
DTI quantiles
requested/approved amount quantiles
term distribution
interest-rate distribution by product/year
```

## Loans/repayments

``` text
approved/originated loan count
installments per loan
repayment-status distribution
DPD quantiles
30+ DPD prevalence
partial-payment count
missed-payment count
recovery cases
paid-off-loan count
active-loan count
multiple-active-loan customers
previous-delinquency customers
```

## Transactions

``` text
event-type distribution
events per customer
cash-flow coverage
salary-credit coverage
transaction amount quantiles
```

## Data quality

``` text
defects by source
defects by rule
late-arriving count
corrected-record count
orphan count
duplicate count
```

## ML-readiness diagnostics

``` text
eligible mature loan count
positive 30+ DPD count
positive rate
risk-score-only diagnostic
DTI relationship
behavioral-signal checks
counterexample counts
```

**Final status.** The automatic report is `data/generated_metadata/generation_report.json`: counts, customer, application, loan/repayment, transaction, data-quality, history-coverage, KPI, ML-readiness (loan-level and snapshot) and clean-truth validation sections, the post-schedule-debt audit, the acceptance checklist, the known limitations and the reproducibility result.

------------------------------------------------------------------------

# 74. Counterexample validation

Explicitly count examples such as:

``` text
good risk score + later 30+ DPD
weak risk score + remains healthy
high DTI + remains healthy
lower/moderate DTI + later 30+ DPD
multiple active loans + healthy
temporary late/partial behavior + recovery
```

If these categories are absent, the data are too deterministic.

If they dominate the population, the data may be too noisy.

**Final realised counterexample counts** are listed in section 46; the data contain neither too few (deterministic) nor too many (noisy) such cases.

------------------------------------------------------------------------

# 75. Reproducibility

Default seed **42**; generation is configuration-driven (`generation_config.json`). The same code, config and seed produce **byte-identical** source files (26 of 26 files compared), verified in-process and **across processes with different `PYTHONHASHSEED`
values**. Per-customer random streams are derived from the seed and the customer index, so results do not depend on iteration order. The only run-dependent entries are the `reproducibility` and `_elapsed_seconds` keys appended to the final report.
A different seed gives a statistically similar but distinct universe. No system-time randomness is used.

------------------------------------------------------------------------

# 76. Generator architecture (final)

``` text
src/team2_project/generation/
├── config.py       GenConfig (all calibration and rates) and batch cutoffs
├── reference.py    loads/validates the fixed 12 branches and 5 products (reference_data/)
├── macro.py        monthly macro context and internal macro-pressure score
├── names.py        name, email-provider and handle pools
├── customers.py    entry cohorts, demographics, income/employment state timelines, latent traits
├── histories.py    month-by-month per-customer simulation: stress, applications, underwriting, loans,
│                   instalment outcomes, payment ledger, cash-flow events
├── behaviour.py    installment outcome model (on-time / late / partial / missed / cure)
├── tables.py       clean-truth tables: applications, repayment versions, transactions
├── batches.py      delivery frames, late-arriving records, corrections, customer re-deliveries
├── defects.py      controlled defect injection and quality manifest
├── export.py       CSV / JSON Lines writers
├── dictionary.py   field-level data dictionary (schema_dictionary.md)
├── validate.py     41 clean-truth checks and the full generation report
├── pipeline.py     orchestration, acceptance checklist, reproducibility check, CLI
└── util.py         deterministic date / amortisation helpers
tests/              test_generation.py, test_post_export.py, test_stress_consistency.py (23 tests)
```

------------------------------------------------------------------------

# 77. Generation sequence

Implement in this order:

``` text
1. Inspect repository and existing reference files
2. Load/validate the existing 12 branches
3. Load/validate the existing 5 products
4. Generate 2016–2025 macro context
5. Generate clean customers and customer-entry cohorts
6. Generate evolving customer histories
7. Generate clean applications
8. Store application-time financial snapshots
9. Resolve decisions and manual review
10. Create approved loan accounts internally
11. Generate amortization/repayment schedules
12. Simulate monthly financial state
13. Generate actual repayment outcomes
14. Generate transaction/cash-flow events
15. Validate clean truth
16. Inject controlled DQ defects
17. Generate late-arriving/corrected deliveries
18. Split/export four ingestion batches
19. Produce quality injection manifest
20. Produce full validation report
21. Re-run reproducibility check
22. Stop
```

**Final status:** all steps were executed in this order; the generator then stopped at step 22 (no Bronze/Silver/Gold/ML work is part of this phase).

------------------------------------------------------------------------

# 78. What not to do

Do not:

``` text
train the final ML model
build Gold tables
build Power BI
build FastAPI
build LangChain
```

during this task.

Those are later phases.

Also do not:

-   change 12 branches to 16;
-   change 5 products to 7;
-   shorten the history to 2023--2026;
-   remove actual payment fields;
-   generate rich cash flow for only \~200 borrowers;
-   make delinquency depend almost entirely on risk score;
-   expose hidden stress variables;
-   use future information in historical applications;
-   generate one giant undifferentiated dump instead of the agreed
    ingestion batches;
-   corrupt primary IDs;
-   make exactly 5% of every file dirty;
-   clean adverse financial behavior as if it were bad data.

These scope boundaries still hold: the generator only creates source data. Deliberate scope simplifications (no write-offs/collections, no full ledger, no per-purchase POS data, no business-day constraints, no regulatory Expected Loss model) are explained in `DATA_DESIGN_DECISIONS.md` and listed in section 86.

------------------------------------------------------------------------

# 79. Output directory

``` text
data/
├── landing/
│   ├── batch_001/ .. batch_004/      delivered sources (section 59)
└── generated_metadata/
    ├── generation_report.json        statistical validation, acceptance checklist, limitations
    ├── generation_config.json        the exact configuration (seed 42)
    ├── schema_dictionary.md          conventions, per-batch counts and the full data dictionary
    └── quality_injection_manifest.csv  development-only defect manifest
```

**Git policy.** `data/landing/` (about 276 MB) and the manifest are regenerable and are excluded from Git (`.gitignore`); the generator code, tests, configuration, this specification and
`generation_config.json`, `generation_report.json` and `schema_dictionary.md` are versioned. Regenerate with `PYTHONPATH=src python -m team2_project.generation --out data`.

------------------------------------------------------------------------

# 80. Data dictionary

`data/generated_metadata/schema_dictionary.md` is generated from `dictionary.py` and documents, for every field of every source (including the nested `transactions.json` fields): source, field name, data type, nullability, key role, business meaning, valid domain/range, sensitivity
classification, generation rule and Silver validation expectation. It also contains the authoritative conventions (monthly_debt, DTI, statuses, repayment and DPD semantics, loan states, delinquency ageing, prevalence definitions, prior delinquency,
card events, transaction correction semantics, manifest semantics, the application cap and the known limitations) and the delivered file counts per batch. Where this document and the dictionary overlap they agree.

------------------------------------------------------------------------

# 81. Sensitivity

All customer data are synthetic.

Do not use real PII.

Still classify fields realistically for governance.

For example:

``` text
first_name                synthetic personal identifier
last_name                 synthetic personal identifier
email                     synthetic contact data
phone                     synthetic contact data
date_of_birth             synthetic personal data
annual_income             synthetic financial data
```

This helps demonstrate production-minded governance.

------------------------------------------------------------------------

# 82. Source-to-target readiness

Do not build Silver/Gold yet, but generate source fields that cleanly
support later mappings.

Expected future Gold model includes at least:

``` text
fact_loan_application
fact_repayment

dim_date
dim_customer_segment
dim_product
dim_branch
dim_risk_band
dim_application_status
```

Do not bake Gold surrogate keys into raw source files.

Raw sources use business/source keys.

Raw sources carry only business/source keys (CU/LA/RP/EV/LN/AC/HH, branch and product codes); no Gold surrogate keys are present.

------------------------------------------------------------------------

# 83. Final acceptance checklist

Status at freeze (evidence from `generation_report.json`; 40 of 40 mandatory acceptance checks pass, one advisory):

## Reference data
-   [x] Exactly 12 existing branches preserved.
-   [x] Exactly 5 existing products preserved.
-   [x] Codes remain stable.

## History
-   [x] Detailed history covers 2016-01-01 through 2025-12-31 (activity in every year and into December 2025).
-   [x] Customers enter throughout the decade (4,602 pre-date 2016).
-   [x] Repeat borrowers (3,329), paid-off loans (5,525), previous delinquency and overlapping loans (2,459) exist.

## Scale
-   [x] ~15k customers (15,000); 30k-40k applications (30,012); 400k-700k transaction events (666,818); total volume 1,097,081.
-   [ ] 200k-350k repayment rows (soft): **371,260, about 6% above; advisory, intentionally not clipped (section 6).**
-   [x] Counts arise naturally rather than by duplication.

## Customers
-   [x] Greek-name share 87.6%; seven email providers with eleven local-part patterns; phone formats vary.
-   [x] Income is right-skewed and conditionally generated; employment histories evolve coherently.

## Applications
-   [x] Application-time income, employment status, declared expenses and existing monthly debt are present; DTI is derivable.
-   [x] Decisions are probabilistic; manual review is meaningful; decision time is meaningful; amount/term/rate are coherent with product, date and risk.

## Repayments
-   [x] Scheduled and actual payment fields exist; late, partial and missed instalments exist; recovery exists; 30+ DPD exists at useful imbalanced prevalence.
-   [x] Outstanding balance can be derived; loan states (ACTIVE / MATURED / DEFAULTED / PAID_OFF) are consistent.

## Transactions
-   [x] Loan repayment, salary/inflow, card, direct-debit, transfer and cash events exist; rich history for 61.4% of borrowers; patterns are heterogeneous.

## Macro
-   [x] 120 monthly observations 2016-2025; influence is moderate, not deterministic.

## Dirty data
-   [x] 4.25% of delivered rows affected; rates vary naturally by source; official Team 2 defect families present; primary IDs protected; manifest exists; valid adverse behavior remains valid data.

## Batches
-   [x] Four ingestion batches; batch_001 is the baseline through 2025-09-30; batches 002-004 are Oct/Nov/Dec 2025; late-arriving and corrected records exist; same-seed generation is reproducible.

## ML readiness
-   [x] Monthly loan snapshots can be constructed; complete 90-day windows are identifiable; right-censoring is possible; no hidden generator state or future target is exported; risk score alone does not determine delinquency; observable behavior adds signal; counterexamples exist.

## Mandatory capstone analytics
-   [x] Applications, Requested Amount, Approval Rate, Average Decision Time, Debt-to-Income Band, Delinquency Rate (provisional, section 70B), Outstanding Balance and Manual-Review Rate are calculable.

------------------------------------------------------------------------

# 84. Generation, verification and freeze procedure (as executed)

The generator was implemented and verified in this order; this section replaces the original execution protocol for the implementing assistant.

1.  Inspect the repository and reuse the existing 12 branches and 5 products (copied into `reference_data/`).
2.  Implement the generator per this specification; generate clean truth and validate it (41 checks) before any defect is injected.
3.  Inject controlled defects; build the four batches (late-arriving, corrected and re-delivered records); export CSV / JSON Lines.
4.  Produce the full report, data dictionary, config and development-only manifest.
5.  Verify: same-seed reproducibility, cross-process `PYTHONHASHSEED` determinism, latest-wins reconstruction against clean truth, scan of delivered files for forbidden fields, manifest-to-delivered checks, independent as-of recomputation of `monthly_debt` and outstanding principal, and the 23-test suite.
6.  Several forensic audits and a final logical-consistency check corrected or documented remaining issues (loan completion semantics, removal of the 365-day debt-expiry rule, capped post-schedule debt, as-of prior delinquency, strict mature-loan denominator, stress/underwriting debt consistency).
7.  Freeze: commit and tag `data-generator-v1`. **Do not proceed to Bronze/Silver/Gold/final ML as part of the generator task.** Any future change requires an explicit versioned decision.

------------------------------------------------------------------------

# 85. Definition of success

The output should feel like data from a small synthetic Greek banking
portfolio observed for ten years---not like seven unrelated Faker files.

The same source universe must naturally support:

``` text
raw source files
→ incremental Bronze ingestion
→ Silver quality/conformance
→ Gold dimensional model
→ mandatory banking KPIs
→ Power BI
→ API/LLM analytics
→ leakage-safe behavioral feature engineering
→ 90-day delinquency early-warning ML
→ predictive portfolio BI
```

The generator should prioritize **coherence, traceability, realistic
overlap, temporal correctness and analytical usefulness** over
artificially impressive ML scores or artificially round row counts.

At freeze the dataset behaves as a small synthetic Greek banking portfolio observed for ten years, with the transparent limitations of section 86.

------------------------------------------------------------------------

# 86. Known limitations (documented, accepted at freeze)

``` text
 1. No write-off, closure, collections or recovery model: unresolved instalments/loans age indefinitely; open DPD reaches several thousand days. Analyse by DPD ageing buckets (section 70B);
    the delinquency KPI convention is deferred to the analytics phase.
 2. Post-schedule unresolved debt contributes min(last instalment, outstanding principal as of the date) to monthly_debt and to hidden stress: a synthetic proxy for the burden of post-schedule debt.
 3. Applications per customer are capped at 8 (synthetic safeguard); about 12% of applicants sit exactly at the cap.
 4. Decision, due and payment dates are not business-day adjusted (about a quarter of decisions fall on weekends).
 5. Age/employment edge cases remain: students up to about 45, a few early "retired", some employed customers aged 75+, some non-mortgage loans ending after age 80.
 6. CARD_PAYMENT is an aggregated card-spend event, not an individual POS transaction; there is no per-purchase detail and no full ledger/accounting system.
 7. Monthly macro values have no publication lag and the reference rate applies for the whole month of a change: the ML phase must lag monthly macro features.
 8. Transactions have no version timestamp; for the same event_id the later batch wins.
 9. Outstanding balance counts approved loans with no instalment due yet at the full approved amount (disbursement date is not a source field).
10. A few early-terminated loans have every emitted instalment cured (settled 45+ days late) yet keep their remaining principal outstanding with no further schedule (an artifact of the termination rule).
11. Quarterly snapshots in the report are a generator diagnostic only; the final ML phase uses monthly snapshots and temporal splits. The snapshot-level positive rate (about 1.2%) is a different quantity from the loan-level prevalence (about 11.5%).
12. No regulatory Expected Loss (PD/LGD/EAD) framework: probability-weighted exposure in the ML phase must not be labelled Expected Loss.
13. The test suite does not detect a future-information regression inside the risk score / approval logic (the code was traced and verified correct).
14. The repayment-row count is about 6% above the soft design target (advisory).
```

------------------------------------------------------------------------

# 87. Document map

| Document | Purpose |
|---|---|
| `DATA.md` (this file) | What exactly is the final dataset (specification, definitions, realised values) |
| `DATA_DESIGN_DECISIONS.md` | Why the dataset was designed this way (rationale and scope simplifications) |
| `PROJECT_OVERVIEW.md` | End-to-end project map, phases and definitions of done |
| `data/generated_metadata/schema_dictionary.md` | Field-level data dictionary, conventions and per-batch counts |
| `data/generated_metadata/generation_report.json` | Statistical validation report, acceptance checklist, limitations |
| `data/generated_metadata/generation_config.json` | Exact generator configuration (seed 42) |
