"""Hardened fork: voice notes are transcribed on the Mac by default, and the
local model is released after an idle spell (core/services/transcriber)."""
import importlib.util
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "core" / "services" / "transcriber" / "engine.py"


def _load(monkeypatch, backend=None):
    if backend is None:
        monkeypatch.delenv("TRANSCRIBER_BACKEND", raising=False)
    else:
        monkeypatch.setenv("TRANSCRIBER_BACKEND", backend)
    spec = importlib.util.spec_from_file_location("transcriber_engine_under_test", ENGINE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["transcriber_engine_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_default_backend_is_local(monkeypatch):
    assert _load(monkeypatch).BACKEND == "local"


def test_cloud_is_still_available_by_choice(monkeypatch):
    assert _load(monkeypatch, "cloud").BACKEND == "cloud"


def test_model_not_loaded_at_import(monkeypatch):
    assert _load(monkeypatch).model_loaded() is False


def test_idle_exit_decision(monkeypatch):
    e = _load(monkeypatch)
    assert e.should_exit_idle(now=2000, last_used=1000, in_flight=0, loaded=True, idle_exit_s=900)
    assert not e.should_exit_idle(now=1500, last_used=1000, in_flight=0, loaded=True, idle_exit_s=900)
    assert not e.should_exit_idle(now=2000, last_used=1000, in_flight=1, loaded=True, idle_exit_s=900)
    assert not e.should_exit_idle(now=2000, last_used=1000, in_flight=0, loaded=False, idle_exit_s=900)
    assert not e.should_exit_idle(now=9999, last_used=0, in_flight=0, loaded=True, idle_exit_s=0)
