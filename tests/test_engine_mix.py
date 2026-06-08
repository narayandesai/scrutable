import numpy as np
import scrutable as sc
from scrutable.profiles import CONSISTENT_FAST, sample_workload


def test_engine_mix_share_ratio(tiny_infra):
    rng = np.random.default_rng(42)
    model_a = sample_workload(CONSISTENT_FAST, "wl-a", rng)
    model_b = sample_workload(CONSISTENT_FAST, "wl-b", rng)
    mix = sc.WorkloadMix(
        total_rate=200.0,
        period=3600.0,
        entries=[
            sc.WorkloadEntry(model=model_a, share=0.7),
            sc.WorkloadEntry(model=model_b, share=0.3),
        ],
    )
    engine = sc.SimulationEngine(infra=tiny_infra, mix=mix, seed=0)
    engine.run(30.0)
    responses = engine.buffer.window(0.0, 35.0)
    count_a = sum(1 for r in responses if r.workload_id == "wl-a")
    count_b = sum(1 for r in responses if r.workload_id == "wl-b")
    ratio = count_a / count_b
    # Expected ≈ 7/3 = 2.33; allow ±35%
    assert 1.5 < ratio < 3.1
