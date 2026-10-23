"""League tables with the regulation tie-breakers, groups and point deductions.

Order inside a table: points (after deductions) -> among teams level on points:
head-to-head points, head-to-head goal difference, head-to-head goals scored ->
overall goal difference -> overall goals scored -> fair-play points (fewer is better).

Fair-play points per player per match: yellow card 1, two yellows (second-yellow
red) 3, straight red 3, yellow followed by a straight red 4.

Results awarded by the competition (walkovers etc.) are listed per competition
under "awarded" and count from their gameweek onward.

Per-competition rules live in COMPETITION_RULES (keyed by the theme name in
theme.py). Team names there do not need to match the data letter for letter:
"PS. BARITO PUTERA" matches "Barito Putera" or "PS Barito Putera FC" (case,
punctuation and the words FC / PS are ignored; one name may contain the other).
"""
from __future__ import annotations

import re

import pandas as pd

COMPETITION_RULES: dict[str, dict] = {
    "BRI Super League": {
        "groups": None,                                   # single table
        "deductions": {"Isenmulang Kalteng FC": -2, "Java United FC": -2},
    },
    "Pegadaian Championship": {
        "groups": {
            "Group A": ["Adhyaksa FC Bekasi", "Persikad", "PSGC Ciamis", "PSMS Medan", "PSPS Pekanbaru",
                        "Persiraja Banda Aceh", "PSIS Semarang", "Semen Padang FC", "Sumsel United",
                        "Persiku"],
            "Group B": ["De Red FC", "Deltras FC", "Persis", "PS. Barito Putera", "RANS Nusantara FC",
                        "Kendal Tornado FC", "Persela Lamongan", "Persipura Jayapura",
                        "Persiba Balikpapan", "PSBS Biak"],
        },
        "deductions": {"Persiraja Banda Aceh": -1, "PSIS Semarang": -1, "Semen Padang FC": -1,
                       "Sumsel United": -1, "Persiku": -2,
                       "Kendal Tornado FC": -1, "Persela Lamongan": -1, "Persipura Jayapura": -1,
                       "Persiba Balikpapan": -4, "PSBS Biak": -4},
        # results decided off the pitch; they replace any recorded result for that fixture/gameweek
        "awarded": [
            {"gameweek": 3, "home": "PSIS Semarang", "away": "Persiku", "score": (3, 0), "label": "WO"},
        ],
    },
    "Indonesian Women's League": {
        "groups": None,
        # optional: list the 6 clubs so they appear in the table before their first match
        "teams": [],
        "deductions": {},
    },
}


def rules_for(competition: str) -> dict:
    from .theme import theme_for
    return COMPETITION_RULES.get(theme_for(competition).name, {"groups": None, "deductions": {}})


# --------------------------------------------------------------------------- #
# name matching
# --------------------------------------------------------------------------- #
from .theme import match_name as resolve, name_tokens as _tokens  # noqa: E402  (shared matcher)


# --------------------------------------------------------------------------- #
def results_from_report(data: pd.DataFrame) -> pd.DataFrame:
    """One row per match: Gameweek, Home, Away, FTHG, FTAG (from 'Match' and 'Result')."""
    keys = ["Match", "Result"] + [c for c in ("Date", "Gameweek") if c in data.columns]
    uk = data[keys].drop_duplicates().copy()
    uk["Home"] = uk["Match"].str.split(" - ", n=1).str[0].str.strip()
    uk["Away"] = uk["Match"].str.split(" - ", n=1).str[1].str.strip()
    uk["FTHG"] = uk["Result"].str.split("-").str[0].str.strip().astype(int)
    uk["FTAG"] = uk["Result"].str.split("-").str[1].str.strip().astype(int)
    if "Gameweek" not in uk:
        uk["Gameweek"] = 0
    return uk[["Gameweek", "Home", "Away", "FTHG", "FTAG"]].reset_index(drop=True)


