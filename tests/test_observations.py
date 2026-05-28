from scrutable.observations import ObservationBuffer


def test_window_returns_responses_in_range(build_response):
    buf = ObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives at 1.0
    buf.append(build_response(issued_at=1.0, latency=1.0))   # arrives at 2.0
    buf.append(build_response(issued_at=4.0, latency=1.0))   # arrives at 5.0
    result = buf.window(1.0, 3.0)
    assert len(result) == 2


def test_window_is_inclusive_on_both_ends(build_response):
    buf = ObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives at 1.0
    buf.append(build_response(issued_at=4.0, latency=1.0))   # arrives at 5.0
    result = buf.window(1.0, 5.0)
    assert len(result) == 2


def test_window_empty_when_no_responses_in_range(build_response):
    buf = ObservationBuffer()
    buf.append(build_response(issued_at=10.0, latency=1.0))  # arrives at 11.0
    result = buf.window(0.0, 5.0)
    assert result == []


def test_expire_removes_old_responses(build_response):
    buf = ObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))   # arrives at 1.0
    buf.append(build_response(issued_at=1.0, latency=1.0))   # arrives at 2.0
    buf.append(build_response(issued_at=9.0, latency=1.0))   # arrives at 10.0
    buf.expire(before=5.0)
    result = buf.window(0.0, 3.0)
    assert result == []
    result = buf.window(9.0, 11.0)
    assert len(result) == 1


def test_buffer_preserves_arrival_order(build_response):
    buf2 = ObservationBuffer()
    r_early = build_response(issued_at=3.0, latency=1.0)
    r_late = build_response(issued_at=1.0, latency=5.0)
    buf2.append(r_early)   # arrives 4.0
    buf2.append(r_late)    # arrives 6.0
    assert buf2.window(3.5, 5.0) == [r_early]
    assert buf2.window(5.5, 7.0) == [r_late]


def test_window_returns_copy_not_reference(build_response):
    buf = ObservationBuffer()
    buf.append(build_response(issued_at=0.0, latency=1.0))
    result = buf.window(0.0, 2.0)
    result.clear()
    assert len(buf.window(0.0, 2.0)) == 1
