from __future__ import annotations
import numpy as np
from scrutable.models import WorkloadModel, WorkloadState, NodeState


def _weibull_cdf(t: float, scale: float, shape: float) -> float:
    if t <= 0.0:
        return 0.0
    return float(1.0 - np.exp(-((t / scale) ** shape)))


def sample_latency(
    model: WorkloadModel,
    wstate: WorkloadState,
    nstate: NodeState,
    rng: np.random.Generator,
) -> float:
    base = rng.lognormal(mean=np.log(model.latency_median), sigma=model.latency_sigma)
    effective = base * wstate.latency_multiplier * nstate.latency_multiplier + nstate.latency_addend
    noise = rng.normal(0.0, model.noise_sigma)
    return max(0.0, effective + noise)


def sample_error_code(
    model: WorkloadModel,
    wstate: WorkloadState,
    nstate: NodeState,
    rng: np.random.Generator,
    sim_time: float,
) -> int:
    base_rate = _weibull_cdf(sim_time, model.error_scale, model.error_shape)
    effective_rate = min(
        1.0,
        max(0.0, base_rate * wstate.error_rate_multiplier * nstate.error_rate_multiplier),
    )
    return 0 if rng.random() >= effective_rate else 1


class WorkloadRegistry:
    def __init__(self) -> None:
        self._models: dict[str, WorkloadModel] = {}

    def register(self, model: WorkloadModel) -> None:
        self._models[model.workload_id] = model

    def get(self, workload_id: str) -> WorkloadModel:
        return self._models[workload_id]

    def all_ids(self) -> list[str]:
        return list(self._models.keys())
