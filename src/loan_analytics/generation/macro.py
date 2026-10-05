"""Monthly macroeconomic context, 2016-01 .. 2025-12 (120 rows).

SYNTHETIC, calibrated to *approximate* Greek / Euro-area patterns:
 * reference_rate  - approximates the ECB main refinancing rate (step path);
 * inflation_rate  - Greek HICP-like y/y inflation (anchor points + noise);
 * unemployment_rate - Greek unemployment (anchor points + noise);
 * consumer_confidence_index - synthetic 0-100 style index.
These values are NOT official statistics.

``macro_pressure`` is an internal, standardised stress input (not exported).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import GenConfig

N_MONTHS = 120


def _anchors(points: dict) -> pd.Series:
    idx = pd.period_range("2016-01", "2025-12", freq="M")
    s = pd.Series(np.nan, index=idx)
    for k, v in points.items():
        s[pd.Period(k, "M")] = v
    return s.interpolate(method="linear").bfill().ffill()


_UNEMP = {
    "2016-01": 24.6, "2016-12": 23.2, "2017-12": 20.9, "2018-12": 18.4, "2019-12": 16.6,
    "2020-04": 17.0, "2020-12": 16.1, "2021-12": 14.0, "2022-12": 12.5, "2023-12": 10.9,
    "2024-12": 9.6, "2025-12": 8.5,
}
_INFL = {
    "2016-01": -0.3, "2016-06": 0.0, "2016-12": 1.0, "2017-06": 1.3, "2017-12": 1.0,
    "2018-06": 0.9, "2018-12": 0.6, "2019-06": 0.3, "2019-12": 0.2, "2020-05": -0.9,
    "2020-12": -2.4, "2021-06": 0.9, "2021-12": 4.8, "2022-03": 7.2, "2022-10": 12.1,
    "2022-12": 8.7, "2023-04": 5.4, "2023-12": 3.2, "2024-06": 2.4, "2024-12": 2.9,
    "2025-06": 2.9, "2025-12": 2.6,
}
_CONF = {
    "2016-01": 58.0, "2016-12": 60.0, "2017-12": 66.0, "2018-12": 72.0, "2019-12": 78.0,
    "2020-04": 60.0, "2020-12": 66.0, "2021-12": 74.0, "2022-10": 58.0, "2023-06": 68.0,
    "2024-06": 73.0, "2025-12": 76.0,
}
_REF_STEPS = [  # (first month, rate %)
    ("2016-01", 0.05), ("2016-03", 0.00), ("2022-07", 0.50), ("2022-09", 1.25),
    ("2022-11", 2.00), ("2022-12", 2.50), ("2023-02", 3.00), ("2023-03", 3.50),
    ("2023-05", 3.75), ("2023-06", 4.00), ("2023-08", 4.25), ("2023-09", 4.50),
    ("2024-06", 4.25), ("2024-09", 3.65), ("2024-10", 3.40), ("2024-12", 3.15),
    ("2025-02", 2.90), ("2025-03", 2.65), ("2025-04", 2.40), ("2025-06", 2.15),
]


@dataclass
class Macro:
    df: pd.DataFrame            # exported columns
    pressure: np.ndarray        # internal standardised macro pressure, length 120
    ref_rate: np.ndarray        # reference rate as decimal (0.025 = 2.5%)


def build_macro(cfg: GenConfig) -> Macro:
    rng = np.random.default_rng([cfg.seed, 2])
    idx = pd.period_range("2016-01", "2025-12", freq="M")

    unemp = _anchors(_UNEMP).to_numpy()
    infl = _anchors(_INFL).to_numpy()
    conf = _anchors(_CONF).to_numpy()
    # smooth AR(1) noise so series do not look like straight lines
    def ar_noise(sd: float, rho: float = 0.6) -> np.ndarray:
        e = rng.normal(0, sd, N_MONTHS)
        out = np.zeros(N_MONTHS)
        for t in range(1, N_MONTHS):
            out[t] = rho * out[t - 1] + e[t]
        return out

    unemp = unemp + ar_noise(0.10)
    infl = infl + ar_noise(0.18)
    conf = conf + ar_noise(1.6)

    ref = np.zeros(N_MONTHS)
    for first, rate in _REF_STEPS:
        ref[idx.get_loc(pd.Period(first, "M")):] = rate

    df = pd.DataFrame({
        "month": [str(p) for p in idx],
        "inflation_rate": np.round(infl, 2),
        "unemployment_rate": np.round(unemp, 2),
        "reference_rate": np.round(ref, 2),
        "consumer_confidence_index": np.round(conf, 1),
    })

    def z(a):
        return (a - a.mean()) / a.std()

    ref_chg = pd.Series(ref).diff(12).fillna(0).to_numpy()
    infl_smooth = pd.Series(infl).rolling(6, min_periods=1).mean().to_numpy()
    raw = 0.40 * z(unemp) + 0.30 * z(infl_smooth) + 0.20 * z(ref_chg) - 0.10 * z(conf)
    pressure = (raw - raw.mean()) / raw.std()
    return Macro(df=df, pressure=pressure, ref_rate=ref / 100.0)
