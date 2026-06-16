import pytest
import numpy as np
from scrutable.plant import PlantConfig, Plant
from scrutable.engine import SimulationEngine
from scrutable.traffic import WorkloadEntry, WorkloadMix
from scrutable.models import WorkloadModel, Disturbance, DisturbanceScope
from scrutable.rollout import AlarmLog
from scrutable.pipeline import ChangeSource, ReleaseBundler, RemediationCycle, RolloutController


def _plant() -> Plant:
    return Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["canary", "prod"]},
        nodes={"canary": ["canary-n1"], "prod": ["prod-n1"]},
    ))


def _engine(plant: Plant) -> SimulationEngine:
    model = WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    )
    mix = WorkloadMix(
        total_rate=100.0,
        period=3600.0,
        entries=[WorkloadEntry(model=model, share=1.0)],
    )
    return SimulationEngine(infra=plant, mix=mix, seed=42)


def _factory(change_id: str) -> Disturbance:
    return Disturbance(
        disturbance_id=f"bug-{change_id}",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_addend": 0.3},
    )


def test_pipeline_registered_and_runs():
    plant = _plant()
    engine = _engine(plant)
    alarm_log = AlarmLog()

    pipeline = RolloutController(
        change_stream=ChangeSource(change_rate=5.0, bug_fraction=0.0, disturbance_factory=_factory),
        bundler=ReleaseBundler(bundle_size=3),
        cluster_order=["canary", "prod"],
        bake_duration=2.0,
        alarm_log=alarm_log,
        debug_cycle=RemediationCycle(median_seconds=1.0, sigma=0.1),
        rollback_duration=1.0,
    )
    engine.add_rollout_pipeline(pipeline)
    engine.run(30.0)

    assert pipeline.releases_attempted >= 1


def test_benign_pipeline_all_releases_complete():
    plant = _plant()
    engine = _engine(plant)
    alarm_log = AlarmLog()

    pipeline = RolloutController(
        change_stream=ChangeSource(change_rate=10.0, bug_fraction=0.0, disturbance_factory=_factory),
        bundler=ReleaseBundler(bundle_size=2),
        cluster_order=["canary", "prod"],
        bake_duration=1.0,
        alarm_log=alarm_log,
        debug_cycle=RemediationCycle(median_seconds=1.0, sigma=0.1),
        rollback_duration=0.5,
    )
    engine.add_rollout_pipeline(pipeline)
    engine.run(60.0)

    assert pipeline.releases_attempted >= 3
    assert pipeline.releases_rolled_back == 0
    # In benign case, all or nearly all attempted releases should complete
    # (last one may not if it starts near the end of simulation)
    assert pipeline.releases_completed >= pipeline.releases_attempted - 1
