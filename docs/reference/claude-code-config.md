# Claude Code Configuration Rule

Claude Code uses **two separate config files** with different purposes. Never confuse them.

## Config Files

| File | Purpose | Managed by |
|------|---------|------------|
| `~/.claude/settings.json` | Harness settings: permissions, hooks, env vars, model, agent, MCP servers, effort level | Direct edit or `update-config` skill |
| `~/.claude.json` | Runtime preferences: UI toggles, OAuth state, feature flags set via `/config` | `/config` UI or careful direct edit |

These are **not interchangeable**. A key that belongs in one will be silently ignored in the other.

## Verified Settings

These have been tested and confirmed working:

| Feature | Key | File | Verified |
|---------|-----|------|----------|
| Chrome on by default | `"claudeInChromeDefaultEnabled"` | `~/.claude.json` | docs, 2026-10 |
| Remote Control all sessions | `"remoteControlAtStartup"` | `~/.claude/settings.json` (docs); upstream AOS also wrote `~/.claude.json` | docs, 2026-10 |
| Default agent | `"agent": "skye"` | `~/.claude/settings.json` | confirmed |
| Claude Code auto-update off | `"env": {"DISABLE_AUTOUPDATER": "1"}` | `~/.claude/settings.json` | docs, 2026-10 |

## AOS Defaults (hardened fork)

- **Remote Control and Claude in Chrome are OFF** and opt-in. Never set
  `remoteControlAtStartup`, `claudeInChromeDefaultEnabled` or `"chrome"`
  directly: the operator turns them on with
  `aos claude-features enable remote-control|chrome`, and the
  `claude_defaults` reconcile check enforces that choice
  (`core/infra/lib/claude_features.py`).
- **No permission bypass by default.** `cld` runs under the rules in
  `settings.json`; only `cld-unsafe` passes `--dangerously-skip-permissions`.
  Do not set `permissions.defaultMode` to `bypassPermissions`.
- **Permissions** come from `core/infra/lib/claude_permissions.py` (scoped
  Read/Edit allows, deny rules) and the Bash guard hook
  `core/hooks/guard_bash.py`; reconcile restores both. Change the module, not
  the live file.
- **Sandbox** (OS-enforced limits for shell commands) is opt-in:
  `aos claude-features enable sandbox` writes the `sandbox` block defined in
  `core/infra/lib/claude_features.py`. Change it there, not in settings.json.
- `~/.claude/` is protected by Claude Code itself: no allow rule lets an
  agent edit it outside bypass mode. That is intended.

## The Rule: Don't Assume, Verify

Claude Code settings are **not well-documented** in a single table. Many keys exist only in source code or are set by `/config` without being listed in the official settings docs.

When working with Claude Code configuration:

1. **Never guess a key name.** If you don't know the exact key, don't invent one.
2. **Check the docs first.** Fetch `https://code.claude.com/docs/en/settings` or the relevant feature page.
3. **If docs don't have it, test it.** Toggle via `/config`, then diff `~/.claude.json` to find the actual key.
4. **Document what you verify.** Add confirmed keys to the table above so we don't re-discover them.
5. **settings.json vs .claude.json is not obvious.** The `/config` UI writes to `~/.claude.json`. The `settings.json` file is for harness-level config. When in doubt, check both files before and after a change.
