from datetime import datetime, timezone

import numpy as np
import pytest

from fitwriter import write_fit
from wasitthewind import analysis, models, wind
from wasitthewind.physics import Bike, Rider, speed_at_power

# Invented place, days and rider (round numbers).
LAT0, LON0 = 10.0, 20.0
DEMO = Rider(mass_kg=70.0, bike=Bike(mass_kg=10.0, crr=0.005, cda_m2=0.35))


def north_wind_fetch(speed_ms):
    def fetch(model, day, nodes):
        t0 = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp()
        times = [t0 + 900 * k for k in range(96)]
        return times, {f"{a:.4f},{b:.4f}": ([speed_ms] * 96, [0.0] * 96) for a, b in nodes}
    return fetch


def out_and_back(path, day, wind_ms, power=180.0, leg_m=4000.0):
    """4 km due north then 4 km back south on the flat, speeds from the physics, the rider feeling half the 10 m wind."""
    rows, lat, dist = [], LAT0, 0.0
    i = 0
    while dist < 2 * leg_m:
        north = dist < leg_m
        head = (0.5 * wind_ms) if north else -(0.5 * wind_ms)
        v = speed_at_power(power + 15 * np.sin(i / 40), 0.0, DEMO, head)
        lat += (1 if north else -1) * v / 111_195.0
        dist += v
        rows.append({"t": i, "lat": lat, "lon": LON0, "hr": 120, "cadence": 85, "dist": dist,
                     "power": power + 15 * np.sin(i / 40), "temp": 18, "speed": v, "alt": 20.0})
        i += 1
    write_fit(path, datetime(2026, 1, day, 9, 0, tzinfo=timezone.utc), rows)


def test_judge_end_to_end(tmp_path):
    for day, w in ((10, 0.0), (11, 2.0), (12, 6.0), (13, 4.0)):
        out_and_back(tmp_path / f"r{day}.fit", day, w)
    series = []
    for day, w in ((10, 0.0), (11, 2.0), (12, 6.0), (13, 4.0)):
        rs, (lat, lon) = analysis.prepare(tmp_path / f"r{day}.fit", tmp_path / "cache",
                                          wind_models=[wind.DEFAULT_MODEL], fetch=north_wind_fetch(w))
        assert lat.size == rs.epoch.size
        series.append(rs)
    v = analysis.judge(series[2], series, make=models.LinearModel, rider=DEMO, height_factors=[0.5])
    # An out-and-back into a wind costs time; the physics knows it for sure.
    assert v.variants[f"physics ×0.50, {wind.DEFAULT_MODEL}"] > 0
    lo, hi = v.range_s
    assert lo <= v.gap_s <= hi
    assert v.headline.rider_total_s > 700
    assert v.mean_wind10 == pytest.approx(6.0, abs=0.01)


class _Speed:
    """A fake speed model: 8 m/s, plus `odd` per m/s of tailwind and `even` per m/s of wind either way."""

    def __init__(self, odd, even):
        self.odd, self.even = odd, even

    def __call__(self, X, y):
        return self

    def quantiles(self, X, qs=models.QUANTILES):
        h = np.asarray(X)[:, models.SPEED_FEATURES.index("head")]
        v = 8.0 - self.odd * h + self.even * np.abs(h)
        return np.tile(v[:, None], (1, len(qs)))


def test_ghost_ignores_what_the_wind_says_about_the_day(tmp_path):
    # A model that only learned "windy days are fast days" must not move the ghost.
    for day, w in ((10, 0.0), (12, 6.0)):
        out_and_back(tmp_path / f"r{day}.fit", day, w)
    series = [analysis.prepare(tmp_path / f"r{d}.fit", tmp_path / "cache", wind_models=[wind.DEFAULT_MODEL],
                               fetch=north_wind_fetch(w))[0] for d, w in ((10, 0.0), (12, 6.0))]
    v = analysis.judge(series[1], series, make=_Speed(odd=0.0, even=0.3), extra_variants=False)
    assert v.gap_s == pytest.approx(0.0, abs=1.0)
    # One that learned the headwind slows the rider does: into the wind on the way out, the ghost wins.
    v = analysis.judge(series[1], series, make=_Speed(odd=0.3, even=0.0), extra_variants=False)
    assert v.gap_s > 10


def test_the_ghost_does_not_depend_on_the_order_of_the_other_rides(tmp_path):
    for day, w in ((10, 0.0), (11, 3.0), (12, 6.0)):
        out_and_back(tmp_path / f"r{day}.fit", day, w)
    series = [analysis.prepare(tmp_path / f"r{d}.fit", tmp_path / "cache", wind_models=[wind.DEFAULT_MODEL],
                               fetch=north_wind_fetch(w))[0] for d, w in ((10, 0.0), (11, 3.0), (12, 6.0))]
    seen = []

    def make(X, y):
        seen.append(X.copy())
        return models.LinearModel(X, y)

    analysis.judge(series[2], series[:2], make=make, extra_variants=False)
    analysis.judge(series[2], series[1::-1], make=make, extra_variants=False)
    assert np.array_equal(seen[0], seen[1])
