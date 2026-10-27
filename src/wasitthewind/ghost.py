"""The ghost: the same ride, the same legs, no wind.

For every 30-second chunk ridden without a stop, a speed model predicts the
speed twice: with the wind the rider had, and with no wind at all. The ghost
covers the chunk in the rider's own time scaled by the ratio of the two:

    ghost seconds = 30 × (predicted speed with the wind) / (predicted speed with no wind)

so the rider's own good or bad day stays in, and only the wind comes out.
Chunks with a stop are ridden by the ghost exactly as by the rider: a red
light doesn't care about the wind. Everything is in moving time.

`gap_s` is the rider's time minus the ghost's: positive, the wind cost time;
negative, it gave some.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MIN_STRETCH_M = 500.0


@dataclass
class Ghost:
    ride: str
    start_s: np.ndarray  # chunk start, seconds since the ride's first record
    dist_m: np.ndarray  # distance covered in each chunk
    rider_s: np.ndarray  # seconds the rider spent moving in the chunk
    ghost_s: np.ndarray  # seconds the ghost needs for the same chunk
    head10: np.ndarray  # mean headwind at 10 m (m/s), for the stretches
    speed10: np.ndarray  # mean wind speed at 10 m

    @property
    def rider_total_s(self) -> float:
        return float(self.rider_s.sum())

    @property
    def ghost_total_s(self) -> float:
        return float(self.ghost_s.sum())

    @property
    def gap_s(self) -> float:
        """Rider minus ghost, seconds: what the wind cost (or, negative, gave)."""
        return self.rider_total_s - self.ghost_total_s

    @property
    def gap_pct(self) -> float:
        return 100.0 * self.gap_s / self.ghost_total_s if self.ghost_total_s else 0.0

    def cumulative(self):
        """(distance, rider seconds, ghost seconds) at each chunk end, from zero."""
        d = np.concatenate([[0.0], np.cumsum(self.dist_m)])
        return d, np.concatenate([[0.0], np.cumsum(self.rider_s)]), np.concatenate([[0.0], np.cumsum(self.ghost_s)])

    def ghost_lead_m(self):
        """How far ahead of the rider the ghost is (metres; negative: behind) at each chunk end."""
        d, tr, tg = self.cumulative()
        ghost_d = np.interp(tr, tg, d)
        return ghost_d - d


def ghost_rows(chunk: dict) -> np.ndarray:
    """Chunks the ghost rides on its own: ridden without a stop, above walking pace."""
    return np.asarray(chunk["full"], bool) & (np.asarray(chunk["speed"]) > 1.5)


def replay(chunk: dict, v_wind, v_calm, model: str) -> Ghost:
    """The ghost of one ride from its chunks and the predicted speeds, with and without the wind, on `ghost_rows`."""
    rows = ghost_rows(chunk)
    speed = np.asarray(chunk["speed"], float)
    moving_share = np.clip(np.asarray(chunk["dist_m"], float) / np.maximum(speed * 30.0, 1e-9), 0.0, 1.0)
    rider = np.where(rows, 30.0, 30.0 * moving_share)
    ghost = rider.copy()
    if rows.any():
        ratio = np.asarray(v_wind, float) / np.maximum(np.asarray(v_calm, float), 0.3)
        ghost[rows] = 30.0 * np.clip(ratio, 0.3, 3.0)
    return Ghost(ride=str(chunk["ride"][0]) if rows.size else "", start_s=np.asarray(chunk["start_s"], float),
                 dist_m=np.asarray(chunk["dist_m"], float), rider_s=rider, ghost_s=ghost,
                 head10=np.asarray(chunk[f"head10__{model}"], float),
                 speed10=np.asarray(chunk[f"speed10__{model}"], float))


@dataclass
class Stretch:
    start_m: float
    length_m: float
    lost_s: float  # positive: time the wind cost on the stretch
    head10_ms: float  # mean headwind at 10 m, weighted by time
    first: int
    last: int


def stretches(g: Ghost, n: int = 3, worst: bool = True, min_length_m: float = MIN_STRETCH_M,
              min_rate: float = 0.02) -> list[Stretch]:
    """The `n` stretches where the wind cost the most time (or, `worst=False`, gave the most).

    A stretch is a run of consecutive chunks where the wind cost (or gave)
    more than `min_rate` of the rider's time; a single calm chunk between two
    windy ones doesn't cut it. Runs shorter than `min_length_m` are dropped,
    the others ranked by the time lost (or gained).
    """
    loss = (g.rider_s - g.ghost_s) * (1 if worst else -1)
    rate = loss / np.maximum(g.rider_s, 1e-9)
    on = (rate > min_rate) & (g.rider_s > 0)
    hole = np.zeros_like(on)
    hole[1:-1] = ~on[1:-1] & on[:-2] & on[2:]
    on = on | hole
    d0 = np.concatenate([[0.0], np.cumsum(g.dist_m)])
    runs = []
    i = 0
    while i < on.size:
        if not on[i]:
            i += 1
            continue
        j = i
        while j + 1 < on.size and on[j + 1]:
            j += 1
        length = d0[j + 1] - d0[i]
        total = loss[i:j + 1].sum()
        if length >= min_length_m and total > 0:
            runs.append((total, i, j))
        i = j + 1
    out = []
    for _, a, b in sorted(runs, reverse=True)[:n]:
        w = g.rider_s[a:b + 1]
        out.append(Stretch(start_m=float(d0[a]), length_m=float(d0[b + 1] - d0[a]),
                           lost_s=float((g.rider_s - g.ghost_s)[a:b + 1].sum()),
                           head10_ms=float(np.average(g.head10[a:b + 1], weights=np.maximum(w, 1e-9))),
                           first=a, last=b))
    return out
