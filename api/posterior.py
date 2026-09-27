"""Beta-Binomial posterior per H3 cell (plan §4).

Prior:   alpha0 = score_b * n0, beta0 = (1 - score_b) * n0, n0 = 10.
Update:  each accepted event adds alpha += conf, n_events += 1 (beta unchanged; a rat-free night would
         add to beta, roadmap). score_b_updated = alpha / (alpha + beta).
Gate:    events with conf < MIN_CONF or n_hits < MIN_HITS are logged and queued but do not move the posterior.
"""
from __future__ import annotations

import os
import math
from dataclasses import dataclass

N0 = float(os.environ.get("NIGHT_OWL_N0", os.environ.get("BARN_OWL_N0", "10")))
PRIOR_SCORE_B = float(os.environ.get("NIGHT_OWL_PRIOR_SCORE_B", os.environ.get("BARN_OWL_PRIOR_SCORE_B", "0.2")))  # unknown h3
MIN_CONF = float(os.environ.get("NIGHT_OWL_MIN_CONF", os.environ.get("BARN_OWL_MIN_CONF", "0.5")))
MIN_HITS = int(os.environ.get("NIGHT_OWL_MIN_HITS", os.environ.get("BARN_OWL_MIN_HITS", "3")))


def accepts(conf: float, n_hits: int) -> bool:
    """Plan §4: conf >= 0.5 and at least 3 hits move the posterior."""
    return conf >= MIN_CONF and n_hits >= MIN_HITS


@dataclass
class Posterior:
    alpha: float
    beta: float
    n_events: int = 0
    prior_strength: float | None = None

    def __post_init__(self) -> None:
        if self.prior_strength is None:
            self.prior_strength = self.alpha + self.beta

    @classmethod
    def from_score_b(cls, score_b: float, n0: float = N0) -> "Posterior":
        p = min(max(float(score_b), 1e-3), 1 - 1e-3)
        return cls(alpha=p * n0, beta=(1.0 - p) * n0, n_events=0)

    def update(self, conf: float) -> "Posterior":
        self.alpha += float(conf)
        self.n_events += 1
        return self

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def interval(self) -> list[float]:
        """Approximate central 95% Beta interval for the current sensor posterior.

        The Wilson form stays within [0, 1] for small probabilities and narrows
        as accepted observations add evidence. It is an approximation, unlike
        the model's exported interval which also includes ensemble spread.
        """
        total = self.alpha + self.beta
        mean = self.mean
        z = 1.959963984540054
        centre = (mean + z * z / (2 * total)) / (1 + z * z / total)
        half = z * math.sqrt(mean * (1 - mean) / total + z * z / (4 * total * total)) / (1 + z * z / total)
        return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]

    def to_dict(self) -> dict:
        return {"alpha": round(self.alpha, 4), "beta": round(self.beta, 4), "n_events": self.n_events}


def percentile_rank(values: list[float]) -> list[float]:
    """0..100, average rank on ties, 100 = highest. Same rule as city/make_fixture.py."""
    n = len(values)
    if n < 2:
        return [50.0 for _ in values]
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return [round(100.0 * r / (n - 1), 1) for r in ranks]
