from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Protocol
from scrutable.models import WorkloadModel


class DiurnalCurve(Protocol):
    def __call__(self, phase: float) -> float: ...


@dataclass(frozen=True)
class FlatCurve:
    def __call__(self, phase: float) -> float:
        return 1.0


@dataclass(frozen=True)
class SinusoidalCurve:
    peak_phase: float
    trough_depth: float

    def __call__(self, phase: float) -> float:
        return 1.0 + self.trough_depth * math.cos(2.0 * math.pi * (phase - self.peak_phase))


@dataclass(frozen=True)
class DoublePeakCurve:
    peak1_phase: float
    peak2_phase: float
    trough_depth: float

    def __call__(self, phase: float) -> float:
        a = self.trough_depth / 2.0
        return (
            1.0
            + a * math.cos(4.0 * math.pi * (phase - self.peak1_phase))
            + a * math.cos(4.0 * math.pi * (phase - self.peak2_phase))
        )


@dataclass
class MarkovActivity:
    onset_rate: float
    recovery_rate: float
    initial_active: bool = True


@dataclass
class WorkloadEntry:
    model: WorkloadModel
    share: float
    diurnal: DiurnalCurve = field(default_factory=FlatCurve)
    activity: MarkovActivity | None = None


@dataclass
class WorkloadMix:
    total_rate: float
    period: float
    entries: list[WorkloadEntry]
    _lookup: dict[str, WorkloadEntry] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        total = sum(e.share for e in self.entries)
        if abs(total - 1.0) >= 1e-6:
            raise ValueError(f"WorkloadEntry shares must sum to 1.0, got {total:.8f}")
        self._lookup = {e.model.workload_id: e for e in self.entries}

    def rate_at(self, workload_id: str, t: float) -> float:
        entry = self._lookup[workload_id]
        phase = (t % self.period) / self.period
        return self.total_rate * entry.share * entry.diurnal(phase)
