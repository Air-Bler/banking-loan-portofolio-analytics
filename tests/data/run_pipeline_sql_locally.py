"""Runs the pipeline SQL in local Spark and checks it against the official Team 2 data. Owner: P1

  pip install pyspark==4.0.1          (needs Java 17 or 21)
  python tests/data/run_pipeline_sql_locally.py --pipelines pipelines --landing data/landing \
         --metadata data/generated_metadata [--all-only]

Pipeline-only syntax is translated: streaming tables and materialized views become cached temp views,
STREAM(x) becomes x, read_files() becomes a view over the landing files (with _metadata and _rescued_data),
and the AUTO CDC flow is emulated (SCD2 = one row per version with __START_AT / __END_AT).

Checks, after batch_001 and after all four batches:
  * every expectation evaluated, the reconciliation passes
  * every planted defect in quality_injection_manifest.csv is caught by the right rule, fixed in
    standardisation, or superseded by a later correct delivery; and no rule fires on clean records
  * the 8 KPIs compared with the dataset's clean-truth KPIs in generation_report.json
"""
import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

args = argparse.ArgumentParser()
args.add_argument("--pipelines", default="pipelines")
args.add_argument("--landing", default="data/landing")
args.add_argument("--metadata", default="data/generated_metadata")
args.add_argument("--all-only", action="store_true", help="skip the batch_001-only run")
cli = args.parse_args()
PIPE, LANDING, META = Path(cli.pipelines), Path(cli.landing), Path(cli.metadata)
BATCHES = sorted(p.name for p in LANDING.iterdir() if p.name.startswith("batch_"))

spark = (SparkSession.builder.master("local[2]").config("spark.ui.enabled", "false")
         .config("spark.ui.showConsoleProgress", "false").config("spark.sql.session.timeZone", "UTC")
         .config("spark.sql.shuffle.partitions", "8").config("spark.driver.memory", "4500m")
         .config("spark.sql.subquery.maxThreadThreshold", "1").getOrCreate())
spark.sparkContext.setLogLevel("ERROR")
logging.disable(logging.CRITICAL)


def statements():
    out = []
    for layer in ["bronze", "silver", "gold"]:
        for f in sorted((PIPE / layer).glob("*.sql")):
            for raw in re.split(r";\s*(?:\n|$)", f.read_text()):
                body = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("--")).strip()
                if body:
                    out.append((f"{layer}/{f.name}", body))
    return out


def read_files_view(name, pattern, fmt, schema, batches):
    fname = pattern.rsplit("/", 1)[1]
    frames = []
    for b in batches:
        path = LANDING / b / fname
        if not path.exists():
            continue
        if fmt == "text":
            frames.append(spark.read.text(str(path)).select("value", "_metadata"))
            continue
        cols = [c.strip().split()[0] for c in schema.replace("\n", " ").split(",") if c.strip()]
        df = spark.read.option("header", True).csv(str(path))
        extra = [c for c in df.columns if c not in cols]
        rescued = F.to_json(F.struct(*extra)) if extra else F.lit(None).cast("string")
        frames.append(df.select(*cols, rescued.alias("_rescued_data"), "_metadata"))
    df = frames[0]
    for other in frames[1:]:
        df = df.unionByName(other)
    df.createOrReplaceTempView(f"rf_{name}")
    return f"rf_{name}"


