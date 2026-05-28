from __future__ import annotations
import numpy as np
from scrutable.models import WorkloadModel, WorkloadState, NodeState

_BATCH = 512


class _SampleBuffer:
    """Pre-draws batches of random values to amortize per-call RNG overhead."""

    def __init__(self, rng: np.random.Generator) -> None:
        self._rng = rng
        self._normals: np.ndarray = np.empty(_BATCH)
        self._uniforms: np.ndarray = np.empty(_BATCH)
        self._ni = _BATCH
        self._ui = _BATCH

    def _refill_normals(self) -> None:
        self._normals = self._rng.standard_normal(_BATCH)
        self._ni = 0

    def _refill_uniforms(self) -> None:
        self._uniforms = self._rng.random(_BATCH)
        self._ui = 0

    def lognormal(self, mean: float, sigma: float) -> float:
        if self._ni >= _BATCH:
            self._refill_normals()
        z = self._normals[self._ni]
        self._ni += 1
        return float(np.exp(mean + sigma * z))

    def normal(self, loc: float, scale: float) -> float:
        if self._ni >= _BATCH:
            self._refill_normals()
        z = self._normals[self._ni]
        self._ni += 1
        return float(loc + scale * z)

    def random(self) -> float:
        if self._ui >= _BATCH:
            self._refill_uniforms()
        v = self._uniforms[self._ui]
        self._ui += 1
        return float(v)

    def integers(self, n: int) -> int:
        if self._ui >= _BATCH:
            self._refill_uniforms()
        v = self._uniforms[self._ui]
        self._ui += 1
        return int(v * n)


def _weibull_cdf(t: float, scale: float, shape: float) -> float:
    if t <= 0.0:
        return 0.0
    if t < scale * 0.001:
        return 0.0
    return float(1.0 - np.exp(-((t / scale) ** shape)))


def sample_latency(
    model: WorkloadModel,
    wstate: WorkloadState,
    nstate: NodeState,
    rng: np.random.Generator | _SampleBuffer,
) -> float:
    base = rng.lognormal(mean=np.log(model.latency_median), sigma=model.latency_sigma)
    effective = base * wstate.latency_multiplier * nstate.latency_multiplier + nstate.latency_addend
    noise = rng.normal(0.0, model.noise_sigma)
    return max(0.0, effective + noise)


def sample_error_code(
    model: WorkloadModel,
    wstate: WorkloadState,
    nstate: NodeState,
    rng: np.random.Generator | _SampleBuffer,
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
