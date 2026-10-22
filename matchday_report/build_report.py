"""Build the PDF from the command line.

    python build_report.py report.xlsx timeline.xlsx --gameweek 1 -o matchday_1.pdf
"""
import argparse

from report.io import read_report, read_timeline
from report.metrics import Matchday
from report.pdf import build_pdf
from report.standings import rules_for


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("timeline", nargs="?")
    ap.add_argument("--gameweek", type=int)
    ap.add_argument("--competition", default=None,
                    help="competition name (picks colours/logo); default: timeline Competition column")
    ap.add_argument("--league", default=None, help="header text override")
    ap.add_argument("--season", default=None, help="header text override, e.g. 2026-27")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    rep = read_report(a.report)
    tl, notes, comp = None, [], a.competition
    if a.timeline:
        tl, info = read_timeline(a.timeline)
        notes = info.notes
        if comp is None and "Competition" in tl and tl["Competition"].notna().any():
            comp = str(tl["Competition"].dropna().iloc[0])
    gw = a.gameweek or int(rep["Gameweek"].max())
    md = Matchday(rep, tl, gw, rules_for(comp or ""))
    out = a.out or f"matchday_{gw}_report.pdf"
    build_pdf(md, comp or "League", a.league, a.season, notes, out_path=out)
    for n in notes + md.notes:
        print("note:", n)
    print("written", out)


if __name__ == "__main__":
    main()
