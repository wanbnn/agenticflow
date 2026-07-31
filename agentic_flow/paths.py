from __future__ import annotations

import os
import sys
from pathlib import Path


def default_data_dir() -> Path:
    configured = os.getenv("AGENTIC_FLOW_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "AgenticFlow"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AgenticFlow"
    base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "agenticflow"
