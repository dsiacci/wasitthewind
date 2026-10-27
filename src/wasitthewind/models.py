"""The speed model: TabPFN v2 learns how fast the rider goes, simple baselines keep it honest.

TabPFN is a tabular foundation model (Prior Labs): pre-trained on synthetic
tables, it predicts on a new table in one forward pass, given the training
rows as context. Nothing is fine-tuned. Weights: TabPFN v2 regressor, Prior
Labs License 1.1. Built with PriorLabs-TabPFN.

One table (see `ride.py`): 30-second chunks of the rider's other rides, with
power, grade, headwind and crosswind at rider height, temperature and minutes
ridden; the target is the mean speed.

The ghost's speed is not the chunk predicted with the wind set to zero. A
first version did that, and the ghost came out slower than the rider on every
ride, as if the wind had always helped, calm days included (docs/results.md).
The model had learned the kind of day from the wind: a strong crosswind meant
a windy day on the coast road, where the rider goes fast; no wind at all
meant a calm day inland, on slower roads. Setting the wind to zero moved the
ride inland. So the ghost keeps the crosswind and asks the model twice, with
the headwind as it was and turned around (a tailwind of the same strength),
and takes the mean of the two: what the wind did by blowing one way rather
than the other, with the kind of day left as it was.

Started from z2analyzer (same author, Apache 2.0): https://github.com/dsiacci/z2analyzer
"""

from __future__ import annotations

import os

import numpy as np

QUANTILES = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
MAX_CONTEXT = 3000  # rows given to TabPFN as context (a small CPU stays at a few seconds)
SPEED_FEATURES = ("power", "grade", "head", "cross", "temp", "elapsed_min")
WIND_FEATURES = ("head", "cross")


def make_regressor(n_estimators: int = 4, random_state: int = 0):
    """A TabPFN v2 regressor on CPU (the v2 weights, not the newer non-commercial ones)."""
    os.environ.setdefault("TABPFN_ALLOW_CPU_LARGE_DATASET", "1")
    from tabpfn import TabPFNRegressor
    from tabpfn.constants import ModelVersion

    return TabPFNRegressor.create_default_for_version(ModelVersion.V2, n_estimators=n_estimators, device="cpu",
                                                      random_state=random_state)


class TabPFNModel:
    name = "TabPFN v2"

    def __init__(self, X, y, n_estimators: int = 4, max_rows: int = MAX_CONTEXT, seed: int = 0):
        X, y = _subsample(np.asarray(X, np.float32), np.asarray(y, np.float32), max_rows, seed)
        self.reg = make_regressor(n_estimators=n_estimators, random_state=seed)
        self.reg.fit(X, y)

    def quantiles(self, X, qs=QUANTILES) -> np.ndarray:
        out = self.reg.predict(np.asarray(X, np.float32), output_type="quantiles", quantiles=list(qs))
        return np.column_stack([np.asarray(o, float) for o in out])


class LinearModel:
    """Least squares on the same features; the spread comes from the training residuals."""

    name = "linear regression"

    def __init__(self, X, y):
        X = np.asarray(X, float)
        A = np.column_stack([X, np.ones(len(X))])
        self.coef, *_ = np.linalg.lstsq(A, np.asarray(y, float), rcond=None)
        self.resid = np.asarray(y, float) - A @ self.coef

    def quantiles(self, X, qs=QUANTILES) -> np.ndarray:
        X = np.asarray(X, float)
        pred = np.column_stack([X, np.ones(len(X))]) @ self.coef
        return pred[:, None] + np.quantile(self.resid, qs)[None, :]


class ConstantModel:
    """One number for everything (with the spread of the training values)."""

    name = "constant"

    def __init__(self, X, y):
        self.q = np.asarray(y, float)

    def quantiles(self, X, qs=QUANTILES) -> np.ndarray:
        return np.tile(np.quantile(self.q, qs), (len(X), 1))


