import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.observations import ObservationBuffer
from scrutable.models import WorkloadModel, WorkloadState
from scrutable.workload import WorkloadRegistry
from scrutable.simulator import ServiceSimulator
from scrutable.synthesizer import InputSynthesizer
from scrutable.traffic import WorkloadEntry, WorkloadMix, SinusoidalCurve


def _model(wid: str) -> WorkloadModel:
    return WorkloadModel(
        workload_id=wid,
        latency_median=0.01,
        latency_sigma=0.1,
        error_scale=1000.0,
        error_shape=1.5,
        noise_sigma=0.001,
    )


def _make_synth(tiny_infra, mix: WorkloadMix, seed: int = 42):
    loop = EventLoop()
    registry = WorkloadRegistry()
    for entry in mix.entries:
        registry.register(entry.model)
    workload_states = {
        entry.model.workload_id: WorkloadState(workload_id=entry.model.workload_id)
        for entry in mix.entries
    }
    buffer = ObservationBuffer()
    rng = np.random.default_rng(seed)
    sim = ServiceSimulator(loop, tiny_infra, registry, workload_states, buffer, rng)
    synth = InputSynthesizer(mix, loop, sim, rng)
    return loop, synth, buffer


def _single_workload_mix(wid: str, total_rate: float) -> WorkloadMix:
    return WorkloadMix(
        total_rate=total_rate,
        period=3600.0,
        entries=[WorkloadEntry(model=_model(wid), share=1.0)],
    )


def test_synthesizer_produces_responses(tiny_infra):
    mix = _single_workload_mix("wl1", 10.0)
    loop, synth, buffer = _make_synth(tiny_infra, mix)
    synth.start()
    loop.run(1.0)
    assert len(buffer.window(0.0, 2.0)) > 0


def test_synthesizer_rate_approximated(tiny_infra):
    mix = _single_workload_mix("wl1", 100.0)
    loop, synth, buffer = _make_synth(tiny_infra, mix, seed=0)
    synth.start()
    loop.run(10.0)
    count = len(buffer.window(0.0, 12.0))
    assert 700 < count < 1300


def test_synthesizer_multiple_workloads(tiny_infra):
    mix = WorkloadMix(
        total_rate=20.0,
        period=3600.0,
        entries=[
            WorkloadEntry(model=_model("wl1"), share=0.5),
            WorkloadEntry(model=_model("wl2"), share=0.5),
        ],
    )
    loop, synth, buffer = _make_synth(tiny_infra, mix)
    synth.start()
    loop.run(5.0)
    all_resp = buffer.window(0.0, 10.0)
    wids = {r.workload_id for r in all_resp}
    assert "wl1" in wids
    assert "wl2" in wids


def test_synthesizer_schedules_continuously(tiny_infra):
    mix = _single_workload_mix("wl1", 10.0)
    loop, synth, buffer = _make_synth(tiny_infra, mix)
    synth.start()
    loop.run(1.0)
    count_1s = len(buffer.window(0.0, 2.0))
    loop.run(2.0)
    count_2s = len(buffer.window(0.0, 3.0))
    assert count_2s > count_1s


def test_synthesizer_sinusoidal_peak_exceeds_trough(tiny_infra):
    curve = SinusoidalCurve(peak_phase=0.0, trough_depth=0.5)
    mix = WorkloadMix(
        total_rate=200.0,
        period=1000.0,
        entries=[WorkloadEntry(model=_model("wl1"), share=1.0, diurnal=curve)],
    )
    loop, synth, buffer = _make_synth(tiny_infra, mix, seed=0)
    synth.start()
    loop.run(1000.0)
    # peak at phase=0 (t=0), trough at phase=0.5 (t=500); compare narrow windows
    peak_count = len(buffer.window(0.0, 100.0))
    trough_count = len(buffer.window(450.0, 550.0))
    assert peak_count > trough_count


def test_synthesizer_70_30_split(tiny_infra):
    mix = WorkloadMix(
        total_rate=100.0,
        period=3600.0,
        entries=[
            WorkloadEntry(model=_model("wl1"), share=0.7),
            WorkloadEntry(model=_model("wl2"), share=0.3),
        ],
    )
    loop, synth, buffer = _make_synth(tiny_infra, mix, seed=0)
    synth.start()
    loop.run(30.0)
    responses = buffer.window(0.0, 35.0)
    count1 = sum(1 for r in responses if r.workload_id == "wl1")
    count2 = sum(1 for r in responses if r.workload_id == "wl2")
    ratio = count1 / count2
    assert 1.6 < ratio < 3.2  # expected ≈ 7/3 = 2.33
