#!/usr/bin/env bash
# ─── Supabase Integration Setup ───────────────────────────
# The app's database, user sign-ups/logins and file storage. Installs the
# Supabase CLI, signs in through the browser, and registers Supabase's MCP
# server with Claude Code so Skye can read and manage projects directly.
#
# Usage:
#   setup.sh              — interactive setup
#   setup.sh --check      — verify install + sign-in

source "$(dirname "$0")/../_lib.sh"

NAME="supabase"
echo ""
echo "${BOLD}Supabase${RESET} — your app's database and logins"
echo ""

errors=0

# ── Step 1: Supabase CLI ──────────────────────────────────

check_command "Supabase installed" "command -v supabase" || {
    if ! $IS_CHECK; then
        _info "Installing Supabase..."
        brew install supabase/tap/supabase 2>&1 | tail -3
        check_command "Supabase installed" "command -v supabase" || ((errors++))
    else
        ((errors++))
    fi
}

# ── Step 2: Sign in (browser) ─────────────────────────────

if supabase projects list &>/dev/null; then
    _ok "Signed in to Supabase"
elif $IS_CHECK; then
    _fail "Not signed in to Supabase"
    ((errors++))
else
    _info "Opening your browser to sign in to Supabase..."
    supabase login 2>&1 || true
    if supabase projects list &>/dev/null; then
        _ok "Signed in to Supabase"
    else
        _warn "Sign-in didn't finish. Your assistant can try again any time."
        ((errors++))
    fi
fi

# ── Step 3: Let Skye manage projects (Claude Code MCP) ───

if command -v claude &>/dev/null; then
    if claude mcp get supabase &>/dev/null; then
        _ok "Your assistant can reach Supabase"
    elif ! $IS_CHECK; then
        claude mcp add --scope user --transport http supabase https://mcp.supabase.com/mcp >/dev/null 2>&1 \
            && _ok "Your assistant can reach Supabase (approve it once with /mcp)" \
            || _warn "Couldn't register Supabase with Claude Code"
    else
        _warn "Supabase not registered with Claude Code"
    fi
fi

# ── Result ────────────────────────────────────────────────

echo ""
if [[ $errors -eq 0 ]]; then
    setup_complete "$NAME"
else
    setup_failed "$NAME" "$errors issue(s)"
fi

exit $errors
