"""Streamlit front-end for the matchday report.

Run locally:   streamlit run app.py

Data comes from a Google Drive folder (configured in .streamlit/secrets.toml, see
README) or, as a fallback, from files uploaded in the sidebar.
"""
from __future__ import annotations

import io
import os

import pandas as pd
import streamlit as st

from report import charts
from report.io import read_report, read_timeline
from report.metrics import Matchday
from report.pdf import build_pdf
from report.sources import Competition, DriveSource, LocalSource, build_competitions
from report.specs import GLOSSARY, PLAYER_PAGES, TEAM_PAGES
from report.tables import display_frame
from report.standings import awarded_results, guess_competition, rules_for
from report.theme import THEMES, logo_file, season_and_label, theme_for

st.set_page_config(page_title="Matchday Report", page_icon="⚽", layout="wide")


# --------------------------------------------------------------------------- #
# data sources
# --------------------------------------------------------------------------- #
def _secret(*path):
    try:
        v = st.secrets
        for p in path:
            v = v[p]
        return v
    except Exception:  # noqa: BLE001 – no secrets file / key
        return None


def drive_configured() -> bool:
    return bool(_secret("gdrive", "folder_id") and _secret("gcp_service_account"))


@st.cache_resource
def _drive() -> DriveSource:
    return DriveSource(dict(_secret("gcp_service_account")), _secret("gdrive", "folder_id"))


def _source():
    local = os.environ.get("MATCHDAY_DATA_DIR")      # optional: a local folder instead of Drive
    return LocalSource(local) if local else _drive()


@st.cache_data(ttl=300, show_spinner="Listing files in Google Drive…")
def list_source_files():
    return _source().list_files()


@st.cache_data(show_spinner=False, max_entries=200)
def download(file_id: str, modified: str, _meta) -> bytes:
    # (file_id, modified) is the cache key: a file is downloaded again only when it changes
    return _source().download(_meta)


@st.cache_resource(show_spinner="Reading and sorting competitions…", max_entries=4)
def load_competitions(signature: tuple):
    files = list_source_files()
    prog = st.progress(0.0, text="Downloading files…")
    pairs = []
    for i, f in enumerate(files):
        pairs.append((f, download(f.file_id, f.modified, f)))
        prog.progress((i + 1) / len(files), text=f"Downloading {f.name}")
    prog.empty()
    return build_competitions(pairs)


@st.cache_resource(show_spinner="Reading uploaded files…", max_entries=4)
def load_uploads(rep_raw: bytes, tl_raw: bytes | None):
    rep = read_report(rep_raw)
    tl, notes = (None, [])
    if tl_raw:
        tl, info = read_timeline(tl_raw)
        notes = info.notes
    name = "League"
    if tl is not None and "Competition" in tl and tl["Competition"].notna().any():
        name = str(tl["Competition"].dropna().iloc[0])
    return {name: Competition(name, rep, tl, notes)}, notes


@st.cache_resource(show_spinner="Calculating matchday stats…", max_entries=12)
def build_matchday(signature, comp_name: str, gw: int, _comp: Competition) -> Matchday:
    return Matchday(_comp.report, _comp.timeline, gw, rules_for(comp_name))


@st.cache_data(show_spinner="Building PDF…", max_entries=12)
def make_pdf(signature, comp_name: str, gw: int, league: str, season: str, notes: tuple,
             _md: Matchday) -> bytes:
    return build_pdf(_md, comp_name, league, season, notes)


def show_fig(fig):
    if fig is None:
        st.info("Needs complete event (timeline) data.")
        return
    st.image(charts.to_png(fig, dpi=170, transparent=False), use_container_width=True)


# --------------------------------------------------------------------------- #
# sidebar: source -> competition -> gameweek
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("Data")
    use_drive = drive_configured() or bool(os.environ.get("MATCHDAY_DATA_DIR"))
    mode = st.radio("Source", ["Google Drive", "Upload files"], index=0 if use_drive else 1,
                    horizontal=True)

comps, global_notes, signature = {}, [], ()
if mode == "Google Drive":
    if not use_drive:
        st.error("Google Drive is not configured. Add `[gdrive] folder_id` and "
                 "`[gcp_service_account]` to the app's secrets (see README), or use *Upload files*.")
        st.stop()
    with st.sidebar:
        if st.button("↻ Refresh data", use_container_width=True,
                     help="Re-list the Drive folder and pick up new or changed files"):
            list_source_files.clear()
            st.session_state.pop("pdf", None)
    try:
        files = list_source_files()
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not read the Drive folder: {e}")
        st.stop()
    signature = tuple(sorted((f.file_id, f.modified) for f in files))
    comps, global_notes = load_competitions(signature)
