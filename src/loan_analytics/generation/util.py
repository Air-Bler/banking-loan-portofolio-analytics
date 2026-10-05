"""Small deterministic helpers (no hidden randomness)."""
from __future__ import annotations

from datetime import date

_ISO: dict = {}


def iso(o: int) -> str:
    s = _ISO.get(o)
    if s is None:
        s = date.fromordinal(o).isoformat()
        _ISO[o] = s
    return s


def ts(o: int, secs: int) -> str:
    return f"{iso(o)}T{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"


def det_secs(a: int, b: int = 0, lo: int = 8 * 3600, hi: int = 19 * 3600) -> int:
    """Deterministic pseudo time-of-day in [lo, hi)."""
    return lo + (a * 7919 + b * 104729 + 13) % (hi - lo)


def year_of(o: int) -> int:
    return date.fromordinal(o).year


def month_index(o: int) -> int:
    d = date.fromordinal(o)
    return (d.year - 2016) * 12 + d.month - 1


def add_months(o: int, k: int, day: int | None = None) -> int:
    """Ordinal of the same (or given) day-of-month k months later (day clipped to 28)."""
    d = date.fromordinal(o)
    m0 = d.year * 12 + d.month - 1 + k
    y, m = divmod(m0, 12)
    dd = min(day if day is not None else d.day, 28)
    return date(y, m + 1, dd).toordinal()


def annuity_payment(principal: float, annual_rate: float, n: int) -> float:
    r = annual_rate / 12.0
    if r <= 1e-12:
        return round(principal / n, 2)
    return round(principal * r / (1.0 - (1.0 + r) ** (-n)), 2)
