"""Section 3 demo: SPHERICAL_COW vs long_tail at 10k effective QPS.

SPHERICAL_COW: 1 workload always on, total_rate=10_000 -> 10k QPS
long_tail:    50k workloads, 10% active at steady state,
              total_rate=100_000 -> ~10k effective QPS

Runs 4 jobs (2 profiles × 2 sensor percentiles) in parallel.
"""
from __future__ import annotations
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from scrutable.profiles import SPHERICAL_COW, make_long_tail
from scrutable.scenarios.slo_performance import sweep_slo_performance


def _run(profile_name: str, total_rate: float, percentile: float) -> tuple:
    from scrutable.profiles import SPHERICAL_COW, make_long_tail
    profile = SPHERICAL_COW if profile_name == "spherical_cow" else make_long_tail()
    pts = sweep_slo_performance(
        [profile], [1.0],
        seed=42, total_rate=total_rate, n_calibration_windows=60,
        post_disturbance=30.0, disturbance_addend=0.3,
        target_fpr=0.001, percentile=percentile, workers=1,
    )
    return profile_name, percentile, pts[0]


JOBS = [
    ("spherical_cow", 10_000.0,  99.9),
    ("spherical_cow", 10_000.0,  50.0),
    ("long_tail",    100_000.0,  99.9),
    ("long_tail",    100_000.0,  50.0),
]

if __name__ == "__main__":
    t0 = time.time()
    results: dict[tuple, object] = {}

    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_run, *job): job for job in JOBS}
        for fut in as_completed(futures):
            name, pct, pt = fut.result()
            results[(name, pct)] = pt
            det = f"{pt.time_to_first_detection:.1f}s" if pt.time_to_first_detection is not None else "None"
            print(f"  {name} P{pct}: recall={pt.recall:.2f}  det={det}", flush=True)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s\n")

    print(f"{'Profile':<18} | {'Sensor':<7} | {'Recall':<6} | {'SNR':<8} | Det. latency")
    print("-" * 60)
    for name, pct in [("spherical_cow", 99.9), ("spherical_cow", 50.0),
                      ("long_tail", 99.9), ("long_tail", 50.0)]:
        pt = results[(name, pct)]
        snr = pt.snr.get(pct)
        snr_str = f"{snr:.2f}" if snr is not None else "None"
        det = f"{pt.time_to_first_detection:.1f}s" if pt.time_to_first_detection is not None else "None"
        print(f"{name:<18} | P{pct:<6} | {pt.recall:<6.2f} | {snr_str:<8} | {det}")
