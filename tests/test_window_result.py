import numpy as np
import pytest
from scrutable.window_result import WindowResult


def _exact(latencies, error_rate=0.0, t_start=0.0, t_end=1.0):
    return WindowResult(
        t_start=t_start, t_end=t_end,
        count=len(latencies), error_rate=error_rate,
        _latencies=np.array(latencies, dtype=np.float64),
    )


def _precomputed(d, count=100):
    return WindowResult(t_start=0.0, t_end=1.0, count=count, error_rate=0.0,
                        _precomputed=d)


def test_percentile_exact_delegates_to_numpy():
    vals = [0.1, 0.2, 0.3, 0.4, 0.5]
    assert _exact(vals).percentile(50) == pytest.approx(np.percentile(vals, 50))


def test_percentile_precomputed_lookup():
    assert _precomputed({99.9: 0.42}).percentile(99.9) == pytest.approx(0.42)


def test_percentile_keyerror_for_undeclared():
    with pytest.raises(KeyError):
        _precomputed({99.0: 0.3}).percentile(99.9)


def test_len():
    assert len(_exact([0.1, 0.2, 0.3])) == 3


def test_bool_true_when_nonempty():
    assert bool(_exact([0.1]))


def test_bool_false_when_empty():
    assert not bool(WindowResult(t_start=0.0, t_end=1.0, count=0, error_rate=0.0))


def test_error_rate_stored():
    assert _exact([0.1, 0.2], error_rate=0.25).error_rate == pytest.approx(0.25)
