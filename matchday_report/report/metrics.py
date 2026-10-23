"""All football calculations for one matchday.

Sources
-------
report.xlsx   – complete counts for every match (passes, shots, duels, cards …)
timeline.xlsx – event coordinates; used for anything spatial or time-based
                (positions, zones, pass lengths, PPDA, possessions, goal minutes).

A match only feeds timeline-based numbers when its timeline is complete
(its event passes match the report's pass count). Partial timelines would
silently understate everything, so those matches show "–" instead.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

PITCH_L, PITCH_W = 105.0, 68.0
COVERAGE_OK = 0.98

# event groups --------------------------------------------------------------- #
PASS_ACTS = {"passing", "pass failed"}
SHOT_ACTS = {"shoot on target", "shoot off target", "shoot blocked"}
CROSS_ACTS = {"cross", "cross failed", "cross blocked"}
LOSS_ACTS = {"pass failed", "cross failed", "dribble failed", "loose ball"}
RECOVERY_ACTS = {"recovery ball", "intercept", "tackle"}
POSSESSION_ACTS = {"passing", "pass failed", "ball carry", "dribble success", "dribble failed",
                   "cross", "cross failed", "shoot on target", "shoot off target",
                   "shoot blocked", "goal kick", "throw in", "free kick", "corner",
                   "recovery ball", "intercept"}
TOUCH_ACTS = POSSESSION_ACTS | {"header", "header failed", "cross blocked", "loose ball",
                                "fouled", "duel won", "duel lost", "clearance", "tackle",
                                "keeper", "save", "cross claim", "block", "block cross",
                                "offside"}
PPDA_DEF_ACTS = {"tackle", "tackle failed", "intercept", "foul"}

INTERVALS = ["1-15'", "16-30'", "31-45+'", "46-60'", "61-75'", "76-90+'"]


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def short_name(full: str, nick=None) -> str:
    if isinstance(nick, str) and nick.strip():
        return nick.strip()
    parts = str(full).split()
    if len(parts) <= 1:
        return str(full)
    return f"{parts[0][0]}. {parts[-1]}"


def minute_label(sec: float, period: int) -> tuple[int, str]:
    """Return (football minute, display label) for a clock time in seconds."""
    m = int(math.floor(sec / 60.0)) + (1 if sec % 60 else 0)
    m = max(m, 1)
    if period == 1 and m > 45:
        return m, f"45+{m - 45}'"
    if period == 2 and m > 90:
        return m, f"90+{m - 90}'"
    return m, f"{m}'"


def interval_of(m: int, period: int) -> str:
    if period == 1:
        return INTERVALS[0] if m <= 15 else INTERVALS[1] if m <= 30 else INTERVALS[2]
    return INTERVALS[3] if m <= 60 else INTERVALS[4] if m <= 75 else INTERVALS[5]


def _s(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col] if col in df.columns else pd.Series(0, index=df.index)


def safe_div(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(b > 0, a / b, np.nan)
    return out


# --------------------------------------------------------------------------- #
@dataclass
class Matchday:
    report: pd.DataFrame
    timeline: pd.DataFrame | None
    gameweek: int
    rules: dict = field(default_factory=dict)        # groups + deductions, see standings.COMPETITION_RULES
    notes: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.report = self._ensure_columns(self.report)
        self.R = self.report[self.report["Gameweek"] == self.gameweek].copy()
        if self.R.empty:
            raise ValueError(f"No rows for gameweek {self.gameweek} in report file.")
        self.R["short"] = [short_name(n, k) for n, k in zip(self.R["Name"], self.R["Nick"])]
        tl = self.timeline if self.timeline is not None else pd.DataFrame(columns=["Match"])
        self.T_all = tl[tl["Match"].isin(self.R["Match"].unique())].copy()
        self.matches = self._build_matches()
        ok = self.matches.loc[self.matches["tl_complete"], "Match"]
        self.T = self.T_all[self.T_all["Match"].isin(ok)].copy()
        self._prep_events()
        self.team_match = self._build_team_match()
        self.teams = self._aggregate_teams()
        self.players = self._build_players()
        self.goal_events = self._goal_events()
        self._coverage_notes()

    # ------------------------------------------------------------------ #
    REQUIRED = ["Player Match ID", "Player ID", "Name", "Team", "Opponent", "Match", "Home/Away",
                "Date", "Result", "Gameweek", "MoP"]
    OPTIONAL_TEXT = {"Nick": None, "Venue": "", "Starter/Subs": "", "Subs": None,
                     "Position (in match)": ""}

    def _ensure_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Exports differ a little between competitions/seasons: fail clearly on truly
        required columns, fill everything else so the report still builds."""
        missing = [c for c in self.REQUIRED if c not in df.columns]
        if missing:
            raise ValueError("Report file is missing required column(s): " + ", ".join(missing))
        add = {}
        for c, default in self.OPTIONAL_TEXT.items():
            if c not in df.columns:
                add[c] = default
        absent_stats = [c for c in self.REPORT_SUM_COLS + ["Ball Possession"] if c not in df.columns]
        for c in absent_stats:
            add[c] = 0
        if absent_stats:
            self.notes.append("Columns not in the report file (shown as 0): " + ", ".join(absent_stats))
        return df.assign(**add) if add else df

    # ------------------------------------------------------------------ #
    # matches & coverage
    # ------------------------------------------------------------------ #
    def _build_matches(self) -> pd.DataFrame:
        rows = []
        for match, g in self.R.groupby("Match", sort=False):
            home_rows = g[g["Home/Away"].str.lower() == "home"]
            away_rows = g[g["Home/Away"].str.lower() == "away"]
            home = home_rows["Team"].iloc[0] if len(home_rows) else match.split(" - ")[0]
            away = away_rows["Team"].iloc[0] if len(away_rows) else g.loc[g.Team != home, "Team"].iloc[0]
            res = re.findall(r"\d+", str(g["Result"].iloc[0]))
            hg, ag = (int(res[0]), int(res[1])) if len(res) >= 2 else (np.nan, np.nan)
            date = pd.to_datetime(g["Date"].iloc[0], format="%d %b %Y %H:%M", errors="coerce")
            rep_passes = g["Passes"].sum()
            ev = self.T_all[self.T_all["Match"] == match]
            tl_passes = ev["Action"].isin(PASS_ACTS).sum() if len(ev) else 0
            cov = min(1.0, tl_passes / rep_passes) if rep_passes else 0.0
            rows.append(dict(Match=match, home=home, away=away, hg=hg, ag=ag, date=date,
                             venue=g["Venue"].iloc[0], tl_events=len(ev), coverage=cov,
                             tl_complete=cov >= COVERAGE_OK))
        m = pd.DataFrame(rows).sort_values(["date", "home"]).reset_index(drop=True)
        return m

    def _coverage_notes(self):
        bad = self.matches[~self.matches["tl_complete"]]
        if len(bad) and (self.matches["tl_events"] == 0).all():
            self.notes.append("No timeline data for this gameweek – event-based stats (positions, zones, "
                              "goal minutes, PPDA…) are not shown; match pages use nominal positions.")
            return
        for _, r in bad.iterrows():
            pct = f"timeline only {r.coverage:.0%} complete" if r.tl_events else "no timeline events"
            self.notes.append(f"{r.home} vs {r.away}: {pct} – event-based "
                              f"stats (positions, zones, goal minutes, PPDA…) not shown.")

    # ------------------------------------------------------------------ #
    # event preparation
    # ------------------------------------------------------------------ #
    def _prep_events(self):
        T = self.T
        if T.empty:
            return
        T["x1m"], T["y1m"] = T["X1"] * PITCH_L / 100, T["Y1"] * PITCH_W / 100
        T["x2m"], T["y2m"] = T["X2"] * PITCH_L / 100, T["Y2"] * PITCH_W / 100
        dx, dy = T["x2m"] - T["x1m"], T["y2m"] - T["y1m"]
        T["plen"] = np.hypot(dx, dy)
        ang = np.degrees(np.arctan2(dy.abs(), dx))
        T["dir"] = np.select([ang < 45, ang > 135], ["fwd", "back"], "lat")
        T.loc[dx.isna(), "dir"] = None
        T["third1"] = pd.cut(T["X1"], [-1, 100 / 3, 200 / 3, 101], labels=["own", "mid", "fin"])
        gx, gy = PITCH_L, PITCH_W / 2
        T["end_goal_dist"] = np.hypot(gx - T["x2m"], gy - T["y2m"])
        T["start_goal_dist"] = np.hypot(gx - T["x1m"], gy - T["y1m"])
        in_box = lambda x, y: (x >= 84.3) & (y >= 20.35) & (y <= 79.65)
        T["start_in_box"] = in_box(T["X1"], T["Y1"])
        T["end_in_box"] = in_box(T["X2"], T["Y2"])
        teams = self.matches.set_index("Match")[["home", "away"]]
        T["opp"] = [teams.at[m, "away"] if t == teams.at[m, "home"] else teams.at[m, "home"]
                    for m, t in zip(T["Match"], T["Team"])]
        self.T = T

    # ------------------------------------------------------------------ #
    # team x match
    # ------------------------------------------------------------------ #
    REPORT_SUM_COLS = [
        "Goals", "Own Goal", "Shots", "Shot on", "Shot off", "Shot Blocked", "Passes", "Pass",
        "Pass Fail", "Cross", "Cross Fail", "Cross Blocked", "Tackle", "Tackle Fail",
        "Tackle - Sliding Tackle", "Aerial Duels", "Aerial Won", "Duel Won - Defending",
        "Duel Won - Offensive", "Duel Lost - Defending", "Duel Lost - Offensive", "Dribble",
        "Dribble Fail", "Corner", "Freekick", "Foul", "Fouled", "Yellow Card", "Red Card",
        "Offside", "Intercept", "Recovery", "Block", "Key Pass", "Assist", "Create Chance",
        "Pass - Progressive Pass", "Pass - Long Ball", "Pass Fail - Long Ball", "Pass to Box",
        "Pass Fail - Pass to Box Failed", "Touch", "Penalty Goal", "Penalty Missed", "Throw In",
        "Ball Carry - Progressive Carry", "Save", "Clearance", "Miss Big Chance",
        "Shot on - Free Kick", "Shot off - Free Kick", "Shot Blocked - Free Kick",
        "Goal - Free Kick", "Loose Ball", "Concede Penalty",
    ]

    def _build_team_match(self) -> pd.DataFrame:
        cols = [c for c in self.REPORT_SUM_COLS if c in self.R.columns]
        tm = self.R.groupby(["Match", "Team"])[cols].sum()
        tm["possession"] = self.R.groupby(["Match", "Team"])["Ball Possession"].max()
        tm = tm.reset_index()
        mm = self.matches.set_index("Match")
        tm["opponent"] = [mm.at[m, "away"] if t == mm.at[m, "home"] else mm.at[m, "home"]
                          for m, t in zip(tm["Match"], tm["Team"])]
        tm["gf"] = [mm.at[m, "hg"] if t == mm.at[m, "home"] else mm.at[m, "ag"]
                    for m, t in zip(tm["Match"], tm["Team"])]
        tm["ga"] = [mm.at[m, "ag"] if t == mm.at[m, "home"] else mm.at[m, "hg"]
                    for m, t in zip(tm["Match"], tm["Team"])]
        tm["tl"] = tm["Match"].map(mm["tl_complete"])

        # derived counts from the report
        tm["passes_att"], tm["passes_acc"] = tm["Passes"], tm["Pass"]
        tm["cross_att"] = tm["Cross"] + tm["Cross Fail"] + tm["Cross Blocked"]
        tm["cross_acc"] = tm["Cross"]
        tm["drib_att"], tm["drib_acc"] = tm["Dribble"] + tm["Dribble Fail"], tm["Dribble"]
        tm["off_duel_att"] = tm["drib_att"] + tm["Duel Won - Offensive"] + tm["Duel Lost - Offensive"]
        tm["off_duel_won"] = tm["Dribble"] + tm["Duel Won - Offensive"]
        tm["def_duel_att"] = (tm["Tackle"] + tm["Tackle Fail"] + tm["Duel Won - Defending"]
                              + tm["Duel Lost - Defending"])
        tm["def_duel_won"] = tm["Tackle"] + tm["Duel Won - Defending"]
        tm["tackle_att"], tm["tackle_acc"] = tm["Tackle"] + tm["Tackle Fail"], tm["Tackle"]
        tm["long_att"] = tm["Pass - Long Ball"] + tm["Pass Fail - Long Ball"]
        tm["long_acc"] = tm["Pass - Long Ball"]
        tm["pen_att"] = tm["Penalty Goal"] + tm["Penalty Missed"]
        tm["pen_goals"] = tm["Penalty Goal"]
        tm["dfk_att"] = tm["Shot on - Free Kick"] + tm["Shot off - Free Kick"] + tm["Shot Blocked - Free Kick"]
        tm["dfk_goals"] = tm["Goal - Free Kick"]
        opp = tm.set_index(["Match", "Team"])
        tm["shots_against"] = [opp.loc[(m, o), "Shots"] for m, o in zip(tm.Match, tm.opponent)]
        tm["blocks_pct"] = safe_div(tm["Block"], tm["shots_against"]) * 100

        tl = self._timeline_team_metrics()
        if tl is not None and not tl.empty:
            tm = tm.merge(tl, on=["Match", "Team"], how="left")
            # shots-against geometry
            o = tl.set_index(["Match", "Team"])[["shot_dist"]]
            tm["shot_dist_against"] = [o["shot_dist"].get((m, t), np.nan)
                                       for m, t in zip(tm.Match, tm.opponent)]
        return tm

    def _timeline_team_metrics(self) -> pd.DataFrame | None:
        T = self.T
        if T.empty:
            return None
        out = []
        for (match, team), ev in T.groupby(["Match", "Team"]):
            r = {"Match": match, "Team": team}
            p = ev[ev["Action"].isin(PASS_ACTS)]
            ok = p["Action"] == "passing"
            for d in ("fwd", "lat", "back"):
                r[f"{d}_att"] = int((p["dir"] == d).sum())
                r[f"{d}_acc"] = int(((p["dir"] == d) & ok).sum())
            r["pass_len"] = p["plen"].mean()
            f3 = (p["X1"] < 200 / 3) & (p["X2"] >= 200 / 3)
            r["final3_att"], r["final3_acc"] = int(f3.sum()), int((f3 & ok).sum())
            r["deep_compl"] = int((ok & (p["end_goal_dist"] <= 20)).sum())
            bx = p["end_in_box"] & ~p["start_in_box"]
            r["box_pass_att"], r["box_pass_acc"] = int(bx.sum()), int((bx & ok).sum())
            prog = self._progressive(p)
            r["prog_att"], r["prog_acc"] = int(prog.sum()), int((prog & ok).sum())
            # transitions
            loss = ev[ev["Action"].isin(LOSS_ACTS)]
            rec = ev[ev["Action"].isin(RECOVERY_ACTS)]
            for z in ("own", "mid", "fin"):
                r[f"loss_{z}"] = int((loss["third1"] == z).sum())
                r[f"rec_{z}"] = int((rec["third1"] == z).sum())
            r["losses"], r["recoveries"] = len(loss), len(rec)
            # attack
            t = ev[ev["Action"].isin(TOUCH_ACTS)]
            r["box_touches"] = int(t["start_in_box"].sum())
            c = ev[ev["Action"].isin(CROSS_ACTS)]
            left = c["Y1"] < 50
            r["cross_l_att"], r["cross_l_acc"] = int(left.sum()), int((left & (c.Action == "cross")).sum())
            r["cross_r_att"], r["cross_r_acc"] = int((~left).sum()), int((~left & (c.Action == "cross")).sum())
            s = ev[ev["Action"].isin(SHOT_ACTS)]
            r["shot_dist"] = s["start_goal_dist"].mean() if len(s) else np.nan
            out.append(r)
        df = pd.DataFrame(out)
        df = df.merge(self._ppda(), on=["Match", "Team"], how="left")
        df = df.merge(self._possessions(), on=["Match", "Team"], how="left")
        df = df.merge(self._corners_summary(), on=["Match", "Team"], how="left")
        return df

    @staticmethod
    def _progressive(p: pd.DataFrame) -> pd.Series:
        """Glossary rule: distance to goal reduced by 30 m (own half), 15 m (crossing
        halfway), 10 m (opponent half)."""
        gain = p["start_goal_dist"] - p["end_goal_dist"]
        own1, own2 = p["X1"] < 50, p["X2"] < 50
        need = np.where(own1 & own2, 30, np.where(~own1 & ~own2, 10, 15))
        return (gain >= need).fillna(False)

    def _ppda(self) -> pd.DataFrame:
        T, rows = self.T, []
        for (match, team), ev in T.groupby(["Match", "Team"]):
            opp_ev = T[(T["Match"] == match) & (T["Team"] != team)]
            opp_passes = (opp_ev["Action"].isin(PASS_ACTS) & (opp_ev["X1"] <= 60)).sum()
            d = ev[(ev["X1"] >= 40) & (ev["Action"].isin(PPDA_DEF_ACTS) |
                   ((ev["Action"].isin({"duel won", "duel lost"})) & (ev["Sub 1"] == "Defending")))]
            rows.append({"Match": match, "Team": team,
                         "ppda": opp_passes / len(d) if len(d) else np.nan})
        return pd.DataFrame(rows)

    def _possessions(self) -> pd.DataFrame:
        rows = []
        for (match, period), ev in self.T.groupby(["Match", "period"]):
            ev = ev[ev["Action"].isin(POSSESSION_ACTS)].sort_values(["sec", "ID"])
            if ev.empty:
                continue
            change = ev["Team"] != ev["Team"].shift()
            starts = ev[change][["Team", "sec"]].copy()
            starts["end"] = starts["sec"].shift(-1).fillna(ev["sec"].max())
            starts["dur"] = (starts["end"] - starts["sec"]).clip(lower=0)
            starts["Match"] = match
            rows.append(starts)
        if not rows:
            return pd.DataFrame(columns=["Match", "Team"])
        P = pd.concat(rows)
        g = P.groupby(["Match", "Team"])["dur"]
        out = pd.DataFrame({
            "n_poss": g.size(),
            "poss_lt5": g.apply(lambda s: (s < 5).sum()),
            "poss_5_15": g.apply(lambda s: ((s >= 5) & (s < 15)).sum()),
            "poss_15_45": g.apply(lambda s: ((s >= 15) & (s < 45)).sum()),
            "poss_45": g.apply(lambda s: (s >= 45).sum()),
            "poss_avg": g.mean(),
        }).reset_index()
        return out

    def corner_events(self) -> pd.DataFrame:
        T = self.T
        if T.empty:
            return pd.DataFrame()
        c = T[T["Action"] == "corner"].copy()
        if c.empty:
            return c
        c["side"] = np.where(c["Y1"] < 50, "left", "right")
        # The corner row has no end point: the delivery is the next pass/cross by
        # the same team. If that delivery starts away from the flag, it was short.
        deliveries = T[T["Action"].isin(PASS_ACTS | CROSS_ACTS)]
        ends, short = [], []
        for _, e in c.iterrows():
            nxt = deliveries[(deliveries.Match == e.Match) & (deliveries.Team == e.Team) &
                             (deliveries.period == e.period) & (deliveries.sec >= e.sec) &
                             (deliveries.sec <= e.sec + 10)]
            if nxt.empty:
                # no logged delivery: use the first touch by anyone (defenders mirrored)
                first = T[(T.Match == e.Match) & (T.period == e.period) & (T.sec >= e.sec) &
                          (T.sec <= e.sec + 6) & (T.ID != e.ID) & T.X1.notna()]
                if first.empty:
                    ends.append((np.nan, np.nan)); short.append(False); continue
                f = first.iloc[0]
                x, y = (f.X1, f.Y1) if f.Team == e.Team else (100 - f.X1, 100 - f.Y1)
                ends.append((x, y)); short.append(False); continue
            d = nxt.iloc[0]
            from_flag = d.X1 >= 96 and (d.Y1 <= 5 or d.Y1 >= 95)
            ends.append((d.X2, d.Y2) if from_flag else (d.X1, d.Y1))
            short.append(not from_flag)
        c["X2"], c["Y2"] = [e[0] for e in ends], [e[1] for e in ends]
        c["is_short"] = short
        ex, ey = c["X2"] * PITCH_L / 100, c["Y2"] * PITCH_W / 100
        box = (c["X2"] >= 84.3) & (c["Y2"] >= 20.35) & (c["Y2"] <= 79.65)
        gk = (ex >= 99.5) & (ey >= 24.84) & (ey <= 43.16)
        near_side = np.where(c["side"] == "left", ey < 34, ey >= 34)
        close = ex >= 94.5
        c["target"] = np.select(
            [c["X2"].isna(), c["is_short"] | ~box, gk, close & near_side, close & ~near_side],
            ["unknown", "short", "gk", "near", "far"], "penalty")
        # shot by the same team within 15 s
        shots = T[T["Action"].isin(SHOT_ACTS)]
        c["with_shot"] = [
            bool(((shots.Match == m) & (shots.Team == t) & (shots.period == p) &
                  (shots.sec >= s) & (shots.sec <= s + 15)).any())
            for m, t, p, s in zip(c.Match, c.Team, c.period, c.sec)]
        return c

    def _corners_summary(self) -> pd.DataFrame:
        c = self.corner_events()
        if c.empty:
            return pd.DataFrame(columns=["Match", "Team"])
        rows = []
        for (m, t), g in c.groupby(["Match", "Team"]):
            r = {"Match": m, "Team": t, "corners_tl": len(g), "corners_shot": int(g.with_shot.sum())}
            for z in ("near", "far", "penalty", "gk", "short"):
                r[f"cor_{z}"] = int((g.target == z).sum())
                r[f"cor_{z}_shot"] = int(((g.target == z) & g.with_shot).sum())
            rows.append(r)
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ #
    def _aggregate_teams(self) -> pd.DataFrame:
        tm = self.team_match
        num = tm.select_dtypes("number").columns
        mean_cols = [c for c in ["possession", "pass_len", "shot_dist", "shot_dist_against",
                                 "ppda", "poss_avg", "blocks_pct"] if c in tm.columns]
        agg = {c: ("mean" if c in mean_cols else "sum") for c in num}
        teams = tm.groupby("Team").agg(agg).copy()
        tl_n = tm.groupby("Team")["tl"].sum()
        for c in self._TL_COLS:                       # no/partial timeline: columns still exist
            if c not in teams.columns:
                teams[c] = np.nan
        teams["matches"] = tm.groupby("Team").size()
        teams["tl"] = tl_n > 0
        # timeline-only columns are meaningless for teams without a complete timeline
        tl_cols = [c for c in teams.columns if c in self._TL_COLS]
        teams.loc[~teams["tl"], tl_cols] = np.nan
        return teams.reset_index()

    _TL_COLS = {"fwd_att", "fwd_acc", "lat_att", "lat_acc", "back_att", "back_acc", "pass_len",
                "final3_att", "final3_acc", "deep_compl", "box_pass_att", "box_pass_acc", "prog_att", "prog_acc",
                "loss_own", "loss_mid", "loss_fin", "rec_own", "rec_mid", "rec_fin", "losses",
                "recoveries", "box_touches", "cross_l_att", "cross_l_acc", "cross_r_att",
                "cross_r_acc", "shot_dist", "shot_dist_against", "ppda", "n_poss", "poss_lt5",
                "poss_5_15", "poss_15_45", "poss_45", "poss_avg", "corners_tl", "corners_shot",
                "cor_near", "cor_far", "cor_penalty", "cor_gk", "cor_short", "cor_near_shot",
                "cor_far_shot", "cor_penalty_shot", "cor_gk_shot", "cor_short_shot"}

    # ------------------------------------------------------------------ #
    # players
    # ------------------------------------------------------------------ #
    def _build_players(self) -> pd.DataFrame:
        R = self.R[self.R["MoP"] > 0]
        cols = [c for c in self.REPORT_SUM_COLS if c in R.columns] + ["MoP"]
        P = R.groupby(["Player ID"])[cols].sum()
        first = R.groupby("Player ID")[["Name", "short", "Team"]].first()
        P = first.join(P).reset_index()
        P["cross_att"] = P["Cross"] + P["Cross Fail"] + P["Cross Blocked"]
        P["drib_att"] = P["Dribble"] + P["Dribble Fail"]
        P["off_duel_att"] = P["drib_att"] + P["Duel Won - Offensive"] + P["Duel Lost - Offensive"]
        P["off_duel_won"] = P["Dribble"] + P["Duel Won - Offensive"]
        P["def_duel_att"] = P["Tackle"] + P["Tackle Fail"] + P["Duel Won - Defending"] + P["Duel Lost - Defending"]
        P["def_duel_won"] = P["Tackle"] + P["Duel Won - Defending"]
        P["duels_att"] = P["off_duel_att"] + P["def_duel_att"] + P["Aerial Duels"]
        P["duels_won"] = P["off_duel_won"] + P["def_duel_won"] + P["Aerial Won"]
        P["pen_att"] = P["Penalty Goal"] + P["Penalty Missed"]
        P["dfk_att"] = P["Shot on - Free Kick"] + P["Shot off - Free Kick"] + P["Shot Blocked - Free Kick"]
        P["shots_on"] = P["Shot on"]
        for c in ["final3_att", "final3_acc", "deep_compl", "box_touches", "box_pass_att", "box_pass_acc"]:
            P[c] = np.nan
        if not self.T.empty and "Player Match ID" in self.T.columns:
            P = P.drop(columns=["final3_att", "final3_acc", "deep_compl", "box_touches",
                                "box_pass_att", "box_pass_acc"])
            pid = self.R.set_index("Player Match ID")["Player ID"]
            T = self.T.copy()
            T["pid"] = T["Player Match ID"].map(pid)
            p = T[T["Action"].isin(PASS_ACTS)]
            ok = p["Action"] == "passing"
            f3 = (p["X1"] < 200 / 3) & (p["X2"] >= 200 / 3)
            g = pd.DataFrame({
                "final3_att": f3.groupby(p["pid"]).sum(),
                "final3_acc": (f3 & ok).groupby(p["pid"]).sum(),
                "deep_compl": (ok & (p["end_goal_dist"] <= 20)).groupby(p["pid"]).sum(),
                "box_pass_att": (p["end_in_box"] & ~p["start_in_box"]).groupby(p["pid"]).sum(),
                "box_pass_acc": (ok & p["end_in_box"] & ~p["start_in_box"]).groupby(p["pid"]).sum(),
            })
            touches = T[T["Action"].isin(TOUCH_ACTS) & T["start_in_box"]].groupby("pid").size()
            g["box_touches"] = touches
            P = P.merge(g, left_on="Player ID", right_index=True, how="left")
            # players whose match had no complete timeline -> NaN rather than 0
            covered = set(self.T["Player Match ID"].dropna().map(pid).dropna())
            for c in ["final3_att", "final3_acc", "deep_compl", "box_touches", "box_pass_att", "box_pass_acc"]:
                P[c] = np.where(P["Player ID"].isin(covered), P[c].fillna(0), np.nan)
        return P

    # ------------------------------------------------------------------ #
    # goals / scorers / positions
    # ------------------------------------------------------------------ #
    def _goal_events(self) -> pd.DataFrame:
        T = self.T
        if T.empty:
            return pd.DataFrame(columns=["Match", "Team", "scorer", "minute", "label", "kind",
                                         "period", "interval", "for_team", "against_team"])
        g = T[T["Action"].isin({"goal", "penalty goal"}) | T["Action"].str.contains("own goal", na=False)].copy()
        g = g.drop_duplicates(["Match", "period", "sec", "Act Name", "Action"])
        rows = []
        for _, e in g.iterrows():
            m, lab = minute_label(e["sec"], e["period"])
            own = "own goal" in e["Action"]
            for_team = e["opp"] if own else e["Team"]
            rows.append(dict(Match=e["Match"], Team=e["Team"], scorer=short_name(e["Act Name"]),
                             minute=m, label=lab, period=e["period"], sec=e["sec"],
                             kind="og" if own else ("pen" if e["Action"] == "penalty goal" else "goal"),
                             interval=interval_of(m, e["period"]), for_team=for_team,
                             against_team=e["Team"] if own else e["opp"]))
        return pd.DataFrame(rows).sort_values(["Match", "period", "sec"])

    def match_events(self, match: str) -> pd.DataFrame:
        """Goals and red cards for the match header (minute-ordered)."""
        mrow = self.matches.set_index("Match").loc[match]
        if mrow.tl_complete:
            ge = self.goal_events[self.goal_events.Match == match]
            ev = [dict(team=r.for_team, label=r.label, name=r.scorer + (" (P)" if r.kind == "pen" else
                       " (OG)" if r.kind == "og" else ""), icon="goal", key=(r.period, r.sec))
                  for r in ge.itertuples()]
            reds = self.T[(self.T.Match == match) & (self.T.Action.str.contains("red card", na=False))]
            for _, r in reds.iterrows():
                _, lab = minute_label(r.sec, r.period)
                ev.append(dict(team=r.Team, label=lab, name=short_name(r["Act Name"]), icon="red",
                               key=(r.period, r.sec)))
            return pd.DataFrame(ev).sort_values("key") if ev else pd.DataFrame(
                columns=["team", "label", "name", "icon", "key"])
        # fallback: scorer names from the report, no minutes
        R = self.R[self.R.Match == match]
        ev = []
        for _, r in R[R["Goals"] > 0].iterrows():
            ev += [dict(team=r.Team, label="", name=r.short, icon="goal", key=(0, 0))] * int(r.Goals)
        for _, r in R[R["Red Card"] > 0].iterrows():
            ev.append(dict(team=r.Team, label="", name=r.short, icon="red", key=(0, 0)))
        return pd.DataFrame(ev) if ev else pd.DataFrame(columns=["team", "label", "name", "icon", "key"])

    NOMINAL = {  # (x along pitch 0-100, y across 0-100 with 0 = left)
        "GK": (6, 50), "CB": (22, 50), "LCB": (22, 35), "RCB": (22, 65), "LB": (28, 12),
        "RB": (28, 88), "LWB": (42, 10), "RWB": (42, 90), "DM": (38, 50), "CM": (50, 50),
        "LM": (56, 12), "RM": (56, 88), "CAM": (64, 50), "LAM": (66, 20), "RAM": (66, 80),
        "LFW": (76, 18), "RFW": (76, 82), "LW": (72, 15), "RW": (72, 85), "CF": (80, 50),
        "SS": (72, 50),
    }

    def lineup_positions(self, match: str, team: str) -> tuple[pd.DataFrame, bool]:
        """Average positions (timeline) or nominal positions (fallback).
        Returns (df[x, y, label, role, subbed_off], is_average)."""
        R = self.R[(self.R.Match == match) & (self.R.Team == team)].copy()
        R["role"] = np.where(R["Starter/Subs"].str.lower().str.startswith("starter"), "starter",
                             np.where(R["Starter/Subs"].str.lower().str.contains("in"), "sub_in", "bench"))
        R = R[R.role != "bench"]
        R["subbed_off"] = R["Subs"].notna() & (R["Subs"].astype(str).str.strip() != "") & (R.role == "starter")
        mrow = self.matches.set_index("Match").loc[match]
        if mrow.tl_complete:
            ev = self.T[(self.T.Match == match) & self.T.Action.isin(TOUCH_ACTS) & self.T.X1.notna()]
            pos = ev.groupby("Player Match ID").agg(x=("X1", "mean"), y=("Y1", "mean"),
                                                     num=("Num", lambda s: s.mode().iat[0] if len(s.mode()) else np.nan))
            R = R.merge(pos, left_on="Player Match ID", right_index=True, how="left")
            R = R[R.x.notna()]
            R["label"] = R["num"].map(lambda v: "" if pd.isna(v) else str(int(v)))
            return R[["x", "y", "label", "role", "subbed_off", "short", "Position (in match)"]], True
        S = R[R.role == "starter"].copy()
        xs, ys = [], []
        for pos, grp in S.groupby("Position (in match)"):
            bx, by = self.NOMINAL.get(str(pos).upper(), (50, 50))
            n = len(grp)
            spread = 22 if n > 1 else 0
            offs = np.linspace(-spread, spread, n) if n > 1 else [0]
            for (idx, _), o in zip(grp.iterrows(), offs):
                xs.append((idx, bx, by + o))
        for idx, x, y in xs:
            S.loc[idx, "x"], S.loc[idx, "y"] = x, y
        S["label"] = S["Position (in match)"].astype(str)
        return S[["x", "y", "label", "role", "subbed_off", "short", "Position (in match)"]], False

    def match_stat_lines(self, match: str) -> list[tuple[str, float, float, str]]:
        tm = self.team_match.set_index(["Match", "Team"])
        mrow = self.matches.set_index("Match").loc[match]
        h, a = tm.loc[(match, mrow.home)], tm.loc[(match, mrow.away)]
        lines = [("Possession", h.possession, a.possession, "pct"),
                 ("Shots", h.Shots, a.Shots, "int"),
                 ("On target", h["Shot on"], a["Shot on"], "int"),
                 ("Passes", h.Passes, a.Passes, "int"),
                 ("Pass accuracy", 100 * h.Pass / max(h.Passes, 1), 100 * a.Pass / max(a.Passes, 1), "pct"),
                 ("PPDA", h.get("ppda", np.nan), a.get("ppda", np.nan), "f2"),
                 ("Corners", h.Corner, a.Corner, "int"),
                 ("Free kicks", h.Freekick, a.Freekick, "int"),
                 ("Fouls", h.Foul, a.Foul, "int"),
                 ("Yellow cards", h["Yellow Card"], a["Yellow Card"], "int"),
                 ("Red cards", h["Red Card"], a["Red Card"], "int")]
        return lines

    # ------------------------------------------------------------------ #
    # standings (cumulative up to this gameweek)
    # ------------------------------------------------------------------ #
    def standings(self) -> list[tuple[str | None, pd.DataFrame]]:
        """Regulation tables: [(group name or None, table)], see standings.py."""
        from .standings import league_tables
        tables, notes = league_tables(self.report[self.report["Gameweek"] <= self.gameweek], self.rules,
                                      self.gameweek)
        for n in notes:
            if n not in self.notes:
                self.notes.append(n)
        return tables

    # goal-dynamics tables -------------------------------------------------- #
    def goal_dynamics(self, conceded: bool = False) -> pd.DataFrame:
        ge = self.goal_events
        if ge.empty:
            return pd.DataFrame()
        key = "against_team" if conceded else "for_team"
        t = pd.crosstab(ge[key], ge["interval"]).reindex(columns=INTERVALS, fill_value=0)
        t.insert(0, "2nd half", t[INTERVALS[3:]].sum(axis=1))
        t.insert(0, "1st half", t[INTERVALS[:3]].sum(axis=1))
        t.insert(0, "Total", t["1st half"] + t["2nd half"])
        t = t.sort_values(["Total", "1st half"], ascending=[conceded, False])
        t.index.name = "Team"
        return t
