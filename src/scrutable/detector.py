from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Response, Alarm


@runtime_checkable
class Detector(Protocol):
    detector_id: str
    window_size: float
    tick_interval: float

    def detect(self, window: list[Response]) -> list[Alarm]:
        ...
