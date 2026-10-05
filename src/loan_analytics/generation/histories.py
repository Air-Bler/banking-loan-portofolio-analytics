"""Chronological per-customer simulation of the banking universe.

For each customer, month by month:
  stress evolves (customer vulnerability, debt burden, macro, shocks)
  -> due installments settle (on-time / late / partial / missed / cured)
  -> applications are submitted, underwritten and (if approved) become loans
  -> cash-flow activity is emitted.

Everything the underwriter uses is information known *as of the application
date*. Latent stress / shocks never leave this module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from .behaviour import settle_date, settle_installment
from .config import GenConfig
from .customers import (E_EMPLOYED, E_RETIRED, E_SELF, E_STUDENT, E_UNEMP, E_OTHER, CustomerWorld)
from .macro import Macro
from .reference import BRANCH_PROFILE, RATE_PASS_THROUGH, Reference
from .util import add_months, annuity_payment, det_secs, month_index

# product index order follows products.csv: PL-STD, PL-GRN, AUT-NEW, MTG-FIX, SME-WCL
P_PL, P_GRN, P_AUT, P_MTG, P_SME = range(5)
TERMS = {
    P_PL: ([12, 18, 24, 30, 36, 48, 60, 72, 84], [.10, .04, .22, .06, .28, .15, .09, .04, .02]),
    P_GRN: ([24, 36, 48, 60, 72, 84, 96], [.14, .26, .26, .20, .09, .03, .02]),
    P_AUT: ([24, 36, 48, 60, 72, 84], [.14, .26, .28, .20, .08, .04]),
    P_MTG: ([120, 144, 180, 240, 300, 360], [.08, .07, .15, .30, .18, .22]),
    P_SME: ([12, 18, 24, 36, 48, 60], [.22, .12, .28, .22, .11, .05]),
}
BASE_PRODUCT_W = np.array([0.37, 0.11, 0.19, 0.11, 0.22])
SEG_ADJ = {
    "SME": np.array([0.30, 0.15, 0.45, 0.20, 5.0]),
    "PREMIER": np.array([0.7, 1.2, 1.0, 2.0, 0.6]),
    "AFFLUENT": np.array([0.9, 1.2, 1.1, 1.5, 0.7]),
    "MASS": np.array([1.1, 0.9, 0.95, 0.6, 0.35]),
}
REQ_MEDIAN = {P_PL: (8500, 24000, .45, .45), P_GRN: (13000, 24000, .45, .45),
              P_AUT: (19000, 24000, .50, .45), P_MTG: (115000, 24000, .75, .35),
              P_SME: (42000, 30000, .65, .50)}
LTI_SOFT = {P_PL: 1.1, P_GRN: 1.2, P_AUT: 1.9, P_MTG: 6.5, P_SME: 3.5}
PROD_OFFSET = {P_PL: 0.0, P_GRN: 0.15, P_AUT: 0.20, P_MTG: -0.20, P_SME: -0.35}
MANUAL_EXTRA = {P_PL: 0.0, P_GRN: 0.06, P_AUT: 0.05, P_MTG: 0.30, P_SME: 0.22}
DEC_DAYS = {P_PL: 1.0, P_GRN: 2.5, P_AUT: 1.8, P_MTG: 14.0, P_SME: 7.0}
DISB_LAG = {P_PL: (1, 6), P_GRN: (2, 8), P_AUT: (2, 11), P_MTG: (15, 46), P_SME: (5, 21)}
EMP_PEN = {E_EMPLOYED: 0.0, E_SELF: -0.15, E_RETIRED: -0.10, E_UNEMP: -1.3, E_STUDENT: -0.9, E_OTHER: -0.5}
EMP_SHOCK = {E_EMPLOYED: 1.0, E_SELF: 1.5, E_RETIRED: 0.5, E_UNEMP: 0.5, E_STUDENT: 0.7, E_OTHER: 1.0}
CHANNELS = ["BRANCH", "ONLINE", "MOBILE", "PHONE"]
DUE_DAYS = [1, 5, 10, 15, 20, 25]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def loan_in_debt(L: "Loan", a: int) -> bool:
    """Is the loan a debt obligation as observable on date ``a``?

    True while the schedule is running, and after the schedule ended (maturity or
    early termination) for as long as the debt has not been observably paid off by
    ``a``. There is no write-off/closure model, so unresolved debt never expires.
    Uses only information dated on or before ``a`` (no look-ahead).
    """
    if L.dec_o > a:
        return False
    if L.end_o < 0 or L.end_o > a:
        return True
    return L.paid_off_o is None or L.paid_off_o > a


def loan_running(L: "Loan", a: int) -> bool:
    return L.dec_o <= a and (L.end_o < 0 or L.end_o > a)


def loan_outstanding(L: "Loan", a: int) -> float:
    """Outstanding principal as of date ``a``: approved principal minus principal received
    on or before ``a`` (interest-first allocation). Payments dated after ``a`` are ignored."""
    return L.principal - sum(p for (o, p) in L.pledger if o <= a)


def monthly_debt_contribution(L: "Loan", a: int) -> float:
    """Monthly burden of ``L`` as known on date ``a`` (0 if not a debt obligation).

    * schedule still running on ``a``: the scheduled instalment ``L.pmt``;
    * schedule ended (matured / early-terminated) but not observably paid off by ``a``:
      ``min(L.pmt, outstanding principal as of a)`` - a synthetic proxy for the monthly
      burden of unresolved post-schedule debt (it never expires and never uses payments
      after ``a``).
    """
    if not loan_in_debt(L, a):
        return 0.0
    if loan_running(L, a):
        return L.pmt
    return min(L.pmt, max(loan_outstanding(L, a), 0.0))


def month_debt_service(loans: list, ms: int):
    """Hidden-stress monthly debt service at month start ``ms`` -> (amount, running-loan count).

    Same convention as underwriting: running loans contribute their scheduled instalment; ended-but-
    unresolved loans contribute ``min(instalment, outstanding principal as of ms)`` (strictly as-of,
    no payment dated after ``ms`` is used)."""
    act_pmt = 0.0
    n_act = 0
    for L in loans:
        if loan_running(L, ms):
            act_pmt += L.pmt
            n_act += 1
        elif loan_in_debt(L, ms):
            act_pmt += monthly_debt_contribution(L, ms)
    return act_pmt, n_act


class Loan:
    """Contractual loan state.

    status: ACTIVE (schedule still running), MATURED (final scheduled instalment
    generated, k == term) or DEFAULTED (schedule stopped after repeated unresolved
    instalments). MATURED is NOT "paid off": ``paid_off_o`` is set only when every
    instalment of a matured schedule was fully settled; it is the date of the last
    settlement (cures can arrive after maturity).
    """
    __slots__ = ("gi", "dec_o", "disb_o", "first_due", "term", "rate", "pmt", "bal", "k",
                 "status", "consec", "next_due", "due_day", "def_o", "principal",
                 "end_o", "max_settle", "unsettled", "paid_off_o", "pledger")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


@dataclass
class SimOutput:
    apps: list = field(default_factory=list)       # dict per application
    inst: list = field(default_factory=list)       # (gi, k, due_o, prin_due, int_due, tot_due, pays)
    tx: list = field(default_factory=list)         # (o, secs, etype, cust, amount, channel, direction, system)
    arrears_audit: list = field(default_factory=list)  # (app_gi, loan_gi, as_of, contribution, pmt, outstanding)
    stats: dict = field(default_factory=dict)


class Simulator:
    def __init__(self, cfg: GenConfig, ref: Reference, macro: Macro, world: CustomerWorld):
        self.cfg, self.ref, self.macro, self.w = cfg, ref, macro, world
        self.H0, self.H1 = cfg.h0, cfg.h1
        self.out = SimOutput()
        pr = ref.products
        self.pmin = pr["min_amount"].to_numpy(float)
        self.pmax = pr["max_amount"].to_numpy(float)
        self.tmin = pr["min_term_months"].to_numpy(int)
        self.tmax = pr["max_term_months"].to_numpy(int)
        self.pbase = pr["base_rate"].to_numpy(float)
        self.pcode = list(pr["product_code"])
        self.ppass = np.array([RATE_PASS_THROUGH[c] for c in self.pcode])
        bw = np.array([BRANCH_PROFILE[c][0] for c in ref.branch_codes])
        self.bw = bw / bw.sum()
        # month boundaries
        self.MS, self.ME = [], []
        for y in range(2016, 2026):
            for mth in range(1, 13):
                self.MS.append(date(y, mth, 1).toordinal())
                nxt = date(y + (mth == 12), mth % 12 + 1, 1).toordinal()
                self.ME.append(nxt - 1)
        self._build_day_weights()
        self.n_apps_total = 0
        self.n_rejected_streak = 0

    # ------------------------------------------------------------------
    def _build_day_weights(self):
        n = self.H1 - self.H0 + 1
        w = np.zeros(n)
        season = {1: .95, 2: 1.0, 3: 1.05, 4: 1.05, 5: 1.05, 6: 1.05, 7: .95, 8: .70, 9: 1.0, 10: 1.05,
                  11: 1.05, 12: 1.12}
        for j in range(n):
            d = date.fromordinal(self.H0 + j)
            g = 1.0 + 0.22 * (d.year - 2016)
            if d.year == 2020 and 3 <= d.month <= 5:
                g *= 0.55
            w[j] = g * season[d.month] * (0.15 if d.weekday() >= 5 else 1.0)
        self.cum = np.cumsum(w)

    def sample_days(self, rng, k: int, a: int, b: int) -> list:
        lo = self.cum[a - self.H0 - 1] if a > self.H0 else 0.0
        hi = self.cum[b - self.H0]
        u = lo + rng.random(k) * (hi - lo)
        idx = np.searchsorted(self.cum, u)
        return [self.H0 + int(min(i, self.H1 - self.H0)) for i in idx]

    # ------------------------------------------------------------------
    def run_all(self) -> SimOutput:
        for i in range(self.w.n):
            self.run_customer(i)
        return self.out

    # ------------------------------------------------------------------
    def run_customer(self, i: int):
        cfg, w, H0, H1 = self.cfg, self.w, self.H0, self.H1
        if w.prop[i] <= 0:
            return
        rng = np.random.default_rng([cfg.seed, 11, i])
        created = int(w.created_o[i])
        start_o = max(created, H0)
        lam = w.prop[i] * (H1 - start_o) / 365.25
        n = min(int(rng.poisson(lam)), 8)
        if n == 0:
            return
        # ---- application dates -------------------------------------------------
        days = []
        if created >= H0 and rng.random() < 0.6:
            first = start_o + int(rng.exponential(75.0))
            if first <= H1:
                days.append(first)
                if n > 1:
                    days += self.sample_days(rng, n - 1, first, H1)
        if not days:
            days = self.sample_days(rng, n, start_o, H1)
        days.sort()
        spaced = []
        for d in days:
            if spaced and d < spaced[-1] + 7:
                d = spaced[-1] + 7
            if d <= H1:
                spaced.append(d)
        days = spaced
        if not days:
            return

        due_day = DUE_DAYS[int(rng.integers(len(DUE_DAYS)))]
        m_first = month_index(days[0])
        m_start = max(0, m_first - 6)
        loans: list = []
        bad30: list = []
        ai = 0
        ar = 0.0
        shock_on = shock_end = -1
        amp = 0.0
        kshock = 0.95
        recs: list = []  # per-month cash-flow records: (m, f, salary_absent, mi_, emp, x_m)
        first_disb = None
        prop_seq = 0

        for m in range(m_start, 120):
            MS, ME = self.MS[m], self.ME[m]
            if ai >= len(days) and not any(L.status == "ACTIVE" for L in loans):
                break
            mid = (MS + ME) // 2
            inc, emp, _ = w.state_at(i, mid)
            mi_ = inc / 12.0
            act_pmt, n_act = month_debt_service(loans, MS)
            pti = (act_pmt + w.ext_ratio[i] * mi_) / mi_
            mp = self.macro.pressure[m]

            # shocks: income hit now (cash-flow visible), stress effect lags one month
            if m > shock_end:
                p_sh = cfg.shock_base_prob * math.exp(0.45 * w.susc[i] + 0.25 * mp) * EMP_SHOCK[emp]
                if rng.random() < p_sh:
                    shock_on = m
                    shock_end = m + 1 + int(rng.exponential(2.2))
                    amp = float(min(max(rng.normal(1.3, 0.4), 0.5), 2.4))
                    kshock = 2.4 if rng.random() < cfg.shock_major_share else 0.95
            f = 1.0
            s_m = 0.0
            if shock_on >= 0:
                if shock_on <= m <= shock_end:
                    f = max(0.2, 1.0 - 0.28 * amp * (0.7 if m == shock_on else 1.0))
                elif m > shock_end:
                    f = 1.0 - 0.28 * amp * 0.5 ** (m - shock_end)
                if shock_on + 1 <= m <= shock_end + 1:
                    s_m = kshock * amp
                elif m > shock_end + 1:
                    s_m = kshock * amp * 0.5 ** (m - shock_end - 1)
            salary_absent = bool(f < 0.55 and rng.random() < 0.4)

            ar = 0.75 * ar + rng.normal(0.0, 0.45)
            bad_recent = sum(1 for b in bad30 if ME - 365 < b <= ME)
            z = (cfg.stress_intercept - 0.80 * w.resil[i]
                 + 0.9 * min(max((pti - 0.32) / 0.12, -1.0), 3.0)
                 + 0.30 * mp + 0.22 * max(0, n_act - 1) + 0.40 * min(2, bad_recent))
            x_m = z + s_m + ar
            recs.append((m, f, salary_absent, mi_, emp, x_m))

            # ---- settle installments due this month -----------------------------
            for L in loans:
                if L.status != "ACTIVE":
                    continue
                while L.status == "ACTIVE" and L.next_due <= ME:
                    self._installment(rng, L, x_m, bad30, due_day)

            # ---- applications dated within this month ----------------------------
            while ai < len(days) and days[ai] <= ME:
                loan = self._application(rng, i, days[ai], m, loans, bad30, due_day, prop_seq)
                prop_seq += 1
                ai += 1
                if loan is not None:
                    loans.append(loan)
                    if first_disb is None:
                        first_disb = loan.disb_o

        # ---- cash-flow / transaction history ---------------------------------------
        if not loans:
            return
        self._cashflow(rng, i, recs, first_disb, loans)

    # ------------------------------------------------------------------
    def _installment(self, rng, L: Loan, x_m: float, bad30: list, due_day: int):
        cfg = self.cfg
        k = L.k + 1
        r = L.rate / 12.0
        interest = round(L.bal * r, 2)
        principal = round(L.bal, 2) if k == L.term else round(L.pmt - interest, 2)
        tot = round(principal + interest, 2)
        L.bal = round(L.bal - principal, 2)
        due_o = L.next_due
        u = x_m + rng.normal(0.0, cfg.inst_noise_sd)
        pays = [(o, a) for (o, a) in settle_installment(rng, u, due_o, tot, cfg) if o <= self.H1 and a > 0]
        so = settle_date(pays, tot)
        if so is None:
            if due_o + 30 <= self.H1:
                bad30.append(due_o + 30)
        elif so - due_o >= 30:
            bad30.append(due_o + 30)
        if so is None:
            L.unsettled += 1
        elif so > L.max_settle:
            L.max_settle = so
        unresolved = so is None or (so - due_o) >= 45
        L.consec = L.consec + 1 if unresolved else 0
        self.out.inst.append((L.gi, k, due_o, principal, interest, tot, tuple(pays)))
        cum = 0.0                                  # principal ledger (interest-first), for as-of balances
        for (po, pa) in sorted(pays):
            before = max(0.0, cum - interest)
            cum += pa
            L.pledger.append((po, max(0.0, cum - interest) - before))
        L.k = k
        if k >= L.term:
            L.status = "MATURED"          # schedule ended; NOT necessarily paid off
            L.end_o = due_o
            L.paid_off_o = L.max_settle if L.unsettled == 0 else None
        elif L.consec >= cfg.default_consecutive:
            L.status = "DEFAULTED"        # schedule stops; debt never paid off
            L.def_o = due_o
            L.end_o = due_o
        else:
            L.next_due = add_months(L.first_due, k, due_day)

    # ------------------------------------------------------------------
    def _application(self, rng, i, ao, m, loans, bad30, due_day, seq):
        cfg, w, ref = self.cfg, self.w, self.ref
        gi = len(self.out.apps)
        inc, emp, _ = w.state_at(i, ao)
        mi_ = inc / 12.0
        age = (ao - int(w.dob_o[i])) / 365.25
        seg = w.df_segment[i]
        year = date.fromordinal(ao).year
        n_act = sum(1 for L in loans if loan_in_debt(L, ao))
        debt_loans = 0.0
        n_post = n_capped = 0
        for L in loans:
            c = monthly_debt_contribution(L, ao)
            debt_loans += c
            if loan_in_debt(L, ao) and not loan_running(L, ao):
                n_post += 1
                n_capped += int(c < L.pmt - 1e-9)
                self.out.arrears_audit.append((gi, L.gi, ao, c, L.pmt, loan_outstanding(L, ao)))
        if n_post:
            st_ = self.out.stats
            st_["apps_with_post_schedule_unresolved_debt"] = st_.get("apps_with_post_schedule_unresolved_debt", 0) + 1
            st_["apps_where_outstanding_cap_reduced_contribution"] = st_.get("apps_where_outstanding_cap_reduced_contribution", 0) + int(n_capped > 0)
        # genuinely settled history observable at ao (matured schedule fully paid by ao)
        completed = sum(1 for L in loans if L.paid_off_o is not None and L.paid_off_o <= ao)
        ext = w.ext_ratio[i] * mi_ * float(np.exp(rng.normal(0, 0.05)))
        mdebt = round(debt_loans + ext, 2)
        dti = mdebt / mi_
        prior_bad = sum(1 for b in bad30 if ao - 1825 < b <= ao)
        tenure = max(0.0, (ao - int(w.created_o[i])) / 365.25)

        # ---- risk score (observable, informative but far from deterministic) --------
        zs = (0.70 * w.resil[i] + 0.012 * min(tenure, 10) - 0.22 * (dti - 0.25) / 0.15
              - 0.9 * min(prior_bad, 2) + 0.05 * min(completed, 4) + 0.68 * rng.normal())
        score = int(min(max(round(670 + 78 * zs), 300), 850))

        # ---- product, amount, term -----------------------------------------------
        pw = BASE_PRODUCT_W * SEG_ADJ[seg]
        if seg != "SME":
            pw[P_SME] *= 0.15 if emp != E_SELF else 0.6
        if year < 2020:
            pw[P_GRN] *= 0.10
        elif year < 2022:
            pw[P_GRN] *= 0.6
        pw[P_MTG] *= 0.6 if year <= 2018 else (0.85 if year <= 2021 else (1.0 if year == 2022 else (0.7 if year <= 2024 else 0.9)))
        if not (25 <= age <= 62) or inc < 12000 or emp in (E_STUDENT, E_UNEMP):
            pw[P_MTG] = 0.0
        if emp in (E_STUDENT, E_UNEMP):
            pw[P_SME] *= 0.2
        pw = pw / pw.sum()
        p = int(rng.choice(5, p=pw))
        med, ref_inc, ie, sig = REQ_MEDIAN[p]
        req = med * (inc / ref_inc) ** ie * math.exp(rng.normal(0, sig))
        req = float(min(max(round(req / 10.0) * 10.0, self.pmin[p]), self.pmax[p]))
        terms, tp = TERMS[p]
        term = int(rng.choice(terms, p=tp))
        max_term_age = int((75 - age) * 12)
        if term > max_term_age:
            ok = [t for t in terms if t <= max_term_age]
            term = max(ok) if ok else terms[0]
        term = int(min(max(term, self.tmin[p]), self.tmax[p]))

        # ---- pricing ------------------------------------------------------------
        mo = month_index(ao)
        rate = (self.pbase[p] + self.ppass[p] * self.macro.ref_rate[mo]
                - 0.012 * (score - 670) / 100.0 + rng.normal(0, 0.0012))
        if p == P_MTG:
            rate += 0.0003 * (term - 240) / 12.0
        elif term > 60:
            rate += 0.0015 * (term - 60) / 12.0
        rate = float(min(max(rate, 0.02), 0.22))
        pmt_est = annuity_payment(req, rate, term)
        pti_post = (mdebt + pmt_est) / mi_
        lti = req / inc

        # ---- channel -----------------------------------------------------------------
        pdig = min(max(w.digital[i] * (0.3 + 0.08 * (year - 2016)), 0.02), 0.95)
        if p == P_MTG:
            pdig *= 0.25
        elif p == P_SME:
            pdig *= 0.5
        pph = 0.07
        u = rng.random()
        if u < pdig:
            channel = "MOBILE" if rng.random() < 0.40 + 0.04 * (year - 2016) else "ONLINE"
        elif u < pdig + pph:
            channel = "PHONE"
        else:
            channel = "BRANCH"

        branch = int(w.home_branch[i]) if rng.random() > 0.10 else int(rng.choice(12, p=self.bw))

        # ---- decision --------------------------------------------------------------
        logit = (cfg.approval_intercept + 1.25 * (score - 660) / 70.0
                 - 2.4 * max(0.0, pti_post - 0.40) / 0.15
                 - 1.0 * min(3.0, max(0.0, lti / LTI_SOFT[p] - 1.0))
                 + EMP_PEN[emp] - 0.9 * min(prior_bad, 2) + (0.25 if completed and not prior_bad else 0.0)
                 + PROD_OFFSET[p] - 0.12 * max(0, n_act - 1))
        pm = 0.04 + 0.30 * math.exp(-((logit / 0.9) ** 2)) + MANUAL_EXTRA[p] + (0.08 if req > 0.6 * self.pmax[p] else 0.0)
        manual = bool(rng.random() < min(pm, 0.85))
        if manual:
            logit += rng.normal(0, 0.7)
        p_app = _sigmoid(logit)
        p_wd = cfg.withdrawn_base * (1 + 0.8 * manual + (0.4 if p == P_MTG else 0.0))
        wd = rng.random() < p_wd
        mean_days = DEC_DAYS[p] * (2.5 if manual else 1.0) * (0.7 if (channel in ("ONLINE", "MOBILE") and not manual) else 1.0)
        dd = mean_days * math.exp(rng.normal(0, 0.55))
        if wd:
            dd *= 0.6
        dec_days = int(round(dd))
        if (manual or p in (P_MTG, P_SME)) and not wd:
            dec_days = max(dec_days, 1)
        dec_o = ao + dec_days

        # customer-level snapshot of what the bank knew at application time
        exp_share = min(max(0.55 - 0.12 * math.log(max(inc, 3000) / 24000.0) + rng.normal(0, 0.08), 0.20), 0.90)
        declared_exp = float(max(round(mi_ * exp_share / 10.0) * 10.0, 100.0))

        app = dict(cust=i, gi=gi, branch=branch, prod=p, app_o=ao, dec_o=None, status=None,
                   req=req, appr=None, term=term, rate=None, score=score, mdebt=mdebt,
                   inc=inc, emp=emp, exp=declared_exp, consent="Y", manual="Y" if manual else "N",
                   channel=channel, upd_o=ao, upd_s=det_secs(gi, 3), seq=seq, pmt=None)
        self.out.apps.append(app)

        if dec_o > self.H1:  # still pending at the end of the horizon
            app["status"] = "UNDER_REVIEW" if manual else "SUBMITTED"
            return None
        app["dec_o"] = dec_o
        app["upd_o"] = dec_o
        if wd:
            app["status"] = "WITHDRAWN"
            if rng.random() < 0.12:
                app["consent"] = "N"
            return None
        if rng.random() >= p_app:
            app["status"] = "REJECTED"
            return None

        # ---- approval -> loan account ---------------------------------------------------
        app["status"] = "APPROVED"
        if rng.random() < 0.78 or req <= self.pmin[p]:
            appr = req
        else:
            appr = float(min(max(round(req * rng.uniform(0.55, 0.95) / 10.0) * 10.0, self.pmin[p]), req))
        app["appr"] = appr
        app["rate"] = round(rate, 4)
        lo, hi = DISB_LAG[p]
        disb = dec_o + int(rng.integers(lo, hi))
        cand = add_months(disb, 0, due_day)
        if cand < disb + 20:
            cand = add_months(disb, 1, due_day)
        if cand < disb + 20:
            cand = add_months(disb, 2, due_day)
        pmt = annuity_payment(appr, app["rate"], term)
        app["pmt"] = pmt
        return Loan(gi=gi, dec_o=dec_o, disb_o=disb, first_due=cand, term=term, rate=app["rate"],
                    pmt=pmt, bal=appr, k=0, status="ACTIVE", consec=0, next_due=cand,
                    due_day=due_day, def_o=-1, principal=appr, end_o=-1, max_settle=-1,
                    unsettled=0, paid_off_o=None, pledger=[])

    # ------------------------------------------------------------------
    def _cashflow(self, rng, i, recs, first_disb, loans):
        """Non-loan transaction events (salary, card, direct debit, cash, transfers)."""
        cfg, w, out = self.cfg, self.w, self.out
        cust_created = int(w.created_o[i])
        intensity = cfg.tx_intensity
        if not w.cashflow[i]:
            # sparse-history borrowers: a few scattered events only
            k = int(rng.poisson(3.0 * intensity))
            if k and recs:
                for _ in range(k):
                    m, f, absent, mi_, emp, x = recs[int(rng.integers(len(recs)))]
                    o = self.MS[m] + int(rng.integers(0, 28))
                    if o < cust_created:
                        continue
                    amt = round(mi_ * 0.8 * math.exp(rng.normal(-1.8, 0.7)), 2)
                    et, ch, dr, sy = [("CARD_PAYMENT", "POS", "DEBIT", "card-switch"),
                                      ("BANK_TRANSFER_OUT", "ONLINE", "DEBIT", "payments-hub"),
                                      ("ACCOUNT_CREDIT", "TRANSFER", "CREDIT", "core-banking")][int(rng.integers(3))]
                    out.tx.append((o, int(rng.integers(8 * 3600, 21 * 3600)), et, i, max(amt, 1.0), ch, dr, sy))
            return
        # rich internal cash-flow history is observed around each loan lifecycle
        # (3 months before disbursement to 21 months after), not for the whole decade
        allowed = set()
        for L in loans:
            md = month_index(L.disb_o)
            allowed.update(range(md - 3, md + 22))
        m_lo = max(month_index(cust_created), 0)
        sday = int(w.salary_day[i])
        act = w.act[i]
        sr = float(w.spend_ratio[i])
        for (m, f, absent, mi_, emp, x) in recs:
            if m < m_lo or m not in allowed:
                continue
            MS = self.MS[m]
            net = 0.80 * mi_
            ev = []  # (day_offset, etype, amount, channel, direction, system)
            if emp == E_EMPLOYED:
                if not absent:
                    amount = net * (1 + rng.normal(0, 0.02)) * min(1.0, f + 0.15)
                    d = min(max(sday + int(rng.integers(-1, 3)), 1), 28) - 1
                    ev.append((d, "SALARY_CREDIT", amount, "PAYROLL", "CREDIT", "payroll-gw"))
            elif emp == E_RETIRED:
                ev.append((min(max(sday, 1), 27), "ACCOUNT_CREDIT", net * (1 + rng.normal(0, 0.01)), "PENSION", "CREDIT", "core-banking"))
            elif emp == E_SELF:
                nc = 1 + int(rng.poisson(0.5))
                parts = np.exp(rng.normal(0, 0.4, nc))
                parts = parts / parts.sum()
                for q in range(nc):
                    ev.append((int(rng.integers(0, 28)), "ACCOUNT_CREDIT", net * f * parts[q] * (1 + rng.normal(0, 0.1)),
                               "TRANSFER", "CREDIT", "core-banking"))
            elif emp == E_UNEMP:
                if rng.random() < 0.55:
                    ev.append((int(rng.integers(0, 28)), "ACCOUNT_CREDIT", net * 0.35, "BENEFIT", "CREDIT", "core-banking"))
            else:
                if rng.random() < 0.7:
                    ev.append((int(rng.integers(0, 28)), "BANK_TRANSFER_IN", net * 0.4 * (1 + rng.normal(0, 0.2)), "TRANSFER", "CREDIT", "payments-hub"))
            spend = sr * net * (0.6 + 0.4 * f) * (1 + rng.normal(0, 0.08))
            stressed = f < 0.8
            ncard = int(rng.poisson(0.28 * act[0] * intensity)) + (1 if (act[0] > 0 and rng.random() < 0.22 * intensity) else 0)
            if stressed:
                ncard = max(0, ncard - 1)
            if ncard:
                parts = np.exp(rng.normal(0, 0.7, ncard))
                parts = parts / parts.sum()
                for q in range(ncard):
                    ev.append((int(rng.integers(0, 28)), "CARD_PAYMENT", 0.45 * spend * parts[q], "POS", "DEBIT", "card-switch"))
            if act[1] > 0 and rng.random() < 0.45 * intensity:
                ev.append((int(rng.integers(2, 26)), "DIRECT_DEBIT", 0.12 * spend * math.exp(rng.normal(0, 0.25)), "DIRECT_DEBIT", "DEBIT", "payments-hub"))
            for _ in range(int(rng.poisson(0.14 * act[2] * intensity * (1.5 if stressed else 1.0)))):
                ev.append((int(rng.integers(0, 28)), "CASH_WITHDRAWAL", 0.07 * spend * math.exp(rng.normal(0, 0.3)), "ATM", "DEBIT", "atm-network"))
            for _ in range(int(rng.poisson(0.10 * act[3] * intensity))):
                ev.append((int(rng.integers(0, 28)), "BANK_TRANSFER_OUT", 0.10 * spend * math.exp(rng.normal(0, 0.5)), "ONLINE", "DEBIT", "payments-hub"))
            for _ in range(int(rng.poisson(0.08 * act[4] * intensity * (1.8 if stressed else 1.0)))):
                ev.append((int(rng.integers(0, 28)), "BANK_TRANSFER_IN", 0.12 * net * math.exp(rng.normal(0, 0.5)), "ONLINE", "CREDIT", "payments-hub"))
            for (dday, et, amt, ch, dr, sy) in ev:
                o = MS + dday
                if o < cust_created or o > self.H1:
                    continue
                out.tx.append((o, int(rng.integers(7 * 3600, 22 * 3600)), et, i, round(max(amt, 1.0), 2), ch, dr, sy))
