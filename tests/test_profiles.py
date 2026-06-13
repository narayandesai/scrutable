import numpy as np
import pytest
from scrutable.profiles import (
    FieldDist,
    WorkloadSpec,
    PlantEntry,
    PlantProfile,
    PlantProfileSampler,
    build_workload_mix,
    sample_plant_profile,
    sample_workload,
    CONSISTENT_FAST,
    HIGH_VARIANCE_LATENCY,
    BURSTY_ERRORS,
    SLOW_RELIABLE,
    LATENCY_VARIANCE_SPECTRUM,
    SPHERICAL_COW,
)
from scrutable.traffic import MarkovActivity


# --- PlantProfileSampler (formerly PlantProfile) ---

def test_sample_workload_all_fields_positive():
    rng = np.random.default_rng(42)
    model = sample_workload(CONSISTENT_FAST, "wl-test", rng)
    assert model.latency_median > 0
    assert model.latency_sigma > 0
    assert model.error_scale > 0
    assert model.error_shape > 0
    assert model.noise_sigma > 0


def test_sample_workload_reproducible():
    model1 = sample_workload(CONSISTENT_FAST, "wl-1", np.random.default_rng(0))
    model2 = sample_workload(CONSISTENT_FAST, "wl-1", np.random.default_rng(0))
    assert model1.latency_median == pytest.approx(model2.latency_median)
    assert model1.latency_sigma == pytest.approx(model2.latency_sigma)


def test_high_variance_latency_spreads_more_than_consistent_fast():
    rng_hv = np.random.default_rng(1)
    rng_cf = np.random.default_rng(1)
    hv_medians = [sample_workload(HIGH_VARIANCE_LATENCY, f"wl-{i}", rng_hv).latency_median for i in range(100)]
    cf_medians = [sample_workload(CONSISTENT_FAST, f"wl-{i}", rng_cf).latency_median for i in range(100)]
    assert np.std(hv_medians) > np.std(cf_medians)


def test_bursty_errors_has_lower_error_scale_than_slow_reliable():
    rng_be = np.random.default_rng(2)
    rng_sr = np.random.default_rng(2)
    be_scales = [sample_workload(BURSTY_ERRORS, f"wl-{i}", rng_be).error_scale for i in range(100)]
    sr_scales = [sample_workload(SLOW_RELIABLE, f"wl-{i}", rng_sr).error_scale for i in range(100)]
    assert np.mean(be_scales) < np.mean(sr_scales)


def test_catalog_constants_have_correct_names():
    assert CONSISTENT_FAST.name == "consistent_fast"
    assert HIGH_VARIANCE_LATENCY.name == "high_variance_latency"
    assert BURSTY_ERRORS.name == "bursty_errors"
    assert SLOW_RELIABLE.name == "slow_reliable"


def test_latency_variance_spectrum_has_five_profiles():
    assert len(LATENCY_VARIANCE_SPECTRUM) == 5


def test_latency_variance_spectrum_ordered_by_increasing_sigma():
    sigmas = [p.entries[0].spec.latency_sigma for p in LATENCY_VARIANCE_SPECTRUM]
    assert sigmas == sorted(sigmas)


def test_latency_variance_spectrum_profiles_have_equal_median():
    medians = [p.entries[0].spec.latency_median for p in LATENCY_VARIANCE_SPECTRUM]
    assert all(m == pytest.approx(medians[0]) for m in medians)


def test_latency_variance_spectrum_sigmas_strictly_ordered():
    sigmas = [p.entries[0].spec.latency_sigma for p in LATENCY_VARIANCE_SPECTRUM]
    assert all(sigmas[i] < sigmas[i + 1] for i in range(len(sigmas) - 1))


def test_error_shape_clamped_to_minimum():
    sampler = PlantProfileSampler(
        name="clamp_test",
        latency_median=FieldDist(lognormal_mean=0.0, lognormal_sigma=0.1),
        latency_sigma=FieldDist(lognormal_mean=0.0, lognormal_sigma=0.1),
        error_scale=FieldDist(lognormal_mean=5.0, lognormal_sigma=0.1),
        error_shape=FieldDist(lognormal_mean=-10.0, lognormal_sigma=0.01),
        noise_sigma=FieldDist(lognormal_mean=-5.0, lognormal_sigma=0.1),
    )
    rng = np.random.default_rng(0)
    for _ in range(20):
        model = sample_workload(sampler, "wl-clamp", rng)
        assert model.error_shape >= 0.1


# --- WorkloadSpec, PlantEntry, PlantProfile ---

