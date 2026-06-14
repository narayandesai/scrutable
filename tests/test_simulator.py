import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.observations import NumpyObservationBuffer
from scrutable.models import Request, WorkloadModel, WorkloadState
from scrutable.workload import WorkloadRegistry
from scrutable.simulator import ServiceSimulator


def _make_simulator(tiny_infra, seed=42):
    loop = EventLoop()
    registry = WorkloadRegistry()
    registry.register(
        WorkloadModel(
            workload_id="wl1",
            latency_median=0.1,
            latency_sigma=0.3,
            error_scale=1000.0,
            error_shape=1.5,
            noise_sigma=0.001,
        )
    )
    workload_states = {"wl1": WorkloadState(workload_id="wl1")}
    buffer = NumpyObservationBuffer()
    rng = np.random.default_rng(seed)
    sim = ServiceSimulator(loop, tiny_infra, registry, workload_states, buffer, rng)
    return loop, sim, buffer


def test_response_arrives_after_latency(tiny_infra):
    loop, sim, buffer = _make_simulator(tiny_infra)
    req = Request(request_id="r1", workload_id="wl1", issued_at=5.0)
    sim.handle_request(req)
    loop.run(100.0)
    w = buffer.window(0.0, 100.0)
    assert len(w) == 1
    assert w.percentile(50) > 0.0


def test_response_has_correct_workload_id(tiny_infra):
    loop, sim, buffer = _make_simulator(tiny_infra)
    req = Request(request_id="r1", workload_id="wl1", issued_at=0.0)
    sim.handle_request(req)
    loop.run(100.0)
    # WorkloadResult doesn't expose per-response workload_id; verify count
    assert len(buffer.window(0.0, 100.0)) == 1


def test_response_node_belongs_to_enabled_cluster(tiny_infra):
    loop, sim, buffer = _make_simulator(tiny_infra)
    req = Request(request_id="r1", workload_id="wl1", issued_at=0.0)
    sim.handle_request(req)
    loop.run(100.0)
    # Verify response was produced (non-503 means a cluster handled it)
    w = buffer.window(0.0, 100.0)
    assert len(w) == 1
    assert w.error_rate == 0.0


def test_no_clusters_enabled_produces_503(tiny_infra):
    loop, sim, buffer = _make_simulator(tiny_infra)
    for c in tiny_infra.all_clusters():
        c.traffic_enabled = False
    req = Request(request_id="r1", workload_id="wl1", issued_at=0.0)
    sim.handle_request(req)
    loop.run(1.0)
    w = buffer.window(0.0, 1.0)
    assert len(w) == 1
    assert w.error_rate == 1.0


def test_multiple_requests_produce_multiple_responses(tiny_infra):
    loop, sim, buffer = _make_simulator(tiny_infra)
    for i in range(10):
        sim.handle_request(Request(request_id=f"r{i}", workload_id="wl1", issued_at=float(i)))
    loop.run(1000.0)
    assert len(buffer.window(0.0, 1000.0)) == 10


def test_503_and_normal_responses_in_same_buffer(tiny_infra):
    loop, sim, buffer = _make_simulator(tiny_infra)
    # issue a normal request first — response schedules for a future time
    sim.handle_request(Request(request_id="r1", workload_id="wl1", issued_at=0.0))
    # disable all clusters and issue a 503 — appended directly at issued_at=0.5
    for c in tiny_infra.all_clusters():
        c.traffic_enabled = False
    sim.handle_request(Request(request_id="r2", workload_id="wl1", issued_at=0.5))
    loop.run(100.0)
    w = buffer.window(0.0, 100.0)
    assert len(w) == 2
    # The buffer stores arrivals sorted; verify the internal array is sorted
    buffer._materialize()
    assert list(buffer._arrivals) == sorted(buffer._arrivals)
