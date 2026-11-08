"""
Invariant: ~/aos/ (runtime copy) is clean and protected from local commits.

Three protections:
1. A pre-commit hook that blocks ALL commits to ~/aos/
2. A .no-auto-commit marker file
3. If the repo is dirty or has local commits ahead of origin, auto-clean

Why: Services or sessions sometimes write files into ~/aos/ by accident.
If those files get committed, `git pull --ff-only` fails and the machine
can't update. This has happened with .inflight.json, .jsonl transcripts,
and execution logs.

See GitHub issue #9.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from base import CheckResult, ReconcileCheck, Status

RUNTIME_DIR = Path.home() / "aos"

PRE_COMMIT_HOOK = """\
#!/bin/bash
# Installed by AOS reconcile — do not remove
# ~/aos/ is a read-only runtime copy. All commits go to ~/project/aos/
echo "ERROR: ~/aos/ is read-only runtime — edits here are wiped every 30 minutes." >&2
echo "Make the change in the workshop (~/project/aos/, the workshop skill), push it," >&2
echo "then install it with 'aos update'." >&2
exit 1
"""

MAX_LISTED = 20


def _hook_current(text: str) -> bool:
    """Installed hook blocks commits and points at the workshop."""
    return "read-only runtime" in text and "workshop" in text


def _porcelain_paths(porcelain: str) -> list[str]:
    """File names from `git status --porcelain` output (renames → new name)."""
    paths = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip().strip('"'))
    return paths


def _name_list(paths: list[str]) -> str:
    shown = ", ".join(paths[:MAX_LISTED])
    extra = len(paths) - MAX_LISTED
    return shown + (f" (+{extra} more)" if extra > 0 else "")


class RuntimeProtectionCheck(ReconcileCheck):
    name = "runtime_protection"
    # Hardened fork: repair on the 30-minute periodic run too, not only on
    # deploy, so tampering (an agent loosening its own permissions, flags or
    # code) is undone within half an hour.
    periodic_fix = True
    description = "~/aos/ is clean and protected from accidental commits"

    hooks_dir = RUNTIME_DIR / ".git" / "hooks"
    hook_path = RUNTIME_DIR / ".git" / "hooks" / "pre-commit"
    marker_path = RUNTIME_DIR / ".no-auto-commit"

    def check(self) -> bool:
        if not RUNTIME_DIR.is_dir():
            return True  # No runtime dir, nothing to protect
        if not (RUNTIME_DIR / ".git").is_dir():
            return True  # Not a git repo

        # Check 1: pre-commit hook exists and blocks commits
        if not self.hook_path.exists():
            return False
        if not _hook_current(self.hook_path.read_text()):
            return False

        # Check 2: .no-auto-commit marker exists
        if not self.marker_path.exists():
            return False

        # Check 3: repo is clean (no uncommitted changes)
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=RUNTIME_DIR, capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            return False

        # Check 4: no local commits ahead of origin/main
        result = subprocess.run(
            ["git", "rev-list", "--count", "origin/main..HEAD"],
            cwd=RUNTIME_DIR, capture_output=True, text=True, timeout=10
        )
        try:
            ahead = int(result.stdout.strip())
            if ahead > 0:
                return False
        except (ValueError, AttributeError):
            pass  # Can't determine — skip this check

        return True

    def fix(self) -> CheckResult:
        if not RUNTIME_DIR.is_dir() or not (RUNTIME_DIR / ".git").is_dir():
            return CheckResult(self.name, Status.SKIP, "~/aos/ not a git repo")

        fixed = []

        # Fix 1: Install pre-commit hook
        if not self.hook_path.exists() or not _hook_current(self.hook_path.read_text()):
            self.hooks_dir.mkdir(parents=True, exist_ok=True)
            self.hook_path.write_text(PRE_COMMIT_HOOK)
            self.hook_path.chmod(0o755)
            fixed.append("pre-commit hook")

        # Fix 2: Create .no-auto-commit marker
        if not self.marker_path.exists():
            self.marker_path.touch()
            fixed.append(".no-auto-commit marker")

        # Fix 3: Clean dirty working tree
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=RUNTIME_DIR, capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            # Name what gets discarded so a wipe is never silent.
            discarded = _porcelain_paths(result.stdout)
            # Reset tracked files, clean untracked (but not ignored)
            subprocess.run(
                ["git", "checkout", "--", "."],
                cwd=RUNTIME_DIR, capture_output=True, timeout=10
            )
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=RUNTIME_DIR, capture_output=True, timeout=10
            )
            fixed.append(
                f"discarded uncommitted changes to {_name_list(discarded)} "
                "(make lasting changes in ~/project/aos via the workshop)"
            )

        # Fix 4: Reset local commits ahead of origin
        result = subprocess.run(
            ["git", "rev-list", "--count", "origin/main..HEAD"],
            cwd=RUNTIME_DIR, capture_output=True, text=True, timeout=10
        )
        try:
            ahead = int(result.stdout.strip())
            if ahead > 0:
                names = subprocess.run(
                    ["git", "diff", "--name-only", "origin/main", "HEAD"],
                    cwd=RUNTIME_DIR, capture_output=True, text=True, timeout=10
                ).stdout.split()
                subprocess.run(
                    ["git", "reset", "--hard", "origin/main"],
                    cwd=RUNTIME_DIR, capture_output=True, timeout=10
                )
                fixed.append(
                    f"reset {ahead} local commits to origin/main"
                    + (f" (files: {_name_list(names)})" if names else "")
                )
        except (ValueError, AttributeError):
            pass

        if fixed:
            return CheckResult(
                self.name, Status.FIXED,
                f"Runtime protection: {', '.join(fixed)}"
            )
        return CheckResult(self.name, Status.OK, "ok")
