"""Overnight "advance" report → morning briefing lines (hardened fork).

core/bin/crons/advance writes ~/.aos/work/advance/latest.json each night.
The briefing shows it only if it is from today or last night (≤ 20 h old),
so a skipped night never re-shows a stale report.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timedelta
from pathlib import Path

MAX_EACH = 4


def _state_file() -> Path:
    return Path.home() / ".aos" / "work" / "advance" / "latest.json"


def load(now: datetime | None = None) -> dict | None:
    try:
        data = json.loads(_state_file().read_text())
    except (OSError, json.JSONDecodeError):
        return None
    try:
        generated = datetime.fromisoformat(data.get("generated", ""))
    except ValueError:
        return None
    now = now or datetime.now()
    if generated.tzinfo is not None:
        generated = generated.replace(tzinfo=None)
    if now.replace(tzinfo=None) - generated > timedelta(hours=20):
        return None
    return data


def briefing_lines(now: datetime | None = None) -> list[str]:
    """HTML lines for Telegram (parse_mode=HTML); [] when there's nothing to show."""
    data = load(now)
    if not data:
        return []
    esc = html.escape
    moved, needs, parked = (data.get(k) or [] for k in ("moved", "needs_you", "parked"))
    if not (moved or needs or parked or data.get("error")):
        return []
    lines = ["\U0001f319 <b>WHILE YOU SLEPT</b>"]
    for i in moved[:MAX_EACH]:
        lines.append(f"  ✅ <b>{esc(i['item'])}</b> — {esc(i.get('did', ''))}")
    if needs:
        lines.append("  <i>Needs you:</i>")
        for i in needs[:MAX_EACH]:
            lines.append(f"  ❓ <b>{esc(i['item'])}</b> — {esc(i.get('ask', ''))}")
    if parked:
        lines.append("  <i>Parked (reply to revive or drop):</i>")
        for i in parked[:MAX_EACH]:
            lines.append(f"  \U0001f4a4 {esc(i['item'])} — {esc(i.get('why', ''))}")
    if data.get("error"):
        lines.append(f"  ⚠️ The overnight run had a problem: {esc(str(data['error'])[:160])}")
    outputs = data.get("outputs")
    if outputs and moved:
        lines.append(f"  <i>Details: {esc(outputs)}/report.md</i>")
    lines.append("")
    return lines
