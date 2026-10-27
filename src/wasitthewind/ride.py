"""From a FIT file to one-second series with the wind, then to the 30-second rows the models learn from.

Per second: distance along the track, grade (the bike computer's barometric
altitude, smoothed over 100 m), heading (from the positions 20 m behind and
ahead), power, speed, temperature, minutes ridden, and the 10 m wind of each
weather model, as headwind and crosswind for the rider's heading.

Per 30 seconds, ridden without a stop: means of the same, plus the change of
kinetic energy (a chunk that ends faster than it started got some of its
speed from the legs). None of the saved arrays holds a position.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import wind as windmod
from .fitfile import Ride, fill_short_gaps
from .geo import cumulative_m, headings_deg

CHUNK_S = 30
GRADE_SPAN_M = 100.0
MAX_GRADE = 0.25


@dataclass
class RideSeries:
    name: str
    start_epoch: float
    epoch: np.ndarray
    moving: np.ndarray
    dist: np.ndarray
    speed: np.ndarray
    power: np.ndarray
    grade: np.ndarray
    elev: np.ndarray
    temp: np.ndarray
    heading: np.ndarray
    elapsed_min: np.ndarray
    head10: dict[str, np.ndarray] = field(default_factory=dict)  # model -> headwind at 10 m
    cross10: dict[str, np.ndarray] = field(default_factory=dict)
    speed10: dict[str, np.ndarray] = field(default_factory=dict)  # wind speed at 10 m
    from10: dict[str, np.ndarray] = field(default_factory=dict)  # direction it blows from

    ARRAYS = ("epoch", "moving", "dist", "speed", "power", "grade", "elev", "temp", "heading", "elapsed_min")

    @property
    def models(self) -> list[str]:
        return list(self.head10)

    def save(self, path: str | Path) -> None:
        """Series without positions."""
        extra = {}
        for m in self.models:
            extra[f"head10__{m}"] = self.head10[m]
            extra[f"cross10__{m}"] = self.cross10[m]
            extra[f"speed10__{m}"] = self.speed10[m]
            extra[f"from10__{m}"] = self.from10[m]
        np.savez_compressed(path, name=self.name, start_epoch=self.start_epoch,
                            **{k: getattr(self, k) for k in self.ARRAYS}, **extra)

    @classmethod
    def load(cls, path: str | Path) -> "RideSeries":
        z = np.load(path, allow_pickle=False)
        rs = cls(name=str(z["name"]), start_epoch=float(z["start_epoch"]), **{k: z[k] for k in cls.ARRAYS})
        for key in z.files:
            if "__" in key:
                kind, model = key.split("__", 1)
                getattr(rs, kind)[model] = z[key]
        return rs


def smoothed_grade(dist_m, alt_m, span_m: float = GRADE_SPAN_M):
    """Grade from altitude, as the slope of a straight line fitted over `span_m` of road around each point."""
    d = np.asarray(dist_m, dtype=float)
    z = fill_short_gaps(np.asarray(alt_m, dtype=float), 30)
    ok = np.isfinite(d) & np.isfinite(z)
    if ok.sum() < 3:
        return np.zeros(d.size), np.where(np.isfinite(z), z, 0.0)
    keep = ok & np.concatenate([[True], np.diff(np.where(ok, d, -1)) > 0.05])
    dd, zz = d[keep], z[keep]
    step = 10.0
    grid = np.arange(dd[0], dd[-1] + step, step)
    zg = np.interp(grid, dd, zz)
    half = max(1, int(round(span_m / step / 2)))
    k = np.arange(-half, half + 1) * step
    pad = np.pad(zg, half, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(pad, k.size)
    slope = (windows - windows.mean(axis=1, keepdims=True)) @ k / (k @ k)
    zs = windows.mean(axis=1)
    grade = np.clip(np.interp(d, grid, slope), -MAX_GRADE, MAX_GRADE)
    return grade, np.interp(d, grid, zs)


def series(ride: Ride, fields: list[windmod.WindField] | None = None) -> RideSeries:
    """One-second series of a ride, with the wind of each field along it."""
    lat = fill_short_gaps(ride.lat, 10)
    lon = fill_short_gaps(ride.lon, 10)
    ok = np.isfinite(lat) & np.isfinite(lon)
    lat_f = np.interp(ride.t, ride.t[ok], lat[ok])
    lon_f = np.interp(ride.t, ride.t[ok], lon[ok])
    speed = np.nan_to_num(fill_short_gaps(ride.speed, 5), nan=0.0)
    moving = speed >= 1.0
    dist = cumulative_m(lat_f, lon_f)
    grade, elev = smoothed_grade(dist, ride.alt)
    heading = headings_deg(lat_f, lon_f, dist)
    temp = fill_short_gaps(ride.temp, 120)
    temp = np.where(np.isfinite(temp), temp, np.nanmedian(temp) if np.isfinite(temp).any() else 20.0)
    epoch = ride.start.timestamp() + ride.t
    rs = RideSeries(name=ride.name, start_epoch=ride.start.timestamp(), epoch=epoch, moving=moving, dist=dist,
                    speed=speed, power=np.nan_to_num(fill_short_gaps(ride.power, 5), nan=0.0), grade=grade,
                    elev=elev, temp=temp, heading=heading, elapsed_min=np.cumsum(moving) / 60.0)
    for f in fields or []:
        u, v = f.at(epoch, lat_f, lon_f)
        head, cross = windmod.components(u, v, heading)
        s, d = windmod.from_uv(u, v)
        rs.head10[f.model], rs.cross10[f.model] = head, cross
        rs.speed10[f.model], rs.from10[f.model] = s, d
    return rs


def positions(ride: Ride):
    """Gap-filled positions, for the maps only (never saved with the series)."""
    lat = fill_short_gaps(ride.lat, 10)
    lon = fill_short_gaps(ride.lon, 10)
    ok = np.isfinite(lat) & np.isfinite(lon)
    return np.interp(ride.t, ride.t[ok], lat[ok]), np.interp(ride.t, ride.t[ok], lon[ok])


def chunks(rs: RideSeries, size_s: int = CHUNK_S) -> dict[str, np.ndarray]:
    """Means over 30-second windows; `full` marks windows ridden without a stop."""
    n = rs.moving.size // size_s
    if n == 0:
        return {}
    cut = n * size_s

    def m(x):
        return np.asarray(x[:cut], dtype=float).reshape(n, size_s).mean(axis=1)

    def edge(x, i):
        return np.asarray(x[:cut], dtype=float).reshape(n, size_s)[:, i]

    v0, v1 = edge(rs.speed, 0), edge(rs.speed, -1)
    out = {
        "ride": np.full(n, rs.name),
        "start_s": np.arange(n) * size_s,
        "full": m(rs.moving.astype(float)) >= 0.999,
        "power": m(rs.power),
        "speed": m(rs.speed),
        "grade": m(rs.grade),
        "elev": m(rs.elev),
        "temp": m(rs.temp),
        "elapsed_min": m(rs.elapsed_min),
        "dist_m": edge(rs.dist, -1) - edge(rs.dist, 0),
        "dv2": v1**2 - v0**2,  # times half the mass over the duration: the power spent speeding up
        "heading_change": _heading_spread(rs.heading[:cut].reshape(n, size_s)),
    }
    for model in rs.models:
        out[f"head10__{model}"] = m(rs.head10[model])
        out[f"cross10__{model}"] = m(np.abs(rs.cross10[model]))
        out[f"speed10__{model}"] = m(rs.speed10[model])
    return out


def _heading_spread(h):
    """How much the heading turns within a window (degrees), to spot hairpins and roundabouts."""
    r = np.radians(h)
    c = np.hypot(np.cos(r).mean(axis=1), np.sin(r).mean(axis=1))
    return np.degrees(np.sqrt(-2 * np.log(np.clip(c, 1e-9, 1.0))))
