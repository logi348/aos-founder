#!/usr/bin/env bash
# ─── Vercel Integration Setup ─────────────────────────────
# Puts the operator's app on the internet. Installs Node and the Vercel CLI,
# signs in through the browser, and registers Vercel's MCP server with Claude
# Code so Skye can check deployments directly.
#
# Usage:
#   setup.sh              — interactive setup
#   setup.sh --check      — verify install + sign-in

source "$(dirname "$0")/../_lib.sh"

NAME="vercel"
echo ""
echo "${BOLD}Vercel${RESET} — put your app on the internet"
echo ""

errors=0

# ── Step 1: Node (every modern web app needs it) ─────────

check_command "Node installed" "command -v node" || {
    if ! $IS_CHECK; then
        _info "Installing Node (needed to build web apps)..."
        brew install node 2>&1 | tail -3
        check_command "Node installed" "command -v node" || ((errors++))
    else
        ((errors++))
    fi
}

# ── Step 2: Vercel CLI ────────────────────────────────────

check_command "Vercel installed" "command -v vercel" || {
    if ! $IS_CHECK; then
        _info "Installing Vercel..."
        brew install vercel-cli 2>&1 | tail -3
        check_command "Vercel installed" "command -v vercel" || ((errors++))
    else
        ((errors++))
    fi
}

# ── Step 3: Sign in (browser) ─────────────────────────────

if vercel whoami &>/dev/null; then
    _ok "Signed in to Vercel as $(vercel whoami 2>/dev/null | tail -1)"
elif $IS_CHECK; then
    _fail "Not signed in to Vercel"
    ((errors++))
else
    _info "Opening your browser to sign in to Vercel..."
    vercel login 2>&1 || true
    if vercel whoami &>/dev/null; then
        _ok "Signed in to Vercel"
    else
        _warn "Sign-in didn't finish. Skye can try again any time."
        ((errors++))
    fi
fi

# ── Step 4: Let Skye see deployments (Claude Code MCP) ───

if command -v claude &>/dev/null; then
    if claude mcp get vercel &>/dev/null; then
        _ok "Skye can reach Vercel"
    elif ! $IS_CHECK; then
        claude mcp add --scope user --transport http vercel https://mcp.vercel.com >/dev/null 2>&1 \
            && _ok "Skye can reach Vercel (approve it once with /mcp)" \
            || _warn "Couldn't register Vercel with Claude Code"
    else
        _warn "Vercel not registered with Claude Code"
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