else:
    with st.sidebar:
        rep_file = st.file_uploader("Player match stats (report.xlsx)", type=["xlsx"])
        tl_file = st.file_uploader("Event timeline (timeline.xlsx)", type=["xlsx"])
    if rep_file is None:
        st.title("Matchday Report")
        st.write("Upload the **player match stats** file (required) and the **event timeline** "
                 "file (recommended) in the sidebar.")
        st.stop()
    rep_raw = rep_file.getvalue()
    tl_raw = tl_file.getvalue() if tl_file else None
    signature = (hash(rep_raw), hash(tl_raw))
    comps, global_notes = load_uploads(rep_raw, tl_raw)
    # Without a timeline the file doesn't say which competition it is: let the user pick
    # (pre-selected when the timeline names a known competition).
    detected = next(iter(comps))
    options = [t.name for t in THEMES]
    guess = theme_for(detected).name
    if guess not in options:                  # no timeline: guess from the club names
        guess = guess_competition(c_teams := comps[detected].report["Team"].unique()) or options[0]
    with st.sidebar:
        chosen = st.selectbox("Competition", options, index=options.index(guess) if guess in options else 0,
                              help="Sets colours, logo, groups and point deductions")
    c = comps[detected]
    season_txt = season_and_label(detected)
    if not season_txt:          # infer from match dates: Jul-Dec -> 2026-27, Jan-Jun -> 2025-26
        d = pd.to_datetime(c.report["Date"], format="%d %b %Y %H:%M", errors="coerce").dropna()
        if len(d):
            y = int(d.min().year) - (1 if d.min().month < 7 else 0)
            season_txt = f"{y}-{str(y + 1)[-2:]}"
    name = f"{chosen} {season_txt}".strip()
    comps = {name: Competition(name, c.report, c.timeline, c.notes)}

if not comps:
    st.error("No usable data found.")
    for n in global_notes:
        st.caption("• " + n)
    st.stop()

with st.sidebar:
    st.header("Report")
    if mode == "Google Drive":
        comp_name = st.selectbox("Competition", sorted(comps))
    else:
        comp_name = next(iter(comps))
    comp = comps[comp_name]
    gws = comp.gameweeks
    gw = st.selectbox("Gameweek", gws, index=len(gws) - 1, format_func=lambda g: f"Matchday {g}")
    th = theme_for(comp_name)
    league = st.text_input("League name (header)", th.name, key=f"lg_{comp_name}")
    season = st.text_input("Season (header)", season_and_label(comp_name), key=f"ss_{comp_name}")
    st.markdown(f"<div style='display:flex;gap:6px;align-items:center'>Theme "
                f"<span style='width:18px;height:18px;border-radius:3px;background:{th.primary}'></span>"
                f"<span style='width:18px;height:18px;border-radius:3px;background:{th.secondary}'></span>"
                f"</div>", unsafe_allow_html=True)

md = build_matchday(signature, comp_name, gw, comp)
tl_notes = tuple(n for n in comp.notes)

for n in tl_notes:
    st.warning(n)
if comp.timeline is None:
    st.warning("No timeline for this competition – event-based stats (positions, zones, PPDA, "
               "goal minutes…) are hidden.")

st.markdown(f"<h1 style='color:{th.primary};font-weight:600;margin-bottom:0'>{league}</h1>"
            f"<div style='color:#4a4d55;font-size:1.1rem;margin-bottom:1rem'>"
            f"{season + ' // ' if season else ''}GW#{gw:02d}</div>", unsafe_allow_html=True)

with st.sidebar:
    st.divider()
    pdf_key = (comp_name, gw, league, season)
    if st.button("Build PDF report", type="primary", use_container_width=True):
        st.session_state["pdf"] = (pdf_key, make_pdf(signature, comp_name, gw, league, season,
                                                     tl_notes, md))
    if st.session_state.get("pdf") and st.session_state["pdf"][0] == pdf_key:
        fname = f"{league}_GW{gw:02d}_report.pdf".replace(" ", "_").replace("'", "")
        st.download_button("⬇ Download PDF", st.session_state["pdf"][1], file_name=fname,
                           mime="application/pdf", use_container_width=True)

tabs = st.tabs(["Fixtures & table", "Matches", "Goals", "Teams", "Players", "Data & glossary"])

# --- fixtures & standings --------------------------------------------------- #
with tabs[0]:
    c1, c2 = st.columns([1, 1.3])
    with c1:
        st.subheader("Results")
        fx = md.matches.assign(Score=lambda d: d.hg.astype(str) + " – " + d.ag.astype(str),
                               Date=lambda d: d.date.dt.strftime("%d.%m.%Y %H:%M"))
        fx = fx[["Date", "home", "Score", "away", "venue"]].rename(
            columns={"home": "Home", "away": "Away", "venue": "Venue"})
        for a in awarded_results(md.rules, list(md.report["Team"].unique()), gw):
            if a["Gameweek"] == gw:
                fx.loc[len(fx)] = [a["label"], a["Home"], f'{a["FTHG"]} – {a["FTAG"]}', a["Away"], ""]
        st.dataframe(fx, hide_index=True, use_container_width=True)
    with c2:
        st.caption(f"Standings after matchday {gw}")
        for group, table in md.standings():
            st.subheader(group.upper() if group else f"Table after matchday {gw}")
            st.dataframe(table[["Pos", "Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts", "Adj", "FP"]],
                         hide_index=True, use_container_width=True,
                         height=min(670, 38 + 35 * len(table)))
            adj = table[table.Adj != 0]
            if len(adj):
                st.caption("Points adjustment: " + ", ".join(f"{r.Team} ({r.Adj:+d})" for r in adj.itertuples()))