def translate(body, batches):
    m = re.match(r"CREATE FLOW \w+\s+AS AUTO CDC INTO (\w+)\s+FROM STREAM\((\w+)\)\s+KEYS \((\w+)\)\s+"
                 r"SEQUENCE BY (\w+)\s+STORED AS SCD TYPE (\d)", body, re.S)
    if m:
        target, source, key, seq, scd = m.groups()
        q = (f"SELECT *, {seq} AS __START_AT, LEAD({seq}) OVER (PARTITION BY {key} ORDER BY {seq}) AS __END_AT "
             f"FROM {source}") if scd == "2" else (
            f"SELECT * EXCEPT (rn) FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY {key} ORDER BY {seq} DESC) rn "
            f"FROM {source}) WHERE rn = 1")
        return target, q, []
    m = re.match(r"CREATE OR REFRESH (?:STREAMING TABLE|MATERIALIZED VIEW) (\w+)", body)
    assert m, body[:80]
    parts = re.split(r"\n\s*AS\s*\n", body, maxsplit=1)
    if len(parts) == 1:
        return None
    name, (header, query) = m.group(1), parts
    constraints = re.findall(r"CONSTRAINT (\w+)\s+EXPECT \((.*?)\)(\s+ON VIOLATION FAIL UPDATE)?\s*(?:,|\n\))",
                             header, re.S)
    rf = re.search(r"STREAM read_files\(\s*'([^']+)',\s*format => '(\w+)'(.*?)\n\)", query, re.S)
    if rf:
        pattern, fmt, rest = rf.groups()
        sm = re.search(r"schema => '(.*?)'", rest, re.S)
        query = query[: rf.start()] + read_files_view(name, pattern, fmt, sm.group(1) if sm else None, batches) \
            + query[rf.end():]
    return name, re.sub(r"STREAM\((\w+)\)", r"\1", query), constraints


WORK = Path(__file__).resolve().parent / ".check_output"


def run(batches):
    """Builds every table in dependency order. Each result is written to Parquet and read back (like a
    materialised table), which keeps memory low; a table is reused when its SQL, its inputs and the
    loaded batches are unchanged since the last run."""
    import hashlib

    for t in spark.catalog.listTables():
        if t.isTemporary:
            spark.catalog.dropTempView(t.name)
    store = WORK / "_".join(batches)
    store.mkdir(parents=True, exist_ok=True)
    pending = [t for t in (translate(b, batches) for _, b in statements()) if t]
    names = {t[0] for t in pending}
    deps = {t[0]: {n for n in names if n != t[0] and re.search(rf"\b{n}\b", t[1])} for t in pending}
    done, rebuilt, expectations = set(), set(), {}
    while pending:
        ready = [t for t in pending if deps[t[0]] <= done]
        if not ready:
            sys.exit(f"dependency cycle: { {t[0]: deps[t[0]] - done for t in pending} }")
        for name, query, constraints in ready:
            t0 = time.time()
            digest = hashlib.sha256(query.encode()).hexdigest()
            marker = store / f"{name}.sha"
            reuse = (marker.exists() and marker.read_text() == digest and not (deps[name] & rebuilt)
                     and (store / name).exists())
            try:
                if not reuse:
                    spark.sql(f"CREATE OR REPLACE TEMP VIEW {name}__q AS {query}")
                    spark.table(f"{name}__q").write.mode("overwrite").parquet(str(store / name))
                    marker.write_text(digest)
                    rebuilt.add(name)
                spark.read.parquet(str(store / name)).createOrReplaceTempView(name)
                for cname, expr, fail in constraints:
                    bad = spark.sql(f"SELECT COUNT(*) FROM {name} WHERE NOT ({expr})").first()[0]
                    expectations[cname] = (bad, bool(fail.strip()))
            except Exception as e:
                sys.exit(f"ERROR {name}: {str(e).splitlines()[0][:500]}")
            print(f"    {'reused' if reuse else 'built'} {name} in {time.time() - t0:.0f}s", flush=True)
            done.add(name)
        pending = [t for t in pending if t[0] not in done]
    return expectations, store


def q(sql):
    return spark.sql(sql).collect()


