#!/usr/bin/env python3
"""PreToolUse guard for the Bash tool (hardened fork).

Claude Code permission rules match command *text*, which is easy to sidestep
(`/usr/bin/sudo`, `bash -c '...'`, `curl … | sh` split at the pipe). This hook
parses the command properly and applies a few hard rules. Hooks run in every
permission mode, including bypassPermissions (`cld-unsafe`).

Decisions (printed as PreToolUse JSON on stdout, exit 0):
  deny — sudo/doas; the macOS `security` keychain CLI (use `agent-secret`);
         a download piped or substituted into a shell; recursive rm of a path
         outside the AOS directories; any reference to ~/.ssh, the login
         keychains or a browser profile/cookie store.
  ask  — recursive rm whose target can't be resolved (e.g. `rm -rf "$DIR"`).
         Interactive sessions prompt; the Telegram bridge forwards it to the
         operator's phone; headless dontAsk jobs are refused.
  (nothing) — everything else is left to the normal permission rules.

Stdlib only: it runs under whatever `python3` is on PATH. If it cannot parse
a command it stays silent rather than blocking (shlex failure on odd quoting);
the settings.json deny rules remain as a second layer.

Allowed rm roots: ~/aos, ~/.aos, ~/vault, ~/project, the temp dirs and
anything in AOS_GUARD_EXTRA_RM_ROOTS (colon-separated). The roots themselves
are protected; only paths strictly inside them may be removed recursively.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))

RM_ROOTS = [HOME / "aos", HOME / ".aos", HOME / "vault", HOME / "project",
            Path("/tmp"), Path("/private/tmp"), Path("/var/folders"),
            Path("/private/var/folders")]

SENSITIVE = [
    HOME / ".ssh",
    HOME / "Library" / "Keychains",
    HOME / "Library" / "Cookies",
    HOME / "Library" / "Safari",
    HOME / "Library" / "Application Support" / "Google" / "Chrome",
    HOME / "Library" / "Application Support" / "Chromium",
    HOME / "Library" / "Application Support" / "BraveSoftware",
    HOME / "Library" / "Application Support" / "Microsoft Edge",
    HOME / "Library" / "Application Support" / "Arc",
    HOME / "Library" / "Application Support" / "Firefox",
    HOME / "Library" / "Containers" / "com.apple.Safari",
]

SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
DOWNLOADERS = {"curl", "wget"}
WRAPPERS = {"nohup", "time", "command", "builtin", "exec", "nice", "caffeinate", "env", "xargs"}
OPERATORS = {";", "&&", "||", "|", "&", "|&", "(", ")", "\n"}


def _roots() -> list[Path]:
    extra = [Path(p).expanduser() for p in os.environ.get("AOS_GUARD_EXTRA_RM_ROOTS", "").split(":") if p]
    tmp = os.environ.get("TMPDIR")
    return RM_ROOTS + extra + ([Path(tmp)] if tmp else [])


def _expand(word: str) -> str | None:
    """Expand ~ and $HOME; None if any other variable or substitution remains."""
    w = word
    if w == "~" or w.startswith("~/"):
        w = str(HOME) + w[1:]
    w = w.replace("${HOME}", str(HOME)).replace("$HOME", str(HOME))
    if "$" in w or "`" in w:
        return None
    return w


def _segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    segs: list[list[str]] = [[]]
    for tok in lexer:
        if tok in OPERATORS or set(tok) <= set(";&|()"):
            segs.append([tok])  # keep the operator as a marker at segment start
            segs.append([])
        else:
            segs[-1].append(tok)
    return [s for s in segs if s]


def _strip(words: list[str]) -> list[str]:
    """Drop leading VAR=value assignments and harmless wrappers (timeout N, env …)."""
    i = 0
    while i < len(words):
        w = words[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
            i += 1
        elif os.path.basename(w) in WRAPPERS:
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 1
        elif os.path.basename(w) == "timeout":
            i += 1
            while i < len(words) and (words[i].startswith("-") or re.match(r"^\d", words[i])):
                i += 1
        else:
            break
    return words[i:]


def _resolve(word: str, cwd: Path) -> Path | None:
    exp = _expand(word)
    if exp is None:
        return None
    # A glob only widens what it names; judge it by the fixed prefix.
    m = re.search(r"[*?\[]", exp)
    if m:
        exp = exp[: m.start()] or "."
    p = Path(exp)
    if not p.is_absolute():
        p = cwd / p
    return Path(os.path.normpath(str(p)))


def _inside(p: Path, root: Path) -> bool:
    try:
        rel = p.relative_to(Path(os.path.normpath(str(root))))
    except ValueError:
        return False
    return str(rel) not in ("", ".")


def _check_rm(args: list[str], cwd: Path) -> tuple[str, str] | None:
    recursive = False
    targets: list[str] = []
    end_of_opts = False
    for a in args:
        if not end_of_opts and a == "--":
            end_of_opts = True
        elif not end_of_opts and a.startswith("--"):
            recursive |= a in ("--recursive",)
        elif not end_of_opts and a.startswith("-") and len(a) > 1:
            recursive |= "r" in a or "R" in a
        else:
            targets.append(a)
    if not recursive:
        return None
    roots = _roots()
    for t in targets:
        p = _resolve(t, cwd)
        if p is None:
            return ("ask", f"Recursive rm of an unresolved path ({t!r}); confirm it is inside the AOS directories.")
        if not any(_inside(p, r) for r in roots):
            return ("deny", f"Recursive rm outside the AOS directories is blocked: {p}")
    return None


def _check_words(words: list[str], cwd: Path, depth: int) -> tuple[str, str] | None:
    words = _strip(words)
    if not words:
        return None
    name = os.path.basename(words[0])
    if name in ("sudo", "doas", "su"):
        return ("deny", "sudo is blocked for agents; run it yourself if it is really needed.")
    if name == "security":
        return ("deny", "The `security` keychain CLI is blocked; use `agent-secret get NAME`.")
    if name == "rm":
        return _check_rm(words[1:], cwd)
    if name in SHELLS or name == "eval":
        args = words[1:]
        joined = " ".join(args)
        if re.search(r"\b(curl|wget)\b", joined):
            return ("deny", "Running downloaded code in a shell is blocked (curl/wget into sh/bash/eval).")
        if name in SHELLS and "-c" in args and depth < 3:
            idx = args.index("-c")
            if idx + 1 < len(args):
                return check_command(args[idx + 1], cwd, depth + 1)
    if name == "source" or name == ".":
        if any(re.search(r"<\(|\b(curl|wget)\b", a) for a in words[1:]):
            return ("deny", "Sourcing downloaded code is blocked.")
    return None


def check_command(command: str, cwd: Path | None = None, depth: int = 0) -> tuple[str, str] | None:
    cwd = cwd or Path.cwd()
    expanded = command.replace("${HOME}", str(HOME)).replace("$HOME", str(HOME))
    expanded = re.sub(r"(?<![\w/])~(?=/)", str(HOME), expanded)
    for s in SENSITIVE:
        if str(s) in expanded:
            return ("deny", f"Access to {s} is blocked for agents.")
    # Download piped straight into a shell, process substitution or $( ).
    if re.search(r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(\S*/)?(sh|bash|zsh|dash|ksh|python3?|perl|ruby|osascript)\b", command):
        return ("deny", "Piping a download into an interpreter is blocked.")
    if re.search(r"(?:\$\(|<\(|`)\s*(curl|wget)\b", command) and re.search(r"\b(sh|bash|zsh|eval|source)\b", command):
        return ("deny", "Running downloaded code in a shell is blocked.")
    try:
        segs = _segments(command)
    except ValueError:
        return None
    result = None
    for seg in segs:
        if seg and (seg[0] in OPERATORS or set(seg[0]) <= set(";&|()")):
            continue
        r = _check_words(seg, cwd, depth)
        if r and r[0] == "deny":
            return r
        result = result or r
    return result


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    cwd = Path(payload.get("cwd") or os.getcwd())
    verdict = check_command(command, cwd)
    if verdict:
        decision, reason = verdict
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": f"[aos guard] {reason}",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
