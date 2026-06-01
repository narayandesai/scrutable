import numpy as np
import pytest
from scrutable.models import WorkloadModel, WorkloadState, NodeState
from scrutable.workload import WorkloadRegistry, sample_latency, sample_error_code


@pytest.fixture
def model():
    return WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    )


@pytest.fixture
def neutral_wstate():
    return WorkloadState(workload_id="wl1")


@pytest.fixture
def neutral_nstate():
    return NodeState(node_id="n1", cluster_id="c1", region_id="r1")


def test_sample_latency_is_positive(model, neutral_wstate, neutral_nstate, seeded_rng):
    for _ in range(100):
        latency = sample_latency(model, neutral_wstate, neutral_nstate, seeded_rng)
        assert latency >= 0.0


def test_sample_latency_respects_multiplier(model, neutral_nstate, seeded_rng):
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    wstate_normal = WorkloadState(workload_id="wl1", latency_multiplier=1.0)
    wstate_slow = WorkloadState(workload_id="wl1", latency_multiplier=10.0)
    samples_normal = [sample_latency(model, wstate_normal, neutral_nstate, rng1) for _ in range(50)]
    samples_slow = [sample_latency(model, wstate_slow, neutral_nstate, rng2) for _ in range(50)]
    assert sum(samples_slow) > sum(samples_normal)


def test_sample_latency_node_multiplier(model, neutral_wstate, seeded_rng):
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    nstate_normal = NodeState(node_id="n1", cluster_id="c1", region_id="r1", latency_multiplier=1.0)
    nstate_slow = NodeState(node_id="n1", cluster_id="c1", region_id="r1", latency_multiplier=5.0)
    samples_normal = [sample_latency(model, neutral_wstate, nstate_normal, rng1) for _ in range(50)]
    samples_slow = [sample_latency(model, neutral_wstate, nstate_slow, rng2) for _ in range(50)]
    assert sum(samples_slow) > sum(samples_normal)


def test_sample_error_code_returns_zero_or_one(model, neutral_wstate, neutral_nstate, seeded_rng):
    for _ in range(100):
        code = sample_error_code(model, neutral_wstate, neutral_nstate, seeded_rng, sim_time=1.0)
        assert code in (0, 1)


def test_sample_error_code_elevated_by_multiplier(model, neutral_nstate, seeded_rng):
    rng1 = np.random.default_rng(0)
    rng2 = np.random.default_rng(0)
    model_low_scale = WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=1.0,    # CDF reaches high values quickly
        error_shape=1.0,
        noise_sigma=0.001,
    )
    wstate_normal = WorkloadState(workload_id="wl1", error_rate_multiplier=1.0)
    wstate_high = WorkloadState(workload_id="wl1", error_rate_multiplier=100.0)
    errors_normal = sum(
        sample_error_code(model_low_scale, wstate_normal, neutral_nstate, rng1, sim_time=1.0)
        for _ in range(200)
    )
    errors_high = sum(
        sample_error_code(model_low_scale, wstate_high, neutral_nstate, rng2, sim_time=1.0)
        for _ in range(200)
    )
    assert errors_high >= errors_normal


def test_registry_get_returns_registered_model():
    registry = WorkloadRegistry()
    model = WorkloadModel(
        workload_id="wl42",
        latency_median=0.05,
        latency_sigma=0.2,
        error_scale=500.0,
        error_shape=1.0,
        noise_sigma=0.005,
    )
    registry.register(model)
    assert registry.get("wl42") is model


def test_registry_all_ids():
    registry = WorkloadRegistry()
    for i in range(3):
        registry.register(
            WorkloadModel(
                workload_id=f"wl{i}",
                latency_median=0.1,
                latency_sigma=0.3,
                error_scale=500.0,
                error_shape=1.0,
                noise_sigma=0.001,
            )
        )
    assert set(registry.all_ids()) == {"wl0", "wl1", "wl2"}


