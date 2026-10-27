import numpy as np
import pytest

from wasitthewind.geo import bearing_deg, cumulative_m, headings_deg, trim_mask

# Invented coordinates, far from any real ride.
LAT0, LON0 = 10.0, 20.0


def test_bearing_cardinal_points():
    assert bearing_deg(LAT0, LON0, LAT0 + 0.01, LON0) == pytest.approx(0.0, abs=1e-6)
    assert bearing_deg(LAT0, LON0, LAT0, LON0 + 0.01) == pytest.approx(90.0, abs=0.01)
    assert bearing_deg(LAT0, LON0, LAT0 - 0.01, LON0) == pytest.approx(180.0, abs=1e-6)
    assert bearing_deg(LAT0, LON0, LAT0, LON0 - 0.01) == pytest.approx(270.0, abs=0.01)


def test_headings_follow_a_square_loop():
    n = 200
    side = np.linspace(0, 0.01, n, endpoint=False)
    lat = np.concatenate([LAT0 + side, np.full(n, LAT0 + 0.01), LAT0 + 0.01 - side, np.full(n, LAT0)])
    lon = np.concatenate([np.full(n, LON0), LON0 + side, np.full(n, LON0 + 0.01), LON0 + 0.01 - side])
    d = cumulative_m(lat, lon)
    h = headings_deg(lat, lon, d)
    assert h[n // 2] == pytest.approx(0.0, abs=0.5)
    assert h[n + n // 2] == pytest.approx(90.0, abs=0.5)
    assert h[2 * n + n // 2] == pytest.approx(180.0, abs=0.5)
    assert h[3 * n + n // 2] == pytest.approx(270.0, abs=0.5)


def test_trim_mask_cuts_both_ends():
    d = np.arange(0, 10001, 100.0)
    m = trim_mask(d, 2000)
    assert not m[:20].any() and m[20:81].all() and not m[81:].any()
