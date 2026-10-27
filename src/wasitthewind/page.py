"""The result page: a night race against your own ghost.

One HTML file, nothing loaded from anywhere: the fonts (Chakra Petch, SIL
Open Font License) travel inside the page, the charts are inline SVG, and the
two dots race with SVG's own animation, no script. Every figure drawn along
the ride (the map, the delta, the wind band) leaves out its first and last
2 km, so a screenshot doesn't show where a ride starts or ends; the numbers
still count the whole ride.
"""

from __future__ import annotations

import base64
import html
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources

import numpy as np

from .geo import trim_mask

ENDS_M = 2000.0
CREDITS = ("Built with PriorLabs-TabPFN · wind: Open-Meteo, Météo-France AROME and ECMWF IFS models (CC BY 4.0) · "
           "fonts: Chakra Petch (SIL Open Font License)")
FACES = (("Chakra Petch", 500, "ChakraPetch-500.woff2"), ("Chakra Petch", 700, "ChakraPetch-700.woff2"))
RACE_S = 24.0  # the dots' race lasts this long on screen
e = html.escape


@lru_cache(maxsize=1)
def fonts_css() -> str:
    out = []
    for family, weight, name in FACES:
        data = resources.files("wasitthewind").joinpath("static", "fonts", name).read_bytes()
        out.append(f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;font-display:swap;"
                   f"src:url(data:font/woff2;base64,{base64.b64encode(data).decode()}) format('woff2')}}")
    return "\n".join(out)


