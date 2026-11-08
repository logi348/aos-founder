"""
Founder-edition workshop: durable, approved, undoable changes to AOS itself.

The problem: runtime_protection (periodic_fix=True — every 30 minutes and on
deploy) wipes uncommitted edits in ~/aos and resets local commits to
origin/main when ~/aos is a git clone. The workshop gives the operator a place
where changes survive:

    ~/project/aos (workshop) → the operator's own private repo → aos update

Everything here runs offline in a fake HOME. Local bare repos stand in for
GitHub: `me-aos.git` for the operator's private <me>/aos, `upstream.git` for
the original project. workshop-setup's WORKSHOP_REPO_URL hook skips `gh`
entirely; a stub `gh` first on PATH proves it is never called.

`aos update` is stood in for by `git fetch && git merge --ff-only` in ~/aos —
the same move release-manager's convert path makes before it moves ~/aos.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SETUP = REPO_ROOT / "core" / "bin" / "internal" / "workshop-setup"
SAFETY = REPO_ROOT / "core" / "bin" / "internal" / "workshop-safety-check"
RECONCILE = REPO_ROOT / "core" / "infra" / "reconcile"
RP_PATH = RECONCILE / "checks" / "runtime_protection.py"

UPSTREAM_GITHUB = "https://github.com/logi348/aos-founder.git"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _env(home: Path, extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env.update(GIT_ENV)
    env["HOME"] = str(home)
    env["GIT_CONFIG_GLOBAL"] = str(home / ".gitconfig")
    env.pop("AOS_HOME_OVERRIDE", None)
    if extra:
        env.update(extra)
    return env


def git(home: Path, *args, cwd: Path | None = None, check=True) -> str:
    r = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
        env=_env(home), timeout=60,
    )
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {r.stderr}")
    return r.stdout.strip()


def _load_rp():
    for p in (str(RECONCILE), str(RECONCILE / "checks")):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("runtime_protection_under_test", RP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def world(tmp_path):
    """Fake HOME with ~/aos as a git clone of the 'original project', plus an
    empty bare repo standing in for the operator's private <me>/aos."""
    home = tmp_path / "home"
    home.mkdir()
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    (home / ".gitconfig").write_text("[init]\n\tdefaultBranch = main\n")

    upstream = remotes / "upstream.git"
    git(home, "init", "--quiet", "--bare", "-b", "main", str(upstream))
    seed = tmp_path / "seed"
    git(home, "init", "--quiet", "-b", "main", str(seed))
    (seed / "README.md").write_text("AOS\n")
    (seed / ".gitignore").write_text(".no-auto-commit\n")
    (seed / "core" / "skills" / "briefing").mkdir(parents=True)
    (seed / "core" / "skills" / "briefing" / "SKILL.md").write_text("long briefing\n")
    git(home, "add", "README.md", ".gitignore", "core", cwd=seed)
    git(home, "commit", "--quiet", "-m", "seed", cwd=seed)
    git(home, "tag", "stable", cwd=seed)
    git(home, "push", "--quiet", str(upstream), "main", "--tags", cwd=seed)

    runtime = home / "aos"
    git(home, "clone", "--quiet", str(upstream), str(runtime))
    # As on a real install, ~/aos tracks the original project on GitHub (never
    # contacted here — setup repoints it before any fetch).
    git(home, "remote", "set-url", "origin", UPSTREAM_GITHUB, cwd=runtime)
    assert git(home, "tag", "-l", "stable", cwd=runtime) == "stable"

    mine = remotes / "me-aos.git"
    git(home, "init", "--quiet", "--bare", "-b", "main", str(mine))

    (home / ".aos" / "config").mkdir(parents=True)
    (home / ".aos" / "config" / "operator.yaml").write_text("name: Founder\nagent_name: Skye\n")

    # A gh that must never run.
    stub_bin = tmp_path / "stubbin"
    stub_bin.mkdir()
    gh_marker = tmp_path / "gh-was-called"
    gh = stub_bin / "gh"
    gh.write_text(f"#!/bin/bash\ntouch '{gh_marker}'\nexit 1\n")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)

    return {
        "home": home, "runtime": runtime, "workshop": home / "project" / "aos",
        "mine": mine, "upstream": upstream, "stub_bin": stub_bin, "gh_marker": gh_marker,
    }


def run_setup(w, *args):
    env = _env(w["home"], {
        "WORKSHOP_REPO_URL": str(w["mine"]),
        "WORKSHOP_REPO_SLUG": "me/aos",
        "WORKSHOP_PYTHON": sys.executable,
        "PATH": f"{w['stub_bin']}{os.pathsep}{os.environ.get('PATH', '')}",
    })
    return subprocess.run(["bash", str(SETUP), *args], capture_output=True, text=True,
                          env=env, timeout=120)