class ColumnsModel:
    """A model that only sees some of the columns (the same model without the wind, say)."""

    def __init__(self, base, cols, X, y, label: str | None = None):
        self.cols = list(cols)
        self.m = base(np.asarray(X)[:, self.cols], y)
        self.name = label or f"{base.name} on {len(self.cols)} column(s)"

    def quantiles(self, X, qs=QUANTILES) -> np.ndarray:
        return self.m.quantiles(np.asarray(X)[:, self.cols], qs)


def _subsample(X, y, max_rows: int, seed: int):
    if len(y) <= max_rows:
        return X, y
    idx = np.random.default_rng(seed).choice(len(y), size=max_rows, replace=False)
    return X[idx], y[idx]


def median(model, X) -> np.ndarray:
    return model.quantiles(X, (0.5,))[:, 0]


def score(y, q: np.ndarray, qs=QUANTILES) -> dict:
    """Error of the median, and how often the 10-90 % interval holds the truth."""
    qs = list(qs)
    y = np.asarray(y, float)
    med = q[:, qs.index(0.5)]
    lo, hi = q[:, qs.index(0.1)], q[:, qs.index(0.9)]
    err = med - y
    return {"n": int(len(err)), "mae": float(np.mean(np.abs(err))), "bias": float(np.mean(err)),
            "rmse": float(np.sqrt(np.mean(err**2))),
            "coverage_80": float(np.mean((y >= lo) & (y <= hi))) if len(err) else float("nan")}


def speed_table(all_chunks: list[dict], model: str, factor: float) -> dict:
    """The training table: full chunks moving above walking pace, wind moved to rider height."""
    c = {k: np.concatenate([ch[k] for ch in all_chunks if ch]) for k in all_chunks[0]}
    rows = c["full"] & (c["speed"] > 1.5)
    cols = {"power": c["power"], "grade": c["grade"], "head": factor * c[f"head10__{model}"],
            "cross": factor * c[f"cross10__{model}"], "temp": c["temp"], "elapsed_min": c["elapsed_min"]}
    return {"X": np.column_stack([cols[f][rows] for f in SPEED_FEATURES]).astype(np.float32),
            "y": c["speed"][rows].astype(np.float32), "ride": c["ride"][rows],
            "features": np.array(SPEED_FEATURES)}


def features(chunk: dict, model: str, factor: float, turned: bool = False) -> np.ndarray:
    """Feature rows of one ride's chunks; with `turned`, the headwind blows the other way."""
    head = (-factor if turned else factor) * chunk[f"head10__{model}"]
    cols = {"power": chunk["power"], "grade": chunk["grade"], "head": head,
            "cross": factor * chunk[f"cross10__{model}"], "temp": chunk["temp"], "elapsed_min": chunk["elapsed_min"]}
    return np.column_stack([cols[f] for f in SPEED_FEATURES]).astype(np.float32)


def without_wind(base):
    """A factory for the same model blind to the wind columns."""
    keep = [i for i, f in enumerate(SPEED_FEATURES) if f not in WIND_FEATURES]

    def make(X, y):
        return ColumnsModel(base, keep, X, y, label=f"{base.name}, no wind")

    return make


def leave_one_ride_out(table: dict, factories: dict) -> dict:
    """Each ride predicted by models trained on all the others, for every model factory."""
    rides = sorted(set(table["ride"].tolist()))
    out = {name: {"per_ride": {}} for name in factories}
    preds = {name: [] for name in factories}
    truth = []
    for r in rides:
        test = table["ride"] == r
        if test.sum() == 0 or (~test).sum() < 20:
            continue
        truth.append(table["y"][test])
        for name, make in factories.items():
            m = make(table["X"][~test], table["y"][~test])
            q = m.quantiles(table["X"][test])
            preds[name].append(q)
            out[name]["per_ride"][r] = score(table["y"][test], q)
    y = np.concatenate(truth) if truth else np.zeros(0)
    for name in factories:
        if preds[name]:
            out[name]["all"] = score(y, np.concatenate(preds[name]))
    return out
