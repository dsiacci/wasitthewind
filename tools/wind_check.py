"""How good is the rebuilt wind? The model lattice against stations and METAR, at the hours of the rides.

For every outdoor ride in a folder, the lattice that covers it and the
measuring stations within `--near-km` of the track is loaded (the analysis
asks for the same blocks, without the stations), then interpolated at every
station, at every hour from one hour before the start to one hour after the
end. Only times, station names and wind figures are printed: nothing
about where the ride went.

    python tools/wind_check.py RIDES_DIR --meteofrance H_20_latest-2025-2026.csv.gz \
        --cache weather-cache [--metar LFKJ:41.9236:8.8029] [--markdown out.md]
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wasitthewind import stations, wind  # noqa: E402
from wasitthewind.fitfile import read_fit  # noqa: E402
from wasitthewind.geo import haversine_m  # noqa: E402

CALM_MS = 2.0  # directions are only compared above this measured speed


def pairs(field: wind.WindField, m: stations.Measured):
    k = (m.times >= field.times[0]) & (m.times <= field.times[-1])
    if not k.any():
        return None
    t = m.times[k]
    u, v = field.at(t, np.full(t.size, m.lat), np.full(t.size, m.lon))
    mu, mv = wind.to_uv(m.speed[k], np.nan_to_num(m.direction[k], nan=0.0))
    has_dir = np.isfinite(m.direction[k])
    return {"t": t, "model_u": u, "model_v": v, "meas_s": m.speed[k], "meas_d": m.direction[k],
            "meas_u": mu, "meas_v": mv, "has_dir": has_dir}


def scores(rows: list[dict]) -> dict:
    if not rows:
        return {}
    cat = {k: np.concatenate([r[k] for r in rows]) for k in rows[0]}
    ms, md = wind.from_uv(cat["model_u"], cat["model_v"])
    s = cat["meas_s"]
    ok_dir = cat["has_dir"] & (s >= CALM_MS)
    du = cat["model_u"] - cat["meas_u"]
    dv = cat["model_v"] - cat["meas_v"]
    dd = np.abs((md - cat["meas_d"] + 180.0) % 360.0 - 180.0)
    vec = cat["has_dir"] | (s == 0)
    return {
        "n": int(s.size),
        "measured": float(np.mean(s)),
        "model": float(np.mean(ms)),
        "bias": float(np.mean(ms - s)),
        "mae": float(np.mean(np.abs(ms - s))),
        "corr": float(np.corrcoef(ms, s)[0, 1]) if s.size > 2 and np.std(s) > 0 else float("nan"),
        "vec_rmse": float(np.sqrt(np.mean(du[vec] ** 2 + dv[vec] ** 2))) if vec.any() else float("nan"),
        "dir_mae": float(np.mean(dd[ok_dir])) if ok_dir.any() else float("nan"),
        "n_dir": int(ok_dir.sum()),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rides", type=Path)
    ap.add_argument("--meteofrance", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("weather-cache"))
    ap.add_argument("--metar", action="append", default=[], help="ICAO:lat:lon of an airport (repeatable)")
    ap.add_argument("--models", default=",".join(wind.MODELS))
    ap.add_argument("--near-km", type=float, default=15.0, help="stations this close to the track are checked")
    ap.add_argument("--markdown", type=Path)
    args = ap.parse_args(argv)

    mf = stations.read_meteofrance(args.meteofrance)
    airports = []
    for spec in args.metar:
        icao, la, lo = spec.split(":")
        airports.append((icao, float(la), float(lo)))
    models = args.models.split(",")
    per_model: dict[str, list] = {m: [] for m in models}
    per_station: dict[tuple, list] = {}
    lines = []
    for path in sorted(args.rides.glob("*.fit")):
        ride = read_fit(path)
        if ride.is_virtual or not ride.has_power:
            continue
        end = ride.time_at(ride.t[-1])
        days = wind.days_covering(ride.start, end)
        t0 = (ride.start - timedelta(hours=1)).timestamp()
        t1 = (end + timedelta(hours=1)).timestamp()
        ok = np.isfinite(ride.lat) & np.isfinite(ride.lon)
        tlat, tlon = ride.lat[ok][::30], ride.lon[ok][::30]

        def near(la, lo):
            return haversine_m(tlat, tlon, la, lo).min() <= args.near_km * 1000

        measured = [m.between(t0, t1) for m in mf.values() if near(m.lat, m.lon)]
        for icao, la, lo in airports:
            if near(la, lo):
                text = stations.fetch_text(stations.iem_metar_url(icao, ride.start - timedelta(hours=1),
                                                                  end + timedelta(days=1)))
                measured.append(stations.read_iem_metar(text, la, lo).between(t0, t1))
        measured = [m for m in measured if m.times.size]
        lats, lons = wind.lattice(min(tlat.min(), *(m.lat for m in measured)) if measured else tlat.min(),
                                  max(tlat.max(), *(m.lat for m in measured)) if measured else tlat.max(),
                                  min(tlon.min(), *(m.lon for m in measured)) if measured else tlon.min(),
                                  max(tlon.max(), *(m.lon for m in measured)) if measured else tlon.max())
        for model in models:
            field = wind.load_field(lats, lons, days, model=model, cache_dir=args.cache)
            inside = [m for m in measured if field.covers(m.lat, m.lon)]
            for m in inside:
                p = pairs(field, m)
                if p is None:
                    continue
                per_model[model].append(p)
                per_station.setdefault((model, m.source, m.name), []).append(p)
                sc = scores([p])
                lines.append(f"{ride.start:%Y-%m-%d} {model:28s} {m.source:12s} {m.name:20s} "
                             f"n={sc['n']:3d} meas={sc['measured']:4.1f} model={sc['model']:4.1f} "
                             f"bias={sc['bias']:+4.1f} vec={sc['vec_rmse']:4.1f} dir={sc['dir_mae']:5.1f}")
    for line in lines:
        print(line)
    out = ["| model | where | n | measured (m/s) | model (m/s) | bias | MAE | r | vector RMSE | direction error (°, ≥ 2 m/s) |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for model in models:
        sc = scores(per_model[model])
        if sc:
            out.append(_row(model, "all stations", sc))
        for (mm, src, name), rows in sorted(per_station.items()):
            if mm == model:
                out.append(_row(model, f"{name} ({src})", scores(rows)))
    print("\n".join(out))
    if args.markdown:
        args.markdown.write_text("\n".join(out) + "\n")
    return 0


def _row(model, where, sc):
    return (f"| {model} | {where} | {sc['n']} | {sc['measured']:.1f} | {sc['model']:.1f} | {sc['bias']:+.1f} | "
            f"{sc['mae']:.1f} | {sc['corr']:.2f} | {sc['vec_rmse']:.1f} | {sc['dir_mae']:.0f} ({sc['n_dir']}) |")


if __name__ == "__main__":
    raise SystemExit(main())
