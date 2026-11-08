# Pulling in upstream changes

This repository is a hardened fork of AOS (`github.com/AOS-Agent/aos`). Nothing
on the Mac mini ever fetches from upstream: `check-update` reads only this fork's
`origin`, and the nightly `auto-update` / `harness-update` crons are disabled
(see HARDENING.md). Upstream changes reach the machine only when you review them
here, merge them, push to the fork, and then run `aos update` on the Mac mini.

## The automatic part: a weekly sync PR

`.github/workflows/upstream-sync.yaml` runs every Monday (or on demand:
Actions → Upstream sync → Run workflow). If upstream has new commits it opens
a pull request merging them into `main`. **It never merges anything.** The
PR body is the report from `.github/scripts/upstream-report.sh`:
- the new commits and changed files;
- flagged lines: permission bypasses, update crons or new scheduled jobs,
  blanket permissions, macOS security settings, new network destinations or
  downloads, the upstream repo address coming back, Telegram/inbound auth
  code, and trust logic;
- the sensitive paths touched (migrations, reconcile checks, install.sh,
  the bridge, workflows);
- `uv.lock` and test-suite results on the merged tree.

Upstream's code (the tests) runs in a job that has only a read-only token
and saves no credentials, so it can't push. The job that opens the PR runs
only git and gh. If the merge conflicts, or the push is refused because
upstream changed `.github/workflows`, you get an issue instead. Then merge
by hand as below.

One-time setting: Settings → Actions → General → "Allow GitHub Actions to
create and approve pull requests".

**Your part:** read the PR (the ⚠️ sections first), merge it, then on the
Mac mini either run `aos update` or tap **Apply update** on the Telegram
notification. You can also paste the PR link to Claude and ask it to check
the PR against HARDENING.md.

## By hand

Do this on a working copy (your laptop, or `~/project/aos-founder`), never in
`~/aos` on the Mac mini.

### One-time setup

```bash
git clone https://github.com/logi348/aos-founder.git
cd aos-founder
git remote add upstream https://github.com/AOS-Agent/aos.git
git remote set-url --push upstream DISABLED   # you never push to upstream
```

### Each time you want to look at upstream

```bash
git fetch upstream
git log --oneline main..upstream/main          # what's new
git diff --stat main...upstream/main           # which files
git diff main...upstream/main -- install.sh bootstrap.sh core/infra/migrations core/infra/reconcile config/crons.yaml
```

Read the diff before merging. The places most likely to undo a hardening change,
and therefore worth reading line by line:

| Path | Why |
|---|---|
| `install.sh`, `bootstrap.sh` | settings.json contents, macOS defaults, sudo, optional installs, repo URLs |
| `core/infra/migrations/` | migrations run automatically on `aos update`; a new one can rewrite settings, plists or config |
| `core/infra/reconcile/checks/` | reconcile "fixes" drift back to whatever the check considers correct (e.g. `hooks.py`, `claude_defaults.py`) |
| `config/crons.yaml` | re-enabled `auto-update` / `harness-update`, new scheduled jobs |
| `core/bin/cli/cld`, any `claude ... --dangerously-skip-permissions` / `bypassPermissions` | permission bypasses |
| `core/services/bridge/` | Telegram auth, the local API, approval flow |
| `config/defaults/*.yaml` | comms scope, trust defaults |
| new `curl`, `requests`, `httpx`, `fetch`, `git clone`, `pip install`, `npm i` | new outbound traffic or runtime downloads (see SECURITY-AUDIT.md) |

A quick tripwire after every fetch:

```bash
git diff main...upstream/main | grep -nE '^\+.*(dangerously-skip-permissions|bypassPermissions|askForPassword|screensharing|AOS-Agent/aos|Bash\(\*\)|remoteControlAtStartup|claudeInChromeDefaultEnabled|break-system-packages|sudo -n true|enabled: true)'
```

### Merging

```bash
git switch main
git switch -c upstream-sync-$(date +%Y%m%d)
git merge upstream/main          # or: git cherry-pick <sha> ... for selected fixes
# resolve conflicts in favour of the hardening (see HARDENING.md for intent)
# re-run the checks:
grep -rnE 'dangerously-skip-permissions|bypassPermissions' --exclude-dir=.git . | grep -v -e HARDENING.md -e UPSTREAM.md -e SECURITY-AUDIT.md -e CHANGELOG.md
uv run pytest -q                  # on a machine where the dev env is installed
git switch main && git merge --ff-only upstream-sync-$(date +%Y%m%d)
git push origin main
```

Upstream's own repository references (`AOS-Agent/aos`) will reappear in merged
files; replace them with `logi348/aos-founder` again before pushing.

## Applying it on the Mac mini

```bash
aos check-update     # shows what is pending from the fork
aos update           # pulls from origin, runs migrations, restarts services
```

The fork is private, so the Mac mini needs GitHub credentials for `git fetch`:
`gh auth login` then `gh auth setup-git` (or a read-only deploy key).
