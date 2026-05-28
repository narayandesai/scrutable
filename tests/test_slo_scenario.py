import numpy as np
from scrutable.profiles import LATENCY_VARIANCE_SPECTRUM
from scrutable.scenarios.slo_spectrum import run_slo_scenario, ScenarioResult, TimeWindow


def test_run_slo_scenario_returns_result():
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    result = run_slo_scenario(profile, seed=42, rate=500.0, burn_in=5.0, post_disturbance=10.0)
    assert isinstance(result, ScenarioResult)


def test_scenario_result_has_time_windows():
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    result = run_slo_scenario(profile, seed=42, rate=500.0, burn_in=5.0, post_disturbance=10.0)
    assert len(result.windows) > 0
    assert all(isinstance(w, TimeWindow) for w in result.windows)


def test_time_window_has_all_percentiles():
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    result = run_slo_scenario(profile, seed=42, rate=500.0, burn_in=5.0, post_disturbance=10.0)
    for w in result.windows:
        assert w.p50 > 0.0
        assert w.p90 >= w.p50
        assert w.p99 >= w.p90
        assert w.p999 >= w.p99


def test_scenario_records_disturbance_time():
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    result = run_slo_scenario(profile, seed=42, rate=500.0, burn_in=5.0, post_disturbance=10.0)
    assert result.disturbance_at == 5.0


def test_scenario_records_threshold():
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    result = run_slo_scenario(profile, seed=42, rate=500.0, burn_in=5.0, post_disturbance=10.0)
    assert result.slo_threshold_p999 > 0.0


def test_disturbance_elevates_latency_on_low_variance_profile():
    # v1 (sigma=0.1): additive +1s on 50% of nodes raises P99 from ~0.13s to ~1.1s
    profile = LATENCY_VARIANCE_SPECTRUM[0]
    result = run_slo_scenario(profile, seed=42, rate=500.0, burn_in=5.0, post_disturbance=15.0)
    # use arrival-time windows that are clearly post-disturbance (delay 1s for in-flight to clear)
    pre = [w for w in result.windows if w.t_end <= result.disturbance_at]
    post = [w for w in result.windows if w.t_start >= result.disturbance_at + 2.0]
    assert pre and post
    avg_pre_p99 = np.mean([w.p99 for w in pre])
    avg_post_p99 = np.mean([w.p99 for w in post])
    assert avg_post_p99 > avg_pre_p99 * 3


def test_scenario_profile_name_preserved():
    profile = LATENCY_VARIANCE_SPECTRUM[2]
    result = run_slo_scenario(profile, seed=42, rate=500.0, burn_in=5.0, post_disturbance=10.0)
    assert result.profile_name == profile.name
