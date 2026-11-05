"""Synthetic-only identity-level bootstrap: a methodological demonstration, not an approved method.

Decisions D14 (minimum identity count) and D15 (uncertainty method) of the baseline analysis
preregistration are **pending/review**. Nothing here settles them, and no output of this module is a
scientific result, a calibrated confidence statement, a match decision or a protection claim.

What is resampled: the **identities** only. The input is the sequence of one identity-median value
per contributing identity (already computed by ``aggregate_baseline``); clips and frames are never
resampled because they are not independent within an identity. Each repetition draws ``n`` values
with replacement from the ``n`` identity values and records their median.

Interval: the percentile interval of the repetition medians, using linear interpolation between
order statistics (``(reps - 1) * q`` positions). The seed, level and repetitions are mandatory and
recorded in :attr:`SyntheticIdentityBootstrap.name`. ``random.Random(seed)`` makes the result
deterministic on one Python version.

Limitations: the percentile bootstrap of a median with few identities is known to be unreliable and
its coverage is **not** validated here. The only withheld cases are mechanical: fewer than two
identity values (no resampling variation exists) and all-equal values (the interval would be a
zero-width point that conveys false precision). Missing identities are never imputed. Two
identities is not an endorsed sample size.

:func:`aggregate_baseline` accepts any estimator only for simulated, non-smoke result sets, so this
estimator cannot be attached to real or smoke data.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Final

from frp.aggregation import Interval

NOT_AUTHORISED_NOTE: Final = (
    "Not available / not scientifically authorised: D14 and D15 are pending review."
)


def _check_number(name: str, value: object, *, integer: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int if integer else (int, float)):
        raise ValueError(f"{name} must be {'an integer' if integer else 'a number'}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


class SyntheticIdentityBootstrap:
    """Seeded percentile bootstrap over identity values. Synthetic demonstration only."""

    def __init__(self, *, seed: int, level: float, repetitions: int) -> None:
        _check_number("seed", seed, integer=True)
        _check_number("level", level)
        _check_number("repetitions", repetitions, integer=True)
        if not 0.0 < level < 1.0:
            raise ValueError("level must be strictly between 0 and 1")
        if repetitions < 1:
            raise ValueError("repetitions must be >= 1")
        self.seed, self.level, self.repetitions = seed, float(level), repetitions

    @property
    def name(self) -> str:
        return (
            "synthetic-identity-bootstrap-v0-unapproved"
            f"(seed={self.seed},level={self.level},repetitions={self.repetitions})"
        )

    def interval(self, identity_values: Sequence[float]) -> Interval | None:
        for value in identity_values:
            _check_number("identity value", value)
        values = [float(v) for v in identity_values]
        if len(values) < 2 or min(values) == max(values):
            return None
        rng = random.Random(self.seed)  # noqa: S311 - reproducible, not security-sensitive
        n = len(values)
        medians = sorted(self._median(rng.choices(values, k=n)) for _ in range(self.repetitions))
        tail = (1.0 - self.level) / 2.0
        return Interval(
            lower=_quantile(medians, tail), upper=_quantile(medians, 1.0 - tail), level=self.level
        )

    @staticmethod
    def _median(sample: list[float]) -> float:
        ordered = sorted(sample)
        mid = len(ordered) // 2
        return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def _quantile(ordered: Sequence[float], q: float) -> float:
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


__all__ = ["NOT_AUTHORISED_NOTE", "SyntheticIdentityBootstrap"]
