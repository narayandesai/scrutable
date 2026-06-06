from __future__ import annotations
from scrutable.plant import Plant
from scrutable.rollout import Rollout


class RolloutSystem:
    def __init__(self) -> None:
        self._rollouts: dict[str, Rollout] = {}

    def register(self, rollout: Rollout) -> None:
        self._rollouts[rollout._release.release_id] = rollout

    def get(self, release_id: str) -> Rollout:
        try:
            return self._rollouts[release_id]
        except KeyError:
            raise ValueError(f"Unknown release_id: {release_id!r}")

    def all_rollouts(self) -> list[Rollout]:
        return list(self._rollouts.values())


class OperationsSystem:
    def __init__(self, plant: Plant) -> None:
        self._plant = plant

    def drain(self, cluster_id: str) -> None:
        self._plant.set_cluster_enabled(cluster_id, False)

    def restore(self, cluster_id: str) -> None:
        self._plant.set_cluster_enabled(cluster_id, True)
