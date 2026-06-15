from __future__ import annotations
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from scrutable.plant import PlantConfig, Plant
from scrutable.models import Disturbance, DisturbanceScope
from scrutable.disturbance import TimedDisturbance
from scrutable.engine import SimulationEngine
from scrutable.profiles import PlantEntry, PlantProfile, build_workload_mix
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
    snr: dict[float, float | None]    # SNR per percentile; None if < 2 burn-in windows
    noise: dict[float, float | None]  # std of burn-in per-window estimates per percentile
    signal: dict[float, float | None] # mean(post) - mean(burn-in) per percentile


def _make_plant() -> Plant:
    return Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={
            "r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"],
            "r1c2": ["r1c2n1", "r1c2n2", "r1c2n3"],
        },
    ))


_SNR_PERCENTILES = (50.0, 75.0, 90.0, 99.0, 99.9)


def _run_chunk(
    profile: PlantProfile,
    seed: int,
    total_rate: float,
    total_duration: float,
    disturbance_at: float,
    disturbance_addend: float,
    disturbance_coverage: float,
    disturbance_duration: float | None = None,
) -> "NumpyObservationBuffer":
    """Simulate one workload chunk; return buffer for merging."""
    total_share = sum(e.share for e in profile.entries)
    if abs(total_share - 1.0) > 1e-9:
        normalized = [
            PlantEntry(spec=e.spec, share=e.share / total_share,
                       activity=e.activity, diurnal=e.diurnal)
            for e in profile.entries
        ]
        profile = PlantProfile(name=profile.name, entries=normalized)
        total_rate = total_rate * total_share
    plant = _make_plant()
    mix = build_workload_mix(profile, total_rate=total_rate, period=3600.0)
    engine = SimulationEngine(infra=plant, mix=mix, seed=seed)
    disturbance = Disturbance(
        disturbance_id="perf-sweep",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=disturbance_coverage),
        node_effects={"latency_addend": disturbance_addend},
    )
    remove_at = disturbance_at + disturbance_duration if disturbance_duration is not None else None
    engine.add_timed_disturbance(TimedDisturbance(disturbance=disturbance, inject_at=disturbance_at, remove_at=remove_at))
    engine.run(total_duration)
    return engine.buffer


def _run_chunk_kwargs(kwargs: dict) -> "NumpyObservationBuffer":
    return _run_chunk(**kwargs)


def _run_chunk_by_index(
    profile_factory: str,
    chunk_index: int,
    n_chunks: int,
    profile_seed: int,
    sim_seed: int,
    total_rate: float,
    total_duration: float,
    disturbance_at: float,
    disturbance_addend: float,
    disturbance_coverage: float,
    disturbance_duration: float | None = None,
) -> "NumpyObservationBuffer":
    """Reconstruct profile slice inside the worker to avoid pickling large profiles."""
    from scrutable.profiles import SPHERICAL_COW, make_long_tail, split_profile
    if profile_factory == "spherical_cow":
        profile = SPHERICAL_COW
    elif profile_factory == "long_tail":
        profile = make_long_tail(rng=__import__("numpy").random.default_rng(profile_seed))
    else:
        raise ValueError(f"Unknown profile_factory: {profile_factory!r}")
    chunks = split_profile(profile, n_chunks)
    return _run_chunk(
        profile=chunks[chunk_index],
        seed=sim_seed,
        total_rate=total_rate,
        total_duration=total_duration,
        disturbance_at=disturbance_at,
        disturbance_addend=disturbance_addend,
        disturbance_coverage=disturbance_coverage,
        disturbance_duration=disturbance_duration,
    )


def _run_chunk_by_index_kwargs(kwargs: dict) -> "NumpyObservationBuffer":
    return _run_chunk_by_index(**kwargs)


def _run_chunk_by_index_histogram_kwargs(kwargs: dict) -> "HistogramBuffer":
    from scrutable.histogram_buffer import HistogramBuffer
    h_keys = {'histogram_percentiles', 'histogram_dt',
               'histogram_latency_lo', 'histogram_latency_hi', 'histogram_n_bins'}
    sim_kwargs = {k: v for k, v in kwargs.items() if k not in h_keys}
    nbuf = _run_chunk_by_index(**sim_kwargs)
    return HistogramBuffer.from_numpy_buffer(
        nbuf,
        total_duration=kwargs['total_duration'],
        percentiles=kwargs['histogram_percentiles'],
        dt=kwargs.get('histogram_dt', 1.0),
        latency_lo=kwargs.get('histogram_latency_lo', 1e-3),
        latency_hi=kwargs.get('histogram_latency_hi', 10.0),
        n_bins=kwargs.get('histogram_n_bins', 200),
    )


def _run_profile_parallel(
    profile: PlantProfile,
    window_sizes: list[float],
    seed: int,
    total_rate: float,
    n_calibration_windows: int,
    post_disturbance: float,
    disturbance_addend: float,
    disturbance_coverage: float,
    target_fpr: float,
    percentile: float,
    simulation_workers: int,
) -> list[PerformancePoint]:
    """Simulate one profile across N worker processes, merge, then analyze."""
    from scrutable.profiles import split_profile
    from scrutable.observations import NumpyObservationBuffer, merge_observation_buffers

    disturbance_at = max(window_sizes) * n_calibration_windows
    total_duration = disturbance_at + post_disturbance

    chunks = split_profile(profile, simulation_workers)
    chunk_kwargs = [
        dict(
            profile=chunk,
            seed=seed + i,
            total_rate=total_rate,
            total_duration=total_duration,
            disturbance_at=disturbance_at,
            disturbance_addend=disturbance_addend,
            disturbance_coverage=disturbance_coverage,
        )
        for i, chunk in enumerate(chunks)
    ]

    with ProcessPoolExecutor(max_workers=simulation_workers) as pool:
        chunk_bufs = list(pool.map(_run_chunk_kwargs, chunk_kwargs))

    buf = merge_observation_buffers(chunk_bufs)

    sigma = profile.entries[0].spec.latency_sigma
    return [
        _analyze_buffer(
            buf=buf,
            profile_name=profile.name,
            sigma=sigma,
            window_size=ws,
            calibration_duration=ws * n_calibration_windows,
            disturbance_at=disturbance_at,
            total_duration=total_duration,
            percentile=percentile,
            target_fpr=target_fpr,
        )
        for ws in window_sizes
    ]


