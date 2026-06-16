import pytest
import numpy as np
from collections import deque
from scrutable.pipeline import ChangeStream, ReleaseBundler, RolloutPipeline
from scrutable.rollout import AlarmLog
from scrutable.plant import PlantConfig, Plant
from scrutable.event_loop import EventLoop
from scrutable.models import Disturbance, DisturbanceScope, ReleaseChange
from scrutable.pipeline import DebugCycle


def _factory(change_id: str) -> Disturbance:
    return Disturbance(
        disturbance_id=f"bug-{change_id}",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_addend": 0.3},
    )


def _two_cluster_plant() -> Plant:
    return Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["canary", "prod"]},
        nodes={"canary": ["canary-n1"], "prod": ["prod-n1"]},
    ))


def test_change_stream_no_bug_when_fraction_zero():
    rng = np.random.default_rng(42)
    stream = ChangeStream(change_rate=1.0, bug_fraction=0.0, disturbance_factory=_factory)
    change = stream.generate_change("ch1", rng)
    assert change.change_id == "ch1"
    assert change.disturbance is None


def test_change_stream_always_bug_when_fraction_one():
    rng = np.random.default_rng(42)
    stream = ChangeStream(change_rate=1.0, bug_fraction=1.0, disturbance_factory=_factory)
    change = stream.generate_change("ch1", rng)
    assert change.disturbance is not None
    assert change.disturbance.disturbance_id == "bug-ch1"


def test_change_stream_bug_fraction_statistical():
    rng = np.random.default_rng(0)
    stream = ChangeStream(change_rate=1.0, bug_fraction=0.1, disturbance_factory=_factory)
    n = 2000
    bugs = sum(
        1 for i in range(n)
        if stream.generate_change(f"ch{i}", rng).disturbance is not None
    )
    # 10% ± 3σ ≈ 10% ± 1.4% at n=2000
    assert 160 <= bugs <= 240


def test_change_stream_next_arrival_delay_positive():
    rng = np.random.default_rng(42)
    stream = ChangeStream(change_rate=2.0, bug_fraction=0.1, disturbance_factory=_factory)
    delay = stream.next_arrival_delay(rng)
    assert delay > 0.0


def test_change_stream_next_arrival_delay_mean():
    rng = np.random.default_rng(0)
    stream = ChangeStream(change_rate=2.0, bug_fraction=0.1, disturbance_factory=_factory)
    delays = [stream.next_arrival_delay(rng) for _ in range(2000)]
    assert abs(np.mean(delays) - 0.5) < 0.05  # mean should be ~1/rate = 0.5


def test_bundler_returns_none_before_full():
    bundler = ReleaseBundler(bundle_size=3)
    for i in range(2):
        result = bundler.add(ReleaseChange(change_id=f"ch{i}"))
        assert result is None


def test_bundler_returns_release_when_full():
    bundler = ReleaseBundler(bundle_size=3)
    for i in range(2):
        bundler.add(ReleaseChange(change_id=f"ch{i}"))
    release = bundler.add(ReleaseChange(change_id="ch2"))
    assert release is not None
    assert len(release.changes) == 3
    assert [c.change_id for c in release.changes] == ["ch0", "ch1", "ch2"]


def test_bundler_resets_after_flush():
    bundler = ReleaseBundler(bundle_size=2)
    bundler.add(ReleaseChange(change_id="ch0"))
    bundler.add(ReleaseChange(change_id="ch1"))  # flushes
    result = bundler.add(ReleaseChange(change_id="ch2"))
    assert result is None


def test_bundler_release_ids_are_unique():
    bundler = ReleaseBundler(bundle_size=1)
    r1 = bundler.add(ReleaseChange(change_id="ch0"))
    r2 = bundler.add(ReleaseChange(change_id="ch1"))
    assert r1 is not None and r2 is not None
    assert r1.release_id != r2.release_id


def test_debug_cycle_sample_positive():
    from scrutable.pipeline import DebugCycle
    rng = np.random.default_rng(42)
    dc = DebugCycle()
    assert dc.sample_duration(rng) > 0.0


def test_debug_cycle_median_approximately_correct():
    from scrutable.pipeline import DebugCycle
    rng = np.random.default_rng(0)
    dc = DebugCycle(median_seconds=6.0 * 3600.0, sigma=0.84)
    samples = [dc.sample_duration(rng) for _ in range(2000)]
    # median of lognormal(mu, sigma) is exp(mu) = median_seconds
    assert abs(float(np.median(samples)) - 6.0 * 3600.0) / (6.0 * 3600.0) < 0.1


