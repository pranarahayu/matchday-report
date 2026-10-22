"""Matplotlib figures used by both the PDF and the Streamlit app.

Every function takes a `Theme` (see theme.py) so the same chart renders in the
colours of each competition.
"""
from __future__ import annotations

import io
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Arc, Circle, FancyArrowPatch, Rectangle  # noqa: E402

from .metrics import INTERVALS, PITCH_L, PITCH_W, Matchday  # noqa: E402
from .theme import (CARD, GREEN, INK, INK2, MUTED, RED, ROW_ALT, STRIPE, DEFAULT, Theme,  # noqa: E402
                    logo, logo_file, mpl_font)

plt.rcParams.update({"font.size": 8, "text.color": INK, "axes.edgecolor": "#e4e5ea"})


def T(ax, x, y, s, size=8, weight="Regular", family="body", color=INK, **kw):
    """Text with the report fonts."""
    return ax.text(x, y, s, fontproperties=mpl_font(family, weight), fontsize=size, color=color, **kw)


def team_label(name: str, width: int = 22) -> str:
    n = str(name)
    for suf in (" FC", " F.C."):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n if len(n) <= width else n[: width - 1] + "…"


def to_png(fig, dpi: int = 220, transparent: bool = True) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0.02,
                transparent=transparent)
    plt.close(fig)
    return buf.getvalue()


def _logo(fig, name, kind, color, cx, cy, size, W, H):
    """Place a logo centred on (cx, cy) in figure inches."""
    ax = fig.add_axes([(cx - size / 2) / W, (cy - size / 2) / H, size / W, size / H])
    ax.imshow(logo(kind, name, color))
    ax.axis("off")


# --------------------------------------------------------------------------- #
# pitches (metres)
# --------------------------------------------------------------------------- #
def draw_vertical_pitch(ax, th: Theme, lw=0.7, stripes=14, bg=CARD):
    """Attacking upwards; x = across (0-68), y = along (0-105)."""
    line = th.primary
    ax.add_patch(Rectangle((0, 0), PITCH_W, PITCH_L, fc=bg, ec="none", zorder=0))
    band = PITCH_L / max(stripes, 1)
    for i in range(1, stripes, 2):
        ax.add_patch(Rectangle((0, i * band), PITCH_W, band, fc=STRIPE, ec="none", zorder=0))
    kw = dict(fc="none", ec=line, lw=lw, zorder=1)
    ax.add_patch(Rectangle((0, 0), PITCH_W, PITCH_L, **kw))
    ax.plot([0, PITCH_W], [PITCH_L / 2] * 2, color=line, lw=lw, zorder=1)
    ax.add_patch(Circle((PITCH_W / 2, PITCH_L / 2), 9.15, **kw))
    for y0, s in ((0, 1), (PITCH_L, -1)):
        ax.add_patch(Rectangle((PITCH_W / 2 - 20.16, y0), 40.32, 16.5 * s, **kw))
        ax.add_patch(Rectangle((PITCH_W / 2 - 9.16, y0), 18.32, 5.5 * s, **kw))
        ax.add_patch(Arc((PITCH_W / 2, y0 + 11 * s), 18.3, 18.3, theta1=37 if s > 0 else 217,
                         theta2=143 if s > 0 else 323, ec=line, lw=lw, zorder=1))
        ax.plot([PITCH_W / 2 - 3.66, PITCH_W / 2 + 3.66], [y0, y0], color=line, lw=lw * 3.2,
                solid_capstyle="butt", zorder=1)
        ax.add_patch(Circle((PITCH_W / 2, y0 + 11 * s), 0.35, fc=line, ec="none", zorder=1))
        for xc in (0, PITCH_W):
            a0 = {(0, 1): 0, (1, 1): 90, (1, -1): 180, (0, -1): 270}[(int(xc > 0), s)]
            ax.add_patch(Arc((xc, y0), 2.4, 2.4, theta1=a0, theta2=a0 + 90, ec=line, lw=lw * 0.8, zorder=1))
    ax.add_patch(Circle((PITCH_W / 2, PITCH_L / 2), 0.35, fc=line, ec="none", zorder=1))
    ax.set_xlim(-0.8, PITCH_W + 0.8)
    ax.set_ylim(-0.8, PITCH_L + 0.8)
    ax.set_aspect("equal")
    ax.axis("off")


