from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Signal
from scrutable.window_result import WindowResult


@runtime_checkable
class Sensor(Protocol):
    sensor_id: str
    window_size: float
    sampling_period: float

    def measure(self, window: WindowResult) -> list[Signal]: ...
