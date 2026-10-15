"""core/bin/crons/advance — the overnight "advance and report" pass (hardened fork)."""
import importlib.machinery
import importlib.util
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("advance_cron", str(REPO / "core" / "bin" / "crons" / "advance"))
_spec = importlib.util.spec_from_loader("advance_cron", _loader)
adv = importlib.util.module_from_spec(_spec)
_loader.exec_module(adv)

SCHEMA = (REPO / "tests" / "fixtures" / "work_schema.sql").read_text()


def _db(tmp_path):
    db = tmp_path / "work.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    now = datetime.now().isoformat(timespec="seconds")
    future = (datetime.now() + timedelta(days=3)).isoformat(timespec="seconds")
    rows = [
        ("t1", "Pricing page for night rate", "active", 1, None),
        ("t2", "Idea: kids summer league", "todo", 3, None),
        ("t3", "Old finished thing", "done", 2, None),
        ("t4", "Snoozed thing", "todo", 2, future),
    ]
    for tid, title, status, prio, snooze in rows:
        conn.execute("INSERT INTO tasks (id, title, status, priority, created_at, snoozed_until) "
                     "VALUES (?,?,?,?,?,?)", (tid, title, status, prio, now, snooze))
    conn.execute("INSERT INTO task_handoffs (task_id, state, next_step, timestamp) VALUES (?,?,?,?)",
                 ("t1", "copy drafted", "compare competitor prices", now))
    conn.execute("INSERT INTO inbox (id, text, captured_at) VALUES ('i1', 'try a members-only open gym', ?)", (now,))
    conn.commit()
    conn.close()
    return db


def test_gathers_only_open_unsnoozed_tasks_with_handoff(tmp_path):
    tasks = adv.gather_tasks(_db(tmp_path))
    ids = [t["id"] for t in tasks]
    assert ids == ["t1", "t2"]
    assert tasks[0]["h_next"] == "compare competitor prices"


def test_gathers_inbox_initiatives_and_captures(tmp_path):
    db = _db(tmp_path)
    assert adv.gather_inbox(db)[0]["text"].startswith("try a members-only")
    vault = tmp_path / "vault"
    ini = vault / "knowledge" / "initiatives"
    ini.mkdir(parents=True)
    (ini / "a.md").write_text("---\ntitle: League launch\nstatus: shaping\n---\nbody")
    (ini / "b.md").write_text("---\ntitle: Old\nstatus: done\n---\n")
    assert [i["title"] for i in adv.gather_initiatives(vault)] == ["League launch"]
    tri = vault / "knowledge" / "triage"
    tri.mkdir(parents=True)
    (tri / "inbox.md").write_text("# Inbox\n- [idea] sauna?\n- [task] call plumber\n")
    assert adv.gather_captures(vault) == ["- [idea] sauna?", "- [task] call plumber"]


def test_missing_sources_are_empty_not_errors(tmp_path):
    assert adv.gather_tasks(tmp_path / "nope.db") == []
    assert adv.gather_inbox(tmp_path / "nope.db") == []
    assert adv.gather_initiatives(tmp_path) == []
    assert adv.gather_captures(tmp_path) == []
    assert adv.load_previous(tmp_path) == {}


def test_prompt_states_the_boundaries_and_contract(tmp_path):
    p = adv.build_prompt({"tasks": [{"id": "t1", "title": "X"}]}, date(2026, 10, 15), tmp_path / "out")
    assert "REVERSIBLE" in p and "Never" in p
    for forbidden in ("Message or email anyone", "git push", "spend money", "mark tasks done"):
        assert forbidden in p
    assert str(tmp_path / "out") in p
    assert "<<<ADVANCE_REPORT" in p and "at most 3" in p


def test_command_is_headless_without_bypass_and_blocks_outward_actions():
    cmd = adv.build_command()
    assert "--dangerously-skip-permissions" not in cmd and "bypassPermissions" not in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert "--tools" not in cmd
    for rule in ("Bash(*git push*)", "Bash(*comms-send*)", "Bash(*api.telegram.org*)", "Bash(*work done*)"):
        assert rule in cmd


def test_parse_report_good_bad_missing():
    good = 'blah\n<<<ADVANCE_REPORT\n{"moved":[{"item":"A","did":"researched","links":["/x"]}],' \
           '"needs_you":[{"item":"B","ask":"pick a price"}],"parked":[{"bad":1}]}\nADVANCE_REPORT>>>'
    r = adv.parse_report(good)
    assert r["moved"][0]["item"] == "A" and r["needs_you"][0]["ask"] == "pick a price"
    assert r["parked"] == []  # entries without an item are dropped
    assert "error" in adv.parse_report("no block")
    assert "error" in adv.parse_report("<<<ADVANCE_REPORT {not json} ADVANCE_REPORT>>>")


def test_write_report_and_main(tmp_path, monkeypatch):
    db = _db(tmp_path)
    monkeypatch.setattr(adv, "WORK_DB", db)
    monkeypatch.setattr(adv, "VAULT", tmp_path / "vault")
    monkeypatch.setattr(adv, "OUT_ROOT", tmp_path / "vault" / "advance")
    monkeypatch.setattr(adv, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(adv, "HOME", tmp_path)
    seen = {}

    def fake_dispatch(prompt, cwd, timeout=0):
        seen["prompt"] = prompt
        return ('<<<ADVANCE_REPORT {"moved":[{"item":"Pricing page","did":"compared 4 competitors",'
                '"links":["' + str(tmp_path) + '/vault/advance/x.md"]}],"needs_you":[],"parked":[]} ADVANCE_REPORT>>>')

    monkeypatch.setattr(adv, "dispatch", fake_dispatch)
    assert adv.main([]) == 0
    latest = json.loads((tmp_path / "state" / "latest.json").read_text())
    assert latest["moved"][0]["did"] == "compared 4 competitors"
    assert latest["date"] == date.today().isoformat()
    note = (tmp_path / "vault" / "advance" / date.today().isoformat() / "report.md").read_text()
    assert "Pricing page" in note and "## Needs you" in note
    assert "Pricing page for night rate" in seen["prompt"]


def test_failed_run_still_reports_the_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(adv, "WORK_DB", _db(tmp_path))
    monkeypatch.setattr(adv, "VAULT", tmp_path / "vault")
    monkeypatch.setattr(adv, "OUT_ROOT", tmp_path / "vault" / "advance")
    monkeypatch.setattr(adv, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(adv, "HOME", tmp_path)

    def boom(prompt, cwd, timeout=0):
        raise RuntimeError("usage limit")

    monkeypatch.setattr(adv, "dispatch", boom)
    assert adv.main([]) == 0
    assert "usage limit" in json.loads((tmp_path / "state" / "latest.json").read_text())["error"]


def test_nothing_open_skips_without_running(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(adv, "WORK_DB", tmp_path / "none.db")
    monkeypatch.setattr(adv, "VAULT", tmp_path / "vault")
    monkeypatch.setattr(adv, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(adv, "dispatch", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    assert adv.main([]) == 0
    assert "nothing open" in capsys.readouterr().out
