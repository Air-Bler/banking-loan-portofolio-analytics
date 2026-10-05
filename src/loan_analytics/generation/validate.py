"""Validation of the clean truth and the full statistical generation report.

All behavioural diagnostics are computed from *exported observable* columns only
(no latent generator state), using as-of-snapshot reconstruction.
"""
from __future__ import annotations

import bisect
import math
from datetime import date

import numpy as np
import pandas as pd

from .config import BATCH_IDS, GenConfig

FORBIDDEN_COLUMNS = {"future_delinquency", "will_default", "future_default", "latent_default_probability",
                     "hidden_stress", "future_income_drop", "future_payment_status", "resil", "stress"}
INF = 10 ** 9


# ---------------------------------------------------------------------------
def final_installments(rep: pd.DataFrame) -> pd.DataFrame:
    """Latest version of every installment (state at 2025-12-31)."""
    r = rep.sort_values(["repayment_id", "_rec_o", "_batch"], kind="mergesort")
    return r.drop_duplicates("repayment_id", keep="last").reset_index(drop=True)


def q(s, probs=(0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0)) -> dict:
    s = pd.Series(s).dropna().astype(float)
    if len(s) == 0:
        return {}
    return {f"p{int(p * 100)}": round(float(s.quantile(p)), 3) for p in probs}


def dist(s, top=None) -> dict:
    vc = pd.Series(s).value_counts(dropna=False)
    if top:
        vc = vc.head(top)
    n = vc.sum()
    return {str(k): {"n": int(v), "share": round(float(v) / n, 4)} for k, v in vc.items()}


def auc(score, y) -> float:
    score = np.asarray(score, float)
    y = np.asarray(y, bool)
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = pd.Series(score).rank().to_numpy()
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def logistic_fit(X, y, l2=1.0, iters=30):
    n, p = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(p + 1)
    for _ in range(iters):
        z = Xb @ w
        mu = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        W = mu * (1 - mu) + 1e-9
        g = Xb.T @ (mu - y) + l2 * np.r_[0, w[1:]]
        H = (Xb * W[:, None]).T @ Xb + l2 * np.diag(np.r_[0, np.ones(p)])
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-7:
            break
    return w


def logistic_predict(w, X):
    z = np.hstack([np.ones((len(X), 1)), X]) @ w
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


