from __future__ import annotations
import numpy as np
import pytest
from scrutable.models import Response
from scrutable.histogram_buffer import HistogramBuffer, merge_histogram_buffers
from scrutable.observations import NumpyObservationBuffer

PERCENTILES = (50.0, 90.0, 99.0, 99.9)


def _r(issued_at: float, latency: float, error_code: int = 0) -> Response:
    return Response(
        request_id="x", node_id="n",
        workload_id="w", cluster_id="c", region_id="r",
        issued_at=issued_at,
        latency=latency, error_code=error_code,
    )


def test_window_count_matches_appended():
    hbuf = HistogramBuffer(total_duration=10.0, percentiles=PERCENTILES)
    for i in range(100):
        hbuf.append(_r(issued_at=float(i) * 0.05, latency=0.1))
    assert len(hbuf.window(0.0, 10.0)) == 100


def test_window_empty_outside_range():
    hbuf = HistogramBuffer(total_duration=10.0, percentiles=PERCENTILES)
    for i in range(5):
        hbuf.append(_r(issued_at=float(i), latency=0.1))
    # arrivals at 0.1–4.1, all in cell 0–4; window 6–7 should be empty
    assert not hbuf.window(6.0, 7.0)


def test_error_rate():
    hbuf = HistogramBuffer(total_duration=10.0, percentiles=PERCENTILES)
    hbuf.append(_r(issued_at=0.0, latency=0.1, error_code=0))
    hbuf.append(_r(issued_at=0.1, latency=0.1, error_code=1))
    hbuf.append(_r(issued_at=0.2, latency=0.1, error_code=1))
    w = hbuf.window(0.0, 5.0)
    assert w.error_rate == pytest.approx(2 / 3)


def test_expire_removes_old_cells():
    hbuf = HistogramBuffer(total_duration=10.0, percentiles=PERCENTILES)
    for i in range(5):
        hbuf.append(_r(issued_at=float(i), latency=0.1))
    hbuf.expire(before=3.0)
    assert not hbuf.window(0.0, 2.0)
    # i=4: issued_at=4.0, arrival=4.1 → cell 4; window(4.0, 5.0) covers cell 4
    assert len(hbuf.window(4.0, 5.0)) == 1


def test_percentile_close_to_numpy():
    rng = np.random.default_rng(42)
    n = 10_000
    latencies = rng.lognormal(-2, 0.4, n)
    responses = [_r(issued_at=float(i) * 0.001, latency=float(lat))
                 for i, lat in enumerate(latencies)]
    total_duration = float(n) * 0.001 + 1.0
    hbuf = HistogramBuffer(total_duration=total_duration, percentiles=PERCENTILES)
    for r in responses:
        hbuf.append(r)
    w = hbuf.window(0.0, total_duration)
    for p in PERCENTILES:
        expected = float(np.percentile(latencies, p))
        got = w.percentile(p)
        assert abs(got - expected) / expected < 0.05, (
            f"p{p}: expected≈{expected:.4f}, got={got:.4f}"
        )


def test_from_numpy_buffer_matches_direct():
    rng = np.random.default_rng(7)
    n = 5_000
    latencies = rng.lognormal(-2, 0.4, n)
    responses = [_r(issued_at=float(i) * 0.001, latency=float(lat))
                 for i, lat in enumerate(latencies)]
    total_duration = float(n) * 0.001 + 1.0
    hbuf_direct = HistogramBuffer(total_duration=total_duration, percentiles=PERCENTILES)
    for r in responses:
        hbuf_direct.append(r)
    nbuf = NumpyObservationBuffer.from_responses(responses)
    hbuf_from = HistogramBuffer.from_numpy_buffer(
        nbuf, total_duration=total_duration, percentiles=PERCENTILES)
    w_direct = hbuf_direct.window(0.0, total_duration)
    w_from   = hbuf_from.window(0.0, total_duration)
    assert len(w_direct) == len(w_from)
    for p in PERCENTILES:
        assert w_direct.percentile(p) == pytest.approx(w_from.percentile(p), rel=1e-6)


def test_merge_histogram_buffers():
    total_duration = 10.0
    hbuf1 = HistogramBuffer(total_duration=total_duration, percentiles=PERCENTILES)
    hbuf2 = HistogramBuffer(total_duration=total_duration, percentiles=PERCENTILES)
    responses = [_r(issued_at=float(i) * 0.1, latency=0.1) for i in range(100)]
    for i, r in enumerate(responses):
        (hbuf1 if i % 2 == 0 else hbuf2).append(r)
    merged = merge_histogram_buffers([hbuf1, hbuf2])
    assert len(merged.window(0.0, total_duration)) == 100


def test_bool_false_when_empty():
    hbuf = HistogramBuffer(total_duration=5.0, percentiles=PERCENTILES)
    assert not hbuf.window(0.0, 5.0)
