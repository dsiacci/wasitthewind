"""What moves the ghost? Ways of taking the wind out, ride by ride.

For every ride, TabPFN learns from the other rides, then predicts the ride's
30-second pieces with the wind as it was and with the wind taken out in one
of several ways: all of it set to zero (the first version of the ghost), the
crosswind only, the headwind only, the headwind turned around (the ghost
today: the mean of the two answers), and a model that never saw the
crosswind. Each gives a ghost; the gap is printed as a share of the ghost's
time. Run it next to the physics to see which one tells the truth.

    python tools/counterfactuals.py SERIES_DIR --out counterfactuals.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wasitthewind import ghost as G  # noqa: E402
from wasitthewind import models, wind  # noqa: E402
from wasitthewind.ride import RideSeries, chunks  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("series", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default=wind.DEFAULT_MODEL)
    args = ap.parse_args(argv)

    wm, F = args.model, list(models.SPEED_FEATURES)
    rides = [RideSeries.load(p) for p in sorted(args.series.glob("*.npz")) if not p.name.endswith(".track.npz")]
    ch = {r.name: chunks(r) for r in rides}
    res = {}
    for r in rides:
        t0 = time.time()
        c = ch[r.name]
        tab = models.speed_table([ch[o.name] for o in rides if o.name != r.name], wm, 1.0)
        rows = G.ghost_rows(c)
        sub = {k: (v[rows] if isinstance(v, np.ndarray) and v.shape[:1] == rows.shape else v) for k, v in c.items()}
        x = models.features(sub, wm, 1.0)
        variants = {"actual": x}
        for name, cols in (("head0", ["head"]), ("cross0", ["cross"]), ("both0", ["head", "cross"])):
            xx = x.copy()
            for col in cols:
                xx[:, F.index(col)] = 0.0
            variants[name] = xx
        variants["turned"] = models.features(sub, wm, 1.0, turned=True)
        m = models.TabPFNModel(tab["X"], tab["y"])
        p = dict(zip(variants, models.median(m, np.vstack(list(variants.values()))).reshape(len(variants), -1)))
        entry = {"wind10": float(np.mean(c[f"speed10__{wm}"]))}
        for name in ("head0", "cross0", "both0"):
            entry[f"gap_pct_{name}"] = G.replay(c, p["actual"], p[name], wm).gap_pct
        entry["gap_pct_turned"] = G.replay(c, p["actual"], 0.5 * (p["actual"] + p["turned"]), wm).gap_pct
        # a model that never saw the crosswind, headwind to zero
        keep = [i for i, f in enumerate(F) if f != "cross"]
        m2 = models.TabPFNModel(tab["X"][:, keep], tab["y"])
        x2 = x[:, keep]
        x2c = x2.copy()
        x2c[:, [F[i] for i in keep].index("head")] = 0.0
        p2 = models.median(m2, np.vstack([x2, x2c])).reshape(2, -1)
        entry["gap_pct_nocross_head0"] = G.replay(c, p2[0], p2[1], wm).gap_pct
        y = c["speed"][rows]
        entry["mae"] = float(np.mean(np.abs(p["actual"] - y)))
        entry["mae_nocross"] = float(np.mean(np.abs(p2[0] - y)))
        res[r.name] = entry
        print(r.name, " ".join(f"{k} {v:+.2f}" for k, v in entry.items()), f"({time.time() - t0:.0f} s)", flush=True)
        args.out.write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