# ---------------------------------------------------------------------------
def validate_clean(cfg: GenConfig, ref, world, apps, rep, tx, macro) -> list:
    checks = []

    def chk(name, cond, detail=""):
        checks.append({"check": name, "passed": bool(cond), "detail": str(detail)})

    fin = final_installments(rep)
    cust_ids = set(world.df["customer_id"])
    chk("customers.customer_id unique", world.df["customer_id"].is_unique)
    chk("applications.application_id unique", apps["application_id"].is_unique)
    chk("repayments.repayment_id unique (final rows)", fin["repayment_id"].is_unique)
    chk("transactions.event_id unique", tx["event_id"].is_unique)
    chk("applications.customer_id FK", apps["customer_id"].isin(cust_ids).all())
    chk("applications.branch_code FK", apps["branch_code"].isin(ref.branch_codes).all())
    chk("applications.product_code FK", apps["product_code"].isin(ref.product_codes).all())
    created = world.created_o[apps["_cust_i"].to_numpy()]
    chk("customer.created_at <= application_date", (created <= apps["_app_o"].to_numpy()).all())
    opened = {r.branch_code: pd.Timestamp(r.opened_date).toordinal() for r in ref.branches.itertuples()}
    chk("branch.opened_date <= application_date",
        (apps["branch_code"].map(opened).to_numpy() <= apps["_app_o"].to_numpy()).all())
    dec = apps[apps["decision_date"].notna()]
    dd = (pd.to_datetime(dec["decision_date"]) - pd.to_datetime(dec["application_date"])).dt.days
    chk("application_date <= decision_date", (dd >= 0).all())
    ud = (pd.to_datetime(apps["updated_at"].str[:10]) - pd.to_datetime(apps["application_date"])).dt.days
    chk("application_date <= updated_at", (ud >= 0).all())
    chk("pending <=> null decision_date",
        (apps["status"].isin(["SUBMITTED", "UNDER_REVIEW"]) == apps["decision_date"].isna()).all())
    pr = ref.products.set_index("product_code")
    mn, mx = apps["product_code"].map(pr["min_amount"]), apps["product_code"].map(pr["max_amount"])
    chk("requested_amount within product range", ((apps["requested_amount"] >= mn) & (apps["requested_amount"] <= mx)).all())
    tmn, tmx = apps["product_code"].map(pr["min_term_months"]), apps["product_code"].map(pr["max_term_months"])
    chk("term within product range", ((apps["term_months"] >= tmn) & (apps["term_months"] <= tmx)).all())
    ap = apps[apps["status"] == "APPROVED"]
    chk("approved: 0 < approved_amount <= requested", ((ap["approved_amount"] > 0) & (ap["approved_amount"] <= ap["requested_amount"])).all())
    chk("approved: interest_rate present in range", ap["interest_rate"].between(0.02, 0.22).all())
    nap = apps[apps["status"] != "APPROVED"]
    chk("non-approved: no approved_amount / rate", nap["approved_amount"].isna().all() and nap["interest_rate"].isna().all())
    chk("currency EUR only", (apps["currency"] == "EUR").all() and (fin["currency"] == "EUR").all() and (tx["currency"] == "EUR").all())
    chk("risk_score in 300..850", apps["risk_score"].between(300, 850).all())
    chk("consent_flag in Y/N", apps["consent_flag"].isin(["Y", "N"]).all())
    chk("monthly_debt >= 0 and expenses > 0", (apps["monthly_debt"] >= 0).all() and (apps["declared_monthly_expenses"] > 0).all())
    # repayments
    chk("repayments.application_id are approved applications", fin["application_id"].isin(set(ap["application_id"])).all())
    chk("total_due = principal_due + interest_due", ((fin["principal_due"] + fin["interest_due"] - fin["total_due"]).abs() < 0.011).all())
    chk("total_paid = principal_paid + interest_paid", ((fin["principal_paid"] + fin["interest_paid"] - fin["total_paid"]).abs() < 0.011).all())
    chk("0 <= total_paid <= total_due", ((fin["total_paid"] >= 0) & (fin["total_paid"] <= fin["total_due"] + 0.011)).all())
    settled = fin["payment_status"].isin(["ON_TIME", "LATE"])
    exp_dpd = np.maximum(0, fin["_pay_o"] - fin["_due_o"])
    chk("settled: dpd = max(0, payment_date - due_date)", (fin.loc[settled, "days_past_due"] == exp_dpd[settled]).all())
    chk("settled status consistent with dpd", ((fin.loc[settled, "payment_status"] == "ON_TIME") == (fin.loc[settled, "days_past_due"] == 0)).all())
    chk("open rows: PARTIAL/MISSED have dpd >= 0 and total_paid < total_due",
        ((fin.loc[~settled, "total_paid"] < fin.loc[~settled, "total_due"]).all()))
    g = fin.groupby("application_id")["installment_number"].agg(["min", "max", "count"])
    chk("installment numbers contiguous from 1", ((g["min"] == 1) & (g["max"] == g["count"])).all())
    first_due = fin[fin["installment_number"] == 1].set_index("application_id")["_due_o"]
    decd = pd.to_datetime(ap.set_index("application_id")["decision_date"]).map(lambda t: t.toordinal())
    chk("first installment due after decision", (first_due - decd.reindex(first_due.index) > 0).all())
    term = ap.set_index("application_id")["term_months"]
    full = g[g["max"] == term.reindex(g.index)].index
    sp = fin[fin["application_id"].isin(full)].groupby("application_id")["principal_due"].sum()
    chk("schedule-complete loans: scheduled principal = approved_amount",
        ((sp - ap.set_index("application_id")["approved_amount"].reindex(sp.index)).abs() < 0.5).all(),
        f"{len(full)} schedule-complete loans checked")
    lt_ = loan_table(cfg, apps, fin)
    po = lt_[lt_["paid_off"]]
    chk("paid-off loans have zero outstanding principal (|x|<0.5)", (po["outstanding"].abs() < 0.5).all(), f"{len(po)} paid-off loans")
    unres = lt_[lt_["schedule_complete"] & ~lt_["paid_off"]]
    chk("schedule-complete but unresolved loans keep positive outstanding principal", (unres["outstanding"] > 0.005).all(), f"{len(unres)} loans")
    chk("paid-off loans have no open (PARTIAL/MISSED) instalment", (po["n_open"] == 0).all())
    # transactions
    lt = tx[tx["event_type"] == "LOAN_REPAYMENT"]
    ev_sum = lt.groupby("repayment_id")["amount"].sum()
    paid = fin.set_index("repayment_id")["total_paid"]
    common = paid.index.intersection(ev_sum.index)
    chk("repayment total_paid = sum of payment events", ((paid.reindex(common) - ev_sum.reindex(common)).abs() < 0.011).all())
    chk("paid installments all have events", (paid[paid > 0].index.isin(ev_sum.index)).all())
    chk("transaction repayment_id FK", lt["repayment_id"].isin(set(fin["repayment_id"])).all())
    chk("transaction customer FK", tx["customer_id"].isin(cust_ids).all())
    chk("no forbidden/latent columns exported",
        not (FORBIDDEN_COLUMNS & (set(apps.columns) | set(fin.columns) | set(world.df.columns) | set(tx.columns))))
    chk("macro has 120 monthly rows", len(macro.df) == 120 and macro.df["month"].is_unique)
    chk("branches=12, products=5", len(ref.branches) == 12 and len(ref.products) == 5)
    return checks


# ---------------------------------------------------------------------------
def _dti_band(x):
    return pd.cut(x, [-1, 0.2, 0.35, 0.5, 100], labels=["<20%", "20-35%", "35-50%", ">50%"]).astype(str)


def _risk_band(s):
    return pd.cut(s, [0, 579, 669, 739, 799, 1000], labels=["300-579", "580-669", "670-739", "740-799", "800-850"]).astype(str)


def loan_table(cfg, apps, fin):
    ap = apps[apps["status"] == "APPROVED"].copy()
    # settlement date of fully settled instalments only (-1 for PARTIAL / MISSED)
    fin = fin.assign(_settle=np.where(fin["payment_status"].isin(["ON_TIME", "LATE"]), fin["_pay_o"], -1))
    agg = fin.groupby("application_id").agg(
        n_inst=("installment_number", "count"), last_k=("installment_number", "max"),
        first_due=("_due_o", "min"), last_due=("_due_o", "max"),
        max_dpd=("days_past_due", "max"), principal_paid=("principal_paid", "sum"),
        n_late=("payment_status", lambda s: int((s == "LATE").sum())),
        n_partial=("payment_status", lambda s: int((s == "PARTIAL").sum())),
        n_missed=("payment_status", lambda s: int((s == "MISSED").sum())),
        max_settle=("_settle", "max"))
    ap = ap.merge(agg, left_on="application_id", right_index=True, how="left")
    for c in ("n_inst", "n_late", "n_partial", "n_missed"):
        ap[c] = ap[c].fillna(0).astype(int)
    ap["ever30"] = (ap["max_dpd"].fillna(0) >= 30)
    # observable date on which the loan first reached 30+ DPD (due_date + 30 of its first such instalment)
    bad = fin[fin["days_past_due"] >= 30]
    first30 = (bad["_due_o"] + 30).groupby(bad["application_id"]).min()
    ap["first30_o"] = ap["application_id"].map(first30).fillna(INF)
    # schedule_complete: the final contractual instalment exists. NOT the same as paid off.
    ap["schedule_complete"] = (ap["last_k"].fillna(0) == ap["term_months"]) & (ap["n_inst"] == ap["term_months"])
    ap["n_open"] = ap["n_partial"] + ap["n_missed"]
    # paid_off: schedule complete AND every instalment fully settled (observed at 2025-12-31)
    ap["paid_off"] = ap["schedule_complete"] & (ap["n_open"] == 0)
    ap["paid_off_o"] = np.where(ap["paid_off"], ap["max_settle"].fillna(INF), INF)
    ap["principal_paid"] = ap["principal_paid"].fillna(0.0)
    ap["outstanding"] = ap["approved_amount"] - ap["principal_paid"]
    ap["dti"] = ap["monthly_debt"] / (ap["annual_income_at_application"] / 12.0)
    return ap


