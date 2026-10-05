"""Configuration for the Team 2 synthetic banking source-data generator.

Everything that influences the generated universe lives here so that the same
code + config + seed always reproduces byte-identical source files.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

BATCH_IDS = ("batch_001", "batch_002", "batch_003", "batch_004")


def d2o(d: date) -> int:
    return d.toordinal()


def o2d(o: int) -> date:
    return date.fromordinal(o)


@dataclass(frozen=True)
class GenConfig:
    seed: int = 42
    out_dir: str = "data"

    # --- horizon -----------------------------------------------------------
    history_start: date = date(2016, 1, 1)
    history_end: date = date(2025, 12, 31)
    # end-of-delivery cutoffs of batch_001 .. batch_004
    batch_cutoffs: tuple = (
        date(2025, 9, 30),
        date(2025, 10, 31),
        date(2025, 11, 30),
        date(2025, 12, 31),
    )

    # --- population --------------------------------------------------------
    n_customers: int = 15000
    pre_history_share: float = 0.30       # customers already existing before 2016
    greek_name_share: float = 0.87
    zero_propensity_share: float = 0.12   # deposit-only customers who never apply
    app_rate_per_year: float = 0.38       # mean applications / customer-year (before frailty)
    cashflow_coverage: float = 0.58       # share of borrowers with rich internal cash-flow history

    # --- underwriting ------------------------------------------------------
    approval_intercept: float = 0.55
    withdrawn_base: float = 0.045

    # --- behaviour simulation ---------------------------------------------
    shock_base_prob: float = 0.010        # monthly probability of an income shock
    shock_major_share: float = 0.30       # share of shocks that hit hard and abruptly
    stress_intercept: float = -0.35
    thr_late: float = 2.50                # u above -> late payment
    thr_serious: float = 3.80             # u above -> partial / long delays
    thr_severe: float = 4.60              # u above -> mostly missed
    inst_noise_sd: float = 0.9            # installment-level noise on top of monthly stress
    default_consecutive: int = 3          # unresolved installments before the schedule stops
    tx_intensity: float = 0.7             # scales non-loan cash-flow event volume

    # --- defect injection rates (share of delivered source rows) -----------
    defect_rate_customers: float = 0.058
    defect_rate_applications: float = 0.058
    defect_rate_repayments: float = 0.048
    defect_rate_transactions: float = 0.039

    # --- late-arriving / corrected records (shares of previous-window rows)
    late_share_customers: float = 0.10
    late_share_applications: float = 0.04
    late_share_transactions: float = 0.004
    correction_share_customers: float = 0.008
    correction_share_applications: float = 0.004
    correction_share_transactions: float = 0.0004
    contact_change_share: float = 0.02

    def to_json_dict(self) -> dict:
        def conv(v):
            if isinstance(v, date):
                return v.isoformat()
            if isinstance(v, (tuple, list)):
                return [conv(x) for x in v]
            return v

        return {k: conv(v) for k, v in asdict(self).items()}

    def dump(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json_dict(), indent=2), encoding="utf-8")

    # convenience ordinals
    @property
    def h0(self) -> int:
        return d2o(self.history_start)

    @property
    def h1(self) -> int:
        return d2o(self.history_end)

    @property
    def cutoff_ords(self) -> tuple:
        return tuple(d2o(c) for c in self.batch_cutoffs)