def rp_check(mod, monkeypatch, runtime: Path):
    monkeypatch.setattr(mod, "RUNTIME_DIR", runtime)
    chk = mod.RuntimeProtectionCheck()
    chk.hooks_dir = runtime / ".git" / "hooks"
    chk.hook_path = runtime / ".git" / "hooks" / "pre-commit"
    chk.marker_path = runtime / ".no-auto-commit"
    return chk


def aos_update_standin(w):
    git(w["home"], "fetch", "--quiet", "origin", cwd=w["runtime"])
    git(w["home"], "merge", "--quiet", "--ff-only", "origin/main", cwd=w["runtime"])


# ── Scripts are shippable ────────────────────────────────────────────────────


@pytest.mark.parametrize("script", [SETUP, SAFETY])
def test_scripts_are_executable_and_parse(script):
    assert os.access(script, os.X_OK)
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0


# ── Setup ────────────────────────────────────────────────────────────────────


def test_setup_creates_an_independent_workshop(world):
    w = world
    assert run_setup(w, "--check").returncode == 1

    r = run_setup(w)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not w["gh_marker"].exists(), "gh must not run when WORKSHOP_REPO_URL is set"

    ws, rt, home = w["workshop"], w["runtime"], w["home"]
    assert (ws / ".git").is_dir()
    assert git(home, "remote", "get-url", "origin", cwd=ws) == str(w["mine"])
    assert git(home, "remote", "get-url", "upstream", cwd=ws) == UPSTREAM_GITHUB
    assert git(home, "remote", "get-url", "--push", "upstream", cwd=ws) == "DISABLED"
    assert git(home, "config", "remote.upstream.tagOpt", cwd=ws) == "--no-tags"
    assert git(home, "remote", "get-url", "origin", cwd=rt) == str(w["mine"])
    assert git(home, "symbolic-ref", "--short", "HEAD", cwd=ws) == "main"

    # The operator's repo got main — and no tags (no stale `stable`).
    assert git(home, "rev-parse", "main", cwd=w["mine"]) == git(home, "rev-parse", "HEAD", cwd=rt)
    assert git(home, "ls-remote", "--tags", str(w["mine"])) == ""
    assert git(home, "tag", "-l", "stable", cwd=ws) == ""
    assert git(home, "tag", "-l", "stable", cwd=rt) == ""

    data = yaml.safe_load((home / ".aos" / "config" / "operator.yaml").read_text())
    assert data["role"] == "developer"
    assert data["workshop"]["repo"] == "me/aos"
    assert data["workshop"]["url"] == str(w["mine"])
    assert data["workshop"]["created"]
    assert data["name"] == "Founder"  # existing content preserved

    assert run_setup(w, "--check").returncode == 0
    # Idempotent.
    r2 = run_setup(w)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    data2 = yaml.safe_load((home / ".aos" / "config" / "operator.yaml").read_text())
    assert data2["workshop"]["created"] == data["workshop"]["created"]


def test_after_setup_only_upstream_points_at_logi348(world):
    w = world
    assert run_setup(w).returncode == 0
    for repo in (w["runtime"], w["workshop"]):
        out = git(w["home"], "remote", "-v", cwd=repo)
        for line in out.splitlines():
            name, url = line.split()[:2]
            if "logi348" in url:
                assert name == "upstream", f"{repo}: {line}"
                if "(push)" in line:
                    pytest.fail(f"{repo}: upstream push URL is not DISABLED: {line}")
        if repo == w["workshop"]:
            assert git(w["home"], "remote", "get-url", "--push", "upstream", cwd=repo) == "DISABLED"
        else:
            assert "upstream" not in git(w["home"], "remote", cwd=repo).split()


# ── A change survives runtime protection; undo works ─────────────────────────


def test_change_survives_runtime_protection_and_undo_reverts(world, monkeypatch):
    w = world
    home, ws, rt = w["home"], w["workshop"], w["runtime"]
    assert run_setup(w).returncode == 0
    rp = _load_rp()

    # Make a change the workshop way: branch, commit, ff main, push.
    skill = ws / "core" / "skills" / "briefing" / "SKILL.md"
    git(home, "switch", "--quiet", "-c", "change/short-briefing", cwd=ws)
    skill.write_text("three bullet points\n")
    git(home, "add", "core/skills/briefing/SKILL.md", cwd=ws)
    git(home, "commit", "--quiet", "-m", "Shorter morning briefing", cwd=ws)
    git(home, "switch", "--quiet", "main", cwd=ws)
    git(home, "merge", "--quiet", "--ff-only", "change/short-briefing", cwd=ws)
    git(home, "push", "--quiet", "origin", "main", cwd=ws)

    aos_update_standin(w)
    deployed = rt / "core" / "skills" / "briefing" / "SKILL.md"
    assert deployed.read_text() == "three bullet points\n"

    chk = rp_check(rp, monkeypatch, rt)
    res = chk.fix()
    assert deployed.read_text() == "three bullet points\n", res.message
    assert chk.check() is True
    assert "workshop" in chk.hook_path.read_text()

    # Undo: revert in the workshop, push, update.
    head = git(home, "rev-parse", "HEAD", cwd=ws)
    git(home, "revert", "--no-edit", head, cwd=ws)
    git(home, "push", "--quiet", "origin", "main", cwd=ws)
    aos_update_standin(w)
    assert deployed.read_text() == "long briefing\n"
    chk.fix()
    assert deployed.read_text() == "long briefing\n"
    assert chk.check() is True