def test_debug_cycle_has_long_tail():
    from scrutable.pipeline import DebugCycle
    rng = np.random.default_rng(0)
    dc = DebugCycle(median_seconds=6.0 * 3600.0, sigma=0.84)
    samples = [dc.sample_duration(rng) for _ in range(2000)]
    p95 = float(np.percentile(samples, 95))
    # with sigma=0.84, P95 ≈ 24h; allow generous range
    assert 12.0 * 3600.0 <= p95 <= 48.0 * 3600.0


def test_pipeline_starts_rollout_after_bundle_fills():
    plant = _two_cluster_plant()
    loop = EventLoop()
    rng = np.random.default_rng(42)
    alarm_log = AlarmLog()
    pipeline = RolloutPipeline(
        change_stream=ChangeStream(change_rate=10.0, bug_fraction=0.0, disturbance_factory=_factory),
        bundler=ReleaseBundler(bundle_size=2),
        cluster_order=["canary", "prod"],
        bake_duration=1.0,
        alarm_log=alarm_log,
        debug_cycle=DebugCycle(median_seconds=2.0, sigma=0.1),
        rollback_duration=1.0,
    )
    registered_rollouts: list = []
    registered_actuators: list = []
    pipeline._activate(
        loop=loop,
        rng=rng,
        add_rollout=lambda r: registered_rollouts.append(r),
        add_actuator=lambda a: registered_actuators.append(a),
    )
    # change_rate=10 means avg 0.1s between changes; bundle_size=2 → release after ~0.2s
    loop.run(until=5.0)
    assert len(registered_rollouts) >= 1
    assert len(registered_actuators) >= 1


def test_pipeline_increments_releases_attempted():
    loop = EventLoop()
    rng = np.random.default_rng(0)
    alarm_log = AlarmLog()
    pipeline = RolloutPipeline(
        change_stream=ChangeStream(change_rate=10.0, bug_fraction=0.0, disturbance_factory=_factory),
        bundler=ReleaseBundler(bundle_size=2),
        cluster_order=["canary", "prod"],
        bake_duration=1.0,
        alarm_log=alarm_log,
        debug_cycle=DebugCycle(median_seconds=1.0, sigma=0.1),
        rollback_duration=1.0,
    )
    pipeline._activate(loop=loop, rng=rng, add_rollout=lambda r: None, add_actuator=lambda a: None)
    loop.run(until=5.0)
    assert pipeline.releases_attempted >= 1


def test_pipeline_queues_release_when_active_rollout_exists():
    loop = EventLoop()
    rng = np.random.default_rng(0)
    alarm_log = AlarmLog()
    # Large bake_duration so rollout stays active while more bundles arrive
    pipeline = RolloutPipeline(
        change_stream=ChangeStream(change_rate=10.0, bug_fraction=0.0, disturbance_factory=_factory),
        bundler=ReleaseBundler(bundle_size=2),
        cluster_order=["canary", "prod"],
        bake_duration=1000.0,
        alarm_log=alarm_log,
        debug_cycle=DebugCycle(median_seconds=1.0, sigma=0.1),
        rollback_duration=1.0,
    )
    pipeline._activate(loop=loop, rng=rng, add_rollout=lambda r: None, add_actuator=lambda a: None)
    loop.run(until=5.0)
    # First release started immediately; subsequent ones queued
    assert pipeline.releases_attempted == 1
    assert len(pipeline._pending) >= 1


def test_pipeline_fixed_release_has_no_disturbances():
    loop = EventLoop()
    rng = np.random.default_rng(42)
    alarm_log = AlarmLog()
    # bug_fraction=1.0: every change has a bug
    pipeline = RolloutPipeline(
        change_stream=ChangeStream(change_rate=10.0, bug_fraction=1.0, disturbance_factory=_factory),
        bundler=ReleaseBundler(bundle_size=1),
        cluster_order=["canary", "prod"],
        bake_duration=1.0,
        alarm_log=alarm_log,
        debug_cycle=DebugCycle(median_seconds=0.01, sigma=0.1),
        rollback_duration=0.01,
    )
    released_rollouts: list = []
    pipeline._activate(
        loop=loop,
        rng=rng,
        add_rollout=lambda r: released_rollouts.append(r),
        add_actuator=lambda a: None,
    )

    # Let first rollout start
    loop.run(until=0.5)
    assert len(released_rollouts) >= 1
    first_rollout = released_rollouts[0]

    # Manually trigger failure: halt + begin_rollback + on_failure
    first_rollout.halt(0.5)
    first_rollout.begin_rollback(0.5, duration=0.01)
    pipeline._on_failure(first_rollout.release, 0.5)

    # Let rollback + debug cycle complete
    loop.run(until=5.0)

    # A fixed release (no disturbances) should have been started
    assert len(released_rollouts) >= 2
    fixed = released_rollouts[-1].release
    assert all(ch.disturbance is None for ch in fixed.changes)