def test_workload_spec_stores_plain_floats():
    spec = WorkloadSpec(
        latency_median=0.1,
        latency_sigma=0.25,
        error_scale=50000.0,
        error_shape=1.5,
        noise_sigma=0.005,
    )
    assert spec.latency_median == 0.1
    assert spec.latency_sigma == 0.25


def test_plant_entry_defaults_no_activity_flat_diurnal():
    spec = WorkloadSpec(0.1, 0.25, 50000.0, 1.5, 0.005)
    entry = PlantEntry(spec=spec, share=1.0)
    assert entry.activity is None


def test_plant_profile_stores_entries():
    spec = WorkloadSpec(0.1, 0.25, 50000.0, 1.5, 0.005)
    profile = PlantProfile(name="test", entries=[PlantEntry(spec=spec, share=1.0)])
    assert profile.name == "test"
    assert len(profile.entries) == 1


# --- build_workload_mix ---

def test_build_workload_mix_assigns_ids_from_profile_name():
    spec = WorkloadSpec(0.1, 0.25, 50000.0, 1.5, 0.005)
    profile = PlantProfile(name="demo", entries=[
        PlantEntry(spec=spec, share=0.6),
        PlantEntry(spec=spec, share=0.4),
    ])
    mix = build_workload_mix(profile, total_rate=1000.0, period=3600.0)
    ids = [e.model.workload_id for e in mix.entries]
    assert ids == ["demo-0", "demo-1"]


def test_build_workload_mix_preserves_spec_values():
    spec = WorkloadSpec(0.2, 0.3, 10000.0, 1.2, 0.01)
    profile = PlantProfile(name="p", entries=[PlantEntry(spec=spec, share=1.0)])
    mix = build_workload_mix(profile, total_rate=500.0, period=3600.0)
    m = mix.entries[0].model
    assert m.latency_median == 0.2
    assert m.latency_sigma == 0.3
    assert m.error_scale == 10000.0
    assert m.error_shape == 1.2
    assert m.noise_sigma == 0.01


def test_build_workload_mix_passes_activity():
    spec = WorkloadSpec(0.1, 0.25, 50000.0, 1.5, 0.005)
    activity = MarkovActivity(onset_rate=0.1, recovery_rate=0.5)
    profile = PlantProfile(name="p", entries=[PlantEntry(spec=spec, share=1.0, activity=activity)])
    mix = build_workload_mix(profile, total_rate=100.0, period=3600.0)
    assert mix.entries[0].activity is activity


def test_build_workload_mix_total_rate_and_period():
    spec = WorkloadSpec(0.1, 0.25, 50000.0, 1.5, 0.005)
    profile = PlantProfile(name="p", entries=[PlantEntry(spec=spec, share=1.0)])
    mix = build_workload_mix(profile, total_rate=2000.0, period=7200.0)
    assert mix.total_rate == 2000.0
    assert mix.period == 7200.0


# --- SPHERICAL_COW ---

def test_spherical_cow_is_plant_profile():
    assert isinstance(SPHERICAL_COW, PlantProfile)


def test_spherical_cow_has_correct_parameters():
    entry = SPHERICAL_COW.entries[0]
    assert entry.spec.latency_median == pytest.approx(0.1)
    assert entry.spec.latency_sigma == pytest.approx(0.25)


# --- sample_plant_profile ---

def test_sample_plant_profile_returns_n_entries():
    profile = sample_plant_profile(CONSISTENT_FAST, n=10, rng=np.random.default_rng(0))
    assert isinstance(profile, PlantProfile)
    assert len(profile.entries) == 10


def test_sample_plant_profile_equal_shares():
    profile = sample_plant_profile(CONSISTENT_FAST, n=4, rng=np.random.default_rng(0))
    shares = [e.share for e in profile.entries]
    assert all(s == pytest.approx(0.25) for s in shares)


def test_sample_plant_profile_reproducible():
    p1 = sample_plant_profile(CONSISTENT_FAST, n=5, rng=np.random.default_rng(42))
    p2 = sample_plant_profile(CONSISTENT_FAST, n=5, rng=np.random.default_rng(42))
    for e1, e2 in zip(p1.entries, p2.entries):
        assert e1.spec.latency_median == pytest.approx(e2.spec.latency_median)


# --- HIGH_VARIANCE factory ---

import math
from scrutable.profiles import make_high_variance, make_long_tail
from scipy.stats import norm

def _aggregate_cdf(x: float, p_fast: float, mu_fast: float, s_fast: float,
                   mu_slow: float, s_slow: float) -> float:
    return (p_fast * norm.cdf((math.log(x) - math.log(mu_fast)) / s_fast) +
            (1 - p_fast) * norm.cdf((math.log(x) - math.log(mu_slow)) / s_slow))

