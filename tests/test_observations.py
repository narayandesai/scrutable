import numpy as np
import pytest
from scrutable.observations import NumpyObservationBuffer, merge_observation_buffers
from scrutable.window_result import WindowResult


def test_window_returns_responses_in_range(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives 1.0
    buf.append(build_response(issued_at=1.0, latency=1.0))   # arrives 2.0
    buf.append(build_response(issued_at=4.0, latency=1.0))   # arrives 5.0
    assert len(buf.window(1.0, 3.0)) == 2


def test_window_is_inclusive_on_both_ends(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives 1.0
    buf.append(build_response(issued_at=4.0, latency=1.0))   # arrives 5.0
    assert len(buf.window(1.0, 5.0)) == 2


def test_window_empty_when_no_responses_in_range(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=10.0, latency=1.0))
    assert not buf.window(0.0, 5.0)


def test_expire_removes_old_responses(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives 1.0
    buf.append(build_response(issued_at=1.0, latency=1.0))   # arrives 2.0
    buf.append(build_response(issued_at=9.0, latency=1.0))   # arrives 10.0
    buf.expire(before=5.0)
    assert not buf.window(0.0, 3.0)
    assert len(buf.window(9.0, 11.0)) == 1


def test_buffer_preserves_arrival_order(build_response):
    buf = NumpyObservationBuffer()
    r_early = build_response(issued_at=3.0, latency=1.0)   # arrives 4.0
    r_late  = build_response(issued_at=1.0, latency=5.0)   # arrives 6.0
    buf.append(r_early)
    buf.append(r_late)
    w1 = buf.window(3.5, 5.0)
    w2 = buf.window(5.5, 7.0)
    assert len(w1) == 1
    assert len(w2) == 1
    assert w1.percentile(50) == pytest.approx(r_early.latency)
    assert w2.percentile(50) == pytest.approx(r_late.latency)


def test_window_returns_window_result(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=0.5))
    assert isinstance(buf.window(0.0, 2.0), WindowResult)


def test_append_after_window_does_not_mutate_earlier_result(build_response):
    buf = NumpyObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))
    result = buf.window(0.0, 2.0)
    assert len(result) == 1
    buf.append(build_response(issued_at=0.5, latency=1.0))
    assert len(result) == 1  # snapshot; not affected by subsequent appends


def test_window_result_percentile_matches_numpy(build_response):
    rng = np.random.default_rng(42)
    buf = NumpyObservationBuffer()
    latencies = rng.lognormal(-2, 0.3, 1000)
    for i, lat in enumerate(latencies):
        buf.append(build_response(issued_at=float(i) * 0.001, latency=float(lat)))
    result = buf.window(0.0, 2.0)
    assert result.percentile(99.9) == pytest.approx(np.percentile(latencies, 99.9))


def test_window_result_error_rate(build_response):
    buf = NumpyObservationBuffer()
    for i in range(10):
        buf.append(build_response(issued_at=float(i) * 0.1, latency=0.1,
                                  error_code=1 if i < 3 else 0))
    assert buf.window(0.0, 2.0).error_rate == pytest.approx(0.3)


def test_from_responses(build_response):
    responses = [build_response(issued_at=float(i), latency=0.1) for i in range(5)]
    buf = NumpyObservationBuffer.from_responses(responses)
    assert len(buf.window(0.0, 10.0)) == 5


def test_merge_observation_buffers(build_response):
    buf1 = NumpyObservationBuffer.from_responses([
        build_response(issued_at=0.0, latency=0.5),   # arrives 0.5
        build_response(issued_at=2.0, latency=0.5),   # arrives 2.5
    ])
    buf2 = NumpyObservationBuffer.from_responses([
        build_response(issued_at=1.0, latency=0.5),   # arrives 1.5
        build_response(issued_at=3.0, latency=0.5),   # arrives 3.5
    ])
    merged = merge_observation_buffers([buf1, buf2])
    assert len(merged.window(0.0, 4.0)) == 4
    assert len(merged.window(1.0, 2.0)) == 1   # only arrival at 1.5
