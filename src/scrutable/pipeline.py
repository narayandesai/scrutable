from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import numpy as np
from scrutable.models import Disturbance, Release, ReleaseChange


@dataclass
class ChangeStream:
    change_rate: float
    bug_fraction: float
    disturbance_factory: Callable[[str], Disturbance]

    def next_arrival_delay(self, rng: np.random.Generator) -> float:
        return float(rng.exponential(1.0 / self.change_rate))

    def generate_change(self, change_id: str, rng: np.random.Generator) -> ReleaseChange:
        has_bug = float(rng.random()) < self.bug_fraction
        disturbance = self.disturbance_factory(change_id) if has_bug else None
        return ReleaseChange(change_id=change_id, disturbance=disturbance)


class ReleaseBundler:
    def __init__(self, bundle_size: int) -> None:
        self._bundle_size = bundle_size
        self._changes: list[ReleaseChange] = []
        self._release_count = 0

    def add(self, change: ReleaseChange) -> Release | None:
        self._changes.append(change)
        if len(self._changes) >= self._bundle_size:
            return self._flush()
        return None

    def _flush(self) -> Release:
        self._release_count += 1
        release = Release(
            release_id=f"r{self._release_count}",
            changes=list(self._changes),
        )
        self._changes.clear()
        return release


@dataclass
class DebugCycle:
    median_seconds: float = 6.0 * 3600.0
    sigma: float = 0.84

    def sample_duration(self, rng: np.random.Generator) -> float:
        mu = np.log(self.median_seconds)
        return float(rng.lognormal(mu, self.sigma))
