#!/usr/bin/env bash
# upstream-report.sh BASE HEAD — Markdown review aid for an upstream sync PR.
# Lists what changed and flags the changes most likely to undo the hardening
# (see HARDENING.md / UPSTREAM.md). It never executes anything from HEAD.
set -uo pipefail
BASE="$1"; HEAD="$2"
# Added lines as "path: +line" (no context, no diff headers).
added() {
  git diff -U0 "$BASE...$HEAD" -- "$@" | awk '
    /^\+\+\+ b\// { f = substr($0, 7); next }
    /^\+[^+]/     { print f ": " $0 }'
}

echo "## Upstream changes"
echo
echo "$(git rev-list --count "$BASE..$HEAD") new upstream commit(s):"
echo
echo '```'
git log --oneline --no-merges "$BASE..$HEAD" | head -60
echo '```'
echo
echo "### Files"
echo '```'
git diff --stat "$BASE...$HEAD" | tail -80
echo '```'
echo

echo "## Review these closely"
echo
flag() {  # title, then a grep -E pattern over added lines
  local title="$1" pat="$2"; shift 2
  local hits; hits=$(added "$@" | grep -E "$pat" | cut -c1-220 | head -25)
  if [[ -n "$hits" ]]; then
    echo "### ⚠️ $title"; echo '```'; echo "$hits"; echo '```'; echo
  fi
}
flag "Permission bypass" 'dangerously-skip-permissions|bypassPermissions|"defaultMode"' .
flag "Update crons re-enabled / new scheduled jobs" 'enabled: *true|^\+  [a-z0-9-]+:$|auto-update|harness-update' config/crons.yaml
flag "Blanket permissions / Claude settings" 'Bash\(\*\)|Read\(\*\)|Write\(\*\)|Edit\(\*\)|remoteControlAtStartup|claudeInChromeDefaultEnabled|hasTrustDialogAccepted' .
flag "macOS security settings" 'askForPassword|screensharing|pmset|autoLoginUser|nvram|sudo -n true|sudo true' install.sh bootstrap.sh core
flag "New network destinations or downloads" 'https?://|curl |wget |git clone|pip3? install|uv pip install|npm (i|install)|bun (i|install)|brew install|urlopen|requests\.(get|post)|httpx\.' .
flag "Upstream repo address (should point at the fork)" 'AOS-Agent/aos|install\.hish\.am|hishamalhadi' . ':!core/infra/migrations/137_repo_url_aos_agent.py' ':!UPSTREAM.md' ':!HARDENING.md' ':!SECURITY-AUDIT.md' ':!CHANGELOG.md'
flag "Inbound-message or Telegram auth code" '_is_authorized|allowed_chat_id|forum_group_id|callback_query|Access-Control|0\.0\.0\.0' core/services
flag "Trust / approval logic" 'trust_level|default_level|requires_human_approval|promote' core config

echo "### Sensitive paths touched"
echo '```'
git diff --name-only "$BASE...$HEAD" -- \
  install.sh bootstrap.sh config/crons.yaml config/defaults core/infra/migrations \
  core/infra/reconcile core/infra/lib/claude_permissions.py core/infra/lib/claude_features.py \
  core/infra/lib/human_gate.py core/hooks core/bin/cli/cld core/bin/cli/cld-unsafe \
  core/services/bridge core/services/whatsmeow .github core/engine/comms/scope.py \
  | sed 's/^/  /'
echo '```'
echo
echo "New migrations run automatically on \`aos update\`; read each one."
