"""
Invariant: Remote Control and Claude in Chrome match the operator's choice.

Hardened fork. Upstream forced remoteControlAtStartup and
claudeInChromeDefaultEnabled to true in ~/.claude.json on every reconcile
pass. Both are now opt-in: the source of truth is
~/.aos/config/claude-features.json (absent → both off), changed only via
`aos claude-features enable|disable <remote-control|chrome>`. This check
enforces that file in ~/.claude.json and ~/.claude/settings.json, so an
upstream merge or a stray edit can't silently turn them back on.

Logic lives in core/infra/lib/claude_features.py (shared with the CLI).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from base import CheckResult, ReconcileCheck, Status

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from lib import claude_features


class ClaudeDefaultsCheck(ReconcileCheck):
    name = "claude_defaults"
    # Hardened fork: repair on the 30-minute periodic run too, not only on
    # deploy, so tampering (an agent loosening its own permissions, flags or
    # code) is undone within half an hour.
    periodic_fix = True
    description = "Remote Control / Chrome match ~/.aos/config/claude-features.json (default off)"

    def check(self) -> bool:
        return not claude_features.drift()

    def fix(self) -> CheckResult:
        changed = claude_features.apply()
        if changed:
            state = claude_features.load()
            summary = ", ".join(f"{k}={'on' if v else 'off'}" for k, v in state.items())
            return CheckResult(self.name, Status.FIXED, f"Applied {summary} to {', '.join(changed)}")
        return CheckResult(self.name, Status.OK, "ok")
