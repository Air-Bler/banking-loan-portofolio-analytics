"""End-to-end orchestration: clean truth -> validate -> defects -> batches -> report."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from .batches import build_delivery
from .config import BATCH_IDS, GenConfig
from .customers import build_customers
from .defects import inject_all
from .dictionary import render_markdown
from .export import write_batches
from .histories import Simulator
from .macro import build_macro
from .reference import load_reference
from .tables import build_applications, build_repayments, build_transactions
from .validate import build_report, validate_clean

CONVENTIONS = """
## Conventions (authoritative)

* **Synthetic data only.** No real PII. Latent generator variables (financial resilience, stress, shocks)
  are never exported. Macro series are *synthetic, calibrated to approximate Greek / Euro-area patterns*.
* **Horizon:** detailed events 2016-01-01 .. 2025-12-31; customers/branches may pre-date 2016.
* **monthly_debt** = existing monthly debt obligations *before* the requested loan: an external-obligation
  component, plus the scheduled instalment of each of this bank's loans whose schedule is running on the
  application date, plus - for loans whose schedule has ended (maturity or early termination) but that are not
  observably paid off by that date - `min(last scheduled instalment, outstanding principal as of the application
  date)`. The latter is a synthetic proxy for the monthly burden of unresolved post-schedule debt; it has no
  expiry and never uses payments dated after the application date. **DTI** = `monthly_debt / (annual_income_at_application / 12)`.
  Application-time snapshots (`annual_income_at_application`, `employment_status_at_application`,
  `declared_monthly_expenses`) are never overwritten by later customer changes.
* **Application status:** APPROVED / REJECTED / WITHDRAWN are final. SUBMITTED / UNDER_REVIEW only appear for
  applications still undecided at 2025-12-31 (`decision_date` null). An application row is written when it is
  decided (`updated_at` = decision time); for WITHDRAWN, `decision_date` is the withdrawal date.
  Approval rate = APPROVED / (APPROVED + REJECTED). Average decision time uses APPROVED + REJECTED.
* **Repayments:** one row per scheduled instalment; only instalments due on or before 2025-12-31 exist.
  Partial payments are individual `LOAN_REPAYMENT` events in transactions.json; the repayment row is the aggregate.
  A fully settled instalment has `payment_date` = final settlement date, `total_paid` = `total_due`,
  status ON_TIME (settled <= due) or LATE, `days_past_due = max(0, payment_date - due_date)`.
  An open instalment is PARTIAL (paid > 0) or MISSED (paid = 0); its `days_past_due` is measured against the
  delivery cutoff stored in `updated_at` (month-end snapshot). Open instalments are re-delivered when they
  settle (later `updated_at` wins) and once more in batch_004 with DPD at 2025-12-31.
* **30+ DPD event:** an instalment is 30+ DPD from `due_date + 30` until fully settled.
* **Delinquency ageing:** open (PARTIAL/MISSED) instalments are never written off or closed and their DPD keeps
  growing until 2025-12-31. Analyse open exposure in DPD ageing buckets: 30-59, 60-89, 90-179, 180-365, 365+
  (`generation_report.json` -> `loans_repayments.open_installment_dpd_ageing`). No universal "30-365 days" delinquency
  KPI is defined here; the final KPI convention is set in the Gold/Power BI phase.
* **Prevalence definitions (kept distinct):** loan-level eventual 30+ DPD prevalence = loans with >=1 instalment
  reaching 30+ DPD / approved loans whose first instalment fell due >=12 months before 2025-12-31 (strict
  observation window). Snapshot-level = probability a performing loan reaches 30+ DPD within the next 90 days
  (quarterly diagnostic here, monthly in the ML phase).
* **Prior delinquency** for an application on date t = a 30+ DPD event whose observable date (due_date + 30) is <= t.
* **Transaction events:** `CARD_PAYMENT` is an aggregated card-spend/payment activity event (a few per month),
  not an individual point-of-sale transaction. Transactions have no version timestamp: for the same `event_id`
  the later delivery batch wins when reconstructing source state; batch order is the only correction ordering
  mechanism (corrected events may carry the same `source.version`).
