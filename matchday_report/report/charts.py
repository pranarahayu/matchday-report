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


def _plot_lineup(ax, pos: pd.DataFrame, th: Theme, is_avg: bool, def_line: float = np.nan):
    draw_vertical_pitch(ax, th)
    if is_avg and pd.notna(def_line):          # metres from own goal (bottom of the pitch)
        ax.plot([0.6, PITCH_W - 0.6], [def_line, def_line], color=th.secondary, lw=0.9,
                ls=(0, (3, 2)), zorder=2.5, solid_capstyle="butt")
        T(ax, PITCH_W - 1.2, def_line + 0.9, f"DEF. LINE {def_line:.0f} m", size=4.4, weight="Bold",
          family="title", color=th.secondary, ha="right", va="bottom", zorder=5)
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
    if kind == "m":
        return f"{v:.1f} m"
    if kind == "pct":
        return f"{v:.0f}%"
    if kind == "f2":
        return f"{v:.2f}"
    return f"{int(round(v))}"


fmt_stat = _fmt

MATCH_STATS = ["Shots", "On target", "xG", "xT", "Corners", "Fouls", "Yellow cards", "Red cards", "Possession",
               "Field tilt"]


def match_figure(md: Matchday, match: str, th: Theme = DEFAULT, with_xg: bool = True,
                 with_xt: bool = True):
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
        _plot_lineup(ax, pos, th, is_avg, md.team_value(match, team, "def_line"))
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
    rows = [(s, *lines[s]) for s in MATCH_STATS if s in lines and (with_xg or s != "xG")
            and (with_xt or s != "xT")]
    n = len(rows)
    row_h = min(0.31, 2.6 / max(n, 1))
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
XG_BINS = [0.15, 0.4, 0.8]           # xG per interval: <0.15 | 0.15-0.4 | 0.4-0.8 | 0.8+


def goal_dynamics_figure(table: pd.DataFrame, th: Theme = DEFAULT, conceded=False, with_xg: bool = True):
    """Goals per 15-minute interval: dot size = goals, dot colour = xG in that interval.
    Intervals with chances but no goal get a small dot. Total xG is printed on the right."""
    if table.empty:
        return None
    col = th.secondary if conceded else th.primary
    seq = th.seq(5, col)                      # light -> dark
    has_xg = with_xg and "xG" in table.columns
    n = len(table)
    fig, ax = plt.subplots(figsize=(3.45, 0.25 * n + 0.75))

    def shade(xg):
        return seq[1 + int(np.searchsorted(XG_BINS, xg, side="right"))]

    for i, (team, row) in enumerate(table.iterrows()):
        yy = n - 1 - i
        ax.axhline(yy, color="#e7e8ec", lw=0.5, zorder=0)
        for j, iv in enumerate(INTERVALS):
            g = row[iv]
            xg = row.get(f"xG {iv}", np.nan) if has_xg else np.nan
            c = shade(xg) if has_xg else seq[min(4, 2 + int(g))]
            if g > 0:
                ax.scatter(j, yy, s=55 + 60 * g, color=c, edgecolor=CARD, lw=1, zorder=3)
                T(ax, j, yy - 0.02, int(g), size=5.5, weight="Bold", family="title",
                  color=CARD if c not in seq[:2] else INK, ha="center", va="center", zorder=4)
            elif has_xg and xg >= 0.05:
                ax.scatter(j, yy, s=16, color=c, edgecolor="none", zorder=3)
        if has_xg:
            T(ax, len(INTERVALS) - 0.25, yy, f"{row['xG']:.2f}", size=6, color=INK2, ha="left", va="center")
    ax.set_yticks(range(n))
    ax.set_yticklabels([team_label(t, 20) for t in table.index[::-1]])
    for lab in ax.get_yticklabels():
        lab.set_fontproperties(mpl_font("body", "Regular")); lab.set_fontsize(6.6)
    ax.set_xticks(range(len(INTERVALS)))
    ax.set_xticklabels([iv.rstrip("'") for iv in INTERVALS])
    for lab in ax.get_xticklabels():
        lab.set_fontproperties(mpl_font("body", "Regular")); lab.set_fontsize(5); lab.set_color(MUTED)
    ax.xaxis.tick_top()
    right = len(INTERVALS) + 0.35 if has_xg else len(INTERVALS) - 0.5
    if has_xg:
        T(ax, len(INTERVALS) - 0.25, n - 0.4 + 0.35, "xG", size=5.6, color=MUTED, ha="left", va="bottom",
          clip_on=False)
    ax.set_xlim(-0.5, right); ax.set_ylim(-0.6, n - 0.4)
    ax.set_facecolor("none")
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0)
    if has_xg:                                 # legend: colour = xG, size = goals
        T(ax, -0.5, -1.15, "xG in interval:", size=5, color=INK2, va="center", clip_on=False)
        for k, lab in enumerate(["< 0.15", "0.15–0.4", "0.4–0.8", "0.8+"]):
            x = 1.15 + k * 1.15
            ax.scatter(x, -1.15, s=30, color=seq[1 + k], edgecolor="none", clip_on=False)
            T(ax, x + 0.18, -1.15, lab, size=5, color=INK2, va="center", clip_on=False)
        T(ax, -0.5, -1.75, "Dot size = goals  ·  small dot = chances but no goal", size=5, color=MUTED,
          va="center", clip_on=False)
        ax.set_ylim(-2.05, n - 0.4)
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


