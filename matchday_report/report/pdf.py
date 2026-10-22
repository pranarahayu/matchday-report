"""Assemble the matchday report PDF with ReportLab, styled per competition."""
from __future__ import annotations

import hashlib
import io
import os
import tempfile

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Spacer)
from reportlab.platypus import Table as RLTable
from reportlab.platypus import TableStyle

from . import charts
from .metrics import Matchday
from .specs import GLOSSARY, PLAYER_PAGES, TEAM_PAGES, Table
from .tables import col_header, fmt_value, league_average, ranked
from .theme import (CARD, INK, INK2, MUTED, Theme, font_path, logo, logo_file, season_and_label,
                    theme_for)

# --------------------------------------------------------------------------- #
# fonts: Poppins for titles, Be Vietnam Pro (or Poppins) for body text
# --------------------------------------------------------------------------- #
for fam in ("title", "body"):
    for w in ("Light", "Regular", "Medium", "Bold"):
        pdfmetrics.registerFont(TTFont(f"{fam}-{w}", font_path(fam, w)))
pdfmetrics.registerFontFamily("body-Regular", normal="body-Regular", bold="body-Bold",
                              italic="body-Regular", boldItalic="body-Bold")

PAGE_W, PAGE_H = A4
MARGIN = 14 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
GAP = 6 * mm
HALF_W = (CONTENT_W - GAP) / 2
C = colors.HexColor
RULE = C("#dfe1e6")
LOGO_CACHE = os.path.join(tempfile.gettempdir(), "matchday_logos")
os.makedirs(LOGO_CACHE, exist_ok=True)


