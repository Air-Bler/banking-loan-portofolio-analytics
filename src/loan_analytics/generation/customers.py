"""Customers: entry cohorts, demographics, income, employment and state history.

``customers.csv`` holds the *current* master state; the full state timeline
(income / employment over the decade) is kept internally so application-time
snapshots can be reconstructed exactly as the bank knew them at the time.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from . import names as N
from .config import GenConfig, d2o
from .macro import Macro
from .reference import BRANCH_PROFILE, Reference
from .util import iso, ts, year_of

EMP = ["EMPLOYED", "SELF_EMPLOYED", "RETIRED", "UNEMPLOYED", "STUDENT", "OTHER"]
E_EMPLOYED, E_SELF, E_RETIRED, E_UNEMP, E_STUDENT, E_OTHER = range(6)

_INCOME_PARAMS = {  # (median EUR, sigma of log)
    E_EMPLOYED: (21500, 0.50), E_SELF: (22500, 0.85), E_RETIRED: (13500, 0.40),
    E_UNEMP: (7500, 0.65), E_STUDENT: (5500, 0.70), E_OTHER: (9500, 0.70),
}
_EMP_BONUS = {E_EMPLOYED: 0.15, E_SELF: -0.20, E_RETIRED: 0.25, E_UNEMP: -0.55,
              E_STUDENT: -0.25, E_OTHER: -0.20}


def _emp_probs(age: float) -> list:
    if age < 24:
        return [0.40, 0.04, 0.00, 0.12, 0.38, 0.06]
    if age < 35:
        return [0.68, 0.11, 0.00, 0.11, 0.04, 0.06]
    if age < 60:
        return [0.68, 0.17, 0.01, 0.08, 0.00, 0.06]
    if age < 67:
        return [0.38, 0.13, 0.38, 0.05, 0.00, 0.06]
    return [0.06, 0.05, 0.84, 0.01, 0.00, 0.04]


def _income_draw(rng, emp: int, age: float, sme: bool) -> float:
    med, sig = _INCOME_PARAMS[emp]
    if emp in (E_EMPLOYED, E_SELF):
        med *= 0.75 + 0.55 * math.exp(-(((age - 48.0) / 17.0) ** 2))
    if sme:
        med *= 1.6
        sig *= 1.05
    x = math.exp(rng.normal(math.log(med), sig))
    return float(min(max(round(x / 10.0) * 10.0, 2400.0), 650000.0))


@dataclass
class CustomerWorld:
    n: int
    df: pd.DataFrame                      # exported-style current master + internals
    ev_o: list = field(default_factory=list)      # per customer: ordinals of state events
    ev_inc: list = field(default_factory=list)
    ev_emp: list = field(default_factory=list)
    ev_start: list = field(default_factory=list)  # employment start ordinal or -1
    contact_change: dict = field(default_factory=dict)  # idx -> (ordinal, email, phone)
    # latent / behavioural (internal only, never exported)
    resil: np.ndarray = None
    susc: np.ndarray = None
    ext_ratio: np.ndarray = None
    prop: np.ndarray = None
    digital: np.ndarray = None
    cashflow: np.ndarray = None
    home_branch: np.ndarray = None
    spend_ratio: np.ndarray = None
    act: np.ndarray = None                # (n, 5) activity multipliers
    salary_day: np.ndarray = None
    created_o: np.ndarray = None
    created_s: np.ndarray = None
    dob_o: np.ndarray = None
    df_segment: list = None

    def state_at(self, i: int, o: int):
        """(annual_income, employment_code, employment_start) known at ordinal ``o``."""
        k = bisect.bisect_right(self.ev_o[i], o) - 1
        if k < 0:
            k = 0
        return self.ev_inc[i][k], self.ev_emp[i][k], self.ev_start[i][k]

    def last_event_o(self, i: int, o: int) -> int:
        k = bisect.bisect_right(self.ev_o[i], o) - 1
        return self.ev_o[i][k] if k >= 0 else -1


# --------------------------------------------------------------------------
# (pattern name, probability) - the dictionary documents exactly this list
EMAIL_PATTERNS = [
    ("firstname.lastname", .18), ("firstinitial.lastname", .12), ("lastname.firstname", .06),
    ("firstnameYYYY (birth year)", .12), ("initials_number", .08), ("first-last", .05),
    ("nickname (first name only)", .05), ("firstname-lastinitial+number", .08),
    ("handle+number (unrelated to legal name)", .12), ("lastname.firstinitial", .08),
    ("firstnamelastname", .06),
]


def _make_email(rng, first: str, last: str, birth_year: int, taken: set) -> str:
    f, l = first.lower(), last.lower()
    pat = rng.choice(len(EMAIL_PATTERNS), p=[p for _, p in EMAIL_PATTERNS])
    num = int(rng.integers(1, 99))
    if pat == 0:
        local = f"{f}.{l}"
    elif pat == 1:
        local = f"{f[0]}.{l}"
    elif pat == 2:
        local = f"{l}.{f}"
    elif pat == 3:
        local = f"{f}{birth_year}"
    elif pat == 4:
        local = f"{f[0]}{l[0]}_{num}"
    elif pat == 5:
        local = f"{f}-{l}"
    elif pat == 6:
        local = f
    elif pat == 7:
        local = f"{f}-{l[0]}{num}"
    elif pat == 8:
        local = f"{N.HANDLES[int(rng.integers(len(N.HANDLES)))]}{num}"
    elif pat == 9:
        local = f"{l}.{f[0]}"
    else:
        local = f"{f}{l}"
    doms = [d for d, _ in N.EMAIL_PROVIDERS]
    w = np.array([p for _, p in N.EMAIL_PROVIDERS])
    dom = doms[int(rng.choice(len(doms), p=w / w.sum()))]
    email = f"{local}@{dom}"
    while email in taken:
        email = f"{local}{int(rng.integers(1, 9999))}@{dom}"
    taken.add(email)
    return email


def _make_phone(rng) -> str:
    kind = rng.choice(5, p=[.45, .22, .05, .18, .10])
    if kind <= 2:
        core = "69" + str(int(rng.integers(0, 10))) + f"{int(rng.integers(0, 10_000_000)):07d}"
        return core if kind == 0 else ("+30" + core if kind == 1 else "0030" + core)
    area = N.GR_AREA_CODES[int(rng.integers(len(N.GR_AREA_CODES)))]
    core = area + f"{int(rng.integers(0, 10 ** (10 - len(area)))):0{10 - len(area)}d}"
    return core if kind == 3 else "+30" + core


# --------------------------------------------------------------------------
def build_customers(cfg: GenConfig, ref: Reference, macro: Macro) -> CustomerWorld:
    rng = np.random.default_rng([cfg.seed, 3])
    n = cfg.n_customers
    H0, H1 = cfg.h0, cfg.h1

    # ---- households --------------------------------------------------------
    members = []  # (hh, greek, female, surname)
    hh = 0
    while len(members) < n:
        size = int(rng.choice([1, 2, 3, 4], p=[.78, .17, .04, .01]))
        greek = rng.random() < cfg.greek_name_share
        pool = N.GR_SURNAMES if greek else N.INTL_SURNAMES
        sur = pool[int(rng.integers(len(pool)))]
        for _ in range(size):
            members.append((hh, greek, bool(rng.random() < 0.5), sur))
        hh += 1
    members = members[:n]

    # ---- entry dates ---------------------------------------------------------
    pre = rng.random(n) < cfg.pre_history_share
    created_o = np.zeros(n, dtype=np.int64)
    pre0, pre1 = d2o(date(2008, 1, 1)), H0 - 1
    years = np.arange(2016, 2026)
    yw = 1.0 + 0.07 * (years - 2016)
    yw = yw / yw.sum()
    for j in range(n):
        if pre[j]:
            u = rng.random() ** 0.8
            created_o[j] = pre0 + int(u * (pre1 - pre0))
        else:
            y = int(years[int(rng.choice(len(years), p=yw))])
            a, b = d2o(date(y, 1, 1)), d2o(date(y, 12, 31))
            created_o[j] = a + int(rng.integers(0, b - a + 1))
    created_s = rng.integers(8 * 3600, 19 * 3600 + 1800, n)
    order = np.lexsort((np.arange(n), created_s, created_o))
    members = [members[k] for k in order]
    created_o, created_s = created_o[order], created_s[order]

    # ---- ids & households -----------------------------------------------------
    cust_ids = [f"CU{j + 1:06d}" for j in range(n)]
    first_seen: dict = {}
    for j, m in enumerate(members):
        first_seen.setdefault(m[0], j)
    hh_rank = {h: r for r, h in enumerate(sorted(first_seen, key=first_seen.get))}
    hh_size: dict = {}
    for m in members:
        hh_size[m[0]] = hh_size.get(m[0], 0) + 1
    household_id = []
    for m in members:
        if hh_size[m[0]] == 1 and rng.random() < 0.12:
            household_id.append(None)
        else:
            household_id.append(f"HH{hh_rank[m[0]] + 1:06d}")

    # household home branch
    bcodes = ref.branch_codes
    bw = np.array([BRANCH_PROFILE[b][0] for b in bcodes])
    bw = bw / bw.sum()
    hh_branch = {h: int(rng.choice(len(bcodes), p=bw)) for h in sorted(first_seen)}
    home_branch = np.array([hh_branch[m[0]] for m in members], dtype=np.int64)
    # a minority of members bank at another branch
    switch = rng.random(n) < 0.12
    home_branch[switch] = rng.choice(len(bcodes), size=int(switch.sum()), p=bw)

    # ---- demographics --------------------------------------------------------
    first, last, dob_o, email, phone = [], [], np.zeros(n, dtype=np.int64), [], []
    taken: set = set()
    age_c = np.zeros(n)
    for j, (h, greek, female, sur) in enumerate(members):
        r = rng.random()
        if r < 0.17:
            age = max(18.0, rng.normal(25, 4))
        elif r < 0.75:
            age = max(18.0, rng.normal(40, 9))
        else:
            age = max(18.0, rng.normal(56, 8))
        end_age = age + (H1 - created_o[j]) / 365.25
        if end_age > 86:
            age = max(18.0, age - (end_age - 86))
        age_c[j] = age
        dob_o[j] = created_o[j] - int(age * 365.25) - int(rng.integers(0, 365))
        if greek:
            pool = N.GR_FEMALE if female else N.GR_MALE
            fn = pool[int(rng.integers(len(pool)))]
            ln = N.feminize(sur) if female else sur
        else:
            pool = N.INTL_FEMALE if female else N.INTL_MALE
            fn = pool[int(rng.integers(len(pool)))]
            ln = sur
        first.append(fn)
        last.append(ln)
        by = year_of(int(dob_o[j]))
        email.append(_make_email(rng, fn, ln, by, taken))
        phone.append(_make_phone(rng))

    # ---- employment / income / state timeline ---------------------------------
    infl_by_year = macro.df.groupby(macro.df["month"].str[:4])["inflation_rate"].mean().to_dict()
    ev_o, ev_inc, ev_emp, ev_start = [], [], [], []
    is_sme = np.zeros(n, dtype=bool)
    inc0 = np.zeros(n)
    emp0 = np.zeros(n, dtype=np.int64)
    for j in range(n):
        so = max(int(created_o[j]), H0)
        age = age_c[j] + (so - created_o[j]) / 365.25
        emp = int(rng.choice(6, p=_emp_probs(age)))
        sme = (emp == E_SELF and rng.random() < 0.38) or (emp == E_EMPLOYED and rng.random() < 0.012)
        is_sme[j] = sme
        inc = _income_draw(rng, emp, age, sme)
        inc0[j], emp0[j] = inc, emp
        if emp in (E_EMPLOYED, E_SELF, E_RETIRED, E_UNEMP):
            mean_t = {E_EMPLOYED: 5.0, E_SELF: 7.0, E_RETIRED: 6.0, E_UNEMP: 0.7}[emp]
            ten = min(rng.exponential(mean_t), max(age - 17.0, 0.1))
            est = max(so - int(ten * 365.25), int(dob_o[j]) + 16 * 365)
            est = min(est, so)
        else:
            est = -1
        eo, ei, ee, es = [so], [inc], [emp], [est]
        cur_inc, cur_emp = inc, emp
        for y in range(max(2016, year_of(so)), 2026):
            a = max(so + 1, d2o(date(y, 1, 1)))
            b = d2o(date(y, 12, 31))
            if a > b:
                continue
            age_y = age_c[j] + (a - created_o[j]) / 365.25
            od = a + int(rng.integers(0, b - a + 1))
            new_emp = None
            if cur_emp in (E_EMPLOYED, E_SELF) and age_y >= 62 and rng.random() < 0.22:
                new_emp = E_RETIRED
            else:
                pchg = {E_EMPLOYED: .035, E_SELF: .06, E_UNEMP: .30, E_STUDENT: .20 if age_y < 30 else .02,
                        E_OTHER: .12, E_RETIRED: .0}[cur_emp]
                if rng.random() < pchg:
                    if cur_emp == E_EMPLOYED:
                        new_emp = int(rng.choice([E_SELF, E_UNEMP, E_EMPLOYED], p=[.25, .30, .45]))
                    elif cur_emp == E_SELF:
                        new_emp = int(rng.choice([E_EMPLOYED, E_UNEMP, E_SELF], p=[.40, .25, .35]))
                    elif cur_emp == E_UNEMP:
                        new_emp = int(rng.choice([E_EMPLOYED, E_UNEMP, E_OTHER], p=[.60, .25, .15]))
                    elif cur_emp == E_STUDENT:
                        new_emp = int(rng.choice([E_EMPLOYED, E_STUDENT, E_UNEMP], p=[.60, .30, .10]))
                    else:
                        new_emp = int(rng.choice([E_EMPLOYED, E_OTHER, E_UNEMP], p=[.40, .40, .20]))
            if new_emp is not None:
                draw = _income_draw(rng, new_emp, age_y, False)
                if new_emp == E_RETIRED:
                    draw = max(cur_inc * 0.62, 6000.0)
                cur_inc = float(max(round(math.exp(0.45 * math.log(cur_inc) + 0.55 * math.log(draw)) / 10) * 10, 2400))
                cur_emp = new_emp
                eo.append(od); ei.append(cur_inc); ee.append(cur_emp); es.append(od)
            elif rng.random() < 0.55:
                g = math.exp(rng.normal(0.03 + 0.5 * infl_by_year.get(str(y), 1.0) / 100.0, 0.07))
                if cur_emp == E_RETIRED:
                    g = 1 + (g - 1) * 0.4
                cur_inc = float(max(round(cur_inc * g / 10) * 10, 2400))
                eo.append(od); ei.append(cur_inc); ee.append(cur_emp)
                es.append(es[-1])
        ev_o.append(eo); ev_inc.append(ei); ev_emp.append(ee); ev_start.append(es)

    # ---- segment (moderately related to income, not deterministic) ---------------
    segment = []
    for j in range(n):
        inc = inc0[j]
        r = rng.random()
        if is_sme[j]:
            seg = "SME"
        elif inc >= 60000:
            seg = "PREMIER" if r < 0.70 else "AFFLUENT"
        elif inc >= 42000:
            seg = "PREMIER" if r < 0.20 else ("AFFLUENT" if r < 0.85 else "MASS")
        elif inc >= 28000:
            seg = "AFFLUENT" if r < 0.55 else "MASS"
        else:
            seg = "AFFLUENT" if r < 0.08 else "MASS"
        segment.append(seg)
    segment = np.array(segment)

    # ---- latent behavioural traits (internal only) -------------------------------
    zinc = (np.log(inc0) - np.log(inc0).mean()) / np.log(inc0).std()
    empb = np.array([_EMP_BONUS[int(e)] for e in emp0])
    resil = 0.30 * zinc + 0.50 * empb + 0.88 * rng.normal(size=n)
    resil = (resil - resil.mean()) / resil.std()
    susc = rng.normal(size=n) + 0.5 * (emp0 == E_SELF)
    ext = np.where(rng.random(n) < 0.38, 0.0,
                   np.clip(np.exp(rng.normal(math.log(0.10), 0.65, n)), 0.01, 0.55))
    seg_mult = {"SME": 1.6, "PREMIER": 1.15, "AFFLUENT": 1.05, "MASS": 0.95}
    emp_mult = {E_STUDENT: .4, E_UNEMP: .6, E_RETIRED: .6}
    base_mean = cfg.app_rate_per_year / (1 - cfg.zero_propensity_share)
    shape = 1.5
    prop = rng.gamma(shape, base_mean / shape, n)
    prop *= np.array([seg_mult[s] for s in segment]) * np.array([emp_mult.get(int(e), 1.0) for e in emp0])
    prop[rng.random(n) < cfg.zero_propensity_share] = 0.0
    bdig = np.array([BRANCH_PROFILE[bcodes[b]][1] for b in home_branch])
    digital = np.clip(rng.beta(2, 3, n) + 0.30 * (1 - (age_c - 20) / 60) - 0.10 + 0.3 * (bdig - 0.5), 0.02, 0.98)
    pcf = np.clip(cfg.cashflow_coverage + np.where(created_o < H0, 0.08, -0.04) + 0.06 * (emp0 == E_EMPLOYED), 0.2, 0.95)
    cashflow = rng.random(n) < pcf
    spend_ratio = np.clip(0.85 - 0.08 * zinc + rng.normal(0, 0.10, n), 0.35, 1.05)
    act = np.exp(rng.normal(0, 0.45, (n, 5)))
    act[rng.random((n, 5)) < 0.10] = 0.0
    salary_day = rng.integers(1, 28, n)

    # ---- current master state --------------------------------------------------
    cur_inc = np.array([ev_inc[j][-1] for j in range(n)])
    cur_emp = [EMP[ev_emp[j][-1]] for j in range(n)]
    cur_start = [iso(ev_start[j][-1]) if ev_start[j][-1] > 0 else None for j in range(n)]
    upd_o = np.array([max(int(created_o[j]), ev_o[j][-1]) if len(ev_o[j]) > 1 else int(created_o[j]) for j in range(n)])

    # contact changes in the incremental window (Oct-Dec 2025)
    contact_change = {}
    cc = cfg.batch_cutoffs[0].toordinal() + 1
    for j in np.where(rng.random(n) < cfg.contact_change_share)[0]:
        j = int(j)
        if created_o[j] >= cc - 5:
            continue
        o = cc + int(rng.integers(0, H1 - cc + 1))
        newmail = _make_email(rng, first[j], last[j], year_of(int(dob_o[j])), taken)
        contact_change[j] = (o, newmail, _make_phone(rng))

    df = pd.DataFrame({
        "customer_id": cust_ids,
        "first_name": first,
        "last_name": last,
        "email": email,
        "phone": phone,
        "date_of_birth": [iso(int(o)) for o in dob_o],
        "segment": segment,
        "annual_income": cur_inc,
        "household_id": household_id,
        "employment_status": cur_emp,
        "employment_start_date": cur_start,
        "created_at": [ts(int(created_o[j]), int(created_s[j])) for j in range(n)],
        "updated_at": [iso(int(u)) for u in upd_o],  # placeholder, replaced at delivery build
    })
    return CustomerWorld(
        n=n, df=df, ev_o=ev_o, ev_inc=ev_inc, ev_emp=ev_emp, ev_start=ev_start,
        contact_change=contact_change, resil=resil, susc=susc, ext_ratio=ext, prop=prop,
        digital=digital, cashflow=cashflow, home_branch=home_branch, spend_ratio=spend_ratio,
        act=act, salary_day=salary_day, created_o=created_o, created_s=created_s, dob_o=dob_o,
        df_segment=[str(x) for x in segment],
    )
