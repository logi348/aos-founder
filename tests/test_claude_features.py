"""Hardened fork: Remote Control / Claude in Chrome are opt-in.

core/infra/lib/claude_features.py, the `aos claude-features` CLI and the
claude_defaults reconcile check. Everything runs under a scratch $HOME.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "core" / "infra"))
sys.path.insert(0, str(REPO / "core" / "infra" / "reconcile"))
sys.path.insert(0, str(REPO / "core" / "infra" / "reconcile" / "checks"))

from lib import claude_features as cf  # noqa: E402
from claude_defaults import ClaudeDefaultsCheck  # noqa: E402

CLI = REPO / "core" / "bin" / "cli" / "claude-features"


def _home(tmp_path, monkeypatch, claude_json=None, settings=None):
    monkeypatch.setenv("HOME", str(tmp_path))
    if claude_json is not None:
        (tmp_path / ".claude.json").write_text(json.dumps(claude_json))
    if settings is not None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text(json.dumps(settings))


def _cj(tmp_path):
    return json.loads((tmp_path / ".claude.json").read_text())


def _st(tmp_path):
    return json.loads((tmp_path / ".claude" / "settings.json").read_text())


def test_defaults_are_off():
    assert cf.DEFAULTS == {"remote-control": False, "chrome": False}


def test_reconcile_turns_upstream_always_on_off(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch,
          claude_json={"remoteControlAtStartup": True, "claudeInChromeDefaultEnabled": True, "projects": {}},
          settings={"agent": "chief", "chrome": True, "remoteControlAtStartup": True})
    check = ClaudeDefaultsCheck()
    assert check.check() is False
    check.fix()
    assert _cj(tmp_path)["remoteControlAtStartup"] is False
    assert _cj(tmp_path)["claudeInChromeDefaultEnabled"] is False
    assert _cj(tmp_path)["projects"] == {}
    assert "chrome" not in _st(tmp_path)
    assert _st(tmp_path)["remoteControlAtStartup"] is False
    assert _st(tmp_path)["agent"] == "chief"
    assert ClaudeDefaultsCheck().check() is True


def test_opt_in_sticks_through_reconcile(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch, claude_json={}, settings={})
    cf.save({"remote-control": True, "chrome": False})  # what a confirmed `enable` writes
    cf.apply()
    assert _cj(tmp_path)["remoteControlAtStartup"] is True
    assert _st(tmp_path)["remoteControlAtStartup"] is True
    assert _cj(tmp_path)["claudeInChromeDefaultEnabled"] is False
    assert ClaudeDefaultsCheck().check() is True  # reconcile keeps the opt-in

    cf.save({"remote-control": True, "chrome": True})
    cf.apply()
    assert _st(tmp_path)["chrome"] is True


def test_cli_enable_needs_a_person_at_a_terminal(tmp_path, monkeypatch):
    """No TTY (an agent's Bash tool, cron, a pipe) → refused, nothing written."""
    _home(tmp_path, monkeypatch, claude_json={}, settings={})
    r = subprocess.run([sys.executable, str(CLI), "enable", "remote-control"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert r.returncode == 3
    assert "terminal" in r.stderr or "Claude Code session" in r.stderr
    assert not cf.config_path().exists()


def test_cli_disable_is_never_gated(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch, claude_json={}, settings={})
    cf.save({"remote-control": True, "chrome": True})
    r = subprocess.run([sys.executable, str(CLI), "disable", "chrome"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stderr
    assert "chrome" not in _st(tmp_path)
    assert _cj(tmp_path)["claudeInChromeDefaultEnabled"] is False


def test_cli_rejects_unknown_feature(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch, claude_json={})
    r = subprocess.run([sys.executable, str(CLI), "enable", "everything"], capture_output=True, text=True)
    assert r.returncode == 2


def test_missing_settings_json_is_not_created(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch, claude_json={})
    ClaudeDefaultsCheck().fix()
    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert ClaudeDefaultsCheck().check() is True
