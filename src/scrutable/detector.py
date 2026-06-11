from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Signal, Alarm


@runtime_checkable
class Detector(Protocol):
    detector_id: str

    def detect(self, signals: list[Signal]) -> list[Alarm]: ...
