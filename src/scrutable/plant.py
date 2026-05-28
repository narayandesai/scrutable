from __future__ import annotations
from dataclasses import dataclass
from scrutable.models import NodeState, ClusterState


@dataclass
class PlantConfig:
    regions: list[str]
    clusters: dict[str, list[str]]   # region_id -> [cluster_id]
    nodes: dict[str, list[str]]       # cluster_id -> [node_id]


class Plant:
    def __init__(self, config: PlantConfig) -> None:
        self.regions: list[str] = config.regions
        self._clusters: dict[str, ClusterState] = {}
        self._nodes: dict[str, NodeState] = {}
        self._cluster_to_nodes: dict[str, list[str]] = {}

        for region_id, cluster_ids in config.clusters.items():
            for cluster_id in cluster_ids:
                self._clusters[cluster_id] = ClusterState(
                    cluster_id=cluster_id, region_id=region_id
                )
                node_ids = config.nodes.get(cluster_id, [])
                self._cluster_to_nodes[cluster_id] = node_ids
                for node_id in node_ids:
                    self._nodes[node_id] = NodeState(
                        node_id=node_id, cluster_id=cluster_id, region_id=region_id
                    )

    def get_cluster(self, cluster_id: str) -> ClusterState:
        return self._clusters[cluster_id]

    def get_node(self, node_id: str) -> NodeState:
        return self._nodes[node_id]

    def enabled_clusters(self) -> list[ClusterState]:
        return [c for c in self._clusters.values() if c.traffic_enabled]

    def nodes_in_cluster(self, cluster_id: str) -> list[str]:
        return self._cluster_to_nodes[cluster_id]

    def all_nodes(self) -> list[NodeState]:
        return list(self._nodes.values())

    def all_clusters(self) -> list[ClusterState]:
        return list(self._clusters.values())

    def all_node_ids(self) -> list[str]:
        return list(self._nodes.keys())

    def all_cluster_ids(self) -> list[str]:
        return list(self._clusters.keys())
