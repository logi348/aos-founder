# Hardening notes

This fork (`github.com/logi348/aos-hardened`) is AOS with the changes below,
made for an unattended Mac mini reachable over Tailscale. Each numbered section
is one commit on the `hardening` branch (`git log cda5054..hardening`);
`cda5054` is the untouched upstream code. See SECURITY-AUDIT.md for the full
inventory and UPSTREAM.md for pulling in upstream changes.

## Pre-install checklist (Mac mini)

The step-by-step version is in **SETUP.md**.

These are setup choices, not code, and they matter as much as the code.

1. **Two macOS accounts.** Create an admin account for installs and system
   changes, and a **standard (non-admin) account that AOS runs in**. Log in
   as the standard user for day-to-day running. Even if an agent got past
   every guardrail, it can't change the system. Install steps that need
   admin rights ask for the admin password.
2. **Read-only GitHub access on the Mac.** If the Mac's GitHub login could
   push, an agent could push code to `main` and the next update would deploy
   it, which would bypass your review. On github.com, create a fine-grained
   personal access token: repository `logi348/aos-hardened` only,
   **Contents: Read-only**, expiry of your choice. On the Mac:
   `gh auth login --with-token < token.txt && gh auth setup-git`, then delete
   `token.txt`. Also turn on 2FA on your GitHub account and branch protection
   on `main` (require a pull request).
3. **Remote access.**
   - Tailscale access rules so only your own devices can reach the Mac.
   - SSH with keys only (`PasswordAuthentication no`), or Tailscale SSH.
   - No port forwarding on your router.
   - Leave the optional mesh feature off.
4. **Keep personal accounts off the machine.** Use the dedicated email.
   Don't sync personal iCloud data to it, and don't add your password
   manager or a browser profile with your logins. Your personal Telegram
   stays on your phone.
5. **FileVault on.** Accept that after a power cut you unlock it once, or add
   a small UPS so that's rare.
6. **Install.** Install from the fork (now on `main`):
   `gh repo clone logi348/aos-hardened ~/aos && bash ~/aos/install.sh --always-on`.
   - `--always-on` keeps the Mac awake and restarts it after a power cut. It
     doesn't touch the screen lock.
   - Other flags are off by default: `--with-superwhisper`, `--with-obsidian`,
     `--with-theming`, `--with-ytdlp-pot`.
   - A reconcile check resets `~/aos` to the fork's `main` every 30 minutes,
     so never keep changes in `~/aos`. Change the fork instead.
7. **First week:**
   - Run `aos telegram-pair` and `approval-smoke-test` (§6b).
   - Run the real tests (§10).
   - Watch `~/.aos/logs/approval-mcp.log` and `~/.aos/logs/bridge.log`.
   - Optionally try `aos claude-features enable sandbox` (§2).
   - Raise individual agents to 3 only once the trust log shows they've
     earned it.
8. **Backups.** Turn on Time Machine. Keep `~/vault` in its own private git
   repo.
9. **GitHub setting for the weekly upstream PR.** Settings → Actions →
   General → "Allow GitHub Actions to create and approve pull requests".

---

## 1. Updates under your control

**What changed**
- Every upstream reference now points at the fork. Files changed:
  - `README.md`, `bootstrap.sh`, `install.sh`
  - `core/bin/cli/aos-report` (its issues go to the fork)
  - `core/engine/work/backend.py` (GitHub task sync goes to the fork)
  - `core/infra/migrations/137_repo_url_aos_agent.py` (old pre-rename remotes are redirected to the fork, not upstream)
  - `docs/releases/0.7.9.md`
  - tests: `test_aos_report_2323_gh_repo.py`, `test_aos_report_2338_queue_drain.py`, `test_aos_report_2349_scrub.py`, `test_migration_137_idempotency.py`
  - the old `install.hish.am` instructions are replaced by a clone command.
- `bootstrap.sh` can fetch the private fork with `GITHUB_TOKEN` or a logged-in `gh`.
- `config/crons.yaml`: `auto-update` and `harness-update` are `enabled: false`. `check-update` (notify only) stays.
- `check-update` fetches only from `origin`, never "the first remote".
- settings.json gets `DISABLE_AUTOUPDATER=1`, so Claude Code itself only updates when you run `claude update`.

**Why.** Upstream pulled and executed new code at 04:00 every day with no
signature check, and updated Claude Code unpinned at 04:15.

