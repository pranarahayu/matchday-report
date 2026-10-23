"""Competition themes, fonts and logos.

Logos
-----
Drop PNG files (transparent background works best) into:

    assets/logos/competitions/<slug>.png     e.g. bri-super-league.png
    assets/logos/teams/<slug>.png            e.g. persija-jakarta.png

<slug> is the name in lower case with anything that is not a letter or digit
replaced by "-" (see `slug()`); the app's "Data & glossary" tab lists the exact
file names it looks for. Until a file exists a placeholder badge is drawn.

Fonts
-----
Titles use Poppins. Body text uses Be Vietnam Pro when its .ttf files are in
assets/fonts (BeVietnamPro-Light/Regular/Medium/SemiBold/Bold.ttf); otherwise
Poppins is used for everything.
"""
from __future__ import annotations

import functools
import os
import re
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
LOGO_DIR = os.path.join(ROOT, "assets", "logos")

GREEN, RED = "#1f9d55", "#e3262b"     # substitution markers (as in the template)
INK, INK2, MUTED = "#1b1d22", "#4a4d55", "#8b8f98"
PAGE_BG, CARD, STRIPE, ROW_ALT = "#ffffff", "#ffffff", "#f5f6f9", "#f3f4f7"


# --------------------------------------------------------------------------- #
def mix(hex1: str, hex2: str, t: float) -> str:
    """Blend hex1 -> hex2 by t (0 = hex1, 1 = hex2)."""
    a = [int(hex1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


@dataclass(frozen=True)
class Theme:
    name: str               # display name in headers
    primary: str
    secondary: str
    keywords: tuple = ()

    def tint(self, t: float, color: str | None = None) -> str:
        """t=0 -> full colour, t=1 -> white."""
        return mix(color or self.primary, "#ffffff", t)

    @property
    def slug(self) -> str:
        return slug(self.name)

    def seq(self, n: int = 5, color: str | None = None) -> list[str]:
        """Light -> dark sequential steps of one hue."""
        c = color or self.primary
        return [mix(c, "#ffffff", t) for t in [0.85, 0.65, 0.45, 0.22, 0.0][-n:]]


THEMES = [
    Theme("BRI Super League", "#00529c", "#ed1c24", ("super league", "liga 1", "bri")),
    Theme("Pegadaian Championship", "#034d43", "#fac61b", ("championship", "pegadaian", "liga 2")),
    Theme("Indonesian Women's League", "#ec008d", "#d4af37", ("women", "wanita", "putri", "perempuan")),
]
DEFAULT = Theme("League", "#00529c", "#ed1c24")


def theme_for(competition: str) -> Theme:
    c = competition.lower()
    for th in THEMES:
        if any(k in c for k in th.keywords):
            return th
    return Theme(competition, DEFAULT.primary, DEFAULT.secondary)


def season_and_label(competition: str) -> str:
    """'Super League 2026-27' -> '2026-27'."""
    m = re.search(r"((?:19|20)\d{2})\s*[-/–]\s*(\d{2,4})", competition)
    if m:
        return f"{m.group(1)}-{m.group(2)[-2:]}"
    m = re.search(r"(19|20)\d{2}", competition)
    return m.group(0) if m else ""


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")


# --------------------------------------------------------------------------- #
# fonts
# --------------------------------------------------------------------------- #
def font_path(family: str, weight: str) -> str:
    """family: 'title' (Poppins) or 'body' (Be Vietnam Pro if present)."""
    order = {"Light": ["Light", "Regular"], "Regular": ["Regular"], "Medium": ["Medium", "Regular"],
             "SemiBold": ["SemiBold", "Bold", "Medium"], "Bold": ["Bold", "SemiBold"]}[weight]
    fams = ["BeVietnamPro", "Poppins"] if family == "body" else ["Poppins"]
    for fam in fams:
        for w in order:
            p = os.path.join(FONT_DIR, f"{fam}-{w}.ttf")
            if os.path.exists(p):
                return p
    import matplotlib
    return os.path.join(matplotlib.get_data_path(), "fonts", "ttf",
                        "DejaVuSans-Bold.ttf" if weight in ("Bold", "SemiBold") else "DejaVuSans.ttf")


def has_body_font() -> bool:
    return os.path.exists(os.path.join(FONT_DIR, "BeVietnamPro-Regular.ttf"))


@functools.lru_cache(maxsize=None)
def mpl_font(family: str, weight: str):
    from matplotlib.font_manager import FontProperties
    return FontProperties(fname=font_path(family, weight))


# --------------------------------------------------------------------------- #
# logos
# --------------------------------------------------------------------------- #
_STOP = {"fc", "f", "c", "ps", "the"}


def name_tokens(name: str) -> frozenset:
    """Words of a club name, ignoring case, punctuation and FC/PS."""
    return frozenset(t for t in re.split(r"[^a-z0-9]+", str(name).lower()) if t and t not in _STOP)


def match_name(name: str, candidates) -> str | None:
    """Candidate that is the same club as `name`: exact word match first, otherwise one
    name containing the other ("PERSIB" ~ "PERSIB Bandung"), only if that is unambiguous."""
    want = name_tokens(name)
    exact = [c for c in candidates if name_tokens(c) == want]
    if exact:
        return exact[0]
    cand = [c for c in candidates if want and (want <= name_tokens(c) or name_tokens(c) <= want)]
    return cand[0] if len(cand) == 1 else None


@functools.lru_cache(maxsize=8)
def _logo_index(kind: str) -> dict:
    folder = os.path.join(LOGO_DIR, kind)
    if not os.path.isdir(folder):
        return {}
    return {f[:-4].replace("-", " "): os.path.join(folder, f)
            for f in os.listdir(folder) if f.lower().endswith(".png")}


def logo_file(kind: str, name: str) -> str:
    """Path of the logo for `name` (fuzzy-matched); the exact-slug path if none exists yet."""
    exact = os.path.join(LOGO_DIR, kind, f"{slug(name)}.png")
    if os.path.exists(exact):
        return exact
    idx = _logo_index(kind)
    hit = match_name(name, list(idx))
    return idx[hit] if hit else exact


def initials(name: str) -> str:
    words = [w for w in re.split(r"[\s\-]+", str(name)) if w and w.upper() not in ("FC", "F.C.")]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(w[0] for w in words[:3]).upper()


@functools.lru_cache(maxsize=256)
def logo(kind: str, name: str, color: str, size: int = 256) -> Image.Image:
    """Real logo if the PNG exists, otherwise a shield placeholder with initials."""
    p = logo_file(kind, name)
    if os.path.exists(p):
        im = Image.open(p).convert("RGBA")
        im.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
        return canvas
    S = size * 4  # supersample for smooth edges
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w, h = S * 0.74, S * 0.86
    x0, y0 = (S - w) / 2, (S - h) / 2
    shield = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h * 0.58), (S / 2, y0 + h), (x0, y0 + h * 0.58)]
    d.polygon(shield, fill=mix(color, "#ffffff", 0.88), outline=color, width=int(S * 0.025))
    txt = initials(name)
    fnt = ImageFont.truetype(font_path("title", "Bold"), int(S * (0.26 if len(txt) <= 2 else 0.2)))
    bb = d.textbbox((0, 0), txt, font=fnt)
    d.text(((S - (bb[2] - bb[0])) / 2 - bb[0], y0 + h * 0.36 - (bb[3] - bb[1]) / 2 - bb[1]), txt,
           fill=color, font=fnt)
    return im.resize((size, size), Image.LANCZOS)
