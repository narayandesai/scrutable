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
    slo_target: SloTarget
    calibration_duration_s: float
    effective_fpr: float


def run_canary_rollout(
    change_rate: float = 1.0 / 3600.0,
    bug_fraction: float = 0.2,
    bundle_size: int = 3,
    bake_duration: float = 3600.0,
    rollback_duration: float = 3600.0,
    debug_median_s: float = 6.0 * 3600.0,
    debug_sigma: float = 0.84,
    latency_disturbance_addend: float = 0.3,
    calibration_duration: float | None = None,
    slo_target: SloTarget | None = None,
    total_duration: float = 30.0 * 24 * 3600.0,
    total_rate: float = 1000.0,
    percentile: float = 99.9,
    target_fpr: float = 0.001,
    max_daily_alerts: float | None = 4.0,
    max_alerts_per_bake: float | None = 0.5,
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

    _calibrator_proto = LatencySloCalibrator(
        target_fpr=target_fpr,
        max_daily_alerts=max_daily_alerts,
        max_alerts_per_bake=max_alerts_per_bake,
        bake_duration=bake_duration,
    )
    _eff_fpr = _calibrator_proto._effective_fpr(window_size)

    if slo_target is not None:
        # Caller supplies a pre-calibrated target — skip calibration phase.
        target = slo_target
        calibration_duration = calibration_duration or 0.0
    else:
        # Derive calibration_duration from effective FPR (n ≈ 2 / effective_fpr windows).
        if calibration_duration is None:
            n_cal_windows = max(50, round(2.0 / _eff_fpr))
            calibration_duration = n_cal_windows * window_size

        # buffer_max_age=window_size keeps the buffer at O(rate × window_size) in memory.
        cal_engine = SimulationEngine(infra=plant, mix=mix, seed=seed, buffer_max_age=window_size)
        recorder = PercentileRecorderSensor(percentile=percentile, window_size=window_size)
        cal_engine.add_sensor(recorder)
        cal_engine.run(calibration_duration)
        target = _calibrator_proto.calibrate_from_values(
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
        slo_target=target,
        calibration_duration_s=calibration_duration,
        effective_fpr=_eff_fpr,
    )


if __name__ == "__main__":
    _WEEK = 7 * 24 * 3600.0
    _BASE_CHANGES_PER_WEEK = 150.0
    _SHARED = dict(
        bug_fraction=0.01,
        bake_duration=2 * 24 * 3600.0,
        rollback_duration=3600.0,
        debug_median_s=6.0 * 3600.0,
        debug_sigma=0.84,
        window_size=300.0,
        percentile=99.9,
        target_fpr=0.01,
        max_daily_alerts=4.0,
        max_alerts_per_bake=0.5,
        total_rate=10.0,
        total_duration=8 * _WEEK,
        seed=42,
    )

    # Run 100% baseline first — this calibrates the SLO and produces the 100% result.
    print("Calibrating SLO and running 100% baseline... ", end="", flush=True)
    _base = run_canary_rollout(
        change_rate=_BASE_CHANGES_PER_WEEK / _WEEK,
        bundle_size=int(_BASE_CHANGES_PER_WEEK),
        **_SHARED,
    )
    _slo = _base.slo_target
    print("done\n")

    print("=== Parameters ===")
    print(f"  bug_fraction:         {_SHARED['bug_fraction']:.1%}")
    print(f"  base_change_rate:     {_BASE_CHANGES_PER_WEEK:.0f} changes/week")
    print(f"  bake_duration:        {_SHARED['bake_duration']/86400:.1f} days")
    print(f"  rollback_duration:    {_SHARED['rollback_duration']/3600:.1f} h")
    print(f"  debug_median:         {_SHARED['debug_median_s']/3600:.1f} h  "
          f"(sigma={_SHARED['debug_sigma']})")
    print(f"  total_duration:       {_SHARED['total_duration']/_WEEK:.0f} weeks")
    print(f"  total_rate:           {_SHARED['total_rate']:.0f} req/s")
    print(f"\n=== SLO Calibration ===")
    print(f"  window_size:          {_SHARED['window_size']:.0f} s  "
          f"({_SHARED['window_size']/60:.0f} min)")
    print(f"  percentile:           P{_SHARED['percentile']}")
    print(f"  target_fpr:           {_SHARED['target_fpr']}  (per window)")
    print(f"  max_daily_alerts:     {_SHARED['max_daily_alerts']}")
    print(f"  max_alerts_per_bake:  {_SHARED['max_alerts_per_bake']}")
    print(f"  effective_fpr:        {_base.effective_fpr:.2e}  (binding constraint)")
    print(f"  calibration_duration: {_base.calibration_duration_s/86400:.1f} days  "
          f"({_base.calibration_duration_s/_SHARED['window_size']:.0f} windows)")
    print(f"  slo_threshold:        {_slo.threshold:.4f} s  (latency P{_slo.percentile})")

    print("\n=== Results ===")
    hdr = f"  {'Scale':>6}  {'Bundle':>6}  {'P(bug)':>7}  {'Attempted':>9}  "
    hdr += f"{'Rollback%':>9}  {'Debug median':>13}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    # 100% result already in hand; run 50% and 150% with the shared SLO target.
    _scale_results = {1.0: _base}
    for scale in [0.5, 1.5]:
        changes_per_week = _BASE_CHANGES_PER_WEEK * scale
        bundle_size = max(1, round(changes_per_week))
        print(f"  Running {int(scale*100)}%... ", end="", flush=True)
        _scale_results[scale] = run_canary_rollout(
            change_rate=changes_per_week / _WEEK,
            bundle_size=bundle_size,
            slo_target=_slo,
            **_SHARED,
        )
        print("done")

    print()
    for scale in [0.5, 1.0, 1.5]:
        r = _scale_results[scale]
        changes_per_week = _BASE_CHANGES_PER_WEEK * scale
        bundle_size = max(1, round(changes_per_week))
        p_bug = 1 - (1 - _SHARED['bug_fraction']) ** bundle_size
        rollback_rate = (
            r.releases_rolled_back / r.releases_attempted
            if r.releases_attempted > 0 else 0.0
        )
        debug_med = (
            f"{float(np.median(r.debug_durations_s))/3600:.1f}h"
            if r.debug_durations_s else "n/a"
        )
        print(f"  {int(scale*100):>5}%  {bundle_size:>6}  {p_bug:>7.1%}  "
              f"{r.releases_attempted:>9}  {rollback_rate:>9.1%}  {debug_med:>13}")
