"""Where the data comes from: a Google Drive folder (or a local folder for testing).

The folder can be organised any way you like – one sub-folder per competition,
one file per gameweek, or big combined exports. Every .xlsx / Google Sheet in
the folder (and its sub-folders) is read and classified by its columns:

* timeline files  – have "Act Name" and "X1" columns (and a "Competition" column)
* report files    – have "Player Match ID" and "Gameweek" but no "Act Name"

The competition of each report row is found through its Player Match ID, which
also appears in the timeline. Rows that cannot be matched that way fall back to
(1) the competition most of the rest of the same file belongs to, then (2) the
name of the sub-folder the file sits in.
"""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field

import pandas as pd

from .io import read_report, read_timeline

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
FOLDER_MIME = "application/vnd.google-apps.folder"


@dataclass
class SourceFile:
    file_id: str
    name: str
    folder: str          # sub-folder path ("" for the root)
    modified: str        # used as a cache key
    mime: str


# --------------------------------------------------------------------------- #
# Google Drive
# --------------------------------------------------------------------------- #
class DriveSource:
    """Reads a shared Drive folder with a service account (read-only scope)."""

    def __init__(self, service_account_info: dict, folder_id: str):
        from google.oauth2 import service_account          # lazy: only needed for Drive
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_info(
            dict(service_account_info), scopes=["https://www.googleapis.com/auth/drive.readonly"])
        self.svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.folder_id = folder_id

    def list_files(self) -> list[SourceFile]:
        out, stack = [], [(self.folder_id, "")]
        while stack:
            fid, path = stack.pop()
            token = None
            while True:
                resp = self.svc.files().list(
                    q=f"'{fid}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                    pageSize=1000, pageToken=token,
                    supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
                for f in resp.get("files", []):
                    if f["mimeType"] == FOLDER_MIME:
                        stack.append((f["id"], f"{path}/{f['name']}".strip("/")))
                    elif f["mimeType"] in (XLSX_MIME, SHEET_MIME) or f["name"].lower().endswith(".xlsx"):
                        out.append(SourceFile(f["id"], f["name"], path, f["modifiedTime"], f["mimeType"]))
                token = resp.get("nextPageToken")
                if not token:
                    break
        return out

    def download(self, f: SourceFile) -> bytes:
        from googleapiclient.http import MediaIoBaseDownload

        if f.mime == SHEET_MIME:   # native Google Sheet -> export as xlsx
            req = self.svc.files().export_media(fileId=f.file_id, mimeType=XLSX_MIME)
        else:
            req = self.svc.files().get_media(fileId=f.file_id, supportsAllDrives=True)
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, req, chunksize=20 * 1024 * 1024)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue()


class LocalSource:
    """Same interface over a local folder – handy for testing and offline use."""

    def __init__(self, root: str):
        self.root = root

    def list_files(self) -> list[SourceFile]:
        out = []
        for dirpath, _, files in os.walk(self.root):
            for n in files:
                if n.lower().endswith(".xlsx") and not n.startswith("~$"):
                    p = os.path.join(dirpath, n)
                    rel = os.path.relpath(dirpath, self.root)
                    out.append(SourceFile(p, n, "" if rel == "." else rel,
                                          str(os.path.getmtime(p)), XLSX_MIME))
        return out

    def download(self, f: SourceFile) -> bytes:
        with open(f.file_id, "rb") as fh:
            return fh.read()


# --------------------------------------------------------------------------- #
# Turning files into competitions
# --------------------------------------------------------------------------- #
@dataclass
class Competition:
    name: str
    report: pd.DataFrame
    timeline: pd.DataFrame | None
    notes: list[str] = field(default_factory=list)

    @property
    def gameweeks(self) -> list[int]:
        return sorted(int(g) for g in self.report["Gameweek"].dropna().unique())

    @property
    def league_and_season(self) -> tuple[str, str]:
        """'Super League 2026-27' -> ('Super League', '2026/27')."""
        m = re.match(r"^(.*?)[\s\-–]*((?:19|20)\d{2})\s*[-/–]\s*(\d{2,4})\s*$", self.name)
        if m:
            return m.group(1).strip(), f"{m.group(2)}/{m.group(3)}"
        return self.name, ""


