"""League tables with the regulation tie-breakers, groups and point deductions.

Order inside a table: points (after deductions) -> among teams level on points:
head-to-head points, head-to-head goal difference, head-to-head goals scored ->
overall goal difference -> overall goals scored.

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
    """One row per match: Home, Away, FTHG, FTAG (from the 'Match' and 'Result' columns)."""
    keys = ["Match", "Result"] + (["Date"] if "Date" in data.columns else [])
    uk = data[keys].drop_duplicates().copy()
    uk["Home"] = uk["Match"].str.split(" - ", n=1).str[0].str.strip()
    uk["Away"] = uk["Match"].str.split(" - ", n=1).str[1].str.strip()
    uk["FTHG"] = uk["Result"].str.split("-").str[0].str.strip().astype(int)
    uk["FTAG"] = uk["Result"].str.split("-").str[1].str.strip().astype(int)
    return uk[["Home", "Away", "FTHG", "FTAG"]].reset_index(drop=True)


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


def table(df_results: pd.DataFrame, teams, deductions: dict[str, int] | None = None) -> pd.DataFrame:
    """One ranked table for `teams` (results involving other teams are ignored)."""
    deductions = deductions or {}
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
    groups = []
    for pts in sorted(df["Pts"].unique(), reverse=True):
        group = df[df["Pts"] == pts].copy()
        if len(group) > 1:
            tied = pd.merge(group, _h2h(group["Team"].tolist(), res), on="Team", how="left")
            groups.append(tied.sort_values(["H2H_Pts", "H2H_GD", "H2H_GF", "GD", "GF"],
                                           ascending=False, kind="stable")[df.columns])
        else:
            groups.append(group)
    out = pd.concat(groups).reset_index(drop=True)
    out = out[["Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts", "Adj"]]
    out.insert(0, "Pos", range(1, len(out) + 1))
    return out


def league_tables(data: pd.DataFrame, rules: dict | None = None) -> tuple[list[tuple[str | None, pd.DataFrame]], list[str]]:
    """data: report rows up to the gameweek being reported.
    Returns ([(group name or None, table), ...], notes)."""
    rules = rules or {}
    notes: list[str] = []
    res = results_from_report(data)
    data_teams = sorted(set(res["Home"]) | set(res["Away"]))

    def to_data(name):
        hit = resolve(name, data_teams)
        return hit if hit else name            # club with no matches yet keeps its configured name

    deductions = {}
    for name, pts in (rules.get("deductions") or {}).items():
        deductions[to_data(name)] = pts
    groups = rules.get("groups")
    if not groups:
        teams = data_teams + [to_data(t) for t in rules.get("teams", [])] + list(deductions)
        return [(None, table(res, teams, deductions))], notes

    out, placed = [], set()
    for gname, members in groups.items():
        teams = [to_data(t) for t in members]
        placed |= set(teams)
        out.append((gname, table(res, teams, {t: p for t, p in deductions.items() if t in teams})))
    stray = [t for t in data_teams if t not in placed]
    if stray:
        notes.append("Teams in the data but not in any group (add them to COMPETITION_RULES in "
                     "report/standings.py): " + ", ".join(stray))
        out.append(("Unassigned", table(res, stray)))
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
