"""Measured wind, to check the rebuilt one: weather stations and airport reports.

- Météo-France hourly climatological data, one file per département
  (meteo.data.gouv.fr, Licence Ouverte 2.0). ``FF`` is the mean wind over the
  last 10 minutes before the hour at 10 m, in m/s; ``DD`` its direction, in
  degrees (where it blows from). Times are UTC.
- METAR from the Iowa Environmental Mesonet (Iowa State University): the
  airport's wind every 30 minutes, in knots, a 10-minute mean as well.
"""

from __future__ import annotations

import csv
import gzip
import io
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

KNOT_MS = 0.514444
METEOFRANCE_HOURLY = "https://meteofrance.s3.sbg.io.cloud.ovh.net/data/synchro_ftp/BASE/HOR/H_{dep}_latest-2025-2026.csv.gz"
IEM_ASOS = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
USER_AGENT = "wasitthewind (+https://github.com/dsiacci/wasitthewind)"


@dataclass
class Measured:
    """Wind measured at one place: times in epoch seconds (UTC), speed in m/s, direction FROM in degrees."""

    source: str
    station: str
    name: str
    lat: float
    lon: float
    alt_m: float
    times: np.ndarray
    speed: np.ndarray
    direction: np.ndarray

    def between(self, t0: float, t1: float) -> "Measured":
        k = (self.times >= t0) & (self.times <= t1)
        return Measured(self.source, self.station, self.name, self.lat, self.lon, self.alt_m,
                        self.times[k], self.speed[k], self.direction[k])


def _num(s: str) -> float:
    s = s.strip()
    return float(s) if s else np.nan


def read_meteofrance(path: str | Path, stations: set[str] | None = None) -> dict[str, Measured]:
    """Stations of a Météo-France hourly file (``H_<dep>_*.csv.gz``) with their wind."""
    opener = gzip.open if str(path).endswith(".gz") else open
    rows: dict[str, dict] = {}
    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        head = [h.strip() for h in next(reader)]
        col = {h: i for i, h in enumerate(head)}
        for r in reader:
            sid = r[col["NUM_POSTE"]].strip()
            if stations is not None and sid not in stations:
                continue
            ff = _num(r[col["FF"]])
            if not np.isfinite(ff):
                continue
            st = rows.setdefault(sid, {"name": r[col["NOM_USUEL"]].strip(), "lat": _num(r[col["LAT"]]),
                                       "lon": _num(r[col["LON"]]), "alt": _num(r[col["ALTI"]]),
                                       "t": [], "ff": [], "dd": []})
            stamp = r[col["AAAAMMJJHH"]].strip()
            t = datetime(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]), int(stamp[8:10]), tzinfo=timezone.utc)
            st["t"].append(t.timestamp())
            st["ff"].append(ff)
            st["dd"].append(_num(r[col["DD"]]))
    out = {}
    for sid, st in rows.items():
        order = np.argsort(st["t"])
        out[sid] = Measured("Météo-France", sid, st["name"], st["lat"], st["lon"], st["alt"],
                            np.asarray(st["t"])[order], np.asarray(st["ff"])[order],
                            np.asarray(st["dd"])[order])
    return out


def read_iem_metar(text: str, lat: float, lon: float, alt_m: float = np.nan) -> Measured:
    """METAR wind from the IEM ``asos.py`` comma output (columns station, valid, sknt, drct)."""
    reader = csv.DictReader(io.StringIO(text))
    t, s, d, sid = [], [], [], ""
    for r in reader:
        sid = r["station"]
        sk = r.get("sknt", "M")
        if sk in ("M", ""):
            continue
        when = datetime.strptime(r["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        dr = r.get("drct", "M")
        t.append(when.timestamp())
        s.append(float(sk) * KNOT_MS)
        d.append(np.nan if dr in ("M", "") else float(dr))
    return Measured("METAR", sid, sid, lat, lon, alt_m, np.asarray(t), np.asarray(s), np.asarray(d))


def download(url: str, dest: str | Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest.with_suffix(".part"), "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    dest.with_suffix(".part").replace(dest)
    return dest


def iem_metar_url(station: str, start: datetime, end: datetime) -> str:
    params = [("station", station), ("data", "sknt"), ("data", "drct"),
              ("year1", start.year), ("month1", start.month), ("day1", start.day),
              ("year2", end.year), ("month2", end.month), ("day2", end.day),
              ("tz", "Etc/UTC"), ("format", "onlycomma"), ("missing", "M")]
    return IEM_ASOS + "?" + urllib.parse.urlencode(params)


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", errors="replace")
