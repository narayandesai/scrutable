"""
SLO detection performance across the latency variance spectrum.

For each combination of (variance profile, window size), measures:
  - Recall: fraction of post-disturbance windows where the detector fires
  - FPR: fraction of burn-in windows where the detector fires (false positives)

Plots both metrics vs window size with one line per profile, showing how
detection quality degrades as latency variance grows.

Usage:
    uv run examples/slo_performance_demo.py
    uv run examples/slo_performance_demo.py --save slo_performance.html
"""
from __future__ import annotations
import argparse
import scrutable as sc
from scrutable.scenarios.slo_performance import sweep_slo_performance
import plotly.graph_objects as go
from plotly.subplots import make_subplots

RATE = 5.0           # low rate: detection-window sample count drives estimation noise
N_WORKLOADS = 10
BURN_IN = 120.0      # long enough for stable calibration on all profiles (P99.9≈10s for v5)
POST_DISTURBANCE = 60.0
WINDOW_SIZES = [0.5, 1.0, 2.0, 5.0, 10.0, 20.0]
SEED = 42

PROFILE_COLORS = [
    "#4C9BE8",
    "#27AE60",
    "#F5A623",
    "#E8754C",
    "#C0392B",
]


def build_figure(results) -> go.Figure:
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["Recall vs window size", "False positive rate vs window size"],
        horizontal_spacing=0.12,
    )

    profiles_seen: list[str] = []
    by_profile: dict[str, list] = {}
    for pt in results:
        by_profile.setdefault(pt.profile_name, []).append(pt)

    for idx, (name, pts) in enumerate(by_profile.items()):
        pts_sorted = sorted(pts, key=lambda p: p.window_size)
        xs = [p.window_size for p in pts_sorted]
        recalls = [p.recall for p in pts_sorted]
        fprs = [p.fpr for p in pts_sorted]
        color = PROFILE_COLORS[idx % len(PROFILE_COLORS)]
        sigma = pts_sorted[0].sigma
        label = f"{name} (σ={sigma:.1f})"
        show = True

        fig.add_trace(go.Scatter(
            x=xs, y=recalls, mode="lines+markers",
            name=label, line=dict(color=color, width=2),
            marker=dict(size=7), showlegend=show, legendgroup=name,
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=xs, y=fprs, mode="lines+markers",
            name=label, line=dict(color=color, width=2),
            marker=dict(size=7), showlegend=False, legendgroup=name,
        ), row=1, col=2)

    fig.update_xaxes(title_text="Window size (s)", type="log")
    fig.update_yaxes(title_text="Recall", range=[0, 1.05], row=1, col=1)
    fig.update_yaxes(title_text="False positive rate", range=[-0.02, 1.05], row=1, col=2)
    fig.update_layout(
        height=500,
        title=dict(
            text=(
                "SLO Detection Performance: Recall and FPR vs Window Size<br>"
                f"<sup>Additive disturbance +0.8s on 50% of nodes  |  "
                f"Threshold calibrated on full burn-in (2× P99.9)  |  "
                f"Rate={int(RATE * N_WORKLOADS)} req/s  |  burn-in={BURN_IN}s</sup>"
            ),
            x=0.5,
        ),
        legend=dict(orientation="v", x=1.02, y=1),
        template="plotly_white",
    )
    return fig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", metavar="FILE")
    args = parser.parse_args()

    print("Sweeping performance across spectrum × window sizes...")
    print(f"  Profiles: {len(sc.LATENCY_VARIANCE_SPECTRUM)}  |  Window sizes: {WINDOW_SIZES}")

    results = sweep_slo_performance(
        sc.LATENCY_VARIANCE_SPECTRUM,
        WINDOW_SIZES,
        seed=SEED,
        rate=RATE,
        n_workloads=N_WORKLOADS,
        burn_in=BURN_IN,
        post_disturbance=POST_DISTURBANCE,
    )

    print("\nResults:")
    print(f"{'Profile':<16} {'W':>6} {'Recall':>8} {'FPR':>8}")
    for pt in results:
        print(f"{pt.profile_name:<16} {pt.window_size:>6.1f} {pt.recall:>8.2f} {pt.fpr:>8.2f}")

    fig = build_figure(results)

    if args.save:
        fig.write_html(args.save)
        print(f"\nSaved to {args.save}")
    else:
        fig.show()


if __name__ == "__main__":
    main()
