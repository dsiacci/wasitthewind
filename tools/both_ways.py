"""The proof, part two: flat roads ridden both ways.

On a flat road ridden out and back at a similar power, the way into the wind
should be the slower one, by about what the wind says; once the wind is taken
out, the two ways should ride at the same speed. If the gap doesn't melt, the
rebuilt wind (or the model) is wrong, and that's worth saying.

For every pair of rides (a ride with itself included), stretches of at least
400 m where the second ride passes within 25 m of the first going the other
way, both nearly flat (|grade| < 2 %), at powers within 15 % of each other.

Even 1 % of grade weighs more than 1 m/s of wind, so the two ways are
compared at the same power and grade: each speed is divided by the speed a
model predicts for that power and grade with no wind ("calm-relative
speed"). If the wind is right, the way into it is slow on that scale, and
dividing by the speed predicted *with* the wind instead brings both ways
back level. Two models do the predicting: the physics (when the rider's mass
is given) and TabPFN (from ``tools/validate.py``).

Needs the positions (``prepare --tracks``); prints only dates, lengths,
speeds, winds and percentages.

    WASITTHEWIND_RIDER_KG=... python tools/both_ways.py SERIES_DIR --validate results.json [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wasitthewind import wind  # noqa: E402
from wasitthewind.analysis import fitted_rider, physics_speeds  # noqa: E402
from wasitthewind.ghost import ghost_rows  # noqa: E402
from wasitthewind.ride import CHUNK_S, RideSeries, chunks  # noqa: E402

STEP_M = 10.0
NEAR_M = 25.0
MIN_LEN_M = 400.0
FLAT = 0.02
POWER_TOL = 0.15
MODEL = wind.DEFAULT_MODEL


def resampled(rs: RideSeries, lat, lon, ratios: dict[str, np.ndarray]):
    """Every 10 m of moving road: position, heading, grade, speed, power, headwind, and per-chunk predictions."""
    mv = rs.moving & (rs.speed > 1.5)
    d = rs.dist
    grid = np.arange(d[mv][0], d[mv][-1], STEP_M) if mv.any() else np.zeros(0)
    idx = np.clip(np.searchsorted(d, grid), 0, d.size - 1)
    idx = idx[mv[idx]]
    out = {"i": idx, "lat": lat[idx], "lon": lon[idx], "heading": rs.heading[idx], "grade": rs.grade[idx],
           "speed": rs.speed[idx], "power": rs.power[idx], "head": rs.head10[MODEL][idx]}
    chunk_of = np.minimum(idx // CHUNK_S, max(len(next(iter(ratios.values()), [1])) - 1, 0))
    for k, r in ratios.items():
        out[k] = r[chunk_of] if r.size else np.full(idx.size, np.nan)
    return out


def local_xy(lat, lon, lat0):
    k = np.pi / 180 * 6_371_008.8
    return lon * k * np.cos(np.radians(lat0)), lat * k


def matches(a: dict, b: dict, same: bool):
    """Runs of points of `a` with a point of `b` within 25 m going the other way."""
    lat0 = float(np.mean(a["lat"]))
    ax, ay = local_xy(a["lat"], a["lon"], lat0)
    bx, by = local_xy(b["lat"], b["lon"], lat0)
    cell = {}
    for j, (x, y) in enumerate(zip((bx // NEAR_M).astype(int), (by // NEAR_M).astype(int))):
        cell.setdefault((x, y), []).append(j)
    partner = np.full(ax.size, -1)
    for i in range(ax.size):
        cx, cy = int(ax[i] // NEAR_M), int(ay[i] // NEAR_M)
        best, bd = -1, NEAR_M
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cell.get((cx + dx, cy + dy), ()):
                    if same and abs(int(a["i"][i]) - int(b["i"][j])) < 120:
                        continue
                    dist = np.hypot(ax[i] - bx[j], ay[i] - by[j])
                    turn = abs((a["heading"][i] - b["heading"][j] + 180) % 360 - 180)
                    if dist < bd and turn > 150:
                        best, bd = j, dist
        partner[i] = best
    flat = np.abs(a["grade"]) < FLAT
    ok = (partner >= 0) & flat
    ok &= np.where(partner >= 0, np.abs(b["grade"][np.maximum(partner, 0)]) < FLAT, False)
    runs, i = [], 0
    while i < ok.size:
        if not ok[i]:
            i += 1
            continue
        j = i
        while j + 1 < ok.size and (ok[j + 1] or (j + 2 < ok.size and ok[j + 2])):
            j += 1
        if (j - i + 1) * STEP_M >= MIN_LEN_M:
            runs.append((i, j))
        i = j + 1
    return [(np.arange(i, j + 1)[ok[i:j + 1]], partner[i:j + 1][ok[i:j + 1]]) for i, j in runs]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("series", type=Path)
    ap.add_argument("--validate", type=Path, help="tools/validate.py output, for the TabPFN ghost")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--factor", type=float, default=wind.rider_height_factor(),
                    help="headwind felt / 10 m headwind, for the physics (default: log profile, 1.2 m, roughness 0.1 m)")
    args = ap.parse_args(argv)

    val = json.loads(args.validate.read_text()) if args.validate else None
    rider = None
    if os.environ.get("WASITTHEWIND_RIDER_KG"):
        from wasitthewind.physics import Bike, Rider

        rider = Rider(mass_kg=float(os.environ["WASITTHEWIND_RIDER_KG"]), bike=Bike(mass_kg=11.5))
    rides = {}
    all_ch = {}
    for p in sorted(args.series.glob("*.npz")):
        if p.name.endswith(".track.npz"):
            continue
        rs = RideSeries.load(p)
        tr = np.load(p.with_name(f"{rs.name}.track.npz"))
        rides[rs.name] = (rs, tr["lat"], tr["lon"])
        all_ch[rs.name] = chunks(rs)
    if rider is not None:
        rider = fitted_rider(rider, list(all_ch.values()), MODEL, args.factor)  # stays in memory
    res = {}
    for name, (rs, lat, lon) in rides.items():
        ch = all_ch[name]
        rows = ghost_rows(ch)
        ratios = {}
        if val and name in val["rides"] and "per_chunk_v_wind" in val["rides"][name]["ghost"][MODEL]:
            gv = val["rides"][name]["ghost"][MODEL]
            ratios["tabpfn_w"] = np.array([np.nan if x is None else x for x in gv["per_chunk_v_wind"]])
            ratios["tabpfn_0"] = np.array([np.nan if x is None else x for x in gv["per_chunk_v_calm"]])
        if rider is not None:
            vw, vc = physics_speeds(ch, rider, MODEL, args.factor)
            for k, v in (("physics_w", vw), ("physics_0", vc)):
                r = np.full(rows.size, np.nan)
                r[rows] = v
                ratios[k] = r
        res[name] = resampled(rs, lat, lon, ratios)
    pairs = []
    names = sorted(res)
    for ia, na in enumerate(names):
        for nb in names[ia:]:
            for ai, bi in matches(res[na], res[nb], same=(na == nb)):
                a, b = res[na], res[nb]
                pa, pb = a["power"][ai].mean(), b["power"][bi].mean()
                if abs(pa - pb) > POWER_TOL * max(pa, pb):
                    continue
                if na == nb and a["i"][ai].mean() > b["i"][bi].mean():
                    continue  # each out-and-back once
                e = {"a": na, "b": nb, "length_m": float(len(ai) * STEP_M),
                     "power_ratio": float(pa / pb),
                     "speed_a": float(a["speed"][ai].mean()), "speed_b": float(b["speed"][bi].mean()),
                     "grade_a": float(a["grade"][ai].mean()), "grade_b": float(b["grade"][bi].mean()),
                     "head_a": float(a["head"][ai].mean()), "head_b": float(b["head"][bi].mean())}
                for k in ("tabpfn", "physics"):
                    if f"{k}_w" in a and f"{k}_w" in b:
                        # calm-relative speed (÷ prediction with no wind), and the same ÷ prediction with the wind
                        e[f"rel0_a_{k}"] = float(np.nanmean(a["speed"][ai] / a[f"{k}_0"][ai]))
                        e[f"rel0_b_{k}"] = float(np.nanmean(b["speed"][bi] / b[f"{k}_0"][bi]))
                        e[f"relw_a_{k}"] = float(np.nanmean(a["speed"][ai] / a[f"{k}_w"][ai]))
                        e[f"relw_b_{k}"] = float(np.nanmean(b["speed"][bi] / b[f"{k}_w"][bi]))
                pairs.append(e)
    # orient each pair: "into" is the way with more headwind
    for e in pairs:
        if e["head_a"] < e["head_b"]:
            for k in list(e):
                if k.endswith("_a"):
                    kb = k[:-2] + "_b"
                    e[k], e[kb] = e[kb], e[k]
                elif "_a_" in k:
                    kb = k.replace("_a_", "_b_")
                    e[k], e[kb] = e[kb], e[k]
            e["a"], e["b"] = e["b"], e["a"]
            e["power_ratio"] = 1 / e["power_ratio"]

    def day(n):
        return datetime.fromtimestamp(rides[n][0].start_epoch, timezone.utc).strftime("%d/%m")

    print(f"{len(pairs)} stretches")
    for e in sorted(pairs, key=lambda e: e["head_b"] - e["head_a"]):
        line = (f"{day(e['a'])}→{day(e['b'])} {e['length_m']:5.0f} m  headwind {e['head_a']:+.1f}/{e['head_b']:+.1f}  "
                f"grade {100 * e['grade_a']:+.1f}/{100 * e['grade_b']:+.1f} %  "
                f"speed {100 * (e['speed_a'] / e['speed_b'] - 1):+.1f} %  power ratio {e['power_ratio']:.2f}")
        for k in ("tabpfn", "physics"):
            if f"rel0_a_{k}" in e:
                line += (f"  {k}: calm-relative {100 * (e[f'rel0_a_{k}'] / e[f'rel0_b_{k}'] - 1):+.1f} %, "
                         f"wind out {100 * (e[f'relw_a_{k}'] / e[f'relw_b_{k}'] - 1):+.1f} %")
        print(line)
    if pairs:
        w = np.array([e["length_m"] for e in pairs])
        dh = np.array([e["head_a"] - e["head_b"] for e in pairs])
        raw = np.array([100 * (e["speed_a"] / e["speed_b"] - 1) for e in pairs])
        summary = {"n": len(pairs), "length_m": float(w.sum()), "mean_head_diff": float(np.average(dh, weights=w)),
                   "raw_pct": float(np.average(raw, weights=w)),
                   "raw_corr_with_head_diff": float(np.corrcoef(dh, raw)[0, 1]) if len(pairs) > 2 else float("nan")}
        for k in ("tabpfn", "physics"):
            if all(f"rel0_a_{k}" in e for e in pairs):
                r0 = np.array([100 * (e[f"rel0_a_{k}"] / e[f"rel0_b_{k}"] - 1) for e in pairs])
                rw = np.array([100 * (e[f"relw_a_{k}"] / e[f"relw_b_{k}"] - 1) for e in pairs])
                summary[f"{k}_calm_relative_pct"] = float(np.average(r0, weights=w))
                summary[f"{k}_wind_out_pct"] = float(np.average(rw, weights=w))
                summary[f"{k}_calm_relative_abs_pct"] = float(np.average(np.abs(r0), weights=w))
                summary[f"{k}_wind_out_abs_pct"] = float(np.average(np.abs(rw), weights=w))
                summary[f"{k}_corr_calm_relative_with_head_diff"] = (float(np.corrcoef(dh, r0)[0, 1])
                                                                     if len(pairs) > 2 else float("nan"))
        summary["raw_abs_pct"] = float(np.average(np.abs(raw), weights=w))
        print(json.dumps(summary, indent=1))
        if args.json:
            args.json.write_text(json.dumps({"summary": summary, "pairs": pairs,
                                             "days": {n: day(n) for n in rides}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
