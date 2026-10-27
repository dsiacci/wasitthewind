import numpy as np
import pytest

from wasitthewind.ghost import ghost_rows, replay, stretches

M = "m"


def chunk(n=20, head=None):
    head = np.zeros(n) if head is None else np.asarray(head, float)
    return {"ride": np.full(n, "r"), "start_s": np.arange(n) * 30.0, "full": np.ones(n, bool),
            "speed": np.full(n, 8.0), "dist_m": np.full(n, 240.0), f"head10__{M}": head,
            f"speed10__{M}": np.abs(head)}


def test_no_wind_no_gap():
    c = chunk()
    rows = ghost_rows(c)
    g = replay(c, np.full(rows.sum(), 8.0), np.full(rows.sum(), 8.0), M)
    assert g.gap_s == pytest.approx(0.0) and g.rider_total_s == 600.0
    assert np.allclose(g.ghost_lead_m(), 0.0)


def test_headwind_half_then_tailwind():
    head = np.r_[np.full(10, 4.0), np.full(10, -4.0)]
    c = chunk(head=head)
    v_wind = np.r_[np.full(10, 6.0), np.full(10, 9.0)]  # slower into it, faster with it
    v_calm = np.full(20, 8.0)
    g = replay(c, v_wind, v_calm, M)
    # Into the wind the ghost needs 30*6/8 = 22.5 s per chunk; with it, 33.75 s.
    assert g.ghost_s[0] == pytest.approx(22.5) and g.ghost_s[-1] == pytest.approx(33.75)
    assert g.gap_s == pytest.approx(600 - 10 * 22.5 - 10 * 33.75)
    lead = g.ghost_lead_m()
    assert lead[10] > 0  # the ghost pulls away into the wind
    assert lead[-1] < lead[10]  # and gets caught back with the wind
    worst = stretches(g, n=1)[0]
    assert worst.start_m == 0 and worst.length_m == pytest.approx(2400.0) and worst.head10_ms == pytest.approx(4.0)
    best = stretches(g, n=1, worst=False)[0]
    assert best.start_m == pytest.approx(2400.0) and best.lost_s < 0


def test_stops_are_ridden_by_the_ghost_too():
    c = chunk()
    c["full"][5] = False
    c["dist_m"][5] = 120.0  # half the chunk stopped
    rows = ghost_rows(c)
    g = replay(c, np.full(rows.sum(), 6.0), np.full(rows.sum(), 8.0), M)
    assert g.rider_s[5] == pytest.approx(15.0) and g.ghost_s[5] == pytest.approx(15.0)


def test_stretches_do_not_overlap():
    head = np.r_[np.full(5, 3.0), np.zeros(5), np.full(5, 3.0), np.zeros(5)]
    c = chunk(head=head)
    v_wind = np.where(head > 0, 7.0, 8.0)
    g = replay(c, v_wind, np.full(20, 8.0), M)
    s = stretches(g, n=3)
    assert len(s) == 2
    spans = sorted((x.first, x.last) for x in s)
    assert spans[0][1] < spans[1][0]
