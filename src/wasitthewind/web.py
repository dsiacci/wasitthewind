"""The web app: drop a ride, race its ghost a few minutes later, find every earlier race.

    wasitthewind serve --data ~/wasitthewind [--library prepared/] [--mass-kg 70]
    # then open http://127.0.0.1:8766/

A web service you run yourself: the pages come from your own machine, the
FIT files you drop stay in its data folder, and no page loads anything from
the internet. The only thing that leaves the machine is the wind request:
lattice blocks of 0.1° around the ride and its date (`wind.py`). Each
analysis keeps a folder: the file dropped (`in/`), `meta.json`, the series
(no positions) and the track (positions, for the map: they stay here), the
verdict as `result.json` and its page. The ghost learns the rider from every
other analysis (and from `--library`, prepared series of older rides). The
analyses run one at a time, in a background thread.

Started from z2analyzer's web app (same author, Apache 2.0): https://github.com/dsiacci/z2analyzer
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import queue
import re
import secrets
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from .page import CSS, document as page_document, fonts_css, hm, mmss, verdict_words, when

e = html.escape
ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")
MAX_UPLOAD = 32 * 1024 * 1024
STEPS = ("Reading the ride", "The wind along it (Open-Meteo: AROME and IFS)",
         "Learning you from your other rides (TabPFN)", "The race against your ghost")

SCRIPT = ("document.querySelectorAll('.drop input').forEach(function(i){i.addEventListener('change',function(){"
          "var z=i.closest('.drop');z.querySelector('.name').textContent=i.files.length?i.files[0].name:'';"
          "z.classList.toggle('has',i.files.length>0);});});")
SCRIPT_HASH = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()

APP_CSS = """
.appbar { display:flex; align-items:center; gap:10px; padding:10px max(16px, env(safe-area-inset-right)) 10px max(16px, env(safe-area-inset-left));
  background:var(--night); color:#eef3ff; position:relative; z-index:3; border-bottom:1px solid rgba(169,232,255,.10); }
.appbar .brand { font:700 21px/1 var(--hud); letter-spacing:.04em; color:#eef3ff; text-decoration:none; margin-right:auto; }
.appbar .brand i { color:var(--ghost); font-style:normal; text-shadow:0 0 10px rgba(169,232,255,.6); }
.btn { display:inline-flex; align-items:center; justify-content:center; gap:8px; font:700 15px/1 var(--hud); letter-spacing:.04em;
  color:#070b14; background:var(--me); border:0; border-radius:10px; padding:11px 16px; text-decoration:none; cursor:pointer; white-space:nowrap;
  text-transform:uppercase; }
.btn.quiet { background:rgba(238,243,255,.10); color:#eef3ff; }
.btn.big { font-size:18px; padding:15px 24px; }
.btn.line { background:transparent; color:var(--ink); box-shadow:inset 0 0 0 2px var(--line); }
.hero.short { padding-bottom:70px; }
.hero .btn.big { margin-top:20px; }
.form { display:flex; flex-direction:column; gap:14px; }
.form p { margin:0; color:var(--muted); font:500 15.5px/1.45 var(--body); }
.drop { position:relative; display:grid; place-items:center; gap:4px; text-align:center; min-height:150px; padding:18px; border-radius:16px;
  border:2px dashed color-mix(in srgb, var(--ink) 26%, transparent); background:var(--soft); cursor:pointer; }
.drop input { position:absolute; inset:0; width:100%; height:100%; opacity:0; cursor:pointer; }
.drop .what { font:700 17px/1.3 var(--hud); }
.drop .hint { font:500 13px/1.3 var(--body); color:var(--muted); }
.drop .name { font:700 22px/1.1 var(--hud); color:var(--me); word-break:break-all; }
.drop.has { border-style:solid; border-color:var(--me); }
.drop.has .what, .drop.has .hint { display:none; }
.field { display:flex; flex-direction:column; gap:6px; font:700 12.5px/1.2 var(--hud); letter-spacing:.12em; text-transform:uppercase; color:var(--muted); }
.field select { font:500 16px/1.2 var(--body); color:var(--ink); background:var(--card); border:1px solid var(--line); border-radius:10px; padding:11px 12px; }
.steps { list-style:none; margin:0; padding:0; display:grid; gap:12px; font:600 18px/1.3 var(--hud); }
.steps li { display:flex; gap:12px; align-items:center; color:var(--muted); opacity:.55; }
.steps li::before { content:""; width:22px; height:22px; border-radius:50%; border:3px solid var(--line); flex:none; }
.steps li.done { color:var(--ink); opacity:1; } .steps li.done::before { background:var(--back); border-color:var(--back); }
.steps li.now { color:var(--ink); opacity:1; } .steps li.now::before { border-color:var(--ghost) var(--ghost) var(--line) var(--line); animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
.tiles { list-style:none; margin:0; padding:0; display:grid; gap:12px; grid-template-columns:repeat(auto-fill, minmax(min(100%, 300px), 1fr)); }
.tile a { display:block; text-decoration:none; color:inherit; padding:14px 16px; border-radius:16px; background:var(--card); border:1px solid var(--line);
  box-shadow:0 12px 28px -22px rgba(7,11,20,.6); }
.tile .k { font:700 12px/1.2 var(--hud); letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
.tile .t { font:700 22px/1.15 var(--hud); margin:6px 0 4px; text-transform:uppercase; }
.tile .t b { color:var(--face); } .tile.gave .t b { color:var(--back); } .tile.calm .t b { color:var(--muted); }
.tile .s { font:500 14px/1.35 var(--body); color:var(--muted); }
.tile.running .t, .tile.failed .t { color:var(--muted); }
.about { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.about form { margin-left:auto; }
.chip { font:600 13.5px/1.25 var(--hud); padding:7px 12px 6px; border-radius:10px; background:var(--soft); border:1px solid var(--line); }
.error { font:600 17px/1.4 var(--body); }
@media (max-width:520px) { .appbar .btn.quiet { display:none; } .appbar .brand { font-size:19px; } }
"""

FOOTER = ("<footer><b>wasitthewind</b>Runs on this machine: the rides you drop stay in its data folder; only the wind "
          "request (0.1° blocks around a ride and its date) goes out. Built with PriorLabs-TabPFN · wind: Open-Meteo "
          "(CC BY 4.0), Météo-France AROME and ECMWF IFS · fonts: Chakra Petch (OFL).</footer>")


# ------------------------------------------------------------------ the analyses on disk


class Store:
    """One folder per analysis under `root/analyses/<id>/`."""

    def __init__(self, root: str | Path):
        self.root = Path(root) / "analyses"
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def folder(self, aid: str) -> Path:
        if not ID.fullmatch(aid or ""):
            raise KeyError(aid)
        return self.root / aid

    def create(self, filename: str, data: bytes, params: dict) -> dict:
        aid = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
        f = self.folder(aid)
        (f / "in").mkdir(parents=True)
        name = safe_name(filename)
        (f / "in" / name).write_bytes(data)
        meta = {"id": aid, "file": name, "params": params, "status": "queued", "step": 0,
                "created": datetime.now(timezone.utc).isoformat(timespec="microseconds")}
        self.save(meta)
        return meta

    def save(self, meta: dict) -> None:
        f = self.folder(meta["id"])
        tmp = f / "meta.json.tmp"
        tmp.write_text(json.dumps(meta, indent=1), encoding="utf-8")
        tmp.replace(f / "meta.json")

    def get(self, aid: str) -> dict | None:
        try:
            return json.loads((self.folder(aid) / "meta.json").read_text(encoding="utf-8"))
        except (KeyError, OSError, ValueError):
            return None

    def update(self, aid: str, **fields) -> dict:
        with self.lock:
            meta = self.get(aid)
            if meta is None:
                raise KeyError(aid)
            meta.update(fields)
            self.save(meta)
            return meta

    def all(self) -> list[dict]:
        out = [m for m in (self.get(p.name) for p in self.root.iterdir() if p.is_dir()) if m]
        return sorted(out, key=lambda m: (m.get("ride_start", 0) or 0, m["created"]), reverse=True)

    def delete(self, aid: str) -> None:
        shutil.rmtree(self.folder(aid), ignore_errors=True)


def safe_name(filename: str) -> str:
    base = Path((filename or "").replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip(".-") or "upload"
    return base[-80:]


def is_fit(data: bytes) -> bool:
    return len(data) >= 12 and data[8:12] == b".FIT"


# ------------------------------------------------------------------ one analysis


@dataclass
class Settings:
    cache: str
    library: str | None = None
    tz: str = "Europe/Paris"
    mass_kg: float | None = None  # only for the physics lines of the range; kept in memory
    wind_models: tuple = ("meteofrance_arome_france_hd", "ecmwf_ifs")
    fetch: object = None  # tests answer the wind requests themselves


def _context(store: Store, settings: Settings, exclude: str):
    from .ride import RideSeries

    out = []
    for m in store.all():
        p = store.folder(m["id"]) / "series.npz"
        if m["id"] != exclude and m.get("status") == "done" and p.exists():
            out.append(RideSeries.load(p))
    if settings.library:
        for p in sorted(Path(settings.library).glob("*.npz")):
            if not p.name.endswith(".track.npz"):
                rs = RideSeries.load(p)
                if all(abs(rs.start_epoch - o.start_epoch) > 60 for o in out):
                    out.append(rs)
    return out


def run(store: Store, aid: str, settings: Settings, make=None) -> dict:
    """One analysis, from the file dropped to its page."""
    from zoneinfo import ZoneInfo

    from . import analysis, page, wind
    from .physics import Bike, Rider

    meta = store.update(aid, status="running", step=0, error=None)
    folder = store.folder(aid)
    src = folder / "in" / meta["file"]
    store.update(aid, step=1)
    rs, (lat, lon) = analysis.prepare(src, settings.cache, wind_models=settings.wind_models, fetch=settings.fetch)
    rs.name = aid
    # the same ride dropped twice never learns from itself
    others = [o for o in _context(store, settings, aid) if abs(o.start_epoch - rs.start_epoch) > 60]
    if len(others) < 2:
        raise ValueError("the ghost learns you from your other rides: add at least two more rides with power first")
    rs.save(folder / "series.npz")
    np.savez_compressed(folder / "track.npz", lat=lat, lon=lon)
    store.update(aid, step=2, ride_start=rs.start_epoch, moving_s=float(rs.moving.sum()))
    rider = Rider(mass_kg=settings.mass_kg, bike=Bike()) if settings.mass_kg else None
    v = analysis.judge(rs, others, make=make, rider=rider)
    store.update(aid, step=3)
    compare = None
    other_id = meta["params"].get("compare")
    if other_id and (om := store.get(other_id)) and om.get("status") == "done":
        compare = {"label": when(om["ride_start"], ZoneInfo(settings.tz)), "this_s": v.headline.rider_total_s,
                   "other_s": om["result"]["rider_s"], "this_gap_s": v.gap_s, "other_gap_s": om["result"]["gap_s"]}
    lo, hi = v.range_s
    result = {"gap_s": v.gap_s, "lo_s": lo, "hi_s": hi, "rider_s": v.headline.rider_total_s,
              "ghost_s": v.headline.ghost_total_s, "mean_wind10": v.mean_wind10, "variants": v.variants,
              "worst": [s.__dict__ for s in v.worst], "best": [s.__dict__ for s in v.best], "context_rides": len(others)}
    (folder / "result.json").write_text(json.dumps(result, indent=1))
    html_text = page.result_page(v, rs, lat, lon, wind.rider_height_factor(), title=meta["params"].get("name") or "Ride",
                                 compare=compare, tz=ZoneInfo(settings.tz))
    (folder / "page.html").write_text(html_text, encoding="utf-8")
    return store.update(aid, status="done", step=len(STEPS), result=result)


def friendly(ex: Exception) -> str:
    msg = str(ex) or ex.__class__.__name__
    if "urlopen" in msg or "HTTP Error" in msg or "timed out" in msg:
        return "The weather archive didn't answer (Open-Meteo). Try again in a minute."
    return msg[:1].upper() + msg[1:]


class Analyst:
    """Runs the analyses one at a time in a background thread."""

    def __init__(self, store: Store, settings: Settings, make=None):
        self.store, self.settings, self.make = store, settings, make
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=self._loop, daemon=True).start()
        for m in reversed(store.all()):  # interrupted by a restart: run them again
            if m["status"] in ("queued", "running"):
                self.q.put(m["id"])

    def submit(self, aid: str) -> None:
        self.q.put(aid)

    def stop(self) -> None:
        self.q.put(None)

    def _loop(self) -> None:
        while (aid := self.q.get()) is not None:
            try:
                run(self.store, aid, self.settings, self.make)
            except Exception as ex:
                if self.store.get(aid):
                    self.store.update(aid, status="failed", error=friendly(ex))


# ------------------------------------------------------------------ pages


def document(title: str, body: str, refresh: bool = False) -> str:
    csp = (f"default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; "
           f"script-src 'sha256-{SCRIPT_HASH}'; form-action 'self'; base-uri 'none'")
    return (f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">"
            f"<meta http-equiv=\"Content-Security-Policy\" content=\"{csp}\">"
            + ("<meta http-equiv=\"refresh\" content=\"2\">" if refresh else "")
            + f"<meta name=\"theme-color\" content=\"#070b14\"><title>{e(title)}</title>"
            f"<style>{fonts_css()}{CSS}{APP_CSS}</style></head><body>{appbar()}{body}{FOOTER}"
            f"<script>{SCRIPT}</script></body></html>\n")


def appbar() -> str:
    return ('<nav class="appbar"><a class="brand" href="/">was<i>it</i>the<i>wind</i></a>'
            '<a class="btn quiet" href="/">Your races</a><a class="btn" href="/new">New analysis</a></nav>')


def short_hero(kicker: str, title: str, sub: str) -> str:
    return (f'<header class="hero short"><div class="wrap"><div class="kicker">{e(kicker)}</div><h1>{title}</h1>'
            f'<p class="sub">{sub}</p></div></header>')


def _tz(settings: Settings):
    from zoneinfo import ZoneInfo

    return ZoneInfo(settings.tz)


def tile(meta: dict, settings: Settings) -> str:
    st = meta.get("status")
    day = when(meta["ride_start"], _tz(settings)) if meta.get("ride_start") else meta["file"]
    if st == "done":
        r = meta["result"]
        kind, _, _ = verdict_words(r["gap_s"], r["lo_s"], r["hi_s"], r["rider_s"])
        title = {"calm": "Not the wind", "cost": f"Wind cost <b>{mmss(r['gap_s'])}</b>",
                 "gave": f"Wind gave <b>{mmss(-r['gap_s'])}</b>"}[kind]
        sub = f"{hm(r['rider_s'])} moving · ghost {hm(r['ghost_s'])} · range {mmss(r['lo_s'], True)} to {mmss(r['hi_s'], True)}"
    elif st == "failed":
        kind, title, sub = "failed", "Not analysed", e(meta.get("error") or "")
    else:
        kind, title, sub = "running", "Racing…", "the ghost is on its way"
    return (f'<li class="tile {kind}"><a href="/a/{meta["id"]}"><div class="k">{e(day)}</div><div class="t">{title}</div>'
            f'<div class="s">{sub}</div></a></li>')


def home_page(store: Store, settings: Settings) -> str:
    items = store.all()
    head = short_hero("Was it really the wind?", "Race your ghost",
                      "Drop a ride: the same ride comes back without the wind, at the same power, and races you. "
                      "The gap at the finish is what the wind cost or gave."
                      '<br><a class="btn big" href="/new">New analysis</a>')
    if not items:
        body = '<section class="card"><p class="note">No race yet. Each ride you add also teaches the ghost how you ride.</p></section>'
    else:
        body = f'<section aria-label="Your races"><ul class="tiles">{"".join(tile(m, settings) for m in items)}</ul></section>'
    return document("wasitthewind", f'{head}<main class="wrap">{body}</main>')


def new_page(store: Store, settings: Settings, token: str) -> str:
    done = [m for m in store.all() if m.get("status") == "done"]
    opts = '<option value="">No comparison</option>' + "".join(
        f'<option value="{e(m["id"])}">{e(when(m["ride_start"], _tz(settings)))} · {hm(m["result"]["rider_s"])}</option>'
        for m in done)
    head = short_hero("New analysis", "Drop a ride", "The original FIT file of your bike computer, with power.")
    form = (f'<section class="card"><form class="form" method="post" action="/new" enctype="multipart/form-data">'
            f'<input type="hidden" name="token" value="{e(token)}">'
            f'<label class="drop"><input type="file" name="file" accept=".fit,.FIT" required>'
            f'<span class="what">Choose or drop a FIT file</span><span class="hint">Outdoors, with a power meter. It stays on this machine.</span>'
            f'<span class="name"></span></label>'
            f'<label class="field">Compare with an earlier ride on the same road<select name="compare">{opts}</select></label>'
            f'<p>The wind is asked for on 0.1° blocks around the ride, for its date: that request is all that leaves this machine.</p>'
            f'<button class="btn big" type="submit">Race my ghost</button></form></section>')
    return document("wasitthewind · new analysis", f'{head}<main class="wrap">{form}</main>')


def progress_page(meta: dict) -> str:
    k = int(meta.get("step", 0))
    items = "".join(f'<li class="{"done" if i < k else "now" if i == k else ""}">{e(s)}</li>' for i, s in enumerate(STEPS))
    head = short_hero(meta["file"], "Racing…", "Your ghost is warming up.")
    body = (f'{head}<main class="wrap"><section class="card"><h2>A few minutes on a small CPU</h2><ol class="steps">{items}</ol>'
            f'<p class="note">This page follows the analysis and opens the race by itself.</p></section></main>')
    return document("wasitthewind · racing", body, refresh=True)


def failed_page(meta: dict, token: str) -> str:
    head = short_hero(meta["file"], "Not analysed", "")
    body = (f'{head}<main class="wrap"><section class="card"><p class="error">{e(meta.get("error") or "Something went wrong.")}</p>'
            f'<div class="about" style="margin-top:14px"><a class="btn" href="/new">Try another file</a>{delete_form(meta, token)}</div>'
            f'</section></main>')
    return document("wasitthewind · not analysed", body)


def delete_form(meta: dict, token: str) -> str:
    return (f'<form method="post" action="/a/{meta["id"]}/delete"><input type="hidden" name="token" value="{e(token)}">'
            f'<button class="btn line" type="submit">Delete</button></form>')


def result_page(store: Store, meta: dict, token: str) -> str:
    """The analysis's own page, with the app's bar on top and what it was made from at the bottom."""
    text = (store.folder(meta["id"]) / "page.html").read_text(encoding="utf-8")
    n = meta.get("result", {}).get("context_rides", 0)
    about = (f'<section class="card about"><span class="chip">{e(meta["file"])}</span>'
             f'<span class="chip">ghost learned from {n} other rides</span>{delete_form(meta, token)}</section>')
    text = text.replace("</style>", APP_CSS + "</style>", 1)
    text = text.replace("<body>", "<body>" + appbar(), 1)
    return text.replace("</main>", about + "</main>", 1)


# ------------------------------------------------------------------ the server


def parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    """Fields and files of a multipart/form-data body, as browsers send it."""
    m = re.search(r'boundary="?([^";]+)"?', content_type or "")
    if not m or not content_type.lower().startswith("multipart/form-data"):
        raise ValueError("expected a form with a file")
    sep = b"--" + m.group(1).encode("latin-1")
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for chunk in body.split(sep)[1:]:
        if chunk.startswith(b"--"):
            break
        head, _, data = chunk.partition(b"\r\n\r\n")
        if data.endswith(b"\r\n"):
            data = data[:-2]
        disp = next((ln for ln in head.decode("utf-8", "replace").split("\r\n")
                     if ln.lower().startswith("content-disposition:")), "")
        name = re.search(r';\s*name="([^"]*)"', disp)
        if not name:
            continue
        filename = re.search(r';\s*filename="([^"]*)"', disp)
        if filename is not None:
            files[name.group(1)] = (filename.group(1), data)
        else:
            fields[name.group(1)] = data.decode("utf-8", "replace")
    return fields, files


class App:
    def __init__(self, store: Store, settings: Settings, make=None):
        self.store, self.settings = store, settings
        self.token = secrets.token_urlsafe(16)
        self.analyst = Analyst(store, settings, make)

    def stop(self) -> None:
        self.analyst.stop()

    def new(self, fields: dict, files: dict) -> dict:
        """Check the form and queue the analysis; a ValueError says what is wrong with it."""
        filename, data = files.get("file", ("", b""))
        if not data:
            raise ValueError("no file came with the form")
        if not is_fit(data):
            raise ValueError(f"{filename} is not a FIT file")
        params = {}
        other = fields.get("compare", "").strip()
        if other:
            om = self.store.get(other)
            if not om or om.get("status") != "done":
                raise ValueError("the ride to compare with is not there any more")
            params["compare"] = other
        meta = self.store.create(filename, data, params)
        self.analyst.submit(meta["id"])
        return meta


def make_server(app: App, host: str = "127.0.0.1", port: int = 8766) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "wasitthewind"

        def log_message(self, fmt, *args):
            pass

        def _send(self, code: int, text: str = "", location: str | None = None) -> None:
            data = text.encode("utf-8")
            self.send_response(code)
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def _oops(self, code: int, title: str, msg: str) -> None:
            body = (f'{short_hero("wasitthewind", e(title), "")}<main class="wrap"><section class="card"><p class="error">{e(msg)}</p>'
                    f'<a class="btn" href="/new">New analysis</a> <a class="btn line" href="/">Your races</a></section></main>')
            self._send(code, document(f"wasitthewind · {title}", body))

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/":
                return self._send(200, home_page(app.store, app.settings))
            if path == "/new":
                return self._send(200, new_page(app.store, app.settings, app.token))
            m = re.fullmatch(r"/a/([0-9a-f-]+)", path)
            if m and (meta := app.store.get(m.group(1))):
                if meta["status"] == "done":
                    return self._send(200, result_page(app.store, meta, app.token))
                if meta["status"] == "failed":
                    return self._send(200, failed_page(meta, app.token))
                return self._send(200, progress_page(meta))
            if path == "/favicon.ico":
                self.send_response(204)
                return self.end_headers()
            return self._oops(404, "Not found", "There is no such page, or that analysis was deleted.")

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                size = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                size = -1
            if size < 0 or size > MAX_UPLOAD:
                self.close_connection = True
                return self._oops(413, "Too big", f"Files up to {MAX_UPLOAD // 2 ** 20} MB.")
            body = self.rfile.read(size)
            try:
                fields, files = parse_multipart(self.headers.get("Content-Type", ""), body)
            except ValueError:
                fields, files = {}, {}
                if self.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded"):
                    from urllib.parse import parse_qs

                    fields = {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace")).items()}
            if not secrets.compare_digest(fields.get("token", ""), app.token):
                return self._oops(403, "Expired form", "This form comes from an older page: open it again and retry.")
            if path == "/new":
                try:
                    meta = app.new(fields, files)
                except ValueError as ex:
                    return self._oops(400, "Not analysed", friendly(ex))
                return self._send(303, "", location=f"/a/{meta['id']}")
            m = re.fullmatch(r"/a/([0-9a-f-]+)/delete", path)
            if m and app.store.get(m.group(1)):
                app.store.delete(m.group(1))
                return self._send(303, "", location="/")
            return self._oops(404, "Not found", "There is no such page, or that analysis was deleted.")

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd
