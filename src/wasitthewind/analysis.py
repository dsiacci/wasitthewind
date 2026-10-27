"""One ride, from the FIT file to the ghost and the verdict.

    prepare   FIT → one-second series with the wind of every model (no positions)
    ghost     the series and the rider's other rides → the ghost, its gap and its range

The range comes from what we don't know: which weather model is right
(AROME or IFS) and which speed model is right (TabPFN, or the physics when
the rider's mass is given). The headline is AROME with TabPFN.
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
    """Predicted speeds of the ghost rows, with the wind and with none, from the other rides as context."""
    make = make or (lambda X, y: models.TabPFNModel(X, y))
    table = models.speed_table(context, wind_model, factor)
    m = make(table["X"], table["y"])
    rows = ghostmod.ghost_rows(chunk)
    sub = {k: (v[rows] if isinstance(v, np.ndarray) and v.shape[:1] == rows.shape else v) for k, v in chunk.items()}
    xw = models.features(sub, wind_model, factor)
    xc = models.features(sub, wind_model, factor, calm=True)
    both = models.median(m, np.vstack([xw, xc]))
    return both[: len(xw)], both[len(xw):]


def physics_speeds(chunk: dict, rider, wind_model: str, factor: float, rho=None):
    """The same two predictions from the physics (a fitted rider: see `physics.fit_drag_and_rolling`)."""
    from .physics import air_density, speed_at_power

    rows = ghostmod.ghost_rows(chunk)
    p = chunk["power"][rows]
    g = chunk["grade"][rows]
    w = factor * chunk[f"head10__{wind_model}"][rows]
    r = air_density(chunk["temp"][rows], chunk["elev"][rows]) if rho is None else rho
    return speed_at_power(p, g, rider, w, r), speed_at_power(p, g, rider, 0.0, r)


def judge(rs: RideSeries, context: list[RideSeries], make=None, rider=None, height_factor: float | None = None,
          extra_variants: bool = True) -> Verdict:
    """The ghost of `rs` learned from `context` (the rider's other rides), with its range."""
    if not context:
        raise ValueError("the ghost needs at least one other ride to learn the rider from")
    ch = chunks(rs)
    ctx = [chunks(c) for c in context if c.name != rs.name]
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
            k = wind.rider_height_factor() if height_factor is None else height_factor
            for m in rs.models:
                a, b = physics_speeds(ch, rider, m, k)
                v.variants[f"physics, {m}"] = ghostmod.replay(ch, a, b, m).gap_s
    return v
