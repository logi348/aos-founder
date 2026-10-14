# Security audit

An inventory of outbound network destinations, LaunchAgents, listening ports,
secret handling and runtime code execution in AOS. It was done by reading and
grepping the code; nothing was executed.

**Baseline.** File and line references are to the **upstream** code, commit
`cda5054` (the first commit on this repository; `git show cda5054:<path>`),
so they stay stable while this fork changes. The table below says what the
`hardening` branch changed. Scope: everything except `tests/`, `CHANGELOG.md`
and `.git`. `vendor/` is empty. Qareen, n8n, eventd and listen are no longer
in the tree (migrations 108/109); migrations that mention them are listed
where it matters.

## Highest-risk findings and their status in this fork

| # | Severity | Finding (upstream) | Status in this fork |
|---|---|---|---|
| H1 | Critical | Bridge API `127.0.0.1:4098`: no auth, `Access-Control-Allow-Origin: *`. `POST /send` drives a Claude session running with `bypassPermissions` in `$HOME`, so any web page open on the Mac could likely make it run things. `/history` and `/stream` were readable cross-origin. | **Fixed.** Host check, browser (Origin) requests refused, no CORS, bearer token from `~/.aos/services/bridge/api.token` (0600) on everything except `GET /health`. Bridge Claude sessions no longer bypass permissions (phone approval, cwd `~/.aos/work`). |
| H2 | High | Unattended 04:00 `auto-update` fetches from GitHub with no signature check, then executes the new code (migrations, reconcile fixes, `uv pip install`, `npm ci`/`build`). | **Disabled** (`enabled: false`). Updates come only from your fork's `origin` and only when you run `aos update` (see UPSTREAM.md). There is still no signature check, so protect the fork (2FA, branch protection). |
| H3 | High | `harness-update` runs `npm update -g @anthropic-ai/claude-code` daily, unpinned. | **Disabled.** Claude Code's own auto-updater is off via `DISABLE_AUTOUPDATER=1` in settings.json. |
| H4 | High | meshd binds `0.0.0.0:4100` with no auth (its docstring says otherwise). | **Unchanged.** It is optional, has no plist and is started by hand. Don't run it, or run it only behind Tailscale ACLs. Listed under remaining risks in HARDENING.md. |
| H5 | High | The installer enabled Screen Sharing (VNC, all interfaces), disabled the screen-lock password and auto-logout, and set Wake-on-LAN, whenever sudo was cached, which it always was (up-front `sudo true` plus a keep-alive loop). | **Fixed.** Screen lock untouched; Screen Sharing only printed as instructions; power settings behind `--always-on`; no keep-alive loop. |
| H6 | Medium | `aos mesh init` writes Headscale on `0.0.0.0:8080` over plain HTTP, STUN on `0.0.0.0:3478`, and a reusable 30-day pre-auth key in plaintext (whose text claims "24 hours"). | **Unchanged** (optional mesh feature). |
| H7 | Medium | Migration 080 once wrote `AOS_QAREEN_HOST=0.0.0.0`; 095 reverts it, but rolls back to the exposed plist if Qareen fails to restart. | **Moot on a fresh install** (Qareen is removed). 080 now fails on a machine below it because its template is gone; a fresh install isn't below it. |
| H8 | Medium | WhatsApp bridge `127.0.0.1:7601`: no auth, `/send` accepts any Content-Type (CSRF from a web page), and the `/qr` page loads an unpinned CDN script. | **Fixed.** Host/Origin checks, no CORS, JSON-only POSTs; QR rendered on the server with a strict CSP. (Go code not compiled here; the modules aren't cached offline.) |
| H9 | Medium | The transcriber's default backend is `cloud`: voice notes go to openrouter.ai. | **Unchanged.** Set `TRANSCRIBER_BACKEND=local` to keep audio on the Mac (see HARDENING.md). |
| H10 | Medium | Reconcile `fix()` runs `npm i -g dev-browser` (unpinned) and `git reset --hard origin/main` / `git clean -fd` in `~/aos`. | **Unchanged.** The reset now targets your fork. Never keep local commits in `~/aos`; merge into the fork's `main` instead. |
| — | High | Telegram auth was per chat, not per user: every member of the forum group was authorized. Onboarding stored the chat of whoever last messaged the bot. | **Fixed.** Owner-only gate on every update; manual pairing with a one-time code and @username check. |
| — | High | Every `claude` launched by `cld`, crons and the bridge used `--dangerously-skip-permissions` / `bypassPermissions`. settings.json allowed `Bash(*)`, `Read(*)`, `Write(*)`, `Edit(*)`, and reconcile re-added blanket allows. | **Fixed.** See HARDENING.md §2: scoped allows, deny rules, Bash guard hook, dontAsk for headless jobs, phone approval for the bridge, `cld-unsafe` only by explicit choice. |
| — | Medium | iMessage scope defaulted to `all` and failed open when comms.yaml was missing; people-intel read chat.db with no scope check. | **Fixed.** Empty allowlist by default, fail closed, people-intel goes through the gate. |
| — | Medium | `morning-context` sent your city to api.aladhan.com daily. | **Removed** (item 9). |

Secondary notes from the same pass:
- `core/bin/cli/mesh` (send) interpolates `$message` into `python3 -c`, so a `'` in a message is an injection. Optional feature; unchanged.
- `agent-secret set NAME VALUE` passes the value on argv (briefly visible in `ps`), and Keychain items have no `-T` ACL, so any process running as you can read any `aos.*` secret. Onboarding now uses the hidden prompt for the bot token. The rest is unchanged.
- install.sh deploys `com.aos.sentinel` (KeepAlive iMessage reader) as infrastructure; migration 112 boots it out afterwards.
- watchdog still posts to the retired `listen` service on :7600.

---

## 1. Outbound network destinations

Legend: **RT** = runtime (services/crons/CLIs). **INST** = install-time or migration (one-off). **SETUP** = an integration setup or skill script run by the operator.

### Installer / bootstrap
| file:line | destination | purpose | when |
|---|---|---|---|
| bootstrap.sh:20,31 | codeload.github.com/AOS-Agent/aos (tar.gz main) | download repo tarball, then `exec install.sh` | INST |
| install.sh:59,1184 | github.com/AOS-Agent/aos.git | `git clone --branch $AOS_BRANCH` | INST |
| install.sh:105 | brew.sh | connectivity probe | INST |
| install.sh:431 | raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | **curl \| bash** Homebrew installer | INST |
| install.sh:1020 | claude.ai/install.sh | **curl \| sh** Claude Code installer | INST |
| install.sh:952 | github.com/Brainicism/bgutil-ytdlp-pot-provider.git | git clone yt-dlp PO-token plugin | INST |
| install.sh:942,964,976 | PyPI | `pip install bgutil-ytdlp-pot-provider`, `pip3 install --break-system-packages youtube-transcript-api`, `surya-ocr imagehash transformers` | INST |
| install.sh:500 | PyPI (uv.lock) | `uv sync --frozen` core env | INST |
| install.sh:1747 | PyPI | per-service `uv pip install -r` | INST |
| install.sh:520,536,706,734,795,843,853,907,919,929,1071 | Homebrew (formulae/casks) | uv, bun, gh, cmux, google-chrome, obsidian, superwhisper, jq, ffmpeg, yt-dlp, tailscale | INST |
| install.sh:555 | npm registry (via bun) | `bun install -g @tobilu/qmd` | INST |
| install.sh:588-665 | Apple softwareupdate | Xcode CLT install | INST |

### Migrations (run at install and on every auto-update, `core/infra/migrations/`)
| file:line | destination | purpose | when |
|---|---|---|---|
| 017_bridge_topics.py:34,56-63 | api.telegram.org | create forum topics | INST |
| 019_transcriber_service.py:48-75 | PyPI | uv venv + `uv pip install` | INST |
| 054_qareen_service.py:~100-111 | PyPI | qareen pip install (code now absent) | INST |
| 056_n8n_service.py:137 | npm registry | `npm install -g n8n` (template now removed by 109) | INST |
| 057_crawler_service.py:48,113-126 | PyPI + Playwright CDN | crawl4ai install + Chromium download | INST |
| 086_rebuild_release_frontends.py:94-102 | npm registry | `npm ci` + `npm run build` | INST |
| 095_loopback_bind_hardening.py:129-136 | api.telegram.org | notify operator | INST |
| 096_uv_managed_python.py:198-205 | python-build-standalone (uv) + PyPI | `uv python install`, `uv sync` | INST |
| 097_cmux_is_the_terminal.py:88 | Homebrew | `brew install --cask cmux` | INST |

### Update / maintenance crons (scheduler, `config/crons.yaml`)
| file:line | destination | purpose | when |
|---|---|---|---|
| core/bin/crons/check-update:98-101,370-376,474,566 | github.com/AOS-Agent/aos (origin) | git fetch main + `stable` tag | RT (every 2h, apply 04:00) |
| core/bin/crons/check-update:859-865 | PyPI | `uv pip install` service venv rebuild | RT (04:00) |
| core/bin/crons/check-update:263 | api.telegram.org | update notifications | RT |
| core/bin/internal/release-manager:135,177-182,471,492 | npm registry; github origin | `npm ci`, git fetch/pull | RT (04:00) |
| core/bin/crons/harness-update:119 | npm registry | `npm update -g @anthropic-ai/claude-code` | RT (04:15) |
| core/bin/crons/watchdog:162,168 | 1.1.1.1, www.google.com | internet probe | RT (5m) |
| core/bin/crons/watchdog:115,149 | 127.0.0.1:7600 + registry health URLs | job post / health | RT |
| core/bin/crons/morning-context:37 | wttr.in | weather | RT (06:30) |
| core/bin/crons/morning-context:75 | api.aladhan.com | prayer times (sends city) | RT (06:30) |
| core/bin/crons/feed-digest:23 → telegram | api.telegram.org | digest | RT |
| core/bin/internal/scheduler:439-446,571-577 | user-configured (`crons.yaml` `ping:` / `~/.aos/config/healthchecks.yaml`) — healthchecks.io | success pings | RT |
| core/infra/reconcile/checks/dev_browser.py:27 | npm registry | `npm i -g dev-browser` | RT (reconcile fix on deploy) |

### Notifications / Telegram (all to `api.telegram.org/bot<token>/…`)
| file:line | purpose | when |
|---|---|---|
| core/infra/lib/notify.py:210,257 | sendMessage | RT |
| core/engine/notify/router.py:484 | sendMessage | RT |
| core/engine/comms/channels/telegram.py:234 | sendMessage | RT |
| core/services/bridge/daily_briefing.py:578,731,789 | sendMessage | RT |
| core/services/bridge/evening_checkin.py:382 | sendMessage | RT |
| core/services/bridge/heartbeat.py:101,301 | getChat/sendMessage | RT |
| core/services/bridge/topic_manager.py:28,208-215 | topic API | RT |
| core/services/bridge/main.py (python-telegram-bot) | long-poll getUpdates | RT (resident) |
| core/bin/cli/aos-report:322 | sendMessage | RT |
| core/infra/integrations/telegram/setup.sh:25; manifest.yaml:49 | getMe | SETUP |

### Comms / content / intelligence
| file:line | destination | purpose | when |
|---|---|---|---|
| core/engine/comms/channels/slack_session.py:100-115 | `https://<workspace>.slack.com/api/*` (from `~/.aos/config/converse.yaml`) | Slack via user session tokens (xoxc/xoxd cookie) | RT (converse, optional) |
| core/services/bridge/main.py:359-361 (slack_bolt) | Slack (Socket Mode) | bridge Slack channel | RT |
| core/engine/comms/channels/gmail_ingest.py:460-462 | oauth2.googleapis.com/token | OAuth refresh | RT |
| core/engine/comms/channels/gmail_ingest.py:481 | Google APIs via `gws` CLI | Gmail ingest | RT |
| core/engine/intelligence/content/backends/fxtwitter.py:33-36 | api.fxtwitter.com | tweet extraction | RT |
| core/services/crawler/crawl_cli.py:50-51 | api.fxtwitter.com + arbitrary URLs (crawl4ai/Playwright) | crawl | RT |
| core/engine/intelligence/ingest/fetcher.py:14,30; runner.py:44 | localhost:1200 (RSSHub) + feed URLs from `feeds.yaml` | feed ingest | RT (30m) |
| apps/content-engine/platforms/youtube.py:57; base.py:20; ocr.py:152; transcribe.py:29,53 | YouTube/Instagram/TikTok/X via yt-dlp + youtube-transcript-api | content extraction | RT |
| core/services/transcriber/cloud.py:37,221-229 | **openrouter.ai/api/v1/audio/transcriptions** | voice transcription (**default backend**) | RT |
| core/services/transcriber/engine.py:29,127 | huggingface.co (mlx-community/whisper-large-v3-turbo) | model download when local backend | RT (first use) |
| core/services/bridge/telegraph_publisher.py:72 (telegraph lib) | telegra.ph / api.telegra.ph | publish long-form | RT |
| core/engine/work/intake/ascbuild.py:55,155,179 | api.appstoreconnect.apple.com + signed download URLs | ASC build intake | RT (cron) |
| core/engine/work/backend.py:435-477; core/bin/cli/aos-report:220,272 | GitHub via `gh` (AOS-Agent/aos) | create/list/close issues | RT |
| core/engine/council/engine.py:153; synthesis.py:62; bridge session_manager.py:535; persistent_session.py:132 | Anthropic via `claude -p` | LLM calls | RT |
| core/services/mesh/heartbeat.py:94-101 | `http://<admin_node>:4100/heartbeat` (plain HTTP over tailnet) | fleet heartbeat | RT (optional) |
| core/bin/cli/mesh:501 | `http://<target_ip>:4100/message` | mesh send | RT (manual) |
| core/skills/new-ios-app/scripts/preflight.sh:93,123 | PyPI; api.appstoreconnect.apple.com | pip install pyjwt; ASC probe | SETUP |
| core/skills/skill-creator/eval-viewer/viewer.html:7-10; assets/eval_review.html; scripts/generate_report.py:39-41 | fonts.googleapis.com, fonts.gstatic.com, cdn.sheetjs.com (SRI present) | static HTML assets | RT (opened in browser) |
| core/services/whatsmeow/main.go:434 | cdn.jsdelivr.net/npm/qrcode@1.5.4 (no SRI) | QR page | RT |
| core/services/whatsmeow (whatsmeow lib) | WhatsApp servers (web.whatsapp.com websocket) | WhatsApp bridge | RT (resident) |
| core/infra/integrations/email/setup.sh:95-110 | imap/smtp gmail, office365, mail.me.com | email setup | SETUP |
| core/infra/integrations/codex/setup.sh:25; manifest.yaml:80 | npm registry | `npm install -g @openai/codex` | SETUP |
| core/infra/integrations/github/setup.sh:23; calendar/google-workspace/obsidian manifests | Homebrew / bun | gh, ical-buddy, googleworkspace-cli, qmd | SETUP |
| core/engine/arms/install.py:203,215 | Homebrew; `aos deploy` → PyPI | module install converge | RT (operator-triggered) |
| core/bin/cli/aos:748-799 | PyPI | `aos deploy` `uv pip install` | RT (manual + update) |

Loopback-only HTTP clients, not outbound: 127.0.0.1:7601 (whatsmeow), :7602 (transcriber), :4098 (bridge), :4097 (eventd, absent), :4100 (mesh), :5678/:4096 (retired), https://127.0.0.1:27124 (Obsidian Local REST, `curl -k`), localhost:1200 (RSSHub).

## 2. LaunchAgents / LaunchDaemons

| label | runs | schedule / KeepAlive | installed from |
|---|---|---|---|
| com.aos.scheduler | `aos-python core/bin/internal/scheduler` (runs all `config/crons.yaml` jobs, incl. **auto-update/harness-update**) | StartCalendarInterval every 5 min, Background | config/launchagents/com.aos.scheduler.plist; install.sh:1771-1773 (INFRA_PLISTS) + 1818-1890; 096_uv_managed_python.py:156-163 |
| com.aos.bridge | `~/.aos/services/bridge/.venv/bin/python core/services/bridge/main.py` (Telegram/Slack + **:4098 API**) | RunAtLoad, **KeepAlive**, Throttle 5 | config/launchagents/com.aos.bridge.plist.template; install.sh:1818 (registry `active`); 012_service_launchagents.py:60-100; scheduler:113-118 (reloads after reboot) |
| com.aos.transcriber | transcriber venv `main.py` (uvicorn 127.0.0.1:7602) | RunAtLoad, KeepAlive, Throttle 5, env `TRANSCRIBER_PORT=7602` | config/launchagents/com.aos.transcriber.plist.template; install.sh:1818; 012; 019 |
| com.aos.sentinel | `aos-python -m core.engine.comms.sentinel.service` (iMessage reader) | RunAtLoad, **KeepAlive**, Interactive | config/launchagents/com.aos.sentinel.plist.template; install.sh:1774 (**always deployed as INFRA**); 012 (globs all templates); 071_sentinel_plist.py:122. Booted out afterwards by 112_comms_arms_default_off.py |
| com.aos.converse | `aos-python -m core.services.converse.main` | RunAtLoad=false, Disabled=true, KeepAlive=false | core/services/converse/com.aos.converse.plist.template; 101_converse_service.py (writes plist, never loads) |
| com.aos.whatsmeow | Go whatsmeow bridge (127.0.0.1:7601) | KeepAlive (manifest) | `plist_template: generated` — rendered by `aos deploy` / arms install (core/engine/arms/install.py:215-244); core/services/whatsmeow/service.yaml |
| com.aos.claude-remote | `core/bin/setup/claude-remote-start` → `echo y \| claude remote-control --spawn worktree\|session --permission-mode default` | n/a (template `com.aos.claude-remote.plist.template` **not in repo**) | install.sh:1080-1101,1775; "configured during onboarding" |
| com.aos.envoy | `python <envoy runner>` | StartInterval 300, RunAtLoad | core/engine/comms/envoy/cli.py:40-58,152 (`cmd_install_daemon`, auto-called by `envoy start`) |
| com.aos.mesh | meshd (0.0.0.0:4100) | KeepAlive (manifest), `plist_template: null` | none in repo, started by hand |
| com.agent.chrome | `open -a "Google Chrome"` | RunAtLoad | install.sh:800-823 (inline heredoc) |
| com.agent.superwhisper | `open -a superwhisper` | RunAtLoad | install.sh:866-889 (inline heredoc) |
| com.apple.screensharing (system **LaunchDaemon**) | macOS Screen Sharing (VNC 5900) | `launchctl load -w` (persistent) | install.sh:2186 |
| com.aos.qareen / qareen-deploy / com.agent.qareen-dev | Qareen dashboard :4096 / :4097 | KeepAlive | historical: 054:146-166, 080:141-177, 095 (rewrites); removed by 108 |
| com.aos.qareen-tunnel | cloudflared tunnel | KeepAlive | historical (TunnelManager); unloaded by 098 |
| n8n LaunchAgent (retired) | n8n :5678 | KeepAlive | historical: 056:184-195; removed by 109 |
| com.aos.listen, com.aos.companion, com.aos.slack-watch, com.aos.memory, com.aos.work-runner, com.aos.dashboard | retired | — | removed by 055/098/109/110/128 |
| com.aos.ios-deploy, com.aos.domain-watch/-catch, com.aos.sana-watch, com.aos.healthsync-deploy | instance-only (no template in repo) | — | referenced in config/modules.yaml:281, 120_retire_dead_mcp_entries_and_orphans.py |

Generic plist writers: core/infra/lib/launchers.py:144-176 (rewrites ProgramArguments to `~/.aos/launchers/<Name>` wrappers), core/infra/lib/service_ctl.py:194, 104_interpreter_resolver.py:113-126, core/bin/cli/aos:977-988 (reload all `com.aos.*`).

## 3. Listening ports

| service | port | bind | file:line | flag |
|---|---|---|---|---|
| Bridge API (aiohttp) | 4098 | 127.0.0.1 | core/services/bridge/api_server.py:30,307 | ⚠ no auth, **CORS \***, `/send` → bypassPermissions Claude (H1) |
| Transcriber (uvicorn) | 7602 (`TRANSCRIBER_PORT`) | 127.0.0.1 (hardcoded) | core/services/transcriber/main.py:31-32,228-231 | ok |
| whatsmeow (Go) | 7601 (`WHATSMEOW_PORT`) | 127.0.0.1 | core/services/whatsmeow/main.go:473-493 | ⚠ no auth, `/send` CSRF-able (H8) |
| **meshd** | 4100 (`MESHD_PORT`) | **0.0.0.0** | core/services/mesh/server.py:235; main.py:145 | 🚩 **non-loopback**, no auth (H4) |
| **Headscale** (config written by `aos mesh init`) | 8080 HTTP; 3478/udp STUN; 9090 metrics | **0.0.0.0:8080, 0.0.0.0:3478**; 127.0.0.1:9090 | core/bin/cli/mesh:126-147 | 🚩 non-loopback, plain HTTP control server (H6) |
| **Screen Sharing** (macOS) | 5900 | all interfaces | install.sh:2186 | 🚩 enabled by the installer (H5) |
| skill-creator eval viewer | random/`--port` | 127.0.0.1 | core/skills/skill-creator/eval-viewer/generate_review.py:443-446 | ok |
| Qareen (retired) | 4096 | `AOS_QAREEN_HOST` env + `--host` arg | see below | historical 🚩 |
| Qareen dev (retired) | 4097 | `host='0.0.0.0'` in a `python -c` arg | 095:168-185 | historical 🚩 |
| n8n (retired) | 5678 | `N8N_LISTEN_ADDRESS`, default `::` | 095:15-19,188-201 | historical 🚩 |
| `tailscale serve` (opt-in) | tailnet 8443 HTTPS → 127.0.0.1:4096 | tailnet | 095:275-342 (only if `AOS_MIGRATION_MAY_CREATE_TAILSCALE_SERVE=1`) | opt-in |
| listen (retired) | 7600 | — | config/services.d/listen.yaml | watchdog still POSTs to it (core/bin/crons/watchdog:115) |
| Third-party, referenced only | 27124 (Obsidian REST, HTTPS self-signed), 1200 (RSSHub), 8081 (operator's Adhan dashboard) | not in this repo | config/capabilities.yaml:28; config/modules.yaml | — |

**Migrations 080 and 095:**
- **080** (`080_remote_access_init.py`) rewrites `~/Library/LaunchAgents/com.aos.qareen.plist` from `config/launchagents/com.aos.qareen.plist.template`. Per the docstring at :14-21, that template set `AOS_QAREEN_HOST=0.0.0.0` (the "LAN/Tailscale bind"). It then bootout/bootstrap/kickstarts. `check()` (:84-98) only tests that the env key is *present*, not its value. Once rebound by Qareen's TunnelManager, the value could be 127.0.0.1. The template is no longer in the repo, so on a fresh install `up()` fails at :141-143 ("Plist template not found"). Because the runner stops on a failed migration, 080 would block every migration after it on a machine whose watermark is below 080. The Qareen code that read `AOS_QAREEN_HOST` is not in the tree.
- **095** (`095_loopback_bind_hardening.py`) is the fix. It sets the Qareen `--host` arg and `AOS_QAREEN_HOST` to `127.0.0.1` (:142-165), dev 4097 `host='0.0.0.0'`→loopback (:168-185), and adds `N8N_LISTEN_ADDRESS=127.0.0.1` (:188-201). It backs up each plist (`.pre-095.bak`) first. **If Qareen fails to restart it rolls back to the exposed 0.0.0.0 plist** (:410-435), notifies over Telegram and returns False, so the exposure stays and the batch stops. The tailscale-serve route is opt-in only (:275-306), and Funnel is never enabled. `check()` (:348-374) verifies the values.
- `core/infra/reconcile/checks/network_binding.py` (:35,78-81,337,427) reports wildcard listeners and `0.0.0.0` in deployed plists. It is report-only, and would flag meshd.
- No code in this tree reads a host env var that could be set to a Tailscale IP. The only env-configurable binds are the port-only `TRANSCRIBER_PORT`, `WHATSMEOW_PORT` and `MESHD_PORT` (mesh is already 0.0.0.0).

## 4. Secrets

Storage is mainly the macOS **login keychain** through `core/bin/cli/agent-secret`: account `aos`, service `aos.<NAME>`, with a fallback to the legacy `agent.keychain`.
Systemic issues:
- `set` passes the value on argv (`security add-generic-password … -w "$VALUE"`, agent-secret:104), so it is briefly visible in `ps`. Callers that pass values on argv: slack_session.py:62, 056:149, integrations/_lib.sh:47.
- Items are created without `-T` ACLs, so any process running as the user can `agent-secret get` any secret.

| file:line | secret | R/W | storage |
|---|---|---|---|
| core/bin/cli/agent-secret:61-75 | all legacy `agent.keychain` items | R (dump-keychain) + W | migrated to login keychain |
| core/bin/cli/agent-secret:83-104,148-161 | any | R/W/delete | login keychain |
| core/services/bridge/main.py:99-110,303-304 | TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID | R | keychain |
| core/services/bridge/main.py:359-361 | SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_ALLOWED_USER_ID | R | keychain |
| core/infra/lib/notify.py:176-178; core/engine/notify/router.py:369,570,608; core/engine/comms/channels/telegram.py:218; core/bin/crons/check-update:259-260; feed-digest:23; aos-report:309-313; 017_bridge_topics.py:209; compile-patterns:53; weekly-digest:46 | TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID | R | keychain (token then goes into the URL path of HTTPS requests) |
| core/services/bridge/telegraph_publisher.py:23 | TELEGRAPH_TOKEN | R | keychain (relative path `bin/agent-secret`, which depends on cwd) |
| core/engine/comms/channels/slack_session.py:48,62,103-104 | SLACK_XOXC, SLACK_XOXD (user session token + `d` cookie) | R/W | keychain |
| core/engine/comms/converse/reauth.py:34-48,71-116 | "Chrome Safe Storage" key → decrypts Chrome `Cookies` DB → SLACK_XOXD | R (keychain + Chrome cookie DB copy) / W keychain | keychain; temp copy of Chrome Cookies |
| core/engine/work/intake/ascbuild.py:114-115 | ASC_ISSUER_ID, ASC_KEY_ID (+ `.p8` key file) | R | keychain + `~/.appstoreconnect/private_keys/AuthKey_*.p8` (plaintext file) |
| core/skills/new-ios-app/scripts/credentials.sh:12-34; preflight.sh:101-103; ios-dev-loop/scripts/ship.sh:60,191-251 | ASC_KEY_ID, ASC_ISSUER_ID, APPLE_ID, APPLE_TEAM_ID; .p8 path | R (exported to env for fastlane/altool) | keychain + .p8 file |
| core/infra/reconcile/checks/google_workspace.py:29-43,86,130; integrations/google-workspace/manifest.yaml:84,132-140; core/bin/internal/gws-account:26 | GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_PRIMARY_EMAIL | R | keychain (exported as `GOOGLE_WORKSPACE_CLI_CLIENT_*` env) |
| core/engine/comms/channels/gmail_ingest.py:13-20,78,456-462,719; 059_gws_cli.py:95-103; 134_google_credentials_hardening.py | Google OAuth **refresh_token** + client_secret | R/W | **plaintext JSON** `~/.aos/config/google/credentials/<email>.json` (0600 since 134; gws rewrites it) |
| core/services/transcriber/cloud.py:43-47,58-80,194 | OPENROUTER key | R | keychain (`openrouter-api`/`api-key`) → env `OPENROUTER_API_KEY` → **plaintext file** `~/.aos/config/openrouter.key` |
| core/infra/migrations/056_n8n_service.py:73,149 | N8N_API_KEY | R/W (generated) | keychain |
| core/infra/integrations/email/manifest.yaml:49,68; email/setup.sh:54 | IMAP_HOST, EMAIL_ADDRESS, EMAIL_PASSWORD (app password) | R/W | keychain (manifest health check interpolates the password into a `python3 -c` command line) |
| config/capabilities.yaml:29 | OBSIDIAN_REST_API_KEY | R | keychain |
| core/infra/integrations/telegram/setup.sh:23; telegram/manifest.yaml:49,76,82 | TELEGRAM_BOT_TOKEN/CHAT_ID | R/W | keychain |
| core/bin/cli/aos-snapshot:94 | arbitrary keys (account=$USER) | R | keychain |
| core/infra/integrations/codex/setup.sh:77; codex/manifest.yaml:51 | OPENAI_API_KEY (env, warned against); `~/.codex/auth.json` | R | env / third-party file |
| core/bin/cli/mesh:252-279 | Headscale **reusable pre-auth key (720h)** | W | **plaintext** `~/.aos/mesh/<name>-invite.txt` |
| core/bin/cli/mesh:128-131 | Headscale private/noise keys | W (by headscale) | `~/.aos/headscale/*.key` |
| core/services/whatsmeow/main.go:58-61,447-450 | WhatsApp device session keys | W | `whatsmeow.db` (sqlite) next to the binary |
| core/bin/setup/generate-connect-script:99,118-168 | SSH host alias config | W | `~/.ssh/config` (0600) |
| core/bin/crons/auto-commit:29 | — | guard | refuses to commit `.env`, `*.pem`, `*.key`, `credentials`, `agent.keychain` |

No `.env`/dotenv loading in runtime code. `.aos-app.env` (new-ios-app scaffold.py:511-517) holds only non-secret app identifiers.

## 5. Runtime download-and-execute

| file:line | what | trigger |
|---|---|---|
| config/crons.yaml `auto-update` → core/bin/crons/check-update:414-647 | git fetch `stable`/main from github.com/AOS-Agent/aos → `git merge --ff-only` or **`git reset --hard`** (git installs) / `release-manager create+activate` (release installs) → **`exec` the newly fetched check-update `--continue`**. No signature verification. | scheduler, daily 04:00 (+ `check-update` status every 2h) |
| core/bin/crons/check-update:984-1010 | phase 2: runs reconcile `run` (fixes) and **`migrations/runner.py migrate`** (imports and runs any new migration Python) | same |
| core/bin/crons/check-update:1016-1020 | `aos sync-skills/agents/rules/mcp` (writes ~/.claude skills/agents/rules; mcp set currently empty) | same |
| core/bin/crons/check-update:817-865 | rebuild changed service venvs: **`uv pip install`** from PyPI (unpinned unless a lock file is present) | same |
| core/bin/internal/release-manager:115-145 | **`npm ci` + `npm run build`** for every tracked package.json whose build uses vite (lifecycle scripts execute) | release creation during auto-update |
| core/bin/internal/release-manager:442-530 | `convert`: `git pull --ff-only origin main` and move the clone | check-update:968 on git installs |
| core/bin/crons/harness-update:116-133 | **`npm update -g @anthropic-ai/claude-code`** (unpinned) | scheduler, daily 04:15 |
| core/infra/reconcile/checks/dev_browser.py:24-27 | **`npm i -g dev-browser`** if missing | reconcile `run` (deploys); not periodic |
| core/infra/reconcile/checks/runtime_protection.py:101-125 | `git checkout -- .`, `git clean -fd`, **`git reset --hard origin/main`** in ~/aos | reconcile `run` |
| core/infra/migrations/056_n8n_service.py:137 | `npm install -g n8n` | migration (pending only) |
| core/infra/migrations/019_transcriber_service.py:48-75; 054:~111; 057:113-126; 096:198-205; 086:94-102; 097:88 | uv venv/pip install, Playwright Chromium download, `uv python install`, npm ci/build, brew cask cmux | migrations (run by auto-update when pending) |
| core/engine/arms/install.py:203,215,236-244 | `brew install <formula>`, `aos deploy <svc>` (pip), write + bootstrap a LaunchAgent | operator `arms` install |
| core/bin/cli/aos:748-799 | `aos deploy`: `uv pip install` service deps | manual + update |
| core/services/transcriber/engine.py:29,127 | mlx-whisper pulls `mlx-community/whisper-large-v3-turbo` from Hugging Face (weights, not code) | first local transcription |
| apps/content-engine/*.py (yt-dlp subprocess) | yt-dlp runs on arbitrary user-supplied URLs; the bgutil plugin is cloned at install | RT on demand |
| core/services/bridge/session_manager.py:535-544,723-732; persistent_session.py:132-138 | `claude -p <message> --permission-mode bypassPermissions` — remote text → code execution by design (Telegram chat-id / Slack user allowlist), **plus the unauthenticated :4098 `/send`** | inbound Telegram/Slack/HTTP |
| core/bin/setup/claude-remote-start:17-20 | `claude remote-control` auto-answering "y", spawn worktree/session (remote session spawning through Anthropic) | LaunchAgent com.aos.claude-remote (if configured at onboarding) |
| bootstrap.sh:31-45; install.sh:431,1020 | curl tarball → exec install.sh; curl \| bash Homebrew; curl \| sh claude.ai installer | install only |
| MCP servers | none fetched via npx/uvx: `aos sync-mcp` `aos_servers = {}` (core/bin/cli/aos:220-270); 059/110/120 only *remove* entries. `uvx ruff` only in core/bin/cli/ship-check:113 (dev tool) | — |

### Secondary observations
- `core/bin/cli/mesh:488-496` interpolates `$message` into `python3 -c "…json.dumps('$message')"`, a shell/Python injection if the message contains `'`.
- install.sh always deploys `com.aos.sentinel` (KeepAlive iMessage reader) as INFRA (:1774), and 012 globs every template. Only migration 112 boots it out afterwards, so it runs until migrations finish.
- watchdog still targets the retired `listen` on :7600 (core/bin/crons/watchdog:115).
