"""Loading the two input files.

* report.xlsx   – one row per player per match (aggregated match stats)
* timeline.xlsx – one row per event, with pitch coordinates (0-100, every team
                  attacking left -> right, Y=0 is the attacking team's left side)

Some exporters write .xlsx files whose zip "central directory" is missing or
truncated; Excel/pandas then refuse to open them. `read_timeline` falls back
to a tolerant reader that recovers every complete row it can find.
"""
from __future__ import annotations

import html
import io
import re
import struct
import zlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #
def _to_bytes(src) -> bytes:
    """Accept a path, bytes, or a file-like object (e.g. Streamlit upload)."""
    if isinstance(src, (bytes, bytearray)):
        return bytes(src)
    if hasattr(src, "getvalue"):
        return src.getvalue()
    if hasattr(src, "read"):
        return src.read()
    with open(src, "rb") as fh:
        return fh.read()


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def recover_xlsx(raw: bytes) -> tuple[pd.DataFrame, dict]:
    """Rebuild the first worksheet of a damaged .xlsx from its local zip entries."""
    entries: dict[str, bytes] = {}
    i = 0
    while True:
        i = raw.find(b"PK\x03\x04", i)
        if i < 0:
            break
        try:
            _, flag, method, _, _, _, csize, _, nlen, elen = struct.unpack(
                "<HHHHHIIIHH", raw[i + 4:i + 30])
        except struct.error:
            break
        name = raw[i + 30:i + 30 + nlen].decode("utf-8", "ignore")
        start = i + 30 + nlen + elen
        end = start + csize if (csize and not flag & 8) else len(raw)
        chunk = raw[start:end]
        if method == 8:
            dec = zlib.decompressobj(-15)
            try:
                data = dec.decompress(chunk)
            except zlib.error:
                data = b""
        else:
            data = chunk
        entries[name] = data
        i = start + 1

    shared: list[str] = []
    if "xl/sharedStrings.xml" in entries:
        sx = entries["xl/sharedStrings.xml"].decode("utf-8", "ignore")
        for si in re.findall(r"<si>(.*?)</si>", sx, re.S):
            shared.append(html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))))

    sheet_name = next((n for n in entries if n.startswith("xl/worksheets/sheet")), None)
    if sheet_name is None:
        raise ValueError("No worksheet could be recovered from the file.")
    xml = entries[sheet_name].decode("utf-8", "ignore")

    dim = re.search(r'<dimension ref="[A-Z]+\d+:[A-Z]+(\d+)"', xml)
    declared_rows = int(dim.group(1)) if dim else None

    cell_re = re.compile(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>(.*?)</c>)', re.S)
    rows = []
    for body in re.findall(r"<row [^>]*>(.*?)</row>", xml, re.S):
        rec = {}
        for col, attrs, inner in cell_re.findall(body):
            inner = inner or ""
            t = re.search(r't="(\w+)"', attrs)
            ctype = t.group(1) if t else "n"
            if ctype == "inlineStr":
                m = re.search(r"<t[^>]*>(.*?)</t>", inner, re.S)
                val = html.unescape(m.group(1)) if m else None
            else:
                m = re.search(r"<v>(.*?)</v>", inner, re.S)
                val = m.group(1) if m else None
                if val is not None and ctype == "s":
                    val = shared[int(val)] if int(val) < len(shared) else None
                elif val is not None and ctype == "str":
                    val = html.unescape(val)
            rec[_col_index(col)] = val
        rows.append(rec)
    if not rows:
        raise ValueError("The worksheet is empty or unreadable.")
    header = rows[0]
    ncol = max(header) + 1
    cols = [header.get(k) or f"col{k}" for k in range(ncol)]
    df = pd.DataFrame([[r.get(k) for k in range(ncol)] for r in rows[1:]], columns=cols)
    info = {
        "recovered": True,
        "rows_recovered": len(df),
        "rows_declared": (declared_rows - 1) if declared_rows else None,
    }
    return df, info


# --------------------------------------------------------------------------- #
# Public loaders
# --------------------------------------------------------------------------- #
@dataclass
class LoadInfo:
    recovered: bool = False
    rows_recovered: int = 0
    rows_declared: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def truncated(self) -> bool:
        return bool(self.rows_declared and self.rows_recovered < self.rows_declared)


def read_report(src) -> pd.DataFrame:
    raw = _to_bytes(src)
    try:
        df = pd.read_excel(io.BytesIO(raw))
    except Exception:  # damaged zip – same recovery as the timeline
        df, _ = recover_xlsx(raw)
    df.columns = [str(c).strip() for c in df.columns]
    num_cols = df.columns.difference(
        ["Name", "Position (in match)", "Team", "Opponent", "Match", "Home/Away",
         "Venue", "Date", "Result", "Starter/Subs", "Subs", "Nick"])
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["Match"] = df["Match"].astype(str).str.strip()
    df["Team"] = df["Team"].astype(str).str.strip()
    df["Opponent"] = df["Opponent"].astype(str).str.strip()
    return df.copy()


def _parse_clock(s) -> float:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return np.nan
    m = re.match(r"\s*(\d+)\s*:\s*(\d+)", str(s))
    if not m:
        return np.nan
    return int(m.group(1)) * 60 + int(m.group(2))


def read_timeline(src) -> tuple[pd.DataFrame, LoadInfo]:
    raw = _to_bytes(src)
    info = LoadInfo()
    try:
        df = pd.read_excel(io.BytesIO(raw))
    except Exception:
        df, meta = recover_xlsx(raw)
        info.recovered = True
        info.rows_recovered = meta["rows_recovered"]
        info.rows_declared = meta["rows_declared"]
        if info.truncated:
            info.notes.append(
                f"Timeline file is damaged/truncated: recovered {info.rows_recovered:,} of "
                f"{info.rows_declared:,} event rows. Stats that need event coordinates are "
                f"incomplete for the affected matches.")
        else:
            info.notes.append("Timeline file had a damaged zip directory; all rows were recovered.")
    df.columns = [str(c).strip() for c in df.columns]
    info.rows_recovered = info.rows_recovered or len(df)

    for c in ["ID", "Match ID", "Gameweek", "Num", "Player ID", "X1", "Y1", "X2", "Y2",
              "Num.1", "Passed Player ID", "xg value", "Player Match ID",
              "Passed Player Match ID"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["Match", "Team", "Action", "Act Name", "Pas Name", "Stage",
              "Sub 1", "Sub 2", "Sub 3", "Sub 4"]:
        if c in df.columns:
            df[c] = df[c].astype("string").str.strip()
    df["Action"] = df["Action"].str.lower()
    # "Home vs Away" -> "Home - Away" so it joins with report.xlsx
    df["Match"] = df["Match"].str.replace(r"\s+vs\.?\s+", " - ", regex=True)
    df["sec"] = df["Min"].map(_parse_clock)
    df["period"] = np.where(df["Stage"].str.contains("2", na=False), 2, 1)
    df = df.sort_values(["Match", "period", "sec", "ID"]).reset_index(drop=True)
    return df, info
