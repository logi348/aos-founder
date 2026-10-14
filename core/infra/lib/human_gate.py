"""Require a person at a terminal before raising trust (hardened fork).

Upstream marked promotions `requires_human_approval: true` in trust.yaml, but
nothing read the flag: `trust-review promote`, the comms graduation `confirm
... accept` CLI and `converse create --trust 3` applied immediately for
anyone who could run them — including any agent with Bash.

`require_human(action)` refuses unless:
  - it is not running inside a Claude Code tool call (CLAUDECODE unset), and
  - stdin and stdout are a real terminal, and
  - the person types back a short random code shown on /dev/tty.

An agent's Bash tool has no terminal, so it is refused outright; the code
stops a scripted `yes |`. Combined with the settings.json deny rule on
editing ~/.aos/config/trust.yaml and the Bash guard, raising trust stays a
human action. Lowering trust (demote, reject) is never gated.

Set AOS_HUMAN_GATE_TEST_CODE only in tests (it fixes the code; it does not
skip the terminal check).
"""
from __future__ import annotations

import os
import secrets
import sys

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _ask(tty, action: str, code: str) -> str:
    tty.write(f"\n  About to {action}.\n  Type {code} to confirm: ")
    tty.flush()
    return tty.readline().strip().upper()


class HumanGateRefused(SystemExit):
    pass


def _refuse(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)
    raise HumanGateRefused(3)


def require_human(action: str, *, stdin=None, stdout=None, tty_path: str = "/dev/tty",
                  tty=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if os.environ.get("CLAUDECODE"):
        _refuse(f"Refusing to {action} from inside a Claude Code session. "
                "Run this command yourself in a Terminal window.")
    if not (stdin.isatty() and stdout.isatty()):
        _refuse(f"Refusing to {action} without an interactive terminal. "
                "Run this command yourself in a Terminal window.")
    code = os.environ.get("AOS_HUMAN_GATE_TEST_CODE") or "".join(
        secrets.choice(_ALPHABET) for _ in range(4))
    try:
        if tty is None:
            with open(tty_path, "r+") as t:
                answer = _ask(t, action, code)
        else:
            answer = _ask(tty, action, code)
    except OSError:
        _refuse(f"Refusing to {action}: no terminal to confirm on.")
    if answer != code:
        _refuse("Confirmation code did not match — nothing changed.")