def _analyze_buffer(
    buf,
    profile_name: str,
    sigma: float,
    window_size: float,
    calibration_duration: float,
    disturbance_at: float,
    total_duration: float,
    percentile: float,
    target_fpr: float,
) -> PerformancePoint:
    calibrator = LatencySloCalibrator(target_fpr=target_fpr)
    calibrated = calibrator.calibrate(buf, calibration_end=calibration_duration, percentile=percentile, window_size=window_size)
    detection_target = SloTarget(percentile=percentile, threshold=calibrated.threshold, window_size=window_size)
    sensor = LatencySloSensor(sensor_id="perf", target=detection_target, sampling_period=window_size)
    detector = LatencySloDetector(detector_id="perf", target=detection_target)

    tp = fp = tn = fn = 0
    detection_latencies: list[float] = []
    time_to_first_detection: float | None = None
    burnin_pct: dict[float, list[float]] = {p: [] for p in _SNR_PERCENTILES}
    post_pct: dict[float, list[float]] = {p: [] for p in _SNR_PERCENTILES}

    t = 0.0
    while t + window_size <= total_duration:
        window = buf.window(t, t + window_size)
        if window:
            signals = sensor.measure(window)
            fired = bool(detector.detect(signals))
            is_disturbance = t >= disturbance_at
            bucket = post_pct if is_disturbance else burnin_pct
            for p in _SNR_PERCENTILES:
                bucket[p].append(window.percentile(p))
            if is_disturbance:
                if fired:
                    tp += 1
                    dl = (t + window_size) - disturbance_at
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
    noise_out: dict[float, float | None] = {}
    signal_out: dict[float, float | None] = {}
    for p in _SNR_PERCENTILES:
        bn, po = burnin_pct[p], post_pct[p]
        if len(bn) >= 2 and po:
            n = float(np.std(bn, ddof=1))
            s = float(np.mean(po)) - float(np.mean(bn))
            snr[p] = s / n if n > 0 else float("inf")
            noise_out[p] = n
            signal_out[p] = s
        else:
            snr[p] = None
            noise_out[p] = None
            signal_out[p] = None

    return PerformancePoint(
        profile_name=profile_name,
        sigma=sigma,
        window_size=window_size,
        precision=precision,
        recall=recall,
        fpr=fpr,
        mean_detection_latency=mean_det,
        time_to_first_detection=time_to_first_detection,
        snr=snr,
        noise=noise_out,
        signal=signal_out,
    )


def _run_profile(
    profile: PlantProfile,
    window_sizes: list[float],
    seed: int,
    total_rate: float,
    n_calibration_windows: int,
    post_disturbance: float,
    disturbance_addend: float,
    disturbance_coverage: float,
    target_fpr: float,
    percentile: float,
) -> list[PerformancePoint]:
    """Run one simulation and re-analyze at each window size."""
    disturbance_at = max(window_sizes) * n_calibration_windows
    total_duration = disturbance_at + post_disturbance

    plant = _make_plant()
    mix = build_workload_mix(profile, total_rate=total_rate, period=3600.0)
    engine = SimulationEngine(infra=plant, mix=mix, seed=seed)
    disturbance = Disturbance(
        disturbance_id="perf-sweep",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=disturbance_coverage),
        node_effects={"latency_addend": disturbance_addend},
    )
    engine.add_timed_disturbance(TimedDisturbance(disturbance=disturbance, inject_at=disturbance_at))
    engine.run(total_duration)

    buf = engine.buffer
    sigma = profile.entries[0].spec.latency_sigma
    return [
        _analyze_buffer(
            buf=buf,
            profile_name=profile.name,
            sigma=sigma,
            window_size=ws,
            calibration_duration=ws * n_calibration_windows,
            disturbance_at=disturbance_at,
            total_duration=total_duration,
            percentile=percentile,
            target_fpr=target_fpr,
        )
        for ws in window_sizes
    ]


def _run_profile_kwargs(kwargs: dict) -> list[PerformancePoint]:
    return _run_profile(**kwargs)


def sweep_slo_performance(
    profiles: list[PlantProfile],
    window_sizes: list[float],
    seed: int = 42,
    total_rate: float = 5.0,
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
            window_sizes=window_sizes,
            seed=seed,
            total_rate=total_rate,
            n_calibration_windows=n_calibration_windows,
            post_disturbance=post_disturbance,
            disturbance_addend=disturbance_addend,
            disturbance_coverage=disturbance_coverage,
            target_fpr=target_fpr,
            percentile=percentile,
        )
        for profile in profiles
    ]
    if workers == 1:
        results = []
        for kw in all_kwargs:
            results.extend(_run_profile(**kw))
        return results
    with ProcessPoolExecutor(max_workers=workers) as pool:
        nested = list(pool.map(_run_profile_kwargs, all_kwargs))
    return [pt for pts in nested for pt in pts]
