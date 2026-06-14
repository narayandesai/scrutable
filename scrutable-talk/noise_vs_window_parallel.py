"""Window-size sweep with parallel workload simulation.

Same experiment as noise_vs_window.py but workload chunks across both profiles
are submitted to a single flat ProcessPoolExecutor(max_workers=15).

Workers receive only lightweight scalar arguments and reconstruct their own
profile slice inside the worker — avoids pickling large PlantProfile objects
over pipes, which was serializing worker startup.

Layout:
  SPHERICAL_COW  → 1 chunk  (worker 0)
  long_tail      → 14 chunks (workers 1-14)
"""
from __future__ import annotations
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from scrutable.profiles import SPHERICAL_COW, make_long_tail, split_profile
from scrutable.scenarios.slo_performance import _run_chunk_by_index_histogram_kwargs, _analyze_buffer
from scrutable.histogram_buffer import merge_histogram_buffers

WINDOW_SIZES  = [1.0, 5.0, 30.0, 60.0, 120.0]
N_CAL_WINDOWS = 30
POST_DIST     = 30.0
DIST_ADDEND   = 0.3
DIST_COVERAGE = 0.5
TARGET_FPR    = 0.001
PERCENTILE    = 99.9
PERCENTILES = (50.0, 75.0, 90.0, 99.0, 99.9)
SEED          = 42
PROFILE_SEED  = 42  # seed for make_long_tail RNG

DISTURBANCE_AT = max(WINDOW_SIZES) * N_CAL_WINDOWS   # 3600s
TOTAL_DURATION = DISTURBANCE_AT + POST_DIST

COMMON = dict(
    total_rate=0,           # overridden per profile
    total_duration=TOTAL_DURATION,
    disturbance_at=DISTURBANCE_AT,
    disturbance_addend=DIST_ADDEND,
    disturbance_coverage=DIST_COVERAGE,
)

def _write_csv(results: dict[str, dict], window_sizes: list[float], path: "Path") -> None:
    import csv
    percentiles = (50.0, 75.0, 90.0, 99.0, 99.9)
    fieldnames = ["profile", "window_size", "recall", "fpr",
                  *[f"noise_p{p}".replace(".", "_") for p in percentiles],
                  *[f"snr_p{p}".replace(".", "_") for p in percentiles]]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for name, ws_map in results.items():
            for ws in window_sizes:
                p = ws_map[ws]
                row = {"profile": name, "window_size": ws,
                       "recall": p.recall, "fpr": p.fpr}
                for pct in percentiles:
                    row[f"noise_p{pct}".replace(".", "_")] = p.noise.get(pct)
                    row[f"snr_p{pct}".replace(".", "_")] = p.snr.get(pct)
                w.writerow(row)


if __name__ == "__main__":
    from pathlib import Path
    t0 = time.time()

    sc_jobs = [dict(
        profile_factory="spherical_cow", chunk_index=0, n_chunks=1,
        profile_seed=PROFILE_SEED, sim_seed=SEED,
        **{**COMMON, "total_rate": 10_000.0},
        histogram_percentiles=PERCENTILES,
    )]
    lt_jobs = [dict(
        profile_factory="long_tail", chunk_index=i, n_chunks=14,
        profile_seed=PROFILE_SEED, sim_seed=SEED + i,
        **{**COMMON, "total_rate": 100_000.0},
        histogram_percentiles=PERCENTILES,
    ) for i in range(14)]

    all_jobs = [("spherical_cow", kw) for kw in sc_jobs] + \
               [("long_tail",     kw) for kw in lt_jobs]

    chunk_buffers: dict[str, list] = {"spherical_cow": [], "long_tail": []}

    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_run_chunk_by_index_histogram_kwargs, kw): name for name, kw in all_jobs}
        for fut in as_completed(futures):
            name = futures[fut]
            chunk_buffers[name].append(fut.result())
            print(f"  chunk done for {name} ({time.time()-t0:.1f}s)", flush=True)

    print(f"\nAll chunks done in {time.time()-t0:.1f}s — merging and analyzing...", flush=True)

    profiles_meta = {
        "spherical_cow": SPHERICAL_COW,
        "long_tail":     make_long_tail(rng=__import__("numpy").random.default_rng(PROFILE_SEED)),
    }
    results: dict[str, dict] = {}
    for name, profile in profiles_meta.items():
        # pop frees the chunk buffers once merged; one profile in memory at a time.
        buf = merge_histogram_buffers(chunk_buffers.pop(name))
        sigma = profile.entries[0].spec.latency_sigma
        pts = [
            _analyze_buffer(
                buf=buf,
                profile_name=name,
                sigma=sigma,
                window_size=ws,
                calibration_duration=ws * N_CAL_WINDOWS,
                disturbance_at=DISTURBANCE_AT,
                total_duration=TOTAL_DURATION,
                percentile=PERCENTILE,
                target_fpr=TARGET_FPR,
            )
            for ws in WINDOW_SIZES
        ]
        results[name] = {p.window_size: p for p in pts}

    print(f"\nDone in {time.time()-t0:.1f}s\n")

    print(f"{'Window':>8} | {'SC noise(P99.9)':>16} | {'SC noise(P50)':>14} | {'LT noise(P99.9)':>16} | {'LT noise(P50)':>14} | {'Noise ratio(P99.9)':>20}")
    print("-" * 100)
    for ws in WINDOW_SIZES:
        sc   = results["spherical_cow"][ws]
        lt_r = results["long_tail"][ws]
        sc_n999 = sc.noise.get(99.9)
        sc_n50  = sc.noise.get(50.0)
        lt_n999 = lt_r.noise.get(99.9)
        lt_n50  = lt_r.noise.get(50.0)
        ratio   = (lt_n999 / sc_n999) if (sc_n999 and lt_n999) else None
        def fmt(v):   return f"{v:.4f}s" if v is not None else "None"
        def fmt_r(v): return f"{v:.0f}×"  if v is not None else "None"
        ws_str = f"{ws:.0f}s" if ws < 60 else f"{ws/60:.0f}m"
        print(f"{ws_str:>8} | {fmt(sc_n999):>16} | {fmt(sc_n50):>14} | {fmt(lt_n999):>16} | {fmt(lt_n50):>14} | {fmt_r(ratio):>20}")

    print()
    print("If 'wider windows fix P99.9': LT noise(P99.9) drops like SC noise(P99.9).")
    print("If mix-shift dominated: ratio stays large or grows.")

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / "noise_vs_window_parallel.csv"
    _write_csv(results, WINDOW_SIZES, csv_path)
    print(f"\nResults saved to {csv_path}")
