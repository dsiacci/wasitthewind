"""The wind along a ride, rebuilt from weather-model grids.

Nothing is asked about the track itself. The tool asks Open-Meteo for the
wind on a fixed lattice of points (every 0.025°, about 2.5 km), in square
blocks of 0.1° that cover the ride, for whole UTC days; the blocks and the
date are all that leave the machine. The lattice is then interpolated here,
in space (bilinear) and time (linear), on the east and north components.

Models (Open-Meteo historical forecasts, CC BY 4.0):
- ``meteofrance_arome_france_hd``: Météo-France AROME, about 1.5 km, every
  15 minutes; the main source over France and Corsica.
- ``ecmwf_ifs``: ECMWF IFS, about 9 km, hourly; a second opinion, used for
  the range.

The models give the wind at 10 m. A rider sits around 1.2 m above the road,
where the wind is weaker; :func:`rider_height_factor` moves it down with the
logarithmic profile. Shelter from hills, walls and trees is not modelled.
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

API = "https://historical-forecast-api.open-meteo.com/v1/forecast"
USER_AGENT = "wasitthewind (+https://github.com/dsiacci/wasitthewind)"
STEP_DEG = 0.025
BLOCK_DEG = 0.1
MAX_LOCATIONS = 100  # per request

MODELS = {
    # name: (Open-Meteo resolution key, seconds between values)
    "meteofrance_arome_france_hd": ("minutely_15", 900),
    "ecmwf_ifs": ("hourly", 3600),
}
DEFAULT_MODEL = "meteofrance_arome_france_hd"


# --- the lattice -------------------------------------------------------------


def lattice(lat_min, lat_max, lon_min, lon_max, margin_deg: float = 0.05,
            step: float = STEP_DEG, block: float = BLOCK_DEG):
    """Lattice latitudes and longitudes covering a box, snapped outward to whole blocks.

    Works in whole steps so that two rides in the same area ask for exactly
    the same points.
    """
    per_block = int(round(block / step))

    def axis(lo, hi):
        b0 = math.floor((lo - margin_deg) / block + 1e-9)
        b1 = math.ceil((hi + margin_deg) / block - 1e-9)
        k = np.arange(b0 * per_block, b1 * per_block + 1)
        return np.round(k * step, 4)

    return axis(lat_min, lat_max), axis(lon_min, lon_max)


def lattice_for_track(lat, lon, **kw):
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    ok = np.isfinite(lat) & np.isfinite(lon)
    if not ok.any():
        raise ValueError("the ride has no positions")
    return lattice(lat[ok].min(), lat[ok].max(), lon[ok].min(), lon[ok].max(), **kw)


# --- vectors -----------------------------------------------------------------


def to_uv(speed, direction_from_deg):
    """East and north components of a wind given as speed and the direction it blows FROM."""
    s = np.asarray(speed, dtype=float)
    r = np.radians(np.asarray(direction_from_deg, dtype=float))
    return -s * np.sin(r), -s * np.cos(r)


def from_uv(u, v):
    """(speed, direction the wind blows FROM, degrees) from east and north components."""
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    return np.hypot(u, v), np.degrees(np.arctan2(-u, -v)) % 360.0


def components(u, v, heading_deg):
    """(headwind, crosswind) for a rider going `heading_deg`.

    Headwind is positive in the rider's face, negative at the back. Crosswind
    is positive when it pushes the rider to the right (it comes from the left).
    """
    h = np.radians(np.asarray(heading_deg, dtype=float))
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    head = -(u * np.sin(h) + v * np.cos(h))
    cross = u * np.cos(h) - v * np.sin(h)
    return head, cross


def rider_height_factor(height_m: float = 1.2, z0_m: float = 0.1, ref_m: float = 10.0) -> float:
    """Ratio of the wind at `height_m` to the wind at `ref_m`, logarithmic profile.

    `z0_m` is the roughness length: 0.03 for open flat country, 0.1 for
    farmland with hedges and scattered trees, 0.3 to 0.5 for maquis and
    villages. With the defaults the rider feels a bit over half the 10 m wind.
    """
    if not (0 < z0_m < height_m < ref_m or 0 < z0_m < ref_m <= height_m):
        raise ValueError("need 0 < roughness < heights")
    return math.log(height_m / z0_m) / math.log(ref_m / z0_m)


# --- the field ---------------------------------------------------------------


@dataclass
class WindField:
    """Wind at 10 m on a lattice: u and v of shape (time, lat, lon), times in epoch seconds (UTC)."""

    model: str
    times: np.ndarray
    lats: np.ndarray
    lons: np.ndarray
    u: np.ndarray
    v: np.ndarray

    def covers(self, lat, lon) -> np.ndarray:
        lat = np.asarray(lat, dtype=float)
        lon = np.asarray(lon, dtype=float)
        return ((lat >= self.lats[0]) & (lat <= self.lats[-1])
                & (lon >= self.lons[0]) & (lon <= self.lons[-1]))

    def at(self, when, lat, lon):
        """(u, v) at epoch seconds `when` and positions, bilinear in space and linear in time."""
        when = np.atleast_1d(np.asarray(when, dtype=float))
        lat = np.broadcast_to(np.asarray(lat, dtype=float), when.shape)
        lon = np.broadcast_to(np.asarray(lon, dtype=float), when.shape)
        if not self.covers(lat, lon).all():
            raise ValueError("position outside the wind lattice")
        if when.min() < self.times[0] or when.max() > self.times[-1]:
            raise ValueError("time outside the wind field")
        ti, tw = _index(self.times, when)
        yi, yw = _index(self.lats, lat)
        xi, xw = _index(self.lons, lon)
        out = []
        for g in (self.u, self.v):
            acc = np.zeros(when.shape)
            for dt_, wt in ((0, 1 - tw), (1, tw)):
                for dy, wy in ((0, 1 - yw), (1, yw)):
                    for dx, wx in ((0, 1 - xw), (1, xw)):
                        acc += wt * wy * wx * g[ti + dt_, yi + dy, xi + dx]
            out.append(acc)
        return out[0], out[1]


def _index(axis: np.ndarray, x: np.ndarray):
    """Lower cell index and weight of x along an increasing axis (clipped to the last cell)."""
    i = np.clip(np.searchsorted(axis, x, side="right") - 1, 0, axis.size - 2)
    w = (x - axis[i]) / (axis[i + 1] - axis[i])
    return i, np.clip(w, 0.0, 1.0)


# --- fetching and caching ----------------------------------------------------


def days_covering(start: datetime, end: datetime) -> list[date]:
    """UTC days from one hour before `start` to one hour after `end`."""
    a = (start - timedelta(hours=1)).astimezone(timezone.utc).date()
    b = (end + timedelta(hours=1)).astimezone(timezone.utc).date()
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def _node_key(lat: float, lon: float) -> str:
    return f"{lat:.4f},{lon:.4f}"


def load_field(lats, lons, days: list[date], model: str = DEFAULT_MODEL,
               cache_dir: str | Path | None = None, fetch=None) -> WindField:
    """The wind field on a lattice for whole UTC days, from the cache or from Open-Meteo.

    `fetch(model, day, nodes) -> (times, {node_key: (speeds, directions)})` can
    be swapped for tests; by default it calls Open-Meteo.
    """
    if model not in MODELS:
        raise ValueError(f"unknown model {model!r}; known: {', '.join(MODELS)}")
    fetch = fetch or fetch_open_meteo
    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    nodes = [(float(a), float(b)) for a in lats for b in lons]
    all_times: list[float] = []
    per_node: dict[str, tuple[list, list]] = {_node_key(*n): ([], []) for n in nodes}
    for day in sorted(days):
        cached = _read_cache(cache_dir, model, day)
        missing = [n for n in nodes if _node_key(*n) not in cached["nodes"]]
        if missing:
            times, values = fetch(model, day, missing)
            if cached["times"] and list(cached["times"]) != list(times):
                cached = {"times": [], "nodes": {}}
                missing = nodes
                times, values = fetch(model, day, missing)
            cached["times"] = list(times)
            cached["nodes"].update({k: [list(s), list(d)] for k, (s, d) in values.items()})
            _write_cache(cache_dir, model, day, cached)
        all_times.extend(cached["times"])
        for n in nodes:
            s, d = cached["nodes"][_node_key(*n)]
            per_node[_node_key(*n)][0].extend(s)
            per_node[_node_key(*n)][1].extend(d)
    t = np.asarray(all_times, dtype=float)
    shape = (t.size, lats.size, lons.size)
    u = np.full(shape, np.nan)
    v = np.full(shape, np.nan)
    for i, a in enumerate(lats):
        for j, b in enumerate(lons):
            s, d = per_node[_node_key(a, b)]
            u[:, i, j], v[:, i, j] = to_uv(_floats(s), _floats(d))
    good = np.isfinite(u).all(axis=(1, 2)) & np.isfinite(v).all(axis=(1, 2))
    if not good.any():
        raise RuntimeError(f"{model} has no wind for {days[0]}..{days[-1]} on this lattice")
    return WindField(model=model, times=t[good], lats=lats, lons=lons, u=u[good], v=v[good])


def _floats(xs) -> np.ndarray:
    return np.array([np.nan if x is None else float(x) for x in xs])


def _cache_path(cache_dir, model: str, day: date) -> Path | None:
    if cache_dir is None:
        return None
    return Path(cache_dir) / model / f"{day.isoformat()}.json"


def _read_cache(cache_dir, model: str, day: date) -> dict:
    p = _cache_path(cache_dir, model, day)
    if p is not None and p.exists():
        return json.loads(p.read_text())
    return {"times": [], "nodes": {}}


def _write_cache(cache_dir, model: str, day: date, data: dict) -> None:
    p = _cache_path(cache_dir, model, day)
    if p is None:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")))
    tmp.replace(p)


def fetch_open_meteo(model: str, day: date, nodes, pause_s: float = 1.0):
    """Wind at 10 m for whole UTC `day` at lattice `nodes`, from Open-Meteo's historical forecasts."""
    key, _ = MODELS[model]
    times: list[float] | None = None
    values: dict[str, tuple[list, list]] = {}
    for start in range(0, len(nodes), MAX_LOCATIONS):
        chunk = nodes[start:start + MAX_LOCATIONS]
        params = {
            "latitude": ",".join(f"{a:.4f}" for a, _ in chunk),
            "longitude": ",".join(f"{b:.4f}" for _, b in chunk),
            key: "wind_speed_10m,wind_direction_10m",
            "models": model,
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "wind_speed_unit": "ms",
            "timezone": "GMT",
        }
        data = _get_json(API + "?" + urllib.parse.urlencode(params))
        if isinstance(data, dict):
            data = [data]
        if len(data) != len(chunk):
            raise RuntimeError(f"Open-Meteo returned {len(data)} locations for {len(chunk)}")
        for node, d in zip(chunk, data):
            block = d[key]
            t = [datetime.fromisoformat(x).replace(tzinfo=timezone.utc).timestamp() for x in block["time"]]
            if times is None:
                times = t
            values[_node_key(*node)] = (block["wind_speed_10m"], block["wind_direction_10m"])
        if start + MAX_LOCATIONS < len(nodes):
            time.sleep(pause_s)
    return times or [], values


def _get_json(url: str, retries: int = 6, wait_s: float = 65.0):
    """GET a JSON document; on HTTP 429 (the free API's per-minute limit), wait and try again."""
    import urllib.error

    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == retries:
                raise
            time.sleep(wait_s)
