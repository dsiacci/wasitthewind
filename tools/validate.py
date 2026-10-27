"""The proof, part one: does the wind help predict the speed, and what does each ride's ghost say?

Input: prepared series (``wasitthewind prepare``), no positions, no mass.

1. Leave one ride out: each ride's 30-second speeds predicted by models that
   only saw the other rides: TabPFN v2 with and without the wind columns, a
   linear regression with and without them, a constant.
2. The ghost of every ride, learned from the other rides only, for each
   weather model.

Writes a JSON file with times in seconds and speeds in m/s: no watts.

    python tools/validate.py SERIES_DIR --out results.json [--quick]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wasitthewind import ghost as ghostmod  # noqa: E402
from wasitthewind import models, wind  # noqa: E402
from wasitthewind.analysis import tabpfn_speeds  # noqa: E402
from wasitthewind.ride import RideSeries, chunks  # noqa: E402


def _on_rows(c, v):
    """Predicted speeds back on every chunk (NaN where the ghost rides like the rider)."""
    out = np.full(len(c["full"]), np.nan)
    out[ghostmod.ghost_rows(c)] = v
    return [None if not np.isfinite(x) else round(float(x), 4) for x in out]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("series", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--quick", action="store_true", help="linear models only (no TabPFN), to test the plumbing")
    ap.add_argument("--skip-loo", action="store_true", help="only the ghosts")
    ap.add_argument("--only", nargs="+", metavar="NAME", help='leave one ride out for these models only, e.g. "TabPFN, wind"')
    args = ap.parse_args(argv)

    rides = [RideSeries.load(p) for p in sorted(args.series.glob("*.npz")) if not p.name.endswith(".track.npz")]
    ch = {r.name: chunks(r) for r in rides}
    out: dict = {"rides": {}, "loo": {}}
    tab = (lambda X, y: models.TabPFNModel(X, y)) if not args.quick else models.LinearModel

    for wm in ([] if args.skip_loo else wind.MODELS):
        table = models.speed_table(list(ch.values()), wm, 1.0)
        factories = {
            "TabPFN, wind": tab,
            "TabPFN, no wind": models.without_wind(models.TabPFNModel if not args.quick else models.LinearModel),
            "linear, wind": models.LinearModel,
            "linear, no wind": models.without_wind(models.LinearModel),
            "constant": models.ConstantModel,
        }
        if args.only:
            factories = {k: v for k, v in factories.items() if k in args.only}
        t0 = time.time()
        res = models.leave_one_ride_out(table, factories)
        out["loo"][wm] = {name: {"all": r.get("all"), "per_ride": r["per_ride"]} for name, r in res.items()}
        print(f"[{wm}] leave-one-ride-out in {time.time() - t0:.0f} s, {len(table['y'])} rows", flush=True)
        for name, r in res.items():
            a = r.get("all") or {}
            print(f"  {name:18s} MAE {a.get('mae', float('nan')):.3f} m/s  bias {a.get('bias', float('nan')):+.3f}  "
                  f"80% interval holds {100 * a.get('coverage_80', float('nan')):.0f}%", flush=True)

    for r in rides:
        others = [ch[o.name] for o in rides if o.name != r.name]
        entry = {"start_epoch": r.start_epoch, "moving_s": float(r.moving.sum()), "ghost": {}}
        c = ch[r.name]
        for wm in wind.MODELS:
            vw, vc = tabpfn_speeds(c, others, wm, None if not args.quick else models.LinearModel)
            g = ghostmod.replay(c, vw, vc, wm)
            worst = ghostmod.stretches(g, 3)
            best = ghostmod.stretches(g, 2, worst=False)
            entry["ghost"][wm] = {
                "rider_s": g.rider_total_s, "ghost_s": g.ghost_total_s, "gap_s": g.gap_s, "gap_pct": g.gap_pct,
                "max_lead_m": float(g.ghost_lead_m().max()), "min_lead_m": float(g.ghost_lead_m().min()),
                "mean_wind10": float(np.average(c[f"speed10__{wm}"], weights=g.rider_s)),
                "worst": [s.__dict__ for s in worst], "best": [s.__dict__ for s in best],
                "per_chunk_ghost_s": g.ghost_s.round(3).tolist(),
                "per_chunk_v_wind": _on_rows(c, vw), "per_chunk_v_calm": _on_rows(c, vc),
            }
            print(f"{r.name} {wm:28s} gap {g.gap_s:+6.0f} s ({g.gap_pct:+.1f} %)  wind {entry['ghost'][wm]['mean_wind10']:.1f} m/s",
                  flush=True)
        out["rides"][r.name] = entry
    args.out.write_text(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