def draw_horizontal_pitch(ax, th: Theme, lw=0.5, bg=CARD, line=None):
    line = line or th.tint(0.55)
    ax.add_patch(Rectangle((0, 0), PITCH_L, PITCH_W, fc=bg, ec=line, lw=lw, zorder=1))
    ax.plot([PITCH_L / 2] * 2, [0, PITCH_W], color=line, lw=lw, zorder=1)
    ax.add_patch(Circle((PITCH_L / 2, PITCH_W / 2), 9.15, fc="none", ec=line, lw=lw, zorder=1))
    for x0, s in ((0, 1), (PITCH_L, -1)):
        ax.add_patch(Rectangle((x0, PITCH_W / 2 - 20.16), 16.5 * s, 40.32, fc="none", ec=line, lw=lw, zorder=1))
        ax.add_patch(Rectangle((x0, PITCH_W / 2 - 9.16), 5.5 * s, 18.32, fc="none", ec=line, lw=lw, zorder=1))
    ax.set_xlim(-1, PITCH_L + 1)
    ax.set_ylim(-1, PITCH_W + 1)
    ax.set_aspect("equal")
    ax.axis("off")


def _plot_lineup(ax, pos: pd.DataFrame, th: Theme, is_avg: bool):
    draw_vertical_pitch(ax, th)
    for _, p in pos.iterrows():
        px, py = p.y * PITCH_W / 100, p.x * PITCH_L / 100     # y across (0 = left), x along
        ax.add_patch(Circle((px, py), 2.45, fc=th.primary, ec=CARD, lw=0.6, zorder=3))
        T(ax, px, py - 0.15, p.label, size=4.6 if is_avg else 3.6, weight="Bold", family="title",
          color=CARD, ha="center", va="center", zorder=4)
        if p.subbed_off or p.role == "sub_in":
            ax.add_patch(Circle((px - 1.9, py + 1.9), 0.95, fc=RED if p.subbed_off else GREEN,
                                ec=CARD, lw=0.4, zorder=5))
    if not is_avg:
        T(ax, PITCH_W / 2, 1.8, "nominal positions – no event data", size=4.6, color=MUTED,
          ha="center", va="bottom", zorder=5)


def _fmt(v, kind):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    if kind == "pct":
        return f"{v:.0f}%"
    if kind == "f2":
        return f"{v:.2f}"
    return f"{int(round(v))}"


MATCH_STATS = ["Shots", "On target", "Corners", "Fouls", "Yellow cards", "Red cards", "Possession"]


