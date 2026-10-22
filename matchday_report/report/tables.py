"""Turn a spec (see specs.py) into ranked, formatted rows."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .charts import team_label
from .specs import Col, Table


def _nan(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v)


def col_header(col: Col, rich: bool = False) -> str:
    """Column heading. Attempts/successful columns say so: 'Total/Success', or the
    column's own name with 'total/success' underneath (PDF) / in brackets (app)."""
    if col.kind != "pair" or "/" in col.label:
        return col.label
    if col.label == "Total":
        return "Total/Success"
    return f"{col.label}<br/>total/success" if rich else f"{col.label} (total/success)"


def fmt_value(row, col: Col, rich: bool = False) -> str:
    """rich=True returns ReportLab mini-markup (smaller grey % part)."""
    v = row.get(col.key, np.nan)
    if _nan(v):
        return "–"
    small = (lambda s: f' <font size="5.5" color="#8a8984">{s}</font>') if rich else (lambda s: f"  {s}")
    if col.kind == "int":
        return f"{v:.0f}" if abs(v - round(v)) < 1e-9 else f"{v:.1f}"
    if col.kind == "f1":
        return f"{v:.1f}"
    if col.kind == "f2":
        return f"{v:.2f}"
    if col.kind == "pct":
        return f"{v:.1f}%"
    if col.kind == "pair":
        s = row.get(col.key2, np.nan)
        if _nan(s):
            return f"{v:.0f}"
        pct = f"{100 * s / v:.0f}%" if v else "–"
        fa = lambda x: f"{x:.0f}" if abs(x - round(x)) < 1e-9 else f"{x:.1f}"
        return f"{fa(v)}/{fa(s)}" + small(pct)
    if col.kind == "part":
        tot = row.get(col.key2, np.nan)
        pct = f"{100 * v / tot:.0f}%" if tot else "–"
        return (f"{v:.0f}" if abs(v - round(v)) < 1e-9 else f"{v:.1f}") + small(pct)
    return str(v)


def ranked(df: pd.DataFrame, spec: Table, player: bool = False, limit: int | None = None) -> pd.DataFrame:
    d = df.copy()
    keys = [spec.sort]
    asc = [spec.ascending]
    second = next((c.key2 for c in spec.cols if c.key == spec.sort and c.kind == "pair"), None)
    if second:
        keys.append(second); asc.append(False)
    if player:
        d = d[d[spec.sort].fillna(0) > 0]
        keys.append("MoP"); asc.append(True)
    d = d.sort_values(keys, ascending=asc, na_position="last")
    if limit:
        d = d.head(limit)
    d["rank"] = np.where(d[spec.sort].notna(), np.arange(1, len(d) + 1), np.nan)
    return d


def league_average(df: pd.DataFrame, spec: Table) -> dict:
    out = {}
    for c in spec.cols:
        out[c.key] = df[c.key].mean(skipna=True) if c.key in df else np.nan
        if c.key2 and c.key2 in df:
            out[c.key2] = df[c.key2].mean(skipna=True)
    return out


def display_frame(df: pd.DataFrame, spec: Table, player: bool = False, limit=None) -> pd.DataFrame:
    """Plain-text version for st.dataframe / CSV."""
    r = ranked(df, spec, player, limit)
    rows = []
    if spec.avg and not player:
        avg = league_average(df, spec)
        rows.append({"#": "", "Team": "League average", **{col_header(c): fmt_value(avg, c) for c in spec.cols}})
    for _, row in r.iterrows():
        base = {"#": "" if pd.isna(row["rank"]) else int(row["rank"])}
        if player:
            base.update({"Player": row["short"], "Team": team_label(row["Team"], 24)})
        else:
            base["Team"] = row["Team"]
        rows.append({**base, **{col_header(c): fmt_value(row, c) for c in spec.cols}})
    return pd.DataFrame(rows)
