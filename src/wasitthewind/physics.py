"""Steady-state cycling physics with wind: the cross-check for the learned model.

    P = (m·g·v·(sin θ + Crr·cos θ) + ½·ρ·CdA·(v + w)·|v + w|·v) / η

θ is the road angle (tan θ = grade), m the rider plus the bike, Crr the
rolling resistance, CdA the drag area, ρ the air density, η the drivetrain
efficiency and w the headwind the rider feels (negative at the back). The
rider's mass is a parameter: it is never stored or printed, and neither are
the fitted drag area and rolling resistance, which would give it back.

Started from z2analyzer (same author, Apache 2.0): https://github.com/dsiacci/z2analyzer
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

G = 9.80665  # m/s²


@dataclass(frozen=True)
class Bike:
    mass_kg: float = 11.5  # bike, bottles, tools, computer
    crr: float = 0.005
    cda_m2: float = 0.40
    efficiency: float = 0.975


@dataclass(frozen=True)
class Rider:
    """The rider's mass is a parameter: wasitthewind never stores or prints it."""

    mass_kg: float
    bike: Bike = field(default_factory=Bike)

    @property
    def system_mass_kg(self) -> float:
        return self.mass_kg + self.bike.mass_kg

    def with_fit(self, crr: float, cda_m2: float) -> "Rider":
        return replace(self, bike=replace(self.bike, crr=crr, cda_m2=cda_m2))


def air_density(temp_c=15.0, altitude_m=0.0):
    """Air density (kg/m³) from the temperature and the altitude (standard atmosphere pressure)."""
    t = np.asarray(temp_c, dtype=float)
    z = np.asarray(altitude_m, dtype=float)
    pressure = 101325.0 * (1.0 - 2.25577e-5 * z) ** 5.25588
    return pressure / (287.05 * (t + 273.15))


def power_needed(speed_ms, grade, rider: Rider, headwind_ms=0.0, rho=1.225):
    """Signed pedal power (W) to hold `speed_ms` on `grade` against `headwind_ms`.

    Negative means the slope or a tailwind would push the bike faster with no
    pedalling at all.
    """
    v = np.asarray(speed_ms, dtype=float)
    theta = np.arctan(np.asarray(grade, dtype=float))
    air = v + np.asarray(headwind_ms, dtype=float)
    b = rider.bike
    wheel = (rider.system_mass_kg * G * v * (np.sin(theta) + b.crr * np.cos(theta))
             + 0.5 * rho * b.cda_m2 * air * np.abs(air) * v)
    return wheel / b.efficiency


def speed_at_power(power_w, grade, rider: Rider, headwind_ms=0.0, rho=1.225, v_max_ms=22.0):
    """Speed (m/s) at which `power_w` balances the road and the wind.

    Solved on a grid then refined by bisection, which keeps the fastest
    balance: with a strong tailwind at walking pace the power curve can dip.
    Downhill with no power the result is capped at `v_max_ms` (descending
    speed is the rider's choice, and brakes don't appear in the equation).
    """
    p, g, w, r = np.broadcast_arrays(*(np.atleast_1d(np.asarray(x, dtype=float))
                                       for x in (power_w, grade, headwind_ms, rho)))
    grid = np.linspace(0.0, v_max_ms, 221)
    need = power_needed(grid[:, None], g[None, :], rider, w[None, :], r[None, :])
    below = need <= p[None, :]
    # last grid speed where the power still suffices
    idx = grid.size - 1 - np.argmax(below[::-1], axis=0)
    lo = grid[idx]
    hi = np.minimum(lo + grid[1], v_max_ms)
    capped = idx == grid.size - 1
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        ok = power_needed(mid, g, rider, w, r) <= p
        lo = np.where(ok, mid, lo)
        hi = np.where(ok, hi, mid)
    out = np.where(capped, v_max_ms, 0.5 * (lo + hi))
    out = np.where(below.any(axis=0), out, 0.0)
    scalar = all(np.ndim(x) == 0 for x in (power_w, grade, headwind_ms, rho))
    return float(out[0]) if scalar else out


def fit_drag_and_rolling(power_w, speed_ms, grade, rider: Rider, headwind_ms=0.0, rho=1.225, accel_w=0.0):
    """Least-squares Crr and CdA from steady stretches: P·η − m·a·v − m·g·v·sin θ = Crr·(m·g·v·cos θ) + CdA·(½ρ(v+w)|v+w|v).

    Returns (crr, cda_m2, rms_residual_w). The values stay in memory: printed
    next to the speed, they would give the mass back.
    """
    p = np.asarray(power_w, dtype=float)
    v = np.asarray(speed_ms, dtype=float)
    theta = np.arctan(np.asarray(grade, dtype=float))
    air = v + np.asarray(headwind_ms, dtype=float)
    m = rider.system_mass_kg
    y = p * rider.bike.efficiency - np.asarray(accel_w, dtype=float) - m * G * v * np.sin(theta)
    a = np.column_stack([m * G * v * np.cos(theta), 0.5 * np.asarray(rho, dtype=float) * air * np.abs(air) * v])
    coef, *_ = np.linalg.lstsq(a, y, rcond=None)
    resid = y - a @ coef
    return float(coef[0]), float(coef[1]), float(np.sqrt(np.mean(resid**2)) / rider.bike.efficiency)