# --- matches ---------------------------------------------------------------- #
with tabs[1]:
    labels = {f"{r.home} {r.hg}–{r.ag} {r.away}": r.Match for r in md.matches.itertuples()}
    pick = st.selectbox("Match", list(labels))
    show_fig(charts.match_figure(md, labels[pick], th))
    lines = md.match_stat_lines(labels[pick])
    m = md.matches.set_index("Match").loc[labels[pick]]
    st.dataframe(pd.DataFrame([(l, h, a) for l, h, a, _ in lines], columns=["Stat", m.home, m.away]),
                 hide_index=True, use_container_width=True)

# --- goals ------------------------------------------------------------------ #
with tabs[2]:
    for conceded, title in ((False, "Goals scored by match period"), (True, "Goals conceded by match period")):
        st.subheader(title)
        tab = md.goal_dynamics(conceded)
        if tab.empty:
            st.info("Needs complete event (timeline) data.")
            continue
        c1, c2 = st.columns(2)
        with c1:
            show_fig(charts.goal_dynamics_figure(tab, th, conceded))
        with c2:
            st.dataframe(tab, use_container_width=True)

# --- teams ------------------------------------------------------------------ #
with tabs[3]:
    page = st.radio("Section", list(TEAM_PAGES), horizontal=True,
                    format_func=lambda s: s.split(": ")[1].capitalize())
    specs = [sp for sp in TEAM_PAGES[page] if not (sp.timeline and md.T.empty)]
    if not specs:
        st.info("This section needs timeline (event) data.")
    cols = st.columns(2)
    for i, spec in enumerate(specs):
        with (st.container() if spec.wide else cols[i % 2]):
            st.markdown(f"**{spec.title}**")
            st.dataframe(display_frame(md.teams, spec), hide_index=True, use_container_width=True)
    if page == "Teams: transitions":
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Losses by zone** – blue = above league share")
            show_fig(charts.zones_grid_figure(md.teams, "loss", "losses", th))
        with c2:
            st.markdown("**Recoveries by zone** – blue = above league share")
            show_fig(charts.zones_grid_figure(md.teams, "rec", "recoveries", th))
    if page == "Teams: set pieces":
        st.markdown("**Corner deliveries** – orange = led to a shot within 15 s")
        show_fig(charts.corners_grid_figure(md, th))

# --- players ---------------------------------------------------------------- #
with tabs[4]:
    page = st.radio("Section ", list(PLAYER_PAGES), horizontal=True,
                    format_func=lambda s: s.split(": ")[1].capitalize())
    top = st.slider("Players per list", 5, 30, 10)
    team_filter = st.multiselect("Teams", sorted(md.players.Team.unique()))
    P = md.players if not team_filter else md.players[md.players.Team.isin(team_filter)]
    cols = st.columns(2)
    for i, spec in enumerate([sp for sp in PLAYER_PAGES[page] if not (sp.timeline and md.T.empty)]):
        with cols[i % 2]:
            st.markdown(f"**{spec.title}**")
            st.dataframe(display_frame(P, spec, player=True, limit=top), hide_index=True,
                         use_container_width=True)

# --- data & glossary -------------------------------------------------------- #
with tabs[5]:
    st.subheader("Event-data coverage per match")
    cov = md.matches[["home", "away", "tl_events", "coverage"]].copy()
    cov["coverage"] = (cov["coverage"] * 100).round(0).astype(int).astype(str) + "%"
    st.dataframe(cov.rename(columns={"home": "Home", "away": "Away", "tl_events": "Events",
                                     "coverage": "Coverage"}), hide_index=True)
    for n in md.notes + [n for n in global_notes if n not in tl_notes]:
        st.caption("• " + n)
    if mode == "Google Drive":
        st.subheader("Files read from Drive")
        st.dataframe(pd.DataFrame([(f.folder or "/", f.name, f.modified) for f in list_source_files()],
                                  columns=["Folder", "File", "Modified"]), hide_index=True)
    st.subheader("Logos")
    st.caption("Add PNG files at these paths in the repo (transparent background). Missing ones "
               "show a placeholder badge.")
    import os as _os
    need = [("competitions", th.name)] + [("teams", t) for t in sorted(md.teams.Team)]
    st.dataframe(pd.DataFrame([(k, n, _os.path.relpath(logo_file(k, n)),
                                "✅" if _os.path.exists(logo_file(k, n)) else "placeholder")
                               for k, n in need], columns=["Kind", "Name", "File", "Status"]),
                 hide_index=True, use_container_width=True)
    st.subheader("Glossary")
    for t, d in GLOSSARY:
        st.markdown(f"**{t}** – {d}")
    st.subheader("Downloads")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as xw:
        md.teams.to_excel(xw, sheet_name="teams", index=False)
        md.players.to_excel(xw, sheet_name="players", index=False)
        md.team_match.to_excel(xw, sheet_name="team_match", index=False)
    st.download_button("Team & player tables (.xlsx)", buf.getvalue(), f"matchday_{gw}_tables.xlsx")
