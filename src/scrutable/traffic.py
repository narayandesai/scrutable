from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Protocol


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