CSS = """
/* A night ride: deep ink, a warm rider, a pale ghost; the wind in the face is ember, at the back it is sea-green. */
:root { --night:#070b14; --night2:#0e1526; --paper:#f2f3f6; --card:#ffffff; --ink:#0d1220; --muted:#5b6478;
  --line:rgba(13,18,32,.10); --soft:rgba(13,18,32,.045);
  --me:#ffb238; --ghost:#a9e8ff; --face:#ff6a3d; --back:#2ec4a6; --calm:#8a93a8;
  --hud:"Chakra Petch","Arial Narrow",system-ui,sans-serif;
  --body:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; color-scheme:light; }
@media (prefers-color-scheme: dark) { :root { --paper:#05080f; --card:#0d1424; --ink:#e9edf5; --muted:#949db3;
  --line:rgba(233,237,245,.10); --soft:rgba(233,237,245,.045); color-scheme:dark; } }
* { box-sizing:border-box; }
html { -webkit-text-size-adjust:100%; }
body { margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 var(--body); }
.hero { position:relative; overflow:hidden; color:#eef3ff; padding:max(24px, env(safe-area-inset-top)) 0 76px;
  background:radial-gradient(120% 70% at 80% 0%, rgba(169,232,255,.18), transparent 60%),
    radial-gradient(90% 60% at 10% 100%, rgba(255,178,56,.12), transparent 60%),
    linear-gradient(180deg, var(--night) 0%, var(--night2) 100%); }
.hero::after { content:""; position:absolute; inset:auto -10% -30px -10%; height:120px; pointer-events:none;
  background:radial-gradient(60% 100% at 30% 100%, rgba(200,225,255,.10), transparent 70%),
    radial-gradient(50% 100% at 75% 100%, rgba(200,225,255,.08), transparent 70%); filter:blur(6px); }
.wrap { max-width:1020px; margin:0 auto; padding:0 max(16px, env(safe-area-inset-right)) 0 max(16px, env(safe-area-inset-left)); }
.kicker { font:700 12.5px/1.3 var(--hud); letter-spacing:.18em; text-transform:uppercase; color:rgba(238,243,255,.62); }
.hero h1 { font:700 clamp(34px, 8.4vw, 64px)/1.02 var(--hud); margin:.22em 0 .2em; letter-spacing:.01em; text-transform:uppercase; text-wrap:balance; }
.hero h1 .delta { color:var(--me); white-space:nowrap; }
.hero h1 .delta.gave { color:var(--back); }
.hero .sub { font:500 clamp(15px, 3.6vw, 18px)/1.4 var(--hud); color:rgba(238,243,255,.80); max-width:46em; }
.hud { display:flex; flex-wrap:wrap; gap:10px 26px; margin-top:20px; }
.hud div { font:500 12px/1.2 var(--hud); letter-spacing:.14em; text-transform:uppercase; color:rgba(238,243,255,.55); }
.hud b { display:block; font:700 clamp(26px, 6vw, 36px)/1 var(--hud); letter-spacing:.02em; color:#eef3ff; margin-top:4px;
  font-variant-numeric:tabular-nums; }
.hud .me b { color:var(--me); } .hud .gh b { color:var(--ghost); text-shadow:0 0 12px rgba(169,232,255,.55); }
main { position:relative; z-index:2; margin-top:-52px; padding-bottom:36px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:18px; padding:18px; margin:0 0 14px;
  box-shadow:0 14px 34px -22px rgba(7,11,20,.55); }
.card.dark { background:linear-gradient(180deg, #0b1220, #0e1729); color:#e9edf5; border-color:rgba(169,232,255,.12); }
h2 { font:700 13px/1.2 var(--hud); letter-spacing:.16em; text-transform:uppercase; color:var(--muted); margin:2px 0 14px; }
.card.dark h2 { color:rgba(233,237,245,.6); }
.race svg { width:100%; height:auto; display:block; }
.legend { display:flex; flex-wrap:wrap; gap:6px 18px; font:600 13.5px/1.3 var(--hud); margin-top:10px; color:var(--muted); }
.card.dark .legend { color:rgba(233,237,245,.7); }
.legend i { display:inline-block; width:11px; height:11px; border-radius:50%; margin-right:7px; vertical-align:-1px; }
.chart { position:relative; height:clamp(150px, 36vw, 210px); margin:4px 0 0 40px; }
.chart svg { position:absolute; inset:0; width:100%; height:100%; overflow:visible; }
.ylab { position:absolute; left:-40px; transform:translateY(-50%); font:600 11.5px/1 var(--hud); color:var(--muted); }
.xaxis { position:relative; height:18px; margin:4px 0 0 40px; }
.xaxis span { position:absolute; transform:translateX(-50%); font:600 11.5px/1 var(--hud); color:var(--muted); font-variant-numeric:tabular-nums; }
.band { position:relative; height:14px; margin:10px 0 0 40px; border-radius:4px; overflow:hidden; background:var(--soft); }
.band i { position:absolute; top:0; bottom:0; }
.stretches { list-style:none; margin:0; padding:0; display:grid; gap:10px; grid-template-columns:repeat(auto-fill, minmax(min(100%, 280px), 1fr)); }
.stretch { display:grid; grid-template-columns:auto 1fr auto; gap:2px 12px; align-items:center; padding:12px 14px; border-radius:14px;
  background:var(--soft); border:1px solid var(--line); }
.stretch .n { width:30px; height:30px; border-radius:8px; display:grid; place-items:center; font:700 16px/1 var(--hud); background:var(--face); color:#fff; }
.stretch.gave .n { background:var(--back); }
.stretch .where { font:700 16px/1.2 var(--hud); }
.stretch .what { font:500 13.5px/1.3 var(--body); color:var(--muted); grid-column:2; }
.stretch .cost { grid-row:1 / 3; grid-column:3; text-align:right; }
.stretch .cost b { display:block; font:700 28px/.95 var(--hud); color:var(--face); font-variant-numeric:tabular-nums; }
.stretch.gave .cost b { color:var(--back); }
.stretch .cost small { font:600 11px/1.2 var(--hud); color:var(--muted); text-transform:uppercase; letter-spacing:.08em; }
.range { display:grid; gap:8px; }
.range .row { display:grid; grid-template-columns:minmax(0, 15em) 1fr 4.6em; gap:10px; align-items:center; font:500 14px/1.3 var(--body); }
.range .row b { font:700 15px/1 var(--hud); text-align:right; font-variant-numeric:tabular-nums; }
.range .bar { position:relative; height:12px; background:var(--soft); border-radius:6px; }
.range .bar::before { content:""; position:absolute; left:50%; top:-3px; bottom:-3px; border-left:1px dashed var(--muted); }
.range .bar i { position:absolute; top:0; bottom:0; border-radius:6px; }
.range .row.head { font-weight:700; }
.note { font:500 13.5px/1.45 var(--body); color:var(--muted); margin:12px 0 0; }
.card.dark .note { color:rgba(233,237,245,.62); }
.compare { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.compare div { padding:12px 14px; border-radius:14px; background:var(--soft); border:1px solid var(--line); }
.compare b { display:block; font:700 30px/1 var(--hud); font-variant-numeric:tabular-nums; margin-top:4px; }
.compare span { font:600 12px/1.2 var(--hud); text-transform:uppercase; letter-spacing:.1em; color:var(--muted); }
.compare p { grid-column:1 / -1; margin:2px 0 0; color:var(--muted); font-size:15px; }
.compare p strong { color:var(--ink); }
footer { max-width:1020px; margin:0 auto; padding:6px max(16px, env(safe-area-inset-right)) max(28px, env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left));
  font:500 12.5px/1.5 var(--body); color:var(--muted); }
footer b { font:700 18px/1 var(--hud); color:var(--ink); letter-spacing:.04em; display:block; margin-bottom:6px; }
@media (max-width:520px) { .range .row { grid-template-columns:1fr 4.2em; } .range .row .bar { grid-column:1 / -1; grid-row:2; } }
@media (prefers-reduced-motion: reduce) { .race animateMotion { display:none; } }
"""


