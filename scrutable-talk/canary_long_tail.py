"""Canary rollout comparison on a long-tail plant profile.

Same scenario as canary_rollout.__main__ (100%/150%/200% change rate), but with
a 5-workload mix: one always-on fast workload (90% of traffic) plus four slow
workloads that activate intermittently via Markov chains, together contributing
~1% of effective traffic. Each slow workload has a different latency severity and
activation timescale, so the fraction of slow traffic varies over time.

  Fast:   median=0.339s, σ=0.291, always on,  share=0.90
  Slow-A: median=200s,   σ=0.50,  duty≈14%,   activates every ~2h for ~2h
  Slow-B: median=800s,   σ=0.60,  duty≈18%,   activates every ~4h for ~4h
  Slow-C: median=3000s,  σ=0.70,  duty≈14%,   activates every ~6h for ~6h
  Slow-D: median=8000s,  σ=0.80,  duty≈5%,    activates every ~1h for ~1h
"""
from __future__ import annotations
import numpy as np
from scrutable.models import WorkloadModel
from scrutable.traffic import WorkloadEntry, WorkloadMix, MarkovActivity
from scrutable.scenarios.canary_rollout import run_canary_rollout

_WEEK = 7 * 24 * 3600.0
_BASE_CHANGES_PER_WEEK = 150.0
_H = 3600.0

# onset_rate  = rate of leaving active state   → mean active duration  = 1/onset_rate
# recovery_rate = rate of leaving inactive state → mean inactive duration = 1/recovery_rate
_MIX = WorkloadMix(
    total_rate=10.0,
    period=3600.0,
    entries=[
        WorkloadEntry(
            model=WorkloadModel(
                workload_id="fast",
                latency_median=0.339,
                latency_sigma=0.291,
                error_scale=50000.0,
                error_shape=1.5,
                noise_sigma=0.001,
            ),
            share=0.90,
        ),
        WorkloadEntry(
            model=WorkloadModel(
                workload_id="slow-a",
                latency_median=200.0,
                latency_sigma=0.50,
                error_scale=50000.0,
                error_shape=1.5,
                noise_sigma=0.001,
            ),
            share=0.025,
            activity=MarkovActivity(
                onset_rate=1.0 / (2 * _H),     # active ~2h
                recovery_rate=1.0 / (12 * _H), # inactive ~12h → duty ≈14%
            ),
        ),
        WorkloadEntry(
            model=WorkloadModel(
                workload_id="slow-b",
                latency_median=800.0,
                latency_sigma=0.60,
                error_scale=50000.0,
                error_shape=1.5,
                noise_sigma=0.001,
            ),
            share=0.025,
            activity=MarkovActivity(
                onset_rate=1.0 / (4 * _H),     # active ~4h
                recovery_rate=1.0 / (18 * _H), # inactive ~18h → duty ≈18%
            ),
        ),
        WorkloadEntry(
            model=WorkloadModel(
                workload_id="slow-c",
                latency_median=3000.0,
                latency_sigma=0.70,
                error_scale=50000.0,
                error_shape=1.5,
                noise_sigma=0.001,
            ),
            share=0.025,
            activity=MarkovActivity(
                onset_rate=1.0 / (6 * _H),     # active ~6h
                recovery_rate=1.0 / (36 * _H), # inactive ~36h → duty ≈14%
            ),
        ),
        WorkloadEntry(
            model=WorkloadModel(
                workload_id="slow-d",
                latency_median=8000.0,
                latency_sigma=0.80,
                error_scale=50000.0,
                error_shape=1.5,
                noise_sigma=0.001,
            ),
            share=0.025,
            activity=MarkovActivity(
                onset_rate=1.0 / (1 * _H),     # active ~1h
                recovery_rate=1.0 / (20 * _H), # inactive ~20h → duty ≈5%
            ),
        ),
    ],
)

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
    total_duration=6 * _WEEK,
    seed=42,
    mix=_MIX,
)

if __name__ == "__main__":
    print("Calibrating SLO and running 100% baseline (long-tail)... ", end="", flush=True)
    _base = run_canary_rollout(
        change_rate=_BASE_CHANGES_PER_WEEK / _WEEK,
        bundle_size=int(_BASE_CHANGES_PER_WEEK),
        **_SHARED,
    )
    _slo = _base.slo_target
    print("done\n")

    print("=== Parameters ===")
    print(f"  profile:              long-tail (1 fast + 4 slow w/ Markov)")
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

    _scale_results = {1.0: _base}
    for scale in [1.5, 2.0]:
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
    hdr = (f"  {'Scale':>6}  {'Bundle':>6}  {'P(bug)':>7}  "
           f"{'Orig':>6}  {'w/bug':>6}  "
           f"{'Caught':>7}  {'Escaped':>8}  {'FalseRB':>8}  "
           f"{'Retries':>8}  {'RetryRB':>8}  {'DebugMed':>9}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for scale in [1.0, 1.5, 2.0]:
        r = _scale_results[scale]
        bundle_size = max(1, round(_BASE_CHANGES_PER_WEEK * scale))
        p_bug = 1 - (1 - _SHARED['bug_fraction']) ** bundle_size
        debug_med = (
            f"{float(np.median(r.debug_durations_s))/3600:.1f}h"
            if r.debug_durations_s else "n/a"
        )
        print(f"  {int(scale*100):>5}%  {bundle_size:>6}  {p_bug:>7.1%}  "
              f"{r.original_releases_attempted:>6}  {r.original_releases_with_bug:>6}  "
              f"{r.original_rollbacks:>7}  {r.canary_escapes:>8}  {r.false_rollbacks:>8}  "
              f"{r.retry_releases_attempted:>8}  {r.retry_rollbacks:>8}  {debug_med:>9}")

    print("\n=== Change Velocity ===")
    sim_weeks = _SHARED['total_duration'] / _WEEK
    chdr = (f"  {'Scale':>6}  {'Changes':>8}  {'Changes/wk':>11}  "
            f"{'LeadP50':>8}  {'LeadP90':>8}  {'LeadP95':>8}")
    print(chdr)
    print("  " + "-" * (len(chdr) - 2))
    for scale in [1.0, 1.5, 2.0]:
        r = _scale_results[scale]
        lt = r.change_lead_times
        if lt:
            p50 = f"{float(np.percentile(lt, 50))/3600:.1f}h"
            p90 = f"{float(np.percentile(lt, 90))/3600:.1f}h"
            p95 = f"{float(np.percentile(lt, 95))/3600:.1f}h"
        else:
            p50 = p90 = p95 = "n/a"
        n_changes = len(lt)
        rate = n_changes / sim_weeks if sim_weeks > 0 else 0.0
        print(f"  {int(scale*100):>5}%  {n_changes:>8}  {rate:>11.1f}  "
              f"{p50:>8}  {p90:>8}  {p95:>8}")