class Report:
    """Holds the theme + styles for one PDF build."""

    def __init__(self, md: Matchday, competition: str, league: str | None, season: str | None):
        self.md = md
        self.th: Theme = theme_for(competition)
        self.league = league or self.th.name
        self.season = season if season is not None else season_and_label(competition)
        self.P = C(self.th.primary)
        self.S = C(self.th.secondary)
        p = self.P
        self.st = {
            "h2": ParagraphStyle("h2", fontName="title-Medium", fontSize=10.5, leading=13, textColor=C(INK)),
            "cell": ParagraphStyle("c", fontName="body-Regular", fontSize=6.6, leading=8.4, textColor=C(INK)),
            "cellr": ParagraphStyle("cr", fontName="body-Regular", fontSize=6.6, leading=8.4,
                                    textColor=C(INK), alignment=2),
            "cellb": ParagraphStyle("cb", fontName="body-Medium", fontSize=6.6, leading=8.4,
                                    textColor=C(INK), alignment=2),
            "head": ParagraphStyle("hd", fontName="body-Regular", fontSize=5.3, leading=6.5,
                                   textColor=C(MUTED), alignment=2),
            "headl": ParagraphStyle("hl", fontName="body-Regular", fontSize=5.3, leading=6.5, textColor=C(MUTED)),
            "rank": ParagraphStyle("rk", fontName="title-Medium", fontSize=7.2, leading=9, textColor=p),
            "body": ParagraphStyle("b", fontName="body-Regular", fontSize=7.3, leading=10.2, textColor=C(INK2)),
            "gl_t": ParagraphStyle("g", fontName="title-Medium", fontSize=8, leading=10, textColor=p, spaceBefore=7),
            "note": ParagraphStyle("n", fontName="body-Light", fontSize=6.5, leading=8.8, textColor=C(INK2)),
            "cover_t": ParagraphStyle("ct", fontName="title-Light", fontSize=26, leading=32,
                                      alignment=TA_CENTER, textColor=C(INK)),
            "cover_s": ParagraphStyle("cs", fontName="title-Medium", fontSize=15, leading=22,
                                      alignment=TA_CENTER, textColor=p),
            "cover_m": ParagraphStyle("cm", fontName="title-Light", fontSize=12, leading=18,
                                      alignment=TA_CENTER, textColor=C(INK2)),
            "fix": ParagraphStyle("fx", fontName="body-Regular", fontSize=7.6, leading=10, textColor=C(INK)),
        }

    # ---------------------------------------------------------------- helpers
    @property
    def gw_line(self):
        gw = f"GW#{self.md.gameweek:02d}"
        return f"{self.season} // {gw}" if self.season else gw

    def logo_path(self, kind: str, name: str) -> str:
        src = logo_file(kind, name)
        stamp = os.path.getmtime(src) if os.path.exists(src) else 0      # new logo file -> new cache entry
        key = hashlib.md5(f"{kind}|{name}|{self.th.primary}|{src}|{stamp}".encode()).hexdigest()[:16]
        p = os.path.join(LOGO_CACHE, f"{key}.png")
        if not os.path.exists(p):
            logo(kind, name, self.th.primary).save(p)
        return p

    def team_cell(self, name: str, size=9, width: float | None = None):
        shown = charts.team_label(name, max(10, int((width - size - 16) / 4.1))) if width else name
        return Paragraph(f'<img src="{self.logo_path("teams", name)}" width="{size}" height="{size}" '
                         f'valign="middle"/>&nbsp;&nbsp;{shown}', self.st["cell"])

    # ---------------------------------------------------------------- canvas
    def background(self, canv, doc):
        """Plain white page."""
        canv.saveState()
        canv.setFillColor(colors.white)
        canv.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        canv.restoreState()

    def header(self, canv, doc):
        canv.saveState()
        sec = getattr(canv, "_section", "")
        top = PAGE_H - 9 * mm
        canv.setFillColor(C(INK))
        canv.setFont("title-Light", 13.5); canv.drawString(MARGIN, top - 11, "MATCHDAY DATA REPORT")
        canv.setFont("title-Medium", 13.5); canv.drawString(MARGIN, top - 28, sec.upper())
        # right block: logo + league + season // GW
        canv.setFont("title-Light", 17)
        lw = pdfmetrics.stringWidth(self.league, "title-Light", 17)
        canv.drawRightString(PAGE_W - MARGIN, top - 13, self.league)
        canv.setFillColor(C(INK2)); canv.setFont("title-Light", 10.5)
        canv.drawRightString(PAGE_W - MARGIN, top - 28, self.gw_line)
        lg = 34
        canv.drawImage(ImageReader(self.logo_path("competitions", self.th.name)),
                       PAGE_W - MARGIN - lw - lg - 8, top - 33, lg, lg, mask="auto")
        canv.setStrokeColor(C("#a9acb3")); canv.setLineWidth(1.4)
        canv.line(MARGIN * 0.7, top - 40, PAGE_W - MARGIN * 0.7, top - 40)
        canv.setFillColor(C(MUTED)); canv.setFont("body-Regular", 7)
        canv.drawRightString(PAGE_W - MARGIN, 8 * mm, str(doc.page))
        canv.restoreState()

    # ---------------------------------------------------------------- tables
    def ranked_table(self, df: pd.DataFrame, spec: Table, width: float, player=False, limit=None):
        st = self.st
        d = ranked(df, spec, player=player, limit=limit)
        ncols = len(spec.cols)
        val_w = 50 if ncols > 1 else 60
        if spec.wide:
            val_w = min(68, (width - 150) / ncols)
        rank_w = 18
        name_w = width - rank_w - val_w * ncols
        head = [Paragraph(spec.title, st["h2"]), ""] + [
            Paragraph(f'<font name="body-Medium" color="{self.th.primary}">{col_header(c, rich=True)}</font>'
                      if c.key == spec.sort else col_header(c, rich=True), st["head"]) for c in spec.cols]
        rows = [head]
        style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("SPAN", (0, 0), (1, 0)),
                 ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                 ("LINEBELOW", (0, 0), (-1, 0), 1.2, self.P),
                 ("TOPPADDING", (0, 1), (-1, -1), 2.3), ("BOTTOMPADDING", (0, 1), (-1, -1), 2.3),
                 ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                 ("BOTTOMPADDING", (0, 0), (-1, 0), 3)]
        if spec.avg and not player:
            avg = league_average(df, spec)
            rows.append(["", Paragraph("League average", st["cell"])] +
                        [Paragraph(fmt_value(avg, c, rich=True), st["cellr"]) for c in spec.cols])
            style.append(("BACKGROUND", (0, 1), (-1, 1), C(self.th.tint(0.9))))
        first = len(rows)
        for i, (_, r) in enumerate(d.iterrows()):
            rk = "" if pd.isna(r["rank"]) else str(int(r["rank"]))
            if player:
                name = Paragraph(f'<font name="body-Medium">{r["short"]}</font> '
                                 f'<font size="5.3" color="{MUTED}">{charts.team_label(r["Team"], 26)}</font>',
                                 st["cell"])
            else:
                name = self.team_cell(str(r["Team"]), width=name_w)
            rows.append([Paragraph(rk, st["rank"]), name] +
                        [Paragraph(fmt_value(r, c, rich=True), st["cellb" if c.key == spec.sort else "cellr"])
                         for c in spec.cols])
            style.append(("LINEBELOW", (0, first + i), (-1, first + i), 0.4, RULE))
            if player and i < 3:
                style.append(("BACKGROUND", (0, first + i), (-1, first + i), C(self.th.tint(0.93))))
        if len(rows) == first:
            rows.append(["", Paragraph("No data", st["cell"])] + [""] * ncols)
        t = RLTable(rows, colWidths=[rank_w, name_w] + [val_w] * ncols, hAlign="LEFT")
        t.setStyle(TableStyle(style))
        return t

    def simple_table(self, df: pd.DataFrame, widths, first_left=1, bold_col=None, logos_col=None):
        st = self.st
        rows = [[Paragraph(str(c), st["headl" if i < first_left else "head"]) for i, c in enumerate(df.columns)]]
        for _, r in df.iterrows():
            line = []
            for i, v in enumerate(r.values):
                if i == logos_col:
                    line.append(self.team_cell(str(v), width=widths[i]))
                elif i < first_left:
                    line.append(Paragraph(str(v), st["rank"] if i == 0 and first_left > 1 else st["cell"]))
                else:
                    line.append(Paragraph(str(v), st["cellb" if i == bold_col else "cellr"]))
            rows.append(line)
        t = RLTable(rows, colWidths=widths, hAlign="LEFT", repeatRows=1)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                               ("LINEBELOW", (0, 0), (-1, 0), 1.2, self.P),
                               ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
                               ("TOPPADDING", (0, 0), (-1, -1), 3.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.4)]))
        return t

    # ---------------------------------------------------------------- pages
    def cover(self):
        md, st = self.md, self.st
        out = [Spacer(1, 22 * mm), Paragraph("M A T C H D A Y&nbsp;&nbsp;&nbsp;D A T A&nbsp;&nbsp;&nbsp;R E P O R T", st["cover_t"]),
               Spacer(1, 14 * mm), _img_path(self.logo_path("competitions", self.th.name), 42 * mm),
               Spacer(1, 8 * mm), Paragraph(self.league, st["cover_s"]),
               Paragraph(self.season, st["cover_m"]) if self.season else Spacer(1, 1),
               Paragraph(f"Gameweek {md.gameweek}", st["cover_m"]), Spacer(1, 16 * mm)]
        rows = []
        for _, m in md.matches.iterrows():
            lh, la = self.logo_path("teams", m.home), self.logo_path("teams", m.away)
            rows.append([Paragraph(f'<img src="{lh}" width="13" height="13" valign="middle"/>', st["fix"]),
                         Paragraph(f'<img src="{la}" width="13" height="13" valign="middle"/>', st["fix"]),
                         Paragraph(f'{m.home}&nbsp;&nbsp;<font name="title-Bold" color="{self.th.primary}">'
                                   f'{m.hg} – {m.ag}</font>&nbsp;&nbsp;{m.away}', st["fix"]),
                         Paragraph(m.date.strftime("%d.%m.%Y") if pd.notna(m.date) else "",
                                   ParagraphStyle("d", parent=st["fix"], alignment=2, textColor=C(MUTED)))])
        t = RLTable(rows, colWidths=[18, 22, 112 * mm, 26 * mm], hAlign="CENTER")
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return out + [t]

    def standings_table(self, title: str, full: pd.DataFrame, compact: bool):
        """Primary-colour header band (title + column names) over white rows."""
        P, th = self.P, self.th
        band = ParagraphStyle("band", fontName="title-Bold", fontSize=12, leading=14, textColor=colors.white)
        hd = ParagraphStyle("hd", fontName="title-Medium", fontSize=7, leading=9, textColor=colors.white,
                            alignment=TA_CENTER)
        hdl = ParagraphStyle("hdl", parent=hd, alignment=0)
        cell = ParagraphStyle("sc", fontName="body-Medium", fontSize=7.6 if compact else 8, leading=10,
                              textColor=C(INK))
        num = ParagraphStyle("sn", parent=cell, fontName="body-Regular", alignment=TA_CENTER)
        pts = ParagraphStyle("sp", parent=cell, fontName="title-Bold", alignment=TA_CENTER, textColor=P)
        pos = ParagraphStyle("so", parent=cell, fontName="title-Medium", alignment=TA_CENTER, textColor=P)
        cols = ["P", "W", "D", "L", "GF", "GA", "+/-", "PTS"]
        num_w = 34
        team_w = CONTENT_W - 30 - num_w * len(cols)
        rows = [[Paragraph(title.upper(), band)] + [""] * (len(cols) + 1),
                [Paragraph("POS", hd), Paragraph("CLUB", hdl)] + [Paragraph(c, hd) for c in cols]]
        for r in full.itertuples():
            gd = f"+{r.GD}" if r.GD > 0 else str(r.GD)
            p_txt = f"{r.Pts}*" if r.Adj else str(r.Pts)
            rows.append([Paragraph(f"{r.Pos}.", pos), self.team_cell(r.Team, size=12, width=team_w)]
                        + [Paragraph(str(v), num) for v in (r.P, r.W, r.D, r.L, r.GF, r.GA, gd)]
                        + [Paragraph(p_txt, pts)])
        pad = 3.2 if compact else 4.2
        t = RLTable(rows, colWidths=[30, team_w] + [num_w] * len(cols), hAlign="LEFT")
        t.setStyle(TableStyle([
            ("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 1), P),
            ("TOPPADDING", (0, 0), (-1, 0), 9), ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
            ("LEFTPADDING", (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 2), (-1, -1), pad), ("BOTTOMPADDING", (0, 2), (-1, -1), pad),
            ("BACKGROUND", (0, 2), (-1, -1), colors.white),
            ("LINEBELOW", (0, 2), (-1, -1), 0.6, C(th.tint(0.8))),
            ("BOX", (0, 0), (-1, -1), 1.2, P),
        ]))
        return t

    def standings(self):
        tables = self.md.standings()
        compact = sum(len(t) for _, t in tables) > 18
        out = [Section("Standings")]
        for group, full in tables:
            title = group or f"Table after gameweek {self.md.gameweek}"
            out += [self.standings_table(title, full, compact), Spacer(1, 6 if compact else 8)]
        adj = pd.concat([t for _, t in tables])
        adj = adj[adj["Adj"] != 0]
        if len(adj):
            items = ", ".join(f"{r.Team} ({r.Adj:+d})" for r in adj.itertuples())
            out.append(Paragraph(f"* Points adjustment applied: {items}.", self.st["note"]))
        out.append(Paragraph("Tie-breakers: points, then head-to-head points, head-to-head goal difference, "
                             "head-to-head goals scored, overall goal difference, overall goals scored.",
                             self.st["note"]))
        return out

    def matches(self):
        out = [Section("Matchday overview")]
        n = len(self.md.matches)
        for i, m in enumerate(self.md.matches.Match):
            png = charts.to_png(charts.match_figure(self.md, m, self.th))
            w, h = ImageReader(io.BytesIO(png)).getSize()
            max_h = (PAGE_H - 40 * mm - 9 * mm) / 2          # two blocks per page
            out.append(_img(png, min(CONTENT_W, max_h * w / h)))
            if i % 2 == 0:
                out.append(Spacer(1, 6 * mm))
            elif i < n - 1:
                out.append(PageBreak())
        return out

    def goals(self):
        md, st = self.md, self.st
        out = [Section("Goals")]
        if md.goal_events.empty:
            return out + [Paragraph("Goal minutes need complete event data – none available.", st["body"])]
        for conceded, title in ((False, "Goals scored in match dynamics"), (True, "Goals conceded in match dynamics")):
            tab = md.goal_dynamics(conceded)
            fig = charts.goal_dynamics_figure(tab, self.th, conceded)
            df = tab.reset_index()
            tbl = self.simple_table(df[["Team", "Total", "1st half", "2nd half"]], [118, 44, 44, 44],
                                    bold_col=1, logos_col=0)
            out += [Paragraph(title, st["h2"]), grid([_img(charts.to_png(fig), HALF_W), tbl]), Spacer(1, 4)]
        out.append(Paragraph("Only matches with complete event data are included. Circle size and shade "
                             "show the number of goals.", st["note"]))
        return out

    def team_page(self, title, specs):
        md, st, th = self.md, self.st, self.th
        out = [Section(title)]
        teams = md.teams
        if title == "Teams: transitions":
            for spec in specs:
                prefix = "loss" if spec.sort == "losses" else "rec"
                fig = charts.zones_grid_figure(teams, prefix, spec.sort, th)
                right = [Paragraph(f"{spec.title} by zones", st["h2"]),
                         Paragraph(f'<font color="{th.primary}" name="title-Bold">|||</font>&nbsp; darker = '
                                   "bigger share of the team's total than the league average", st["note"]),
                         Spacer(1, 3)]
                if fig is not None:
                    right.append(_img(charts.to_png(fig), HALF_W - 46))
                out.append(grid([self.ranked_table(teams, spec, HALF_W + 40), right],
                                widths=[HALF_W + 40, HALF_W - 40]))
            return out
        for spec in [s for s in specs if s.wide]:
            out += [self.ranked_table(teams, spec, CONTENT_W), Spacer(1, 12)]
            if title == "Teams: set pieces":
                fig = charts.corners_grid_figure(md, th)
                if fig is not None:
                    out += [Paragraph("Corners distribution", st["h2"]),
                            Paragraph(f'<font color="{th.primary}" name="title-Bold">—</font> delivery&nbsp;&nbsp;&nbsp;'
                                      f'<font color="{th.secondary}" name="title-Bold">—</font> led to a shot '
                                      "within 15 s", st["note"]),
                            _img(charts.to_png(fig), CONTENT_W), Spacer(1, 10)]
        narrow = [s for s in specs if not s.wide]
        if narrow:
            out.append(grid([self.ranked_table(teams, s, HALF_W) for s in narrow]))
        return out

    def player_page(self, title, specs):
        return [Section(title), grid([self.ranked_table(self.md.players, s, HALF_W, player=True, limit=10)
                                      for s in specs])]

    def glossary(self, extra_notes):
      st = self.st
      items = []
      for t, d in GLOSSARY:
        items += [Paragraph(t.upper(), st["gl_t"]), Paragraph(d, st["body"])]
      half = len(items) // 2 + (len(items) // 2) % 2      # split evenly, keep each title with its text
      return [Section("Glossary"), grid([items[:half], items[half:]])]

# --------------------------------------------------------------------------- #
class Section(Flowable):
    """Zero-size marker that tells the page header which section it is on."""

    def __init__(self, name):
        super().__init__()
        self.name = name

    def wrap(self, *a):
        return 0, 0

    def draw(self):
        self.canv._section = self.name


def _img(png: bytes, width: float) -> Image:
    w, h = ImageReader(io.BytesIO(png)).getSize()
    return Image(io.BytesIO(png), width=width, height=width * h / w)


def _img_path(path: str, width: float) -> Image:
    w, h = ImageReader(path).getSize()
    return Image(path, width=width, height=width * h / w)


def grid(items, ncols=2, widths=None, gap=GAP):
    widths = widths or [(CONTENT_W - gap * (ncols - 1)) / ncols] * ncols
    rows = [items[i:i + ncols] + [""] * (ncols - len(items[i:i + ncols])) for i in range(0, len(items), ncols)]
    cw = []
    for i, w in enumerate(widths):
        cw += [w] + ([gap] if i < ncols - 1 else [])
    data = []
    for r in rows:
        line = []
        for i, it in enumerate(r):
            line += [it] + ([""] if i < ncols - 1 else [])
        data.append(line)
    t = RLTable(data, colWidths=cw, hAlign="LEFT")
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                           ("TOPPADDING", (0, 0), (-1, -1), 0)]))
    return t


