"""Delivery batches: split clean truth into four ingestion deliveries.

 * a batch is an ingestion delivery, not a business-date partition;
 * customers are re-delivered when their source attributes genuinely change;
 * a controlled number of records arrive late (older business date, later batch);
 * a controlled number of records are corrected (an earlier delivered value was
   wrong and a later delivery of the same key carries the right one).
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import BATCH_IDS, GenConfig
from .customers import EMP, CustomerWorld
from .util import det_secs, iso, ts
from .tables import batch_of


@dataclass
class Delivery:
    customers: pd.DataFrame
    applications: pd.DataFrame
    repayments: pd.DataFrame
    transactions: pd.DataFrame
    macro: pd.DataFrame
    branches: pd.DataFrame
    products: pd.DataFrame
    notes: list = field(default_factory=list)      # late / corrected manifest rows
    counts: dict = field(default_factory=dict)


def _note(notes, source, rid, fld, dtype, orig, inj, batch):
    notes.append(dict(source_file=source, record_id=rid, field=fld, defect_type=dtype,
                      original_value=orig, injected_value=inj, batch_id=BATCH_IDS[batch]))


def _window(cut, k):
    return (cut[k - 1] + 1, cut[k])


# ---------------------------------------------------------------------------
def customer_deliveries(cfg: GenConfig, world: CustomerWorld, first_rec: dict, rng, notes):
    cut = cfg.cutoff_ords
    n = world.n
    b = world.df
    email0, phone0 = b["email"].tolist(), b["phone"].tolist()
    cols = {c: b[c].tolist() for c in b.columns}

    def upd_at(i, hi):
        created = int(world.created_o[i])
        ev = world.ev_o[i]
        idx = bisect.bisect_right(ev, hi) - 1
        upd = created
        if idx >= 1:
            upd = max(upd, ev[idx])
        cc = world.contact_change.get(i)
        if cc and cc[0] <= hi:
            upd = max(upd, cc[0])
        return upd

    # ---- decide late arrivals (customers created near a cutoff, delivered one batch later)
    late_to: dict = {}
    for i in range(n):
        created = int(world.created_o[i])
        nb = batch_of(created, cut)
        if nb >= 3 or created <= cut[nb] - 45 or created > cut[nb]:
            continue
        if upd_at(i, cut[nb + 1]) != created or first_rec.get(i, 10 ** 9) <= cut[nb]:
            continue
        if rng.random() < cfg.late_share_customers:
            late_to[i] = nb + 1

    rows = []
    for k in range(4):
        lo, hi = (-1, cut[0]) if k == 0 else (cut[k - 1], cut[k])
        for i in range(n):
            created = int(world.created_o[i])
            if created > hi:
                break
            upd = upd_at(i, hi)
            forced = None
            if i in late_to:
                if late_to[i] == k:
                    forced = int(rng.integers(lo + 1, hi + 1))
                elif k < late_to[i]:
                    continue
            if k > 0 and forced is None and upd <= lo:
                continue
            if forced is not None:
                upd = forced
            inc, emp, est = world.state_at(i, hi)
            email, phone = email0[i], phone0[i]
            cc = world.contact_change.get(i)
            if cc and cc[0] <= hi:
                email, phone = cc[1], cc[2]
            ca = cols["created_at"][i]
            ua = ca if upd == created else ts(upd, det_secs(i, k + 1))
            rows.append((cols["customer_id"][i], cols["first_name"][i], cols["last_name"][i], email, phone,
                         cols["date_of_birth"][i], cols["segment"][i], inc, cols["household_id"][i],
                         EMP[emp], iso(est) if est > 0 else None, ca, ua, k, i, False, upd))
            if forced is not None:
                _note(notes, "customers.csv", cols["customer_id"][i], "delivery", "late_arriving_record",
                      f"{BATCH_IDS[k - 1]}", f"{BATCH_IDS[k]}", k)
    cn = ["customer_id", "first_name", "last_name", "email", "phone", "date_of_birth", "segment",
          "annual_income", "household_id", "employment_status", "employment_start_date", "created_at",
          "updated_at", "_batch", "_cust_i", "_protect", "_rec_o"]
    df = pd.DataFrame(rows, columns=cn)

    # ---- corrections: wrong value delivered in batch_001, right value in a later batch
    cands = []
    seen_later = set(df.loc[df["_batch"] > 0, "_cust_i"])
    for idx in np.where(df["_batch"].to_numpy() == 0)[0]:
        i = int(df["_cust_i"].iat[idx])
        if i not in seen_later and int(df["_rec_o"].iat[idx]) <= cut[0] - 20:
            cands.append(int(idx))
    n_corr = int(round(len(cands) * cfg.correction_share_customers))
    chosen = rng.choice(len(cands), size=min(n_corr, len(cands)), replace=False) if cands else []
    new_rows = []
    for c in sorted(int(x) for x in chosen):
        idx = cands[c]
        row = df.iloc[idx].to_dict()
        kk = int(rng.integers(1, 4))
        lo, hi = _window(cut, kk)
        truth = dict(row)
        truth["_batch"] = kk
        o = int(rng.integers(lo, hi + 1))
        truth["updated_at"] = ts(o, det_secs(row["_cust_i"], 9))
        truth["_rec_o"] = o
        truth["_protect"] = True
        r = rng.random()
        if r < 0.6:
            wrong = float(round(row["annual_income"] * rng.uniform(1.05, 1.22) / 10) * 10)
            df.at[idx, "annual_income"] = wrong
            fld, orig, inj = "annual_income", row["annual_income"], wrong
        elif r < 0.8:
            ph = list(row["phone"])
            pos = [p for p, ch in enumerate(ph) if ch.isdigit()]
            j = pos[-3]
            ph[j], ph[pos[-2]] = ph[pos[-2]], ph[j]
            wrong = "".join(ph)
            if wrong == row["phone"]:
                wrong = row["phone"][:-1] + str((int(row["phone"][-1]) + 1) % 10)
            df.at[idx, "phone"] = wrong
            fld, orig, inj = "phone", row["phone"], wrong
        else:
            wrong = "SELF_EMPLOYED" if row["employment_status"] == "EMPLOYED" else "EMPLOYED"
            df.at[idx, "employment_status"] = wrong
            fld, orig, inj = "employment_status", row["employment_status"], wrong
        df.at[idx, "_protect"] = True
        new_rows.append(truth)
        _note(notes, "customers.csv", row["customer_id"], fld, "wrong_value_corrected_later", orig, inj, 0)
        _note(notes, "customers.csv", row["customer_id"], fld, "correction_record", inj, orig, kk)
    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    return df


# ---------------------------------------------------------------------------
def application_deliveries(cfg: GenConfig, apps: pd.DataFrame, rng, notes):
    cut = cfg.cutoff_ords
    df = apps.copy()
    df["_protect"] = False
    decided = df["status"].isin(["APPROVED", "REJECTED", "WITHDRAWN"]).to_numpy()
    # ---- late arrivals
    for k in (1, 2, 3):
        lo, hi = _window(cut, k)
        m = ((df["_batch"] == k - 1) & decided & (df["_rec_o"] > cut[k - 1] - 14)).to_numpy()
        idxs = np.where(m)[0]
        pick = idxs[rng.random(len(idxs)) < cfg.late_share_applications]
        for idx in pick:
            o = int(rng.integers(lo, hi + 1))
            df.at[idx, "_batch"] = k
            df.at[idx, "_rec_o"] = o
            df.at[idx, "updated_at"] = ts(o, det_secs(int(df["_gi"].iat[idx]), 5))
            _note(notes, "loan_applications.csv", df["application_id"].iat[idx], "delivery",
                  "late_arriving_record", BATCH_IDS[k - 1], BATCH_IDS[k], k)
    # ---- corrections
    c_idx = np.where(((df["_batch"] == 0) & decided & (df["_rec_o"] <= cut[0] - 20)).to_numpy())[0]
    n_corr = int(round(len(c_idx) * cfg.correction_share_applications))
    chosen = rng.choice(len(c_idx), size=min(n_corr, len(c_idx)), replace=False) if len(c_idx) else []
    new_rows = []
    for c in sorted(int(x) for x in chosen):
        idx = int(c_idx[c])
        row = df.iloc[idx].to_dict()
        kk = int(rng.integers(1, 4))
        lo, hi = _window(cut, kk)
        o = int(rng.integers(lo, hi + 1))
        truth = dict(row)
        truth["_batch"] = kk
        truth["_rec_o"] = o
        truth["updated_at"] = ts(o, det_secs(int(row["_gi"]), 7))
        truth["_protect"] = True
        if rng.random() < 0.5:
            fld = "declared_monthly_expenses"
            wrong = float(max(round(row[fld] * rng.uniform(0.55, 0.80) / 10) * 10, 50))
        else:
            fld = "monthly_debt"
            wrong = round(row[fld] * rng.uniform(0.50, 0.85), 2)
        df.at[idx, fld] = wrong
        df.at[idx, "_protect"] = True
        new_rows.append(truth)
        _note(notes, "loan_applications.csv", row["application_id"], fld, "wrong_value_corrected_later", row[fld], wrong, 0)
        _note(notes, "loan_applications.csv", row["application_id"], fld, "correction_record", wrong, row[fld], kk)
    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    return df


# ---------------------------------------------------------------------------
def transaction_deliveries(cfg: GenConfig, tx: pd.DataFrame, rng, notes):
    cut = cfg.cutoff_ords
    df = tx.copy()
    df["_protect"] = False
    nonloan = (df["event_type"] != "LOAN_REPAYMENT").to_numpy()
    for k in (1, 2, 3):
        m = ((df["_batch"] == k - 1).to_numpy() & nonloan & (df["_o"].to_numpy() > cut[k - 1] - 14))
        idxs = np.where(m)[0]
        pick = idxs[rng.random(len(idxs)) < cfg.late_share_transactions]
        for idx in pick:
            df.at[idx, "_batch"] = k
            _note(notes, "transactions.json", df["event_id"].iat[idx], "delivery", "late_arriving_record",
                  BATCH_IDS[k - 1], BATCH_IDS[k], k)
    c_idx = np.where(((df["_batch"] == 0).to_numpy()) & ((df["_o"].to_numpy() <= cut[0] - 20)))[0]
    n_corr = int(round(len(c_idx) * cfg.correction_share_transactions))
    chosen = rng.choice(len(c_idx), size=min(n_corr, len(c_idx)), replace=False) if len(c_idx) else []
    new_rows = []
    for c in sorted(int(x) for x in chosen):
        idx = int(c_idx[c])
        row = df.iloc[idx].to_dict()
        kk = int(rng.integers(1, 4))
        truth = dict(row)
        truth["_batch"] = kk
        truth["version"] = "2.4"
        truth["_protect"] = True
        wrong = round(float(row["amount"]) * float(rng.choice([0.1, 1.5, 2.0, 10.0])), 2)
        df.at[idx, "amount"] = wrong
        df.at[idx, "_protect"] = True
        new_rows.append(truth)
        _note(notes, "transactions.json", row["event_id"], "payment.amount", "wrong_value_corrected_later", row["amount"], wrong, 0)
        _note(notes, "transactions.json", row["event_id"], "payment.amount", "correction_record", wrong, row["amount"], kk)
    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    return df


# ---------------------------------------------------------------------------
def macro_deliveries(cfg: GenConfig, macro_df: pd.DataFrame):
    df = macro_df.copy()
    ym = df["month"].tolist()
    cut = cfg.batch_cutoffs
    batch = []
    for m in ym:
        y, mo = int(m[:4]), int(m[5:7])
        if (y, mo) <= (cut[0].year, cut[0].month):
            batch.append(0)
        else:
            batch.append(mo - 9)  # Oct -> 1, Nov -> 2, Dec -> 3
    df["_batch"] = batch
    df["_protect"] = False
    return df


def build_delivery(cfg: GenConfig, ref, world, macro, apps, repayments, transactions) -> Delivery:
    rng = np.random.default_rng([cfg.seed, 31])
    notes: list = []
    first_rec: dict = {}
    for ci, ro in zip(apps["_cust_i"].tolist(), apps["_rec_o"].tolist()):
        if ci not in first_rec or ro < first_rec[ci]:
            first_rec[ci] = ro
    cust = customer_deliveries(cfg, world, first_rec, rng, notes)
    app = application_deliveries(cfg, apps, rng, notes)
    rep = repayments.copy()
    rep["_protect"] = False
    tx = transaction_deliveries(cfg, transactions, rng, notes)
    mac = macro_deliveries(cfg, macro.df)
    br = ref.branches.copy()
    br["_batch"] = 0
    br["_protect"] = False
    pr = ref.products.copy()
    pr["_batch"] = 0
    pr["_protect"] = False
    return Delivery(customers=cust, applications=app, repayments=rep, transactions=tx, macro=mac,
                    branches=br, products=pr, notes=notes)
