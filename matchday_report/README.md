# Matchday Report (Streamlit)

Builds a matchday PDF report: cover, standings, match overviews with average
positions, goal timing, team rankings and player top‑10s. It uses two exports:

| File | Contents | Required |
|---|---|---|
| `report.xlsx` | one row per player per match (counts) | yes |
| `timeline.xlsx` | one row per event with X/Y coordinates | recommended |

Expected goals (xG, xA, xGChain) are not included yet.

## Where the data comes from

**Google Drive (default).** The app reads every `.xlsx` file and Google Sheet in one
shared Drive folder, including its sub-folders. Organise it however you like, for example:

```
Matchday data/
├── Super League/      report_gw1.xlsx, timeline_gw1.xlsx, report_gw2.xlsx, …
├── Liga 2/            …
└── Piala Indonesia/   …
```

* **File type** is detected from the columns: a timeline has `Act Name` + `X1`, a
  report has `Player Match ID` + `Gameweek`. File names don't matter.
* **Competition** comes from the timeline's `Competition` column. Each report row
  is matched to it by `Player Match ID`. If a match has no timeline, the row uses
  the competition of the rest of its file, then the sub-folder name.
* **Gameweeks** are whatever appears in the `Gameweek` column. Several files per
  competition are merged, and duplicate rows are dropped.
* **Caching:** the file list is re-checked every 5 minutes or when you click
  **↻ Refresh data**. A file is downloaded again only when its modified time changes.

**Upload files.** Switch the source to *Upload files* in the sidebar to use a
one-off report + timeline pair without touching Drive.

### One-time Google setup
1. In Google Cloud Console, create (or pick) a project and enable the **Google Drive API**.
2. Go to IAM & Admin → Service accounts → **Create service account**. Then
   Keys → Add key → JSON, and download the key file.
3. In Google Drive, **share the data folder** with the service account's
   `client_email` as a **Viewer**.
4. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in
   the folder ID and the JSON key fields. On Streamlit Cloud, paste the same text
   into App settings → **Secrets**. Keep `secrets.toml` out of git; `.gitignore`
   already excludes it.

Testing without Drive: set `MATCHDAY_DATA_DIR=/path/to/folder` and the app reads
a local folder with the same rules.

## Look & feel

* **Themes per competition** (`report/theme.py` → `THEMES`). The theme is picked by
  keywords in the competition name:

  | Competition | Primary | Secondary | Matches names containing |
  |---|---|---|---|
  | BRI Super League | `#00529c` | `#ed1c24` | super league, liga 1, bri |
  | Pegadaian Championship | `#034d43` | `#fac61b` | championship, pegadaian, liga 2 |
  | Indonesian Women's League | `#ec008d` | `#d4af37` | women, wanita, putri |

  The primary colour is used for pitch lines, players, scores, bars and ranks. The
  secondary colour marks goals conceded and corners that led to a shot.
* **Fonts:** Poppins for titles and numbers, Be Vietnam Pro for body text
  (see `assets/fonts/FONTS.md`).
* **Logos:** drop PNGs into `assets/logos/competitions/` and `assets/logos/teams/`.
  `assets/logos/LOGOS.md` lists the expected file names. Until a file exists, a
  placeholder badge with initials is drawn.

## Standings, groups and point deductions

Configured per competition in `report/standings.py` → `COMPETITION_RULES`:

| Competition | Format | Starting deductions |
|---|---|---|
| BRI Super League | one table (18) | Isenmulang Kalteng −2, Java United −2 |
| Pegadaian Championship | Group A + Group B (10 each) | A: Persiraja, PSIS, Semen Padang, Sumsel United −1 · Persiku −2 · B: Kendal Tornado, Persela, Persipura −1 · Persiba, PSBS Biak −4 |
| Indonesian Women's League | one table (6) | none |

* **Tie-breakers** inside each table: points, then head-to-head points, head-to-head
  goal difference, head-to-head goals scored, overall goal difference, overall goals scored.
  Head-to-head only counts matches inside the same group.
* **Team names** in the config don't need to match the data exactly. Case,
  punctuation and the words "FC"/"PS" are ignored, and "PSBS Biak" matches "PSBS Biak Numfor".
* **Clubs listed in a group** appear in the table even before their first match.
  If the data has a team that isn't in any group, it shows under "Unassigned" with a
  warning, so new clubs are easy to spot.
* **New season:** edit the group lists and deductions in `COMPETITION_RULES`. No other code changes are needed.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Pick the competition and gameweek in the sidebar, then click **Build PDF report**.

Command line, no UI:

```bash
python build_report.py report.xlsx timeline.xlsx --gameweek 1
# optional: --competition "BRI Super League 2026-27" --league "..." --season 2026-27
```

## Deploy on Streamlit Community Cloud

1. Push this folder to a GitHub repository. `app.py` must be at the repo root.
2. Go to share.streamlit.io, then **New app**, pick the repo, and set the main file to `app.py`.
3. Under **Advanced settings → Secrets**, paste your secrets (see above), then deploy.
   No system packages are needed. The fonts ship in `assets/fonts`.

## Code layout

```
app.py              Streamlit UI (tabs + PDF download)
build_report.py     CLI
report/io.py        Excel loading (+ recovery of damaged/truncated .xlsx)
report/sources.py   Google Drive / local folder reader, splits data into competitions
report/metrics.py   all calculations (Matchday class)
report/specs.py     which tables go on which page + glossary   <- edit to add/remove stats
report/tables.py    ranking + formatting
report/standings.py league tables: groups, deductions, head-to-head tie-breakers
report/theme.py     competition colours, fonts, logos/placeholders
report/charts.py    matplotlib figures (pitches, bars, zones, corners)
report/pdf.py       ReportLab layout
```

### Adding a stat
1. Compute it as a column in `Matchday._build_team_match` / `_timeline_team_metrics`
   (teams) or `_build_players` (players).
2. Add a `Table(...)` entry in `specs.py`. Both the PDF and the app pick it up.

### Adding xG later
The timeline already has an `xg value` column. Fill it, then sum it per team and
player in `metrics.py`, and add `Col("xG", "xg", "f2")` entries in `specs.py`.

## Data rules worth knowing
* Event-based stats are used for a match only when its timeline is complete
  (the event pass count matches the report). Otherwise they show "–". The glossary
  page lists coverage per match.
* Coordinates are 0–100, with every team attacking left to right. The pitch is taken as 105 × 68 m.
