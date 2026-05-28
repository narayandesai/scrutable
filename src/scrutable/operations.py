from __future__ import annotations
from dataclasses import dataclass, field
from scrutable.models import Disturbance, WorkloadState
from scrutable.plant import Plant
from scrutable.disturbance import apply_disturbance, remove_disturbance


@dataclass
class SoftwareVersion:
    version_id: str
    disturbances: list[Disturbance] = field(default_factory=list)


class RolloutSystem:
    def __init__(
        self,
        versions: dict[str, SoftwareVersion],
        plant: Plant,
        workload_states: dict[str, WorkloadState],
    ) -> None:
        self._versions = versions
        self._plant = plant
        self._workload_states = workload_states
        self._active: set[str] = set()

    def deploy(self, version_id: str) -> None:
        if version_id in self._active:
            return
        for disturbance in self._versions[version_id].disturbances:
            apply_disturbance(disturbance, self._plant, self._workload_states)
        self._active.add(version_id)

    def rollback(self, version_id: str) -> None:
        if version_id not in self._active:
            return
        for disturbance in self._versions[version_id].disturbances:
            remove_disturbance(disturbance, self._plant, self._workload_states)
        self._active.discard(version_id)


class OperationsSystem:
    def __init__(self, plant: Plant) -> None:
        self._plant = plant

    def drain(self, cluster_id: str) -> None:
        self._plant.set_cluster_enabled(cluster_id, False)

    def restore(self, cluster_id: str) -> None:
        self._plant.set_cluster_enabled(cluster_id, True)
