from __future__ import annotations
from typing import Protocol, runtime_checkable
from scrutable.models import Inference
from scrutable.operations import RolloutSystem, OperationsSystem


@runtime_checkable
class Actuator(Protocol):
    def act(
        self,
        inference: Inference,
        sim_time: float,
        rollouts: RolloutSystem,
        ops: OperationsSystem,
    ) -> None:
        ...
