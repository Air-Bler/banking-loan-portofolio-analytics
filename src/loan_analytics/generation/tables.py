"""Turn the raw simulation output into clean-truth source tables.

Clean truth = internally consistent records *before* any controlled defect is
injected. Delivery batch is derived from the moment a record is recorded in the
source system (``updated_at`` / event time), not from its business date.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .behaviour import settle_date
from .config import GenConfig
from .customers import EMP, CustomerWorld
from .histories import SimOutput
from .reference import Reference
from .util import det_secs, iso, ts


def batch_of(o: int, cutoffs) -> int:
    for j, c in enumerate(cutoffs):
        if o <= c:
            return j
    return len(cutoffs) - 1


# ---------------------------------------------------------------------------
def build_applications(cfg: GenConfig, ref: Reference, world: CustomerWorld, sim: SimOutput):
    apps = sim.apps
    order = sorted(range(len(apps)), key=lambda g: (apps[g]["app_o"], apps[g]["cust"], apps[g]["seq"]))
    num = np.zeros(len(apps), dtype=np.int64)
    for rank, g in enumerate(order):
        num[g] = rank + 1
    bcodes, pcodes = ref.branch_codes, ref.product_codes
    rows = []
    for g in order:
        a = apps[g]
        rows.append((
            f"LA{num[g]:06d}", f"CU{a['cust'] + 1:06d}", bcodes[a["branch"]], pcodes[a["prod"]],
            iso(a["app_o"]), iso(a["dec_o"]) if a["dec_o"] is not None else None, a["status"],
            a["req"], a["appr"], "EUR", a["term"], a["rate"], a["score"], a["mdebt"], a["inc"],
            EMP[a["emp"]], a["exp"], a["consent"], a["manual"], ts(a["upd_o"], a["upd_s"]),
            a["channel"], a["app_o"], a["upd_o"], a["cust"], g,
        ))
    cols = ["application_id", "customer_id", "branch_code", "product_code", "application_date",
            "decision_date", "status", "requested_amount", "approved_amount", "currency", "term_months",
            "interest_rate", "risk_score", "monthly_debt", "annual_income_at_application",
            "employment_status_at_application", "declared_monthly_expenses", "consent_flag",
            "manual_review", "updated_at", "channel", "_app_o", "_rec_o", "_cust_i", "_gi"]
    df = pd.DataFrame(rows, columns=cols)
    df["_batch"] = [batch_of(int(o), cfg.cutoff_ords) for o in df["_rec_o"]]
    return df, num


# ---------------------------------------------------------------------------
def build_repayments(cfg: GenConfig, sim: SimOutput, app_num: np.ndarray):
    """Return (versions_df, installment_index) where versions_df holds every delivered
    version of every installment row (final states plus month-end open snapshots)."""
    cut = cfg.cutoff_ords
    inst = sorted(sim.inst, key=lambda t: (app_num[t[0]], t[1]))
    rows = []
    rid_of: dict = {}
    for n, (gi, k, due, pr, it, tot, pays) in enumerate(inst):
        rid = f"RP{n + 1:07d}"
        rid_of[(gi, k)] = rid
        appid = f"LA{app_num[gi]:06d}"
        settle = settle_date(list(pays), tot)
        vers = []
        if settle is not None:
            jf = batch_of(settle, cut)
            lag = 1 if (gi + k) % 3 == 0 else 0
            rec = min(settle + lag, cut[jf])
            for j in range(jf):
                if due <= cut[j] < settle:
                    vers.append((j, cut[j], False))
            vers.append((jf, rec, True))
        else:
            jf = next(j for j, c in enumerate(cut) if due <= c)
            vers.append((jf, cut[jf], False))
            if jf < len(cut) - 1:
                vers.append((len(cut) - 1, cut[-1], False))
        for (j, rec, final) in vers:
            if final:
                paid_pays = pays
                ref_o = None
            else:
                paid_pays = tuple(p for p in pays if p[0] <= rec)
                ref_o = rec
            paid = round(sum(a for _, a in paid_pays), 2)
            if final:
                pdate = settle
                status = "ON_TIME" if settle <= due else "LATE"
                dpd = max(0, settle - due)
                paid = tot
                secs = det_secs(gi, k)
                upd = ts(rec, secs)
            else:
                pdate = paid_pays[-1][0] if paid_pays else None
                status = "PARTIAL" if paid > 0 else "MISSED"
                dpd = max(0, rec - due)
                upd = ts(rec, 82800 + (gi * 13 + k) % 3000)
            int_paid = round(min(paid, it), 2)
            prin_paid = round(paid - int_paid, 2)
            rows.append((rid, appid, k, iso(due), pr, it, tot,
                         iso(pdate) if pdate is not None else None,
                         prin_paid, int_paid, paid, status, dpd, "EUR", upd, j, rec, gi, due,
                         pdate if pdate is not None else -1))
    cols = ["repayment_id", "application_id", "installment_number", "due_date", "principal_due",
            "interest_due", "total_due", "payment_date", "principal_paid", "interest_paid",
            "total_paid", "payment_status", "days_past_due", "currency", "updated_at",
            "_batch", "_rec_o", "_gi", "_due_o", "_pay_o"]
    df = pd.DataFrame(rows, columns=cols)
    return df, rid_of


# ---------------------------------------------------------------------------
def _athens_offset_hours(o: int) -> int:
    d = date.fromordinal(o)
    # EU DST: last Sunday of March .. last Sunday of October
    def last_sunday(y, m):
        nxt = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        return nxt - timedelta(days=(nxt.weekday() + 1) % 7)
    return 3 if last_sunday(d.year, 3) <= d < last_sunday(d.year, 10) else 2


def build_transactions(cfg: GenConfig, sim: SimOutput, app_num: np.ndarray, rid_of: dict):
    rng = np.random.default_rng([cfg.seed, 21])
    cut = cfg.cutoff_ords
    # ---- loan repayment events -------------------------------------------------
    l_gi, l_k, l_o, l_amt, l_cust = [], [], [], [], []
    apps = sim.apps
    for (gi, k, due, pr, it, tot, pays) in sim.inst:
        for (o, a) in pays:
            l_gi.append(gi); l_k.append(k); l_o.append(o); l_amt.append(a); l_cust.append(apps[gi]["cust"])
    nl = len(l_gi)
    l_secs = rng.integers(6 * 3600, 21 * 3600, nl)
    l_year = np.array([date.fromordinal(o).year for o in l_o]) if nl else np.array([])
    chan_pool = np.array(["DIRECT_DEBIT", "ONLINE", "MOBILE", "BRANCH", "STANDING_ORDER"])
    pdig = np.clip(0.05 + 0.04 * (l_year - 2016), 0.05, 0.45) if nl else np.array([])
    u = rng.random(nl)
    t_br = 0.08
    t_so = t_br + 0.12
    t_on = t_so + 0.04 + 0.20 * pdig
    t_mob = t_on + 0.02 + 0.25 * pdig
    ch_idx = np.zeros(nl, dtype=int)            # 0 = DIRECT_DEBIT (default)
    ch_idx[u < t_mob] = 2
    ch_idx[u < t_on] = 1
    ch_idx[u < t_so] = 4
    ch_idx[u < t_br] = 3
    l_chan = chan_pool[ch_idx]
    l_app = np.array([f"LA{app_num[g]:06d}" for g in l_gi])
    l_rid = np.array([rid_of[(g, k)] for g, k in zip(l_gi, l_k)])
    l_acc = np.array([f"LN{app_num[g]:06d}" for g in l_gi])
    l_ver = np.where(l_year >= 2024, "2.4", np.where(l_year >= 2021, "2.3", "2.1")) if nl else np.array([])

    loan_df = pd.DataFrame({
        "event_type": "LOAN_REPAYMENT", "_o": l_o, "_secs": l_secs, "_cust_i": l_cust,
        "loan_account": l_acc, "application_id": l_app, "repayment_id": l_rid,
        "current_account": None, "amount": np.array(l_amt, dtype=float), "channel": l_chan,
        "direction": "DEBIT", "system": "core-banking", "version": l_ver,
    })

    # ---- non-loan events ----------------------------------------------------------
    tx = sim.tx
    if tx:
        o_, s_, et_, c_, a_, ch_, dr_, sy_ = zip(*tx)
        years = np.array([date.fromordinal(o).year for o in o_])
        nonloan = pd.DataFrame({
            "event_type": et_, "_o": o_, "_secs": s_, "_cust_i": c_,
            "loan_account": None, "application_id": None, "repayment_id": None,
            "current_account": [f"AC{c + 1:06d}" for c in c_], "amount": np.array(a_, dtype=float),
            "channel": ch_, "direction": dr_, "system": sy_,
            "version": np.where(years >= 2024, "2.4", np.where(years >= 2021, "2.3", "2.1")),
        })
        df = pd.concat([loan_df, nonloan], ignore_index=True)
    else:
        df = loan_df
    df["customer_id"] = [f"CU{c + 1:06d}" for c in df["_cust_i"]]
    df["currency"] = "EUR"

    # ---- time handling: UTC 'Z' for most, local offset for ~15% -----------------------
    offs = {}
    for o in set(df["_o"].tolist()):
        offs[o] = _athens_offset_hours(o)
    off = np.array([offs[o] for o in df["_o"]])
    utc_key = df["_o"].to_numpy() * 86400 + df["_secs"].to_numpy() - off * 3600
    order = np.lexsort((np.arange(len(df)), df["_cust_i"].to_numpy(), utc_key))
    df = df.iloc[order].reset_index(drop=True)
    off = off[order]
    utc_key = utc_key[order]
    df["event_id"] = [f"EV{n + 1:09d}" for n in range(len(df))]
    local_flag = (np.arange(len(df)) * 2654435761 % 100) < 15
    times = []
    for n in range(len(df)):
        if local_flag[n]:
            o, s = int(df["_o"].iat[n]), int(df["_secs"].iat[n])
            times.append(ts(o, s) + f"+{off[n]:02d}:00")
        else:
            k = int(utc_key[n])
            o, s = divmod(k, 86400)
            times.append(ts(o, s) + "Z")
    df["event_time"] = times
    df["_batch"] = [batch_of(int(o), cut) for o in df["_o"]]
    cols = ["event_id", "event_type", "event_time", "customer_id", "loan_account", "application_id",
            "repayment_id", "current_account", "amount", "currency", "channel", "direction", "system",
            "version", "_o", "_batch", "_cust_i"]
    return df[cols]
