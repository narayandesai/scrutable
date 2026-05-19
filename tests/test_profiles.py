import numpy as np
from scrutable.profiles import (
    FieldDist,
    WorkloadProfile,
    sample_workload,
    CONSISTENT_FAST,
    HIGH_VARIANCE_LATENCY,
    BURSTY_ERRORS,
    SLOW_RELIABLE,
)


def test_sample_workload_all_fields_positive():
    rng = np.random.default_rng(42)
    model = sample_workload(CONSISTENT_FAST, "wl-test", rng)
    assert model.workload_id == "wl-test"
    assert model.latency_median > 0.0
    assert model.latency_sigma > 0.0
    assert model.error_scale > 0.0
    assert model.error_shape >= 0.1   # clamped minimum
    assert model.noise_sigma > 0.0


def test_sample_workload_reproducible():
    model1 = sample_workload(CONSISTENT_FAST, "wl-1", np.random.default_rng(0))
    model2 = sample_workload(CONSISTENT_FAST, "wl-1", np.random.default_rng(0))
    assert model1.latency_median == model2.latency_median
    assert model1.error_scale == model2.error_scale


def test_high_variance_latency_spreads_more_than_consistent_fast():
    rng_hv = np.random.default_rng(7)
    rng_cf = np.random.default_rng(7)
    hv_medians = [sample_workload(HIGH_VARIANCE_LATENCY, f"wl-{i}", rng_hv).latency_median for i in range(100)]
    cf_medians = [sample_workload(CONSISTENT_FAST, f"wl-{i}", rng_cf).latency_median for i in range(100)]
    assert float(np.std(hv_medians)) > float(np.std(cf_medians))


def test_bursty_errors_has_lower_error_scale_than_slow_reliable():
    rng_be = np.random.default_rng(3)
    rng_sr = np.random.default_rng(3)
    be_scales = [sample_workload(BURSTY_ERRORS, f"wl-{i}", rng_be).error_scale for i in range(100)]
    sr_scales = [sample_workload(SLOW_RELIABLE, f"wl-{i}", rng_sr).error_scale for i in range(100)]
    assert float(np.mean(be_scales)) < float(np.mean(sr_scales))


def test_catalog_constants_have_correct_names():
    assert CONSISTENT_FAST.name == "consistent_fast"
    assert HIGH_VARIANCE_LATENCY.name == "high_variance_latency"
    assert BURSTY_ERRORS.name == "bursty_errors"
    assert SLOW_RELIABLE.name == "slow_reliable"


def test_error_shape_clamped_to_minimum():
    profile = WorkloadProfile(
        name="test",
        latency_median=FieldDist(lognormal_mean=-3.0, lognormal_sigma=0.1),
        latency_sigma=FieldDist(lognormal_mean=-2.0, lognormal_sigma=0.1),
        error_scale=FieldDist(lognormal_mean=5.0, lognormal_sigma=0.1),
        error_shape=FieldDist(lognormal_mean=-10.0, lognormal_sigma=0.01),  # draws near 0
        noise_sigma=FieldDist(lognormal_mean=-5.0, lognormal_sigma=0.1),
    )
    rng = np.random.default_rng(0)
    for _ in range(20):
        model = sample_workload(profile, "wl-clamp", rng)
        assert model.error_shape >= 0.1
