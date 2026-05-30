from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from scrutable.plant import PlantConfig, Plant
from scrutable.workload import WorkloadRegistry
from scrutable.models import Disturbance, DisturbanceScope
from scrutable.disturbance import TimedDisturbance
from scrutable.synthesizer import InputConfig
from scrutable.engine import SimulationEngine
from scrutable.profiles import WorkloadProfile, sample_workload
from scrutable.detectors.slo import LatencySloCalibrator, LatencySloDetector, SloTarget


@dataclass
class TimeWindow:
    t_start: float
    t_end: float
    p50: float
    p90: float
    p99: float
    p999: float
    count: int


@dataclass
class ScenarioResult:
    profile_name: str
    windows: list[TimeWindow]
    slo_threshold_p999: float
    disturbance_at: float
    disturbance_addend: float
    detection_time: float | None  # None if not detected


def _make_plant() -> Plant:
    return Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={
            "r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"],
            "r1c2": ["r1c2n1", "r1c2n2", "r1c2n3"],
        },
    ))


def _compute_window(responses, t_start: float, t_end: float) -> TimeWindow | None:
    # responses are already arrival-windowed by the buffer; no issued_at re-filter needed
    latencies = np.array([r.latency for r in responses])
    if len(latencies) < 10:
        return None
    return TimeWindow(
        t_start=t_start,
        t_end=t_end,
        p50=float(np.percentile(latencies, 50)),
        p90=float(np.percentile(latencies, 90)),
        p99=float(np.percentile(latencies, 99)),
        p999=float(np.percentile(latencies, 99.9)),
        count=len(latencies),
    )


def run_slo_scenario(
    profile: WorkloadProfile,
    seed: int = 42,
    rate: float = 1000.0,       # req/s per workload
    calibration_duration: float = 10.0,  # seconds of baseline before disturbance
    post_disturbance: float = 20.0,  # seconds after disturbance injection
    n_workloads: int = 10,
    disturbance_addend: float = 1.0,  # additive latency penalty in seconds on affected nodes
    disturbance_coverage: float = 0.5,  # fraction of nodes affected
    window_size: float = 1.0,   # time-series window width in seconds
) -> ScenarioResult:
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
        disturbance_id="slo-demo",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=disturbance_coverage),
        node_effects={"latency_addend": disturbance_addend},
    )
    engine.add_timed_disturbance(TimedDisturbance(
        disturbance=disturbance,
        inject_at=calibration_duration,
    ))

    total_duration = calibration_duration + post_disturbance
    engine.run(total_duration)

    buf = engine.buffer
    calibrator = LatencySloCalibrator(multiplier=2.0)
    target = calibrator.calibrate(buf, calibration_end=calibration_duration, percentile=99.9, window_size=window_size)

    detector_calibrated = LatencySloDetector(
        detector_id="slo",
        target=target,
        tick_interval=window_size,
    )

    windows: list[TimeWindow] = []
    detection_time: float | None = None
    t = 0.0
    while t + window_size <= total_duration:
        tw = _compute_window(buf.window(t, t + window_size), t, t + window_size)
        if tw is not None:
            windows.append(tw)
            if detection_time is None and t >= calibration_duration:
                inferences = detector_calibrated.detect(buf.window(t, t + window_size))
                if inferences:
                    detection_time = t + window_size
        t += window_size

    return ScenarioResult(
        profile_name=profile.name,
        windows=windows,
        slo_threshold_p999=target.threshold,
        disturbance_at=calibration_duration,
        disturbance_addend=disturbance_addend,
        detection_time=detection_time,
    )
