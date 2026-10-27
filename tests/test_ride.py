from datetime import date, datetime, timezone

import numpy as np
import pytest

from fitwriter import write_fit
from wasitthewind import wind
from wasitthewind.fitfile import read_fit
from wasitthewind.ride import RideSeries, chunks, series, smoothed_grade

# Invented place and day.
LAT0, LON0 = 10.0, 20.0
START = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)


def test_smoothed_grade_of_a_ramp():
    d = np.arange(0, 2000, 5.0)
    z = 100 + np.where(d < 1000, 0.0, 0.06 * (d - 1000))
    g, zs = smoothed_grade(d, z + np.random.default_rng(0).normal(0, 0.3, d.size))
    assert abs(g[(d > 200) & (d < 800)]).max() < 0.01
    assert g[(d > 1200) & (d < 1800)].mean() == pytest.approx(0.06, abs=0.003)


def northbound_ride(path, n=600):
    """Ten minutes riding due north at 5 m/s on the flat."""
    step = 5.0 / 111_195.0
    samples = [{"t": i, "lat": LAT0 + i * step, "lon": LON0, "hr": 120, "cadence": 85, "dist": i * 5.0,
                "power": 150, "temp": 18, "speed": 5.0, "alt": 50.0} for i in range(n)]
    write_fit(path, START, samples)
    return read_fit(path)


def west_wind_field():
    """A steady 6 m/s wind from the north over the invented place."""
    lats, lons = wind.lattice(LAT0, LAT0 + 0.03, LON0, LON0 + 0.01)
    t0 = datetime(2026, 1, 15, tzinfo=timezone.utc).timestamp()

    def fetch(model, day, nodes):
        times = [t0 + 900 * k for k in range(96)]
        return times, {f"{a:.4f},{b:.4f}": ([6.0] * 96, [0.0] * 96) for a, b in nodes}

    return wind.load_field(lats, lons, [date(2026, 1, 15)], fetch=fetch)


def test_series_carries_the_wind(tmp_path):
    ride = northbound_ride(tmp_path / "r.fit")
    rs = series(ride, [west_wind_field()])
    model = wind.DEFAULT_MODEL
    assert rs.models == [model]
    mid = slice(30, -30)
    assert np.allclose(rs.heading[mid], 0.0, atol=0.5)
    assert np.allclose(rs.head10[model][mid], 6.0, atol=0.05)  # riding into a north wind
    assert np.allclose(rs.cross10[model][mid], 0.0, atol=0.1)
    assert abs(rs.grade).max() < 0.005
    assert rs.dist[-1] == pytest.approx(599 * 5.0, rel=0.01)


def test_chunks_and_save_without_positions(tmp_path):
    ride = northbound_ride(tmp_path / "r.fit")
    rs = series(ride, [west_wind_field()])
    c = chunks(rs)
    assert c["full"].sum() == 20 and c["power"][3] == pytest.approx(150.0)
    assert c[f"head10__{wind.DEFAULT_MODEL}"][5] == pytest.approx(6.0, abs=0.05)
    p = tmp_path / "s.npz"
    rs.save(p)
    z = np.load(p)
    assert not any(k in z.files for k in ("lat", "lon"))
    back = RideSeries.load(p)
    assert back.models == rs.models and np.allclose(back.head10[wind.DEFAULT_MODEL], rs.head10[wind.DEFAULT_MODEL])
