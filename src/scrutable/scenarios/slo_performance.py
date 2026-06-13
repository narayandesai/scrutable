from __future__ import annotations
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from scrutable.plant import PlantConfig, Plant
from scrutable.models import Disturbance, DisturbanceScope
from scrutable.disturbance import TimedDisturbance
from scrutable.engine import SimulationEngine
from scrutable.profiles import PlantProfile, build_workload_mix
from scrutable.detectors.slo import LatencySloCalibrator, LatencySloSensor, LatencySloDetector, SloTarget


@dataclass
class PerformancePoint:
    profile_name: str
    sigma: float          # latency_sigma of the profile (diagnostic label)
    window_size: float    # SloTarget window_size used
    precision: float      # TP / (TP + FP): fraction of alerts that fired on disturbance windows
    recall: float         # TP / (TP + FN): fraction of disturbance windows that fired
    fpr: float            # FP / (FP + TN): fraction of clean windows that fired
    mean_detection_latency: float | None   # mean seconds from disturbance to end of firing window
    time_to_first_detection: float | None  # seconds from disturbance to end of first firing window
    snr: dict[float, float | None]  # SNR per percentile; value is None if < 2 burn-in windows


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
    profile: PlantProfile,
    window_size: float,
    seed: int,
    rate: float,
    calibration_duration: float,
    post_disturbance: float,
    disturbance_addend: float,
    disturbance_coverage: float,
    target_fpr: float,
    percentile: float,
) -> PerformancePoint:
    plant = _make_plant()
    mix = build_workload_mix(profile, total_rate=rate * len(profile.entries), period=3600.0)

    engine = SimulationEngine(infra=plant, mix=mix, seed=seed)

    disturbance = Disturbance(
        disturbance_id="perf-sweep",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=disturbance_coverage),
        node_effects={"latency_addend": disturbance_addend},
    )
    engine.add_timed_disturbance(TimedDisturbance(disturbance=disturbance, inject_at=calibration_duration))

    total_duration = calibration_duration + post_disturbance
    engine.run(total_duration)

    buf = engine.buffer
    calibrator = LatencySloCalibrator(target_fpr=target_fpr)
    calibrated = calibrator.calibrate(buf, calibration_end=calibration_duration, percentile=percentile, window_size=window_size)
    detection_target = SloTarget(
        percentile=percentile,
        threshold=calibrated.threshold,
        window_size=window_size,
    )
    sensor = LatencySloSensor(sensor_id="perf", target=detection_target, sampling_period=window_size)
    detector = LatencySloDetector(detector_id="perf", target=detection_target)

    _SNR_PERCENTILES = (50.0, 75.0, 90.0, 99.0, 99.9)
    tp = 0
    fp = 0
    tn = 0
    fn = 0
    detection_latencies: list[float] = []
    time_to_first_detection: float | None = None
    burnin_pct: dict[float, list[float]] = {p: [] for p in _SNR_PERCENTILES}
    post_pct: dict[float, list[float]] = {p: [] for p in _SNR_PERCENTILES}

    t = 0.0
    while t + window_size <= total_duration:
        responses = buf.window(t, t + window_size)
        if responses:
            signals = sensor.measure(responses)
            alarms = detector.detect(signals)
            fired = bool(alarms)
            is_disturbance = t + window_size > calibration_duration
            latencies = np.array([r.latency for r in responses])
            bucket = post_pct if is_disturbance else burnin_pct
            for p in _SNR_PERCENTILES:
                bucket[p].append(float(np.percentile(latencies, p)))
            if is_disturbance:
                if fired:
                    tp += 1
                    dl = (t + window_size) - calibration_duration
                    detection_latencies.append(dl)
                    if time_to_first_detection is None:
                        time_to_first_detection = dl
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

    snr: dict[float, float | None] = {}
    for p in _SNR_PERCENTILES:
        bn, po = burnin_pct[p], post_pct[p]
        if len(bn) >= 2 and po:
            noise = float(np.std(bn, ddof=1))
            sig = float(np.mean(po)) - float(np.mean(bn))
            snr[p] = sig / noise if noise > 0 else float("inf")
        else:
            snr[p] = None

    sigma = profile.entries[0].spec.latency_sigma

    return PerformancePoint(
        profile_name=profile.name,
        sigma=sigma,
        window_size=window_size,
        precision=precision,
        recall=recall,
        fpr=fpr,
        mean_detection_latency=mean_det,
        time_to_first_detection=time_to_first_detection,
        snr=snr,
    )


def _run_one_kwargs(kwargs: dict) -> PerformancePoint:
    return _run_one(**kwargs)


def sweep_slo_performance(
    profiles: list[PlantProfile],
    window_sizes: list[float],
    seed: int = 42,
    rate: float = 5.0,
    n_calibration_windows: int = 120,
    post_disturbance: float = 60.0,
    disturbance_addend: float = 0.3,
    disturbance_coverage: float = 0.5,
    target_fpr: float = 0.001,
    percentile: float = 99.9,
    workers: int = 1,
) -> list[PerformancePoint]:
    all_kwargs = [
        dict(
            profile=profile,
            window_size=ws,
            seed=seed,
            rate=rate,
            calibration_duration=n_calibration_windows * ws,
            post_disturbance=post_disturbance,
            disturbance_addend=disturbance_addend,
            disturbance_coverage=disturbance_coverage,
            target_fpr=target_fpr,
            percentile=percentile,
        )
        for profile in profiles
        for ws in window_sizes
    ]
    if workers == 1:
        return [_run_one(**kw) for kw in all_kwargs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_run_one_kwargs, all_kwargs))
