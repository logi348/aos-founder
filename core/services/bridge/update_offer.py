"""Telegram "Apply update" button (hardened fork).

check-update (every 2 h, notify-only) sends one message per new fork version
with callback data ``aos_update:<hash>``. A press — which has already passed
the bridge's owner-only gate — applies the update by running
``check-update --apply``, but only if that exact version is still the one
pending in ~/.aos/data/update-state.json. A stale button (the fork moved on)
does nothing and says so. The update runs detached, because it restarts
services including this bridge; check-update reports the result on Telegram.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

PREFIX = "aos_update:"
LATER = "aos_update_later"


def _state_file() -> Path:
    return Path.home() / ".aos" / "data" / "update-state.json"


def pending_hash() -> str | None:
    try:
        s = json.loads(_state_file().read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return s.get("remote") if s.get("status") == "update_available" else None


def decide(callback_data: str) -> tuple[str, str | None]:
    """→ (reply text, hash to apply or None). Pure apart from reading state."""
    if callback_data == LATER:
        return ("OK — run `aos update` or tap Apply on the next notice when you're ready.", None)
    wanted = callback_data[len(PREFIX):]
    current = pending_hash()
    if not current:
        return ("Nothing to apply — already up to date.", None)
    if not wanted or not current.startswith(wanted):
        return ("That button is for an older version — a newer one is pending. "
                "Review it, then use the newest notice or `aos update`.", None)
    return (f"Applying update {current[:12]}… services will restart; I'll report when done.", current)


def start_apply() -> None:
    log = Path.home() / ".aos" / "logs" / "update-apply.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as f:
        subprocess.Popen(
            ["bash", str(Path.home() / "aos" / "core" / "bin" / "crons" / "check-update"), "--apply"],
            stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True,  # survives the bridge restart the update triggers
        )
