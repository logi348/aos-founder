"""Hardened fork: the Telegram "Apply update" button applies only the exact
version it was offered for (update_offer.py)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import update_offer  # noqa: E402

H = "a" * 40


def _state(tmp_path, monkeypatch, **s):
    f = tmp_path / "update-state.json"
    f.write_text(json.dumps(s))
    monkeypatch.setattr(update_offer, "_state_file", lambda: f)


def test_matching_pending_version_is_applied(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, status="update_available", remote=H)
    text, apply = update_offer.decide("aos_update:" + H)
    assert apply == H and "Applying" in text


def test_stale_button_does_nothing(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, status="update_available", remote="b" * 40)
    assert update_offer.decide("aos_update:" + H)[1] is None


def test_up_to_date_or_missing_state_does_nothing(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, status="up_to_date", remote=H)
    assert update_offer.decide("aos_update:" + H)[1] is None
    monkeypatch.setattr(update_offer, "_state_file", lambda: tmp_path / "missing.json")
    assert update_offer.decide("aos_update:" + H)[1] is None


def test_later_and_empty_hash_do_nothing(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, status="update_available", remote=H)
    assert update_offer.decide("aos_update_later")[1] is None
    assert update_offer.decide("aos_update:")[1] is None
