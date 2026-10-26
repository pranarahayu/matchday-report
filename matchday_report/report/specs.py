"""Which tables appear on which page – shared by the PDF builder and the Streamlit app.

Column kinds
  int  : whole number          f1 / f2 : decimals          pct : "52.3%"
  pair : "attempts/successful 42%"  (key = attempts, key2 = successful)
  part : "count 23%" where the % is share of `key2` (a total)
"""
from dataclasses import dataclass, field


@dataclass
class Col:
    label: str
    key: str
    kind: str = "int"
    key2: str | None = None
    mode: str | None = None     # "xg" = only with xG on, "base" = only with xG off, "xt" = only with xT on


@dataclass
class Table:
    title: str
    sort: str                   # column used for ranking
    cols: list
    ascending: bool = False
    avg: bool = True            # show a league-average row (teams only)
    timeline: bool = False      # needs complete event data
    wide: bool = False          # full page width
    mode: str | None = None     # "xg" / "xt" = whole table only when that metric is on


# ----------------------------------------------------------------------------
TEAM_PAGES = {
    "Teams: overview": [
        Table("Goals", "gf", [Col("Total", "gf"), Col("xG", "xg", "f2", mode="xg"), Col("Shots", "Shots"),
                              Col("On target", "Shot on", mode="base")], avg=False),
        Table("Conceded goals", "ga", [Col("Total", "ga"), Col("xG against", "xg_against", "f2", mode="xg"),
                                       Col("Shots against", "shots_against", mode="base")],
              ascending=True, avg=False),
        Table("Shots", "Shots", [Col("Total", "Shots"), Col("On target", "Shot on"),
                                 Col("Avg dist., m", "shot_dist", "f1", mode="base"),
                                 Col("xG/shot", "xg_per_shot", "f2", mode="xg")]),
        Table("Shots against", "shots_against", [Col("Total", "shots_against"),
                                                 Col("Avg dist., m", "shot_dist_against", "f1"),
                                                 Col("xG/shot", "xg_per_shot_against", "f2", mode="xg")],
              ascending=True),
    ],
    "Teams: transitions": [
        Table("Losses", "losses", [Col("Total", "losses"), Col("Own third", "loss_own", "part", "losses"),
                                   Col("Middle third", "loss_mid", "part", "losses"),
                                   Col("Final third", "loss_fin", "part", "losses")],
              ascending=True, timeline=True),
        Table("Recoveries", "recoveries", [Col("Total", "recoveries"),
                                           Col("Own third", "rec_own", "part", "recoveries"),
                                           Col("Middle third", "rec_mid", "part", "recoveries"),
                                           Col("Final third", "rec_fin", "part", "recoveries")],
              timeline=True),
    ],
    "Teams: passes": [
        Table("Passes", "passes_att", [Col("Total", "passes_att", "pair", "passes_acc"),
                                       Col("Forward", "fwd_att", "pair", "fwd_acc"),
                                       Col("Lateral", "lat_att", "pair", "lat_acc"),
                                       Col("Back", "back_att", "pair", "back_acc"),
                                       Col("Long", "long_att", "pair", "long_acc"),
                                       Col("Avg length, m", "pass_len", "f1")], wide=True),
        Table("Ball possession", "possession", [Col("Possession", "possession", "pct"),
                                                Col("Possessions", "n_poss"),
                                                Col("< 5 s", "poss_lt5"), Col("5-15 s", "poss_5_15"),
                                                Col("15-45 s", "poss_15_45"), Col("45+ s", "poss_45"),
                                                Col("Avg duration, s", "poss_avg", "f1")], wide=True),
    ],
    "Teams: key passes": [
        Table("Passes to final third", "final3_att", [Col("Total", "final3_att", "pair", "final3_acc")], timeline=True),
        Table("Deep completions", "deep_compl", [Col("Total", "deep_compl")], timeline=True),
        Table("Progressive passes", "prog_att", [Col("Total", "prog_att", "pair", "prog_acc")], timeline=True),
        Table("Passes into penalty area", "box_pass_att", [Col("Total", "box_pass_att", "pair", "box_pass_acc")], timeline=True),
    ],
    "Teams: attack": [
        Table("Crosses", "cross_att", [Col("Total", "cross_att", "pair", "cross_acc"),
                                       Col("From left", "cross_l_att", "pair", "cross_l_acc"),
                                       Col("From right", "cross_r_att", "pair", "cross_r_acc")]),
        Table("Dribbles", "drib_att", [Col("Total", "drib_att", "pair", "drib_acc")]),
        Table("Touches in penalty area", "box_touches", [Col("Total", "box_touches")], timeline=True),
        Table("Fouls suffered", "Fouled", [Col("Total", "Fouled"), Col("Offsides", "Offside")]),
    ],
    "Teams: duels": [
        Table("Offensive duels", "off_duel_att", [Col("Total", "off_duel_att", "pair", "off_duel_won")]),
        Table("Defensive duels", "def_duel_att", [Col("Total", "def_duel_att", "pair", "def_duel_won")]),
        Table("Aerial duels", "Aerial Duels", [Col("Total", "Aerial Duels", "pair", "Aerial Won")]),
        Table("Tackles", "tackle_att", [Col("Total", "tackle_att", "pair", "tackle_acc")]),
    ],
    "Teams: defence": [
        Table("Interceptions", "Intercept", [Col("Total", "Intercept")]),
        Table("Pressing intensity (PPDA)", "ppda", [Col("PPDA", "ppda", "f2")], ascending=True, timeline=True),
        Table("Shots blocked", "Block", [Col("Total", "Block"), Col("% of opp. shots", "blocks_pct", "f1"),
                                         Col("xG blocked", "xg_blocked", "f2", mode="xg")]),
        Table("Fouls", "Foul", [Col("Total", "Foul"), Col("Yellow", "Yellow Card"), Col("Red", "Red Card")],
              ascending=True),
    ],
    "Teams: expected goals": [
        Table("Expected goals (xG)", "xg", [Col("xG", "xg", "f2"), Col("Non-penalty", "npxg", "f2"),
                                            Col("xG/shot", "xg_per_shot", "f2")], timeline=True, mode="xg"),
        Table("xG against", "xg_against", [Col("xG against", "xg_against", "f2"),
                                           Col("Non-penalty", "npxg_against", "f2")],
              ascending=True, timeline=True, mode="xg"),
        Table("Finishing: goals − xG", "goals_minus_xg", [Col("Goals", "Goals"), Col("xG", "xg", "f2"),
                                                           Col("Goals − xG", "goals_minus_xg", "d2")],
              timeline=True, mode="xg"),
        Table("Goals prevented", "goals_prevented",
              [Col("xGOT faced", "xgot_against", "f2"), Col("Conceded", "ga"),
               Col("Prevented", "goals_prevented", "d2")], timeline=True, mode="xg"),
    ],
    "Teams: expected threat": [
        Table("xT created", "xt", [Col("xT", "xt", "f2"), Col("Passes", "xt_pass", "f2"),
                                   Col("Carries", "xt_carry", "f2")], timeline=True, mode="xt"),
        Table("xT conceded", "xt_against", [Col("xT against", "xt_against", "f2")],
              ascending=True, timeline=True, mode="xt"),
    ],
    "Teams: territory": [
        Table("Field tilt", "field_tilt", [Col("Field tilt", "field_tilt", "pct"),
                                           Col("Final-third passes", "f3_passes")], timeline=True),
        Table("Threat share", "xt_share", [Col("Share of xT", "xt_share", "pct")], timeline=True, mode="xt"),
        Table("Defensive line height", "def_line", [Col("Metres", "def_line", "f1")], timeline=True),
        Table("Opponent defensive line", "def_line_against", [Col("Metres", "def_line_against", "f1")],
              timeline=True),
    ],
    "Teams: set pieces": [
        Table("Corners", "Corner", [Col("Total", "Corner"), Col("With shot", "corners_shot"),
                                    Col("Near post", "cor_near"), Col("Far post", "cor_far"),
                                    Col("Penalty spot", "cor_penalty"), Col("GK zone", "cor_gk"),
                                    Col("Short", "cor_short")], wide=True),
        Table("Penalties", "pen_att", [Col("Taken / scored", "pen_att", "pair", "pen_goals")], avg=False),
        Table("Direct free kicks", "dfk_att", [Col("Shots / goals", "dfk_att", "pair", "dfk_goals")], avg=False),
    ],
}

