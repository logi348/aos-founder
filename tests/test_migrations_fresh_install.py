"""
A fresh install runs every migration from 001 in one process, and the first
failure stops the rest. These pin the fixes for the ones that could never
pass on a new machine:

  - 054 (Qareen), 056 (n8n), 080 (Qareen remote access) install services
    that later migrations retired; their templates are gone, so up() failed.
  - 100 imported `db`, which resolved to the people db module 060–068 had
    already loaded, and failed with a TypeError.
"""

import importlib.util
import sys
import types
from pathlib import Path

MIGRATIONS = Path(__file__).parent.parent / "core" / "infra" / "migrations"


def _load(stem):
    spec = importlib.util.spec_from_file_location(f"fresh_{stem}", MIGRATIONS / f"{stem}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_retired_service_migrations_skip_when_their_templates_are_gone():
    for stem in ("054_qareen_service", "056_n8n_service", "080_remote_access_init"):
        mod = _load(stem)
        assert not mod.TEMPLATE_PATH.exists(), f"{stem}: template is back — revisit the skip"
        assert mod.check() is True, stem


def test_converse_migration_loads_its_own_db_despite_a_cached_db_module(monkeypatch):
    fake = types.ModuleType("db")
    fake.connect = lambda: None  # the people db's signature
    monkeypatch.setitem(sys.modules, "db", fake)
    mod = _load("100_converse_init")
    converse_db = mod._load_converse_db()
    assert converse_db is not None
    assert converse_db is not fake
    assert Path(converse_db.__file__).parts[-3:] == ("comms", "converse", "db.py")


def test_qren_site_root_up_returns_true_when_it_seeds(tmp_path, monkeypatch):
    mod = _load("107_qren_site_root")
    monkeypatch.setattr(mod, "_discover", lambda: tmp_path)
    monkeypatch.setattr(mod, "_config_path", lambda: tmp_path / "cfg" / "qren-root")
    assert mod.up() is True
    assert (tmp_path / "cfg" / "qren-root").read_text().strip() == str(tmp_path)
