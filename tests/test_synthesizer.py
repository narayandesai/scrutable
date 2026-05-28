import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.observations import ObservationBuffer
from scrutable.models import WorkloadModel, WorkloadState
from scrutable.workload import WorkloadRegistry
from scrutable.simulator import ServiceSimulator
from scrutable.synthesizer import InputConfig, InputSynthesizer


def _make_synth(tiny_infra, rates, seed=42):
    loop = EventLoop()
    registry = WorkloadRegistry()
    for wid in rates:
        registry.register(
            WorkloadModel(
                workload_id=wid,
                latency_median=0.01,
                latency_sigma=0.1,
                error_scale=1000.0,
                error_shape=1.5,
                noise_sigma=0.001,
            )
        )
    workload_states = {wid: WorkloadState(workload_id=wid) for wid in rates}
    buffer = ObservationBuffer()
    rng = np.random.default_rng(seed)
    sim = ServiceSimulator(loop, tiny_infra, registry, workload_states, buffer, rng)
    config = InputConfig(workload_rates=rates)
    synth = InputSynthesizer(config, loop, sim, rng)
    return loop, synth, buffer


def test_synthesizer_produces_responses(tiny_infra):
    loop, synth, buffer = _make_synth(tiny_infra, {"wl1": 10.0})
    synth.start()
    loop.run(1.0)
    assert len(buffer.window(0.0, 2.0)) > 0


def test_synthesizer_rate_approximated(tiny_infra):
    loop, synth, buffer = _make_synth(tiny_infra, {"wl1": 100.0}, seed=0)
    synth.start()
    loop.run(10.0)
    count = len(buffer.window(0.0, 12.0))
    # 100 req/s over 10s = ~1000 requests; allow generous tolerance
    assert 700 < count < 1300


def test_synthesizer_multiple_workloads(tiny_infra):
    loop, synth, buffer = _make_synth(tiny_infra, {"wl1": 10.0, "wl2": 10.0})
    synth.start()
    loop.run(5.0)
    all_resp = buffer.window(0.0, 10.0)
    wids = {r.workload_id for r in all_resp}
    assert "wl1" in wids
    assert "wl2" in wids


def test_synthesizer_schedules_continuously(tiny_infra):
    loop, synth, buffer = _make_synth(tiny_infra, {"wl1": 10.0})
    synth.start()
    loop.run(1.0)
    count_1s = len(buffer.window(0.0, 2.0))
    loop.run(2.0)
    count_2s = len(buffer.window(0.0, 3.0))
    assert count_2s > count_1s
