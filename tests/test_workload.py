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


def test_registry_missing_key_raises():
    registry = WorkloadRegistry()
    with pytest.raises(KeyError):
        registry.get("nonexistent")