def awarded_results(rules: dict, data_teams, up_to_gameweek: int | None) -> list[dict]:
    """Configured walkovers etc. up to a gameweek, with names resolved to the data's spelling."""
    out = []
    for a in rules.get("awarded") or []:
        if up_to_gameweek is not None and a["gameweek"] > up_to_gameweek:
            continue
        home = resolve(a["home"], data_teams) or a["home"]
        away = resolve(a["away"], data_teams) or a["away"]
        out.append(dict(Gameweek=a["gameweek"], Home=home, Away=away, FTHG=int(a["score"][0]),
                        FTAG=int(a["score"][1]), label=a.get("label", "awarded")))
    return out


def fair_play_points(data: pd.DataFrame) -> dict[str, int]:
    """Team -> fair-play points (1 yellow, 3 second-yellow red, 3 straight red, 4 yellow + straight red)."""
    if "Yellow Card" not in data or "Red Card" not in data:
        return {}
    y = data["Yellow Card"].fillna(0)
    r = data["Red Card"].fillna(0)
    two_y = data["Red Card - Two Yellow Card"].fillna(0) if "Red Card - Two Yellow Card" in data else 0 * r
    pts = (y.where(r == 0, 0)                                     # yellows only
           + 3 * ((r > 0) & ((two_y > 0) | (y >= 2)))             # sent off for a second yellow
           + 3 * ((r > 0) & (two_y == 0) & (y == 0))              # straight red
           + 4 * ((r > 0) & (two_y == 0) & (y == 1)))             # yellow, then straight red
    return pts.groupby(data["Team"]).sum().astype(int).to_dict()


def _h2h(tied_teams, df_all_results):
    h2h_matches = df_all_results[df_all_results["Home"].isin(tied_teams) &
                                 df_all_results["Away"].isin(tied_teams)]
    h2h = {t: {"H2H_Pts": 0, "H2H_GF": 0, "H2H_GA": 0} for t in tied_teams}
    for _, row in h2h_matches.iterrows():
        home, away, fthg, ftag = row["Home"], row["Away"], row["FTHG"], row["FTAG"]
        pts_home, pts_away = (3, 0) if fthg > ftag else ((0, 3) if ftag > fthg else (1, 1))
        h2h[home]["H2H_Pts"] += pts_home
        h2h[away]["H2H_Pts"] += pts_away
        h2h[home]["H2H_GF"] += fthg
        h2h[home]["H2H_GA"] += ftag
        h2h[away]["H2H_GF"] += ftag
        h2h[away]["H2H_GA"] += fthg
    df = pd.DataFrame.from_dict(h2h, orient="index").reset_index().rename(columns={"index": "Team"})
    df["H2H_GD"] = df["H2H_GF"] - df["H2H_GA"]
    return df


