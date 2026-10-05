"""Controlled source-quality defect injection (Phase B) + development-only manifest.

Only the *delivered* copy of a record is damaged; the clean truth is untouched.
Primary identifiers are never corrupted. Valid adverse banking behaviour
(late / partial / missed payments, high DTI, rejections) is never treated as a
defect. Most defective records carry exactly one defect.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .batches import Delivery
from .config import BATCH_IDS, GenConfig
from .util import iso


class Injector:
    def __init__(self, rng, source: str, df: pd.DataFrame, id_col: str, notes: list):
        self.rng, self.source, self.df, self.id_col, self.notes = rng, source, df, id_col, notes
        self.used: set = set()
        self.extra: list = []     # appended rows (duplicates)

    def eligible(self, mask=None) -> np.ndarray:
        n = len(self.df)
        ok = ~self.df["_protect"].to_numpy(bool)
        if mask is not None:
            ok = ok & np.asarray(mask, bool)
        if self.used:
            u = np.zeros(n, bool)
            u[list(self.used)] = True
            ok = ok & ~u
        return np.where(ok)[0]

    def take(self, n: int, mask=None) -> np.ndarray:
        el = self.eligible(mask)
        n = min(n, len(el))
        if n <= 0:
            return np.array([], dtype=int)
        pick = self.rng.choice(el, size=n, replace=False)
        self.used.update(int(p) for p in pick)
        return pick

    def log(self, idx, fld, dtype, orig, inj):
        self.notes.append(dict(
            source_file=self.source, record_id=self.df[self.id_col].iat[int(idx)], field=fld,
            defect_type=dtype, original_value=orig, injected_value=inj,
            batch_id=BATCH_IDS[int(self.df["_batch"].iat[int(idx)])]))

    def set(self, idx, col, value, dtype, fld=None):
        orig = self.df[col].iat[int(idx)]
        self.df.at[int(idx), col] = value
        self.log(idx, fld or col, dtype, orig, value)


def _counts(total: int, weights: dict) -> dict:
    w = np.array(list(weights.values()), float)
    w = w / w.sum()
    raw = w * total
    base = np.floor(raw).astype(int)
    rem = total - base.sum()
    for j in np.argsort(-(raw - base))[:rem]:
        base[j] += 1
    return dict(zip(weights.keys(), base.tolist()))


# ---------------------------------------------------------------------------
CUST_W = dict(missing_email=.16, malformed_email=.10, duplicate_contact_email=.07, phone_format_issue=.16,
              invalid_phone=.08, missing_phone=.05, whitespace_case=.13, missing_segment=.07,
              missing_income=.06, impossible_dob=.02, date_format_variation=.10)


def _bad_email(rng, e: str) -> str:
    loc, _, dom = e.partition("@")
    k = int(rng.integers(6))
    return [loc + dom, f"{loc}@{dom.replace('.', ',')}", f"{loc}@", f"{loc}@@{dom}",
            f"{loc}@{dom.split('.')[0]}", f"{loc} @{dom}"][k]


def _fmt_phone(rng, p: str) -> str:
    d = "".join(ch for ch in p if ch.isdigit())
    if d.startswith("0030"):
        d = d[4:]
    elif d.startswith("30") and len(d) == 12:
        d = d[2:]
    k = int(rng.integers(4))
    if d.startswith("69") and len(d) == 10:
        return [f"{d[:3]} {d[3:6]} {d[6:]}", f"+30 {d[:3]} {d[3:6]} {d[6:]}", f"{d[:3]}-{d[3:6]}-{d[6:]}",
                f"({d[:2]}) {d[2:]}"][k]
    return [f"{d[:3]} {d[3:]}", f"+30 {d[:3]} {d[3:]}", f"{d[:3]}-{d[3:]}", f"({d[:3]}) {d[3:]}"][k]


def inject_customers(cfg, d: Delivery, rng, notes):
    df = d.customers
    df["annual_income"] = df["annual_income"].astype(object)
    inj = Injector(rng, "customers.csv", df, "customer_id", notes)
    n_def = int(round(cfg.defect_rate_customers * len(df)))
    cnt = _counts(n_def, CUST_W)
    has_email = df["email"].notna().to_numpy()
    for t, k in cnt.items():
        if t == "missing_email":
            for i in inj.take(k):
                inj.set(i, "email", None, t)
        elif t == "malformed_email":
            for i in inj.take(k, has_email):
                inj.set(i, "email", _bad_email(rng, df["email"].iat[i]), t)
        elif t == "duplicate_contact_email":
            for i in inj.take(k, has_email):
                j = int(rng.integers(len(df)))
                while j == i or pd.isna(df["email"].iat[j]) or df["customer_id"].iat[j] == df["customer_id"].iat[i]:
                    j = int(rng.integers(len(df)))
                inj.set(i, "email", df["email"].iat[j], t)
        elif t == "phone_format_issue":
            for i in inj.take(k, df["phone"].notna().to_numpy()):
                inj.set(i, "phone", _fmt_phone(rng, df["phone"].iat[i]), t)
        elif t == "invalid_phone":
            for i in inj.take(k):
                bad = ["12345", "0000000000", "69ABC12345", "+3069123", "99" + str(int(rng.integers(10 ** 7, 10 ** 8))),
                       "6912345#78"][int(rng.integers(6))]
                inj.set(i, "phone", bad, t)
        elif t == "missing_phone":
            for i in inj.take(k):
                inj.set(i, "phone", None, t)
        elif t == "whitespace_case":
            for i in inj.take(k):
                col = ["first_name", "last_name", "email", "segment", "employment_status"][int(rng.integers(5))]
                v = df[col].iat[i]
                if v is None or pd.isna(v):
                    col, v = "last_name", df["last_name"].iat[i]
                form = int(rng.integers(3))
                nv = [f" {v} ", v.upper(), v.lower()][form]
                if nv == v:
                    nv = f"{v} "
                inj.set(i, col, nv, t)
        elif t == "missing_segment":
            for i in inj.take(k):
                inj.set(i, "segment", None, t)
        elif t == "missing_income":
            for i in inj.take(k):
                inj.set(i, "annual_income", None, t)
        elif t == "impossible_dob":
            for i in inj.take(k):
                inj.set(i, "date_of_birth", ["2031-04-12", "1888-01-01", "2026-09-30"][int(rng.integers(3))], t)
        elif t == "date_format_variation":
            for i in inj.take(k):
                y, m, dd = df["date_of_birth"].iat[i].split("-")
                inj.set(i, "date_of_birth", f"{dd}/{m}/{y}", t)


# ---------------------------------------------------------------------------
APP_W = dict(missing_consent=.17, missing_status=.10, duplicate_application_rekeyed=.07,
             exact_duplicate_row=.06, decision_before_application=.12, requested_outside_product_range=.08,
             approved_gt_requested=.10, invalid_currency=.05, risk_score_out_of_range=.12, unknown_customer=.05,
             unknown_branch=.02, unknown_product=.02, nonpositive_requested_amount=.03, date_format_variation=.08)


def inject_applications(cfg, ref, d: Delivery, rng, notes):
    df = d.applications
    for c in ("requested_amount", "approved_amount", "monthly_debt", "risk_score"):
        df[c] = df[c].astype(object)
    inj = Injector(rng, "loan_applications.csv", df, "application_id", notes)
    n_def = int(round(cfg.defect_rate_applications * len(df)))
    cnt = _counts(n_def, APP_W)
    st = df["status"].to_numpy()
    decided = pd.Series(st).isin(["APPROVED", "REJECTED", "WITHDRAWN"]).to_numpy() & df["decision_date"].notna().to_numpy()
    approved = (st == "APPROVED") & df["approved_amount"].notna().to_numpy()
    pmin = dict(zip(ref.products["product_code"], ref.products["min_amount"]))
    pmax = dict(zip(ref.products["product_code"], ref.products["max_amount"]))
    max_num = int(df["application_id"].str[2:].astype(int).max())
    dup_rows = []
    for t, k in cnt.items():
        if t == "missing_consent":
            for i in inj.take(k):
                inj.set(i, "consent_flag", None, t)
        elif t == "missing_status":
            for i in inj.take(k):
                inj.set(i, "status", [None, ""][int(rng.integers(2))], t)
        elif t in ("duplicate_application_rekeyed", "exact_duplicate_row"):
            for i in inj.take(k):
                row = df.iloc[int(i)].to_dict()
                orig_id = row["application_id"]
                if t == "duplicate_application_rekeyed":
                    max_num += 1
                    row["application_id"] = f"LA{max_num:06d}"
                    inj.notes.append(dict(source_file=inj.source, record_id=row["application_id"], field="application_id",
                                          defect_type=t, original_value=orig_id, injected_value="duplicate_of:" + orig_id,
                                          batch_id=BATCH_IDS[int(row["_batch"])]))
                else:
                    nb = int(row["_batch"])
                    if nb < 3 and rng.random() < 0.3:
                        row["_batch"] = nb + 1
                    inj.notes.append(dict(source_file=inj.source, record_id=orig_id, field="*",
                                          defect_type=t, original_value=orig_id, injected_value="exact_duplicate_row",
                                          batch_id=BATCH_IDS[int(row["_batch"])]))
                row["_protect"] = False
                dup_rows.append(row)
        elif t == "decision_before_application":
            for i in inj.take(k, decided):
                o = int(df["_app_o"].iat[i]) - int(rng.integers(1, 21))
                inj.set(i, "decision_date", iso(o), t)
        elif t == "requested_outside_product_range":
            for i in inj.take(k, df["approved_amount"].isna().to_numpy()):
                pc = df["product_code"].iat[i]
                v = pmax[pc] * rng.uniform(1.1, 2.5) if rng.random() < 0.6 else pmin[pc] * rng.uniform(0.15, 0.8)
                inj.set(i, "requested_amount", float(round(v / 10) * 10), t)
        elif t == "approved_gt_requested":
            for i in inj.take(k, approved):
                v = float(round(df["requested_amount"].iat[i] * rng.uniform(1.1, 1.5) / 10) * 10)
                inj.set(i, "approved_amount", v, t)
        elif t == "invalid_currency":
            for i in inj.take(k):
                inj.set(i, "currency", ["EURO", "€", "eur", "XXX", "EU"][int(rng.integers(5))], t)
        elif t == "risk_score_out_of_range":
            for i in inj.take(k):
                inj.set(i, "risk_score", int([0, 1000, 1200, -50, 9999, 250, 900][int(rng.integers(7))]), t)
        elif t == "unknown_customer":
            for i in inj.take(k):
                inj.set(i, "customer_id", f"CU9{int(rng.integers(0, 100000)):05d}", t)
        elif t == "unknown_branch":
            for i in inj.take(k):
                inj.set(i, "branch_code", ["BR099", "BR000", "BR13"][int(rng.integers(3))], t)
        elif t == "unknown_product":
            for i in inj.take(k):
                inj.set(i, "product_code", ["XX-UNK", "PL-XXX", "MTG-VAR"][int(rng.integers(3))], t)
        elif t == "nonpositive_requested_amount":
            for i in inj.take(k):
                v = df["requested_amount"].iat[i]
                inj.set(i, "requested_amount", float(-abs(v)) if rng.random() < 0.6 else 0.0, t)
        elif t == "date_format_variation":
            for i in inj.take(k):
                col = "application_date" if (rng.random() < 0.6 or pd.isna(df["decision_date"].iat[i])) else "decision_date"
                y, m, dd = df[col].iat[i].split("-")
                inj.set(i, col, f"{dd}/{m}/{y}", t)
    if dup_rows:
        d.applications = pd.concat([df, pd.DataFrame(dup_rows)], ignore_index=True)
    else:
        d.applications = df


# ---------------------------------------------------------------------------
REP_W = dict(orphan_application=.17, duplicate_repayment_row=.10, duplicate_installment_number=.08,
             negative_amount=.08, amount_sum_inconsistent=.22, impossible_payment_date=.14,
             dpd_status_inconsistent=.15, invalid_currency=.06)


def inject_repayments(cfg, d: Delivery, rng, notes):
    df = d.repayments
    for c in ("principal_due", "interest_due", "total_due", "principal_paid", "interest_paid", "total_paid", "days_past_due"):
        df[c] = df[c].astype(object)
    inj = Injector(rng, "repayments.csv", df, "repayment_id", notes)
    n_def = int(round(cfg.defect_rate_repayments * len(df)))
    cnt = _counts(n_def, REP_W)
    max_num = int(df["repayment_id"].str[2:].astype(int).max())
    has_pay = df["payment_date"].notna().to_numpy()
    status = df["payment_status"].to_numpy()
    extra = []
    for t, k in cnt.items():
        if t == "orphan_application":
            for i in inj.take(k):
                inj.set(i, "application_id", f"LA9{int(rng.integers(0, 100000)):05d}", t)
        elif t in ("duplicate_repayment_row", "duplicate_installment_number"):
            for i in inj.take(k):
                row = df.iloc[int(i)].to_dict()
                orig = row["repayment_id"]
                if t == "duplicate_installment_number":
                    max_num += 1
                    row["repayment_id"] = f"RP{max_num:07d}"
                    inj.notes.append(dict(source_file=inj.source, record_id=row["repayment_id"], field="installment_number",
                                          defect_type=t, original_value=orig, injected_value="same_installment_as:" + orig,
                                          batch_id=BATCH_IDS[int(row["_batch"])]))
                else:
                    nb = int(row["_batch"])
                    if nb < 3 and rng.random() < 0.3:
                        row["_batch"] = nb + 1
                    inj.notes.append(dict(source_file=inj.source, record_id=orig, field="*", defect_type=t,
                                          original_value=orig, injected_value="exact_duplicate_row",
                                          batch_id=BATCH_IDS[int(row["_batch"])]))
                row["_protect"] = False
                extra.append(row)
        elif t == "negative_amount":
            for i in inj.take(k):
                col = ["principal_paid", "total_due", "interest_due"][int(rng.integers(3))]
                v = df[col].iat[i]
                inj.set(i, col, -abs(float(v)) if float(v) else -1.0, t)
        elif t == "amount_sum_inconsistent":
            for i in inj.take(k):
                v = float(df["total_due"].iat[i])
                inj.set(i, "total_due", round(v * rng.uniform(1.05, 1.4) + 1, 2), t)
        elif t == "impossible_payment_date":
            for i in inj.take(k, has_pay):
                due_o = int(df["_due_o"].iat[i])
                nv = iso(due_o - int(rng.integers(400, 900))) if rng.random() < 0.6 else "2031-" + df["payment_date"].iat[i][5:]
                inj.set(i, "payment_date", nv, t)
        elif t == "dpd_status_inconsistent":
            for i in inj.take(k):
                s = status[i]
                if s == "ON_TIME":
                    inj.set(i, "days_past_due", int(rng.integers(5, 40)), t)
                elif s == "LATE":
                    inj.set(i, "days_past_due", 0, t)
                else:
                    inj.set(i, "payment_status", "ON_TIME", t)
        elif t == "invalid_currency":
            for i in inj.take(k):
                inj.set(i, "currency", ["EURO", "€", "eur", "XXX"][int(rng.integers(4))], t)
    if extra:
        d.repayments = pd.concat([df, pd.DataFrame(extra)], ignore_index=True)
    else:
        d.repayments = df


# ---------------------------------------------------------------------------
TX_W = dict(duplicate_event=.22, missing_required_nested=.18, unknown_reference=.12, malformed_event_type=.12,
            impossible_timestamp=.09, invalid_amount=.13, malformed_currency=.08, wrong_reference_relationship=.06)


def inject_transactions(cfg, d: Delivery, rng, notes):
    df = d.transactions
    df["amount"] = df["amount"].astype(object)
    df["_malformed"] = False
    inj = Injector(rng, "transactions.json", df, "event_id", notes)
    n_def = int(round(cfg.defect_rate_transactions * len(df)))
    cnt = _counts(n_def, TX_W)
    et = df["event_type"].to_numpy()
    is_loan = et == "LOAN_REPAYMENT"
    loan_idx = np.where(is_loan)[0]
    extra = []
    for t, k in cnt.items():
        if t == "duplicate_event":
            for i in inj.take(k):
                row = df.iloc[int(i)].to_dict()
                nb = int(row["_batch"])
                if nb < 3 and rng.random() < 0.3:
                    row["_batch"] = nb + 1
                row["_protect"] = False
                extra.append(row)
                inj.notes.append(dict(source_file=inj.source, record_id=row["event_id"], field="*", defect_type=t,
                                      original_value=row["event_id"], injected_value="exact_duplicate_event",
                                      batch_id=BATCH_IDS[int(row["_batch"])]))
        elif t == "missing_required_nested":
            for i in inj.take(k):
                if is_loan[i]:
                    col = ["repayment_id", "application_id", "loan_account", "amount"][int(rng.integers(4))]
                else:
                    col = ["amount", "currency", "current_account"][int(rng.integers(3))]
                inj.set(i, col, None, t, fld={"amount": "payment.amount", "currency": "payment.currency"}.get(col, "account." + col))
        elif t == "unknown_reference":
            for i in inj.take(k):
                if is_loan[i]:
                    inj.set(i, "repayment_id", f"RP9{int(rng.integers(0, 1000000)):06d}", t, fld="account.repayment_id")
                else:
                    inj.set(i, "customer_id", f"CU9{int(rng.integers(0, 100000)):05d}", t)
        elif t == "malformed_event_type":
            for i in inj.take(k):
                v = df["event_type"].iat[i]
                nv = [v.lower(), v.replace("_", " "), v.replace("_", "-"), v.title().replace("_", " "),
                      v[:-3] + v[-2:]][int(rng.integers(5))]
                inj.set(i, "event_type", nv, t)
        elif t == "impossible_timestamp":
            for i in inj.take(k):
                inj.set(i, "event_time", ["2031-03-14T10:22:00Z", "1970-01-01T00:00:00Z", "2099-12-31T23:59:59Z"][int(rng.integers(3))], t)
        elif t == "invalid_amount":
            for i in inj.take(k, df["amount"].notna().to_numpy()):
                v = float(df["amount"].iat[i])
                r = rng.random()
                nv = -abs(v) if r < 0.45 else (0.0 if r < 0.7 else f"{v:.2f}".replace(".", ","))
                inj.set(i, "amount", nv, t, fld="payment.amount")
        elif t == "malformed_currency":
            for i in inj.take(k):
                inj.set(i, "currency", ["eur", "EURO", "€", "EUR "][int(rng.integers(4))], t, fld="payment.currency")
        elif t == "wrong_reference_relationship":
            for i in inj.take(k, is_loan):
                j = int(loan_idx[int(rng.integers(len(loan_idx)))])
                while df["application_id"].iat[j] == df["application_id"].iat[i]:
                    j = int(loan_idx[int(rng.integers(len(loan_idx)))])
                inj.set(i, "application_id", df["application_id"].iat[j], t, fld="account.application_id")
    # a handful of syntactically broken JSON lines (flagged for the exporter)
    for i in inj.take(4):
        df.at[int(i), "_malformed"] = True
        inj.log(i, "*", "malformed_json_line", "valid_json", "truncated_line")
    if extra:
        ex = pd.DataFrame(extra)
        ex["_malformed"] = False
        d.transactions = pd.concat([df, ex], ignore_index=True)
    else:
        d.transactions = df


# ---------------------------------------------------------------------------
def inject_macro(cfg, d: Delivery, rng, notes):
    df = d.macro
    df["consumer_confidence_index"] = df["consumer_confidence_index"].astype(object)
    i = int(rng.integers(20, 100))
    row = df.iloc[i].to_dict()
    notes.append(dict(source_file="macroeconomic_monthly.csv", record_id=row["month"], field="month",
                      defect_type="duplicate_month", original_value=row["month"], injected_value="duplicate_row",
                      batch_id=BATCH_IDS[0]))
    j = int(rng.integers(20, 100))
    while j == i:
        j = int(rng.integers(20, 100))
    notes.append(dict(source_file="macroeconomic_monthly.csv", record_id=df["month"].iat[j],
                      field="consumer_confidence_index", defect_type="missing_optional_indicator",
                      original_value=df["consumer_confidence_index"].iat[j], injected_value=None, batch_id=BATCH_IDS[0]))
    df.at[j, "consumer_confidence_index"] = None
    d.macro = pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def inject_all(cfg, ref, d: Delivery) -> pd.DataFrame:
    rng = np.random.default_rng([cfg.seed, 41])
    notes = d.notes  # late / corrected entries already present
    inject_customers(cfg, d, rng, notes)
    inject_applications(cfg, ref, d, rng, notes)
    inject_repayments(cfg, d, rng, notes)
    inject_transactions(cfg, d, rng, notes)
    inject_macro(cfg, d, rng, notes)
    man = pd.DataFrame(notes, columns=["source_file", "record_id", "field", "defect_type", "original_value",
                                       "injected_value", "batch_id"])
    return man
