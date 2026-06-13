from __future__ import annotations
import math
import numpy as np
from dataclasses import dataclass, field
from scrutable.models import WorkloadModel
from scrutable.traffic import WorkloadEntry, WorkloadMix, MarkovActivity, DiurnalCurve, FlatCurve


@dataclass(frozen=True)
class FieldDist:
    lognormal_mean: float   # mean of the underlying normal (i.e. mean of log(X))
    lognormal_sigma: float  # sigma of the underlying normal


@dataclass(frozen=True)
class PlantProfileSampler:
    """Generates a random workload population by sampling parameters from FieldDist distributions."""
    name: str
    latency_median: FieldDist
    latency_sigma: FieldDist
    error_scale: FieldDist
    error_shape: FieldDist
    noise_sigma: FieldDist


@dataclass(frozen=True)
class WorkloadSpec:
    """Concrete parameters for a single workload's latency and error distributions."""
    latency_median: float
    latency_sigma: float
    error_scale: float
    error_shape: float
    noise_sigma: float


@dataclass(frozen=True)
class PlantEntry:
    spec: WorkloadSpec
    share: float
    activity: MarkovActivity | None = None
    diurnal: DiurnalCurve = field(default_factory=FlatCurve)


@dataclass(frozen=True)
class PlantProfile:
    """An explicitly enumerated workload population defining a plant."""
    name: str
    entries: list[PlantEntry]


def sample_workload(
    sampler: PlantProfileSampler,
    workload_id: str,
    rng: np.random.Generator,
) -> WorkloadModel:
    def draw(fd: FieldDist) -> float:
        return float(rng.lognormal(mean=fd.lognormal_mean, sigma=fd.lognormal_sigma))

    return WorkloadModel(
        workload_id=workload_id,
        latency_median=draw(sampler.latency_median),
        latency_sigma=draw(sampler.latency_sigma),
        error_scale=draw(sampler.error_scale),
        error_shape=max(0.1, draw(sampler.error_shape)),
        noise_sigma=draw(sampler.noise_sigma),
    )


def sample_plant_profile(
    sampler: PlantProfileSampler,
    n: int,
    rng: np.random.Generator,
) -> PlantProfile:
    share = 1.0 / n
    entries = [
        PlantEntry(
            spec=_spec_from_model(sample_workload(sampler, f"{sampler.name}-{i}", rng)),
            share=share,
        )
        for i in range(n)
    ]
    return PlantProfile(name=sampler.name, entries=entries)


def build_workload_mix(
    profile: PlantProfile,
    total_rate: float,
    period: float,
) -> WorkloadMix:
    entries = [
        WorkloadEntry(
            model=WorkloadModel(
                workload_id=f"{profile.name}-{i}",
                latency_median=e.spec.latency_median,
                latency_sigma=e.spec.latency_sigma,
                error_scale=e.spec.error_scale,
                error_shape=e.spec.error_shape,
                noise_sigma=e.spec.noise_sigma,
            ),
            share=e.share,
            activity=e.activity,
            diurnal=e.diurnal,
        )
        for i, e in enumerate(profile.entries)
    ]
    return WorkloadMix(total_rate=total_rate, period=period, entries=entries)


def _spec_from_model(model: WorkloadModel) -> WorkloadSpec:
    return WorkloadSpec(
        latency_median=model.latency_median,
        latency_sigma=model.latency_sigma,
        error_scale=model.error_scale,
        error_shape=model.error_shape,
        noise_sigma=model.noise_sigma,
    )


# --- PlantProfileSampler catalog ---

CONSISTENT_FAST = PlantProfileSampler(
    name="consistent_fast",
    latency_median=FieldDist(lognormal_mean=math.log(0.05), lognormal_sigma=0.3),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.2), lognormal_sigma=0.2),
    error_scale=FieldDist(lognormal_mean=math.log(5000), lognormal_sigma=0.3),
    error_shape=FieldDist(lognormal_mean=math.log(1.5), lognormal_sigma=0.1),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.005), lognormal_sigma=0.3),
)

HIGH_VARIANCE_LATENCY = PlantProfileSampler(
    name="high_variance_latency",
    latency_median=FieldDist(lognormal_mean=math.log(0.1), lognormal_sigma=1.0),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.5), lognormal_sigma=0.5),
    error_scale=FieldDist(lognormal_mean=math.log(3000), lognormal_sigma=0.5),
    error_shape=FieldDist(lognormal_mean=math.log(1.5), lognormal_sigma=0.2),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.01), lognormal_sigma=0.5),
)

