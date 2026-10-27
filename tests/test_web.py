import json
import re
import threading
import time
import urllib.error
import urllib.request

import pytest

from test_analysis import DEMO, north_wind_fetch, out_and_back
from wasitthewind import analysis, models, web, wind


def _library(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    for day, w in ((10, 0.0), (11, 2.0)):
        out_and_back(tmp_path / f"r{day}.fit", day, w)
        rs, _ = analysis.prepare(tmp_path / f"r{day}.fit", tmp_path / "cache", wind_models=[wind.DEFAULT_MODEL],
                                 fetch=north_wind_fetch(w))
        rs.save(lib / f"{rs.name}.npz")
    return lib


def _settings(tmp_path, lib, w=6.0):
    return web.Settings(cache=str(tmp_path / "cache"), library=str(lib), mass_kg=DEMO.mass_kg,
                        wind_models=(wind.DEFAULT_MODEL,), fetch=north_wind_fetch(w))


def _multipart(fields, filename, data):
    b = "----wasitthewindtest"
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
    return b"".join(parts) + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def test_store_and_names(tmp_path):
    s = web.Store(tmp_path)
    m = s.create("../../etc/My Ride!.FIT", b"x", {})
    assert m["file"] == "My-Ride-.FIT" and (s.folder(m["id"]) / "in" / m["file"]).exists()
    assert s.update(m["id"], status="done")["status"] == "done"
    assert [x["id"] for x in s.all()] == [m["id"]]
    with pytest.raises(KeyError):
        s.folder("../x")
    s.delete(m["id"])
    assert s.all() == []


def test_parse_multipart():
    body, ctype = _multipart({"token": "abc", "compare": ""}, "a.fit", b"\x00\x01--\r\nbin")
    fields, files = web.parse_multipart(ctype, body)
    assert fields == {"token": "abc", "compare": ""}
    assert files["file"] == ("a.fit", b"\x00\x01--\r\nbin")


def test_run_writes_the_page_and_learns_from_the_others(tmp_path):
    lib = _library(tmp_path)
    out_and_back(tmp_path / "r12.fit", 12, 6.0)
    store = web.Store(tmp_path / "data")
    meta = store.create("r12.fit", (tmp_path / "r12.fit").read_bytes(), {})
    done = web.run(store, meta["id"], _settings(tmp_path, lib), make=models.LinearModel)
    assert done["status"] == "done" and done["result"]["context_rides"] == 2
    assert done["result"]["rider_s"] > 700
    assert any(k.startswith("physics") for k in done["result"]["variants"])
    folder = store.folder(meta["id"])
    assert (folder / "page.html").exists() and (folder / "series.npz").exists()
    saved = json.loads((folder / "meta.json").read_text())
    assert str(DEMO.mass_kg) not in json.dumps(saved) and "mass" not in json.dumps(saved)
    page = web.result_page(store, meta | done, "tok")
    assert 'class="appbar"' in page and "ghost learned from 2 other rides" in page


def test_run_refuses_without_enough_rides(tmp_path):
    out_and_back(tmp_path / "r12.fit", 12, 6.0)
    store = web.Store(tmp_path / "data")
    meta = store.create("r12.fit", (tmp_path / "r12.fit").read_bytes(), {})
    with pytest.raises(ValueError, match="other rides"):
        web.run(store, meta["id"], web.Settings(cache=str(tmp_path / "cache"), wind_models=(wind.DEFAULT_MODEL,),
                                                fetch=north_wind_fetch(6.0)), make=models.LinearModel)


def test_server_upload_race_and_delete(tmp_path):
    lib = _library(tmp_path)
    out_and_back(tmp_path / "r12.fit", 12, 6.0)
    app = web.App(web.Store(tmp_path / "data"), _settings(tmp_path, lib), make=models.LinearModel)
    httpd = web.make_server(app, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        home = urllib.request.urlopen(base + "/").read().decode()
        assert "Race your ghost" in home and "No race yet" in home
        new = urllib.request.urlopen(base + "/new").read().decode()
        token = re.search(r'name="token" value="([^"]+)"', new).group(1)

        body, ctype = _multipart({"token": "wrong"}, "r12.fit", (tmp_path / "r12.fit").read_bytes())
        with pytest.raises(urllib.error.HTTPError) as ex:
            urllib.request.urlopen(urllib.request.Request(base + "/new", body, {"Content-Type": ctype}))
        assert ex.value.code == 403

        body, ctype = _multipart({"token": token}, "notes.txt", b"hello")
        with pytest.raises(urllib.error.HTTPError) as ex:
            urllib.request.urlopen(urllib.request.Request(base + "/new", body, {"Content-Type": ctype}))
        assert ex.value.code == 400 and "not a FIT file" in ex.value.read().decode()

        body, ctype = _multipart({"token": token, "compare": ""}, "r12.fit", (tmp_path / "r12.fit").read_bytes())
        r = urllib.request.urlopen(urllib.request.Request(base + "/new", body, {"Content-Type": ctype}))
        url = r.geturl()
        assert re.search(r"/a/\d{8}-\d{6}-[0-9a-f]{4}$", url)
        for _ in range(200):
            text = urllib.request.urlopen(url).read().decode()
            if "Racing…" not in text:
                break
            time.sleep(0.1)
        assert "animateMotion" in text and "Delete" in text, text[-600:]
        assert "Wind cost" in urllib.request.urlopen(base + "/").read().decode()

        aid = url.rsplit("/", 1)[1]
        req = urllib.request.Request(f"{base}/a/{aid}/delete", f"token={token}".encode(),
                                     {"Content-Type": "application/x-www-form-urlencoded"})
        assert "No race yet" in urllib.request.urlopen(req).read().decode()
    finally:
        httpd.shutdown()
        app.stop()