def match_figure(md: Matchday, match: str, th: Theme = DEFAULT):
    m = md.matches.set_index("Match").loc[match]
    W, H = 7.15, 5.0
    fig = plt.figure(figsize=(W, H))
    bg = fig.add_axes([0, 0, 1, 1]); bg.axis("off")
    bg.set_xlim(0, W); bg.set_ylim(0, H)

    pw = 2.25
    ph = pw * PITCH_L / PITCH_W
    pad, y_p = 0.09, 0.12
    left_x, right_x = pad, W - pad - pw
    # white cards behind the pitches
    for x in (left_x, right_x):
        bg.add_patch(Rectangle((x - pad, 0), pw + 2 * pad, ph + y_p + pad, fc=CARD, ec="none"))
    for team, x in ((m.home, left_x), (m.away, right_x)):
        ax = fig.add_axes([x / W, y_p / H, pw / W, ph / H])
        pos, is_avg = md.lineup_positions(match, team)
        _plot_lineup(ax, pos, th, is_avg)
        _logo(fig, team, "teams", th.primary, x + pw / 2, ph + y_p + 0.62, 0.82, W, H)

    # score + meta
    cx = W / 2
    T(bg, cx, ph + y_p + 0.72, f"{int(m.hg)}  –  {int(m.ag)}", size=36, weight="Bold", family="title",
      color=th.primary, ha="center", va="center")
    date = m.date.strftime("%d %b %Y %H:%M") if pd.notna(m.date) else ""
    T(bg, cx, ph + y_p + 0.24, f"{date}  ///  {m.venue}", size=5.6, color=th.primary,
      ha="center", va="center")
    for team, x in ((m.home, left_x), (m.away, right_x)):
        if not os.path.exists(logo_file("teams", team)):      # name only under placeholder badges
            T(bg, x + pw / 2, ph + y_p + 0.12, team_label(team, 28), size=6.5, weight="Medium",
              family="title", color=INK, ha="center", va="bottom")

    # stats panel geometry
    x0, x1 = left_x + pw + 0.42, right_x - 0.42
    lines = {l: (h, a, k) for l, h, a, k in md.match_stat_lines(match)}
    rows = [(s, *lines[s]) for s in MATCH_STATS if s in lines]
    n = len(rows)
    row_h = 0.31
    top = y_p + n * row_h

    # goal / red-card list between the score and the stats
    ev = md.match_events(match)
    ev_top, ev_bot = ph + y_p - 0.12, top + 0.12
    if len(ev):
        step = min(0.15, (ev_top - ev_bot) / max(len(ev), 1))
        for i, r in enumerate(ev.itertuples()):        # chronological, one event per line
            yy = ev_top - i * step
            home = r.team == m.home
            xa, ha = (x0, "left") if home else (x1, "right")
            ix = xa + (0.05 if home else -0.05)
            if r.icon == "goal":
                bg.add_patch(Circle((ix, yy), 0.032, fc=th.primary, ec="none"))
            else:
                bg.add_patch(Rectangle((ix - 0.025, yy - 0.04), 0.05, 0.075, fc=RED, ec="none"))
            T(bg, xa + (0.13 if home else -0.13), yy, f"{r.label}  {r.name}".strip(), size=5.6,
              color=INK2, ha=ha, va="center")

    for i, (label, hv, av, kind) in enumerate(rows):
        yb = top - (i + 1) * row_h
        alt = i % 2 == 1
        bg.add_patch(Rectangle((x0, yb), x1 - x0, row_h, fc=ROW_ALT if alt else CARD, ec="none"))
        hvn = 0 if pd.isna(hv) else float(hv)
        avn = 0 if pd.isna(av) else float(av)
        share = avn / (hvn + avn) if (hvn + avn) else 0
        if share:
            w = (x1 - x0) * share
            bg.add_patch(Rectangle((x1 - w, yb), w, row_h, ec="none",
                                   fc=th.tint(0.78 if alt else 0.86)))
        yc = yb + row_h / 2
        T(bg, x0 + 0.08, yc, _fmt(hv, kind), size=6.6, weight="Bold", family="title",
          color=th.primary, ha="left", va="center")
        T(bg, x1 - 0.08, yc, _fmt(av, kind), size=6.6, weight="Bold", family="title",
          color=th.primary, ha="right", va="center")
        T(bg, (x0 + x1) / 2, yc, label.upper(), size=5.2, color=th.primary, ha="center", va="center")
    return fig


