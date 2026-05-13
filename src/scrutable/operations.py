from __future__ import annotations
from dataclasses import dataclass, field
from scrutable.models import Pathology, WorkloadState
from scrutable.infrastructure import InfrastructureModel
from scrutable.pathology import apply_pathology, remove_pathology


@dataclass
class SoftwareVersion:
    version_id: str
    pathologies: list[Pathology] = field(default_factory=list)


class RolloutSystem:
    def __init__(
        self,
        versions: dict[str, SoftwareVersion],
        infra: InfrastructureModel,
        workload_states: dict[str, WorkloadState],
    ) -> None:
        self._versions = versions
        self._infra = infra
        self._workload_states = workload_states
        self._active: set[str] = set()

    def deploy(self, version_id: str) -> None:
        if version_id in self._active:
            return
        for pathology in self._versions[version_id].pathologies:
            apply_pathology(pathology, self._infra, self._workload_states)
        self._active.add(version_id)

    def rollback(self, version_id: str) -> None:
        if version_id not in self._active:
            return
        for pathology in self._versions[version_id].pathologies:
            remove_pathology(pathology, self._infra, self._workload_states)
        self._active.discard(version_id)


class OperationsSystem:
    def __init__(self, infra: InfrastructureModel) -> None:
        self._infra = infra

    def drain(self, cluster_id: str) -> None:
        self._infra.get_cluster(cluster_id).traffic_enabled = False

    def restore(self, cluster_id: str) -> None:
        self._infra.get_cluster(cluster_id).traffic_enabled = True