def mature_loans(loans: pd.DataFrame, h1: int) -> pd.DataFrame:
    """Strict observation-window criterion: >= 12 months since the first instalment fell due.
    Independent of the outcome (a loan is not admitted merely because it became 30+ DPD)."""
    return loans[loans["first_due"].fillna(INF) <= h1 - 365]


def prior_delinquency_flags(loans: pd.DataFrame) -> pd.Series:
    """True for a loan if ANOTHER loan of the same customer had already reached 30+ DPD
    (first_30dpd date <= this loan's application date). Uses observable dates only,
    never the other loan's eventual outcome."""
    flags = pd.Series(False, index=loans.index)
    for _, g in loans.groupby("_cust_i"):
        if len(g) < 2:
            continue
        f = g["first30_o"].to_numpy(float)
        a = g["_app_o"].to_numpy(float)
        for j in range(len(g)):
            others = np.delete(f, j)
            if (others <= a[j]).any():
                flags.loc[g.index[j]] = True
    return flags


def dpd_ageing_buckets(fin: pd.DataFrame) -> dict:
    """Ageing of OPEN (PARTIAL/MISSED) instalments at 30+ DPD as of the final state."""
    o = fin[~fin["payment_status"].isin(["ON_TIME", "LATE"]) & (fin["days_past_due"] >= 30)]
    labels = ["30-59", "60-89", "90-179", "180-365", "365+"]
    edges = [30, 60, 90, 180, 366, 10 ** 9]
    cat = pd.cut(o["days_past_due"], edges, right=False, labels=labels)
    per_loan = pd.cut(o.groupby("application_id")["days_past_due"].max(), edges, right=False, labels=labels)
    return {"note": "365+ means more than 365 days; bucket = DPD at 2025-12-31 of open instalments (rows are never written off)",
            "open_installments": {k: int(v) for k, v in cat.value_counts().reindex(labels).items()},
            "loans_by_max_open_dpd": {k: int(v) for k, v in per_loan.value_counts().reindex(labels).items()}}


def snapshot_diagnostics(cfg, ref, world, macro, apps, fin, loans) -> dict:
    """Monthly-style (quarterly here) loan snapshots with a 90-day forward 30+ DPD target.
    Uses only exported observable columns; right-censored snapshots are excluded."""
    H1 = cfg.h1
    ok_status = fin["payment_status"].isin(["ON_TIME", "LATE"]).to_numpy()
    pay_o = np.where(ok_status, fin["_pay_o"].to_numpy(), INF)
    fin2 = fin.assign(_settle=pay_o).sort_values(["application_id", "installment_number"], kind="mergesort")
    due_by = {a: (g["_due_o"].to_numpy(), g["_settle"].to_numpy()) for a, g in fin2.groupby("application_id")}
    prod_idx = {c: j for j, c in enumerate(ref.product_codes)}
    created = world.created_o
    unemp = dict(zip(macro.df["month"], macro.df["unemployment_rate"]))
    refr = dict(zip(macro.df["month"], macro.df["reference_rate"]))
    snaps = []
    t = date(2016, 12, 31)
    while t <= date(2025, 12, 31):
        snaps.append(t.toordinal())
        m = t.month + 3
        y = t.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        t = date.fromordinal(nxt.toordinal() - 1)
    feats, labels, tsnap, cens = [], [], [], 0
    lo = loans.set_index("application_id")
    for aid, (due, settle) in due_by.items():
        r = lo.loc[aid]
        term = int(r["term_months"])
        paid_off_o = int(r["paid_off_o"])
        sched_complete = bool(r["schedule_complete"])
        for t in snaps:
            idx = bisect.bisect_right(due, t)
            if idx == 0:
                continue
            if paid_off_o <= t:
                continue          # genuinely settled in full as of t -> closed, not a candidate
            if idx == len(due) and not sched_complete and t < H1:
                continue          # schedule was terminated early (no further instalments): not a candidate
            s = settle[:idx]
            d = due[:idx]
            dpd_asof = np.where(s <= t, np.maximum(0, s - d), t - d)
            overdue30 = ((s > t) & (t - d >= 30)).any()
            if overdue30:
                continue
            if t + 90 > H1:
                cens += 1
                continue
            reach = (due + 30 > t) & (due + 30 <= t + 90) & (settle - due >= 30)
            y = 1 if reach.any() else 0
            w = slice(max(0, idx - 6), idx)
            dw = dpd_asof[w]
            tenure = max(0.0, (int(r["_app_o"]) - int(created[int(r["_cust_i"])])) / 365.25)
            ym = date.fromordinal(t).strftime("%Y-%m")
            inc = float(r["annual_income_at_application"])
            amt = float(r["approved_amount"])
            feats.append([
                float(r["risk_score"]), float(r["dti"]), amt / inc, float(r["term_months"]), float(r["interest_rate"]),
                tenure, idx, float((dw > 0).sum()), float(dw.max()), float((dpd_asof > 0).sum()),
                float((s > t).sum()), unemp[ym], refr[ym], prod_idx[r["product_code"]]])
            labels.append(y)
            tsnap.append(t)
    X = np.array(feats)
    y = np.array(labels)
    ts_ = np.array(tsnap)
    out = {"note": "GENERATOR DIAGNOSTIC ONLY: quarterly snapshots, cheap signal check. The capstone ML phase "
                   "will build MONTHLY loan-level snapshots (target: 30+ DPD within the following 90 days, "
                   "right-censored windows excluded). This is not the final ML implementation.",
           "snapshot_dates": f"quarter-ends {date.fromordinal(snaps[0])}..{date.fromordinal(snaps[-1])}",
           "eligible_snapshots_labelled": int(len(y)), "right_censored_excluded": int(cens),
           "positives": int(y.sum()), "positive_rate": round(float(y.mean()), 4) if len(y) else None}
    if len(y) < 200 or y.sum() < 20:
        return out
    test_start = date(2023, 3, 31).toordinal()
    tr, te = ts_ < test_start, ts_ >= test_start
    out["train_snapshots"], out["test_snapshots"] = int(tr.sum()), int(te.sum())
    out["train_positives"], out["test_positives"] = int(y[tr].sum()), int(y[te].sum())
    out["test_positive_rate"] = round(float(y[te].mean()), 4)
    out["auc_risk_score_only_test(-score)"] = round(auc(-X[te, 0], y[te]), 4)
    out["auc_dti_only_test"] = round(auc(X[te, 1], y[te]), 4)
    out["auc_lti_only_test"] = round(auc(X[te, 2], y[te]), 4)

    def design(cols, onehot_product=True):
        M = X[:, cols]
        if onehot_product:
            P = np.eye(5)[X[:, 13].astype(int)][:, 1:]
            M = np.hstack([M, P])
        return M

    def fit_eval(cols, name):
        M = design(cols)
        mu, sd = M[tr].mean(0), M[tr].std(0) + 1e-9
        Z = (M - mu) / sd
        w = logistic_fit(Z[tr], y[tr])
        p = logistic_predict(w, Z[te])
        out[f"auc_{name}_test"] = round(auc(p, y[te]), 4)
        out[f"brier_{name}_test"] = round(float(np.mean((p - y[te]) ** 2)), 4)

    names = ["risk_score", "dti", "loan_to_income", "term", "interest_rate", "tenure", "instalments_due",
             "late_last6", "max_dpd_last6", "late_all", "open_overdue", "unemployment", "reference_rate"]
    out["single_feature_test_auc_max(a,1-a)"] = {
        names[j]: round(max(auc(X[te, j], y[te]), 1 - auc(X[te, j], y[te])), 4) for j in range(13)}
    fit_eval([0, 1, 2, 3, 4, 5, 11, 12], "origination_logit")
    fit_eval([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], "origination_plus_behaviour_logit")
    fit_eval([6, 7, 8, 9, 10], "behaviour_only_logit")
    return out


