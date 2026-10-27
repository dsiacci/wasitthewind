"""Distances and headings along a track.

Started from z2analyzer (same author, Apache 2.0): https://github.com/dsiacci/z2analyzer
"""

from __future__ import annotations

import numpy as np

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres (arrays welcome)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def cumulative_m(lat, lon):
    """Distance from the first point, in metres, for every point."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    if lat.size == 0:
        return np.zeros(0)
    steps = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
    return np.concatenate([[0.0], np.cumsum(steps)])


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2, degrees clockwise from north, in [0, 360)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float))
    y = np.sin(dl) * np.cos(p2)
    x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
    return np.degrees(np.arctan2(y, x)) % 360.0


def headings_deg(lat, lon, dist_m, span_m: float = 20.0):
    """Direction of travel at every point, from the positions `span_m` behind and ahead.

    A single GPS step is too noisy to give a heading; looking a few metres
    either way smooths it without blurring a hairpin.
    """
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    d = np.asarray(dist_m, dtype=float)
    lo = np.searchsorted(d, d - span_m / 2, side="left").clip(0, d.size - 1)
    hi = np.searchsorted(d, d + span_m / 2, side="right").clip(0, d.size - 1) - 0
    hi = np.minimum(hi, d.size - 1)
    same = lo == hi
    lo = np.where(same, np.maximum(lo - 1, 0), lo)
    hi = np.where(same, np.minimum(hi + 1, d.size - 1), hi)
    return bearing_deg(lat[lo], lon[lo], lat[hi], lon[hi])


def trim_mask(dist_m, trim_m: float = 2000.0):
    """True for the points at least `trim_m` from both ends (for maps and figures)."""
    d = np.asarray(dist_m, dtype=float)
    if d.size == 0:
        return np.zeros(0, dtype=bool)
    return (d >= d[0] + trim_m) & (d <= d[-1] - trim_m)
