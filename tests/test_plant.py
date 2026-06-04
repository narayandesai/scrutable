import pytest
from scrutable.plant import PlantConfig, Plant


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


def test_set_cluster_enabled_reflects_in_enabled_clusters(tiny_infra):
    tiny_infra.set_cluster_enabled("r1c1", False)
    enabled_ids = {c.cluster_id for c in tiny_infra.enabled_clusters()}
    assert "r1c1" not in enabled_ids
    tiny_infra.set_cluster_enabled("r1c1", True)
    enabled_ids = {c.cluster_id for c in tiny_infra.enabled_clusters()}
    assert "r1c1" in enabled_ids


def test_enabled_clusters_cache_invalidated_on_set(tiny_infra):
    first = tiny_infra.enabled_clusters()
    tiny_infra.set_cluster_enabled("r1c1", False)
    second = tiny_infra.enabled_clusters()
    assert len(second) == len(first) - 1


def test_plant_capacity_weight_applied_from_config():
    config = PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1", "r1c2"]},
        nodes={"r1c1": ["r1c1n1"], "r1c2": ["r1c2n1"]},
        capacity_weights={"r1c1": 2.0},
    )
    plant = Plant(config)
    assert plant.get_cluster("r1c1").capacity_weight == 2.0
    assert plant.get_cluster("r1c2").capacity_weight == 1.0


def test_plant_capacity_weight_defaults_to_one():
    config = PlantConfig(
        regions=["r1"],
        clusters={"r1": ["r1c1"]},
        nodes={"r1c1": ["r1c1n1"]},
    )
    plant = Plant(config)
    assert plant.get_cluster("r1c1").capacity_weight == 1.0
