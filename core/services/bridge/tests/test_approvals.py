"""Hardened fork: Telegram bridge sessions ask the operator's phone instead
of bypassing permissions (approvals.py, approval_mcp.py, bridge_permissions.py)."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import approval_mcp  # noqa: E402
import approvals  # noqa: E402
import bridge_permissions  # noqa: E402


# ── bridge_permissions ─────────────────────────────────────────────────────

def test_default_mode_uses_phone_approval_not_bypass(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge_permissions, "MODE_FILE", tmp_path / "missing")
    a = bridge_permissions.args()
    assert "bypassPermissions" not in a
    assert a[a.index("--permission-mode") + 1] == "default"
    assert a[a.index("--permission-prompt-tool") + 1] == "mcp__aos_approval__approve"
    cfg = json.loads(a[a.index("--mcp-config") + 1])
    assert cfg["mcpServers"]["aos_approval"]["args"][0].endswith("approval_mcp.py")


def test_operator_can_choose_dontask_or_bypass(tmp_path, monkeypatch):
    f = tmp_path / "mode"
    monkeypatch.setattr(bridge_permissions, "MODE_FILE", f)
    f.write_text("dontAsk\n")
    assert bridge_permissions.args() == ["--permission-mode", "dontAsk"]
    f.write_text("bypass\n")
    assert bridge_permissions.args() == ["--permission-mode", "bypassPermissions"]
    f.write_text("nonsense\n")
    assert "--permission-prompt-tool" in bridge_permissions.args()


# ── approvals (bridge side) ────────────────────────────────────────────────

def _run(coro):
    return asyncio.run(coro)


def test_allow_and_deny_round_trip():
    sent, edited = [], []

    async def sender(aid, text):
        sent.append((aid, text))
        return "msg"

    async def editor(handle, text):
        edited.append(text)

    async def flow(choice):
        approvals.set_transport(sender, editor)
        before = len(sent)
        task = asyncio.create_task(approvals.request("Edit", {"file_path": "/Users/x/Desktop/a.txt"}, timeout=5))
        while len(sent) == before:
            await asyncio.sleep(0)
        aid = sent[-1][0]
        assert approvals.resolve(f"appr:{aid}:{choice}")
        return await task

    assert _run(flow("a"))["decision"] == "allow"
    assert _run(flow("d"))["decision"] == "deny"
    assert "/Users/x/Desktop/a.txt" in sent[0][1]
    assert edited[0].startswith("✅") and edited[1].startswith("⛔")


def test_timeout_and_no_transport_deny():
    approvals.set_transport(None)
    assert _run(approvals.request("Bash", {"command": "x"}, timeout=1))["decision"] == "deny"

    async def sender(aid, text):
        return "msg"

    approvals.set_transport(sender)
    r = _run(approvals.request("Bash", {"command": "x"}, timeout=0.05))
    assert r["decision"] == "deny" and "No answer" in r["message"]


def test_summary_is_escaped():
    s = approvals.summarize("Bash", {"command": "echo <b>hi</b> & rm"})
    assert "&lt;b&gt;" in s and "&amp;" in s


def test_unrelated_and_stale_callbacks():
    assert approvals.resolve("stop_generation") is False
    assert approvals.resolve("appr:doesnotexist:a") is True  # swallowed, no effect


# ── approval_mcp (Claude Code side) ────────────────────────────────────────

def test_mcp_decide_allow_returns_original_input():
    inp = {"file_path": "/tmp/x"}
    r = approval_mcp.decide({"tool_name": "Edit", "input": inp}, post=lambda p: {"decision": "allow"})
    assert r == {"behavior": "allow", "updatedInput": inp}


def test_mcp_decide_denies_on_anything_else():
    assert approval_mcp.decide({"tool_name": "Edit", "input": {}},
                               post=lambda p: {"decision": "deny", "message": "no"})["behavior"] == "deny"

    def boom(p):
        raise OSError("bridge down")

    assert approval_mcp.decide({"tool_name": "Edit", "input": {}}, post=boom)["behavior"] == "deny"
    assert approval_mcp.decide({"tool_name": "Edit"}, post=lambda p: {"decision": "allow"})["behavior"] == "deny"
    assert approval_mcp.decide({}, post=lambda p: {"decision": "allow"})["behavior"] == "deny"


def test_mcp_no_token_denies(tmp_path, monkeypatch):
    monkeypatch.setenv("AOS_BRIDGE_API_TOKEN_FILE", str(tmp_path / "none"))
    r = approval_mcp.decide({"tool_name": "Edit", "input": {}})
    assert r["behavior"] == "deny"


def test_mcp_jsonrpc_handshake_and_call(capsys, monkeypatch):
    monkeypatch.setattr(approval_mcp, "_post", lambda p: {"decision": "allow"})
    monkeypatch.setattr(approval_mcp, "_log", lambda line: None)
    approval_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-11-25"}})
    approval_mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    approval_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    approval_mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "approve", "arguments": {"tool_name": "Bash", "input": {"command": "ls"}}}})
    approval_mcp.handle({"jsonrpc": "2.0", "id": 4, "method": "bogus"})
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [m["id"] for m in lines] == [1, 2, 3, 4]
    assert lines[0]["result"]["protocolVersion"] == "2025-11-25"
    assert lines[1]["result"]["tools"][0]["name"] == "approve"
    verdict = json.loads(lines[2]["result"]["content"][0]["text"])
    assert verdict == {"behavior": "allow", "updatedInput": {"command": "ls"}}
    assert lines[3]["error"]["code"] == -32601
