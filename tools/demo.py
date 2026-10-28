"""Record the demo video from the web app's own pages.

    python tools/demo.py pages --url http://127.0.0.1:8766 --a ID --b ID --out pages/
    python tools/demo.py record --app pages/ --out demo/ [--voice voice/] [--tempo 1.05]

`pages` saves the pages the video shows, as the running app serves them:
home.html (the list of races), new.html (the form), progress.html (an
analysis running), a.html and b.html (two results: `--a` is the main ride,
with its comparison, and `--b` a second one). `record` photographs each scene
at 1920×1080 with a headless Chromium, the scene's part of the page on
screen; the race scenes are filmed frame by frame, the dots' animation
paused and moved on between frames. ffmpeg then joins the shots with
crossfades, each scene paced on its voice-over clip (voice/<scene>.mp3) when
there is one. Writes wasitthewind-demo.mp4 and wasitthewind-demo.srt
(captions). Needs chromium (or google-chrome), ffmpeg and ffprobe. The scenes
and their words are in tools/demo/scenes.json.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
W, H, FPS, RACE_FPS, FADE, LEAD = 1920, 1080, 30, 15, 0.5, 0.35

sys.path.insert(0, str(HERE.parent / "src"))
from wasitthewind.page import CSS, RACE_S, fonts_css  # noqa: E402

CARD_CSS = """
html, body { height:100%; margin:0; } body { background:var(--night); color:#eef3ff; }
.stage { position:fixed; inset:0; display:grid; place-content:center; text-align:center; overflow:hidden;
  background:radial-gradient(ellipse at 50% 120%, rgba(169,232,255,.16), rgba(169,232,255,0) 60%),
    linear-gradient(180deg, var(--night) 0%, var(--night2) 100%); }
.stage .road { position:absolute; left:-5%; right:-5%; bottom:16%; height:3px; background:rgba(233,237,245,.35); }
.stage .dot { position:absolute; bottom:calc(16% - 9px); width:20px; height:20px; border-radius:50%; }
.stage .dot.me { left:58%; background:var(--me); box-shadow:0 0 18px var(--me); }
.stage .dot.gh { left:61%; background:var(--ghost); box-shadow:0 0 22px var(--ghost); opacity:.85; }
.brand { font:700 124px/.9 var(--hud); letter-spacing:.01em; }
.brand i { font-style:normal; color:var(--ghost); }
.line { font:700 52px/1.05 var(--hud); text-transform:uppercase; margin-top:24px; }
.subl { font:500 26px/1.35 var(--hud); color:rgba(238,243,255,.75); margin-top:14px; }
.credits { font:500 23px/1.6 var(--hud); color:rgba(238,243,255,.82); margin-top:22px; }
.board { width:1120px; text-align:left; }
.board h1 { font:700 56px/1 var(--hud); text-transform:uppercase; margin:0 0 10px; }
.board .lead { font:500 24px/1.35 var(--hud); color:rgba(238,243,255,.72); margin:0 0 26px; }
.board .row { display:grid; grid-template-columns:520px 1fr 120px; align-items:center; gap:22px; margin:14px 0; }
.board .row span { font:600 26px/1.2 var(--hud); color:rgba(238,243,255,.85); }
.board .row i { display:block; height:22px; border-radius:11px; background:rgba(238,243,255,.28); }
.board .row b { font:700 34px/1 var(--hud); text-align:right; font-variant-numeric:tabular-nums; }
.board .row.win span, .board .row.win b { color:var(--ghost); } .board .row.win i { background:var(--ghost); box-shadow:0 0 14px var(--ghost); }
.board .row.lose b { color:var(--face); } .board .row.lose i { background:var(--face); }
.board p { font:500 21px/1.4 var(--hud); color:rgba(238,243,255,.6); margin:22px 0 0; }
.how { width:1160px; text-align:left; }
.how .kick { font:700 17px/1 var(--hud); letter-spacing:.18em; text-transform:uppercase; color:rgba(238,243,255,.6); margin:0 0 30px; }
.how .steps { display:grid; grid-template-columns:repeat(3, 1fr); gap:44px; }
.how .off { opacity:0; }
.how svg { display:block; width:100%; height:150px; margin-bottom:22px; overflow:visible; }
.how b { display:block; font:700 30px/1.05 var(--hud); text-transform:uppercase; }
.how b i { font-style:normal; color:var(--ghost); }
.how p { font:500 19px/1.4 var(--hud); color:rgba(238,243,255,.75); margin:12px 0 0; }
"""

# The three pictures of the "how it works" card: the wind along a road, the ghost beside the rider,
# the gap at the finish.
HOW_ART = [
    '<svg viewBox="0 0 360 150"><defs><marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5"'
    ' orient="auto"><path d="M0 0L10 5L0 10z" fill="#eef3ff"/></marker></defs>'
    '<path d="M8 128C90 70 160 150 240 92S330 48 352 56" fill="none" stroke="rgba(233,237,245,.45)" stroke-width="4"/>'
    + "".join(f'<path d="M{x} {y}l58 16" stroke="#eef3ff" stroke-width="3" stroke-linecap="round" marker-end="url(#ah)"'
              f' opacity=".8"/>' for x, y in ((30, 24), (130, 8), (230, 22), (80, 70), (190, 54)))
    + "</svg>",
    '<svg viewBox="0 0 360 150"><path d="M8 110H352" stroke="rgba(233,237,245,.45)" stroke-width="4"/>'
    '<circle cx="250" cy="110" r="20" fill="var(--ghost)" opacity=".35"/><circle cx="250" cy="110" r="11" fill="var(--ghost)"/>'
    '<circle cx="190" cy="110" r="10" fill="var(--me)"/>'
    '<text x="190" y="76" fill="var(--me)" text-anchor="middle" font-size="18" font-weight="700" font-family="var(--hud)">YOU</text>'
    '<text x="250" y="76" fill="var(--ghost)" text-anchor="middle" font-size="18" font-weight="700" font-family="var(--hud)">'
    'GHOST</text></svg>',
    '<svg viewBox="0 0 360 150"><path d="M8 110H352" stroke="rgba(233,237,245,.45)" stroke-width="4"/>'
    '<path d="M300 40V130" stroke="#eef3ff" stroke-width="4" stroke-dasharray="8 6"/>'
    '<circle cx="292" cy="110" r="20" fill="var(--ghost)" opacity=".35"/><circle cx="292" cy="110" r="11" fill="var(--ghost)"/>'
    '<circle cx="200" cy="110" r="10" fill="var(--me)"/>'
    '<path d="M200 76V68H292V76" fill="none" stroke="#eef3ff" stroke-width="3"/>'
    '<text x="246" y="56" fill="#eef3ff" text-anchor="middle" font-size="26" font-weight="700" font-family="var(--hud)">0:35</text>'
    "</svg>",
]

# What each view puts on screen: CSS added to the app's own page.
VIEWS = {
    None: "",
    # The list of races.
    "list": ".hero { padding-bottom:40px; } main { margin-top:18px !important; }",
    # The form, its file chosen and a ride to compare with picked.
    "drop": ".hero .sub { display:none; } .hero { padding-bottom:50px; } main { zoom:.92; }"
            " .drop.has { box-shadow:0 0 0 4px var(--card), 0 0 0 9px var(--me); }"
            " select { box-shadow:0 0 0 3px var(--card), 0 0 0 6px var(--ghost); }",
    # The verdict: the headline and its numbers.
    "verdict": ".hero { padding:26px 0 46px; } .hero .wrap { max-width:1180px; } .hero h1 { font-size:60px; margin:.12em 0 .14em; }"
               " .hero .sub { font-size:19px; max-width:52em; } .hud { margin-top:12px; } .hud b { font-size:30px; }"
               " main > section:not(.how) { display:none !important; } main { margin-top:-24px !important; zoom:.84; }",
    # The race: the headline on the left, the map on the right, the dots larger; the ghost a wide halo
    # under the rider's dot, so that it shows even when it is only a few seconds away.
    "race": "html, body { background:var(--night) !important; } .appbar, .hero .sub, .hero .kicker, main > section:not(.race),"
            " .about, footer, .race .note { display:none !important; }"
            " .hero { position:fixed; left:0; top:0; bottom:0; width:520px; padding:96px 0 0 !important; background:none !important; }"
            " .hero::after { display:none; } .hero .wrap { padding:0 0 0 56px !important; max-width:none; }"
            " .hero h1 { font-size:48px; } .hud { display:grid; grid-template-columns:1fr; gap:22px; }"
            " main.wrap { margin:0 0 0 520px !important; padding:24px 40px 24px 0 !important; max-width:none !important; }"
            " .race { margin:0 !important; height:672px; box-sizing:border-box; display:grid; grid-template-rows:auto 1fr auto; }"
            " .race svg { height:560px !important; width:100% !important; }"
            " .race svg > g:nth-of-type(1) circle:nth-child(1) { r:26px; opacity:.6; }"
            " .race svg > g:nth-of-type(1) circle:nth-child(2) { r:16px; opacity:1; }"
            " .race svg > g:nth-of-type(2) circle { r:9px; }",
    # Where the ghost was along the ride, and how sure.
    "lead": ".appbar, .hero, main > section:not(.lead):not(.weighed), .about, footer { display:none !important; }"
            " main { margin-top:28px !important; max-width:1180px !important; }",
    # The comparison with an earlier ride, after the verdict.
    "compare": ".hero .sub, .hud { display:none; } .hero { padding-bottom:40px; }"
               " main > section:not(.cmp) { display:none !important; } main { margin-top:22px !important; }"
               " .cmp { box-shadow:0 0 0 4px var(--paper), 0 0 0 9px var(--ghost); zoom:1.15; }",
}

RACE_JS = """<script>
(function(){
  var t = parseFloat(location.hash.slice(1)) || 0;
  function go(){ document.querySelectorAll('svg').forEach(function(s){ if (s.querySelector('animateMotion')) { s.pauseAnimations(); s.setCurrentTime(t); } }); }
  go(); window.addEventListener('load', go);
})();
</script>"""


def run(cmd: list[str], env: dict | None = None) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-1500:]}")
    return r.stdout


def browser() -> str:
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        if shutil.which(name):
            return name
    raise SystemExit("needs chromium or google-chrome")


def shoot(url: str, png: Path) -> None:
    """1280×720 CSS pixels at a scale of 1.5: a 1920×1080 picture with sharp text."""
    run([browser(), "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--lang=en-GB",
         "--force-device-scale-factor=1.5", "--window-size=1280,720", f"--screenshot={png}", url],
        env=dict(os.environ, LANG="en_GB.UTF-8", LANGUAGE="en_GB"))


def doc(body: str) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{fonts_css()}{CSS}{CARD_CSS}</style></head>"
            f"<body>{body}</body></html>")


def card(kind: str, spec: dict, shown: int = 3) -> str:
    """A card of the video; for "how", `shown` is how many of its steps are on screen."""
    e = html.escape
    road = '<div class="road"></div><div class="dot me"></div><div class="dot gh"></div>'
    if kind == "how":
        steps = "".join(f'<div class="{"" if k < shown else "off"}">{HOW_ART[k]}<b><i>{k + 1}</i> {e(t)}</b><p>{e(p)}</p></div>'
                        for k, (t, p) in enumerate(spec["steps"]))
        return doc(f'<div class="stage"><div class="how"><div class="kick">{e(spec["kick"])}</div>'
                   f'<div class="steps">{steps}</div></div></div>')
    if kind == "title":
        return doc(f'<div class="stage">{road}<div class="brand">was<i>it</i>the<i>wind</i></div>'
                   f'<div class="line">{e(spec["line"])}</div><div class="subl">{e(spec["sub"])}</div></div>')
    if kind == "outro":
        lines = "".join(f"<div>{e(x)}</div>" for x in spec["lines"])
        return doc(f'<div class="stage">{road}<div class="brand">was<i>it</i>the<i>wind</i></div>'
                   f'<div class="credits">{lines}</div></div>')
    top = max(r[1] for r in spec["rows"])
    rows = "".join(f'<div class="row {r[2]}"><span>{e(r[0])}</span><i style="width:{100 * r[1] / top:.1f}%"></i>'
                   f'<b>{r[1]:.1f}</b></div>' for r in spec["rows"])
    return doc(f'<div class="stage"><div class="board"><h1>{e(spec["title"])}</h1><p class="lead">{e(spec["lead"])}</p>'
               f'{rows}<p>{e(spec["note"])}</p></div></div>')


def page_variant(src: Path, view: str | None, sc: dict) -> str:
    """The app's own page, with the scene's part on screen."""
    s = src.read_text(encoding="utf-8")
    s = re.sub(r'<meta http-equiv="(refresh|Content-Security-Policy)"[^>]*>', "", s)
    for heading, tag in (("Where the ghost was", "lead"), ("Where the wind weighed", "weighed"), ("How sure", "how"),
                         ("Against", "cmp")):
        s = s.replace(f'<section class="card"><h2>{heading}', f'<section class="card {tag}"><h2>{heading}', 1)
    if view == "drop":
        s = s.replace('<label class="drop">', '<label class="drop has">', 1)
        s = s.replace('<span class="name"></span>', f'<span class="name">{html.escape(sc["file"])}</span>', 1)
        if sc.get("compare"):
            s = re.sub(r'(<option value="[^"]*")(>' + re.escape(sc["compare"]) + ")", r"\1 selected\2", s, count=1)
    if view == "race":
        s = s.replace("</body>", RACE_JS + "</body>", 1) if "</body>" in s else s + RACE_JS
    return s.replace("</style>", VIEWS[view] + "</style>", 1)


def duration(path: Path) -> float:
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).strip())


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def pages(a) -> int:
    from wasitthewind import web

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    def get(path):
        return urllib.request.urlopen(a.url.rstrip("/") + path, timeout=60).read().decode()

    (out / "home.html").write_text(get("/"), encoding="utf-8")
    (out / "new.html").write_text(get("/new"), encoding="utf-8")
    (out / "a.html").write_text(get(f"/a/{a.a}"), encoding="utf-8")
    (out / "b.html").write_text(get(f"/a/{a.b}"), encoding="utf-8")
    (out / "progress.html").write_text(web.progress_page({"file": a.file, "step": 2}), encoding="utf-8")
    print("saved in", out)
    return 0


def record(a) -> int:
    conf = json.loads((HERE / "demo" / "scenes.json").read_text(encoding="utf-8"))
    out = Path(a.out)
    shots = out / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    app = Path(a.app)
    voice = Path(a.voice) if a.voice else None

    plan = []
    for sc in conf["scenes"]:
        kind, name, *view = sc["shot"].split(":")
        clip = voice / f"{sc['id']}.mp3" if voice and (voice / f"{sc['id']}.mp3").exists() else None
        spoken = duration(clip) / a.tempo if clip else len(sc["say"]) / 15.0
        d = max(sc["min"], LEAD + spoken + 0.9)
        page = shots / f"{sc['id']}.html"
        if kind == "card":
            page.write_text(card(name, conf["cards"][name], *(int(x) for x in view)), encoding="utf-8")
        else:
            page.write_text(page_variant(app / f"{name}.html", view[0] if view else None, sc), encoding="utf-8")
        seg = shots / f"{sc['id']}.mp4"
        if kind == "race":
            # The whole race, squeezed into the scene: one picture per frame, the dots moved on each time.
            frames = shots / sc["id"]
            frames.mkdir(exist_ok=True)
            n = int(round(d * RACE_FPS))
            uri = page.resolve().as_uri()
            with ThreadPoolExecutor(max_workers=a.jobs) as pool:
                list(pool.map(lambda i: shoot(f"{uri}#{RACE_S * min(1.0, i / (n * 0.92)):.3f}",
                                              frames / f"{i:04d}.png"), range(n)))
            run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(RACE_FPS), "-i", str(frames / "%04d.png"),
                 "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "18", str(seg)])
        else:
            png = shots / f"{sc['id']}.png"
            shoot(page.resolve().as_uri(), png)
            # the still held as it is: a slow zoom shook the text
            run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(png), "-t", f"{d:.3f}",
                 "-vf", f"scale={W}:{H},format=yuv420p", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium",
                 "-tune", "stillimage", "-crf", "18", str(seg)])
        plan.append({**sc, "seg": seg, "clip": clip, "spoken": spoken, "d": d})
        print(f"{sc['id']}: {d:.1f} s", flush=True)

    starts, t = [], 0.0
    for k, sc in enumerate(plan):
        starts.append(t)
        t += sc["d"] - (FADE if k < len(plan) - 1 else 0)
    total = t
    inputs = sum((["-i", str(sc["seg"])] for sc in plan), [])
    chain, last = [], "[0:v]"
    for k in range(1, len(plan)):
        label = f"[v{k}]"
        chain.append(f"{last}[{k}:v]xfade=transition=fade:duration={FADE}:offset={starts[k]:.3f}{label}")
        last = label
    vfilter = ";".join(chain) if chain else "[0:v]null[v1]"
    vlabel = last if chain else "[v1]"

    audio_in, amix = [], []
    for k, sc in enumerate(plan):
        if sc["clip"]:
            n = len(plan) + len(audio_in) // 2
            audio_in += ["-i", str(sc["clip"])]
            delay = int(round((starts[k] + LEAD) * 1000))
            amix.append(f"[{n}:a]atempo={a.tempo},adelay={delay}|{delay}[a{k}]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, *audio_in]
    if amix:
        labels = "".join(f"[a{k}]" for k, sc in enumerate(plan) if sc["clip"])
        afilter = ";".join(amix) + f";{labels}amix=inputs={len(amix)}:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,apad[aout]"
        cmd += ["-filter_complex", f"{vfilter};{afilter}", "-map", vlabel, "-map", "[aout]", "-c:a", "aac", "-b:a", "160k",
                "-ar", "48000"]
    else:
        cmd += ["-filter_complex", vfilter, "-map", vlabel]
    target = out / "wasitthewind-demo.mp4"
    cmd += ["-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(target)]
    run(cmd)

    lines = []
    for k, sc in enumerate(plan):
        if not sc["say"]:
            continue  # a silent scene
        a0 = starts[k] + LEAD
        lines.append(f"{len(lines) + 1}\n{srt_time(a0)} --> {srt_time(a0 + sc['spoken'])}\n{sc['say']}\n")
    (out / "wasitthewind-demo.srt").write_text("\n".join(lines), encoding="utf-8")
    print(f"{target}: {total:.1f} s, {len(plan)} scenes, {sum(len(sc['say']) for sc in plan)} characters spoken")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pages", help="save the pages the video shows from the running app")
    p.add_argument("--url", default="http://127.0.0.1:8766")
    p.add_argument("--a", required=True, help="the main ride's analysis (with its comparison)")
    p.add_argument("--b", required=True, help="a second ride's analysis")
    p.add_argument("--file", default="ride.fit", help="the file name shown while an analysis runs")
    p.add_argument("--out", required=True)
    r = sub.add_parser("record", help="film the scenes")
    r.add_argument("--app", required=True, help="folder of the saved pages")
    r.add_argument("--out", required=True)
    r.add_argument("--voice", help="folder of <scene>.mp3 voice-over clips")
    r.add_argument("--tempo", type=float, default=1.0, help="play the voice this much faster")
    r.add_argument("--jobs", type=int, default=2, help="pictures taken at once for the race scenes")
    a = ap.parse_args()
    return pages(a) if a.cmd == "pages" else record(a)


if __name__ == "__main__":
    raise SystemExit(main())
