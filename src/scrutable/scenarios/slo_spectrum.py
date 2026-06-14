from __future__ import annotations
from dataclasses import dataclass
from scrutable.plant import PlantConfig, Plant
from scrutable.models import Disturbance, DisturbanceScope
from scrutable.disturbance import TimedDisturbance
from scrutable.engine import SimulationEngine
from scrutable.profiles import PlantProfile, build_workload_mix
from scrutable.detectors.slo import LatencySloCalibrator, LatencySloSensor, LatencySloDetector, SloTarget
from scrutable.window_result import WindowResult


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


def _compute_window(w: WindowResult, t_start: float, t_end: float) -> TimeWindow | None:
    if len(w) < 10:
        return None
    return TimeWindow(
        t_start=t_start,
        t_end=t_end,
        p50=w.percentile(50),
        p90=w.percentile(90),
        p99=w.percentile(99),
        p999=w.percentile(99.9),
        count=len(w),
    )


def run_slo_scenario(
    profile: PlantProfile,
    seed: int = 42,
    rate: float = 1000.0,       # req/s per workload
    calibration_duration: float = 10.0,
    post_disturbance: float = 20.0,
    disturbance_addend: float = 1.0,
    disturbance_coverage: float = 0.5,
    window_size: float = 1.0,
) -> ScenarioResult:
    plant = _make_plant()
    mix = build_workload_mix(profile, total_rate=rate * len(profile.entries), period=3600.0)

    engine = SimulationEngine(infra=plant, mix=mix, seed=seed)

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
    calibrator = LatencySloCalibrator()
    target = calibrator.calibrate(buf, calibration_end=calibration_duration, percentile=99.9, window_size=window_size)

    sensor_calibrated = LatencySloSensor(
        sensor_id="slo",
        target=target,
        sampling_period=window_size,
    )
    detector_calibrated = LatencySloDetector(
        detector_id="slo",
        target=target,
    )

    windows: list[TimeWindow] = []
    detection_time: float | None = None
    t = 0.0
    while t + window_size <= total_duration:
        tw = _compute_window(buf.window(t, t + window_size), t, t + window_size)
        if tw is not None:
            windows.append(tw)
            if detection_time is None and t >= calibration_duration:
                signals = sensor_calibrated.measure(buf.window(t, t + window_size))
                alarms = detector_calibrated.detect(signals)
                if alarms:
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
