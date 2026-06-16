"""
Cadence comparison: traditional (large-batch, weekly) vs. higher-velocity delivery.

The variable under study is *batch size* (changes per release), scaled together with
change rate so the release cadence stays constant at one release per week.  Bug fraction
is fixed at 1 % per change, so larger bundles have a higher probability of containing
at least one bug:

    P(bug in bundle of n) = 1 - 0.99^n

Scales and their P(bug):
    50 %  (n=25 )  ≈ 22 %
   100 %  (n=50 )  ≈ 39 %   ← baseline ("traditional")
   200 %  (n=100)  ≈ 63 %
   400 %  (n=200)  ≈ 86 %

SLO detection notes
-------------------
The detector uses a 60-second observation window calibrated to 0.1 % per-window FPR.
bake_duration defaults to 3 600 s (1 hour) — giving ~60 bake windows and a cumulative
false-alarm rate of ~5.8 %.  A 1-day bake would require either larger windows or a
burst-count detector to keep the cumulative FPR manageable.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.scenarios.canary_rollout import run_canary_rollout

_WEEK_SECONDS = 7 * 24 * 3600.0
# Traditional baseline: 50 changes/release, weekly cadence, 1 % bug fraction
_BASE_BUNDLE_SIZE = 50
_BASE_CHANGES_PER_WEEK = 50.0


@dataclass
class CadenceResult:
    label: str
    scale: float
    bundle_size: int
    changes_per_week_attempted: float
    releases_attempted: int
    releases_completed: int
    releases_rolled_back: int
    rollback_rate: float
    changes_delivered: int
    throughput_changes_per_week: float
    median_debug_h: float | None


def run_cadence_comparison(
    scales: list[float] | None = None,
    sim_duration_days: float = 90.0,
    bug_fraction: float = 0.01,
    bake_duration: float = 86400.0,
    rollback_duration: float = 3600.0,
    debug_median_s: float = 6.0 * 3600.0,
    debug_sigma: float = 0.84,
    # Hourly windows give 24 bake windows per 1-day bake, keeping cumulative
    # FPR manageable (~2.4 % with 7-day calibration at 0.1 % per-window FPR).
    window_size: float = 3600.0,
    calibration_duration: float = 7 * 24 * 3600.0,
    # 10 req/s balances simulation speed (~80 min total) with detection power.
    # Each 1-hour window still has 36 k observations — plenty for stable P99.9.
    # Use 100 req/s for higher fidelity at the cost of ~10× longer runtime.
    total_rate: float = 10.0,
    seed: int = 42,
) -> list[CadenceResult]:
    """Run the cadence comparison across *scales* and return one result per scale.

    Parameters
    ----------
    scales:
        Multipliers applied to both change_rate and bundle_size relative to the
        traditional baseline (50 changes/week, bundle_size=50).  Defaults to
        [0.5, 1.0, 2.0, 4.0].
    sim_duration_days:
        Length of each simulation run in days.
    """
    if scales is None:
        scales = [0.5, 1.0, 2.0, 4.0]

    total_duration = sim_duration_days * 24 * 3600.0
    sim_weeks = total_duration / _WEEK_SECONDS

    results = []
    for scale in scales:
        bundle_size = max(1, round(_BASE_BUNDLE_SIZE * scale))
        change_rate = (_BASE_CHANGES_PER_WEEK * scale) / _WEEK_SECONDS

        r = run_canary_rollout(
            change_rate=change_rate,
            bug_fraction=bug_fraction,
            bundle_size=bundle_size,
            bake_duration=bake_duration,
            rollback_duration=rollback_duration,
            debug_median_s=debug_median_s,
            debug_sigma=debug_sigma,
            window_size=window_size,
            calibration_duration=calibration_duration,
            total_rate=total_rate,
            total_duration=total_duration,
            seed=seed,
        )

        changes_delivered = r.releases_completed * bundle_size
        rollback_rate = (
            r.releases_rolled_back / r.releases_attempted
            if r.releases_attempted > 0
            else 0.0
        )
        median_debug_h = (
            float(np.median(r.debug_durations_s)) / 3600.0
            if r.debug_durations_s
            else None
        )

        results.append(CadenceResult(
            label=f"{int(scale * 100)}%",
            scale=scale,
            bundle_size=bundle_size,
            changes_per_week_attempted=_BASE_CHANGES_PER_WEEK * scale,
            releases_attempted=r.releases_attempted,
            releases_completed=r.releases_completed,
            releases_rolled_back=r.releases_rolled_back,
            rollback_rate=rollback_rate,
            changes_delivered=changes_delivered,
            throughput_changes_per_week=changes_delivered / sim_weeks,
            median_debug_h=median_debug_h,
        ))

    return results


if __name__ == "__main__":
    import sys

    days = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    print(f"Cadence comparison — {days:.0f}-day simulation")
    print(
        "Baseline: 50 changes/release, weekly cadence, 1-day bake, 1 % bug fraction\n"
    )

    rows = run_cadence_comparison(sim_duration_days=days)

    col_w = 13
    header = (
        f"{'Scale':>6}  {'Bundle':>6}  {'Changes/wk':>{col_w}}  "
        f"{'Releases':>8}  {'Rollback%':>9}  {'Throughput':>{col_w}}"
    )
    sep = "-" * len(header)
    print(header)
    print(sep)
    for r in rows:
        print(
            f"{r.label:>6}  {r.bundle_size:>6}  "
            f"{r.changes_per_week_attempted:>{col_w}.0f}  "
            f"{r.releases_attempted:>8}  "
            f"{r.rollback_rate:>9.1%}  "
            f"{r.throughput_changes_per_week:>{col_w}.1f}"
        )
