from __future__ import annotations
from typing import Callable
from scrutable.models import (
    Release, ReleaseChange, ReleaseStatus, RolloutState, RolloutStateTransition,
    WorkloadState, Disturbance, DisturbanceScope,
)
from scrutable.plant import Plant
from scrutable.disturbance import apply_disturbance, remove_disturbance

GateCallback = Callable[["ReleaseStatus", float], bool]


class Rollout:
    def __init__(
        self,
        release: Release,
        cluster_order: list[str],
        stage_interval: float,
        start_at: float = 0.0,
        gates: list[list[GateCallback]] | None = None,
    ) -> None:
        self._release = release
        self.cluster_order = cluster_order
        self.stage_interval = stage_interval
        self.start_at = start_at
        self._gates: list[list[GateCallback]] = gates or []

        self._plant: Plant | None = None
        self._workload_states: dict[str, WorkloadState] | None = None

        self._state = RolloutState.PENDING
        self._deployed_clusters: list[str] = []
        self._started_at: float | None = None
        self._state_entered_at: float | None = None
        self._state_history: list[RolloutStateTransition] = []

    def _activate(self, plant: Plant, workload_states: dict[str, WorkloadState]) -> None:
        if self._plant is not None:
            raise RuntimeError("Rollout._activate called more than once")
        self._plant = plant
        self._workload_states = workload_states

    @property
    def status(self) -> ReleaseStatus:
        stages_total = len(self.cluster_order)
        stages_completed = len(self._deployed_clusters)
        pending = [c for c in self.cluster_order if c not in self._deployed_clusters]

        if self._plant is not None and stages_total > 0:
            total_weight = sum(
                self._plant.get_cluster(c).capacity_weight for c in self.cluster_order
            )
            deployed_weight = sum(
                self._plant.get_cluster(c).capacity_weight for c in self._deployed_clusters
            )
            capacity_fraction = deployed_weight / total_weight if total_weight > 0 else 0.0
        else:
            capacity_fraction = 0.0

        return ReleaseStatus(
            release_id=self._release.release_id,
            state=self._state,
            stages_completed=stages_completed,
            stages_total=stages_total,
            deployed_clusters=list(self._deployed_clusters),
            pending_clusters=pending,
            rollout_fraction=stages_completed / stages_total if stages_total > 0 else 0.0,
            capacity_fraction=capacity_fraction,
            started_at=self._started_at,
            state_entered_at=self._state_entered_at,
            state_history=list(self._state_history),
        )

    def _transition(self, new_state: RolloutState, sim_time: float) -> None:
        if self._state_entered_at is not None:
            self._state_history.append(
                RolloutStateTransition(
                    state=self._state,
                    entered_at=self._state_entered_at,
                    exited_at=sim_time,
                )
            )
        self._state = new_state
        self._state_entered_at = sim_time