# --------------------------------------------------------------------------- #
def shot_map_figure(md: Matchday, match: str, th: Theme = DEFAULT):
    """Both teams' shots on one pitch (home attacks right, away attacks left).
    Circle area = xG; filled = goal, outlined = no goal."""
    if md.T.empty or "xg" not in md.T:
        return None
    m = md.matches.set_index("Match").loc[match]
    sh = md.T[(md.T.Match == match) & md.T["xg"].notna()]
    if sh.empty:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 4.9))
    draw_horizontal_pitch(ax, th, lw=0.7, line=th.tint(0.35))
    for team, col, mirror in ((m.home, th.primary, False), (m.away, th.secondary, True)):
        s = sh[sh.Team == team]
        x = s.X1 * PITCH_L / 100
        y = (100 - s.Y1) * PITCH_W / 100            # attacking left side drawn at the top
        if mirror:
            x, y = PITCH_L - x, PITCH_W - y
        size = 30 + 900 * s["xg"]
        goal = s["is_goal"].astype(bool)
        ax.scatter(x[~goal], y[~goal], s=size[~goal], facecolor="none", edgecolor=col, lw=1.3, zorder=3)
        ax.scatter(x[goal], y[goal], s=size[goal], color=col, edgecolor=CARD, lw=0.8, zorder=4)
        lbl = f"{team_label(team, 24)}   {int(goal.sum())} goals · {s.xg.sum():.2f} xG · {len(s)} shots"
        T(ax, PITCH_L if not mirror else 0, PITCH_W + 2.5, lbl, size=7, weight="Medium", family="title",
          color=col, ha="right" if not mirror else "left", va="bottom")
    T(ax, PITCH_L / 2, -2.5, "circle size = xG  ·  filled = goal", size=6, color=MUTED, ha="center", va="top")
    ax.set_ylim(-6, PITCH_W + 8)
    return fig


# --------------------------------------------------------------------------- #
def xt_zone_figure(md: Matchday, match: str, th: Theme = DEFAULT):
    """Where each team created threat: xT added by completed passes and carries, summed by the
    zone the action started in (same 12 x 8 zones as the grid). Both attack left -> right."""
    from .xt import load_grid
    grid = load_grid()
    if grid is None or md.T.empty or "xt" not in md.T:
        return None
    m = md.matches.set_index("Match").loc[match]
    ev = md.T[(md.T.Match == match) & md.T["xt"].notna()]
    if ev.empty:
        return None
    ny, nx = grid.shape
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 2.75))
    vmax = 0.0
    sums = {}
    for team in (m.home, m.away):
        e = ev[ev.Team == team]
        c = np.clip((e.X1 / 100 * nx).astype(int), 0, nx - 1)
        r = np.clip((e.Y1 / 100 * ny).astype(int), 0, ny - 1)
        z = np.zeros((ny, nx))
        np.add.at(z, (r.to_numpy(), c.to_numpy()), e["xt"].to_numpy())
        sums[team] = (z, e["xt"].sum())
        vmax = max(vmax, z.max())
    for ax, (team, col) in zip(axes, ((m.home, th.primary), (m.away, th.secondary))):
        z, tot = sums[team]
        seq = th.seq(5, col)
        for i in range(ny):
            for j in range(nx):
                v = z[i, j]
                lvl = 0 if v <= 0 or vmax <= 0 else 1 + min(3, int((v / vmax) ** 0.5 * 4))
                ax.add_patch(Rectangle((j * PITCH_L / nx, (ny - 1 - i) * PITCH_W / ny), PITCH_L / nx,
                                       PITCH_W / ny, fc=CARD if lvl == 0 else seq[lvl], ec="none", zorder=0))
        draw_horizontal_pitch(ax, th, lw=0.5, bg="none")
        T(ax, 0, PITCH_W + 2, f"{team_label(team, 24)}   xT {tot:.2f}", size=7, weight="Medium",
          family="title", color=col, va="bottom")
        ax.set_ylim(-1, PITCH_W + 9)
    T(axes[0], 0, -3, "darker = more threat added by passes and carries starting in that zone  ·  both teams attack left to right",
      size=5.5, color=MUTED, va="top")
    plt.subplots_adjust(wspace=0.06)
    return fig
