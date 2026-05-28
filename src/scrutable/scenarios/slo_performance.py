from __future__ import annotations
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor
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
    precision: float      # TP / (TP + FP): fraction of alerts that fired on disturbance windows
    recall: float         # TP / (TP + FN): fraction of disturbance windows that fired
    fpr: float            # FP / (FP + TN): fraction of clean windows that fired
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

    tp = 0
    fp = 0
    tn = 0
    fn = 0
    detection_latencies: list[float] = []

    t = 0.0
    while t + window_size <= total_duration:
        responses = buf.window(t, t + window_size)
        if responses:
            fired = bool(detector.detect(responses))
            # disturbance window if any overlap with [burn_in, total_duration)
            is_disturbance = t + window_size > burn_in
            if is_disturbance:
                if fired:
                    tp += 1
                    detection_latencies.append(max(0.0, t - burn_in))
                else:
                    fn += 1
            else:
                if fired:
                    fp += 1
                else:
                    tn += 1
        t += window_size

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    mean_det = float(np.mean(detection_latencies)) if detection_latencies else None

    # extract sigma from profile (deterministic profiles have lognormal_sigma=0)
    import math
    sigma = math.exp(profile.latency_sigma.lognormal_mean)

    return PerformancePoint(
        profile_name=profile.name,
        sigma=sigma,
        window_size=window_size,
        precision=precision,
        recall=recall,
        fpr=fpr,
        mean_detection_latency=mean_det,
    )


def _run_one_kwargs(kwargs: dict) -> PerformancePoint:
    return _run_one(**kwargs)


def sweep_slo_performance(
    profiles: list[WorkloadProfile],
    window_sizes: list[float],
    seed: int = 42,
    rate: float = 5.0,
    n_workloads: int = 10,
    burn_in: float = 120.0,
    post_disturbance: float = 60.0,
    disturbance_addend: float = 0.8,
    disturbance_coverage: float = 0.5,
    calibration_multiplier: float = 2.0,
    percentile: float = 99.9,
    workers: int = 1,
) -> list[PerformancePoint]:
    all_kwargs = [
        dict(
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
        for profile in profiles
        for ws in window_sizes
    ]
    if workers == 1:
        return [_run_one(**kw) for kw in all_kwargs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_run_one_kwargs, all_kwargs))
