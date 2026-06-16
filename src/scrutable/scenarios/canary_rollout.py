from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.plant import PlantConfig, Plant
from scrutable.engine import SimulationEngine
from scrutable.traffic import WorkloadEntry, WorkloadMix
from scrutable.models import Disturbance, DisturbanceScope, WorkloadModel
from scrutable.rollout import AlarmLog
from scrutable.pipeline import ChangeSource, ReleaseBundler, RemediationCycle, RolloutController
from scrutable.detectors.slo import (
    LatencySloCalibrator,
    LatencySloSensor,
    LatencySloDetector,
    PercentileRecorderSensor,
    SloTarget,
)


@dataclass
class CanaryRolloutResult:
    releases_attempted: int
    releases_completed: int
    releases_rolled_back: int
    debug_durations_s: list[float]
    total_sim_duration_s: float


def run_canary_rollout(
    change_rate: float = 1.0 / 3600.0,
    bug_fraction: float = 0.2,
    bundle_size: int = 3,
    bake_duration: float = 3600.0,
    rollback_duration: float = 3600.0,
    debug_median_s: float = 6.0 * 3600.0,
    debug_sigma: float = 0.84,
    latency_disturbance_addend: float = 0.3,
    calibration_duration: float = 3600.0,
    total_duration: float = 30.0 * 24 * 3600.0,
    total_rate: float = 1000.0,
    percentile: float = 99.9,
    target_fpr: float = 0.001,
    window_size: float = 60.0,
    seed: int = 42,
) -> CanaryRolloutResult:
    plant = Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["canary", "prod"]},
        nodes={
            "canary": [f"canary-n{i}" for i in range(4)],
            "prod": [f"prod-n{i}" for i in range(16)],
        },
    ))

    model = WorkloadModel(
        workload_id="api",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    )
    mix = WorkloadMix(
        total_rate=total_rate,
        period=3600.0,
        entries=[WorkloadEntry(model=model, share=1.0)],
    )

    # Calibration: record per-window percentile values without accumulating raw obs.
    # buffer_max_age=window_size keeps the buffer at O(rate × window_size) in memory.
    cal_engine = SimulationEngine(infra=plant, mix=mix, seed=seed, buffer_max_age=window_size)
    recorder = PercentileRecorderSensor(percentile=percentile, window_size=window_size)
    cal_engine.add_sensor(recorder)
    cal_engine.run(calibration_duration)

    calibrator = LatencySloCalibrator(target_fpr=target_fpr)
    target: SloTarget = calibrator.calibrate_from_values(
        values=recorder.recorded_values,
        percentile=percentile,
        window_size=window_size,
    )

    plant2 = Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["canary", "prod"]},
        nodes={
            "canary": [f"canary-n{i}" for i in range(4)],
            "prod": [f"prod-n{i}" for i in range(16)],
        },
    ))
    engine = SimulationEngine(infra=plant2, mix=mix, seed=seed + 1, buffer_max_age=window_size)

    sensor = LatencySloSensor(
        sensor_id="canary-slo",
        target=target,
        sampling_period=window_size,
    )
    detector = LatencySloDetector(detector_id="canary-slo", target=target)
    engine.add_sensor(sensor)
    engine.add_detector(detector)

    def make_disturbance(change_id: str) -> Disturbance:
        return Disturbance(
            disturbance_id=f"bug-{change_id}",
            scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
            node_effects={"latency_addend": latency_disturbance_addend},
        )

    alarm_log = AlarmLog()
    pipeline = RolloutController(
        change_stream=ChangeSource(
            change_rate=change_rate,
            bug_fraction=bug_fraction,
            disturbance_factory=make_disturbance,
        ),
        bundler=ReleaseBundler(bundle_size=bundle_size),
        cluster_order=["canary", "prod"],
        bake_duration=bake_duration,
        alarm_log=alarm_log,
        debug_cycle=RemediationCycle(median_seconds=debug_median_s, sigma=debug_sigma),
        rollback_duration=rollback_duration,
    )
    engine.add_rollout_pipeline(pipeline)
    engine.run(total_duration)

    return CanaryRolloutResult(
        releases_attempted=pipeline.releases_attempted,
        releases_completed=pipeline.releases_completed,
        releases_rolled_back=pipeline.releases_rolled_back,
        debug_durations_s=list(pipeline.debug_durations),
        total_sim_duration_s=total_duration,
    )


if __name__ == "__main__":
    result = run_canary_rollout(
        total_duration=7.0 * 24 * 3600.0,
        seed=42,
    )
    print(f"Releases attempted:    {result.releases_attempted}")
    print(f"Releases completed:    {result.releases_completed}")
    print(f"Releases rolled back:  {result.releases_rolled_back}")
    if result.debug_durations_s:
        median_h = float(np.median(result.debug_durations_s)) / 3600.0
        print(f"Median debug duration: {median_h:.1f}h")
    rollback_rate = (
        result.releases_rolled_back / result.releases_attempted
        if result.releases_attempted > 0 else 0.0
    )
    print(f"Rollback rate:         {rollback_rate:.1%}")
