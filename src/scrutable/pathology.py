from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.models import Pathology, WorkloadState
from scrutable.infrastructure import InfrastructureModel
from scrutable.event_loop import EventLoop


def stable_subset(entities: list[str], percentage: float, pathology_id: str) -> set[str]:
    threshold = int(percentage * 1000)
    return {e for e in entities if abs(hash(e + pathology_id)) % 1000 < threshold}


def _get_affected_node_ids(pathology: Pathology, infra: InfrastructureModel) -> list[str]:
    if pathology.scope.filter_id is not None:
        candidates = infra.nodes_in_cluster(pathology.scope.filter_id)
    else:
        candidates = infra.all_node_ids()
    return list(stable_subset(candidates, pathology.scope.percentage, pathology.pathology_id))


def _get_affected_workload_ids(
    pathology: Pathology, workload_states: dict[str, WorkloadState]
) -> list[str]:
    candidates = list(workload_states.keys())
    return list(stable_subset(candidates, pathology.scope.percentage, pathology.pathology_id))


def apply_pathology(
    pathology: Pathology,
    infra: InfrastructureModel,
    workload_states: dict[str, WorkloadState],
) -> None:
    if pathology.scope.target_type == "node" and pathology.node_effects:
        for node_id in _get_affected_node_ids(pathology, infra):
            state = infra.get_node(node_id)
            for k, v in pathology.node_effects.items():
                setattr(state, k, v)

    if pathology.scope.target_type == "workload" and pathology.workload_effects:
        for wid in _get_affected_workload_ids(pathology, workload_states):
            state = workload_states.setdefault(wid, WorkloadState(wid))
            for k, v in pathology.workload_effects.items():
                setattr(state, k, v)


def remove_pathology(
    pathology: Pathology,
    infra: InfrastructureModel,
    workload_states: dict[str, WorkloadState],
) -> None:
    if pathology.scope.target_type == "node" and pathology.node_effects:
        for node_id in _get_affected_node_ids(pathology, infra):
            state = infra.get_node(node_id)
            for k in pathology.node_effects:
                setattr(state, k, 1.0)

    if pathology.scope.target_type == "workload" and pathology.workload_effects:
        for wid in _get_affected_workload_ids(pathology, workload_states):
            state = workload_states.setdefault(wid, WorkloadState(wid))
            for k in pathology.workload_effects:
                setattr(state, k, 1.0)


@dataclass
class TimedPathology:
    pathology: Pathology
    inject_at: float
    remove_at: float | None = None


@dataclass
class StochasticPathology:
    pathology: Pathology
    rate: float      # Poisson rate: occurrences per simulation second
    duration: float  # how long each occurrence lasts


class PathologyInjector:
    def __init__(
        self,
        loop: EventLoop,
        infra: InfrastructureModel,
        workload_states: dict[str, WorkloadState],
        rng: np.random.Generator,
    ) -> None:
        self._loop = loop
        self._infra = infra
        self._workload_states = workload_states
        self._rng = rng

    def add_timed(self, tp: TimedPathology) -> None:
        self._loop.schedule(
            tp.inject_at,
            lambda p=tp.pathology: apply_pathology(p, self._infra, self._workload_states),
        )
        if tp.remove_at is not None:
            self._loop.schedule(
                tp.remove_at,
                lambda p=tp.pathology: remove_pathology(p, self._infra, self._workload_states),
            )

    def add_stochastic(self, sp: StochasticPathology) -> None:
        self._schedule_stochastic(sp, self._loop.now)

    def _schedule_stochastic(self, sp: StochasticPathology, current_time: float) -> None:
        wait = self._rng.exponential(1.0 / sp.rate)
        next_time = current_time + wait
        self._loop.schedule(
            next_time,
            lambda s=sp, t=next_time: self._fire_stochastic(s, t),
        )

    def _fire_stochastic(self, sp: StochasticPathology, fire_time: float) -> None:
        apply_pathology(sp.pathology, self._infra, self._workload_states)
        remove_time = fire_time + sp.duration
        self._loop.schedule(
            remove_time,
            lambda p=sp.pathology: remove_pathology(p, self._infra, self._workload_states),
        )
        self._schedule_stochastic(sp, fire_time)