# planted defect -> how the pipeline must handle it: rule ids, or 'fixed' / 'dedup' / 'version'
EXPECTED = {
    ("customers.csv", "impossible_dob"): ["CUS-01"], ("customers.csv", "missing_segment"): ["CUS-02"],
    ("customers.csv", "missing_income"): ["CUS-03"], ("customers.csv", "missing_email"): ["CUS-04"],
    ("customers.csv", "malformed_email"): ["CUS-04"], ("customers.csv", "duplicate_contact_email"): ["CUS-05"],
    ("customers.csv", "missing_phone"): ["CUS-06"], ("customers.csv", "invalid_phone"): ["CUS-06"],
    ("customers.csv", "date_format_variation"): "fixed", ("customers.csv", "whitespace_case"): "fixed",
    ("customers.csv", "phone_format_issue"): "fixed",
    ("loan_applications.csv", "missing_consent"): ["APP-02"], ("loan_applications.csv", "missing_status"): ["APP-03"],
    ("loan_applications.csv", "approved_gt_requested"): ["APP-05"],
    ("loan_applications.csv", "nonpositive_requested_amount"): ["APP-05"],
    ("loan_applications.csv", "requested_outside_product_range"): ["APP-06"],
    ("loan_applications.csv", "decision_before_application"): ["APP-07"],
    ("loan_applications.csv", "duplicate_application_rekeyed"): ["APP-08"],
    ("loan_applications.csv", "invalid_currency"): ["APP-09", "fixed"],
    ("loan_applications.csv", "risk_score_out_of_range"): ["APP-10"],
    ("loan_applications.csv", "unknown_customer"): ["APP-11"],
    ("loan_applications.csv", "unknown_branch"): ["APP-12"], ("loan_applications.csv", "unknown_product"): ["APP-12"],
    ("loan_applications.csv", "date_format_variation"): "fixed",
    ("repayments.csv", "orphan_application"): ["REP-01"],
    ("repayments.csv", "duplicate_installment_number"): ["REP-03"],
    ("repayments.csv", "negative_amount"): ["REP-04"],
    ("repayments.csv", "impossible_payment_date"): ["REP-05"],
    ("repayments.csv", "invalid_currency"): ["REP-06", "fixed"],
    ("repayments.csv", "amount_sum_inconsistent"): ["REP-07"],
    ("repayments.csv", "dpd_status_inconsistent"): ["REP-08"],
    ("transactions.json", "malformed_json_line"): ["TRX-00"],
    ("transactions.json", "missing_required_nested"): ["TRX-02"],
    ("transactions.json", "impossible_timestamp"): ["TRX-03"],
    ("transactions.json", "invalid_amount"): ["TRX-04", "fixed"],
    ("transactions.json", "unknown_reference"): ["TRX-06", "TRX-07"],
    ("transactions.json", "wrong_reference_relationship"): ["TRX-08", "TRX-09", "TRX-02"],  # TRX-09: installment is an orphan; TRX-02: id left empty
    ("transactions.json", "malformed_event_type"): "fixed", ("transactions.json", "malformed_currency"): "fixed",
    ("macroeconomic_monthly.csv", "missing_optional_indicator"): ["MAC-01"],
}
ENTITY = {"customers.csv": "customers", "loan_applications.csv": "loan_applications",
          "repayments.csv": "repayments", "transactions.json": "transactions",
          "macroeconomic_monthly.csv": "macroeconomic_monthly"}
CURRENT = {"customers": "silver_customers_current", "loan_applications": "silver_loan_applications_checked",
           "repayments": "silver_repayments_checked", "transactions": "silver_transactions_checked"}
KEY = {"customers": "customer_id", "loan_applications": "application_id", "repayments": "repayment_id",
       "transactions": "event_id"}
CASCADE_RULES = {"REP-02", "TRX-09"}


