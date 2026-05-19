import math
import numpy as np
from dataclasses import dataclass
from scrutable.models import WorkloadModel


@dataclass(frozen=True)
class FieldDist:
    lognormal_mean: float   # mean of the underlying normal (i.e. mean of log(X))
    lognormal_sigma: float  # sigma of the underlying normal


@dataclass(frozen=True)
class WorkloadProfile:
    name: str
    latency_median: FieldDist
    latency_sigma: FieldDist
    error_scale: FieldDist
    error_shape: FieldDist
    noise_sigma: FieldDist


def sample_workload(
    profile: WorkloadProfile,
    workload_id: str,
    rng: np.random.Generator,
) -> WorkloadModel:
    def draw(fd: FieldDist) -> float:
        return float(rng.lognormal(mean=fd.lognormal_mean, sigma=fd.lognormal_sigma))

    return WorkloadModel(
        workload_id=workload_id,
        latency_median=draw(profile.latency_median),
        latency_sigma=draw(profile.latency_sigma),
        error_scale=draw(profile.error_scale),
        error_shape=max(0.1, draw(profile.error_shape)),
        noise_sigma=draw(profile.noise_sigma),
    )


CONSISTENT_FAST = WorkloadProfile(
    name="consistent_fast",
    latency_median=FieldDist(lognormal_mean=math.log(0.05), lognormal_sigma=0.3),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.2), lognormal_sigma=0.2),
    error_scale=FieldDist(lognormal_mean=math.log(5000), lognormal_sigma=0.3),
    error_shape=FieldDist(lognormal_mean=math.log(1.5), lognormal_sigma=0.1),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.005), lognormal_sigma=0.3),
)

HIGH_VARIANCE_LATENCY = WorkloadProfile(
    name="high_variance_latency",
    latency_median=FieldDist(lognormal_mean=math.log(0.1), lognormal_sigma=1.0),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.5), lognormal_sigma=0.5),
    error_scale=FieldDist(lognormal_mean=math.log(3000), lognormal_sigma=0.5),
    error_shape=FieldDist(lognormal_mean=math.log(1.5), lognormal_sigma=0.2),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.01), lognormal_sigma=0.5),
)

BURSTY_ERRORS = WorkloadProfile(
    name="bursty_errors",
    latency_median=FieldDist(lognormal_mean=math.log(0.08), lognormal_sigma=0.4),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.3), lognormal_sigma=0.3),
    error_scale=FieldDist(lognormal_mean=math.log(50), lognormal_sigma=0.5),
    error_shape=FieldDist(lognormal_mean=math.log(1.2), lognormal_sigma=0.2),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.008), lognormal_sigma=0.3),
)

SLOW_RELIABLE = WorkloadProfile(
    name="slow_reliable",
    latency_median=FieldDist(lognormal_mean=math.log(0.5), lognormal_sigma=0.4),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.3), lognormal_sigma=0.2),
    error_scale=FieldDist(lognormal_mean=math.log(10000), lognormal_sigma=0.3),
    error_shape=FieldDist(lognormal_mean=math.log(1.5), lognormal_sigma=0.1),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.02), lognormal_sigma=0.3),
)
