from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.plant import PlantConfig, Plant
from scrutable.workload import WorkloadRegistry
from scrutable.models import Disturbance, DisturbanceScope
from scrutable.disturbance import TimedDisturbance
from scrutable.synthesizer import InputConfig
from scrutable.engine import SimulationEngine
from scrutable.profiles import WorkloadProfile, sample_workload
from scrutable.detectors.slo import BurnInCalibrator, LatencySloDetector, SloTarget


@dataclass
class PerformancePoint:
    profile_name: str
    sigma: float          # latency_sigma of the profile (diagnostic label)
    window_size: float    # SloTarget window_size used
    fpr: float            # false positive rate: fraction of burn-in windows that fired
    recall: float         # fraction of post-disturbance windows that fired
    mean_detection_latency: float | None  # seconds after disturbance_at, None if recall=0


def _make_plant() -> Plant:
    return Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={
            "r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"],
            "r1c2": ["r1c2n1", "r1c2n2", "r1c2n3"],
        },
    ))


def _run_one(
    profile: WorkloadProfile,
    window_size: float,
    seed: int,
    rate: float,
    n_workloads: int,
    burn_in: float,
    post_disturbance: float,
    disturbance_addend: float,
    disturbance_coverage: float,
    calibration_multiplier: float,
    percentile: float,
) -> PerformancePoint:
    rng = np.random.default_rng(seed)
    plant = _make_plant()

    registry = WorkloadRegistry()
    rates: dict[str, float] = {}
    for i in range(n_workloads):
        wid = f"{profile.name}-{i}"
        registry.register(sample_workload(profile, wid, rng))
        rates[wid] = rate

    engine = SimulationEngine(
        infra=plant,
        registry=registry,
        synth_config=InputConfig(workload_rates=rates),
        seed=seed,
    )

    disturbance = Disturbance(
        disturbance_id="perf-sweep",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=disturbance_coverage),
        node_effects={"latency_addend": disturbance_addend},
    )
    engine.add_timed_disturbance(TimedDisturbance(disturbance=disturbance, inject_at=burn_in))

    total_duration = burn_in + post_disturbance
    engine.run(total_duration)

    buf = engine.buffer
    # Calibrate on the full burn-in period to get a stable long-run threshold.
    # Detection window is varied independently — this is the tradeoff we're measuring.
    calibrator = BurnInCalibrator(multiplier=calibration_multiplier)
    calibrated = calibrator.calibrate(buf, burn_in_end=burn_in, percentile=percentile, window_size=burn_in)
    detection_target = SloTarget(
        percentile=percentile,
        threshold=calibrated.threshold,
        window_size=window_size,
    )
    detector = LatencySloDetector(detector_id="perf", target=detection_target, tick_interval=window_size)

    burn_in_alerts = 0
    burn_in_windows = 0
    post_alerts = 0
    post_windows = 0
    detection_latencies: list[float] = []

    t = 0.0
    while t + window_size <= total_duration:
        responses = buf.window(t, t + window_size)
        if responses:
            fired = bool(detector.detect(responses))
            if t + window_size <= burn_in:
                burn_in_windows += 1
                if fired:
                    burn_in_alerts += 1
            elif t >= burn_in:
                post_windows += 1
                if fired:
                    post_alerts += 1
                    detection_latencies.append(t - burn_in)
        t += window_size

    fpr = burn_in_alerts / burn_in_windows if burn_in_windows > 0 else 0.0
    recall = post_alerts / post_windows if post_windows > 0 else 0.0
    mean_det = float(np.mean(detection_latencies)) if detection_latencies else None

    # extract sigma from profile (deterministic profiles have lognormal_sigma=0)
    import math
    sigma = math.exp(profile.latency_sigma.lognormal_mean)

    return PerformancePoint(
        profile_name=profile.name,
        sigma=sigma,
        window_size=window_size,
        fpr=fpr,
        recall=recall,
        mean_detection_latency=mean_det,
    )


def sweep_slo_performance(
    profiles: list[WorkloadProfile],
    window_sizes: list[float],
    seed: int = 42,
    rate: float = 5.0,        # low rate so detection-window sample count matters
    n_workloads: int = 10,
    burn_in: float = 120.0,   # long enough for stable full-burn-in calibration on v5
    post_disturbance: float = 60.0,
    disturbance_addend: float = 0.8,   # weaker signal: marginal for v3, invisible for v4+
    disturbance_coverage: float = 0.5,
    calibration_multiplier: float = 2.0,
    percentile: float = 99.9,
) -> list[PerformancePoint]:
    results = []
    for profile in profiles:
        for ws in window_sizes:
            pt = _run_one(
                profile=profile,
                window_size=ws,
                seed=seed,
                rate=rate,
                n_workloads=n_workloads,
                burn_in=burn_in,
                post_disturbance=post_disturbance,
                disturbance_addend=disturbance_addend,
                disturbance_coverage=disturbance_coverage,
                calibration_multiplier=calibration_multiplier,
                percentile=percentile,
            )
            results.append(pt)
    return results
