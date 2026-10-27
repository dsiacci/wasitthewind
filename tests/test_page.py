import numpy as np

from test_analysis import DEMO, north_wind_fetch, out_and_back
from wasitthewind import analysis, models, page, wind


def test_result_page_renders_without_network(tmp_path):
    series, tracks = [], {}
    for day, w in ((10, 0.0), (11, 2.0), (12, 6.0)):
        out_and_back(tmp_path / f"r{day}.fit", day, w, leg_m=6000.0)
        rs, (lat, lon) = analysis.prepare(tmp_path / f"r{day}.fit", tmp_path / "cache",
                                          wind_models=[wind.DEFAULT_MODEL], fetch=north_wind_fetch(w))
        series.append(rs)
        tracks[rs.name] = (lat, lon)
    rs = series[2]
    v = analysis.judge(rs, series, make=models.LinearModel, rider=DEMO)
    html = page.result_page(v, rs, *tracks[rs.name], felt_factor=0.54, title="Invented ride")
    assert html.startswith("<!doctype html>") and "</html>" in html
    assert "http://" not in html.replace("http://www.w3.org", "") and "https://" not in html
    assert "animateMotion" in html
    assert "NaN" not in html and ">nan" not in html
    assert "Invented ride" in html


def test_verdict_words():
    assert page.verdict_words(10, -5, 20, 3600)[0] == "calm"
    kind, head, sentence = page.verdict_words(10, -20, 300, 3600)
    assert kind == "unsure" and "5:00 ahead" in sentence and "barely" not in sentence
    kind, head, _ = page.verdict_words(120, 60, 200, 3600)
    assert kind == "cost" and "2:00" in head
    kind, head, _ = page.verdict_words(-90, -150, -40, 3600)
    assert kind == "gave" and "1:30" in head


def test_mmss():
    assert page.mmss(62) == "1:02" and page.mmss(-62, sign=True) == "−1:02" and page.mmss(3725) == "1:02:05"