def manifest_check(out: Path) -> bool:
    import pandas as pd

    man = pd.read_csv(META / "quality_injection_manifest.csv", dtype=str, keep_default_na=False)
    qq = pd.read_parquet(out / "silver_quarantine", columns=["rule_id", "entity", "record_key"])
    cur = pd.concat([pd.read_parquet(out / t, columns=[KEY[e], "batch_id"])
                     .rename(columns={KEY[e]: "record_key", "batch_id": "current_batch"}).assign(entity=e)
                     for e, t in CURRENT.items()])
    qq["record_key"] = qq.record_key.fillna("").astype(str)
    hits = qq.groupby(["entity", "record_key"])["rule_id"].apply(set).to_dict()
    # a shared e-mail stops being shared when the other customer changes e-mail in a later batch
    cust = pd.read_parquet(out / "silver_customers_current", columns=["customer_id", "email"])
    shared = set(cust.email[cust.email.duplicated(keep=False) & cust.email.notna()])
    unshared_now = set(cust.customer_id[~cust.email.isin(shared)])
    current_batch = cur.set_index(["entity", "record_key"])["current_batch"].to_dict()
    ok = True
    print("\n  Planted defects (manifest) -> what the pipeline did")
    print(f"  {'file':24} {'defect':34} {'planted':>7} {'caught':>7} {'fixed':>6} {'superseded':>10} {'missed':>6}")
    for (src, dtype), expect in sorted(EXPECTED.items()):
        entity = ENTITY[src]
        rules = {r for r in (expect if isinstance(expect, list) else []) if r != "fixed"}
        can_fix = expect == "fixed" or (isinstance(expect, list) and "fixed" in expect)
        m = man[(man.source_file == src) & (man.defect_type == dtype)][["record_id", "batch_id"]].drop_duplicates()
        caught = fixed = superseded = 0
        missed = []
        for rec, batch in m.itertuples(index=False):
            if rules & hits.get((entity, rec), set()):
                caught += 1
            elif current_batch.get((entity, rec), "") > batch:
                superseded += 1
            elif dtype == "duplicate_contact_email" and rec in unshared_now:
                superseded += 1
            elif can_fix:
                fixed += 1
            else:
                missed.append(rec)
        ok &= not missed
        print(f"  {src:24} {dtype:34} {len(m):7} {caught:7} {fixed:6} {superseded:10} {len(missed):6}"
              f"{'' if not missed else '  <-- MISSED e.g. ' + ', '.join(missed[:3])}")
    for src, dtype, rules in [("customers.csv", "date_format_variation", {"CUS-01"}),
                              ("customers.csv", "phone_format_issue", {"CUS-06"}),
                              ("customers.csv", "whitespace_case", {"CUS-02", "CUS-04"}),
                              ("loan_applications.csv", "date_format_variation", {"APP-07"}),
                              ("transactions.json", "malformed_event_type", {"TRX-01"}),
                              ("transactions.json", "malformed_currency", {"TRX-05"})]:
        recs = set(man[(man.source_file == src) & (man.defect_type == dtype)].record_id)
        wrong = sorted(r for r in recs if rules & hits.get((ENTITY[src], r), set()))
        ok &= not wrong
        print(f"  fixed in standardisation, never quarantined for it: {src} {dtype}: {len(wrong)} wrongly caught"
              f"{'' if not wrong else '  <-- WRONG e.g. ' + ', '.join(wrong[:3])}")
    print("\n  Rule hits on records with no planted defect at all (cascades REP-02, TRX-09 and CUS-05 partners excluded)")
    planted = set(man.record_id)
    fp = qq[~qq.record_key.isin(planted) & ~qq.rule_id.isin(CASCADE_RULES | {"CUS-05"})]
    if fp.empty:
        print("  none")
    for rule, g in fp.groupby("rule_id"):
        ok = False
        print(f"  {rule}: {len(g)} unexpected, e.g. {', '.join(g.record_key.head(3))}  <-- FALSE POSITIVE")
    print("  CUS-05 on customers not in the manifest (the other owner of a shared e-mail):",
          int((~qq[qq.rule_id == "CUS-05"].record_key.isin(planted)).sum()))
    return ok


