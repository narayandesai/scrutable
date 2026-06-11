from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Response, Signal


@runtime_checkable
class Sensor(Protocol):
    sensor_id: str
    window_size: float
    sampling_period: float

    def measure(self, window: list[Response]) -> list[Signal]: ...
