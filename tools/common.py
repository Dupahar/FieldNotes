"""Shared paths and helpers for the FieldNotes tools."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CALLS = DATA / "calls"
CRM_FILE = DATA / "crm.json"

# Colours used by every chart, so the rep, customer and team views read as one system.
REP_COLOR = "#2563EB"
CUSTOMER_COLOR = "#F97316"
OTHER_COLORS = ["#10B981", "#A855F7", "#64748B", "#EAB308"]


def call_dir(call_id: str) -> Path:
    path = CALLS / call_id
    if not path.is_dir():
        sys.exit(f"error: no call folder {path}. Run tools/transcribe.py first, or check `tools/calls.py list`.")
    return path


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    tmp.replace(path)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "call"


def fmt_ts(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def utf8_stdout() -> None:
    """Windows consoles default to cp1252; agents read our output, so force UTF-8."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
