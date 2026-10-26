"""Expected threat (xT), using Karun Singh's open xT grid.

Grid file: assets/models/xt_grid.json, as published at
https://karun.in/blog/data/open_xt_12x8_v1.json – 8 rows (across the pitch) of 12 values
(along the pitch, own goal -> opponent goal). Any rows x columns size works.

xT of an action = grid value where the ball ends - grid value where it starts.
Counted for completed passes (passing, cross, key pass, assist) and ball carries.
Failed passes count 0, as in the original method. Restarts (throw-ins, free kicks,
goal kicks) are not counted separately because the timeline logs the pass that
follows each restart as its own 'passing' row.

Timeline coordinates: X 0-100 towards the opponent goal, Y 0-100 across. The grid is
left-right symmetric, so which edge Y=0 is does not matter.
"""
from __future__ import annotations

import functools
import json
import os

import numpy as np
import pandas as pd

GRID_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "assets", "models", "xt_grid.json")
PASS_MOVES = {"passing", "cross", "key pass", "assist"}
CARRY_MOVES = {"ball carry"}


@functools.lru_cache(maxsize=4)
def _load(path: str):
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        g = np.array(json.load(fh), dtype=float)
    if g.ndim != 2:
        return None
    if g.shape[0] > g.shape[1]:          # stored as columns x rows: make it rows (across) x cols (along)
        g = g.T
    return g


def load_grid():
    """The xT grid (rows across the pitch, columns from own goal to opponent goal), or None."""
    return _load(os.environ.get("MATCHDAY_XT_GRID", GRID_PATH))


def available() -> bool:
    return load_grid() is not None


def cell_values(grid: np.ndarray, x, y) -> np.ndarray:
    ny, nx = grid.shape
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    c = np.clip(np.floor(x / 100 * nx), 0, nx - 1).astype(int)
    r = np.clip(np.floor(y / 100 * ny), 0, ny - 1).astype(int)
    return grid[r, c]


def add_xt(T: pd.DataFrame) -> pd.DataFrame:
    """Copy of the timeline with 'xt' (threat added) and 'xt_kind' ('pass' / 'carry')."""
    T = T.copy()
    T["xt"] = np.nan
    T["xt_kind"] = None
    grid = load_grid()
    if grid is None or T.empty:
        return T
    moves = T["Action"].isin(PASS_MOVES | CARRY_MOVES) & T[["X1", "Y1", "X2", "Y2"]].notna().all(axis=1)
    m = T[moves]
    T.loc[m.index, "xt"] = cell_values(grid, m.X2, m.Y2) - cell_values(grid, m.X1, m.Y1)
    T.loc[m.index, "xt_kind"] = np.where(m["Action"].isin(CARRY_MOVES), "carry", "pass")
    return T
