"""Hardened fork: the morning briefing's "While you slept" block."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import advance_report  # noqa: E402
import skye_brief  # noqa: E402


def _write(tmp_path, monkeypatch, generated, **report):
    f = tmp_path / "latest.json"
    f.write_text(json.dumps({"generated": generated.isoformat(timespec="seconds"),
                             "outputs": "/v/advance/2026-10-15", **report}))
    monkeypatch.setattr(advance_report, "_state_file", lambda: f)


NOW = datetime(2026, 10, 15, 8, 0)


def test_fresh_report_renders_all_three_parts(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, NOW - timedelta(hours=5),
           moved=[{"item": "Night-rate page", "did": "drafted copy"}],
           needs_you=[{"item": "Summer league", "ask": "pick a start date"}],
           parked=[{"item": "Sauna idea", "why": "no movement in 3 weeks"}])
    text = "\n".join(advance_report.briefing_lines(NOW))
    assert "WHILE YOU SLEPT" in text and "drafted copy" in text
    assert "pick a start date" in text and "Sauna idea" in text
    assert "/v/advance/2026-10-15/report.md" in text


def test_stale_empty_or_missing_report_shows_nothing(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, NOW - timedelta(days=2), moved=[{"item": "x", "did": "y"}])
    assert advance_report.briefing_lines(NOW) == []
    _write(tmp_path, monkeypatch, NOW - timedelta(hours=3), moved=[], needs_you=[], parked=[])
    assert advance_report.briefing_lines(NOW) == []
    monkeypatch.setattr(advance_report, "_state_file", lambda: tmp_path / "missing.json")
    assert advance_report.briefing_lines(NOW) == []


def test_failed_run_is_reported_and_text_is_escaped(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, NOW - timedelta(hours=2), moved=[{"item": "<b>x</b>", "did": "a & b"}],
           error="usage limit")
    text = "\n".join(advance_report.briefing_lines(NOW))
    assert "&lt;b&gt;x&lt;/b&gt;" in text and "a &amp; b" in text
    assert "usage limit" in text


def test_skye_brief_routes_to_skills_and_keeps_ideas_moving():
    t = skye_brief.TEXT
    for skill in ("ramble", "capture", "council", "step-by-step", "recall", "verification-before-completion"):
        assert skill in t
    assert "overnight" in t and "work/cli.py" in t
