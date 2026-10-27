import gzip

import numpy as np
import pytest

from wasitthewind.stations import KNOT_MS, read_iem_metar, read_meteofrance

HEAD = "NUM_POSTE;NOM_USUEL;LAT;LON;ALTI;AAAAMMJJHH;RR1;QRR1;FF;QFF;DD;QDD\n"


def test_meteofrance_hourly_file(tmp_path):
    p = tmp_path / "H_99_latest.csv.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(HEAD)
        f.write("99001001;INVENTED POINT;10.0;20.0;12;2026011506;0;1;4.2;1;250;1\n")
        f.write("99001001;INVENTED POINT;10.0;20.0;12;2026011505;0;1;3.0;1;240;1\n")
        f.write("99001001;INVENTED POINT;10.0;20.0;12;2026011507;0;1;;;;\n")
        f.write("99002001;OTHER;10.1;20.1;300;2026011506;0;1;1.0;1;90;1\n")
    st = read_meteofrance(p, {"99001001"})
    assert list(st) == ["99001001"]
    m = st["99001001"]
    assert m.name == "INVENTED POINT" and m.lat == 10.0 and m.alt_m == 12
    assert m.times.size == 2 and m.times[0] < m.times[1]
    assert m.speed.tolist() == [3.0, 4.2] and m.direction.tolist() == [240.0, 250.0]


def test_iem_metar():
    text = "station,valid,sknt,drct\nXXXX,2026-01-15 06:00,10.00,250.00\nXXXX,2026-01-15 06:30,M,M\nXXXX,2026-01-15 07:00,2.00,M\n"
    m = read_iem_metar(text, 10.0, 20.0)
    assert m.station == "XXXX" and m.times.size == 2
    assert m.speed[0] == pytest.approx(10 * KNOT_MS) and m.direction[0] == 250.0
    assert np.isnan(m.direction[1])