# --------------------------------------------------------------------------- #
def build_pdf(md: Matchday, competition: str, league: str | None = None, season: str | None = None,
              extra_notes=(), out_path=None) -> bytes:
    """competition: the raw competition name (picks the colour theme and logo).
    league / season: optional overrides for the header text."""
    rp = Report(md, competition, league, season)
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                          topMargin=26 * mm, bottomMargin=14 * mm,
                          title=f"{rp.league} – Gameweek {md.gameweek} report", author="Matchday report")
    frame = Frame(MARGIN, 14 * mm, CONTENT_W, PAGE_H - 40 * mm, id="f", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    cover_frame = Frame(MARGIN, 14 * mm, CONTENT_W, PAGE_H - 28 * mm, id="c")
    doc.addPageTemplates([PageTemplate("cover", [cover_frame], onPage=rp.background),
                          PageTemplate("body", [frame], onPage=rp.background, onPageEnd=rp.header)])
    story = rp.cover() + [NextPageTemplate("body"), PageBreak()]
    story += rp.standings() + [PageBreak()]
    story += rp.matches() + [PageBreak()]
    has_tl = not md.T.empty
    skipped = []
    if not md.goal_events.empty:
        story += rp.goals() + [PageBreak()]
    else:
        skipped.append("Goals by match period")
    for pages, builder in ((TEAM_PAGES, rp.team_page), (PLAYER_PAGES, rp.player_page)):
        for title, specs in pages.items():
            usable = [sp for sp in specs if has_tl or not sp.timeline]
            skipped += [f"{title.split(': ')[0]} – {sp.title}" for sp in specs if sp not in usable]
            if usable:
                story += builder(title, usable) + [PageBreak()]
    if skipped:
        extra_notes = list(extra_notes) + ["Left out because they need timeline (event) data: "
                                           + "; ".join(skipped) + "."]
    story += rp.glossary(extra_notes)
    doc.build(story)
    pdf = buf.getvalue()
    if out_path:
        with open(out_path, "wb") as fh:
            fh.write(pdf)
    return pdf