PLAYER_PAGES = {
    "Players: overview": [
        Table("Goals", "Goals", [Col("Total", "Goals"), Col("Shots", "Shots", mode="base"),
                                 Col("xG", "xg", "f2", mode="xg")]),
        Table("Assists", "Assist", [Col("Total", "Assist"), Col("Key passes", "Key Pass", mode="base"),
                                    Col("xA", "xa", "f2", mode="xg")]),
        Table("Shots", "Shots", [Col("Total", "Shots"), Col("On target", "Shot on"),
                                 Col("xG", "xg", "f2", mode="xg")]),
        Table("Chances created", "Create Chance", [Col("Total", "Create Chance")]),
        Table("Passes", "Passes", [Col("Total", "Passes", "pair", "Pass")]),
        Table("Duels", "duels_att", [Col("Total", "duels_att", "pair", "duels_won")]),
    ],
    "Players: expected goals": [
        Table("Expected goals (xG)", "xg", [Col("xG", "xg", "f2"), Col("Goals", "Goals")], timeline=True, mode="xg"),
        Table("Non-penalty xG", "npxg", [Col("npxG", "npxg", "f2"), Col("Shots", "Shots")], timeline=True, mode="xg"),
        Table("xG on target (xGOT)", "xgot", [Col("xGOT", "xgot", "f2"), Col("On target", "Shot on")],
              timeline=True, mode="xg"),
        Table("Finishing: goals − xG", "goals_minus_xg", [Col("Goals − xG", "goals_minus_xg", "d2")],
              timeline=True, mode="xg"),
        Table("Expected assists (xA)", "xa", [Col("xA", "xa", "f2"), Col("Assists", "Assist")], timeline=True, mode="xg"),
        Table("xG + xA", "xg_xa", [Col("xG + xA", "xg_xa", "f2")], timeline=True, mode="xg"),
    ],
    "Players: expected threat": [
        Table("Expected threat (xT)", "xt", [Col("xT", "xt", "f2")], timeline=True, mode="xt"),
        Table("xT from passes", "xt_pass", [Col("xT", "xt_pass", "f2"), Col("Passes", "Passes")],
              timeline=True, mode="xt"),
        Table("xT from carries", "xt_carry", [Col("xT", "xt_carry", "f2"),
                                              Col("Prog. runs", "Ball Carry - Progressive Carry")],
              timeline=True, mode="xt"),
    ],
    "Players: passes": [
        Table("Key passes", "Key Pass", [Col("Total", "Key Pass")]),
        Table("Deep completions", "deep_compl", [Col("Total", "deep_compl")], timeline=True),
        Table("Crosses", "cross_att", [Col("Total", "cross_att", "pair", "Cross")]),
        Table("Passes to final third", "final3_att", [Col("Total", "final3_att", "pair", "final3_acc")], timeline=True),
        Table("Progressive passes (completed)", "Pass - Progressive Pass", [Col("Total", "Pass - Progressive Pass")]),
        Table("Passes into penalty area", "box_pass_att", [Col("Total", "box_pass_att", "pair", "box_pass_acc")], timeline=True),
    ],
    "Players: attack": [
        Table("Touches in penalty area", "box_touches", [Col("Total", "box_touches")], timeline=True),
        Table("Offsides", "Offside", [Col("Total", "Offside")]),
        Table("Dribbles", "drib_att", [Col("Total", "drib_att", "pair", "Dribble")]),
        Table("Fouls suffered", "Fouled", [Col("Total", "Fouled")]),
        Table("Progressive runs", "Ball Carry - Progressive Carry", [Col("Total", "Ball Carry - Progressive Carry")]),
        Table("Offensive duels", "off_duel_att", [Col("Total", "off_duel_att", "pair", "off_duel_won")]),
    ],
    "Players: defence": [
        Table("Defensive duels", "def_duel_att", [Col("Total", "def_duel_att", "pair", "def_duel_won")]),
        Table("Aerial duels", "Aerial Duels", [Col("Total", "Aerial Duels", "pair", "Aerial Won")]),
        Table("Recoveries", "Recovery", [Col("Total", "Recovery")]),
        Table("Interceptions", "Intercept", [Col("Total", "Intercept")]),
        Table("Sliding tackles", "Tackle - Sliding Tackle", [Col("Total", "Tackle - Sliding Tackle")]),
        Table("Shots blocked", "Block", [Col("Total", "Block")]),
    ],
    "Players: set pieces": [
        Table("Penalties", "pen_att", [Col("Taken / scored", "pen_att", "pair", "Penalty Goal")]),
        Table("Direct free kicks", "dfk_att", [Col("Shots / goals", "dfk_att", "pair", "Goal - Free Kick")]),
        Table("Corners", "Corner", [Col("Total", "Corner")]),
        Table("Free kicks taken", "Freekick", [Col("Total", "Freekick")]),
        Table("Throw-ins", "Throw In", [Col("Total", "Throw In")]),
        Table("Fouls", "Foul", [Col("Total", "Foul"), Col("Yellow", "Yellow Card"), Col("Red", "Red Card")]),
    ],
}

