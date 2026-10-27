"""Command line: wasitthewind prepare | ghost | serve."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from . import __version__


def cmd_prepare(args) -> int:
    from .analysis import prepare

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    done = 0
    for p in args.fit:
        try:
            rs, (lat, lon) = prepare(p, args.cache)
        except ValueError as e:
            print(f"skipped: {e}", file=sys.stderr)
            continue
        rs.save(out / f"{rs.name}.npz")
        if args.tracks:
            np.savez_compressed(out / f"{rs.name}.track.npz", lat=lat, lon=lon)
        done += 1
        print(f"{rs.name}: {rs.moving.sum() / 60:.0f} min moving, wind from {', '.join(rs.models)}")
    return 0 if done else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wasitthewind", description="Was it really the wind? Race your ride's ghost.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="FIT files → series with the wind along them (no positions)")
    p.add_argument("fit", nargs="+", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cache", type=Path, default=Path("weather-cache"))
    p.add_argument("--tracks", action="store_true", help="also keep the positions, for the maps (stays local)")
    p.set_defaults(func=cmd_prepare)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
