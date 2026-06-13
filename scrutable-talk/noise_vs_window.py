"""Window-size sweep: does wider windows reduce P99.9 noise?

Compares SPHERICAL_COW (single stable workload) vs long_tail (50k workloads,
10% active via MarkovActivity) across window sizes [1s, 5s, 30s, 60s, 120s].

Each profile runs ONE simulation (length = max_window * n_cal_windows + post),
then re-analyzes the buffer at each window size. The two profiles run in parallel.

Expected:
  SPHERICAL_COW: noise(P99.9) ∝ 1/sqrt(window) — purely estimator variance, reducible
  long_tail:     noise(P99.9) drops slowly or plateaus — mix-shift dominated, irreducible at
                 any window size useful for detection
"""
from __future__ import annotations
import time
from scrutable.profiles import SPHERICAL_COW, make_long_tail
from scrutable.scenarios.slo_performance import sweep_slo_performance

WINDOW_SIZES = [1.0, 5.0, 30.0, 60.0, 120.0]


def _sweep(profile_name: str, total_rate: float) -> list:
    from scrutable.profiles import SPHERICAL_COW, make_long_tail
    from scrutable.scenarios.slo_performance import sweep_slo_performance
    profile = SPHERICAL_COW if profile_name == "spherical_cow" else make_long_tail()
    # workers=1: shared simulation already handles all window sizes in one pass
    return sweep_slo_performance(
        [profile], WINDOW_SIZES,
        seed=42, total_rate=total_rate, n_calibration_windows=30,
        post_disturbance=30.0, disturbance_addend=0.3, disturbance_coverage=0.5,
        target_fpr=0.001, percentile=99.9, workers=1,
    )


if __name__ == "__main__":
    from concurrent.futures import ProcessPoolExecutor, as_completed
    t0 = time.time()

    jobs = [("spherical_cow", 10_000.0), ("long_tail", 100_000.0)]
    results: dict[str, list] = {}

    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_sweep, name, rate): name for name, rate in jobs}
        for fut in as_completed(futures):
            name = futures[fut]
            results[name] = fut.result()
            print(f"  {name} done", flush=True)

    print(f"\nDone in {time.time() - t0:.1f}s\n")

    # Table: noise(P99.9) and noise(P50) per profile per window size
    print(f"{'Window':>8} | {'SC noise(P99.9)':>16} | {'SC noise(P50)':>14} | {'LT noise(P99.9)':>16} | {'LT noise(P50)':>14} | {'Noise ratio(P99.9)':>20}")
    print("-" * 100)
    for ws in WINDOW_SIZES:
        sc = next(p for p in results["spherical_cow"] if p.window_size == ws)
        lt = next(p for p in results["long_tail"] if p.window_size == ws)
        sc_n999 = sc.noise.get(99.9)
        sc_n50  = sc.noise.get(50.0)
        lt_n999 = lt.noise.get(99.9)
        lt_n50  = lt.noise.get(50.0)
        ratio = (lt_n999 / sc_n999) if (sc_n999 and lt_n999) else None
        def fmt(v): return f"{v:.4f}s" if v is not None else "None"
        def fmt_r(v): return f"{v:.0f}×" if v is not None else "None"
        ws_str = f"{ws:.0f}s" if ws < 60 else f"{ws/60:.0f}m"
        print(f"{ws_str:>8} | {fmt(sc_n999):>16} | {fmt(sc_n50):>14} | {fmt(lt_n999):>16} | {fmt(lt_n50):>14} | {fmt_r(ratio):>20}")

    print()
    print("If 'wider windows fix P99.9': long_tail noise(P99.9) should drop like SPHERICAL_COW.")
    print("If mix-shift dominated: the ratio column stays large or grows across window sizes.")