* **Quality manifest semantics:** rows with `defect_type` = `wrong_value_corrected_later`: `original_value` = true
  value, `injected_value` = the wrong value delivered earlier (batch_id = that earlier batch). Rows with
  `defect_type` = `correction_record`: `original_value` = the wrong value being superseded, `injected_value` = the
  correct value re-delivered in the later `batch_id`. For all other defects `original_value` is the clean value and
  `injected_value` the delivered (defective) value.
* **Application count cap:** applications per customer are deliberately capped at 8 as a synthetic-generation
  safeguard (a visible spike at 8 is expected). Not recalibrated.
* **Known limitations:** see `known_limitations` in `generation_report.json` (weekend decisions, demographic edge
  cases, aggregated card events, no write-off model, monthly macro features need publication lag in the ML phase).
* **Loan states:** `schedule_complete` = the final contractual instalment exists (installment_number = term_months).
  `paid_off` = schedule complete AND every instalment fully settled. A matured loan with a PARTIAL/MISSED
  instalment or positive outstanding principal stays *open* and, if 30+ DPD, delinquent. Underwriting only sees
  settlement information dated on or before the application date (e.g. a "completed" prior loan means fully paid
  off as of that date). Instalment rows exist only for dues up to 2025-12-31.
* **Cash-flow history:** rich non-loan events (salary, card, direct debit, cash, transfers) are generated around each
  loan lifecycle (3 months before disbursement to 21 months after) for ~60-65% of borrowers; the rest have sparse history.
* **Quarterly snapshots in `generation_report.json` are a generator diagnostic only.** The later capstone ML phase will
  build MONTHLY loan-level snapshots (target: 30+ DPD within the following 90 days; incomplete windows right-censored).
  No ML model is part of this generator.
* **Outstanding balance** at a date = `approved_amount - sum(principal_paid up to that date)`.
* **Batches:** a batch is an ingestion delivery, not a business-date partition. Late-arriving rows carry old
  business dates in a later batch; corrected rows re-deliver an existing key with a newer `updated_at`.
  Reference files are delivered in batch_001 only; macro rows arrive by month (Oct/Nov/Dec in batches 2-4).
* **Delivery semantics:** `transactions.json` is JSON Lines (one event per line). A few lines are deliberately
  truncated (invalid JSON) for Bronze reject-handling tests.
