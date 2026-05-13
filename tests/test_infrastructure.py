import pytest
from scrutable.infrastructure import InfrastructureConfig, InfrastructureModel


def test_enabled_clusters_returns_all_by_default(tiny_infra):
    assert len(tiny_infra.enabled_clusters()) == 4


def test_enabled_clusters_excludes_disabled(tiny_infra):
    tiny_infra.get_cluster("r1c1").traffic_enabled = False
    enabled = tiny_infra.enabled_clusters()
    assert len(enabled) == 3
    assert all(c.cluster_id != "r1c1" for c in enabled)


def test_nodes_in_cluster_returns_correct_nodes(tiny_infra):
    nodes = tiny_infra.nodes_in_cluster("r1c1")
    assert len(nodes) == 3
    assert "r1c1n1" in nodes
    assert "r1c1n2" in nodes
    assert "r1c1n3" in nodes


def test_get_node_returns_correct_metadata(tiny_infra):
    node = tiny_infra.get_node("r2c1n2")
    assert node.cluster_id == "r2c1"
    assert node.region_id == "r2"


def test_get_cluster_returns_correct_metadata(tiny_infra):
    cluster = tiny_infra.get_cluster("r2c2")
    assert cluster.region_id == "r2"
    assert cluster.traffic_enabled is True


def test_all_nodes_returns_all_12(tiny_infra):
    assert len(tiny_infra.all_nodes()) == 12


def test_all_clusters_returns_all_4(tiny_infra):
    assert len(tiny_infra.all_clusters()) == 4


def test_node_mutation_persists(tiny_infra):
    node = tiny_infra.get_node("r1c1n1")
    node.latency_multiplier = 5.0
    assert tiny_infra.get_node("r1c1n1").latency_multiplier == 5.0


def test_unknown_node_raises(tiny_infra):
    with pytest.raises(KeyError):
        tiny_infra.get_node("nonexistent")
