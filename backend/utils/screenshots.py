"""
Saves a tool's screenshot artifact to disk.

`inspect_website` returns its screenshot as a ToolMessage `artifact`
(see tools/inspect_website.py) precisely so the raw bytes never have to
flow back through the LLM's context — this is the one place that
actually writes them to a file instead of letting them vanish when the
process exits. Shared by cli.py (live printing) and report.py (the
per-case report) so a screenshot is only ever saved once.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import get_settings


def sanitize_for_filename(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", text)[:60]


def save_screenshot(artifact: Optional[dict]) -> Optional[str]:
    """Given a tool's artifact dict, save its screenshot (if present) and return the file path, else None."""
    if not isinstance(artifact, dict):
        return None
    screenshot_b64 = artifact.get("screenshot_base64")
    if not screenshot_b64:
        return None

    settings = get_settings()
    screenshot_dir = Path(settings.SCREENSHOT_DIR)
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    label = sanitize_for_filename(artifact.get("final_url", "screenshot"))
    filename = f"{datetime.now():%Y%m%d_%H%M%S}_{label}.png"
    path = screenshot_dir / filename
    path.write_bytes(base64.b64decode(screenshot_b64))
    return str(path)
