"""core/infra/lib/human_gate.py — raising trust needs a person at a terminal."""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "infra"))
from lib import human_gate  # noqa: E402


class _Stream(io.StringIO):
    def __init__(self, tty):
        super().__init__()
        self._tty = tty

    def isatty(self):
        return self._tty


class _Tty(io.StringIO):
    """A terminal whose operator types `answer`."""
    def __init__(self, answer):
        super().__init__()
        self._answer = answer + "\n"

    def readline(self, *a):
        return self._answer


def test_refused_inside_claude_code(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDECODE", "1")
    with pytest.raises(SystemExit):
        human_gate.require_human("x", stdin=_Stream(True), stdout=_Stream(True),
                                 tty=_Tty("ABCD"))


def test_refused_without_a_terminal(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    with pytest.raises(SystemExit):
        human_gate.require_human("x", stdin=_Stream(False), stdout=_Stream(True),
                                 tty=_Tty("ABCD"))


def test_wrong_code_refused(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.setenv("AOS_HUMAN_GATE_TEST_CODE", "ABCD")
    with pytest.raises(SystemExit):
        human_gate.require_human("x", stdin=_Stream(True), stdout=_Stream(True),
                                 tty=_Tty("WXYZ"))


def test_right_code_passes(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.setenv("AOS_HUMAN_GATE_TEST_CODE", "ABCD")
    human_gate.require_human("x", stdin=_Stream(True), stdout=_Stream(True),
                             tty=_Tty("abcd"))


def test_trust_review_promote_refused_without_terminal(tmp_path, monkeypatch):
    import subprocess
    pytest.importorskip("yaml")  # trust-review imports it at module load
    repo = Path(__file__).resolve().parent.parent
    (tmp_path / ".aos" / "config").mkdir(parents=True)
    trust = tmp_path / ".aos" / "config" / "trust.yaml"
    trust.write_text("agents:\n  engineer:\n    trust_level: 0\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    r = subprocess.run([sys.executable, str(repo / "core" / "bin" / "cli" / "trust-review"),
                        "promote", "engineer", "--to", "3"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert r.returncode == 3
    assert "trust_level: 0" in trust.read_text()
