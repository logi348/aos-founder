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

Self-modification: writes of any kind into ~/aos, ~/.claude, ~/.claude.json,
LaunchAgents/Daemons or shell startup files are denied, as are crontab edits and
loading new launchd jobs; writes into ~/.aos/config are "ask". Running code
from ~/aos is of course fine.

Allowed rm roots: ~/.aos, ~/vault, ~/project, the temp dirs and
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

RM_ROOTS = [HOME / ".aos", HOME / "vault", HOME / "project",
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

# Operator-only config: agents may read these, never write them (raising
# trust / enabling always-on features is a human decision).
OPERATOR_ONLY = [
    HOME / ".aos" / "config" / "trust.yaml",
    HOME / ".aos" / "config" / "claude-features.json",
    HOME / ".aos" / "config" / "always-on",
    HOME / ".aos" / "config" / "bridge-permission-mode",
]
READ_ONLY_CMDS = {"cat", "head", "tail", "less", "more", "grep", "rg", "wc", "ls", "stat",
                  "file", "diff", "jq", "bat", "test", "["}

# Self-modification guard: agents run code from these places but must never
# write to them — that would let them rewrite their own instructions, this
# guard, the permission set, the scheduler's job list or what starts at login.
WRITE_PROTECTED = [
    HOME / "aos",                 # the running framework (agents, skills, crons.yaml, hooks)
    HOME / "aos-releases",        # release installs (~/aos is a symlink into here)
    HOME / ".claude",             # settings.json, agents/skills/rules links, hooks
    HOME / ".claude.json",
    HOME / "Library" / "LaunchAgents",
    Path("/Library/LaunchAgents"),
    Path("/Library/LaunchDaemons"),
    HOME / ".zshrc", HOME / ".zprofile", HOME / ".zshenv", HOME / ".zlogin",
    HOME / ".bashrc", HOME / ".bash_profile", HOME / ".profile",
]
WRITE_PROTECTED_EXCEPT = [HOME / ".claude" / "projects"]   # Claude Code's own session memory
# Writes here need the operator's OK ("ask"): comms allowlist, accounts,
# operator profile, converse defaults ...
WRITE_ASK = [HOME / ".aos" / "config"]

WRITE_ALL_ARGS = {"tee", "touch", "mkdir", "rmdir", "rm", "unlink", "truncate", "chflags", "xattr", "shred"}
WRITE_SKIP_FIRST = {"chmod", "chown", "chgrp"}            # first arg is the mode/owner
WRITE_LAST_ARG = {"cp", "mv", "install", "rsync", "ditto", "ln", "scp"}
IN_PLACE = {"sed", "gsed", "perl", "ruby"}
INLINE_CODE = {"python", "python3", "node", "perl", "ruby", "osascript", "php"}
GIT_WRITE = {"commit", "checkout", "reset", "apply", "am", "merge", "pull", "rebase", "stash",
             "clean", "restore", "switch", "cherry-pick", "revert", "rm", "mv", "add", "init",
             "clone", "fetch", "submodule", "worktree", "update-index", "config"}

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


def _is_op(tok: str) -> bool:
    """A shell operator token. An empty argument (`''`) is NOT an operator."""
    return tok in OPERATORS or (bool(tok) and set(tok) <= set(";&|()"))


def _segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    segs: list[list[str]] = [[]]
    for tok in lexer:
        if _is_op(tok):
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


def _classify_write(p: Path) -> tuple[str, str] | None:
    for ex in WRITE_PROTECTED_EXCEPT:
        if p == ex or _inside(p, ex):
            return None
    for root in WRITE_PROTECTED:
        if p == root or _inside(p, root):
            return ("deny", f"Agents can't modify {root} (their own code, settings or startup "
                            f"items). Propose the change to the operator instead.")
    for root in WRITE_ASK:
        if p == root or _inside(p, root):
            return ("ask", f"Changing {root} needs the operator's OK.")
    return None


def _positional(args: list[str]) -> list[str]:
    out, end = [], False
    for a in args:
        if not end and a == "--":
            end = True
        elif not end and a.startswith("-") and len(a) > 1:
            continue
        else:
            out.append(a)
    return out


def _in_place(name: str, args: list[str]) -> bool:
    for a in args:
        if a == "--in-place" or a == "-i" or (a.startswith("-i") and name in ("sed", "gsed")):
            return True
        if name in ("perl", "ruby") and a.startswith("-") and not a.startswith("--") and "i" in a[1:]:
            return True
    return False


def _write_targets(words: list[str], cwd: Path) -> list[str]:
    """Raw path words this command segment writes to (best effort)."""
    name = os.path.basename(words[0])
    args = words[1:]
    targets: list[str] = []
    # Output redirection anywhere in the segment: `> f`, `>>f`, `2>f`, `&>f`.
    for i, w in enumerate(words):
        m = re.match(r"^(?:\d*|&)?>>?\|?(.*)$", w)
        if m:
            if m.group(1):
                targets.append(m.group(1))
            elif i + 1 < len(words):
                targets.append(words[i + 1])
    pos = _positional(args)
    if name in WRITE_ALL_ARGS:
        targets += pos
    elif name in WRITE_SKIP_FIRST:
        targets += pos[1:]
    elif name in WRITE_LAST_ARG and pos:
        targets.append(pos[-1])
    elif name in IN_PLACE and _in_place(name, args):
        targets += pos
    elif name == "dd":
        targets += [a[3:] for a in args if a.startswith("of=")]
    elif name == "git":
        repo = str(cwd)
        rest = args
        while rest and rest[0].startswith("-"):
            if rest[0] == "-C" and len(rest) > 1:
                repo = rest[1]
                rest = rest[2:]
            else:
                rest = rest[1:]
        if rest and rest[0] in GIT_WRITE:
            targets.append(repo)
    return targets


def _check_words(words: list[str], cwd: Path, depth: int) -> tuple[str, str] | None:
    words = _strip(words)
    if not words:
        return None
    name = os.path.basename(words[0])
    # Applying updates / switching releases is the operator's call (they
    # merge into the fork, then update). Agents may check, not apply.
    if name == "aos" and len(words) > 1 and words[1] in ("update", "repair", "promote", "rollback", "channel"):
        if not (words[1] == "channel" and len(words) == 2):
            return ("ask", f"`aos {words[1]}` changes the running system; the operator decides when.")
    if name in ("check-update", "release-manager") or any(w.endswith("/check-update") or
                                                          w.endswith("/release-manager") for w in words[:2]):
        if any(w in ("--apply", "--continue", "create", "activate", "convert") for w in words):
            return ("ask", "Applying an update is the operator's call.")
    if name == "crontab" and any(a != "-l" for a in words[1:]):
        return ("deny", "Changing the crontab is blocked for agents (it would run code outside "
                        "Claude). Scheduled jobs belong in config/crons.yaml, changed by the operator.")
    if name == "launchctl" and len(words) > 1 and words[1] in ("load", "bootstrap", "submit", "enable"):
        if words[1] == "submit":
            return ("deny", "Agents may not submit new launchd jobs.")
        for w in (w for w in words[2:] if w.endswith(".plist")):
            p = _resolve(w, cwd)
            if p is None or not (_inside(p, HOME / "Library" / "LaunchAgents") and p.name.startswith("com.aos.")):
                return ("deny", "Agents may only (re)load existing AOS LaunchAgents, not new ones.")
    if name in INLINE_CODE:
        for i in range(1, len(words) - 1):
            if words[i] in ("-c", "-e", "-E"):
                code = words[i + 1]
                exp = code.replace("$HOME", str(HOME))
                exp = re.sub(r"(?<![\w/])~(?=/)", str(HOME), exp)
                for root in WRITE_PROTECTED:
                    if str(root) in exp and re.search(
                            r"open\(|write|unlink|remove|rename|rmtree|copy|move|symlink|chmod|mkdir|>", code):
                        return ("deny", f"Inline code that writes under {root} is blocked.")
    for t in _write_targets(words, cwd):
        p = _resolve(t, cwd)
        if p is None:
            continue
        verdict = _classify_write(p)
        if verdict:
            return verdict
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


def _read_only(command: str) -> bool:
    """True when every segment is a plain reader with no output redirection."""
    if re.search(r"(^|[^<>&0-9])>|>>|\btee\b", command):
        return False
    try:
        segs = _segments(command)
    except ValueError:
        return False
    for seg in segs:
        if not seg or _is_op(seg[0]):
            continue
        words = _strip(seg)
        if words and os.path.basename(words[0]) not in READ_ONLY_CMDS:
            return False
    return True


def check_command(command: str, cwd: Path | None = None, depth: int = 0) -> tuple[str, str] | None:
    cwd = cwd or Path.cwd()
    expanded = command.replace("${HOME}", str(HOME)).replace("$HOME", str(HOME))
    expanded = re.sub(r"(?<![\w/])~(?=/)", str(HOME), expanded)
    for s in SENSITIVE:
        if str(s) in expanded:
            return ("deny", f"Access to {s} is blocked for agents.")
    for f in OPERATOR_ONLY:
        if str(f) in expanded and not _read_only(command):
            return ("deny", f"{f} is operator-only; agents may read it but not change it.")
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
        if seg and _is_op(seg[0]):
            continue
        # Track `cd`/`pushd` so `cd ~/aos && echo x > f` is judged in ~/aos.
        stripped = _strip(seg)
        if stripped and stripped[0] in ("cd", "pushd"):
            nxt = _resolve(stripped[1] if len(stripped) > 1 else str(HOME), cwd)
            if nxt is not None:
                cwd = nxt
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
