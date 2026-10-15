"""The Claude Code permission set AOS writes into ~/.claude/settings.json.

Hardened fork. One definition, applied by install.sh (`python3 -m` style CLI
below) and enforced by the `settings_config` reconcile check
(core/infra/reconcile/checks/hooks.py), so an install, a migration and a
reconcile pass all converge on the same rules instead of reconcile quietly
restoring blanket allows.

Design (see HARDENING.md):
  - Read/Edit are pre-approved only under the AOS directories and /tmp.
    Elsewhere an interactive session asks, the Telegram bridge forwards the
    request to the operator's phone, and headless dontAsk jobs are refused.
    (Claude Code consults Edit rules for Write/NotebookEdit too; there is no
    separate Write rule.)
  - Bash stays pre-approved: shell commands cannot be scoped to directories
    by permission rules. The deny list below plus the PreToolUse guard
    (core/hooks/guard_bash.py) are what bound it.
  - Deny rules win over every allow and apply in every mode, including
    bypassPermissions (`cld-unsafe`).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

AOS_DIRS = ["~/aos", "~/.aos", "~/vault", "~/project"]
# Where agents may edit without asking. ~/aos (the running framework: agent
# and skill instructions, hooks, this module, crons.yaml) is readable but
# never editable by agents — framework changes go ~/project/aos → the fork →
# operator merge → `aos update`.
EDIT_DIRS = ["~/.aos", "~/vault", "~/project"]
TEMP_DIRS = ["//tmp", "//private/tmp"]

ALLOW = (
    ["Bash", "Glob", "Grep", "WebSearch", "WebFetch", "Agent", "Task", "TodoWrite", "Skill"]
    + [f"Read({d}/**)" for d in AOS_DIRS + TEMP_DIRS]
    + [f"Edit({d}/**)" for d in EDIT_DIRS + TEMP_DIRS]
)

# Self-modification: what an agent could change to give itself more.
SELF_MOD_PATHS = [
    "~/aos/**", "~/aos-releases/**",
    "~/Library/LaunchAgents/**", "//Library/LaunchAgents/**", "//Library/LaunchDaemons/**",
    "~/.zshrc", "~/.zprofile", "~/.zshenv", "~/.zlogin", "~/.bashrc", "~/.bash_profile", "~/.profile",
]

# Needs the operator's OK each time (ask beats allow): comms allowlist,
# account trust, operator profile, converse defaults …
ASK = ["Edit(~/.aos/config/**)"]

_SECRET_DIRS = [
    "~/.ssh",
    "~/Library/Keychains",
    "~/Library/Cookies",
    "~/Library/Safari",
    "~/Library/Containers/com.apple.Safari",
    "~/Library/Application Support/Google/Chrome",
    "~/Library/Application Support/Chromium",
    "~/Library/Application Support/BraveSoftware",
    "~/Library/Application Support/Microsoft Edge",
    "~/Library/Application Support/Arc",
    "~/Library/Application Support/Firefox",
]

# Operator-only settings: raising trust or opting into always-on features
# is a human decision (core/infra/lib/human_gate.py). Agents may read these.
OPERATOR_ONLY_FILES = [
    "~/.aos/config/trust.yaml",
    "~/.aos/config/claude-features.json",
    "~/.aos/config/always-on",
    "~/.aos/config/bridge-permission-mode",
    "~/.aos/config/lan-allow",
]

DENY = (
    [f"Read({d}/**)" for d in _SECRET_DIRS]
    + [f"Edit({d}/**)" for d in _SECRET_DIRS]
    + [f"Edit({f})" for f in OPERATOR_ONLY_FILES]
    + [f"Edit({p})" for p in SELF_MOD_PATHS]
    + [
        # Command-text rules are a first layer only; guard_bash.py parses
        # the command properly (sudo via a path, bash -c, pipes, rm targets).
        "Bash(sudo)", "Bash(sudo *)",
        "Bash(security)", "Bash(security *)",
        "Bash(curl * | sh)", "Bash(curl * | bash)", "Bash(wget * | sh)", "Bash(wget * | bash)",
        "Bash(rm -rf /)", "Bash(rm -rf ~)", "Bash(rm -rf ~/)", "Bash(rm -rf $HOME)",
        "Bash(rm -fr /)", "Bash(rm -fr ~)", "Bash(rm -fr ~/)", "Bash(rm -fr $HOME)",
    ]
)

# Blanket allows written by upstream install.sh / reconcile. Removed so the
# scoped rules above are the ones that apply.
LEGACY_ALLOW = ["Bash(*)", "Read(*)", "Write(*)", "Edit(*)", "Glob(*)", "Grep(*)",
                "Read", "Write", "Edit", "Edit ~/.claude/**", "Write ~/.claude/**",
                "Edit(~/aos/**)"]  # pre-approved by this fork's first version

# Environment for every Claude Code session (settings.json "env").
#   DISABLE_AUTOUPDATER: Claude Code updates only when the operator runs them.
#   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: no usage telemetry, error
#     reporting, feedback or auto-update traffic — only the model requests
#     themselves go to Anthropic.
REQUIRED_ENV = {
    "DISABLE_AUTOUPDATER": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
}

GUARD_HOOK = {
    "event": "PreToolUse",
    "matcher": "Bash",
    "command": "python3 ~/aos/core/hooks/guard_bash.py",
}


def needs_update(settings: dict) -> bool:
    perms = settings.get("permissions") or {}
    allow, deny, ask = perms.get("allow") or [], perms.get("deny") or [], perms.get("ask") or []
    env = settings.get("env") or {}
    if any(env.get(k) != v for k, v in REQUIRED_ENV.items()):
        return True
    return (any(r not in allow for r in ALLOW)
            or any(r not in deny for r in DENY)
            or any(r not in ask for r in ASK)
            or any(r in allow for r in LEGACY_ALLOW))


def apply(settings: dict) -> list[str]:
    """Bring settings["permissions"] in line. Keeps any extra rules the
    operator added. Returns a list of human-readable changes."""
    changes: list[str] = []
    perms = settings.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])
    deny = perms.setdefault("deny", [])
    for r in LEGACY_ALLOW:
        while r in allow:
            allow.remove(r)
            changes.append(f"removed blanket allow {r}")
    for r in ALLOW:
        if r not in allow:
            allow.append(r)
            changes.append(f"allow {r}")
    for r in DENY:
        if r not in deny:
            deny.append(r)
            changes.append(f"deny {r}")
    ask = perms.setdefault("ask", [])
    for r in ASK:
        if r not in ask:
            ask.append(r)
            changes.append(f"ask {r}")
    env = settings.setdefault("env", {})
    for k, v in REQUIRED_ENV.items():
        if env.get(k) != v:
            env[k] = v
            changes.append(f"env {k}={v}")
    return changes


def main(argv: list[str]) -> int:
    """`claude_permissions.py apply [settings.json]` — used by install.sh."""
    if len(argv) < 2 or argv[1] != "apply":
        print("usage: claude_permissions.py apply [path/to/settings.json]", file=sys.stderr)
        return 2
    path = Path(argv[2]).expanduser() if len(argv) > 2 else Path.home() / ".claude" / "settings.json"
    settings = json.loads(path.read_text()) if path.exists() else {}
    changes = apply(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"{len(changes)} permission change(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
