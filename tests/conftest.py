import pytest
import numpy as np


@pytest.fixture
def seeded_rng():
    return np.random.default_rng(42)


@pytest.fixture
def build_response():
    from scrutable.models import Response

    counter = [0]

    def _build(
        workload_id="wl1",
        node_id="n1",
        cluster_id="c1",
        region_id="r1",
        issued_at=0.0,
        latency=0.1,
        error_code=0,
    ):
        counter[0] += 1
        return Response(
            request_id=f"req-{counter[0]}",
            workload_id=workload_id,
            node_id=node_id,
            cluster_id=cluster_id,
            region_id=region_id,
            issued_at=issued_at,
            latency=latency,
            error_code=error_code,
        )

    return _build


@pytest.fixture
def tiny_infra():
    from scrutable.infrastructure import InfrastructureConfig, InfrastructureModel

    config = InfrastructureConfig(
        regions=["r1", "r2"],
        clusters={"r1": ["r1c1", "r1c2"], "r2": ["r2c1", "r2c2"]},
        nodes={
            "r1c1": ["r1c1n1", "r1c1n2", "r1c1n3"],
            "r1c2": ["r1c2n1", "r1c2n2", "r1c2n3"],
            "r2c1": ["r2c1n1", "r2c1n2", "r2c1n3"],
            "r2c2": ["r2c2n1", "r2c2n2", "r2c2n3"],
        },
    )
    return InfrastructureModel(config)