GLOSSARY_XG = [
    ("xG (expected goals)", "The probability that a shot becomes a goal, from where and how it was taken "
     "(distance, angle, body part, situation, match minute). Penalties count as 0.80. Team and player xG "
     "is the sum over their shots."),
    ("xGOT (expected goals on target)", "For shots on target only: the probability of a goal once the "
     "placement in the goal is known. Penalties on target count as 0.86."),
    ("xA (expected assists)", "The xG of the shot that a key pass or assist set up, credited to the "
     "passer. Shots without a logged key pass or assist give no xA."),
    ("Goals − xG", "Goals scored minus xG: positive = finished better than an average shooter would."),
    ("Goals prevented", "xGOT of shots faced minus goals conceded (own goals excluded): positive = the "
     "goalkeeper kept out more than an average keeper would."),
]

GLOSSARY_XT = [
    ("xT (expected threat)", "How much a completed pass or carry raises the chance of scoring: the value "
     "of the zone where the ball ends minus the value of the zone where it started, from Karun Singh's "
     "open 12 x 8 xT grid. Failed passes count 0. Team xT conceded = the opponent's xT."),
    ("Threat share", "xT version of field tilt: a team's positive xT as a share of both teams' positive xT."),
]

GLOSSARY = [
    ("Field tilt", "Share of both teams' completed passes that start in the final third."),
    ("Defensive line height", "Average distance from own goal of the defensive actions (tackles, "
     "interceptions, clearances, blocks, recoveries, fouls) of the players listed as CB, LB, RB, LWB or RWB. "
     "Needs at least 5 such actions in the match. Higher = a higher line. Shown as the dashed line on the "
     "match pages."),
    ("PPDA", "Opponent passes per defensive action (tackles, interceptions, fouls, defensive "
             "duels) in the opponent's 60% of the pitch nearest their own goal. Lower = more intense pressing."),
    ("Possession", "A spell of consecutive on-ball actions by one team. Durations come from the event clock."),
    ("Transition: loss / recovery", "Loss = failed pass, failed cross, failed dribble or loose ball. "
     "Recovery = ball recovery, interception or successful tackle. Thirds use where the action happened."),
    ("Pass to final third", "A pass that starts outside and ends inside the final third (last 35 m)."),
    ("Deep completion", "A completed pass (crosses excluded) received within 20 m of the opponent goal."),
    ("Progressive pass", "A pass that moves the ball towards goal by at least 30 m (both points in own half), "
     "15 m (crossing halfway) or 10 m (both in opponent half). Team tables: event geometry. Player "
     "table: the data provider's completed progressive-pass tag."),
    ("Forward / lateral / back pass", "By pass angle: within 45° of straight towards goal = forward, within "
     "45° of straight back = back, otherwise lateral. Long = provider's 'Long Ball' tag."),
    ("Offensive duel", "Dribbles plus duels contested while in possession."),
    ("Defensive duel", "Tackles plus duels contested while the opponent had the ball."),
    ("Pass into penalty area", "A pass that starts outside and ends inside the opponent's penalty area."),
    ("Touch in penalty area", "Any on-ball action starting inside the opponent's penalty area."),
    ("Corner targets", "Where the delivery ends: near post / far post (inside 10.5 m of the goal line, "
     "by side), GK zone (six-yard box), penalty spot (rest of the box), short (outside the box or "
     "played short first). 'With shot' = a shot by the same team within 15 s."),
    ("Average positions", "Mean location of all on-ball actions for each player. Filled = starter, "
     "outlined = substitute; red dot = substituted off, green dot = came on. When a match has no "
     "complete event data, starters are placed at their nominal position instead."),
]


# ----------------------------------------------------------------------------
def _keep(mode, with_xg: bool, with_xt: bool = True) -> bool:
    if mode is None:
        return True
    if mode == "xt":
        return with_xt
    return (mode == "xg") == with_xg                  # "xg" with xG on, "base" with xG off


def pages_for(pages: dict, with_xg: bool = True, with_xt: bool = True) -> dict:
    """Pages/tables/columns for the report with or without xG (empty pages are dropped)."""
    out = {}
    for title, specs in pages.items():
        tables = []
        for t in specs:
            if not _keep(t.mode, with_xg, with_xt):
                continue
            cols = [c for c in t.cols if _keep(c.mode, with_xg, with_xt)]
            tables.append(Table(t.title, t.sort, cols, t.ascending, t.avg, t.timeline, t.wide, t.mode))
        if tables:
            out[title] = tables
    return out


def glossary_for(with_xg: bool = True, with_xt: bool = True) -> list:
    return (GLOSSARY_XG if with_xg else []) + (GLOSSARY_XT if with_xt else []) + list(GLOSSARY)
