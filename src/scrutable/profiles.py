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

# Five profiles sharing identical median/error/noise parameters, varying only in
# latency_sigma (the lognormal shape parameter). Each profile's sigma is fixed
# (lognormal_sigma=0.0) so all workloads within a profile are identical.
# This makes P99.9 analytically predictable: exp(log(0.1) + 3.09 * sigma).
# An additive disturbance (+fixed_seconds on 50% of nodes) is detectable on
# low-sigma profiles but falls below the calibrated threshold on high-sigma ones,
# illustrating how SLO SNR degrades as service latency variance grows.
_SPECTRUM_MEDIAN   = FieldDist(lognormal_mean=math.log(0.1), lognormal_sigma=0.0)
_SPECTRUM_ERROR    = FieldDist(lognormal_mean=math.log(5000), lognormal_sigma=0.0)
_SPECTRUM_SHAPE    = FieldDist(lognormal_mean=math.log(1.5), lognormal_sigma=0.0)
_SPECTRUM_NOISE    = FieldDist(lognormal_mean=math.log(0.005), lognormal_sigma=0.0)


def _spectrum_profile(name: str, sigma: float) -> WorkloadProfile:
    return WorkloadProfile(
        name=name,
        latency_median=_SPECTRUM_MEDIAN,
        latency_sigma=FieldDist(lognormal_mean=math.log(sigma), lognormal_sigma=0.0),
        error_scale=_SPECTRUM_ERROR,
        error_shape=_SPECTRUM_SHAPE,
        noise_sigma=_SPECTRUM_NOISE,
    )


LATENCY_VARIANCE_SPECTRUM: list[WorkloadProfile] = [
    _spectrum_profile("variance_v1", sigma=0.1),   # P99.9 ≈ 0.14s, threshold ≈ 0.27s
    _spectrum_profile("variance_v2", sigma=0.3),   # P99.9 ≈ 0.25s, threshold ≈ 0.51s
    _spectrum_profile("variance_v3", sigma=0.6),   # P99.9 ≈ 0.64s, threshold ≈ 1.28s
    _spectrum_profile("variance_v4", sigma=1.0),   # P99.9 ≈ 2.20s, threshold ≈ 4.40s
    _spectrum_profile("variance_v5", sigma=1.5),   # P99.9 ≈ 10.3s, threshold ≈ 20.7s
]