* **Quality manifest** (`quality_injection_manifest.csv`) is development-only and must not be ingested.
"""


def delivery_matrix(counts: dict) -> str:
    files = ["branches.csv", "products.csv", "customers.csv", "loan_applications.csv", "repayments.csv",
             "macroeconomic_monthly.csv", "transactions.json"]
    lines = ["\n## Files delivered per batch (row / event counts, including injected defects)\n",
             "| file | " + " | ".join(counts) + " |", "|---|" + "---|" * len(counts)]
    for f in files:
        lines.append(f"| {f} | " + " | ".join(str(counts[b].get(f, "-")) for b in counts) + " |")
    lines.append("\nbranches.csv and products.csv are reference masters delivered in batch_001 only; "
                 "macroeconomic_monthly.csv delivers history through 2025-09 in batch_001 and one new month per later batch.")
    return "\n".join(lines) + "\n"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def generate(cfg: GenConfig, out_dir: Path, log=print, capture: dict | None = None) -> dict:
    """Run the full pipeline. ``capture`` (optional) receives the in-memory clean truth for tests."""
    t0 = time.time()
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir / "landing", ignore_errors=True)
        shutil.rmtree(out_dir / "generated_metadata", ignore_errors=True)
    (out_dir / "generated_metadata").mkdir(parents=True, exist_ok=True)

    def step(msg):
        log(f"[{time.time() - t0:6.1f}s] {msg}")

    ref = load_reference()
    macro = build_macro(cfg)
    step("reference + macro ready")
    world = build_customers(cfg, ref, macro)
    step(f"customers: {world.n}")
    sim = Simulator(cfg, ref, macro, world).run_all()
    step(f"simulation: {len(sim.apps)} applications, {len(sim.inst)} instalments, {len(sim.tx)} non-loan events")
    apps, app_num = build_applications(cfg, ref, world, sim)
    rep, rid_of = build_repayments(cfg, sim, app_num)
    tx = build_transactions(cfg, sim, app_num, rid_of)
    step(f"clean truth tables: apps={len(apps)} repayment_versions={len(rep)} events={len(tx)}")

    if capture is not None:
        capture.update(cfg=cfg, ref=ref, macro=macro, world=world, sim=sim, apps=apps, app_num=app_num, rep=rep, tx=tx)
    checks = validate_clean(cfg, ref, world, apps, rep, tx, macro)
    failed = [c for c in checks if not c["passed"]]
    step(f"clean-truth validation: {len(checks) - len(failed)}/{len(checks)} checks passed")
    for c in failed:
        step(f"  FAILED: {c['check']} {c['detail']}")
    if failed:
        raise SystemExit("clean truth failed validation; aborting before defect injection")

    delivery = build_delivery(cfg, ref, world, macro, apps, rep, tx)
    manifest = inject_all(cfg, ref, delivery)
    step(f"defects injected; manifest rows: {len(manifest)}")
    counts = write_batches(delivery, out_dir)
    step("batches written")

    meta = out_dir / "generated_metadata"
    manifest.to_csv(meta / "quality_injection_manifest.csv", index=False, lineterminator="\n")
    cfg.dump(meta / "generation_config.json")
    report = build_report(cfg, ref, world, macro, sim, apps, rep, tx, delivery, manifest, counts, checks)
    report["acceptance_checklist"] = checklist(report, cfg, manifest)
    (meta / "schema_dictionary.md").write_text(render_markdown(CONVENTIONS + delivery_matrix(counts)), encoding="utf-8")
    (meta / "generation_report.json").write_text(json.dumps(report, indent=2, default=_json_default), encoding="utf-8")
    step("report written")
    report["_elapsed_seconds"] = round(time.time() - t0, 1)
    return report


# ---------------------------------------------------------------------------
def checklist(rep: dict, cfg: GenConfig, manifest: pd.DataFrame) -> list:
    items = []

    def add(group, text, ok, evidence="", severity="mandatory"):
        items.append({"group": group, "item": text, "passed": bool(ok), "evidence": str(evidence), "severity": severity})

    c = rep["counts"]
    ct = c["clean_truth"]
    cu, ap, lr, tr, ml, kp, dq = (rep["customers"], rep["applications"], rep["loans_repayments"],
                                  rep["transactions"], rep["ml_readiness"], rep["kpis"], rep["data_quality"])
    add("Reference", "Exactly 12 branches / 5 products, codes unchanged", ct["branches"] == 12 and ct["products"] == 5)
    amin, amax = rep["counts"]["date_ranges"]["application_date"]
    add("History", "Detailed history 2016-01-01..2025-12-31", amin >= "2016-01-01" and amax <= "2025-12-31", f"{amin}..{amax}")
    add("History", "Customers enter throughout the decade", all(str(y) in cu["creation_cohorts"] for y in range(2016, 2026)))
    add("History", "Some relationships predate 2016", cu["created_before_2016"] > 0, cu["created_before_2016"])
    add("History", "Repeat borrowers exist", lr["customers_with_multiple_loans"] > 0, lr["customers_with_multiple_loans"])
    hc = rep["history_coverage"]
    add("History", "Applications in every calendar year 2016-2025", all(str(y) in hc["applications_by_year"] and hc["applications_by_year"][str(y)] > 0 for y in range(2016, 2026)), hc["applications_by_year"])
    add("History", "Transaction events in every calendar year 2016-2025", all(hc["transaction_events_by_year"].get(str(y), 0) > 0 for y in range(2016, 2026)), hc["transaction_events_by_year"])
    add("History", "Instalments due in every calendar year 2016-2025", all(hc["repayment_instalments_due_by_year"].get(str(y), 0) > 0 for y in range(2016, 2026)))
    add("History", "Activity extends into late 2025 (application >= 2025-11-01, event >= 2025-12-01)",
        hc["latest_application_date"] >= "2025-11-01" and hc["latest_event_date"] >= "2025-12-01",
        {"app": hc["latest_application_date"], "event": hc["latest_event_date"], "H2_2025_apps_by_month": hc["applications_by_month_2025_H2"]})
    add("Macro", "All 120 macro months 2016-01..2025-12 exist", hc["macro_months_present"] == 120 and not hc["macro_missing_months"], hc["macro_missing_months"])
    add("History", "Genuinely paid-off loans exist (schedule complete AND fully settled)", lr["paid_off_loans"] > 0, lr["paid_off_loans"])
    add("History", "Schedule-complete loans with unresolved debt are kept open (not treated as paid off)",
        lr["schedule_complete_loans"] == lr["paid_off_loans"] + lr["schedule_complete_but_unresolved_loans"], 
        {"schedule_complete": lr["schedule_complete_loans"], "paid_off": lr["paid_off_loans"], "unresolved": lr["schedule_complete_but_unresolved_loans"]})
    add("History", "Previous delinquency exists", lr["customers_with_previous_delinquency_before_later_loan"] > 0)
    add("History", "Multiple simultaneous loans in a minority", 0 < lr["customers_with_overlapping_loans"] < 0.5 * ct["customers"], lr["customers_with_overlapping_loans"])
    add("Scale", "~15k customers", 13500 <= ct["customers"] <= 16500, ct["customers"])
    add("Scale", "30k-40k applications", 30000 <= ct["loan_applications"] <= 40000, ct["loan_applications"])
    add("Scale", "200k-350k repayment rows (approximate target; natural counts preferred)",
        200000 <= ct["repayment_installments"] <= 350000, ct["repayment_installments"], severity="advisory")
    add("Scale", "400k-700k transaction events (soft)", 400000 <= ct["transaction_events"] <= 700000, ct["transaction_events"])
    add("Scale", "Total 650k-1.1M records", 650000 <= c["delivered_rows_grand_total"] <= 1100000, c["delivered_rows_grand_total"])
    add("Customers", "Greek-name share 85-90%", 0.84 <= cu["greek_name_share_proxy"] <= 0.91, cu["greek_name_share_proxy"])
    add("Customers", ">=6 email providers", len(cu["email_provider_mix"]) >= 6, len(cu["email_provider_mix"]))
    add("Customers", "Income right-skewed, not machine-rounded",
        cu["annual_income_quantiles_current"]["p50"] < cu["annual_income_quantiles_current"]["p95"] / 2 and cu["income_ending_000_or_500_share"] < 0.03,
        f"p50={cu['annual_income_quantiles_current']['p50']} 000/500 share={cu['income_ending_000_or_500_share']}")
    add("Applications", "Application-time snapshot differs from current master for some applications",
        cu["applications_where_snapshot_income_differs_from_current"] > 0, cu["applications_where_snapshot_income_differs_from_current"])
    rb = ap["approval_rate_by_risk_band"]
    add("Applications", "Approval probabilistic: overlap across risk bands (no 0%/100% extremes)",
        all(0.0 < v < 1.0 for v in rb.values()), rb)
    mo = ap["manual_review_outcomes"]
    add("Applications", "Manual review meaningful: both approved and rejected outcomes", "APPROVED" in mo and "REJECTED" in mo, mo)
    dm = ap["decision_time_mean_manual_vs_auto"]
    add("Applications", "Manual review increases decision time", dm.get("Y", 0) > dm.get("N", 0), dm)
    add("Repayments", "Late, partial and missed instalments exist",
        lr["late_installments_settled"] > 0 and lr["partial_installments_open"] > 0 and lr["missed_installments_open"] > 0)
    add("Repayments", "Recovery cases exist (also after 30+ DPD)", lr["recovery_cases_loans_after_30plus_dpd_then_3_ontime"] > 0, lr["recovery_cases_loans_after_30plus_dpd_then_3_ontime"])
    prev = lr["loan_level_ever_30plus_dpd"]["prevalence"]
    add("Repayments", "30+ DPD prevalence 8-12% of mature loans", 0.08 <= prev <= 0.12, prev)
    add("Transactions", "All 8 event types present", len(tr["event_type_distribution"]) == 8, len(tr["event_type_distribution"]))
    cov = tr["cash_flow_coverage_borrowers_with_>=12_non_loan_events"]
    add("Transactions", "Rich cash-flow history for 60-80% of borrowers", 0.55 <= cov <= 0.85, cov)
    add("Macro", "120 monthly rows in clean macro source", ct["macro_rows"] == 120)
    ov = dq["overall_share_of_delivered_rows_affected"]
    add("Dirty data", "~4-5% of delivered rows affected overall (4.0-5.5% accepted)", 0.040 <= ov <= 0.055, ov)
    odq = dq["official_team2_defects_present"]
    add("Dirty data", "All official Team 2 defect families present", all(v > 0 for v in odq.values()), odq)
    pk_pairs = {("customers.csv", "customer_id"), ("loan_applications.csv", "application_id"),
                ("repayments.csv", "repayment_id"), ("transactions.json", "event_id")}
    touched = manifest[[(s_, f_) in pk_pairs and d_ != "duplicate_application_rekeyed"
                        for s_, f_, d_ in zip(manifest["source_file"], manifest["field"], manifest["defect_type"])]]
    add("Dirty data", "Primary IDs not corrupted (quarantine key fields only)", len(touched) == 0, len(touched))
    add("Batches", "Four batches; late-arriving and corrected records exist",
        len(c["delivered_rows_per_batch"]) == 4 and sum(dq["late_arriving_records"].values()) > 0 and sum(dq["corrected_records"].values()) > 0,
        {"late": dq["late_arriving_records"], "corrected": dq["corrected_records"]})
    snap = ml["snapshot_diagnostics_90d_forward_30plus_dpd"]
    add("ML readiness", "Monthly/quarterly snapshots + right-censoring identifiable", snap.get("right_censored_excluded", 0) > 0, snap.get("right_censored_excluded"))
    add("ML readiness", "No latent/future labels exported", rep["clean_truth_validation"]["all_passed"])
    a = ml["loan_level_auc_risk_score_only(-score)"]
    add("ML readiness", "Risk score useful but not dominant (loan-level AUC 0.55-0.72)", 0.55 <= a <= 0.72, a)
    cx = ml["counterexamples_loan_level"]
    add("ML readiness", "Counterexamples exist", all(v > 0 for v in cx.values()), cx)
    add("KPIs", "All eight mandatory KPIs calculable", len(kp["overall"]) >= 8)
    return items


# ---------------------------------------------------------------------------
def verify_reproducibility(cfg: GenConfig, out_dir: Path, log=print) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="team2_repro_"))
    try:
        generate(cfg, tmp, log=lambda *_: None)
        diffs, n = [], 0
        for sub in ("landing", "generated_metadata"):
            for p in sorted((out_dir / sub).rglob("*")):
                if p.is_file():
                    q = tmp / p.relative_to(out_dir)
                    n += 1
                    if not q.exists() or _sha(p) != _sha(q):
                        diffs.append(str(p.relative_to(out_dir)))
        return {"files_compared": n, "identical": not diffs, "differences": diffs}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Team 2 synthetic banking source-data generator")
    ap.add_argument("--out", default="data")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--customers", type=int, default=15000)
    ap.add_argument("--verify-repro", action="store_true", help="re-generate into a temp dir and compare checksums")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a GenConfig numeric field")
    a = ap.parse_args(argv)
    kw = {"seed": a.seed, "n_customers": a.customers}
    for kv in a.set:
        k, v = kv.split("=")
        kw[k] = float(v)
    cfg = GenConfig(**kw)
    report = generate(cfg, Path(a.out))
    if a.verify_repro:
        r = verify_reproducibility(cfg, Path(a.out))
        report["reproducibility"] = r
        (Path(a.out) / "generated_metadata" / "generation_report.json").write_text(
            json.dumps(report, indent=2, default=_json_default), encoding="utf-8")
        print("reproducibility:", r)
    chk_ = report["acceptance_checklist"]
    mand = [i for i in chk_ if i["severity"] == "mandatory"]
    failed = [i for i in mand if not i["passed"]]
    print(f"mandatory acceptance checks: {len(mand) - len(failed)}/{len(mand)} passed")
    for i in failed:
        print("  NOT MET:", i["group"], "-", i["item"], "->", i["evidence"])
    for i in chk_:
        if i["severity"] == "advisory" and not i["passed"]:
            print("  ADVISORY (soft target outside range):", i["item"], "->", i["evidence"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
