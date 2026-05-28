import numpy as np
from scrutable.models import WorkloadState, Disturbance, DisturbanceScope
from scrutable.event_loop import EventLoop
from scrutable.disturbance import (
    stable_subset,
    apply_disturbance,
    remove_disturbance,
    TimedDisturbance,
    StochasticDisturbance,
    DisturbanceInjector,
)


def test_stable_subset_is_deterministic():
    entities = [f"node-{i}" for i in range(100)]
    s1 = stable_subset(entities, 0.3, "disturbance-1")
    s2 = stable_subset(entities, 0.3, "disturbance-1")
    assert s1 == s2


def test_stable_subset_percentage_approximate():
    entities = [f"node-{i}" for i in range(1000)]
    result = stable_subset(entities, 0.3, "d1")
    assert 200 < len(result) < 400


def test_stable_subset_full_coverage():
    entities = ["a", "b", "c"]
    result = stable_subset(entities, 1.0, "d1")
    assert result == set(entities)


def test_stable_subset_zero_returns_empty():
    entities = ["a", "b", "c"]
    result = stable_subset(entities, 0.0, "d1")
    assert result == set()


def test_stable_subset_different_disturbances_differ():
    entities = [f"node-{i}" for i in range(100)]
    s1 = stable_subset(entities, 0.5, "disturbance-A")
    s2 = stable_subset(entities, 0.5, "disturbance-B")
    assert s1 != s2


def test_apply_disturbance_mutates_node_state(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    disturbance = Disturbance(
        disturbance_id="d1",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 3.0},
    )
    apply_disturbance(disturbance, tiny_infra, workload_states)
    for node in tiny_infra.all_nodes():
        assert node.latency_multiplier == 3.0


def test_apply_disturbance_respects_percentage(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    disturbance = Disturbance(
        disturbance_id="d-half",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=0.5),
        node_effects={"latency_multiplier": 5.0},
    )
    apply_disturbance(disturbance, tiny_infra, workload_states)
    affected = [n for n in tiny_infra.all_nodes() if n.latency_multiplier == 5.0]
    assert 0 < len(affected) < 12


def test_apply_disturbance_filter_by_cluster(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    disturbance = Disturbance(
        disturbance_id="d-cluster",
        scope=DisturbanceScope(target_type="node", filter_id="r1c1", percentage=1.0),
        node_effects={"latency_multiplier": 2.0},
    )
    apply_disturbance(disturbance, tiny_infra, workload_states)
    for node in tiny_infra.all_nodes():
        if node.cluster_id == "r1c1":
            assert node.latency_multiplier == 2.0
        else:
            assert node.latency_multiplier == 1.0


def test_apply_disturbance_mutates_workload_state(tiny_infra):
    workload_states = {
        "wl1": WorkloadState(workload_id="wl1"),
        "wl2": WorkloadState(workload_id="wl2"),
    }
    disturbance = Disturbance(
        disturbance_id="d-wl",
        scope=DisturbanceScope(target_type="workload", filter_id=None, percentage=1.0),
        workload_effects={"error_rate_multiplier": 10.0},
    )
    apply_disturbance(disturbance, tiny_infra, workload_states)
    assert workload_states["wl1"].error_rate_multiplier == 10.0
    assert workload_states["wl2"].error_rate_multiplier == 10.0


def test_remove_disturbance_resets_node_state(tiny_infra):
    workload_states: dict[str, WorkloadState] = {}
    disturbance = Disturbance(
        disturbance_id="d1",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 4.0},
    )
    apply_disturbance(disturbance, tiny_infra, workload_states)
    remove_disturbance(disturbance, tiny_infra, workload_states)
    for node in tiny_infra.all_nodes():
        assert node.latency_multiplier == 1.0


def test_timed_disturbance_injected_at_correct_time(tiny_infra):
    loop = EventLoop()
    workload_states: dict[str, WorkloadState] = {}
    rng = np.random.default_rng(42)
    injector = DisturbanceInjector(loop, tiny_infra, workload_states, rng)
    disturbance = Disturbance(
        disturbance_id="timed",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 2.0},
    )
    injector.add_timed(TimedDisturbance(disturbance=disturbance, inject_at=5.0))
    loop.run(3.0)
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 1.0
    loop.run(6.0)
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 2.0


def test_timed_disturbance_removed_at_correct_time(tiny_infra):
    loop = EventLoop()
    workload_states: dict[str, WorkloadState] = {}
    rng = np.random.default_rng(42)
    injector = DisturbanceInjector(loop, tiny_infra, workload_states, rng)
    disturbance = Disturbance(
        disturbance_id="timed-remove",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 2.0},
    )
    injector.add_timed(TimedDisturbance(disturbance=disturbance, inject_at=5.0, remove_at=10.0))
    loop.run(7.0)
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 2.0
    loop.run(11.0)
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 1.0


def test_stochastic_disturbance_fires_over_time(tiny_infra):
    loop = EventLoop()
    workload_states: dict[str, WorkloadState] = {}
    rng = np.random.default_rng(42)
    injector = DisturbanceInjector(loop, tiny_infra, workload_states, rng)
    disturbance = Disturbance(
        disturbance_id="stoch",
        scope=DisturbanceScope(target_type="node", filter_id=None, percentage=1.0),
        node_effects={"latency_multiplier": 2.0},
    )
    injector.add_stochastic(StochasticDisturbance(disturbance=disturbance, rate=2.0, duration=100.0))
    # rate=2/s, duration=100s — fires quickly and stays applied; after 5s should be in modified state
    loop.run(5.0)
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 2.0