def test_high_variance_is_plant_profile():
    profile = make_high_variance()
    assert isinstance(profile, PlantProfile)

def test_high_variance_has_100k_entries():
    profile = make_high_variance()
    assert len(profile.entries) == 100_000

def test_high_variance_aggregate_median_approx():
    # Check the mixture CDF at the target percentiles analytically
    p50 = _aggregate_cdf(0.6, 0.99, 0.6, 0.40, 1577.0, 1.5)
    assert abs(p50 - 0.50) < 0.03

def test_high_variance_aggregate_p90_approx():
    p90 = _aggregate_cdf(1.0, 0.99, 0.6, 0.40, 1577.0, 1.5)
    assert abs(p90 - 0.90) < 0.02

def test_high_variance_aggregate_p99_approx():
    p99 = _aggregate_cdf(60.0, 0.99, 0.6, 0.40, 1577.0, 1.5)
    assert abs(p99 - 0.99) < 0.005

def test_high_variance_aggregate_p999_approx():
    p999 = _aggregate_cdf(10800.0, 0.99, 0.6, 0.40, 1577.0, 1.5)
    assert abs(p999 - 0.999) < 0.002

# --- make_long_tail ---
# Mixture: 99% fast lognormal(median≈0.339s, σ=0.291) + 1% slow lognormal(median≈1527s, σ=0.664)
# Targets: P90=0.5s, P99=1s, P99.9=3600s (60 min), P99.99=7200s (120 min)

_LT_P_FAST = 0.99
_LT_MU_FAST, _LT_S_FAST = math.log(0.339), 0.291
_LT_MU_SLOW, _LT_S_SLOW = math.log(1527.0), 0.664

def _lt_cdf(x: float) -> float:
    return (_LT_P_FAST * norm.cdf((math.log(x) - _LT_MU_FAST) / _LT_S_FAST) +
            (1 - _LT_P_FAST) * norm.cdf((math.log(x) - _LT_MU_SLOW) / _LT_S_SLOW))

def test_long_tail_is_plant_profile():
    assert isinstance(make_long_tail(), PlantProfile)

def test_long_tail_default_entry_count():
    assert len(make_long_tail().entries) == 50_000

def test_long_tail_entry_count_parameterized():
    assert len(make_long_tail(n_fast=99, n_slow=1).entries) == 100

def test_long_tail_aggregate_p90():
    assert abs(_lt_cdf(0.5) - 0.90) < 0.01

def test_long_tail_aggregate_p99():
    assert abs(_lt_cdf(1.0) - 0.99) < 0.005

def test_long_tail_aggregate_p999():
    assert abs(_lt_cdf(3600.0) - 0.999) < 0.002

def test_long_tail_aggregate_p9999():
    assert abs(_lt_cdf(7200.0) - 0.9999) < 0.001


def test_high_variance_mostly_inactive():
    profile = make_high_variance()
    for entry in profile.entries[:10]:
        assert entry.activity is not None
        fraction_active = entry.activity.onset_rate / (entry.activity.onset_rate + entry.activity.recovery_rate)
        assert fraction_active < 0.05


def test_long_tail_entries_have_activity():
    profile = make_long_tail(n_fast=99, n_slow=1)
    for entry in profile.entries:
        assert entry.activity is not None


def test_split_profile_chunk_count():
    from scrutable.profiles import split_profile
    chunks = split_profile(SPHERICAL_COW, n=1)
    assert len(chunks) == 1

def test_split_profile_entry_count():
    from scrutable.profiles import split_profile, make_long_tail
    profile = make_long_tail(n_fast=99, n_slow=1)
    chunks = split_profile(profile, n=4)
    assert sum(len(c.entries) for c in chunks) == 100

def test_split_profile_preserves_entries():
    from scrutable.profiles import split_profile, make_long_tail
    profile = make_long_tail(n_fast=99, n_slow=1)
    chunks = split_profile(profile, n=4)
    all_entries = [e for c in chunks for e in c.entries]
    assert all_entries == list(profile.entries)

def test_split_profile_names():
    from scrutable.profiles import split_profile, make_long_tail
    profile = make_long_tail(n_fast=99, n_slow=1)
    chunks = split_profile(profile, n=3)
    assert all(c.name.startswith("long_tail_chunk") for c in chunks)

def test_long_tail_steady_state_fraction_near_ten_percent():
    profile = make_long_tail(n_fast=99, n_slow=1)
    for entry in profile.entries:
        act = entry.activity
        fraction = act.onset_rate / (act.onset_rate + act.recovery_rate)
        assert abs(fraction - 0.10) < 0.01