BURSTY_ERRORS = PlantProfileSampler(
    name="bursty_errors",
    latency_median=FieldDist(lognormal_mean=math.log(0.08), lognormal_sigma=0.4),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.3), lognormal_sigma=0.3),
    error_scale=FieldDist(lognormal_mean=math.log(50), lognormal_sigma=0.5),
    error_shape=FieldDist(lognormal_mean=math.log(1.2), lognormal_sigma=0.2),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.008), lognormal_sigma=0.3),
)

SLOW_RELIABLE = PlantProfileSampler(
    name="slow_reliable",
    latency_median=FieldDist(lognormal_mean=math.log(0.5), lognormal_sigma=0.4),
    latency_sigma=FieldDist(lognormal_mean=math.log(0.3), lognormal_sigma=0.2),
    error_scale=FieldDist(lognormal_mean=math.log(10000), lognormal_sigma=0.3),
    error_shape=FieldDist(lognormal_mean=math.log(1.5), lognormal_sigma=0.1),
    noise_sigma=FieldDist(lognormal_mean=math.log(0.02), lognormal_sigma=0.3),
)


# --- PlantProfile catalog ---

SPHERICAL_COW = PlantProfile(
    name="spherical_cow",
    entries=[PlantEntry(
        spec=WorkloadSpec(
            latency_median=0.1,
            latency_sigma=0.25,
            error_scale=50000.0,
            error_shape=1.5,
            noise_sigma=0.005,
        ),
        share=1.0,
    )],
)


# Five profiles varying only in latency_sigma. P99.9 ≈ exp(log(0.1) + 3.09 * sigma).
# Same disturbance becomes undetectable as sigma grows — the core SNR argument.
def _spectrum_profile(name: str, sigma: float) -> PlantProfile:
    return PlantProfile(
        name=name,
        entries=[PlantEntry(
            spec=WorkloadSpec(
                latency_median=0.1,
                latency_sigma=sigma,
                error_scale=5000.0,
                error_shape=1.5,
                noise_sigma=0.005,
            ),
            share=1.0,
        )],
    )


def make_high_variance(
    n_fast: int = 99_000,
    n_slow: int = 1_000,
    onset_rate: float = 0.001,
    recovery_rate: float = 0.1,
) -> PlantProfile:
    """Bimodal high-variance service: tight bulk (P50=0.6s, P90=1s) with extreme tail (P99=60s, P99.9=3h).

    Parameters derived analytically:
      Fast group (99%): lognormal(median=0.6s, sigma=0.40) → P90/P50 = 1.0/0.6
      Slow group (1%):  lognormal(median=1577s, sigma=1.50) → slow group P90 = 3h
    MarkovActivity: ~1% of workloads active at any given time (onset=0.001/s, recovery=0.1/s).
    """
    fast_spec = WorkloadSpec(
        latency_median=0.6,
        latency_sigma=0.40,
        error_scale=50000.0,
        error_shape=1.5,
        noise_sigma=0.01,
    )
    slow_spec = WorkloadSpec(
        latency_median=1577.0,
        latency_sigma=1.50,
        error_scale=50000.0,
        error_shape=1.5,
        noise_sigma=1.0,
    )
    activity = MarkovActivity(onset_rate=onset_rate, recovery_rate=recovery_rate, initial_active=False)
    share = 1.0 / (n_fast + n_slow)
    entries = (
        [PlantEntry(spec=fast_spec, share=share, activity=activity) for _ in range(n_fast)] +
        [PlantEntry(spec=slow_spec, share=share, activity=activity) for _ in range(n_slow)]
    )
    return PlantProfile(name="high_variance", entries=entries)


LATENCY_VARIANCE_SPECTRUM: list[PlantProfile] = [
    _spectrum_profile("variance_v1", sigma=0.1),   # P99.9 ≈ 0.14s
    _spectrum_profile("variance_v2", sigma=0.3),   # P99.9 ≈ 0.25s
    _spectrum_profile("variance_v3", sigma=0.6),   # P99.9 ≈ 0.64s
    _spectrum_profile("variance_v4", sigma=1.0),   # P99.9 ≈ 2.20s
    _spectrum_profile("variance_v5", sigma=1.5),   # P99.9 ≈ 10.3s
]