def classify(raw: bytes) -> str:
    head = pd.read_excel(io.BytesIO(raw), nrows=0) if raw[:2] == b"PK" else None
    cols = set(map(str, head.columns)) if head is not None else set()
    if {"Act Name", "X1"} <= cols:
        return "timeline"
    if {"Player Match ID", "Gameweek", "Team"} <= cols:
        return "report"
    return "unknown"


def build_competitions(files: list[tuple[SourceFile, bytes]]) -> tuple[dict[str, Competition], list[str]]:
    """files: (meta, raw bytes). Returns {competition name: Competition}, global notes."""
    notes: list[str] = []
    file_notes: dict[str, list[str]] = {}
    timelines, reports = [], []
    for meta, raw in files:
        try:
            kind = classify(raw)
        except Exception:
            kind = "timeline_damaged"      # pandas could not open it: try the tolerant reader
        if kind in ("timeline", "timeline_damaged"):
            try:
                tl, info = read_timeline(raw)
            except Exception as e:  # noqa: BLE001
                notes.append(f"Skipped {meta.name}: {e}")
                continue
            if "Act Name" not in tl.columns:
                if {"Player Match ID", "Gameweek"} <= set(tl.columns):
                    kind = "report"
                else:
                    notes.append(f"Skipped {meta.name}: not a report or timeline file.")
                    continue
            else:
                file_notes[meta.name] = [f"{meta.name}: {n}" for n in info.notes]
                tl["_file"] = meta.name
                timelines.append(tl)
                continue
        if kind == "report":
            rep = read_report(raw).assign(_file=meta.name, _folder=meta.folder)
            reports.append(rep)
        elif kind == "unknown":
            notes.append(f"Skipped {meta.name}: columns not recognised.")

    if not reports:
        return {}, notes + ["No report (player match stats) files found."]

    TL = pd.concat(timelines, ignore_index=True) if timelines else pd.DataFrame()
    if not TL.empty:
        TL = TL.drop_duplicates("ID") if "ID" in TL else TL
        if "Competition" not in TL:
            TL["Competition"] = "Competition"
        TL["Competition"] = TL["Competition"].fillna("Competition").astype(str).str.strip()
    R = pd.concat(reports, ignore_index=True).drop_duplicates("Player Match ID").copy()

    # 1) through Player Match ID
    comp = pd.Series(pd.NA, index=R.index, dtype="object")
    if not TL.empty and "Player Match ID" in TL:
        pm = TL.dropna(subset=["Player Match ID"]).drop_duplicates("Player Match ID") \
               .set_index("Player Match ID")["Competition"]
        comp = R["Player Match ID"].map(pm)
        # spread to every row of the same match (bench players have no events)
        by_match = comp.groupby([R["_file"], R["Match"]]).transform(
            lambda s: s.dropna().mode().iat[0] if s.notna().any() else pd.NA)
        comp = comp.fillna(by_match)
    # 2) majority of the same file
    file_major = comp.groupby(R["_file"]).transform(
        lambda s: s.dropna().mode().iat[0] if s.notna().any() else pd.NA)
    comp = comp.fillna(file_major)
    # 3) sub-folder name, then a generic label
    comp = comp.fillna(R["_folder"].replace("", pd.NA)).fillna("Competition")
    R["Competition"] = comp.astype(str)

    out = {}
    for name, rg in R.groupby("Competition"):
        tg = TL[TL["Competition"] == name].copy() if not TL.empty else None
        c = Competition(name, rg.drop(columns=["_file", "_folder"]).reset_index(drop=True),
                        tg.reset_index(drop=True) if tg is not None and len(tg) else None)
        if tg is not None:
            for fn in tg["_file"].unique():
                c.notes += file_notes.get(fn, [])
        out[name] = c
    return out, notes
