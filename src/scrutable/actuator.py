from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Alarm
from scrutable.operations import RolloutSystem, OperationsSystem


@runtime_checkable
class Actuator(Protocol):
    def act(
        self,
        alarm: Alarm,
        sim_time: float,
        rollouts: RolloutSystem,
        ops: OperationsSystem,
    ) -> None:
        ...
