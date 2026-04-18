"""History storage: write hourly JSON snapshots under history/YYYY/MM/DD/HH.json."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

HISTORY_ROOT = Path(__file__).resolve().parent.parent / "history"


def save_to_history(payload: dict, now: datetime) -> Path:
    """Write payload to history/YYYY/MM/DD/HH.json (UTC). Returns the path."""
    path = (
        HISTORY_ROOT
        / f"{now.year:04d}"
        / f"{now.month:02d}"
        / f"{now.day:02d}"
        / f"{now.hour:02d}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path
