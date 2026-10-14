"""Permission flags for the Claude processes the Telegram bridge starts
(hardened fork). Upstream passed `--permission-mode bypassPermissions`.

Mode comes from ~/.aos/config/bridge-permission-mode (operator-only: agents
can't write it — settings.json deny rule + Bash guard):

  approve  (default) settings.json rules apply; anything not pre-approved is
           sent to the operator's phone for Allow/Deny (approvals.py).
  dontAsk  settings.json rules apply; anything not pre-approved is refused.
  bypass   upstream behaviour, no checks except deny rules and the Bash
           guard. Only for when the approval flow misbehaves.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MODE_FILE = Path.home() / ".aos" / "config" / "bridge-permission-mode"
APPROVAL_TOOL = "mcp__aos_approval__approve"


def mode() -> str:
    try:
        m = MODE_FILE.read_text().strip().split()[0]
    except (OSError, IndexError):
        return "approve"
    return m if m in ("approve", "dontAsk", "bypass") else "approve"


def args(current_mode: str | None = None) -> list[str]:
    m = current_mode or mode()
    if m == "bypass":
        return ["--permission-mode", "bypassPermissions"]
    if m == "dontAsk":
        return ["--permission-mode", "dontAsk"]
    cfg = {"mcpServers": {"aos_approval": {
        "command": sys.executable,
        "args": [str(Path(__file__).resolve().with_name("approval_mcp.py"))],
    }}}
    return ["--permission-mode", "default",
            "--mcp-config", json.dumps(cfg),
            "--permission-prompt-tool", APPROVAL_TOOL]


PROMPT_NOTE = (
    "Some actions need the operator's approval: they get an Allow/Deny prompt "
    "on their phone. If a tool call is denied, say briefly what you were trying "
    "to do and carry on with what you can do."
)


def working_dir() -> str:
    """Default cwd for bridge sessions: ~/aos, not the home directory —
    reads inside the working directory are allowed without asking."""
    p = Path.home() / "aos"
    return str(p if p.is_dir() else Path.home())
