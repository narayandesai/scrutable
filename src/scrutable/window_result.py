from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class WindowResult:
    t_start: float
    t_end: float
    count: int
    error_rate: float
    _latencies: np.ndarray | None = field(default=None, repr=False)
    _precomputed: dict[float, float] = field(default_factory=dict, repr=False)

    def percentile(self, p: float) -> float:
        if self._latencies is not None:
            return float(np.percentile(self._latencies, p))
        if p in self._precomputed:
            return self._precomputed[p]
        raise KeyError(
            f"percentile {p} not declared at HistogramBuffer construction; "
            f"available: {sorted(self._precomputed)}"
        )

    def __len__(self) -> int:
        return self.count

    def __bool__(self) -> bool:
        return self.count > 0
