from __future__ import annotations
from dataclasses import dataclass
import hashlib
import numpy as np
from scrutable.models import Disturbance, WorkloadState
from scrutable.plant import Plant
from scrutable.event_loop import EventLoop


def stable_subset(entities: list[str], percentage: float, disturbance_id: str) -> set[str]:
    threshold = int(percentage * 1000)
    return {
        e for e in entities
        if int.from_bytes(hashlib.md5((e + disturbance_id).encode()).digest()[:4], "little") % 1000 < threshold
    }


def _get_affected_node_ids(disturbance: Disturbance, plant: Plant) -> list[str]:
    if disturbance.scope.filter_id is not None:
        candidates = plant.nodes_in_cluster(disturbance.scope.filter_id)
    else:
        candidates = plant.all_node_ids()
    return list(stable_subset(candidates, disturbance.scope.percentage, disturbance.disturbance_id))


def _get_affected_workload_ids(
    disturbance: Disturbance, workload_states: dict[str, WorkloadState]
) -> list[str]:
    candidates = list(workload_states.keys())
    return list(stable_subset(candidates, disturbance.scope.percentage, disturbance.disturbance_id))


def apply_disturbance(
    disturbance: Disturbance,
    plant: Plant,
    workload_states: dict[str, WorkloadState],
) -> None:
    if disturbance.scope.target_type == "node" and disturbance.node_effects:
        for node_id in _get_affected_node_ids(disturbance, plant):
            state = plant.get_node(node_id)
            for k, v in disturbance.node_effects.items():
                setattr(state, k, v)

    if disturbance.scope.target_type == "workload" and disturbance.workload_effects:
        for wid in _get_affected_workload_ids(disturbance, workload_states):
            # setdefault bootstraps state for workloads that haven't been seen yet,
            # which is intentional: a disturbance can affect a workload before it has
            # produced any events.
            state = workload_states.setdefault(wid, WorkloadState(wid))
            for k, v in disturbance.workload_effects.items():
                setattr(state, k, v)


def _effect_default(key: str) -> float:
    return 0.0 if key.endswith("_addend") else 1.0


def remove_disturbance(
    disturbance: Disturbance,
    plant: Plant,
    workload_states: dict[str, WorkloadState],
) -> None:
    if disturbance.scope.target_type == "node" and disturbance.node_effects:
        for node_id in _get_affected_node_ids(disturbance, plant):
            state = plant.get_node(node_id)
            for k in disturbance.node_effects:
                setattr(state, k, _effect_default(k))

    if disturbance.scope.target_type == "workload" and disturbance.workload_effects:
        for wid in _get_affected_workload_ids(disturbance, workload_states):
            state = workload_states.get(wid)
            if state is None:
                continue
            for k in disturbance.workload_effects:
                setattr(state, k, _effect_default(k))


@dataclass
class TimedDisturbance:
    disturbance: Disturbance
    inject_at: float
    remove_at: float | None = None


@dataclass
class StochasticDisturbance:
    disturbance: Disturbance
    rate: float      # Poisson rate: occurrences per simulation second
    duration: float  # how long each occurrence lasts


class DisturbanceInjector:
    def __init__(
        self,
        loop: EventLoop,
        plant: Plant,
        workload_states: dict[str, WorkloadState],
        rng: np.random.Generator,
    ) -> None:
        self._loop = loop
        self._plant = plant
        self._workload_states = workload_states
        self._rng = rng

    def add_timed(self, td: TimedDisturbance) -> None:
        self._loop.schedule(
            td.inject_at,
            lambda d=td.disturbance: apply_disturbance(d, self._plant, self._workload_states),
        )
        if td.remove_at is not None:
            self._loop.schedule(
                td.remove_at,
                lambda d=td.disturbance: remove_disturbance(d, self._plant, self._workload_states),
            )

    def add_stochastic(self, sd: StochasticDisturbance) -> None:
        self._schedule_stochastic(sd, self._loop.now)

    def _schedule_stochastic(self, sd: StochasticDisturbance, current_time: float) -> None:
        wait = self._rng.exponential(1.0 / sd.rate)
        next_time = current_time + wait
        self._loop.schedule(
            next_time,
            lambda s=sd, t=next_time: self._fire_stochastic(s, t),
        )

    def _fire_stochastic(self, sd: StochasticDisturbance, fire_time: float) -> None:
        apply_disturbance(sd.disturbance, self._plant, self._workload_states)
        remove_time = fire_time + sd.duration
        self._loop.schedule(
            remove_time,
            lambda d=sd.disturbance: remove_disturbance(d, self._plant, self._workload_states),
        )
        self._schedule_stochastic(sd, fire_time)
