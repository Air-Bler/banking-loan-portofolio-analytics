"""Machine/human readable data dictionary (schema_dictionary.md)."""
from __future__ import annotations

from . import names as _N
from .customers import EMAIL_PATTERNS as _EP

HEAD = ["source", "field", "type", "nullable", "key", "business meaning", "valid domain / range",
        "sensitivity", "generation rule", "Silver validation expectation"]

SYN_ID = "synthetic personal identifier"
SYN_CONTACT = "synthetic contact data"
SYN_FIN = "synthetic financial data"
INT = "internal"


def _r(*a):
    return a


FIELDS = [
    # ---- branches ------------------------------------------------------------------
    _r("branches.csv", "branch_code", "string", "no", "PK", "Stable branch code", "BR001..BR012", INT, "existing master, unchanged", "unique, not null"),
    _r("branches.csv", "branch_name", "string", "no", "", "Branch name", "free text", INT, "existing master", "not null"),
    _r("branches.csv", "city", "string", "no", "", "City of the branch", "free text", INT, "existing master", "not null"),
    _r("branches.csv", "region", "string", "no", "", "Greek administrative region", "Attica, Central Macedonia, Crete, Thessaly, Western Greece", INT, "existing master", "not null"),
    _r("branches.csv", "opened_date", "date", "no", "", "Branch opening date (reference only; detailed events start 2016)", "ISO date <= 2015-12-31", INT, "existing master", "valid date"),
    # ---- products ------------------------------------------------------------------
    _r("products.csv", "product_code", "string", "no", "PK", "Stable product code", "PL-STD, PL-GRN, AUT-NEW, MTG-FIX, SME-WCL", INT, "existing master, unchanged", "unique, not null"),
    _r("products.csv", "product_name", "string", "no", "", "Product name", "free text", INT, "existing master", "not null"),
    _r("products.csv", "product_family", "string", "no", "", "Product family", "Consumer, Auto, Mortgage, Business", INT, "existing master", "not null"),
    _r("products.csv", "min_amount", "number", "no", "", "Minimum loan amount (EUR)", ">0", INT, "existing master", "min <= max"),
    _r("products.csv", "max_amount", "number", "no", "", "Maximum loan amount (EUR)", ">= min_amount", INT, "existing master", "min <= max"),
    _r("products.csv", "min_term_months", "integer", "no", "", "Minimum term in months", ">0", INT, "existing master", "min <= max"),
    _r("products.csv", "max_term_months", "integer", "no", "", "Maximum term in months", ">= min_term_months", INT, "existing master", "min <= max"),
    _r("products.csv", "base_rate", "decimal(4)", "no", "", "Reference product rate before market/risk/term adjustment (0.089 = 8.9%)", "0..0.25", INT, "existing master", "range"),
    # ---- customers -----------------------------------------------------------------
    _r("customers.csv", "customer_id", "string", "no", "PK", "Customer key (CU + 6 digits), stable; re-delivered when attributes change", "CU000001..", INT, "sequential by creation time", "not null; latest updated_at wins"),
    _r("customers.csv", "first_name", "string", "no", "", "Given name (85-90% Greek pool, 10-15% international)", "letters", SYN_ID, "large name pools, no influence on risk", "trim, title-case"),
    _r("customers.csv", "last_name", "string", "no", "", "Family name (feminine form for Greek women)", "letters", SYN_ID, "household-shared surname", "trim, title-case"),
    _r("customers.csv", "email", "string", "yes", "", f"Contact email ({len(set(d for d, _ in _N.EMAIL_PROVIDERS))} providers, {len(_EP)} local-part patterns: " + "; ".join(n for n, _ in _EP) + ")", "RFC-like address", SYN_CONTACT, "weighted pattern mix incl. name-unrelated handles; unique unless defect", "lower-case, format check, flag duplicates"),
    _r("customers.csv", "phone", "string", "yes", "", "Greek phone in source-format variants (69x, +3069x, 003069x, 210x, +30210x)", "10 digit Greek number with optional prefix", SYN_CONTACT, "format mix", "standardise to E.164, reject invalid"),
    _r("customers.csv", "date_of_birth", "date", "no", "", "Date of birth (adults only)", "age 18..90 at 2025-12-31", "synthetic personal data", "non-uniform age mixture", "valid date, age range"),
    _r("customers.csv", "segment", "string", "yes", "", "Commercial segment", "MASS, AFFLUENT, PREMIER, SME", INT, "moderately income-related", "upper-case, domain check"),
    _r("customers.csv", "annual_income", "number", "yes", "", "CURRENT declared annual income (EUR); NOT the application-time value", "2,400..650,000", SYN_FIN, "right-skewed log-normal by employment, age, segment; yearly evolution", ">0, latest record wins"),
    _r("customers.csv", "household_id", "string", "yes", "", "Shared household key; null when unknown", "HH + 6 digits", INT, "~40% of customers share a household; ~5% have none", "format check"),
    _r("customers.csv", "employment_status", "string", "no", "", "CURRENT employment status", "EMPLOYED, SELF_EMPLOYED, RETIRED, UNEMPLOYED, STUDENT, OTHER", INT, "age-conditional, evolves yearly", "domain check"),
    _r("customers.csv", "employment_start_date", "date", "yes", "", "Start of the current employment status (null for STUDENT/OTHER)", "<= 2025-12-31", INT, "tenure by status", "date <= load date"),
    _r("customers.csv", "created_at", "timestamp", "no", "", "When the customer entered the bank", "ISO timestamp 2008..2025", INT, "70% enter 2016-2025, 30% pre-2016", "<= updated_at"),
    _r("customers.csv", "updated_at", "timestamp", "no", "", "Last change of the source record (drives latest-wins and late/corrected handling)", "ISO timestamp >= created_at", INT, "last state/contact change", "ordering key for SCD1"),
    # ---- applications ----------------------------------------------------------------
    _r("loan_applications.csv", "application_id", "string", "no", "PK", "Application key (LA + 6 digits), chronological", "LA000001..", INT, "sequential by application date", "unique after dedup"),
    _r("loan_applications.csv", "customer_id", "string", "no", "FK customers", "Applicant", "existing customer", INT, "customers apply after creation", "FK check -> quarantine"),
    _r("loan_applications.csv", "branch_code", "string", "no", "FK branches", "Handling branch", "BR001..BR012", INT, "home branch 90%", "FK check"),
    _r("loan_applications.csv", "product_code", "string", "no", "FK products", "Requested product", "5 product codes", INT, "segment/age/income dependent mix", "FK check"),
    _r("loan_applications.csv", "application_date", "date", "no", "", "Business date of submission", "2016-01-01..2025-12-31", INT, "growth + seasonality + weekday weights", ">= customer created_at"),
    _r("loan_applications.csv", "decision_date", "date", "yes", "", "Date of approval / rejection (or withdrawal for WITHDRAWN); null while pending", ">= application_date", INT, "product/manual-review/channel dependent delay", ">= application_date"),
    _r("loan_applications.csv", "status", "string", "no", "", "APPROVED/REJECTED/WITHDRAWN are final; SUBMITTED/UNDER_REVIEW = undecided at 2025-12-31 (null decision_date)", "APPROVED, REJECTED, WITHDRAWN, SUBMITTED, UNDER_REVIEW", INT, "probabilistic underwriting", "domain check; missing -> quarantine"),
    _r("loan_applications.csv", "requested_amount", "number", "no", "", "Requested amount (EUR)", "product min..max", SYN_FIN, "income/product-scaled log-normal", "product range, >0"),
    _r("loan_applications.csv", "approved_amount", "number", "yes", "", "Approved amount; only for APPROVED (25% partial approvals)", "0 < x <= requested_amount", SYN_FIN, "full or partial approval", "<= requested"),
    _r("loan_applications.csv", "currency", "string", "no", "", "Currency", "EUR", INT, "always EUR", "domain check"),
    _r("loan_applications.csv", "term_months", "integer", "no", "", "Requested/granted term in months", "product term range", INT, "product-specific, age-capped", "product range"),
    _r("loan_applications.csv", "interest_rate", "decimal(4)", "yes", "", "Originated annual rate; only for APPROVED", "0.02..0.22", INT, "base + pass-through of reference rate + risk + term adj + noise", "range"),
    _r("loan_applications.csv", "risk_score", "integer", "no", "", "Application-time credit risk score (higher = safer)", "300..850", SYN_FIN, "informative but non-deterministic", "range check"),
    _r("loan_applications.csv", "monthly_debt", "number", "no", "", "EXISTING monthly debt obligations BEFORE the requested loan (external + this bank's running loans + capped burden of ended-but-unresolved loans)", ">=0", SYN_FIN, "external-obligation ratio x monthly income + scheduled instalment of each loan running on the application date + for loans whose schedule ended but are not observably paid off: min(last instalment, outstanding principal as of the application date); no expiry; no payments after the application date are used", ">=0"),
    _r("loan_applications.csv", "annual_income_at_application", "number", "no", "", "Annual income as known at application time (snapshot)", ">0", SYN_FIN, "customer income timeline as of application_date", ">0"),
    _r("loan_applications.csv", "employment_status_at_application", "string", "no", "", "Employment status at application time (snapshot)", "customer employment domain", INT, "customer timeline as of application_date", "domain check"),
    _r("loan_applications.csv", "declared_monthly_expenses", "number", "no", "", "Declared recurring living/business expenses, excluding debt payments", ">0", SYN_FIN, "share of monthly income, income-dependent", ">0"),
    _r("loan_applications.csv", "consent_flag", "string", "yes", "", "Data-processing consent", "Y, N", INT, "Y except some customer-withdrawn applications", "missing -> quarantine"),
    _r("loan_applications.csv", "manual_review", "string", "no", "", "Manual underwriting review applied", "Y, N", INT, "borderline/large/complex cases", "domain check"),
    _r("loan_applications.csv", "updated_at", "timestamp", "no", "", "Time the record was last written in the source (decision time)", ">= application_date", INT, "decision date + time of day", "latest wins"),
    _r("loan_applications.csv", "channel", "string", "no", "", "Submission channel", "BRANCH, ONLINE, MOBILE, PHONE", INT, "digital share rises over time", "domain check"),
    # ---- repayments ------------------------------------------------------------------
    _r("repayments.csv", "repayment_id", "string", "no", "PK", "Instalment key (RP + 7 digits)", "RP0000001..", INT, "sequential by loan then instalment", "latest updated_at wins"),
    _r("repayments.csv", "application_id", "string", "no", "FK loan_applications", "Approved application the instalment belongs to", "approved application", INT, "from loan schedule", "FK check -> quarantine orphans"),
    _r("repayments.csv", "installment_number", "integer", "no", "", "1-based instalment sequence within the loan", "1..term_months", INT, "annuity schedule", "unique per application"),
    _r("repayments.csv", "due_date", "date", "no", "", "Scheduled due date", "<= 2025-12-31", INT, "monthly on a customer-fixed day", "valid date"),
    _r("repayments.csv", "principal_due", "number", "no", "", "Scheduled principal", ">=0", SYN_FIN, "annuity amortisation", ">=0"),
    _r("repayments.csv", "interest_due", "number", "no", "", "Scheduled interest", ">=0", SYN_FIN, "balance x rate/12", ">=0"),
    _r("repayments.csv", "total_due", "number", "no", "", "Scheduled total = principal_due + interest_due", ">0", SYN_FIN, "sum", "= principal + interest"),
    _r("repayments.csv", "payment_date", "date", "yes", "", "Date of final settlement (fully paid) or last partial payment; null if nothing paid", ">= application date", INT, "behaviour simulation", "not before application"),
    _r("repayments.csv", "principal_paid", "number", "yes", "", "Principal received (interest allocated first)", ">=0", SYN_FIN, "payment allocation", ">=0"),
    _r("repayments.csv", "interest_paid", "number", "yes", "", "Interest received", ">=0", SYN_FIN, "payment allocation", ">=0"),
    _r("repayments.csv", "total_paid", "number", "yes", "", "Total received for the instalment (sum of payment events)", ">=0, <= total_due", SYN_FIN, "sum of events", "= principal_paid + interest_paid"),
    _r("repayments.csv", "payment_status", "string", "no", "", "ON_TIME (settled <= due), LATE (settled after due), PARTIAL (paid < due, still open), MISSED (nothing paid, still open)", "ON_TIME, LATE, PARTIAL, MISSED", INT, "derived from events", "consistent with days_past_due"),
    _r("repayments.csv", "days_past_due", "integer", "no", "", "Settled: max(0, payment_date - due_date). Open: report/cutoff date - due_date (as of updated_at)", ">=0", INT, "see convention", "consistent with status"),
    _r("repayments.csv", "currency", "string", "no", "", "Currency", "EUR", INT, "always EUR", "domain check"),
    _r("repayments.csv", "updated_at", "timestamp", "no", "", "Version time: settlement posting time, or month-end snapshot time for open instalments", "ISO timestamp", INT, "settlement time / cutoff 23:xx", "latest wins"),
    # ---- macro -----------------------------------------------------------------------
    _r("macroeconomic_monthly.csv", "month", "string", "no", "PK", "Calendar month (YYYY-MM)", "2016-01..2025-12", INT, "120 months", "unique"),
    _r("macroeconomic_monthly.csv", "inflation_rate", "number", "no", "", "Annual inflation, % (SYNTHETIC, Greece-like)", "-5..15", INT, "anchored interpolation + noise", "range"),
    _r("macroeconomic_monthly.csv", "unemployment_rate", "number", "no", "", "Unemployment rate, % (SYNTHETIC, Greece-like)", "5..30", INT, "anchored interpolation + noise", "range"),
    _r("macroeconomic_monthly.csv", "reference_rate", "number", "no", "", "Policy reference rate, % (approximates ECB MRO)", "0..6", INT, "step path", "range"),
    _r("macroeconomic_monthly.csv", "consumer_confidence_index", "number", "yes", "", "Synthetic consumer-confidence index (0-100 style)", "0..100", INT, "anchored interpolation + noise", "range; optional"),
    # ---- transactions ----------------------------------------------------------------
    _r("transactions.json", "event_id", "string", "no", "PK", "Event key (EV + 9 digits), chronological", "EV000000001..", INT, "sequential by event time", "dedup on event_id"),
    _r("transactions.json", "event_type", "string", "no", "", "Event type (CARD_PAYMENT is an aggregated card-spend activity event, not an individual POS transaction)", "LOAN_REPAYMENT, SALARY_CREDIT, ACCOUNT_CREDIT, CARD_PAYMENT, DIRECT_DEBIT, CASH_WITHDRAWAL, BANK_TRANSFER_IN, BANK_TRANSFER_OUT", INT, "see generator", "domain check"),
    _r("transactions.json", "event_time", "string(timestamp)", "no", "", "ISO timestamp; UTC 'Z' (~85%) or local offset +02:00/+03:00 (~15%)", "valid instant 2016..2025", INT, "mixed offsets for Silver normalisation", "parse to UTC"),
    _r("transactions.json", "customer_id", "string", "no", "FK customers", "Customer the event belongs to", "existing customer", INT, "", "FK check"),
    _r("transactions.json", "account.loan_account", "string", "yes", "", "Loan account (LN + application number); required for LOAN_REPAYMENT", "LN000001..", INT, "", "required for repayments"),
    _r("transactions.json", "account.application_id", "string", "yes", "FK loan_applications", "Application of the loan; required for LOAN_REPAYMENT", "LA..", INT, "", "FK + relationship check"),
    _r("transactions.json", "account.repayment_id", "string", "yes", "FK repayments", "Instalment settled; required for LOAN_REPAYMENT", "RP..", INT, "", "FK check"),
    _r("transactions.json", "account.current_account", "string", "yes", "", "Customer current account (AC + 6 digits); non-loan events", "AC..", INT, "", "optional"),
    _r("transactions.json", "payment.amount", "number", "no", "", "Event amount in EUR (positive; direction gives sign)", ">0", SYN_FIN, "income/spend model; loan payments = settlement amounts", ">0"),
    _r("transactions.json", "payment.currency", "string", "no", "", "Currency", "EUR", INT, "", "domain check"),
    _r("transactions.json", "payment.channel", "string", "yes", "", "Payment channel", "DIRECT_DEBIT, ONLINE, MOBILE, BRANCH, STANDING_ORDER, PAYROLL, PENSION, TRANSFER, POS, ATM, BENEFIT", INT, "", "optional"),
    _r("transactions.json", "payment.direction", "string", "yes", "", "CREDIT = inflow to the customer account, DEBIT = outflow", "CREDIT, DEBIT", INT, "", "optional"),
    _r("transactions.json", "source.system", "string", "no", "", "Originating system", "core-banking, payroll-gw, card-switch, payments-hub, atm-network", INT, "", "optional"),
    _r("transactions.json", "source.version", "string", "no", "", "Source schema/version", "2.1, 2.3, 2.4", INT, "by event year", "optional"),
]


def render_markdown(conventions: str) -> str:
    out = ["# Team 2 synthetic source data - schema dictionary\n", conventions.strip(), "\n"]
    for src in dict.fromkeys(f[0] for f in FIELDS):
        out.append(f"\n## {src}\n")
        out.append("| " + " | ".join(HEAD[1:]) + " |")
        out.append("|" + "---|" * (len(HEAD) - 1))
        for f in FIELDS:
            if f[0] == src:
                out.append("| " + " | ".join(str(x).replace("|", "/") for x in f[1:]) + " |")
    return "\n".join(out) + "\n"
