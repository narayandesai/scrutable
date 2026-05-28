from scrutable.models import (
    WorkloadModel,
    WorkloadState,
    NodeState,
    ClusterState,
    Request,
    Response,
    DisturbanceScope,
    Disturbance,
    Inference,
)


def test_workload_model_defaults():
    m = WorkloadModel(
        workload_id="wl1",
        latency_median=0.1,
        latency_sigma=0.3,
        error_scale=100.0,
        error_shape=1.5,
        noise_sigma=0.01,
    )
    assert m.workload_id == "wl1"
    assert m.latency_median == 0.1


def test_workload_state_defaults():
    s = WorkloadState(workload_id="wl1")
    assert s.latency_multiplier == 1.0
    assert s.error_rate_multiplier == 1.0


def test_node_state_defaults():
    n = NodeState(node_id="n1", cluster_id="c1", region_id="r1")
    assert n.latency_multiplier == 1.0
    assert n.error_rate_multiplier == 1.0


def test_cluster_state_defaults():
    c = ClusterState(cluster_id="c1", region_id="r1")
    assert c.traffic_enabled is True


def test_request_fields():
    r = Request(request_id="req-1", workload_id="wl1", issued_at=5.0)
    assert r.issued_at == 5.0


def test_response_fields():
    r = Response(
        request_id="req-1",
        workload_id="wl1",
        node_id="n1",
        cluster_id="c1",
        region_id="r1",
        issued_at=0.0,
        latency=0.05,
        error_code=0,
    )
    assert r.error_code == 0


def test_disturbance_scope_defaults():
    s = DisturbanceScope(target_type="node", filter_id=None)
    assert s.percentage == 1.0


def test_disturbance_fields():
    d = Disturbance(
        disturbance_id="d1",
        scope=DisturbanceScope(target_type="node", filter_id=None),
        node_effects={"latency_multiplier": 2.0},
        workload_effects={},
    )
    assert d.node_effects["latency_multiplier"] == 2.0


def test_inference_fields():
    i = Inference(
        detector_id="d1",
        pathology_type="hardware_fault",
        target_id="n1",
        target_level="node",
        confidence=0.9,
        detected_at=10.0,
        window_start=0.0,
        window_end=10.0,
    )
    assert i.confidence == 0.9