def table(df_results: pd.DataFrame, teams, deductions: dict[str, int] | None = None,
          fair_play: dict[str, int] | None = None) -> pd.DataFrame:
    """One ranked table for `teams` (results involving other teams are ignored)."""
    deductions = deductions or {}
    fair_play = fair_play or {}
    teams = list(dict.fromkeys(teams))
    res = df_results[df_results["Home"].isin(teams) & df_results["Away"].isin(teams)]
    stats = {t: {"P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0, "Pts": 0} for t in teams}

    def update(team, played, win, draw, loss, gf, ga, pts):
        s = stats[team]
        s["P"] += played; s["W"] += win; s["D"] += draw; s["L"] += loss
        s["GF"] += gf; s["GA"] += ga; s["Pts"] += pts

    for _, row in res.iterrows():
        home, away, fthg, ftag = row["Home"], row["Away"], row["FTHG"], row["FTAG"]
        if fthg > ftag:
            update(home, 1, 1, 0, 0, fthg, ftag, 3); update(away, 1, 0, 0, 1, ftag, fthg, 0)
        elif ftag > fthg:
            update(home, 1, 0, 0, 1, fthg, ftag, 0); update(away, 1, 1, 0, 0, ftag, fthg, 3)
        else:
            update(home, 1, 0, 1, 0, fthg, ftag, 1); update(away, 1, 0, 1, 0, ftag, fthg, 1)
    for team, pts in deductions.items():
        if team in stats:
            stats[team]["Pts"] += pts

    df = pd.DataFrame.from_dict(stats, orient="index").reset_index().rename(columns={"index": "Team"})
    df["GD"] = df["GF"] - df["GA"]
    df["Adj"] = df["Team"].map(deductions).fillna(0).astype(int)
    df["FP"] = df["Team"].map(fair_play).fillna(0).astype(int)
    groups = []
    for pts in sorted(df["Pts"].unique(), reverse=True):
        group = df[df["Pts"] == pts].copy()
        if len(group) > 1:
            tied = pd.merge(group, _h2h(group["Team"].tolist(), res), on="Team", how="left")
            groups.append(tied.sort_values(["H2H_Pts", "H2H_GD", "H2H_GF", "GD", "GF", "FP"],
                                           ascending=[False] * 5 + [True], kind="stable")[df.columns])
        else:
            groups.append(group)
    out = pd.concat(groups).reset_index(drop=True)
    out = out[["Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts", "Adj", "FP"]]
    out.insert(0, "Pos", range(1, len(out) + 1))
    return out


def league_tables(data: pd.DataFrame, rules: dict | None = None, gameweek: int | None = None
                  ) -> tuple[list[tuple[str | None, pd.DataFrame]], list[str]]:
    """data: report rows up to the gameweek being reported.
    Returns ([(group name or None, table), ...], notes)."""
    rules = rules or {}
    notes: list[str] = []
    res = results_from_report(data)
    data_teams = sorted(set(res["Home"]) | set(res["Away"]))
    for a in awarded_results(rules, data_teams, gameweek):
        same = (res["Gameweek"] == a["Gameweek"]) & (
            ((res["Home"] == a["Home"]) & (res["Away"] == a["Away"])) |
            ((res["Home"] == a["Away"]) & (res["Away"] == a["Home"])))
        res = pd.concat([res[~same], pd.DataFrame([{k: a[k] for k in res.columns}])], ignore_index=True)
        notes.append(f"Awarded result ({a['label']}), gameweek {a['Gameweek']}: "
                     f"{a['Home']} {a['FTHG']}–{a['FTAG']} {a['Away']}.")
    fp = fair_play_points(data)

    def to_data(name):
        hit = resolve(name, data_teams)
        return hit if hit else name            # club with no matches yet keeps its configured name

    deductions = {}
    for name, pts in (rules.get("deductions") or {}).items():
        deductions[to_data(name)] = pts
    groups = rules.get("groups")
    if not groups:
        teams = data_teams + [to_data(t) for t in rules.get("teams", [])] + list(deductions)
        return [(None, table(res, teams, deductions, fp))], notes

    out, placed = [], set()
    for gname, members in groups.items():
        teams = [to_data(t) for t in members]
        placed |= set(teams)
        out.append((gname, table(res, teams, {t: p for t, p in deductions.items() if t in teams}, fp)))
    stray = [t for t in data_teams if t not in placed]
    if stray:
        notes.append("Teams in the data but not in any group (add them to COMPETITION_RULES in "
                     "report/standings.py): " + ", ".join(stray))
        out.append(("Unassigned", table(res, stray, fair_play=fp)))
    return out, notes


def standings(data: pd.DataFrame, deductions: dict[str, int] | None = None) -> pd.DataFrame:
    """Single-table shortcut (kept for compatibility)."""
    return league_tables(data, {"deductions": deductions or {}})[0][0][1]


def guess_competition(team_names) -> str | None:
    """Theme name whose configured clubs best match these team names (None if no overlap)."""
    teams = list(team_names)
    best, best_score = None, 0.0
    for comp, rules in COMPETITION_RULES.items():
        names = list(rules.get("teams") or []) + list(rules.get("deductions") or {})
        for members in (rules.get("groups") or {}).values():
            names += members
        names = list(dict.fromkeys(names))
        if not names:
            continue
        score = sum(resolve(n, teams) is not None for n in names) / len(names)
        if score > best_score:
            best, best_score = comp, score
    return best if best_score >= 0.5 else None
