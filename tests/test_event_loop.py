from scrutable.event_loop import EventLoop


def test_events_fire_in_timestamp_order():
    loop = EventLoop()
    fired = []
    loop.schedule(3.0, lambda: fired.append(3))
    loop.schedule(1.0, lambda: fired.append(1))
    loop.schedule(2.0, lambda: fired.append(2))
    loop.run(10.0)
    assert fired == [1, 2, 3]


def test_priority_breaks_timestamp_tie():
    loop = EventLoop()
    fired = []
    loop.schedule(1.0, lambda: fired.append("second"), priority=10)
    loop.schedule(1.0, lambda: fired.append("first"), priority=0)
    loop.run(10.0)
    assert fired == ["first", "second"]


def test_run_stops_at_until():
    loop = EventLoop()
    fired = []
    loop.schedule(1.0, lambda: fired.append(1))
    loop.schedule(5.0, lambda: fired.append(5))
    loop.run(3.0)
    assert fired == [1]
    assert 5 not in fired


def test_now_reflects_current_event_time():
    loop = EventLoop()
    times = []
    loop.schedule(2.5, lambda: times.append(loop.now))
    loop.run(10.0)
    assert times == [2.5]


def test_handler_scheduled_during_run_fires_if_in_window():
    loop = EventLoop()
    fired = []

    def first():
        fired.append("first")
        loop.schedule(2.0, lambda: fired.append("second"))

    loop.schedule(1.0, first)
    loop.run(10.0)
    assert fired == ["first", "second"]


def test_empty_loop_runs_without_error():
    loop = EventLoop()
    loop.run(100.0)
    assert loop.now == 0.0


def test_now_starts_at_zero():
    loop = EventLoop()
    assert loop.now == 0.0