**Applying updates with your approval:**
- **Weekly upstream PR.** `.github/workflows/upstream-sync.yaml` opens a PR
  when `AOS-Agent/aos` has new commits. It includes a risk report and test
  results on the merged tree, and never merges anything itself. You review
  and merge. Details are in UPSTREAM.md.
- **Telegram offer.** `check-update` (every 2 h) messages you once per new
  fork version, with **Apply update** / **Later** buttons. Upstream only
  wrote a state file. The button works only for your account and only if
  that exact version is still pending. `aos update` in a terminal does the
  same.
- **Agents.** Agents can check for updates; applying (`aos update`,
  `check-update --apply`, `aos channel <x>`) is an "ask".

**Re-enable automatic updates.** Set `enabled: true` on either cron in
`config/crons.yaml`; remove `DISABLE_AUTOUPDATER` from `~/.claude/settings.json` `env`.

## 2. Agent permissions

**What changed**
- `cld` runs without `--dangerously-skip-permissions`. `cld-unsafe` keeps the flag and prints a warning first.
- `core/infra/lib/claude_permissions.py` is the single permission set. `install.sh` applies it, and the `settings_config` reconcile check enforces it (upstream's check re-added blanket `Bash`/`Read`/`Edit`/`Write` allows on every pass).
  - **allow:** `Bash`, `Glob`, `Grep`, `WebSearch`, `WebFetch`, `Agent`, `Task`, `TodoWrite`, `Skill`; `Read(…/**)` for `~/aos`, `~/.aos`, `~/vault`, `~/project`, `/tmp`; `Edit(…/**)` for `~/.aos`, `~/vault`, `~/project`, `/tmp`. Claude Code applies Edit rules to Write too.
  - **ask:** `Edit(~/.aos/config/**)`: comms allowlist, account trust, operator profile, converse defaults.
  - **deny:**
    - Read/Edit of `~/.ssh`, `~/Library/Keychains`, `~/Library/Cookies` and the Safari, Chrome, Chromium, Brave, Edge, Arc and Firefox profile folders;
    - `sudo`, `security`, `curl|sh`, `curl|bash`, `wget|sh`, `wget|bash`;
    - `rm -rf` of `/`, `~` or `$HOME`;
    - Edit of the operator-only files (§5);
    - **self-modification:** Edit of `~/aos` (the running framework: agent and skill instructions, hooks, the guard, this module, `crons.yaml`), LaunchAgents/Daemons and shell startup files.
- `core/hooks/guard_bash.py`, a PreToolUse hook on Bash, registered by install and reconcile. Permission rules match command text and are easy to get around, so the guard parses each command instead. It blocks:
  - `sudo` in any spelling;
  - the `security` CLI (`agent-secret` still works);
  - downloads piped or substituted into a shell or interpreter;
  - recursive `rm` of anything outside the AOS dirs and temp dirs (unresolvable targets like `"$DIR"` get "ask");
  - any mention of the secret folders above;
  - writes to operator-only files;
  - **any write into `~/aos`, `~/.claude`, `~/.claude.json`, LaunchAgents/Daemons or shell startup files.** That covers redirects, cp/mv/tee/ln/chmod, `sed -i`, git write commands, `cd` then write, and inline Python that writes there. Running and reading code in `~/aos` is fine;
  - crontab edits, `launchctl submit`, and loading any plist other than an existing `com.aos.*` one;
  - **other devices on your network:**
    - any command naming a private, link-local or Tailscale address (`192.168.x`, `10.x`, `172.16–31.x`, `169.254.x`, `100.64–127.x`, IPv6 ULA/link-local) or a LAN hostname (`.local`, `.lan`, `.home`, `.home.arpa`, `.internal`, `.ts.net`);
    - discovery and file-share tools (`nmap`, `dns-sd`, `smbutil`, `upnpc`, …).
    - `localhost` stays allowed.
    - To let agents reach one device (say a printer), add its IP, CIDR or hostname to `~/.aos/config/lan-allow`. Only you can edit that file.
  - writes into `~/.aos/config` and applying updates get "ask".

  Hooks run in every mode, including `cld-unsafe`.
- **Agents can't give themselves more.** Their instructions, the guard, the permission set, the job schedule and anything that starts at login are off-limits. Framework changes go `~/project/aos` → the fork → your merge → update.
- **30-minute repair.** The `settings_config`, `claude_defaults` and `runtime_protection` reconcile checks now repair on the 30-minute periodic run, not only on deploy. Anything that slips past the rules (say, a script run from `/tmp`) is undone within half an hour: permissions, the guard hook and the feature flags are restored, and `~/aos` is reset to the fork's `main`.
- **Opt-in macOS sandbox.** `aos claude-features enable sandbox` turns on Claude Code's sandbox for shell commands. macOS itself enforces it, so even a script an agent writes and runs can't write to `~/aos`, `~/.aos/config` or LaunchAgents, or read SSH keys, keychains or browser data.
  - Network is limited to the domains AOS uses.
  - `aos`, `agent-secret`, `launchctl`, `brew`, `gh`, `open`, `tailscale` and git network commands run outside it, as Claude Code documents.
  - It's off until you've tried it on the Mac mini, because Keychain and Homebrew behaviour inside it is undocumented. If shell commands start failing, `aos claude-features disable sandbox`.
- The trust dialog is pre-accepted for `~/aos` only, not your home directory.
- `remoteControlAtStartup` and `claudeInChromeDefaultEnabled` default to off. Upstream's undocumented `"chrome": true` key is no longer written.
- Every other place that bypassed permissions:

  | Where | Upstream | Now |
  |---|---|---|
  | `core/bin/cli/cld` | `--dangerously-skip-permissions` | none (`cld-unsafe` keeps it) |
  | `core/bin/crons/memory-curate` | bypass + allowedTools | `--permission-mode dontAsk --tools/--allowedTools Read,Grep,Glob,Bash` |
  | `core/engine/comms/envoy/runner.py` | bypass + `--allowedTools ""` (which restricted nothing) | `dontAsk --tools ""`: no tools at all |
  | `core/engine/comms/sentinel/spawner.py` | bypass | `dontAsk` + its tool list |
  | `core/engine/comms/converse/turn.py` | bypass | `dontAsk` + each profile's list; the "none" profile gets `--tools ""` |
  | `core/services/bridge/persistent_session.py`, `session_manager.py` ×2 | `bypassPermissions`, cwd `~` | phone approval (§6b), cwd `~/.aos/work` |

**What `dontAsk` means for crons.** A tool call outside the job's list is
refused immediately instead of waiting for a prompt nobody answers. Each job
keeps the tools it was designed to use.

**Re-enable / opt in**
- `cld-unsafe` for a supervised session without checks.
- `aos claude-features enable remote-control` or `aos claude-features enable chrome`. Either asks you to type a code at a terminal; `disable` never asks.
- For one session only: `claude --remote-control` / `/remote-control`, `claude --chrome` / `/chrome`.
- To widen permissions, edit `ALLOW`/`DENY` in `core/infra/lib/claude_permissions.py`, not the live settings.json; reconcile would restore the module's version.

## 3. macOS settings

- `askForPassword -int 0` is gone; your screen-lock setting is untouched.
- Screen Sharing is never enabled by script. The installer prints how to turn it on and says to use it only over Tailscale.
- No sleep, disk sleep, Wake on LAN, autorestart, `AutoBoot` and auto-logout are applied only with `install.sh --always-on`. That flag also writes `~/.aos/config/always-on`, which turns on the autorestart reconcile reminder.
- Health check: auto-login is never required. An informational line explains that auto-login and FileVault are mutually exclusive.
- The onboarding skill no longer pushes auto-login or runs `sudo` to start SSH or Screen Sharing. It explains the FileVault trade-off and walks you through System Settings; you run the two Tailscale `sudo` commands yourself.

**Re-enable.** `bash ~/aos/install.sh --always-on`, or run the `pmset` commands
it prints. Turn on Screen Sharing in System Settings → General → Sharing.

## 4. Messaging defaults

- `config/defaults/comms.yaml`: iMessage is `access: allowlist`, `allowed: []`, `include_groups: false`. Migration 136's inline copy matches.
- **Extra (approved):** a missing, broken or unknown config now fails closed to an empty allowlist; only an explicit `access: all` opens everything. The people-intel iMessage reader (`apple_messages.py`) used to read every conversation with no scope check; it now goes through the same gate.
- **Report: the other channels have no equivalent setting.**
  - WhatsApp (whatsmeow bridge + `whatsapp.py`), Gmail ingest, Apple Mail and the Telegram ingest read everything their credentials can reach.
  - Slack is limited to one user via `SLACK_ALLOWED_USER_ID`.
  - Don't connect WhatsApp or email until you want the system reading them; their crons and arms are off by default (migrations 112/127).

**Re-enable.** List contacts under `imessage.allowed:` in
`~/.aos/config/comms.yaml`, or set `access: all`.

## 5. Trust

- **Defaults:**
  - **Agents: level 2 (SEMI-AUTO).** They act when confident and ask otherwise. Financial commitments, contacting new people, deleting production data and changing goals always escalate.
  - **Messaging other people: level 0.** Texts and emails to contacts are drafted, never sent on their own.
  - Set in `config/defaults/trust.yaml` (`defaults.agent_level: 2`, `comms_level: 0`) and the `operator.yaml` scaffold.
  - Chief's instructions say an agent or capability with no entry uses these defaults. Upstream left that undefined, and at level 0 Chief would not hand work to agents at all.
  - Onboarding offers Copilot (2) as the default.
- **Finding: upstream did not enforce human approval in code.**
  - `requires_human_approval: true` was never read.
  - `trust-review promote`, the comms graduation `runner.py confirm … accept` and `converse create --trust 3` applied immediately, and any agent with Bash could run them or edit `trust.yaml`.
  - Nothing auto-promoted; only demotions were automatic.
- **Extra (approved): the gate** (`core/infra/lib/human_gate.py`). Raising trust refuses unless it is run outside a Claude Code session, from a real terminal, and you type back a random code.
  - Gated: `aos trust promote`, graduation `confirm … accept` from the CLI, `converse create` at trust 3, and `aos claude-features enable`.
  - The Telegram `/approve` path is already limited to your chat.
  - Agents may read but not write `trust.yaml`, `claude-features.json`, `always-on` and `bridge-permission-mode` (deny rules + guard).
  - Lowering trust is never gated.
- Converse sessions still default to trust 2 (`config/defaults/converse.yaml`, semi-auto with review) — unchanged.

**Change trust.** In your own Terminal: `aos trust promote <agent> [capability] --to N`
(asks you to confirm) or `aos trust demote …` (never gated).

## 6. Telegram

**6a. Bridge auth.** Upstream checked the chat ID on every handler, but not
the sender, so every member of the forum group was fully authorized,
including for inline-button presses. Now one gate handler (group −1) runs
before all others and drops any update that isn't from an authorized chat
and from your own account. That covers text, voice, media, commands,
callbacks, edits and future update types. Your account is the private chat
id, or `TELEGRAM_USER_ID` if the chat is a group. Bots, channel posts and
callbacks without a message are rejected. The error handler no longer
replies to strangers. Tests: `core/services/bridge/tests/test_auth_gate.py`.

**Onboarding.**
1. You create the bot with @BotFather on your phone.
2. You store the token at a hidden prompt: `agent-secret set TELEGRAM_BOT_TOKEN`.
3. You run `aos telegram-pair`. It accepts only a *private* message
   containing a one-time code from the @username you typed, shows who it
   found, and asks you to confirm before storing `TELEGRAM_CHAT_ID` and
   `TELEGRAM_USER_ID`.

No more logging into your Telegram in Chrome or taking "whoever messaged the
bot last". Tests: `tests/test_telegram_pair.py`.

**6b. Extra (approved): phone approval.** Bridge Claude sessions run in
`default` mode with `--permission-prompt-tool mcp__aos_approval__approve`:
- Anything the allow list covers runs as before.
- Deny rules and the guard still refuse.
- Anything else arrives on your phone with **Allow / Deny**. No answer in
  5 minutes means deny.
- The chain is `approval_mcp.py` → `POST /approval` on the bridge's local API → `approvals.py` → Telegram.
- **Unverified:** Claude Code's public docs don't specify the prompt tool's
  exact wire format. The server accepts the likely argument names, denies
  anything malformed, and logs argument *names* to `~/.aos/logs/approval-mcp.log`.
  Run `approval-smoke-test` once on the Mac mini: it asks Claude to write
  `~/Desktop/aos-approval-test.txt`, and your phone should get a prompt.
- Bridge sessions start in `~/.aos/work`.
- **Fallback.** Write `dontAsk` (refuse instead of asking) or `bypass`
  (upstream behaviour) to `~/.aos/config/bridge-permission-mode`, then
  `aos deploy bridge`.

**6c. Extra (approved): local APIs.**
- **Bridge API (`127.0.0.1:4098`).** Upstream had no auth and
  `Access-Control-Allow-Origin: *`, so a web page open on the Mac could likely
  drive Claude through `/send`. Now:
  - the Host header is checked;
  - browser (Origin) requests are refused;
  - there are no CORS headers;
  - a bearer token from `~/.aos/services/bridge/api.token` (0600) is required
    for everything except `GET /health`.
- **WhatsApp bridge (`127.0.0.1:7601`).** Host and Origin checks, no CORS,
  JSON-only POSTs. The pairing QR is rendered on the server instead of by an
  unpinned CDN script that could have read the code linking a device to your
  WhatsApp. This Go code was not compiled here (modules not cached offline);
  `aos deploy whatsmeow` will compile it.

## 7. Installer

- Off unless flagged: SuperWhisper (`--with-superwhisper`), Obsidian (`--with-obsidian`), Dock/wallpaper/Terminal theming (`--with-theming`), and the yt-dlp PO-token plugin + bgutil clone (`--with-ytdlp-pot`). yt-dlp itself is still installed.
- **Dropped:** both `pip3 install --break-system-packages` steps (youtube-transcript-api; surya-ocr, imagehash, transformers). Only the optional `apps/content-engine` uses them, and it already skips those features without them. Adding them to the locked uv environment needs a network `uv lock`.

  **Content-engine extras, if you want them:**
  ```bash
  uv venv ~/.aos/venvs/content && uv pip install --python ~/.aos/venvs/content youtube-transcript-api surya-ocr imagehash "transformers>=4.40,<5"
  cd ~/aos/apps/content-engine && ~/.aos/venvs/content/bin/python cli.py "<url>"
  ```
- The background `sudo -n true` keep-alive and the up-front `sudo true` are gone. `_need_sudo` asks for your password right before Command Line Tools, Homebrew and `--always-on`.

## 8. Audit

See SECURITY-AUDIT.md. No code changes in that commit.

## 9. Neutral voice

- The installer glyphs (byte-escaped) are removed and the closing line is "Setup complete."
- Onboarding, morning prompts, the bridge's greeting reply and several skills use neutral greetings.
- The onboarding persona is **Skye**.
- Example names are now "Alex"; the upstream author's real email addresses in `account-resolve` are replaced.
- Example data uses same-shape substitutions so tests keep their meaning.
- The Arabic Whisper priming prompt is a neutral Arabic phrase.

**Removed features:**
- **Prayer times:** `morning-context`'s daily call to `api.aladhan.com`, which sent your city; `AOS_PRAYER_METHOD`; the `prayer_times` output; the `prayer` operator.yaml key; the related test fixtures.
- **Hijri dates:** the `hijri_date` note frontmatter, the `hijri-converter` dependency (pyproject + uv.lock, hand-edited offline: run `uv lock --check` once online), the CI import check and migration 096's import list.
- **The upstream author's personal Adhan/SuperWhisper LaunchAgent labels** in `config/modules.yaml`.

**Kept, because they are functional:**
- name-transliteration tables;
- the recogniser for *inbound* phrases;
- "religious" group-category keywords;
- Arabic-script handling;
- migration 137's old repo path;
- the `am.hish.*` bundle IDs used by cleanup migrations;
- the `islah` bug-intake subsystem name and the `nuchay` project name (both stored identifiers).

`CHANGELOG.md` and `docs/releases/` are left as history; nothing shows them at runtime.

## 10. Tests

PyYAML, rapidfuzz, python-telegram-bot and pytest aren't installed on this
machine, and installing them needs the network, so the full suite could not
run. Instead:
- Every test file was run with a fixture-light pytest stand-in on the stdlib Python 3.14. The identical harness was run on the untouched upstream commit for comparison.
  - **Upstream:** 519 passed, 57 failed, 680 skipped.
  - **This fork:** 583 passed, 58 failed, 685 skipped.
  - About 72 files couldn't import in either run (yaml/rapidfuzz).
- The 57 failures are the same tests in both runs: missing dependencies or fixtures the stand-in lacks.
- The one extra is `test_human_gate.py::test_trust_review_promote_refused_without_terminal`, which needs PyYAML. The same check passed by hand: `trust-review promote` exits 3 without a terminal.
- New tests written and passing here: the guard (including the self-modification and update cases), permission set, claude-features (including the sandbox), human gate, telegram-pair, bridge API auth, approvals, the Apply-update button, converse command shape and the reconcile checks.
- GitHub's CI (`.github/workflows/ci.yaml`) runs the full suite with real dependencies on every push to `main`.
- New or changed tests that need the real environment: bridge auth gate, comms scope/send, migration 136, validate, project layer, people-intel/hygiene.
- **Run the real suite once on the Mac mini:**
  ```bash
  cd ~/aos && uv run --group dev pytest -q
  ~/.aos/services/bridge/.venv/bin/python -m pytest core/services/bridge/tests -q
  ```

## Everyday use + overnight "advance"

AOS should be effortless to use during the day and keep ideas moving at night.

- **Telegram conversations get a compact Chief brief.**
  (`core/services/bridge/chief_brief.py`)
  - Upstream's Telegram sessions skipped Chief's agent file, and with it the
    skill routing. Now they get the essentials:
    - infer intent, and never ask you to fill in structure;
    - use the right skill (ramble, capture, the initiative pipeline,
      council, step-by-step, recall, verification-before-completion);
    - make sure every idea lands in the work system so it can be advanced.
- **Overnight advance pass.** (`core/bin/crons/advance`, 02:30)
  - Chief runs headless in `dontAsk` mode under the normal rules and the
    guard, with an extra deny list for anything outward-facing.
  - It picks up to 3 open items (tasks, inbox, initiatives, quick captures)
    and takes the next *reversible* step on each: research, critique, a plan,
    a draft, or a prototype on a new git branch in `~/project`.
  - Outputs go to `~/vault/advance/<date>/`. Progress is recorded on each
    task's activity and handoff.
  - It never messages anyone, publishes, pushes, spends, deletes, closes
    tasks, or changes goals or settings. It prepares those and lists them
    under "needs you".
- **Morning briefing → "While you slept".** It lists what moved, what needs
  you, and what was parked, with a link to the full report.
- **To turn it off:** set `enabled: false` on `advance` in
  `config/crons.yaml` (through the fork). To preview what it would see, run
  `python3 ~/aos/core/bin/crons/advance --dry-run`.

## Known remaining risks

- **Bash is still broadly allowed.** Until you enable the sandbox,
  confinement is text matching (the guard) plus the 30-minute repair. That
  stops accidents and casual prompt injection, not a determined attacker
  who controls Claude's input. The real wall is the opt-in sandbox (§2) plus
  the non-admin account (checklist).
- **No signature verification on updates.** `aos update` and the Apply
  button trust whatever is on the fork's `main`. Use a read-only token on
  the Mac, 2FA and branch protection on GitHub, and review the sync PRs
  (UPSTREAM.md).
- **Secrets.** Any process running as you can read every `aos.*` Keychain
  item (no ACLs). `agent-secret set NAME VALUE` puts the value briefly in
  `ps`; use the prompt form. Google refresh tokens and an optional
  OpenRouter key live in 0600 files.
- **Voice notes go to OpenRouter by default.** Set `TRANSCRIBER_BACKEND=local`
  in the transcriber's LaunchAgent to keep audio on the Mac (needs the
  mlx-whisper model download).
- **Optional mesh feature.** meshd binds `0.0.0.0:4100` with no auth, and
  `aos mesh init` writes Headscale on `0.0.0.0` over HTTP plus a reusable
  30-day key in plaintext. Leave mesh off.
- **Reconcile still runs `npm i -g dev-browser` unpinned, and resets `~/aos`
  to `origin/main`.**
- **Phone approval is unverified against your Claude Code version** (§6b).
  The fallback mode file is there if it misbehaves.
- **Shared home network.** Until the Mac mini is on a guest network or VLAN:
  - On the router, turn off UPnP, change the default admin password and turn off WPS.
  - On the Mac, turn on the firewall with stealth mode, and turn off AirPlay Receiver and the other sharing services.
  - The guard's LAN block is text matching: a script an agent writes and runs could still reach the network. The sandbox's domain allowlist is what actually closes that, so turn it on early.
- **Prompt injection through messaging.** Anything that reads email, iMessage
  or web content into a Claude session can try to steer it. The allowlist,
  the trust level 0 default and phone approvals limit the blast radius. They
  don't remove the risk.