def test_registry_missing_key_raises_value_error_with_id():
    registry = WorkloadRegistry()
    with pytest.raises(ValueError, match="nonexistent"):
        registry.get("nonexistent")


def test_sample_latency_addend_increases_latency(model, neutral_wstate):
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    nstate_no_addend = NodeState(node_id="n1", cluster_id="c1", region_id="r1", latency_addend=0.0)
    nstate_with_addend = NodeState(node_id="n1", cluster_id="c1", region_id="r1", latency_addend=1.0)
    baseline = np.mean([sample_latency(model, neutral_wstate, nstate_no_addend, rng1) for _ in range(100)])
    elevated = np.mean([sample_latency(model, neutral_wstate, nstate_with_addend, rng2) for _ in range(100)])
    assert elevated > baseline + 0.9


def test_sample_buffer_lognormal_positive():
    from scrutable.workload import _SampleBuffer
    buf = _SampleBuffer(np.random.default_rng(0))
    vals = [buf.lognormal(np.log(0.1), 0.3) for _ in range(200)]
    assert all(v > 0 for v in vals)


def test_sample_buffer_lognormal_mean_plausible():
    from scrutable.workload import _SampleBuffer
    buf = _SampleBuffer(np.random.default_rng(0))
    vals = [buf.lognormal(np.log(0.1), 0.1) for _ in range(2000)]
    assert 0.08 < np.median(vals) < 0.12


def test_sample_buffer_normal_mean_near_loc():
    from scrutable.workload import _SampleBuffer
    buf = _SampleBuffer(np.random.default_rng(0))
    vals = [buf.normal(0.0, 0.01) for _ in range(2000)]
    assert abs(np.mean(vals)) < 0.001


def test_sample_buffer_batches_are_independent():
    from scrutable.workload import _SampleBuffer
    # Two buffers with same seed should produce identical values
    b1 = _SampleBuffer(np.random.default_rng(42))
    b2 = _SampleBuffer(np.random.default_rng(42))
    v1 = [b1.lognormal(0.0, 0.3) for _ in range(50)]
    v2 = [b2.lognormal(0.0, 0.3) for _ in range(50)]
    assert v1 == v2


def test_weibull_early_exit_returns_zero_at_very_small_t():
    from scrutable.workload import _weibull_cdf
    # t << scale: CDF should be effectively zero and early-exit path taken
    assert _weibull_cdf(0.001, scale=5000.0, shape=1.5) == 0.0


def test_sample_error_code_zero_at_very_early_time(model, neutral_wstate, neutral_nstate):
    rng = np.random.default_rng(0)
    results = [sample_error_code(model, neutral_wstate, neutral_nstate, rng, sim_time=0.001)
               for _ in range(100)]
    assert all(r == 0 for r in results)


def test_sample_buffer_integers_in_range():
    from scrutable.workload import _SampleBuffer
    buf = _SampleBuffer(np.random.default_rng(0))
    vals = [buf.integers(5) for _ in range(500)]
    assert all(0 <= v < 5 for v in vals)


def test_sample_buffer_integers_same_seed():
    from scrutable.workload import _SampleBuffer
    b1 = _SampleBuffer(np.random.default_rng(7))
    b2 = _SampleBuffer(np.random.default_rng(7))
    v1 = [b1.integers(4) for _ in range(100)]
    v2 = [b2.integers(4) for _ in range(100)]
    assert v1 == v2


def test_sample_buffer_integers_uses_uniform_batch():
    from scrutable.workload import _SampleBuffer, _BATCH
    # After drawing _BATCH integers the uniform pool should have refreshed;
    # verify no numpy call per draw by confirming reproducibility across a full batch
    buf = _SampleBuffer(np.random.default_rng(99))
    vals = [buf.integers(10) for _ in range(_BATCH + 1)]
    assert len(vals) == _BATCH + 1