# --------------------------------------------------------------------------- #
def goal_dynamics_figure(table: pd.DataFrame, th: Theme = DEFAULT, conceded=False):
    if table.empty:
        return None
    col = th.secondary if conceded else th.primary
    seq = th.seq(5, col)
    n = len(table)
    fig, ax = plt.subplots(figsize=(3.45, 0.27 * n + 0.42))
    vmax = max(table[INTERVALS].values.max(), 1)
    for i, (team, row) in enumerate(table.iterrows()):
        yy = n - 1 - i
        ax.axhline(yy, color="#e7e8ec", lw=0.5, zorder=0)
        for j, iv in enumerate(INTERVALS):
            v = row[iv]
            if v > 0:
                c = seq[min(4, 2 + int(round((v / vmax) * 2)))]
                ax.scatter(j, yy, s=55 + 65 * v, color=c, edgecolor=CARD, lw=1, zorder=3)
                T(ax, j, yy - 0.02, int(v), size=5.5, weight="Bold", family="title",
                  color=CARD if c != seq[0] else INK, ha="center", va="center", zorder=4)
    ax.set_yticks(range(n))
    ax.set_yticklabels([team_label(t, 20) for t in table.index[::-1]])
    for lab in ax.get_yticklabels():
        lab.set_fontproperties(mpl_font("body", "Regular")); lab.set_fontsize(6.6)
    ax.set_xticks(range(len(INTERVALS)))
    ax.set_xticklabels(INTERVALS)
    for lab in ax.get_xticklabels():
        lab.set_fontproperties(mpl_font("body", "Regular")); lab.set_fontsize(5.6); lab.set_color(MUTED)
    ax.xaxis.tick_top()
    ax.set_xlim(-0.5, len(INTERVALS) - 0.5); ax.set_ylim(-0.6, n - 0.4)
    ax.set_facecolor("none")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    return fig


def zones_grid_figure(teams: pd.DataFrame, prefix: str, total: str, th: Theme = DEFAULT, ncols: int = 3):
    """Mini pitches; thirds shaded darker the more a team's share exceeds the league's."""
    t = teams[teams[total].notna() & (teams[total] > 0)].sort_values(total, ascending=prefix == "loss")
    if t.empty:
        return None
    zones = [f"{prefix}_own", f"{prefix}_mid", f"{prefix}_fin"]
    shares = t[zones].div(t[total], axis=0)
    league = shares.mean()
    seq = [CARD] + th.seq(4)
    nrows = int(np.ceil(len(t) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.2, 0.78 * nrows + 0.1))
    axes = np.atleast_1d(axes).ravel()
    for ax in axes:
        ax.axis("off")
    for ax, (idx, row) in zip(axes, t.iterrows()):
        for k, z in enumerate(zones):
            diff = shares.loc[idx, z] - league[z]
            lvl = 0 if diff <= 0 else min(4, 1 + int(diff / 0.04))
            ax.add_patch(Rectangle((k * PITCH_L / 3, 0), PITCH_L / 3, PITCH_W, fc=seq[lvl], ec="none", zorder=0))
        draw_horizontal_pitch(ax, th, lw=0.4, bg="none")
        T(ax, PITCH_L / 2, PITCH_W + 3, team_label(row.Team, 18), size=5.2, color=INK, ha="center", va="bottom")
        ax.set_ylim(-1, PITCH_W + 13)
    plt.subplots_adjust(wspace=0.08, hspace=0.05)
    return fig


def corners_grid_figure(md: Matchday, th: Theme = DEFAULT, ncols: int = 6):
    c = md.corner_events()
    if c.empty:
        return None
    c = c[c.X2.notna()]
    teams = c.groupby("Team").size().sort_values(ascending=False).index
    nrows = int(np.ceil(len(teams) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(7.2, 0.98 * nrows))
    axes = np.atleast_1d(axes).ravel()
    for ax in axes:
        ax.axis("off")
    for ax, team in zip(axes, teams):
        g = c[c.Team == team]
        draw_vertical_pitch(ax, th, lw=0.45, stripes=0)
        ax.set_ylim(PITCH_L - 32, PITCH_L + 10)
        for _, e in g.iterrows():
            p1 = (e.Y1 * PITCH_W / 100, e.X1 * PITCH_L / 100)
            p2 = (e.Y2 * PITCH_W / 100, e.X2 * PITCH_L / 100)
            col = th.secondary if e.with_shot else th.primary
            ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=5,
                                         color=col, lw=0.7, alpha=0.95, zorder=3))
        T(ax, 0, PITCH_L + 3, f"{team_label(team, 15)} ({len(g)})", size=5, color=INK, va="bottom")
    plt.subplots_adjust(wspace=0.06, hspace=0.15)
    return fig
