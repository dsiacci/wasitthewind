import numpy as np
import pytest

from wasitthewind.physics import Bike, Rider, air_density, fit_drag_and_rolling, power_needed, speed_at_power

# A demonstration rider with round, invented numbers.
DEMO = Rider(mass_kg=70.0, bike=Bike(mass_kg=10.0, crr=0.005, cda_m2=0.35, efficiency=0.975))


def test_speed_and_power_are_inverse():
    for grade in (-0.02, 0.0, 0.05):
        for wind in (-3.0, 0.0, 4.0):
            v = speed_at_power(200.0, grade, DEMO, wind)
            assert power_needed(v, grade, DEMO, wind) == pytest.approx(200.0, rel=1e-4)


def test_headwind_slows_tailwind_helps():
    calm = speed_at_power(200.0, 0.0, DEMO, 0.0)
    assert speed_at_power(200.0, 0.0, DEMO, 3.0) < calm < speed_at_power(200.0, 0.0, DEMO, -3.0)
    # Into the wind costs more than the same wind gives back at the back.
    lost = calm - speed_at_power(200.0, 0.0, DEMO, 3.0)
    gained = speed_at_power(200.0, 0.0, DEMO, -3.0) - calm
    assert lost > 0 and gained > 0
    t_out_back = 1 / speed_at_power(200.0, 0.0, DEMO, 3.0) + 1 / speed_at_power(200.0, 0.0, DEMO, -3.0)
    assert t_out_back > 2 / calm


def test_wind_matters_little_on_a_steep_climb():
    flat = speed_at_power(200.0, 0.0, DEMO, 0.0) - speed_at_power(200.0, 0.0, DEMO, 3.0)
    climb = speed_at_power(200.0, 0.08, DEMO, 0.0) - speed_at_power(200.0, 0.08, DEMO, 3.0)
    assert climb < flat / 2


def test_arrays_and_downhill_cap():
    v = speed_at_power(np.array([0.0, 100.0, 300.0]), np.array([-0.15, 0.0, 0.0]), DEMO, 0.0, v_max_ms=20.0)
    assert v.shape == (3,) and v[0] == pytest.approx(20.0) and v[1] < v[2]
    assert speed_at_power(0.0, 0.03, DEMO) == pytest.approx(0.0, abs=1e-9)


def test_fit_recovers_drag_and_rolling():
    rng = np.random.default_rng(1)
    v = rng.uniform(4, 11, 400)
    g = rng.uniform(-0.01, 0.05, 400)
    w = rng.uniform(-3, 3, 400)
    rho = air_density(20.0, 100.0)
    p = power_needed(v, g, DEMO, w, rho) + rng.normal(0, 5, 400)
    start = Rider(mass_kg=70.0, bike=Bike(mass_kg=10.0, crr=0.01, cda_m2=0.5))
    crr, cda, rms = fit_drag_and_rolling(p, v, g, start, w, rho)
    assert crr == pytest.approx(0.005, abs=0.0008) and cda == pytest.approx(0.35, abs=0.01)
    assert rms < 7


def test_air_density():
    assert air_density(15.0, 0.0) == pytest.approx(1.225, abs=0.002)
    assert air_density(30.0, 0.0) < air_density(15.0, 0.0)
    assert air_density(15.0, 1000.0) < air_density(15.0, 0.0)


def test_coasting_reaches_terminal_speed():
    # 80 kg at -8 % with no power: gravity balances drag around 17 m/s.
    v = speed_at_power(0.0, -0.08, DEMO, 0.0, rho=1.225)
    pull = 80.0 * 9.80665 * (np.sin(np.arctan(-0.08)) * -1 - 0.005 * np.cos(np.arctan(0.08)))
    assert v == pytest.approx(np.sqrt(pull / (0.5 * 1.225 * 0.35)), rel=1e-3)
