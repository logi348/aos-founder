#!/usr/bin/env python3
"""MCP server Claude Code uses as its --permission-prompt-tool for bridge
sessions (hardened fork). Stdlib only; speaks newline-delimited JSON-RPC on
stdio.

Tool: approve(tool_name, input, ...) → forwards to the bridge's local API
(POST http://127.0.0.1:4098/approval, bearer token from
~/.aos/services/bridge/api.token), which asks the operator on Telegram.

Returns the permission-prompt result as JSON text:
  {"behavior": "allow", "updatedInput": <input unchanged>}
  {"behavior": "deny",  "message": "<why>"}
Any failure — bridge down, no token, timeout, malformed input — is a deny.

The exact argument names Claude Code sends are not in its public docs, so the
input schema accepts anything and the tool reads `tool_name`/`input` with
fallbacks; every call's argument keys are logged (never values) to
~/.aos/logs/approval-mcp.log so the shape can be checked on the real machine.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

PORT = int(os.environ.get("AOS_BRIDGE_API_PORT", "4098"))
TIMEOUT_S = 330  # a little longer than the bridge's own 300 s wait
LOG = Path.home() / ".aos" / "logs" / "approval-mcp.log"

TOOL = {
    "name": "approve",
    "description": "Ask the AOS operator on Telegram whether a tool call may run.",
    "inputSchema": {"type": "object", "additionalProperties": True,
                    "properties": {"tool_name": {"type": "string"}, "input": {"type": "object"}}},
}


def _log(line: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _token() -> str | None:
    p = Path(os.environ.get("AOS_BRIDGE_API_TOKEN_FILE",
                            Path.home() / ".aos" / "services" / "bridge" / "api.token"))
    try:
        return p.read_text().strip() or None
    except OSError:
        return None


def decide(args: dict, post=None) -> dict:
    """Pure-ish core: args from Claude Code → permission result dict."""
    tool_name = args.get("tool_name") or args.get("toolName") or args.get("name")
    tool_input = args.get("input")
    if tool_input is None:
        tool_input = args.get("tool_input", args.get("arguments"))
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return {"behavior": "deny", "message": "Approval request was malformed; denied."}
    post = post or _post
    try:
        verdict = post({"tool_name": tool_name, "input": tool_input})
    except Exception as e:  # noqa: BLE001
        return {"behavior": "deny", "message": f"Could not reach the operator ({type(e).__name__}); denied."}
    if verdict.get("decision") == "allow":
        return {"behavior": "allow", "updatedInput": tool_input}
    return {"behavior": "deny", "message": str(verdict.get("message") or "Denied by the operator.")}


def _post(payload: dict) -> dict:
    token = _token()
    if not token:
        raise RuntimeError("no bridge API token")
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/approval",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode())


def _reply(msg_id, result=None, error=None) -> None:
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


def handle(msg: dict) -> None:
    method, msg_id = msg.get("method"), msg.get("id")
    if msg_id is None:
        return  # notification (e.g. notifications/initialized)
    if method == "initialize":
        version = (msg.get("params") or {}).get("protocolVersion") or "2025-06-18"
        _reply(msg_id, {"protocolVersion": version,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "aos_approval", "version": "1.0"}})
    elif method == "ping":
        _reply(msg_id, {})
    elif method == "tools/list":
        _reply(msg_id, {"tools": [TOOL]})
    elif method == "tools/call":
        params = msg.get("params") or {}
        args = params.get("arguments") or {}
        _log(f"call keys={sorted(args.keys())} input_keys="
             f"{sorted(args['input'].keys()) if isinstance(args.get('input'), dict) else None}")
        result = decide(args) if params.get("name") == "approve" else \
            {"behavior": "deny", "message": "unknown tool"}
        _reply(msg_id, {"content": [{"type": "text", "text": json.dumps(result)}]})
    else:
        _reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            handle(json.loads(line))
        except Exception as e:  # noqa: BLE001
            _log(f"error: {type(e).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
