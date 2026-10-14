"""Opt-in Claude Code features: Remote Control and Claude in Chrome.

Hardened fork. Upstream forced both on for every session (install.sh and the
`claude_defaults` reconcile check). Here both default to OFF and follow the
operator's choice in ~/.aos/config/claude-features.json, which is changed
only by `aos claude-features enable|disable <feature>` (core/bin/cli/claude-features).
The reconcile check enforces whatever that file says, so an opt-in sticks and
an opt-out sticks.

Where the flags live (Claude Code docs, checked 2026-10):
  - remoteControlAtStartup: documented in ~/.claude/settings.json. Upstream
    wrote it to ~/.claude.json; we set both so neither location turns it on.
  - claudeInChromeDefaultEnabled: ~/.claude.json (global config).
  - The undocumented `"chrome": true` key upstream put in settings.json is
    removed when Chrome is off and not re-added.
Per-session alternatives that need no opt-in: `claude --remote-control`
(or `/remote-control` inside a session) and `claude --chrome` / `/chrome`.

Stdlib only.
"""
from __future__ import annotations

import json
from pathlib import Path

FEATURES = {
    "remote-control": "Remote Control for every session (control this Mac's Claude from claude.ai / the app)",
    "chrome": "Claude in Chrome enabled by default in every session",
}
DEFAULTS = {"remote-control": False, "chrome": False}


def config_path() -> Path:
    return Path.home() / ".aos" / "config" / "claude-features.json"


def claude_json() -> Path:
    return Path.home() / ".claude.json"


def settings_json() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _read(p: Path) -> dict:
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load() -> dict:
    data = _read(config_path())
    return {k: bool(data.get(k, v)) for k, v in DEFAULTS.items()}


def save(choices: dict) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({k: bool(choices[k]) for k in DEFAULTS}, indent=2) + "\n")


def desired() -> dict:
    """{path: {key: value-or-None}} — None means 'remove the key'."""
    c = load()
    return {
        claude_json(): {
            "remoteControlAtStartup": c["remote-control"],
            "claudeInChromeDefaultEnabled": c["chrome"],
        },
        settings_json(): {
            "remoteControlAtStartup": c["remote-control"],
            "chrome": True if c["chrome"] else None,
        },
    }


def drift() -> list[str]:
    out = []
    for path, keys in desired().items():
        if path == settings_json() and not path.exists():
            continue
        data = _read(path)
        for k, v in keys.items():
            if v is None and k in data:
                out.append(f"{path.name}:{k} present")
            elif v is not None and data.get(k) is not v:
                out.append(f"{path.name}:{k}={data.get(k)!r}, want {v}")
    return out


def apply() -> list[str]:
    changed = []
    for path, keys in desired().items():
        if path == settings_json() and not path.exists():
            continue  # install/migrations create it; don't conjure one here
        data = _read(path)
        before = dict(data)
        for k, v in keys.items():
            if v is None:
                data.pop(k, None)
            else:
                data[k] = v
        if data != before:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2) + "\n")
            changed.append(path.name)
    return changed
