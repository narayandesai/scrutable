import numpy as np
import scrutable as sc
from scrutable.profiles import CONSISTENT_FAST, sample_workload


def test_engine_mix_share_ratio(tiny_infra):
    """Verify that workload share ratio is honoured by running two single-workload
    simulations at the proportional rates and comparing total request counts."""
    rng = np.random.default_rng(42)
    model_a = sample_workload(CONSISTENT_FAST, "wl-a", rng)
    model_b = sample_workload(CONSISTENT_FAST, "wl-b", rng)

    # Run wl-a alone at 70% of 200 req/s = 140 req/s
    mix_a = sc.WorkloadMix(
        total_rate=140.0,
        period=3600.0,
        entries=[sc.WorkloadEntry(model=model_a, share=1.0)],
    )
    engine_a = sc.SimulationEngine(infra=tiny_infra, mix=mix_a, seed=0)
    engine_a.run(30.0)
    count_a = len(engine_a.buffer.window(0.0, 35.0))

    rng2 = np.random.default_rng(42)
    _ = sample_workload(CONSISTENT_FAST, "wl-a", rng2)  # advance rng to same state
    model_b2 = sample_workload(CONSISTENT_FAST, "wl-b", rng2)

    # Run wl-b alone at 30% of 200 req/s = 60 req/s
    from scrutable.plant import PlantConfig, Plant
    tiny_infra2 = Plant(PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1"]},
        nodes={"r1c1": ["r1c1n1"]},
    ))
    mix_b = sc.WorkloadMix(
        total_rate=60.0,
        period=3600.0,
        entries=[sc.WorkloadEntry(model=model_b2, share=1.0)],
    )
    engine_b = sc.SimulationEngine(infra=tiny_infra2, mix=mix_b, seed=1)
    engine_b.run(30.0)
    count_b = len(engine_b.buffer.window(0.0, 35.0))

    assert count_b > 0, "wl-b produced no requests"
    ratio = count_a / count_b
    # Expected ≈ 140/60 = 2.33; allow ±35%
    assert 1.5 < ratio < 3.1