# ---------------------------------------------------------------------------
def build_report(cfg, ref, world, macro, sim, apps, rep, tx, delivery, manifest, counts, checks) -> dict:
    fin = final_installments(rep)
    loans = loan_table(cfg, apps, fin)
    H1 = cfg.h1
    rep_out: dict = {"seed": cfg.seed}

    # ---- counts ---------------------------------------------------------------------
    rep_out["counts"] = {
        "clean_truth": {"customers": len(world.df), "loan_applications": len(apps),
                        "repayment_installments": int(len(fin)), "repayment_versions_delivered": int(len(rep)),
                        "transaction_events": len(tx), "macro_rows": len(macro.df),
                        "branches": len(ref.branches), "products": len(ref.products)},
        "delivered_rows_per_batch": counts,
        "delivered_rows_total": {k: int(sum(c.get(k, 0) for c in counts.values())) for k in
                                 ("customers.csv", "loan_applications.csv", "repayments.csv", "transactions.json",
                                  "macroeconomic_monthly.csv", "branches.csv", "products.csv")},
        "unique_primary_ids": {"customers": int(world.df["customer_id"].nunique()),
                               "applications": int(apps["application_id"].nunique()),
                               "repayments": int(fin["repayment_id"].nunique()),
                               "events": int(tx["event_id"].nunique())},
        "date_ranges": {"application_date": [apps["application_date"].min(), apps["application_date"].max()],
                        "due_date": [fin["due_date"].min(), fin["due_date"].max()],
                        "event_time_local_date": [date.fromordinal(int(tx["_o"].min())).isoformat(), date.fromordinal(int(tx["_o"].max())).isoformat()],
                        "customer_created_at": [world.df["created_at"].min(), world.df["created_at"].max()]},
    }
    tot = sum(rep_out["counts"]["delivered_rows_total"].values())
    rep_out["counts"]["delivered_rows_grand_total"] = int(tot)

    # ---- customers ---------------------------------------------------------------------
    cdf = world.df
    age = (H1 - world.dob_o) / 365.25
    cyear = pd.Series([int(s[:4]) for s in cdf["created_at"]])
    rep_out["customers"] = {
        "age_quantiles_at_2025-12-31": q(age),
        "annual_income_quantiles_current": q(cdf["annual_income"]),
        "income_share_gt_100k": round(float((cdf["annual_income"] > 100000).mean()), 4),
        "income_ending_000_or_500_share": round(float((cdf["annual_income"] % 500 == 0).mean()), 4),
        "employment_distribution": dist(cdf["employment_status"]),
        "segment_distribution": dist(cdf["segment"]),
        "creation_cohorts": {str(k): int(v) for k, v in cyear.value_counts().sort_index().items()},
        "created_before_2016": int((world.created_o < cfg.h0).sum()),
        "household_null_share": round(float(cdf["household_id"].isna().mean()), 4),
        "household_shared_share": round(float(cdf["household_id"].dropna().duplicated(keep=False).mean()), 4),
        "greek_name_share_proxy": round(float(cdf["first_name"].isin(__import__("loan_analytics.generation.names", fromlist=["x"]).GR_MALE + __import__("loan_analytics.generation.names", fromlist=["x"]).GR_FEMALE).mean()), 4),
        "email_provider_mix": dist(cdf["email"].str.split("@").str[1]),
        "delivered_email_missing_or_invalid_rate": None,
        "customers_with_state_change_events": int(sum(1 for e in world.ev_o if len(e) > 1)),
        "applications_where_snapshot_income_differs_from_current": int(
            (apps["annual_income_at_application"].to_numpy() != cdf["annual_income"].to_numpy()[apps["_cust_i"].to_numpy()]).sum()),
    }
    dcu = delivery.customers
    bad_email = dcu["email"].isna() | ~dcu["email"].fillna("").str.match(r"^[^@\s]+@[^@\s,]+\.[A-Za-z]{2,}$")
    rep_out["customers"]["delivered_email_missing_or_invalid_rate"] = round(float(bad_email.mean()), 4)
    ph = dcu["phone"].fillna("")
    rep_out["customers"]["delivered_phone_nonstandard_or_missing_rate"] = round(float((~ph.str.match(r"^(\+30|0030)?(69\d{8}|2\d{9})$")).mean()), 4)

    # ---- applications ------------------------------------------------------------------------
    per_cust = apps.groupby("_cust_i").size()
    n_cust_with = len(per_cust)
    decided = apps[apps["status"].isin(["APPROVED", "REJECTED"])]
    dtime = (pd.to_datetime(decided["decision_date"]) - pd.to_datetime(decided["application_date"])).dt.days
    apps = apps.assign(dti=apps["monthly_debt"] / (apps["annual_income_at_application"] / 12.0),
                       year=apps["application_date"].str[:4])
    stat_dist = dist(apps["status"])
    appr_rate = float((decided["status"] == "APPROVED").mean())
    rep_out["applications"] = {
        "applications_per_customer": {"customers_with_>=1": int(n_cust_with), "customers_with_0": int(len(cdf) - n_cust_with),
                                      "distribution": {str(k): int(v) for k, v in per_cust.value_counts().sort_index().items()},
                                      "quantiles_among_applicants": q(per_cust)},
        "status_distribution": stat_dist,
        "approval_rate_approved_over_(approved+rejected)": round(appr_rate, 4),
        "manual_review_rate": round(float((apps["manual_review"] == "Y").mean()), 4),
        "manual_review_outcomes": dist(apps.loc[apps["manual_review"] == "Y", "status"]),
        "decision_time_days_quantiles_approved_rejected": q(dtime),
        "decision_time_mean_by_product": {k: round(float(v), 2) for k, v in dtime.groupby(decided["product_code"]).mean().items()},
        "decision_time_mean_manual_vs_auto": {k: round(float(v), 2) for k, v in dtime.groupby(decided["manual_review"]).mean().items()},
        "product_mix": dist(apps["product_code"]),
        "branch_mix": dist(apps["branch_code"]),
        "channel_mix": dist(apps["channel"]),
        "channel_mix_by_year_digital_share": {y: round(float(g["channel"].isin(["ONLINE", "MOBILE"]).mean()), 3) for y, g in apps.groupby("year")},
        "risk_score_quantiles": q(apps["risk_score"]),
        "dti_quantiles": q(apps["dti"]),
        "dti_band_distribution": dist(_dti_band(apps["dti"])),
        "requested_amount_quantiles": q(apps["requested_amount"]),
        "approved_amount_quantiles": q(apps["approved_amount"]),
        "partial_approval_share_of_approved": round(float((loans["approved_amount"] < loans["requested_amount"]).mean()), 4),
        "term_distribution_by_product": {p: dist(g["term_months"]) for p, g in apps.groupby("product_code")},
        "avg_interest_rate_by_product_year": {p: {y: round(float(v), 4) for y, v in g.groupby(g["application_date"].str[:4])["interest_rate"].mean().dropna().items()} for p, g in apps.groupby("product_code")},
        "approval_rate_by_risk_band": {k: round(float(v), 3) for k, v in decided.groupby(_risk_band(decided["risk_score"]))["status"].apply(lambda s: (s == "APPROVED").mean()).items()},
        "approval_rate_by_dti_band": {k: round(float(v), 3) for k, v in decided.assign(d=decided["monthly_debt"] / (decided["annual_income_at_application"] / 12)).groupby(_dti_band(decided["monthly_debt"] / (decided["annual_income_at_application"] / 12)))["status"].apply(lambda s: (s == "APPROVED").mean()).items()},
    }

    # ---- loans / repayments -------------------------------------------------------------------------
    st = fin["payment_status"]
    settled = st.isin(["ON_TIME", "LATE"])
    n_loans = len(loans)
    mature = mature_loans(loans, H1)
    # recovery: LATE/PARTIAL followed by >=3 consecutive ON_TIME
    fs = fin.sort_values(["application_id", "installment_number"])
    rec_cases = 0       # any late/partial/missed instalment followed by >=3 consecutive ON_TIME
    rec30_cases = 0     # a settled instalment that was 30+ DPD followed by >=3 consecutive ON_TIME
    for aid, g in fs.groupby("application_id"):
        s = g["payment_status"].tolist()
        dp = g["days_past_due"].tolist()
        seen_bad = seen30 = False
        run = run30 = 0
        hit = hit30 = False
        for x, dd_ in zip(s, dp):
            if x in ("LATE", "PARTIAL", "MISSED"):
                seen_bad, run = True, 0
                if x == "LATE" and dd_ >= 30:
                    seen30, run30 = True, 0
                elif seen30:
                    run30 = 0
            elif x == "ON_TIME":
                if seen_bad:
                    run += 1
                    hit = hit or run >= 3
                if seen30:
                    run30 += 1
                    hit30 = hit30 or run30 >= 3
        rec_cases += int(hit)
        rec30_cases += int(hit30)
    # simultaneous active loans: overlapping [first_due, last_due or term end]
    ends = loans["first_due"] + loans["term_months"] * 30.4
    ov_cust = 0
    for ci, g in loans.groupby("_cust_i"):
        if len(g) < 2:
            continue
        st_, en_ = g["first_due"].fillna(INF).to_numpy(), ends.loc[g.index].fillna(INF).to_numpy()
        order = np.argsort(st_)
        st_, en_ = st_[order], en_[order]
        ov_cust += int(any(st_[j + 1] < en_[:j + 1].max() for j in range(len(st_) - 1)))
    # prior delinquency strictly as of each later application: an EARLIER-OBSERVABLE 30+ DPD event
    pflag = prior_delinquency_flags(loans)
    prior_delinq_cust = int(loans.loc[pflag, "_cust_i"].nunique())
    rep_out["loans_repayments"] = {
        "approved_loans": int(n_loans),
        "installments_per_loan_quantiles": q(loans["n_inst"]),
        "loans_without_any_due_installment_yet": int((loans["n_inst"] == 0).sum()),
        "repayment_status_distribution_final_state": dist(st),
        "dpd_quantiles_settled": q(fin.loc[settled, "days_past_due"]),
        "installments_30plus_dpd": int((fin["days_past_due"] >= 30).sum()),
        "loan_level_ever_30plus_dpd": {
            "denominator": "approved loans whose first instalment fell due on or before 2024-12-31 (>= 12 months observable); a loan is never admitted because it experienced the outcome",
            "n_mature_loans": int(len(mature)), "n_30plus": int(mature["ever30"].sum()),
            "prevalence": round(float(mature["ever30"].mean()), 4),
            "prevalence_all_approved_loans": round(float(loans["ever30"].mean()), 4)},
        "open_installment_dpd_ageing": dpd_ageing_buckets(fin),
        "partial_installments_open": int((st == "PARTIAL").sum()),
        "missed_installments_open": int((st == "MISSED").sum()),
        "late_installments_settled": int((st == "LATE").sum()),
        "recovery_cases_loans_any_late_then_3_ontime": int(rec_cases),
        "recovery_cases_loans_after_30plus_dpd_then_3_ontime": int(rec30_cases),
        "loan_state_definitions": {
            "schedule_complete": "final contractual instalment (installment_number == term_months) exists",
            "paid_off": "schedule_complete AND every instalment fully settled (no PARTIAL/MISSED row) at 2025-12-31",
            "open": "approved loan that is not paid off (running, terminated early, or matured with unresolved debt)"},
        "schedule_complete_loans": int(loans["schedule_complete"].sum()),
        "paid_off_loans": int(loans["paid_off"].sum()),
        "schedule_complete_but_unresolved_loans": int((loans["schedule_complete"] & ~loans["paid_off"]).sum()),
        "outstanding_principal_eur_on_schedule_complete_unresolved_loans": round(float(loans.loc[loans["schedule_complete"] & ~loans["paid_off"], "outstanding"].sum()), 2),
        "open_loans_not_paid_off": int((~loans["paid_off"]).sum()),
        "customers_with_overlapping_loans": int(ov_cust),
        "customers_with_previous_delinquency_before_later_loan": int(prior_delinq_cust),
        "customers_with_multiple_loans": int((loans.groupby("_cust_i").size() > 1).sum()),
        "loans_of_repeat_borrowers_having_a_paid_off_loan": int(((loans.groupby("_cust_i")["paid_off"].transform("sum") > 0) & (loans.groupby("_cust_i")["_app_o"].transform("count") > 1)).sum()),
    }

    # ---- transactions --------------------------------------------------------------------------------
    nl = tx[tx["event_type"] != "LOAN_REPAYMENT"]
    borrowers = set(loans["_cust_i"])
    ev_per_cust = nl.groupby("_cust_i").size()
    rich = set(ev_per_cust[ev_per_cust >= 12].index)
    sal = set(tx.loc[tx["event_type"] == "SALARY_CREDIT", "_cust_i"])
    emp_borrowers = set(loans.loc[loans["employment_status_at_application"] == "EMPLOYED", "_cust_i"])
    rep_out["transactions"] = {
        "event_type_distribution": dist(tx["event_type"]),
        "events_per_customer_quantiles_all_events": q(tx.groupby("_cust_i").size()),
        "non_loan_events_per_borrower_quantiles": q(ev_per_cust.reindex(sorted(borrowers)).fillna(0)),
        "cash_flow_coverage_borrowers_with_>=12_non_loan_events": round(len(rich & borrowers) / max(1, len(borrowers)), 4),
        "borrowers_with_any_non_loan_event": round(len(set(ev_per_cust.index) & borrowers) / max(1, len(borrowers)), 4),
        "salary_credit_coverage_among_employed_borrowers": round(len(sal & emp_borrowers) / max(1, len(emp_borrowers)), 4),
        "amount_quantiles_by_type": {t: q(g["amount"]) for t, g in tx.groupby("event_type")},
        "channel_distribution_loan_repayments": dist(tx.loc[tx["event_type"] == "LOAN_REPAYMENT", "channel"]),
        "event_time_offset_mix": {"utc_Z": round(float(tx["event_time"].str.endswith("Z").mean()), 3), "local_offset": round(float((~tx["event_time"].str.endswith("Z")).mean()), 3)},
    }

    # ---- data quality ---------------------------------------------------------------------------------
    m = manifest
    defects = m[~m["defect_type"].isin(["late_arriving_record", "wrong_value_corrected_later", "correction_record"])]
    delivered = rep_out["counts"]["delivered_rows_total"]
    by_source = defects.groupby("source_file")["record_id"].nunique()
    rep_out["data_quality"] = {
        "defects_by_source": {k: int(v) for k, v in defects.groupby("source_file").size().items()},
        "defects_by_rule": {f"{s}|{r}": int(n) for (s, r), n in defects.groupby(["source_file", "defect_type"]).size().items()},
        "distinct_defective_records_by_source": {k: int(v) for k, v in by_source.items()},
        "share_of_delivered_rows_affected": {k: round(float(by_source.get(k, 0)) / max(1, delivered.get(k, 1)), 4) for k in delivered},
        "overall_share_of_delivered_rows_affected": round(float(by_source.sum()) / max(1, sum(delivered.values())), 4),
        "late_arriving_records": {k: int(v) for k, v in m[m["defect_type"] == "late_arriving_record"].groupby("source_file").size().items()},
        "corrected_records": {k: int(v) for k, v in m[m["defect_type"] == "correction_record"].groupby("source_file").size().items()},
        "orphan_repayments": int(defects[defects["defect_type"] == "orphan_application"].shape[0]),
        "duplicate_records": int(defects[defects["defect_type"].str.contains("duplicate")].shape[0]),
        "official_team2_defects_present": {
            "missing_consent": int((defects["defect_type"] == "missing_consent").sum()),
            "missing_status": int((defects["defect_type"] == "missing_status").sum()),
            "inconsistent_amounts": int(defects["defect_type"].isin(["approved_gt_requested", "requested_outside_product_range", "amount_sum_inconsistent", "nonpositive_requested_amount"]).sum()),
            "impossible_dates": int(defects["defect_type"].isin(["decision_before_application", "impossible_payment_date", "impossible_dob", "impossible_timestamp"]).sum()),
            "duplicate_applications": int(defects["defect_type"].isin(["duplicate_application_rekeyed", "exact_duplicate_row"]).sum()),
            "orphan_repayments": int((defects["defect_type"] == "orphan_application").sum()),
            "out_of_range_risk_scores": int((defects["defect_type"] == "risk_score_out_of_range").sum()),
        },
    }

    # ---- decade coverage evidence -------------------------------------------------------------------------------
    app_year = apps["application_date"].str[:4]
    ev_year = pd.Series([date.fromordinal(int(o)).year for o in tx["_o"]])
    due_year = fin["due_date"].str[:4]
    exp_months = [f"{y}-{m:02d}" for y in range(2016, 2026) for m in range(1, 13)]
    present = set(macro.df["month"])
    ev_last = int(tx["_o"].max())
    rep_out["history_coverage"] = {
        "applications_by_year": {k: int(v) for k, v in app_year.value_counts().sort_index().items()},
        "transaction_events_by_year": {str(k): int(v) for k, v in ev_year.value_counts().sort_index().items()},
        "repayment_instalments_due_by_year": {k: int(v) for k, v in due_year.value_counts().sort_index().items()},
        "applications_by_month_2025_H2": {k: int(v) for k, v in apps.loc[apps["application_date"] >= "2025-07-01", "application_date"].str[:7].value_counts().sort_index().items()},
        "latest_application_date": apps["application_date"].max(),
        "latest_event_date": date.fromordinal(ev_last).isoformat(),
        "latest_instalment_due_date": fin["due_date"].max(),
        "macro_months_expected": 120, "macro_months_present": len(present & set(exp_months)),
        "macro_missing_months": sorted(set(exp_months) - present),
    }

    # ---- mandatory KPIs and slicing ---------------------------------------------------------------------------
    cust_info = pd.DataFrame({"customer_id": cdf["customer_id"], "created_o": world.created_o})
    reg = dict(zip(ref.branches["branch_code"], ref.branches["region"]))
    fam = dict(zip(ref.products["product_code"], ref.products["product_family"]))
    a2 = apps.assign(region=apps["branch_code"].map(reg), family=apps["product_code"].map(fam),
                     segment=cdf["segment"].to_numpy()[apps["_cust_i"].to_numpy()],
                     risk_band=_risk_band(apps["risk_score"]), dti_band=_dti_band(apps["dti"]),
                     new_existing=np.where(apps["_app_o"].to_numpy() - world.created_o[apps["_cust_i"].to_numpy()] <= 365, "new", "existing"))
    dec2 = a2[a2["status"].isin(["APPROVED", "REJECTED"])]
    open_delinq = fin[(~fin["payment_status"].isin(["ON_TIME", "LATE"])) & (fin["days_past_due"] >= 30)]["application_id"].nunique()
    active_loans = int((~loans["paid_off"]).sum())      # open = not paid off (includes matured-unresolved)
    kpis = {
        "applications": int(len(apps)),
        "requested_amount_eur": round(float(apps["requested_amount"].sum()), 2),
        "approval_rate": round(appr_rate, 4),
        "avg_decision_time_days": round(float(dtime.mean()), 3),
        "dti_band_counts": dist(a2["dti_band"]),
        "delinquency_rate_loans_30plus_dpd_open_at_2025-12-31": round(open_delinq / max(1, active_loans), 4),
        "outstanding_balance_eur_at_2025-12-31": round(float(loans["outstanding"].sum()), 2),
        "manual_review_rate": round(float((apps["manual_review"] == "Y").mean()), 4),
    }
    slices = {}
    for dim in ["year", "branch_code", "region", "product_code", "family", "segment", "risk_band", "status", "channel", "new_existing"]:
        g = a2.groupby(dim)
        slices[dim] = {"groups": int(g.ngroups), "applications_sample": {str(k): int(v) for k, v in g.size().head(5).items()}}
    by_year = {y: {"applications": int(len(g)), "approval_rate": round(float((g[g['status'].isin(['APPROVED','REJECTED'])]['status'] == 'APPROVED').mean()), 4),
                   "manual_review_rate": round(float((g["manual_review"] == "Y").mean()), 4)} for y, g in a2.groupby("year")}
    rep_out["kpis"] = {"overall": kpis, "by_year": by_year, "slicing_dimensions": slices,
                       "definitions": {
                           "approval_rate": "APPROVED / (APPROVED + REJECTED); WITHDRAWN and pending (SUBMITTED, UNDER_REVIEW) excluded",
                           "avg_decision_time": "mean(decision_date - application_date) over APPROVED + REJECTED",
                           "dti": "monthly_debt / (annual_income_at_application / 12); monthly_debt excludes the requested loan",
                           "dti_bands": "<20%, 20-35%, 35-50%, >50%",
                           "delinquency_rate": "PROVISIONAL (generator report only): loans with at least one open (PARTIAL/MISSED) instalment at >=30 DPD at 2025-12-31 / approved loans that are not paid off. Open rows are never written off, so this is dominated by old unresolved debt; the final KPI convention is set in the analytics phase - analyse open exposure by DPD ageing buckets (30-59, 60-89, 90-179, 180-365, 365+)",
                           "outstanding_balance": "approved_amount - sum(principal_paid) over approved loans, at 2025-12-31; loans with no instalment due yet count at full approved amount (disbursement date is not a source field)",
                           "manual_review_rate": "manual_review = 'Y' / all applications"}}

    # ---- ML readiness & anti-triviality ------------------------------------------------------------------------------
    ml: dict = {"eligible_mature_loan_count": int(len(mature)), "positive_30plus_loans": int(mature["ever30"].sum()),
                "loan_level_positive_rate": round(float(mature["ever30"].mean()), 4)}
    mt = mature.copy()
    mt["risk_band"] = _risk_band(mt["risk_score"])
    mt["dti_band"] = _dti_band(mt["dti"])
    mt["tenure_years"] = (mt["_app_o"] - world.created_o[mt["_cust_i"].to_numpy()]) / 365.25
    mt["tenure_band"] = pd.cut(mt["tenure_years"], [-1, 1, 3, 6, 100], labels=["<1y", "1-3y", "3-6y", ">6y"]).astype(str)
    mt = mt.sort_values(["_cust_i", "_app_o"])
    mt["prior_ever30"] = pflag.reindex(mt.index)        # as-of-application prior delinquency (not eventual outcome)

    def rate_by(col):
        return {str(k): {"n": int(len(g)), "rate_30plus": round(float(g["ever30"].mean()), 4)} for k, g in mt.groupby(col)}

    ml["rate_by_risk_band"] = rate_by("risk_band")
    ml["rate_by_dti_band"] = rate_by("dti_band")
    ml["rate_by_product"] = rate_by("product_code")
    ml["rate_by_branch_max_min"] = {"max": max(v["rate_30plus"] for v in rate_by("branch_code").values()),
                                    "min": min(v["rate_30plus"] for v in rate_by("branch_code").values())}
    ml["rate_by_prior_delinquency"] = rate_by("prior_ever30")
    ml["rate_by_customer_tenure"] = rate_by("tenure_band")
    ml["loan_level_auc_risk_score_only(-score)"] = round(auc(-mt["risk_score"], mt["ever30"]), 4)
    ml["loan_level_auc_dti_only"] = round(auc(mt["dti"], mt["ever30"]), 4)
    hi_score, lo_score = mt["risk_score"] >= 720, mt["risk_score"] < 600
    ml["counterexamples_loan_level"] = {
        "good_risk_score(>=720)_and_30plus": int((hi_score & mt["ever30"]).sum()),
        "weak_risk_score(<600)_and_never_30plus": int((lo_score & ~mt["ever30"]).sum()),
        "high_dti(>45%)_and_never_30plus": int(((mt["dti"] > 0.45) & ~mt["ever30"]).sum()),
        "low_dti(<20%)_and_30plus": int(((mt["dti"] < 0.20) & mt["ever30"]).sum()),
        "recovery_cases_after_30plus_then_3_ontime": int(rec30_cases),
        "customers_with_overlapping_loans_all_healthy": None,
        "new_customer(<1y)_and_never_30plus": int(((mt["tenure_years"] < 1) & ~mt["ever30"]).sum()),
        "long_term_customer(>6y)_and_30plus": int(((mt["tenure_years"] > 6) & mt["ever30"]).sum()),
    }
    ov_ids = [ci for ci, g in loans.groupby("_cust_i") if len(g) > 1]
    healthy_multi = int(sum(1 for ci in ov_ids if not loans.loc[loans["_cust_i"] == ci, "ever30"].any()))
    ml["counterexamples_loan_level"]["customers_with_multiple_loans_all_healthy"] = healthy_multi
    ml["counterexamples_loan_level"].pop("customers_with_overlapping_loans_all_healthy")
    ml["snapshot_diagnostics_90d_forward_30plus_dpd"] = snapshot_diagnostics(cfg, ref, world, macro, apps, fin, loans)
    rep_out["ml_readiness"] = ml

    st_ = sim.stats
    rep_out["m1_post_schedule_unresolved_debt"] = {
        "rule": "after the contractual schedule ends, an unresolved loan stays a debt obligation until observably paid off; its monthly_debt contribution is min(last scheduled instalment, outstanding principal as of the application date)",
        "applications_with_a_post_schedule_unresolved_loan": int(st_.get("apps_with_post_schedule_unresolved_debt", 0)),
        "applications_where_outstanding_cap_reduced_the_contribution": int(st_.get("apps_where_outstanding_cap_reduced_contribution", 0)),
        "loan_application_pairs_audited": len(sim.arrears_audit),
    }
    rep_out["known_limitations"] = [
        "Unresolved instalments/loans are never written off or closed; open DPD grows until 2025-12-31 (use DPD ageing buckets).",
        "Matured/terminated unresolved debt contributes min(last instalment, outstanding principal as of the date) to later monthly_debt and, with the same convention, to the hidden stress debt service - a synthetic proxy for the burden of post-schedule debt.",
        "Application count per customer is deliberately capped at 8 (synthetic safeguard); about 12% of applicants sit exactly at the cap.",
        "Decision dates and due/payment dates are not business-day adjusted (about a quarter of decisions fall on weekends).",
        "Customer age/employment edge cases remain (students up to ~45, a few early 'retired', some employed 75+, some loans ending after age 80).",
        "CARD_PAYMENT is an aggregated card-spend activity event, not an individual POS transaction.",
        "Monthly macro values are keyed to the calendar month without publication lag and the reference rate applies for the whole month of a change: the later ML phase must LAG monthly macro features to avoid publication-time leakage.",
        "Quarterly snapshots here are a diagnostic only; the ML phase builds MONTHLY snapshots. Loan-level eventual 30+ DPD prevalence and the snapshot-level 90-day positive rate are different quantities and are reported separately.",
        "Outstanding balance counts approved loans with no instalment due yet at the full approved amount (disbursement date is not a source field).",
        "Transactions carry no version timestamp: for the same event_id the later delivery batch wins.",
    ]
    rep_out["clean_truth_validation"] = {"checks": checks, "all_passed": all(c["passed"] for c in checks)}
    return rep_out
