"""
SLO threshold detection across the latency variance spectrum.

For each of the five spectrum profiles (ordered by increasing latency variance),
runs a scenario with a fixed-magnitude disturbance injected after burn-in,
then plots P50/P90/P99/P99.9 over time with the SLO threshold, disturbance
marker, and detection marker (if detected).

Usage:
    uv run examples/slo_spectrum_demo.py
    uv run examples/slo_spectrum_demo.py --save slo_spectrum.html
"""
from __future__ import annotations
import argparse
import sys
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import scrutable as sc
from scrutable.scenarios.slo_spectrum import run_slo_scenario, ScenarioResult

RATE = 200.0        # req/s per workload (×20 workloads = 4000 total)
BURN_IN = 60.0      # long enough for v5 tail (P99.9≈10s) to fully arrive before calibrating
POST_DISTURBANCE = 30.0
N_WORKLOADS = 20
DISTURBANCE_ADDEND = 1.0   # additive latency penalty on affected nodes (seconds)
DISTURBANCE_COVERAGE = 0.5  # fraction of nodes affected
SEED = 42

PERCENTILE_COLORS = {
    "p50":  "#4C9BE8",
    "p90":  "#F5A623",
    "p99":  "#E8754C",
    "p999": "#C0392B",
}


def build_figure(results: list[ScenarioResult]) -> go.Figure:
    n = len(results)
    fig = make_subplots(
        rows=n,
        cols=1,
        shared_xaxes=True,
        subplot_titles=[r.profile_name for r in results],
        vertical_spacing=0.06,
    )

    for row, result in enumerate(results, start=1):
        ts = [w.t_start for w in result.windows]
        show_legend = row == 1

        for pct, color in PERCENTILE_COLORS.items():
            values = [getattr(w, pct) for w in result.windows]
            fig.add_trace(
                go.Scatter(
                    x=ts,
                    y=values,
                    mode="lines",
                    name=pct.upper().replace("999", "99.9"),
                    line=dict(color=color, width=1.5),
                    showlegend=show_legend,
                    legendgroup=pct,
                ),
                row=row,
                col=1,
            )

        # SLO threshold
        fig.add_hline(
            y=result.slo_threshold_p999,
            line=dict(color="#C0392B", dash="dash", width=1),
            row=row,
            col=1,
            annotation_text="SLO" if row == 1 else None,
            annotation_position="top right",
        )

        # Disturbance injection marker
        fig.add_vline(
            x=result.disturbance_at,
            line=dict(color="gray", dash="dot", width=1.5),
            row=row,
            col=1,
        )

        # Detection marker
        if result.detection_time is not None:
            fig.add_vline(
                x=result.detection_time,
                line=dict(color="#27AE60", dash="solid", width=2),
                row=row,
                col=1,
            )

    fig.update_layout(
        height=260 * n,
        title=dict(
            text=(
                "SLO Threshold Detection Across Latency Variance Spectrum<br>"
                f"<sup>Disturbance: +{DISTURBANCE_ADDEND}s addend on {int(DISTURBANCE_COVERAGE*100)}% of nodes at T={BURN_IN}s  |  "
                f"Gray dotted = disturbance injected  |  Green solid = detected  |  "
                f"Red dashed = SLO threshold</sup>"
            ),
            x=0.5,
        ),
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
        template="plotly_white",
    )
    fig.update_xaxes(title_text="Simulation time (s)", row=n, col=1)
    fig.update_yaxes(title_text="Latency (s)")

    return fig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", metavar="FILE", help="save to HTML file instead of opening browser")
    args = parser.parse_args()

    print("Running SLO spectrum scenarios...")
    results = []
    for i, profile in enumerate(sc.LATENCY_VARIANCE_SPECTRUM, 1):
        print(f"  [{i}/{len(sc.LATENCY_VARIANCE_SPECTRUM)}] {profile.name}...", end=" ", flush=True)
        result = run_slo_scenario(
            profile,
            seed=SEED,
            rate=RATE,
            calibration_duration=BURN_IN,
            post_disturbance=POST_DISTURBANCE,
            n_workloads=N_WORKLOADS,
            disturbance_addend=DISTURBANCE_ADDEND,
            disturbance_coverage=DISTURBANCE_COVERAGE,
        )
        detected = f"detected at T={result.detection_time:.1f}s" if result.detection_time else "not detected"
        print(detected)
        results.append(result)

    fig = build_figure(results)

    if args.save:
        fig.write_html(args.save)
        print(f"Saved to {args.save}")
    else:
        fig.show()


if __name__ == "__main__":
    main()
