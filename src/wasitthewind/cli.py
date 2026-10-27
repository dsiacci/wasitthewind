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


def _mass(args):
    """The rider's mass, for the physics lines only: from --mass-kg or WASITTHEWIND_RIDER_KG, never written anywhere."""
    import os

    kg = args.mass_kg or os.environ.get("WASITTHEWIND_RIDER_KG")
    return float(kg) if kg else None


def _library(path, exclude_epoch=None):
    from .ride import RideSeries

    out = []
    for p in sorted(Path(path).glob("*.npz")) if path else []:
        if not p.name.endswith(".track.npz"):
            rs = RideSeries.load(p)
            if exclude_epoch is None or abs(rs.start_epoch - exclude_epoch) > 60:
                out.append(rs)
    return out


def _judge(path, args, rider):
    from .analysis import judge, prepare

    rs, track = prepare(path, args.cache)
    others = _library(args.library, rs.start_epoch)
    if len(others) < 2:
        raise ValueError("the ghost learns you from your other rides: prepare at least two more into --library")
    return rs, track, judge(rs, others, rider=rider)


def cmd_ghost(args) -> int:
    from zoneinfo import ZoneInfo

    from . import page, wind
    from .physics import Bike, Rider

    kg = _mass(args)
    rider = Rider(mass_kg=kg, bike=Bike()) if kg else None
    tz = ZoneInfo(args.tz)
    try:
        rs, (lat, lon), v = _judge(args.fit, args, rider)
        compare = None
        if args.compare:
            ors, _, ov = _judge(args.compare, args, rider)
            compare = {"label": page.when(ors.start_epoch, tz), "this_s": v.headline.rider_total_s,
                       "other_s": ov.headline.rider_total_s, "this_gap_s": v.gap_s, "other_gap_s": ov.gap_s}
    except ValueError as e:
        print(f"wasitthewind: {e}", file=sys.stderr)
        return 1
    lo, hi = v.range_s
    g = v.headline
    _, headline, sentence = page.verdict_words(v.gap_s, lo, hi, g.rider_total_s)
    print(f"{page.when(v.start_epoch, tz)} · {page.hm(g.rider_total_s)} moving · ghost {page.hm(g.ghost_total_s)}")
    print(f"{headline}. {sentence}")
    for i, s in enumerate(v.worst, 1):
        print(f"  {i}. km {page.km(s.start_m)} → {page.km(s.start_m + s.length_m)}: {page.mmss(s.lost_s)} lost, "
              f"headwind {page.kmh(s.head10_ms)} at 10 m")
    for name, gap in [("TabPFN, AROME (headline)", v.gap_s), *v.variants.items()]:
        print(f"  {page.VARIANT_LABELS.get(name, name):40s} {page.mmss(gap, sign=True)}")
    if args.page:
        text = page.result_page(v, rs, lat, lon, wind.rider_height_factor(), title=args.title, compare=compare, tz=tz)
        Path(args.page).write_text(text, encoding="utf-8")
        print(f"page: {args.page}")
    return 0


def cmd_serve(args) -> int:
    from .web import App, Settings, Store, make_server

    store = Store(args.data)
    settings = Settings(cache=str(args.cache or Path(args.data) / "weather-cache"),
                        library=str(args.library) if args.library else None, tz=args.tz, mass_kg=_mass(args))
    app = App(store, settings)
    httpd = make_server(app, args.host, args.port)
    print(f"wasitthewind on http://{args.host}:{args.port}/ (data in {store.root.parent})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
        httpd.server_close()
    return 0


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

    g = sub.add_parser("ghost", help="one ride against its ghost: the verdict, and its page")
    g.add_argument("fit", type=Path)
    g.add_argument("--library", type=Path, required=True, help="prepared series of your other rides")
    g.add_argument("--compare", type=Path, help="an earlier ride on the same road (FIT)")
    g.add_argument("--page", type=Path, help="write the result page here")
    g.add_argument("--title", default="Ride")
    g.add_argument("--cache", type=Path, default=Path("weather-cache"))
    g.add_argument("--mass-kg", type=float, help="rider's mass, for the physics lines (or WASITTHEWIND_RIDER_KG)")
    g.add_argument("--tz", default="Europe/Paris")
    g.set_defaults(func=cmd_ghost)

    s = sub.add_parser("serve", help="the web app, on this machine")
    s.add_argument("--data", type=Path, default=Path("wasitthewind-data"))
    s.add_argument("--library", type=Path, help="prepared series of older rides the ghost also learns from")
    s.add_argument("--cache", type=Path)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8766)
    s.add_argument("--mass-kg", type=float, help="rider's mass, for the physics lines (or WASITTHEWIND_RIDER_KG)")
    s.add_argument("--tz", default="Europe/Paris")
    s.set_defaults(func=cmd_serve)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
