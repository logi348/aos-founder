"""Phone approval for Claude tool calls from the Telegram bridge (hardened fork).

Bridge sessions used to run with --permission-mode bypassPermissions: every
tool call from a Telegram-driven Claude ran unasked. Now they run in
`default` mode with `--permission-prompt-tool mcp__aos_approval__approve`:

  * calls the settings.json allow list pre-approves run as before (Bash,
    reads/edits inside the AOS directories, web, agents…) — no prompt;
  * calls a deny rule or the Bash guard refuses never reach the phone;
  * everything else (an edit outside the AOS dirs, an MCP tool, a Bash
    command the guard marks "ask") arrives on the operator's phone as a
    Telegram message with Allow / Deny buttons.

Flow: Claude Code → approval_mcp.py (stdio MCP server it spawns) → POST
/approval on the bridge's local API (token-protected) → this module sends the
Telegram prompt and waits → button press → decision back down the chain.
No answer within APPROVAL_TIMEOUT_S, a bridge restart, or any error = deny.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import secrets
import time

logger = logging.getLogger("aos.bridge.approvals")

APPROVAL_TIMEOUT_S = 300
CALLBACK_PREFIX = "appr:"

# id -> (future, created_at, summary)
_pending: dict[str, tuple[asyncio.Future, float, str]] = {}
# async (approval_id, text_html) -> message handle or None; set by the channel
_sender = None
# async (handle, text_html) -> None; edits the prompt after a decision
_editor = None


def set_transport(sender, editor=None) -> None:
    global _sender, _editor
    _sender, _editor = sender, editor


def summarize(tool_name: str, tool_input: dict) -> str:
    """Short, HTML-escaped description of what is being asked for."""
    ti = tool_input if isinstance(tool_input, dict) else {}
    if tool_name == "Bash":
        detail = ti.get("command", "")
    elif tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Read"):
        detail = ti.get("file_path") or ti.get("notebook_path") or ""
    elif tool_name in ("WebFetch",):
        detail = ti.get("url", "")
    else:
        detail = json.dumps(ti, ensure_ascii=False)[:400]
    detail = str(detail)
    if len(detail) > 600:
        detail = detail[:600] + "…"
    return f"<b>{html.escape(tool_name)}</b>\n<pre>{html.escape(detail)}</pre>"


async def request(tool_name: str, tool_input: dict, timeout: float = APPROVAL_TIMEOUT_S) -> dict:
    """Ask the operator. Returns {"decision": "allow"|"deny", "message": str}."""
    if _sender is None:
        return {"decision": "deny", "message": "No Telegram connection to ask the operator."}
    approval_id = secrets.token_hex(6)
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    summary = summarize(tool_name, tool_input)
    _pending[approval_id] = (fut, time.time(), summary)
    handle = None
    try:
        handle = await _sender(approval_id, "Claude wants to run:\n" + summary)
        if handle is None:
            return {"decision": "deny", "message": "Could not reach the operator's phone."}
        allowed = await asyncio.wait_for(fut, timeout)
    except asyncio.TimeoutError:
        allowed = None
    except Exception as e:  # noqa: BLE001
        logger.error("approval %s failed: %s", approval_id, e)
        allowed = None
    finally:
        _pending.pop(approval_id, None)

    if allowed is True:
        outcome, msg = "allow", "Approved on the operator's phone."
    elif allowed is False:
        outcome, msg = "deny", "The operator denied this on their phone."
    else:
        outcome, msg = "deny", f"No answer within {int(timeout)}s — denied."
    if handle is not None and _editor is not None:
        label = {"allow": "✅ Allowed", "deny": "⛔ Denied"}[outcome]
        if allowed is None:
            label = "⌛ Timed out — denied"
        try:
            await _editor(handle, f"{label}\n{summary}")
        except Exception:  # noqa: BLE001
            pass
    logger.info("approval %s %s: %s", approval_id, outcome, tool_name)
    return {"decision": outcome, "message": msg}


def resolve(callback_data: str) -> bool:
    """Handle a button press. True if it belonged to a pending approval."""
    if not callback_data.startswith(CALLBACK_PREFIX):
        return False
    try:
        _, approval_id, choice = callback_data.split(":", 2)
    except ValueError:
        return False
    entry = _pending.get(approval_id)
    if entry is None:
        return True  # stale button: swallow it, nothing to do
    fut = entry[0]
    if not fut.done():
        fut.set_result(choice == "a")
    return True


async def handle_http(request):
    """POST /approval {tool_name, input} — called by approval_mcp.py. The
    API middleware has already checked the bearer token."""
    from aiohttp import web
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"decision": "deny", "message": "bad request"}, status=400)
    result = await request_approval_from_body(body)
    return web.json_response(result)


async def request_approval_from_body(body: dict) -> dict:
    tool_name = str(body.get("tool_name") or "unknown tool")
    tool_input = body.get("input") if isinstance(body.get("input"), dict) else {}
    return await request(tool_name, tool_input)
