"""
Invariant: settings.json has correct hooks, paths, and permissions.

Checks:
1. Hook commands reference valid ~/aos/ paths (not stale prefixes)
2. Required hooks are registered
3. Permissions match the hardened set in core/infra/lib/claude_permissions.py
   (scoped Read/Edit allows, deny rules for secrets/sudo/keychain/curl|sh),
   and upstream's blanket Bash(*)/Read/Edit/Write allows are removed.

Hardened fork: this check used to re-add blanket "Read"/"Edit"/"Write"
allows on every pass, which silently undid any narrowing. It now enforces the
shared permission set instead. (Claude Code's protection of ~/.claude is not
lifted by any allow rule in current versions, so nothing relied on the
blanket allows for that.)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from base import CheckResult, ReconcileCheck, Status

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from lib import claude_permissions


class HooksPathCheck(ReconcileCheck):
    name = "settings_config"
    # Hardened fork: repair on the 30-minute periodic run too, not only on
    # deploy, so tampering (an agent loosening its own permissions, flags or
    # code) is undone within half an hour.
    periodic_fix = True
    description = "settings.json hooks, paths, and permissions are correct"

    SETTINGS = Path.home() / ".claude" / "settings.json"

    # Old path prefixes that should be replaced
    STALE_PATTERNS = {
        "~/aosv2/": "~/aos/",
        "~/.aos-v2/": "~/aos/",
        "~/agent/": "~/aos/",
        "$HOME/aosv2/": "$HOME/aos/",
    }

    # Required hooks — if missing, add them
    REQUIRED_HOOKS = {
        "SessionStart": {
            "command": "python3 ~/aos/core/engine/work/inject_context.py",
            "statusMessage": "Loading work context...",
        },
        "SessionEnd": {
            "command": "python3 ~/aos/core/engine/work/session_close.py",
            "async": True,
        },
        # aos#236.4: automatic trust-log entries for catalog dispatch —
        # chief.md's "log every catalog dispatch" mandate had no enforcement
        # (5 rows ever written). matcher scopes this to the Agent tool only,
        # so every other PostToolUse consumer is unaffected.
        "PostToolUse": {
            "command": "python3 ~/aos/core/hooks/trust_log_dispatch.py",
            "matcher": "Agent",
            "async": True,
        },
        # Hardened fork: parses every Bash command before it runs (sudo,
        # security, curl|sh, rm -rf outside AOS dirs, secret paths).
        claude_permissions.GUARD_HOOK["event"]: {
            "command": claude_permissions.GUARD_HOOK["command"],
            "matcher": claude_permissions.GUARD_HOOK["matcher"],
        },
    }


    def check(self) -> bool:
        if not self.SETTINGS.exists():
            return False

        text = self.SETTINGS.read_text()

        # Check for stale paths
        if any(pat in text for pat in self.STALE_PATTERNS):
            return False

        try:
            settings = json.loads(text)
        except json.JSONDecodeError:
            return False

        # Check required hooks exist
        hooks = settings.get("hooks", {})
        for event, spec in self.REQUIRED_HOOKS.items():
            if not self._hook_exists(hooks, event, spec["command"]):
                return False

        # Permissions must match the hardened set
        if claude_permissions.needs_update(settings):
            return False

        return True

    def fix(self) -> CheckResult:
        if not self.SETTINGS.exists():
            return CheckResult(
                self.name, Status.SKIP,
                "settings.json does not exist — will be created by install"
            )

        actions = []
        text = self.SETTINGS.read_text()

        # Fix stale paths
        for old, new in self.STALE_PATTERNS.items():
            if old in text:
                text = text.replace(old, new)
                actions.append(f"replaced {old} → {new}")

        try:
            settings = json.loads(text)
        except json.JSONDecodeError:
            return CheckResult(
                self.name, Status.NOTIFY,
                "settings.json is malformed JSON — cannot safely repair",
                notify=True,
            )

        # Add missing required hooks
        hooks = settings.setdefault("hooks", {})
        for event, spec in self.REQUIRED_HOOKS.items():
            if not self._hook_exists(hooks, event, spec["command"]):
                if event not in hooks:
                    hooks[event] = []

                entry = {"type": "command", "command": spec["command"]}
                if spec.get("statusMessage"):
                    entry["statusMessage"] = spec["statusMessage"]
                if spec.get("async"):
                    entry["async"] = True

                block = {"hooks": [entry]}
                if spec.get("matcher"):
                    # Tool-scoped hook (e.g. PostToolUse) — matcher lives on
                    # the outer block, alongside "hooks", not on the entry.
                    block["matcher"] = spec["matcher"]

                hooks[event].append(block)
                actions.append(f"added {event} hook")

        settings["hooks"] = hooks

        # Hardened permission set (scoped allows, deny rules, no blanket allows)
        perm_changes = claude_permissions.apply(settings)
        if perm_changes:
            actions.append(f"permissions: {len(perm_changes)} change(s)")
        self.SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")

        if actions:
            return CheckResult(
                self.name, Status.FIXED,
                f"Fixed settings: {'; '.join(actions)}"
            )
        return CheckResult(self.name, Status.OK, "ok")

    def _hook_exists(self, hooks: dict, event: str, command: str) -> bool:
        """Check if a hook command is registered under an event."""
        event_hooks = hooks.get(event, [])
        if not isinstance(event_hooks, list):
            return False
        for h in event_hooks:
            if isinstance(h, dict):
                if h.get("command") == command:
                    return True
                # Nested: {"hooks": [{"command": "..."}]}
                for inner in h.get("hooks", []):
                    if isinstance(inner, dict) and inner.get("command") == command:
                        return True
        return False
