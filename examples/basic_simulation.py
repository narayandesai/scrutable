import numpy as np
import scrutable as sc
from scrutable import sample_workload, CONSISTENT_FAST, HIGH_VARIANCE_LATENCY, BURSTY_ERRORS, SLOW_RELIABLE

# --- Constants ---
SEED = 42
DURATION = 30.0
RATE_PER_WORKLOAD = 50.0   # req/s
WORKLOADS_PER_PROFILE = 5

PROFILES = [CONSISTENT_FAST, HIGH_VARIANCE_LATENCY, BURSTY_ERRORS, SLOW_RELIABLE]


def build_registry(rng: np.random.Generator) -> tuple[sc.WorkloadRegistry, dict[str, float]]:
    registry = sc.WorkloadRegistry()
    rates: dict[str, float] = {}
    for profile in PROFILES:
        for i in range(WORKLOADS_PER_PROFILE):
            wid = f"{profile.name}-{i}"
            registry.register(sample_workload(profile, wid, rng))
            rates[wid] = RATE_PER_WORKLOAD
    return registry, rates


def main() -> None:
    rng = np.random.default_rng(SEED)

    infra_config = sc.InfrastructureConfig(
        regions=["r1", "r2"],
        clusters={"r1": ["r1c1", "r1c2"], "r2": ["r2c1", "r2c2"]},
        nodes={
            "r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"],
            "r1c2": ["r1c2n1", "r1c2n2", "r1c2n3"],
            "r2c1": ["r2c1n1", "r2c1n2", "r2c1n3"],
            "r2c2": ["r2c2n1", "r2c2n2", "r2c2n3"],
        },
    )
    infra = sc.InfrastructureModel(infra_config)

    registry, rates = build_registry(rng)
    total_workloads = len(PROFILES) * WORKLOADS_PER_PROFILE
    total_rate = total_workloads * RATE_PER_WORKLOAD

    engine = sc.SimulationEngine(
        infra=infra,
        registry=registry,
        synth_config=sc.SynthesizerConfig(workload_rates=rates),
        seed=SEED,
    )
    engine.run(DURATION)

    responses = engine.buffer.window(0.0, DURATION + 1.0)
    latencies = np.array([r.latency for r in responses])
    errors = sum(1 for r in responses if r.error_code != 0)

    profile_counts = "  ".join(f"5x {p.name}" for p in PROFILES)

    print("Scrutable — basic simulation")
    print(f"Infrastructure: 2 regions, 4 clusters, 12 nodes")
    print(f"Workloads:      {total_workloads} ({profile_counts})")
    print(f"Rate:           {int(total_rate)} req/s total  |  Duration: {int(DURATION)}s  |  seed={SEED}")
    print()
    print(f"Responses:      {len(responses):,}")
    if len(latencies) > 0:
        p50 = float(np.percentile(latencies, 50))
        p95 = float(np.percentile(latencies, 95))
        p99 = float(np.percentile(latencies, 99))
        print(f"Latency:        p50={p50:.3f}s  p95={p95:.3f}s  p99={p99:.3f}s")
    print(f"Errors:         {errors:,} ({errors / len(responses) * 100:.1f}%)" if responses else "Errors:         0")

    # TODO Scenario B: inject a timed pathology at T=10 and observe latency/error signal
    # TODO Scenario C: add a Detector and Actuator to close the detection/remediation loop


if __name__ == "__main__":
    main()
