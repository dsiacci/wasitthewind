"""One ride, from the FIT file to the ghost and the verdict.

    prepare   FIT → one-second series with the wind of every model (no positions)
    ghost     the series and the rider's other rides → the ghost, its gap and its range

The range comes from what we don't know: which weather model is right
(AROME or IFS), which speed model is right (TabPFN, or the physics when the
rider's mass is given), and, for the physics, how much of the 10 m wind
reaches a rider 1.2 m above the road: 0.54 of it over farmland with hedges
(roughness 0.1 m), 0.29 over maquis and villages (0.5 m). The headline is
AROME with TabPFN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import ghost as ghostmod
from . import models
from . import wind
from .fitfile import Ride, read_fit
from .ride import RideSeries, chunks, positions, series

HEADLINE_MODEL = wind.DEFAULT_MODEL
ROUGHNESS_M = (0.1, 0.5)


def fields_for(ride: Ride, cache_dir, wind_models=tuple(wind.MODELS), fetch=None) -> list[wind.WindField]:
    lats, lons = wind.lattice_for_track(ride.lat, ride.lon)
    days = wind.days_covering(ride.start, ride.time_at(ride.t[-1]))
    return [wind.load_field(lats, lons, days, model=m, cache_dir=cache_dir, fetch=fetch) for m in wind_models]


def prepare(path: str | Path, cache_dir, wind_models=tuple(wind.MODELS), fetch=None):
    """(series, (lat, lon)) of an outdoor ride with power; raises ValueError otherwise."""
    ride = read_fit(path)
    if ride.is_virtual:
        raise ValueError(f"{Path(path).name}: an indoor ride has no wind")
    if not ride.has_power:
        raise ValueError(f"{Path(path).name}: no power in the file (the ghost needs the legs)")
    rs = series(ride, fields_for(ride, cache_dir, wind_models, fetch))
    return rs, positions(ride)


@dataclass
class Verdict:
    ride: str
    start_epoch: float
    headline: ghostmod.Ghost
    variants: dict[str, float] = field(default_factory=dict)  # name -> gap (s)
    worst: list[ghostmod.Stretch] = field(default_factory=list)
    best: list[ghostmod.Stretch] = field(default_factory=list)
    mean_wind10: float = 0.0

    @property
    def gap_s(self) -> float:
        return self.headline.gap_s

    @property
    def range_s(self) -> tuple[float, float]:
        vals = [self.gap_s, *self.variants.values()]
        return min(vals), max(vals)


def tabpfn_speeds(chunk: dict, context: list[dict], wind_model: str, make=None, factor: float = 1.0):
    """Predicted speeds of the ghost rows, with the wind and with none, from the other rides as context.

    With none: the mean of the speeds with the headwind as it was and turned
    around (see `models`), so the even part of the model's answer to the wind,
    which also tells windy days from calm ones, cancels out.
    """
    make = make or (lambda X, y: models.TabPFNModel(X, y))
    table = models.speed_table(context, wind_model, factor)
    m = make(table["X"], table["y"])
    rows = ghostmod.ghost_rows(chunk)
    sub = {k: (v[rows] if isinstance(v, np.ndarray) and v.shape[:1] == rows.shape else v) for k, v in chunk.items()}
    xw = models.features(sub, wind_model, factor)
    xt = models.features(sub, wind_model, factor, turned=True)
    both = models.median(m, np.vstack([xw, xt]))
    vw, vt = both[: len(xw)], both[len(xw):]
    return vw, 0.5 * (vw + vt)


def fitted_rider(rider, context: list[dict], wind_model: str = HEADLINE_MODEL, factor: float | None = None):
    """The rider with drag and rolling resistance fitted on the steady pieces of the other rides.

    Steady: full 30-second pieces, pedalling, above 3 m/s, grade between −3 and
    8 %, heading within 30°. The fit stays in memory (printed next to a speed,
    it would give the mass back). Too few pieces, or values out of reason: the
    rider as given.
    """
    from .physics import air_density, fit_drag_and_rolling

    if not context:
        return rider
    factor = wind.rider_height_factor() if factor is None else factor
    c = {k: np.concatenate([x[k] for x in context]) for k in context[0]}
    sel = (c["full"] & (c["power"] > 50) & (c["speed"] > 3) & (c["grade"] > -0.03) & (c["grade"] < 0.08)
           & (c["heading_change"] < 30))
    if sel.sum() < 50:
        return rider
    crr, cda, _ = fit_drag_and_rolling(c["power"][sel], c["speed"][sel], c["grade"][sel], rider,
                                       factor * c[f"head10__{wind_model}"][sel],
                                       air_density(c["temp"][sel], c["elev"][sel]),
                                       rider.system_mass_kg * c["dv2"][sel] / 60.0)
    if not (0.001 < crr < 0.02 and 0.15 < cda < 0.8):
        return rider
    return rider.with_fit(crr, cda)


def physics_speeds(chunk: dict, rider, wind_model: str, factor: float, rho=None):
    """The same two predictions from the physics (a fitted rider: see `physics.fit_drag_and_rolling`)."""
    from .physics import air_density, speed_at_power

    rows = ghostmod.ghost_rows(chunk)
    p = chunk["power"][rows]
    g = chunk["grade"][rows]
    w = factor * chunk[f"head10__{wind_model}"][rows]
    r = air_density(chunk["temp"][rows], chunk["elev"][rows]) if rho is None else rho
    return speed_at_power(p, g, rider, w, r), speed_at_power(p, g, rider, 0.0, r)


def judge(rs: RideSeries, context: list[RideSeries], make=None, rider=None, height_factors=None,
          extra_variants: bool = True) -> Verdict:
    """The ghost of `rs` learned from `context` (the rider's other rides), with its range."""
    if not context:
        raise ValueError("the ghost needs at least one other ride to learn the rider from")
    ch = chunks(rs)
    # by date: TabPFN's answer moves by a few seconds with the order of its rows,
    # and the same rides should always give the same ghost
    ctx = [chunks(c) for c in sorted(context, key=lambda c: c.start_epoch) if c.name != rs.name]
    vw, vc = tabpfn_speeds(ch, ctx, HEADLINE_MODEL, make)
    head = ghostmod.replay(ch, vw, vc, HEADLINE_MODEL)
    v = Verdict(ride=rs.name, start_epoch=rs.start_epoch, headline=head,
                worst=ghostmod.stretches(head, 3, worst=True), best=ghostmod.stretches(head, 2, worst=False),
                mean_wind10=float(np.average(ch[f"speed10__{HEADLINE_MODEL}"], weights=head.rider_s)))
    if extra_variants:
        for m in rs.models:
            if m != HEADLINE_MODEL:
                a, b = tabpfn_speeds(ch, ctx, m, make)
                v.variants[f"TabPFN, {m}"] = ghostmod.replay(ch, a, b, m).gap_s
        if rider is not None:
            rider = fitted_rider(rider, ctx)
            factors = height_factors or [wind.rider_height_factor(z0_m=z) for z in ROUGHNESS_M]
            for m in rs.models:
                for k in factors:
                    a, b = physics_speeds(ch, rider, m, k)
                    v.variants[f"physics ×{k:.2f}, {m}"] = ghostmod.replay(ch, a, b, m).gap_s
    return v
