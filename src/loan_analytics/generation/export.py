"""Write the delivered batches (CSV + JSON Lines) and the data dictionary."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .batches import Delivery
from .config import BATCH_IDS

CSV_SPECS = {
    "branches.csv": (["branch_code", "branch_name", "city", "region", "opened_date"], {}),
    "products.csv": (["product_code", "product_name", "product_family", "min_amount", "max_amount",
                      "min_term_months", "max_term_months", "base_rate"],
                     {"min_amount": "f0", "max_amount": "f0", "min_term_months": "int", "max_term_months": "int", "base_rate": "f3"}),
    "customers.csv": (["customer_id", "first_name", "last_name", "email", "phone", "date_of_birth", "segment",
                       "annual_income", "household_id", "employment_status", "employment_start_date",
                       "created_at", "updated_at"], {"annual_income": "f0"}),
    "loan_applications.csv": (["application_id", "customer_id", "branch_code", "product_code", "application_date",
                               "decision_date", "status", "requested_amount", "approved_amount", "currency",
                               "term_months", "interest_rate", "risk_score", "monthly_debt",
                               "annual_income_at_application", "employment_status_at_application",
                               "declared_monthly_expenses", "consent_flag", "manual_review", "updated_at", "channel"],
                              {"requested_amount": "f2", "approved_amount": "f2", "term_months": "int",
                               "interest_rate": "f4", "risk_score": "int", "monthly_debt": "f2",
                               "annual_income_at_application": "f0", "declared_monthly_expenses": "f0"}),
    "repayments.csv": (["repayment_id", "application_id", "installment_number", "due_date", "principal_due",
                        "interest_due", "total_due", "payment_date", "principal_paid", "interest_paid",
                        "total_paid", "payment_status", "days_past_due", "currency", "updated_at"],
                       {"installment_number": "int", "principal_due": "f2", "interest_due": "f2", "total_due": "f2",
                        "principal_paid": "f2", "interest_paid": "f2", "total_paid": "f2", "days_past_due": "int"}),
    "macroeconomic_monthly.csv": (["month", "inflation_rate", "unemployment_rate", "reference_rate",
                                   "consumer_confidence_index"],
                                  {"inflation_rate": "f2", "unemployment_rate": "f2", "reference_rate": "f2",
                                   "consumer_confidence_index": "f1"}),
}


def _fmt(v, kind: str):
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if kind == "int":
        return str(int(round(float(v))))
    if kind.startswith("f"):
        return f"{float(v):.{int(kind[1:])}f}"
    return str(v)


def write_csv(df: pd.DataFrame, name: str, path: Path) -> int:
    cols, kinds = CSV_SPECS[name]
    out = {}
    for c in cols:
        k = kinds.get(c, "s")
        out[c] = [_fmt(v, k) for v in df[c].tolist()]
    pd.DataFrame(out, columns=cols).to_csv(path, index=False, lineterminator="\n", na_rep="")
    return len(df)


def write_jsonl(df: pd.DataFrame, path: Path) -> int:
    cols = ["event_id", "event_type", "event_time", "customer_id", "loan_account", "application_id",
            "repayment_id", "current_account", "amount", "currency", "channel", "direction", "system", "version",
            "_malformed"]
    data = {c: df[c].tolist() for c in cols}
    lines = []

    def ok(v):
        if v is None:
            return False
        try:
            return not pd.isna(v)
        except (TypeError, ValueError):
            return True

    for n in range(len(df)):
        acc = {}
        for key, col in (("loan_account", "loan_account"), ("application_id", "application_id"),
                         ("repayment_id", "repayment_id"), ("current_account", "current_account")):
            if ok(data[col][n]):
                acc[key] = data[col][n]
        pay = {}
        amt = data["amount"][n]
        if ok(amt):
            pay["amount"] = amt if isinstance(amt, str) else float(amt)
        for key in ("currency", "channel", "direction"):
            if ok(data[key][n]):
                pay[key] = data[key][n]
        rec = {"event_id": data["event_id"][n], "event_type": data["event_type"][n],
               "event_time": data["event_time"][n]}
        if ok(data["customer_id"][n]):
            rec["customer_id"] = data["customer_id"][n]
        rec["account"] = acc
        rec["payment"] = pay
        rec["source"] = {"system": data["system"][n], "version": data["version"][n]}
        s = json.dumps(rec, ensure_ascii=False)
        if data["_malformed"][n]:
            s = s[: int(len(s) * 0.62)]
        lines.append(s)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)


def _sort_batch(df: pd.DataFrame, keys) -> pd.DataFrame:
    return df.sort_values(keys, kind="mergesort").reset_index(drop=True)


def write_batches(d: Delivery, out_dir: Path) -> dict:
    landing = out_dir / "landing"
    counts: dict = {}
    for k, b in enumerate(BATCH_IDS):
        bdir = landing / b
        bdir.mkdir(parents=True, exist_ok=True)
        c = {}
        if k == 0:
            c["branches.csv"] = write_csv(d.branches, "branches.csv", bdir / "branches.csv")
            c["products.csv"] = write_csv(d.products, "products.csv", bdir / "products.csv")
        cu = d.customers[d.customers["_batch"] == k]
        c["customers.csv"] = write_csv(_sort_batch(cu, ["customer_id", "updated_at"]), "customers.csv", bdir / "customers.csv")
        ap = d.applications[d.applications["_batch"] == k]
        c["loan_applications.csv"] = write_csv(_sort_batch(ap, ["application_id", "updated_at"]), "loan_applications.csv",
                                               bdir / "loan_applications.csv")
        rp = d.repayments[d.repayments["_batch"] == k]
        c["repayments.csv"] = write_csv(_sort_batch(rp, ["repayment_id", "updated_at"]), "repayments.csv", bdir / "repayments.csv")
        mc = d.macro[d.macro["_batch"] == k]
        c["macroeconomic_monthly.csv"] = write_csv(mc.reset_index(drop=True), "macroeconomic_monthly.csv",
                                                   bdir / "macroeconomic_monthly.csv")
        tx = d.transactions[d.transactions["_batch"] == k]
        tx = tx.assign(_t=tx["event_id"]).sort_values(["_t"], kind="mergesort").reset_index(drop=True)
        c["transactions.json"] = write_jsonl(tx, bdir / "transactions.json")
        counts[b] = c
    return counts
