import pytest
import numpy as np
from scrutable.pipeline import ChangeStream, ReleaseBundler
from scrutable.models import Disturbance, DisturbanceScope, ReleaseChange


def _factory(change_id: str) -> Disturbance:
    return Disturbance(
        disturbance_id=f"bug-{change_id}",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_addend": 0.3},
    )


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
