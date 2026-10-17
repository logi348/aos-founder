"""
The installer must run AOS code on the AOS interpreter, never plain python3.

On a new Mac, `python3` is Homebrew's or Apple's: it has no PyYAML, so the
migration runner died on `import yaml` before migration 001 ran. No
~/.aos/.version was written, and the install reported five critical failures
(migrations, event bus, work system, both CLAUDE.md files). Service venvs built
on Homebrew's python3 could not be installed into either, which left the
bridge without yaml/httpx and the transcriber without mlx-whisper.
"""

import re
from pathlib import Path

INSTALL_SH = (Path(__file__).parent.parent / "install.sh").read_text()


def _code_lines():
    for n, line in enumerate(INSTALL_SH.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        yield n, line


def test_aos_py_points_at_resolver():
    assert 'AOS_PY="$AOS_DIR/core/bin/internal/aos-python"' in INSTALL_SH


def test_migration_runner_uses_aos_python():
    assert '"$AOS_PY" "$AOS_DIR/core/infra/migrations/runner.py" migrate' in INSTALL_SH


def test_no_bare_python3_runs_aos_code():
    # Bare python3 is allowed only for the "Python 3.11+" tool check and inside
    # strings written for later (hook commands, hints to the operator).
    offenders = []
    for n, line in _code_lines():
        if "Python 3.11+" in line:
            continue
        if re.search(r'(?:^|[\s(|$])python3 (?:-c |-\s|"\$AOS_DIR)', line):
            offenders.append(f"{n}: {line.strip()}")
    assert not offenders, "bare python3 in install.sh:\n" + "\n".join(offenders)


def test_service_venvs_prefer_pinned_interpreter():
    assert 'for p in "$pinned_py" ' in INSTALL_SH
    assert 'uv python find' in INSTALL_SH