def document(title: str, body: str, extra_css: str = "") -> str:
    return (f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">"
            f"<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:\">"
            f"<meta name=\"theme-color\" content=\"#070b14\"><title>{e(title)}</title>"
            f"<style>{fonts_css()}{CSS}{extra_css}</style></head><body>{body}"
            f"<footer><b>wasitthewind</b>{e(CREDITS)}<br>The wind is rebuilt from weather models, not measured on the bike. "
            f"A finding about a ride already ridden, not training advice.</footer></body></html>\n")


# ------------------------------------------------------------------ words and numbers


def mmss(seconds: float, sign: bool = False) -> str:
    s = int(round(abs(seconds)))
    txt = f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
    if sign:
        txt = ("+" if seconds >= 0 else "−") + txt
    return txt


def hm(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


def kmh(ms: float) -> str:
    return f"{3.6 * ms:.0f} km/h"


def km(m: float) -> str:
    return f"{m / 1000:.1f}"


def verdict_words(gap_s: float, lo_s: float, hi_s: float, ride_s: float) -> tuple[str, str, str]:
    """(kind, headline html, one sentence) for a gap and its range."""
    small = max(30.0, 0.005 * ride_s)
    if abs(gap_s) < small and lo_s < small and hi_s > -small:
        where = ("level with you" if abs(gap_s) < 1 else
                 f"{mmss(abs(gap_s))} {'ahead of' if gap_s > 0 else 'behind'} you")
        return "calm", "It wasn't the wind", (f"Your ghost, same legs and no wind, finishes {where}, and every other "
                                              f"way of counting within {mmss(max(abs(lo_s), abs(hi_s)))}: "
                                              "the wind barely touched this ride.")
    if gap_s > 0:
        sure = "" if lo_s > 0 else " The range crosses zero, so take it as a lean, not a verdict."
        return ("cost", f"The wind cost you <span class=\"delta\">{mmss(gap_s)}</span>",
                f"Your ghost, same legs and no wind, finishes {mmss(gap_s)} ahead of you "
                f"(somewhere between {mmss(max(lo_s, 0))} and {mmss(hi_s)}).{sure}")
    sure = "" if hi_s < 0 else " The range crosses zero, so take it as a lean, not a verdict."
    return ("gave", f"The wind gave you <span class=\"delta gave\">{mmss(-gap_s)}</span>",
            f"Your ghost, same legs and no wind, finishes {mmss(-gap_s)} behind you "
            f"(somewhere between {mmss(max(-hi_s, 0))} and {mmss(-lo_s)}).{sure}")


# ------------------------------------------------------------------ drawing


def _project(lat, lon, w=1000.0, pad=24.0):
    lat0 = float(np.nanmean(lat))
    x = np.asarray(lon) * np.cos(np.radians(lat0))
    y = -np.asarray(lat, dtype=float)
    x0, x1, y0, y1 = np.nanmin(x), np.nanmax(x), np.nanmin(y), np.nanmax(y)
    span = max(x1 - x0, y1 - y0, 1e-9)
    s = (w - 2 * pad) / span
    h = (y1 - y0) * s + 2 * pad
    return (x - x0) * s + pad, (y - y0) * s + pad, w, h


def race_map(lat, lon, dist, cumulative, keep) -> str:
    """The trimmed track with two dots: the rider and the ghost, racing over `RACE_S` seconds.

    `cumulative` is the ghost's table (`Ghost.cumulative()`): distances at
    chunk ends, and the rider's and the ghost's times there.
    """
    idx = np.flatnonzero(keep)
    if idx.size < 10:
        return ""
    step = max(1, idx.size // 900)
    pts = idx[::step]
    x, y, w, h = _project(lat[pts], lon[pts])
    path = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in zip(x, y))
    d_pts = dist[pts]
    d0, d1 = d_pts[0], d_pts[-1]
    d_end, tr_end, tg_end = cumulative
    # time each racer reaches each drawn point, counted from the first drawn point
    tr = np.interp(d_pts, d_end, tr_end)
    tg = np.interp(d_pts, d_end, tg_end)
    tr, tg = tr - tr[0], tg - tg[0]
    total = max(tr[-1], tg[-1], 1e-9)
    frac = (d_pts - d0) / max(d1 - d0, 1e-9)

    def motion(t):
        n = 60
        kt = np.linspace(0, t[-1] / total, n)
        kp = np.interp(kt * total, t, frac)
        if kt[-1] < 0.999:
            kt = np.append(kt, 1.0)
            kp = np.append(kp, 1.0)
        kt[0], kt[-1] = 0.0, 1.0
        return ";".join(f"{v:.4f}" for v in kt), ";".join(f"{v:.4f}" for v in np.clip(kp, 0, 1))

    ktr, kpr = motion(tr)
    ktg, kpg = motion(tg)
    dur = f"{RACE_S:.0f}s"
    anim = 'calcMode="linear" repeatCount="indefinite" rotate="0"'
    return (f'<svg viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="The ride and its ghost, racing">'
            f'<defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5"/></filter>'
            f'<path id="route" d="{path}"/></defs>'
            f'<use href="#route" fill="none" stroke="rgba(233,237,245,.10)" stroke-width="12" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<use href="#route" fill="none" stroke="rgba(233,237,245,.55)" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<g><circle r="13" style="fill:var(--ghost)" opacity=".35" filter="url(#glow)"/><circle r="7" style="fill:var(--ghost)" opacity=".8"/>'
            f'<animateMotion dur="{dur}" {anim} keyTimes="{ktg}" keyPoints="{kpg}"><mpath href="#route"/></animateMotion></g>'
            f'<g><circle r="8" style="fill:var(--me)" stroke="#070b14" stroke-width="2.5"/>'
            f'<animateMotion dur="{dur}" {anim} keyTimes="{ktr}" keyPoints="{kpr}"><mpath href="#route"/></animateMotion></g>'
            f'</svg>')


def _area(xs, ys, x0, x1, y0, y1):
    sx = lambda v: 100 * (v - x0) / max(x1 - x0, 1e-9)  # noqa: E731
    sy = lambda v: 100 * (y1 - v) / max(y1 - y0, 1e-9)  # noqa: E731
    return " ".join(f"{sx(a):.2f},{sy(b):.2f}" for a, b in zip(xs, ys)), sy


def delta_chart(dist_km, lead_m) -> str:
    """The ghost's lead along the ride (metres): above the line it is ahead, below it is behind."""
    if len(dist_km) < 3:
        return ""
    lo, hi = min(0.0, float(np.min(lead_m))), max(0.0, float(np.max(lead_m)))
    pad = max(10.0, 0.1 * (hi - lo))
    lo, hi = lo - pad, hi + pad
    x0, x1 = float(dist_km[0]), float(dist_km[-1])
    pts, sy = _area(dist_km, lead_m, x0, x1, lo, hi)
    z = sy(0.0)
    poly = f"0,{z:.2f} {pts} 100,{z:.2f}"
    ticks = _ticks(lo + pad, hi - pad)
    ylabs = "".join(f'<span class="ylab" style="top:{sy(t):.1f}%">{t:+.0f} m</span>' for t in ticks)
    return (f'<div class="chart">{ylabs}<svg viewBox="0 0 100 100" preserveAspectRatio="none">'
            f'<defs><clipPath id="up"><rect x="0" y="0" width="100" height="{z:.2f}"/></clipPath>'
            f'<clipPath id="dn"><rect x="0" y="{z:.2f}" width="100" height="{100 - z:.2f}"/></clipPath></defs>'
            f'<polygon points="{poly}" style="fill:var(--ghost)" opacity=".45" clip-path="url(#up)"/>'
            f'<polygon points="{poly}" style="fill:var(--me)" opacity=".55" clip-path="url(#dn)"/>'
            f'<line x1="0" x2="100" y1="{z:.2f}" y2="{z:.2f}" stroke="currentColor" stroke-opacity=".35" stroke-width=".6" vector-effect="non-scaling-stroke"/>'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="1.6" vector-effect="non-scaling-stroke"/>'
            f'</svg></div>{_xaxis(x0, x1)}')


def wind_band(dist_km, head_felt) -> str:
    """Headwind felt along the ride: ember in the face, sea-green at the back, grey when calm."""
    if len(dist_km) < 2:
        return ""
    x0, x1 = float(dist_km[0]), float(dist_km[-1])
    out = []
    for a, b, h in zip(dist_km[:-1], dist_km[1:], head_felt[:-1]):
        s = min(1.0, abs(h) / 3.0)
        col = "var(--face)" if h > 0.25 else ("var(--back)" if h < -0.25 else "var(--calm)")
        op = 0.25 + 0.75 * s if abs(h) > 0.25 else 0.25
        left = 100 * (a - x0) / max(x1 - x0, 1e-9)
        width = 100 * (b - a) / max(x1 - x0, 1e-9)
        out.append(f'<i style="left:{left:.2f}%;width:{width + 0.05:.2f}%;background:{col};opacity:{op:.2f}"></i>')
    return f'<div class="band">{"".join(out)}</div>'


def _ticks(lo, hi):
    span = max(hi - lo, 1e-9)
    step = 10 ** np.floor(np.log10(span / 2))
    for m in (1, 2, 5, 10):
        if span / (m * step) <= 4:
            step *= m
            break
    first = np.ceil(lo / step) * step
    return [float(v) for v in np.arange(first, hi + 1e-9, step)] or [0.0]


def _xaxis(x0, x1):
    n = 5
    vals = np.linspace(x0, x1, n)
    spans = "".join(f'<span style="left:{100 * (v - x0) / max(x1 - x0, 1e-9):.1f}%">{v:.0f} km</span>' for v in vals)
    return f'<div class="xaxis">{spans}</div>'


def range_rows(rows: list[tuple[str, float, bool]], span_s: float) -> str:
    """One bar per variant: the gap from the centre line, cost to the right."""
    span = max(span_s, 1.0)
    out = []
    for label, gap, head in rows:
        x = 50 + 50 * max(-1.0, min(1.0, gap / span))
        left, width = (50, x - 50) if gap >= 0 else (x, 50 - x)
        col = "var(--face)" if gap >= 0 else "var(--back)"
        out.append(f'<div class="row{" head" if head else ""}"><span>{e(label)}</span><div class="bar">'
                   f'<i style="left:{left:.1f}%;width:{max(width, 0.6):.1f}%;background:{col}"></i></div>'
                   f'<b>{mmss(gap, sign=True)}</b></div>')
    return f'<div class="range">{"".join(out)}</div>'


# ------------------------------------------------------------------ the page


VARIANT_LABELS = {
    "TabPFN, ecmwf_ifs": "TabPFN, ECMWF IFS wind",
    "physics ×0.54, meteofrance_arome_france_hd": "Physics, AROME, open country",
    "physics ×0.29, meteofrance_arome_france_hd": "Physics, AROME, maquis and villages",
    "physics ×0.54, ecmwf_ifs": "Physics, IFS, open country",
    "physics ×0.29, ecmwf_ifs": "Physics, IFS, maquis and villages",
}


def when(epoch: float, tz=None) -> str:
    d = datetime.fromtimestamp(epoch, tz or timezone.utc)
    return d.strftime("%a %d %b %Y").replace(" 0", " ")


def result_page(v, rs, lat, lon, felt_factor: float, title: str | None = None, compare=None, tz=None) -> str:
    """The page of one verdict (`analysis.Verdict`) with its series and positions."""
    g = v.headline
    lo, hi = v.range_s
    kind, headline, sentence = verdict_words(v.gap_s, lo, hi, g.rider_total_s)
    d_end, tr_end, tg_end = g.cumulative()
    # one-second distances of the ride for the trimmed figures
    keep = trim_mask(rs.dist, ENDS_M)
    lead = g.ghost_lead_m()
    keep_c = (d_end >= d_end[0] + ENDS_M) & (d_end <= d_end[-1] - ENDS_M)
    model = next(iter(rs.head10))
    head_felt_s = felt_factor * rs.head10.get("meteofrance_arome_france_hd", rs.head10[model])
    sec = np.flatnonzero(keep)[:: max(1, int(keep.sum() // 600))]
    band = wind_band(rs.dist[sec] / 1000, _smooth(head_felt_s, 60)[sec])
    race = race_map(lat, lon, rs.dist, (d_end, tr_end, tg_end), keep)
    gap_ahead = "ahead by" if v.gap_s > 0 else "behind by"
    hud = (f'<div class="hud"><div class="me">You<b>{hm(g.rider_total_s)}</b></div>'
           f'<div class="gh">Your ghost<b>{hm(g.ghost_total_s)}</b></div>'
           f'<div>Wind at 10 m<b>{kmh(v.mean_wind10)}</b></div>'
           f'<div>Your ghost, {gap_ahead}<b>{mmss(abs(v.gap_s))}</b></div></div>')
    body = [f'<header class="hero"><div class="wrap"><div class="kicker">{e(title or "Ride")} · {e(when(v.start_epoch, tz))}</div>'
            f'<h1>{headline}</h1><p class="sub">{e(sentence)}</p>{hud}</div></header><main class="wrap">']
    body.append(f'<section class="card dark race"><h2>The race</h2>{race}'
                f'<div class="legend"><span><i style="background:var(--me)"></i>You</span>'
                f'<span><i style="background:var(--ghost);box-shadow:0 0 8px var(--ghost)"></i>Your ghost: same power, no wind</span></div>'
                f'<p class="note">Both start together; the race is squeezed into {RACE_S:.0f} seconds. '
                f'The first and last 2 km are left off every figure.</p></section>')
    if keep_c.sum() > 3:
        body.append(f'<section class="card"><h2>Where the ghost was</h2>{delta_chart(d_end[keep_c] / 1000, lead[keep_c])}{band}'
                    f'<div class="legend"><span><i style="background:var(--ghost)"></i>Ghost ahead</span>'
                    f'<span><i style="background:var(--me)"></i>Ghost behind</span>'
                    f'<span><i style="background:var(--face)"></i>Wind in your face</span>'
                    f'<span><i style="background:var(--back)"></i>Wind at your back</span></div></section>')
    items = []
    for i, s in enumerate(v.worst, 1):
        items.append(_stretch_card(i, s, felt_factor, gave=False))
    for s in v.best[:1]:
        items.append(_stretch_card("+", s, felt_factor, gave=True))
    if items:
        body.append(f'<section class="card"><h2>Where the wind weighed</h2><ul class="stretches">{"".join(items)}</ul>'
                    f'<p class="note">Kilometres from the start. Headwind at 10 m from the AROME model; the rider, '
                    f'1.2 m above the road, feels about {felt_factor:.2f} of it.</p></section>')
    rows = [("TabPFN, AROME wind (headline)", v.gap_s, True)]
    rows += [(VARIANT_LABELS.get(k, k), x, False) for k, x in v.variants.items()]
    span = max(abs(x) for _, x, _ in rows) * 1.15 if rows else 60
    body.append(f'<section class="card"><h2>How sure</h2>{range_rows(rows, span)}'
                f'<p class="note">Each line replays the ride without the wind another way: another weather model, '
                f'or plain physics instead of TabPFN, with the wind reaching the rider in open country or among '
                f'maquis and villages. The verdict gives the headline and the spread of all of them.</p></section>')
    if compare is not None:
        body.append(_compare_card(compare))
    body.append("</main>")
    return document(f"Was it the wind? {when(v.start_epoch, tz)}", "".join(body))


def _stretch_card(n, s, factor, gave: bool) -> str:
    where = f"km {km(s.start_m)} → {km(s.start_m + s.length_m)}"
    what = (f"{km(s.length_m)} km, headwind {kmh(s.head10_ms)} at 10 m" if s.head10_ms >= 0
            else f"{km(s.length_m)} km, tailwind {kmh(-s.head10_ms)} at 10 m")
    cost = mmss(abs(s.lost_s))
    lab = "gained" if gave else "lost"
    return (f'<li class="stretch{" gave" if gave else ""}"><span class="n">{e(str(n))}</span><span class="where">{e(where)}</span>'
            f'<span class="cost"><b>{cost}</b><small>{lab}</small></span><span class="what">{e(what)}</span></li>')


def _compare_card(c) -> str:
    """`c`: dict with label, this_s, other_s, this_gap_s, other_gap_s."""
    diff = c["this_s"] - c["other_s"]
    wind_diff = c["this_gap_s"] - c["other_gap_s"]
    if abs(diff) < 1:
        share = "Both rides took the same time."
    else:
        pct = 100 * wind_diff / diff
        slower = "slower" if diff > 0 else "faster"
        share = (f"This ride was <strong>{mmss(abs(diff))} {slower}</strong> than {e(c['label'])}; the wind accounts for "
                 f"<strong>{mmss(abs(wind_diff))}</strong> of that difference "
                 f"({'about ' + str(int(round(pct))) + ' %' if 0 <= pct <= 150 else 'in the other direction' if pct < 0 else 'more than all of it'}).")
    return (f'<section class="card"><h2>Against {e(c["label"])}</h2><div class="compare">'
            f'<div><span>This ride</span><b>{hm(c["this_s"])}</b>wind {mmss(c["this_gap_s"], sign=True)}</div>'
            f'<div><span>{e(c["label"])}</span><b>{hm(c["other_s"])}</b>wind {mmss(c["other_gap_s"], sign=True)}</div>'
            f'<p>{share}</p></div></section>')


def _smooth(x, n):
    x = np.asarray(x, dtype=float)
    if x.size < n:
        return x
    k = np.ones(n) / n
    return np.convolve(np.pad(x, (n // 2, n - 1 - n // 2), mode="edge"), k, mode="valid")
