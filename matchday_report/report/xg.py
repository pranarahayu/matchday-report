"""Expected goals (xG) and expected goals on target (xGOT).

The models are XGBoost boosters saved as JSON (assets/models/). They are evaluated
here with plain numpy, so the app does not need the xgboost package.

Features (see assets/models/xg_model_meta.json), built from the timeline:
  distance        metres from the shot to the centre of the goal (pitch 105 x 68 m)
  angle           degrees of goal mouth visible from the shot position
  dist_goal_line  metres to the goal line, abs_y  metres from the centre line of the pitch
  in_box          1 = "Inside Box" tag
  Min             match clock in minutes (decimal)
  body_* / scheme_* one-hot from the shot tags (body part / situation)
  xGOT only:  pl_height (0 bottom, 1 middle, 2 top), pl_side (-1 left, 0 centre, 1 right),
              pl_corner (placement is a corner), near_post (shot placed on the post nearer
              to the shooter's side of the pitch)
Penalties get fixed values from the meta file (xG 0.7991, xGOT 0.855).
"""
from __future__ import annotations

import functools
import json
import os

import numpy as np
import pandas as pd

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "models")
SHOT_ACTS = {"shoot on target", "shoot off target", "shoot blocked"}
GOAL_W = 7.32


# --------------------------------------------------------------------------- #
# XGBoost JSON evaluator
# --------------------------------------------------------------------------- #
class Booster:
    """Minimal predictor for an XGBoost 'gbtree' JSON model with binary:logistic."""

    def __init__(self, path: str):
        with open(path) as fh:
            m = json.load(fh)
        L = m["learner"]
        self.features = L["feature_names"]
        base = float(L["learner_model_param"]["base_score"])
        self.base_margin = np.log(base / (1 - base))            # base_score is a probability
        self.trees = []
        for t in L["gradient_booster"]["model"]["trees"]:
            self.trees.append((np.array(t["left_children"]), np.array(t["right_children"]),
                               np.array(t["split_indices"]), np.array(t["split_conditions"], dtype=float),
                               np.array(t["default_left"], dtype=bool)))

    def predict(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        margin = np.full(len(X), self.base_margin)
        rows = np.arange(len(X))
        for left, right, feat, cond, dleft in self.trees:
            node = np.zeros(len(X), dtype=int)
            while True:
                active = left[node] != -1
                if not active.any():
                    break
                n = node[active]
                x = X[rows[active], feat[n]]
                go_left = np.where(np.isnan(x), dleft[n], x < cond[n])
                node[active] = np.where(go_left, left[n], right[n])
            margin += cond[node]                                  # leaf value
        return 1.0 / (1.0 + np.exp(-margin))


@functools.lru_cache(maxsize=1)
def load_models():
    meta_p = os.path.join(MODEL_DIR, "xg_model_meta.json")
    if not os.path.exists(meta_p):
        return None
    with open(meta_p) as fh:
        meta = json.load(fh)
    xg = Booster(os.path.join(MODEL_DIR, "xg_model.json"))
    xgot_p = os.path.join(MODEL_DIR, "xgot_model.json")
    xgot = Booster(xgot_p) if os.path.exists(xgot_p) else None
    return meta, xg, xgot


# --------------------------------------------------------------------------- #
# features
# --------------------------------------------------------------------------- #
def _tags(row) -> list[str]:
    return [str(row[c]).strip().lower() for c in ("Sub 1", "Sub 2", "Sub 3", "Sub 4")
            if c in row and pd.notna(row[c]) and str(row[c]).strip()]


def shot_features(shots: pd.DataFrame, meta: dict) -> pd.DataFrame:
    L, W = meta.get("pitch_m", [105.0, 68.0])
    body_map, scheme_map, zone_map = meta["body_map"], meta["scheme_map"], meta["zone_map"]
    place_map = meta["xgot"]["placement_map"]
    rows = []
    for _, s in shots.iterrows():
        tags = _tags(s)
        body = next((body_map[t] for t in tags if t in body_map), None)
        scheme = next((scheme_map[t] for t in tags if t in scheme_map), "open_play")
        zone = next((zone_map[t] for t in tags if t in zone_map), None)
        place = next((place_map[t] for t in tags if t in place_map), None)
        pen = "penalty" in tags or s["Action"] == "penalty goal"
        dx = (100 - s["X1"]) * L / 100
        dy = (s["Y1"] - 50) * W / 100
        dist = float(np.hypot(dx, dy))
        a = np.arctan2(GOAL_W * dx, dx ** 2 + dy ** 2 - (GOAL_W / 2) ** 2)
        angle = float(np.degrees(a if a >= 0 else a + np.pi))
        in_box = zone if zone is not None else int(s["X1"] >= 84.3 and 20.35 <= s["Y1"] <= 79.65)
        r = dict(distance=dist, angle=angle, dist_goal_line=dx, abs_y=abs(dy), in_box=in_box,
                 Min=s["sec"] / 60.0, penalty=pen)
        for b in meta["body_levels"]:
            r[f"body_{b}"] = int(body == b)
        for sc in meta["scheme_levels"]:
            r[f"scheme_{sc}"] = int(scheme == sc)
        if place is not None:
            h, side = place
            r.update(pl_height=h, pl_side=side, pl_corner=int(h != 1 and side != 0),
                     # near post: placement on the same side as the shooter (Y<50 = left)
                     near_post=int(side != 0 and np.sign(side) == np.sign(s["Y1"] - 50)))
        else:
            r.update(pl_height=np.nan, pl_side=np.nan, pl_corner=np.nan, near_post=np.nan)
        rows.append(r)
    return pd.DataFrame(rows, index=shots.index)


GOAL_ACTS = {"goal", "penalty goal"}


def shot_rows(T: pd.DataFrame) -> tuple[pd.Index, pd.Series]:
    """One row per shot, before any xG is calculated.

    The timeline logs every goal twice: a 'goal' (or 'penalty goal') row AND the
    'shoot on target' row of the same shot. Each goal is paired with its shot
    (same match, half and player, within 60 s) so it is counted once. A goal with
    no shot row is used as the shot itself.
    Returns (index of shot rows in T, is_goal flag for those rows)."""
    shots = T[T["Action"].isin(SHOT_ACTS) & T["X1"].notna()]
    is_goal = pd.Series(False, index=shots.index)
    extra = []
    on = shots[shots["Action"] == "shoot on target"]
    for gi, g in T[T["Action"].isin(GOAL_ACTS)].iterrows():
        c = on[(on.Match == g.Match) & (on.period == g.period) & (on["Act Name"] == g["Act Name"]) &
               ((on.sec - g.sec).abs() <= 60)]
        c = c[~is_goal.loc[c.index]]
        if len(c):
            is_goal.loc[(c.sec - g.sec).abs().idxmin()] = True
        elif pd.notna(g.X1):
            extra.append(gi)                     # goal without a shot row: it is the shot
    idx = shots.index.append(pd.Index(extra))
    flag = pd.concat([is_goal, pd.Series(True, index=pd.Index(extra))])
    return idx, flag


def add_xg(T: pd.DataFrame) -> pd.DataFrame:
    """Copy of the timeline with:
      is_shot  the deduplicated shot rows (see shot_rows)
      is_goal  shot that produced a goal
      xg       on every shot row;  xgot  on shots on target (and goals)"""
    T = T.copy()
    T["xg"], T["xgot"] = np.nan, np.nan
    T["is_shot"], T["is_goal"] = False, False
    if T.empty:
        return T
    idx, goal = shot_rows(T)
    T.loc[idx, "is_shot"] = True
    T.loc[goal.index, "is_goal"] = goal.values
    models = load_models()
    if models is None or not len(idx):
        return T
    meta, xg_m, xgot_m = models
    shots = T.loc[idx]
    F = shot_features(shots, meta)
    xg = xg_m.predict(F[xg_m.features].to_numpy())
    xg = np.where(F["penalty"], meta.get("penalty_xg", 0.7991), xg)
    T.loc[idx, "xg"] = xg
    on = (shots["Action"] == "shoot on target") | shots["Action"].isin(GOAL_ACTS)
    if xgot_m is not None and on.any():
        Fo = F[on.values]
        xgot = xgot_m.predict(Fo[xgot_m.features].to_numpy())
        xgot = np.where(Fo["penalty"], meta["xgot"].get("penalty_xgot", 0.855), xgot)
        T.loc[Fo.index, "xgot"] = xgot
    return T


def mark_goals(T: pd.DataFrame) -> pd.Series:
    """Kept for compatibility: the is_goal flag set by add_xg."""
    return T["is_goal"] if "is_goal" in T else pd.Series(False, index=T.index)


def _link(creators: pd.DataFrame, shots: pd.DataFrame, window: float) -> dict:
    """Pair chance-creation events with shots: same match, half and team, a different
    player, within `window` seconds (either side; the timeline often logs the pass
    after the shot). Closest first by distance from the pass end point to the shot
    (metres) + 0.5 x seconds apart. Each pass and each shot is used once."""
    pairs = []
    for i, c in creators.iterrows():
        s = shots[(shots.Match == c.Match) & (shots.period == c.period) & (shots.Team == c.Team) &
                  (shots["Act Name"] != c["Act Name"]) & ((shots.sec - c.sec).abs() <= window)]
        for j, x in s.iterrows():
            d = (np.hypot((x.X1 - c.X2) * 1.05, (x.Y1 - c.Y2) * 0.68)
                 if pd.notna(c.get("X2")) and pd.notna(x.X1) else 30.0)
            pairs.append((d + 0.5 * abs(x.sec - c.sec), i, j))
    pairs.sort()
    used_c, used_s, out = set(), set(), {}
    for _, i, j in pairs:
        if i in used_c or j in used_s:
            continue
        used_c.add(i); used_s.add(j); out[i] = j
    return out


def add_xa(T: pd.DataFrame) -> pd.Series:
    """xA on the chance-creation events: an 'assist' gets the xG of the goal it set up,
    a 'key pass' the xG of the (non-goal) shot it set up. Shots without an assist or
    key pass give no xA."""
    xa = pd.Series(0.0, index=T.index)
    if "xg" not in T or not T["xg"].notna().any():
        return xa
    shots = T[T["xg"].notna()]
    for act, pool, window in (("assist", shots[shots["is_goal"]], 150),
                              ("key pass", shots[~shots["is_goal"]], 60)):
        creators = T[T["Action"] == act]
        for i, j in _link(creators, pool, window).items():
            xa.loc[i] = shots.at[j, "xg"]
    return xa
