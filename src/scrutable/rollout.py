from __future__ import annotations
from collections.abc import Sequence
from typing import Callable
from scrutable.event_loop import EventLoop
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
        gates: Sequence[Sequence[GateCallback]] | None = None,
        on_complete: Callable[[RolloutState, float], None] | None = None,
    ) -> None:
        self._release = release
        self.cluster_order = cluster_order
        self.stage_interval = stage_interval
        self.start_at = start_at
        self._gates: list[list[GateCallback]] = [list(s) for s in gates] if gates else []
        self._on_complete = on_complete

        self._plant: Plant | None = None
        self._workload_states: dict[str, WorkloadState] | None = None
        self._loop: EventLoop | None = None

        self._state = RolloutState.PENDING
        self._deployed_clusters: list[str] = []
        self._started_at: float | None = None
        self._state_entered_at: float | None = None
        self._state_history: list[RolloutStateTransition] = []

    @property
    def release(self) -> Release:
        return self._release

    def _activate(
        self,
        plant: Plant,
        workload_states: dict[str, WorkloadState],
        loop: EventLoop | None = None,
    ) -> None:
        if self._plant is not None:
            raise RuntimeError("Rollout._activate called more than once")
        self._plant = plant
        self._workload_states = workload_states
        self._loop = loop

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

    def _cluster_scoped_disturbance(self, change: ReleaseChange, cluster_id: str) -> Disturbance:
        d = change.disturbance
        assert d is not None
        return Disturbance(
            disturbance_id=f"{self._release.release_id}-{change.change_id}-{cluster_id}",
            scope=DisturbanceScope(
                target_type=d.scope.target_type,
                filter_id=cluster_id,
                percentage=d.scope.percentage,
            ),
            node_effects=d.node_effects,
            workload_effects=d.workload_effects,
        )

    def _remove_cluster_effects(self, cluster_id: str) -> None:
        assert self._plant is not None
        assert self._workload_states is not None
        for change in self._release.changes:
            if change.disturbance is not None:
                scoped = self._cluster_scoped_disturbance(change, cluster_id)
                remove_disturbance(scoped, self._plant, self._workload_states)

    def _deploy_stage(self, stage_idx: int, sim_time: float) -> None:
        cluster_id = self.cluster_order[stage_idx]

        if self._state == RolloutState.PENDING:
            self._transition(RolloutState.IN_PROGRESS, sim_time)
            self._started_at = sim_time

        assert self._plant is not None
        assert self._workload_states is not None
        for change in self._release.changes:
            if change.disturbance is not None:
                scoped = self._cluster_scoped_disturbance(change, cluster_id)
                apply_disturbance(scoped, self._plant, self._workload_states)

        self._deployed_clusters.append(cluster_id)

        if len(self._deployed_clusters) == len(self.cluster_order):
            self._transition(RolloutState.COMPLETED, sim_time)
            if self._on_complete is not None:
                self._on_complete(RolloutState.COMPLETED, sim_time)

    def halt(self, sim_time: float) -> None:
        if self._state not in (RolloutState.PENDING, RolloutState.IN_PROGRESS):
            return
        self._transition(RolloutState.HALTED, sim_time)

    def begin_rollback(self, sim_time: float, duration: float) -> None:
        if self._state != RolloutState.HALTED:
            return
        assert self._loop is not None, "begin_rollback requires a loop; pass loop to _activate"
        self._transition(RolloutState.ROLLING_BACK, sim_time)
        finish_at = sim_time + duration
        self._loop.schedule(finish_at, lambda t=finish_at: self._finish_rollback(t))

    def _finish_rollback(self, sim_time: float) -> None:
        for cluster_id in list(self._deployed_clusters):
            self._remove_cluster_effects(cluster_id)
        self._deployed_clusters.clear()
        self._transition(RolloutState.ROLLED_BACK, sim_time)
        if self._on_complete is not None:
            self._on_complete(RolloutState.ROLLED_BACK, sim_time)

    def rollback_cluster(self, cluster_id: str) -> None:
        if cluster_id not in self._deployed_clusters:
            return
        self._remove_cluster_effects(cluster_id)
        self._deployed_clusters.remove(cluster_id)

    def rollback_all(self, sim_time: float) -> None:
        for cluster_id in list(self._deployed_clusters):
            self.rollback_cluster(cluster_id)
        self._transition(RolloutState.ROLLED_BACK, sim_time)
        if self._on_complete is not None:
            self._on_complete(RolloutState.ROLLED_BACK, sim_time)

    def _check_gates(self, stage_idx: int, sim_time: float) -> bool:
        if stage_idx >= len(self._gates):
            return True
        return all(gate(self.status, sim_time) for gate in self._gates[stage_idx])
