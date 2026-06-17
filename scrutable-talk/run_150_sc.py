"""Re-run only the 150% SC case using cached SLO calibration."""
from __future__ import annotations
import json
import pathlib
import numpy as np
from scrutable.scenarios.canary_rollout import run_canary_rollout
from scrutable.detectors.slo import SloTarget

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
    total_duration=6 * _WEEK,
    seed=42,
)

_CACHE = pathlib.Path(__file__).parent / "sc_slo_cache.json"


def _get_slo() -> SloTarget:
    if _CACHE.exists():
        d = json.loads(_CACHE.read_text())
        print(f"Loaded SLO from cache: threshold={d['threshold']:.4f} s  P{d['percentile']}")
        return SloTarget(threshold=d["threshold"], percentile=d["percentile"])

    print("No cache — calibrating 100% baseline... ", end="", flush=True)
    base = run_canary_rollout(
        change_rate=_BASE_CHANGES_PER_WEEK / _WEEK,
        bundle_size=int(_BASE_CHANGES_PER_WEEK),
        **_SHARED,
    )
    slo = base.slo_target
    _CACHE.write_text(json.dumps({"threshold": slo.threshold, "percentile": slo.percentile}))
    print(f"done  threshold={slo.threshold:.4f} s  (cached to {_CACHE.name})")
    return slo


slo = _get_slo()

scale = 1.5
changes_per_week = _BASE_CHANGES_PER_WEEK * scale
bundle_size = max(1, round(changes_per_week))
print(f"Running {int(scale*100)}% SC ({bundle_size} changes/bundle)... ", end="", flush=True)
r = run_canary_rollout(
    change_rate=changes_per_week / _WEEK,
    bundle_size=bundle_size,
    slo_target=slo,
    **_SHARED,
)
print("done\n")

lt = r.change_lead_times
sim_weeks = _SHARED["total_duration"] / _WEEK
n_changes = len(lt)

print(f"=== 150% SC Results ===")
print(f"  orig releases:   {r.original_releases_attempted}")
print(f"  w/ bug:          {r.original_releases_with_bug}")
print(f"  caught (TP):     {r.original_rollbacks}")
print(f"  escaped (FN):    {r.canary_escapes}")
print(f"  false RBs (FP):  {r.false_rollbacks}")
print(f"  retries:         {r.retry_releases_attempted}")
print(f"  retry RBs:       {r.retry_rollbacks}")
if r.debug_durations_s:
    print(f"  debug median:    {float(np.median(r.debug_durations_s))/3600:.1f} h")
print(f"\n=== Change Velocity ===")
print(f"  changes shipped: {n_changes}")
print(f"  changes/week:    {n_changes / sim_weeks:.1f}")
if lt:
    print(f"  lead P50:        {float(np.percentile(lt, 50))/3600:.1f} h")
    print(f"  lead P90:        {float(np.percentile(lt, 90))/3600:.1f} h")
    print(f"  lead P95:        {float(np.percentile(lt, 95))/3600:.1f} h")
