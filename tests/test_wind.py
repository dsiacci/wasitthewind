from datetime import date, datetime, timezone

import numpy as np
import pytest

from wasitthewind import wind

# Invented lattice, far from any real ride.
LATS = np.array([10.0, 10.025, 10.05])
LONS = np.array([20.0, 20.025])
DAY = date(2026, 1, 15)
T0 = datetime(2026, 1, 15, tzinfo=timezone.utc).timestamp()


def test_lattice_snaps_to_whole_blocks():
    lats, lons = wind.lattice(10.02, 10.08, 20.11, 20.13, margin_deg=0.0)
    assert lats[0] == pytest.approx(10.0) and lats[-1] == pytest.approx(10.1)
    assert lons[0] == pytest.approx(20.1) and lons[-1] == pytest.approx(20.2)
    assert np.allclose(np.diff(lats), 0.025) and lats.size == 5
    # Two boxes in the same block ask for the same points.
    a = wind.lattice(10.03, 10.04, 20.12, 20.15, margin_deg=0.0)
    assert np.array_equal(a[0], lats) and np.array_equal(a[1], lons)


def test_uv_round_trip_and_conventions():
    u, v = wind.to_uv(5.0, 270.0)  # from the west: blows towards the east
    assert u == pytest.approx(5.0) and v == pytest.approx(0.0, abs=1e-12)
    s, d = wind.from_uv(u, v)
    assert s == pytest.approx(5.0) and d == pytest.approx(270.0)


def test_head_and_cross_components():
    u, v = wind.to_uv(4.0, 0.0)  # from the north
    head, cross = wind.components(u, v, 0.0)  # riding north, into it
    assert head == pytest.approx(4.0) and cross == pytest.approx(0.0, abs=1e-12)
    head, cross = wind.components(u, v, 180.0)  # riding south, wind at the back
    assert head == pytest.approx(-4.0)
    head, cross = wind.components(u, v, 90.0)  # riding east, wind from the left
    assert head == pytest.approx(0.0, abs=1e-12) and cross == pytest.approx(4.0)


def test_rider_height_factor():
    assert wind.rider_height_factor(10.0) == pytest.approx(1.0)
    f = wind.rider_height_factor(1.2, 0.1)
    assert 0.5 < f < 0.6
    assert wind.rider_height_factor(1.2, 0.03) > f > wind.rider_height_factor(1.2, 0.3)


def fake_fetch(calls):
    """A wind from the west growing with longitude and with time: u = 2 + 40*(lon-20) + t/3600."""
    def fetch(model, day, nodes):
        calls.append(len(nodes))
        times = [T0 + 900 * k for k in range(96)]
        values = {}
        for a, b in nodes:
            u = np.array([2 + 40 * (b - 20.0) + (t - T0) / 3600 for t in times])
            values[f"{a:.4f},{b:.4f}"] = (list(u), [270.0] * len(times))
        return times, values
    return fetch


def test_field_is_interpolated_and_cached(tmp_path):
    calls = []
    f = wind.load_field(LATS, LONS, [DAY], cache_dir=tmp_path, fetch=fake_fetch(calls))
    assert calls == [6] and f.u.shape == (96, 3, 2)
    u, v = f.at(T0 + 5400, 10.01, 20.0125)  # 1.5 h, halfway between the two longitudes
    assert u[0] == pytest.approx(2 + 0.5 + 1.5) and v[0] == pytest.approx(0.0, abs=1e-9)
    # Second load: everything from the cache.
    g = wind.load_field(LATS, LONS, [DAY], cache_dir=tmp_path, fetch=fake_fetch(calls))
    assert calls == [6] and np.allclose(g.u, f.u)
    # A wider lattice only fetches the new points.
    wind.load_field(LATS, np.array([20.0, 20.025, 20.05]), [DAY], cache_dir=tmp_path, fetch=fake_fetch(calls))
    assert calls == [6, 3]


def test_field_refuses_outside_points(tmp_path):
    f = wind.load_field(LATS, LONS, [DAY], cache_dir=tmp_path, fetch=fake_fetch([]))
    with pytest.raises(ValueError):
        f.at(T0 + 60, 10.2, 20.01)
    with pytest.raises(ValueError):
        f.at(T0 - 60, 10.01, 20.01)


def test_days_covering_crosses_midnight():
    s = datetime(2026, 1, 15, 22, 30, tzinfo=timezone.utc)
    e = datetime(2026, 1, 16, 0, 10, tzinfo=timezone.utc)
    assert wind.days_covering(s, e) == [date(2026, 1, 15), date(2026, 1, 16)]
