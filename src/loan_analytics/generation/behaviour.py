"""Payment behaviour: turns a latent monthly stress level into installment outcomes.

The latent stress variables used here (``u``, shocks, AR noise) are INTERNAL.
Only observable payment events leave this module.
"""
from __future__ import annotations

from .config import GenConfig


def settle_installment(rng, u: float, due_o: int, tot: float, cfg: GenConfig) -> list:
    """Return the payment events [(date_ordinal, amount), ...] for one installment.

    ``u`` is the installment-specific stress draw. Outcomes range from early /
    on-time payment through short delays, partial payments with or without
    later cure, to missed installments with or without late recovery.
    """
    if u < cfg.thr_late:
        if rng.random() < 0.03:  # occasional trivial delay even for healthy borrowers
            return [(due_o + 1 + int(rng.integers(0, 4)), tot)]
        early = 0 if rng.random() < 0.65 else -int(rng.integers(1, 4))
        if rng.random() < 0.04:  # paid in two instalments before due date
            a = round(tot * rng.uniform(0.4, 0.7), 2)
            return [(due_o + early - int(rng.integers(1, 6)), a), (due_o + early, round(tot - a, 2))]
        return [(due_o + early, tot)]

    if u < cfg.thr_serious:
        delay = 1 + int(rng.exponential(4.0 + 4.0 * (u - cfg.thr_late)))
        return [(due_o + min(delay, 28), tot)]

    severe = u >= cfg.thr_severe
    r = rng.random()
    if not severe:
        if r < 0.35:
            return [(due_o + int(rng.integers(14, 46)), tot)]
        mode, p_cure = ("partial", 0.55) if r < 0.70 else ("missed", 0.55)
    else:
        if r < 0.18:
            return [(due_o + int(rng.integers(30, 76)), tot)]
        mode, p_cure = ("partial", 0.40) if r < 0.45 else ("missed", 0.35)

    if mode == "partial":
        frac = rng.uniform(0.30, 0.85)
        d1 = due_o + min(int(rng.exponential(5.0)), 20)
        a1 = round(tot * frac, 2)
        pays = [(d1, a1)]
        if rng.random() < p_cure:
            pays.append((d1 + int(rng.integers(10, 70)), round(tot - a1, 2)))
        return pays
    if rng.random() < p_cure:
        return [(due_o + int(rng.integers(20, 100)), tot)]
    return []


def settle_date(pays: list, tot: float):
    """Ordinal when cumulative payments reach the amount due, or None."""
    run = 0.0
    for o, a in pays:
        run += a
        if run >= tot - 0.005:
            return o
    return None
