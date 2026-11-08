#!/usr/bin/env bash
# AOS bootstrap — the curl one-liner target
# Usage: bash -c "$(curl -fsSL .../bootstrap.sh)"
#
# HARD RULE: this script must not depend on git.
#
# On a fresh Mac /usr/bin/git is a stub that pops the Xcode Command Line Tools
# installer and exits non-zero. Under `set -e` that killed the bootstrap, so the
# operator had to sit through the CLT install and then re-paste the one-liner to
# start over. The irony was that install.sh already ships a three-tier CLT
# installer (prereq_xcode_clt) — it just never got to run, because fetching it
# required the very tool it exists to install.
#
# curl and tar ship with macOS and need no toolchain. So: download a tarball to a
# scratch dir, hand off to install.sh, and let it install CLT properly and clone
# the real ~/aos repo with git once git exists. One paste, start to finish.

set -euo pipefail

REPO_TARBALL="https://codeload.github.com/logi348/aos-founder/tar.gz/refs/heads/main"

# The repository is public, so the anonymous tarball URL above works. A token
# (GITHUB_TOKEN, or `gh auth token`) is still used when present, which avoids
# GitHub rate limits on shared networks.
CURL_AUTH=()
_token="${GITHUB_TOKEN:-}"
if [[ -z "$_token" ]] && command -v gh >/dev/null 2>&1; then
    _token="$(gh auth token 2>/dev/null || true)"
fi
if [[ -n "$_token" ]]; then
    REPO_TARBALL="https://api.github.com/repos/logi348/aos-founder/tarball/main"
    CURL_AUTH=(-H "Authorization: Bearer $_token")
fi

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/aos-bootstrap.XXXXXX")"
# Cleaned on failure only. On success we `exec` into install.sh, which replaces
# this process — the trap never fires and the staged files stay readable for the
# life of the installer.
trap 'rm -rf "$STAGE"' EXIT

printf '\n  Bootstrapping AOS...\n\n'

if ! curl -fsSL ${CURL_AUTH[@]+"${CURL_AUTH[@]}"} "$REPO_TARBALL" | tar -xz -C "$STAGE" --strip-components=1; then
    printf '  Could not download AOS.\n' >&2
    printf '  Check your internet connection and run the command again.\n' >&2
    printf '  If it keeps failing, take a screenshot and send it to whoever gave you the link.\n\n' >&2
    exit 1
fi

if [[ ! -f "$STAGE/install.sh" ]]; then
    printf '  Download was incomplete — install.sh is missing.\n' >&2
    printf '  Run the command again.\n\n' >&2
    exit 1
fi

trap - EXIT
exec bash "$STAGE/install.sh" "$@"