ok = True
scenarios = [BATCHES] if cli.all_only else [BATCHES[:1], BATCHES]
for batches in scenarios:
    print(f"\n===== loaded: {', '.join(batches)}", flush=True)
    exp, STORE = run(batches)
    print("  quarantine by rule:", {r[0]: r[1] for r in q(
        "SELECT rule_id, COUNT(*) FROM silver_quarantine GROUP BY rule_id ORDER BY rule_id")})
    print("  silver rows:", {t: q(f"SELECT COUNT(*) FROM {t}")[0][0] for t in
                             ["silver_customers_current", "silver_loan_applications", "silver_repayments",
                              "silver_transactions", "silver_macro_monthly"]})
    for k, (bad, fail) in exp.items():
        if fail and bad:
            ok = False
            print("  FAIL UPDATE would stop the pipeline:", k, bad)
    for r in q("SELECT check_name, silver_value, gold_value, status FROM reconciliation"):
        ok &= r.status == "PASS"
        print(f"  recon {r.status} {r.check_name}: {r.silver_value:,.2f} / {r.gold_value:,.2f}")
    print("  bronze rows:", {t: q(f"SELECT COUNT(*) FROM bronze_{t}")[0][0] for t in
                             ["customers", "branches", "products", "loan_applications", "repayments",
                              "transactions", "macroeconomic_monthly"]})
    print("  refresh_info:", q("SELECT as_of_date, batches_loaded FROM refresh_info")[0].asDict())

report = json.loads((META / "generation_report.json").read_text())
truth = report["kpis"]["overall"]
s = q("SELECT * FROM kpi_portfolio_summary")[0].asDict()
print("\n  KPIs: pipeline (valid records only) vs dataset clean truth (no defects)")
pairs = [("applications", truth["applications"]), ("requested_amount", truth["requested_amount_eur"]),
         ("approval_rate", truth["approval_rate"]), ("avg_decision_days", truth["avg_decision_time_days"]),
         ("dti_share_below_20", truth["dti_band_counts"]["<20%"]["share"]),
         ("dti_share_20_35", truth["dti_band_counts"]["20-35%"]["share"]),
         ("dti_share_35_50", truth["dti_band_counts"]["35-50%"]["share"]),
         ("dti_share_above_50", truth["dti_band_counts"][">50%"]["share"]),
         ("delinquency_rate_30", truth["delinquency_rate_loans_30plus_dpd_open_at_2025-12-31"]),
         ("outstanding_balance", truth["outstanding_balance_eur_at_2025-12-31"]),
         ("manual_review_rate", truth["manual_review_rate"])]
for k, t in pairs:
    v = float(s[k])
    print(f"  {k:22} pipeline {v:>18,.4f}   truth {t:>18,.4f}   diff {100 * (v - t) / t:+.2f}%")
print("  open installment ageing:", {r[0]: r[1] for r in q(
    "SELECT ageing_bucket, open_installments FROM kpi_open_installment_ageing ORDER BY ageing_bucket")},
      " truth:", report["loans_repayments"]["open_installment_dpd_ageing"]["open_installments"])
checks = {
    "fact grain unique": "SELECT COUNT(*) - COUNT(DISTINCT application_id) FROM fact_loan_application",
    "repayment grain unique": "SELECT COUNT(*) - COUNT(DISTINCT repayment_id) FROM fact_repayment",
    "dim_date gaps": "SELECT DATEDIFF(MAX(date), MIN(date)) + 1 - COUNT(*) FROM dim_date",
    "installments outside the calendar": "SELECT COUNT(*) FROM fact_repayment f LEFT ANTI JOIN dim_date d ON f.due_date_key = d.date_key",
    "dangling graph edges": "SELECT COUNT(*) FROM kg_edges e LEFT ANTI JOIN kg_nodes n ON e.source_id = n.node_id",
    "dangling graph edges (target)": "SELECT COUNT(*) FROM kg_edges e LEFT ANTI JOIN kg_nodes n ON e.target_id = n.node_id",
}
for label, sql in checks.items():
    v = q(sql)[0][0]
    ok &= v == 0
    print(f"  check {label}: {v} {'OK' if v == 0 else 'MISMATCH'}")
print("  dims:", {d: q(f"SELECT COUNT(*) FROM {d}")[0][0] for d in
                  ["dim_date", "dim_branch", "dim_product", "dim_customer_segment", "dim_risk_band",
                   "dim_application_status", "macro_monthly", "fact_dq_exception", "kg_nodes", "kg_edges"]})
spark.stop()
ok &= manifest_check(STORE)
print("\nALL CHECKS PASS" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