def test_edit_directly_in_runtime_is_discarded_and_named(world, monkeypatch):
    w = world
    assert run_setup(w).returncode == 0
    rp = _load_rp()
    rt = w["runtime"]
    chk = rp_check(rp, monkeypatch, rt)
    chk.fix()  # install hook + marker

    (rt / "README.md").write_text("edited in place\n")
    (rt / "stray.txt").write_text("untracked\n")
    assert chk.check() is False

    res = chk.fix()
    assert res.status == rp.Status.FIXED
    assert "README.md" in res.message
    assert "stray.txt" in res.message
    assert "workshop" in res.message
    assert (rt / "README.md").read_text() == "AOS\n"
    assert not (rt / "stray.txt").exists()
    assert chk.check() is True


def test_discard_message_caps_listed_names(world, monkeypatch):
    w = world
    assert run_setup(w).returncode == 0
    rp = _load_rp()
    rt = w["runtime"]
    chk = rp_check(rp, monkeypatch, rt)
    chk.fix()
    for i in range(25):
        (rt / f"junk{i:02d}.txt").write_text("x")
    res = chk.fix()
    assert "(+5 more)" in res.message
    assert res.message.count("junk") == rp.MAX_LISTED


# ── Safety check ─────────────────────────────────────────────────────────────


def _safety(stdin: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SAFETY), "-"], input=stdin,
                          capture_output=True, text=True, timeout=30)


def test_safety_check_flags_sensitive_paths():
    r = _safety("core/hooks/x\nconfig/crons.yaml\ncore/skills/foo/SKILL.md\n")
    assert r.returncode == 0
    lines = r.stdout.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("SAFETY: core/hooks/x")
    assert lines[1].startswith("SAFETY: config/crons.yaml")


def test_safety_check_silent_for_ordinary_change():
    r = _safety("core/skills/foo/SKILL.md\n")
    assert r.returncode == 0
    assert r.stdout == ""


@pytest.mark.parametrize("path", [
    "core/infra/lib/claude_permissions.py",
    "core/infra/reconcile/checks/runtime_protection.py",
    "config/defaults/trust.yaml",
    "install.sh",
    "core/bin/crons/check-update",
    "core/bin/internal/release-manager",
])
def test_safety_check_covers_each_listed_path(path):
    assert _safety(path + "\n").stdout.startswith(f"SAFETY: {path}")


def test_safety_check_reads_a_git_range(world):
    w = world
    home = w["home"]
    assert run_setup(w).returncode == 0
    ws = w["workshop"]
    git(home, "switch", "--quiet", "-c", "change/x", cwd=ws)
    (ws / "core" / "hooks").mkdir(parents=True)
    (ws / "core" / "hooks" / "x").write_text("loosened\n")
    git(home, "add", "core/hooks/x", cwd=ws)
    git(home, "commit", "--quiet", "-m", "x", cwd=ws)
    r = subprocess.run(["bash", str(SAFETY), "-C", str(ws), "main..change/x"],
                       capture_output=True, text=True, timeout=30, env=_env(home))
    assert r.returncode == 0
    assert r.stdout.startswith("SAFETY: core/hooks/x")


def test_setup_on_release_install_snapshots_the_running_code(world):
    """~/aos without .git (release install) and no ~/.aos/repo: the workshop
    starts from a snapshot of what's running, and updates then come from it."""
    import shutil

    w = world
    shutil.rmtree(w["runtime"] / ".git")
    r = run_setup(w)
    assert r.returncode == 0, r.stdout + r.stderr
    ws = w["workshop"]
    assert (ws / "core" / "skills" / "briefing" / "SKILL.md").read_text() == "long briefing\n"
    assert git(w["home"], "remote", "get-url", "origin", cwd=ws) == str(w["mine"])
    assert git(w["home"], "rev-parse", "main", cwd=w["mine"]) == git(w["home"], "rev-parse", "HEAD", cwd=ws)
    assert run_setup(w, "--check").returncode == 0
