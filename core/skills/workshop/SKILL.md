---
name: workshop
description: >
  Change how AOS itself works for this operator — durably, with their
  approval, and undoably. Trigger on "change how you work", "change how my
  system works", "customize AOS", "customize yourself", "improve yourself",
  "apply my changes to my system", "undo that change", "undo my last change
  to the system", "check if Rob has improvements", "check for improvements
  from the original copy". Do NOT trigger on shipping or deploying the
  operator's own app or website ("ship my app", "deploy my app", Vercel
  deploys) — that is their project's work, not a change to AOS.
allowed-tools: Bash, Read, Glob, Grep, Edit, Write
---

# Workshop — Changing How AOS Works

The operator wants you to work differently in a way that needs a change to
AOS's own code — a skill, an agent, a script, a default. Preferences that live
in `~/.aos/` (name, tone, schedule under `operator.yaml`) are NOT workshop
work; just change those directly.

**Why the workshop exists:** `~/aos` is the running copy. Edits there are
wiped every 30 minutes by the self-repair check. Durable changes take this
path instead:

```
~/project/aos (workshop)  →  operator's own private GitHub repo  →  aos update (operator approves)
```

The operator's repo (`workshop.repo` in `~/.aos/config/operator.yaml`) is
theirs alone. Their machine updates only from it. The original project is
the `upstream` remote — looked at only when they ask, never pushed to.

**Not this skill:** shipping or deploying the operator's own app ("ship my
app", "deploy my app", Vercel) — that is project work in `~/project/<app>`.

## How you talk about it

- Plain language. No jargon; if you need a technical word, explain it in the
  same sentence. Never show commands — you run them.
- One question at a time.
- Say what changes **for them**, not what changed in the code.

## If the workshop isn't set up yet

Onboarding normally sets it up. Check silently:

```bash
~/aos/core/bin/internal/workshop-setup --check
```

If it exits non-zero, explain in one sentence and ask one question:

> "To change how I work in a way that sticks, I need my own copy of my code
> that I can edit safely. Want me to keep a private copy of my own code on
> your GitHub so I can change how I work for you?"

On yes:

```bash
~/aos/core/bin/internal/workshop-setup
```

If it fails because GitHub isn't connected, help them log in (onboarding's
GitHub step), then run it again. On no, stop.

## Making a change

### 1. Sync and branch

```bash
git -C ~/project/aos fetch origin && git -C ~/project/aos pull --ff-only origin main
git -C ~/project/aos switch -c change/<short-slug>
```

If `pull --ff-only` fails, stop and work out why before going further — never
force anything.

### 2. Edit — only in the workshop

Edit files under `~/project/aos/` only. Never edit `~/aos/` (it gets wiped)
and never touch `~/.claude/` framework copies by hand — they come from the
update. Keep the change as small as it can be.

### 3. Check it

```bash
~/aos/core/bin/cli/aos self-test
[ -x ~/project/aos/core/bin/cli/ship-check ] && bash ~/project/aos/core/bin/cli/ship-check
```

If tests cover the files you touched and run quickly, run just those:

```bash
cd ~/project/aos && uv run --frozen --with pytest python -m pytest -q tests/<relevant_test>.py
```

ship-check exit 1 = stop and fix. Exit 2 = warnings; mention any that matter.

Make sure nothing sensitive is in the change: no `.env`, keys, tokens,
`credentials`, `*.pem`, `*.key`, logs, `.jsonl`, `execution_log/`,
`__pycache__/`, or anything from `~/.aos/`.

### 4. Commit on the branch, then run the safety check

Committing on the change branch is safe — nothing leaves the machine and
nothing runs until step 6.

```bash
cd ~/project/aos
git add <file1> <file2> ...          # list files explicitly — NEVER git add -A or git add .
git commit -m "<one plain line: what changes for the operator>"
~/aos/core/bin/internal/workshop-safety-check -C ~/project/aos main..change/<slug>
```

### 5. Tell them, in plain words

Give a 3-5 line summary of what will be different for them. Example:

> "Here's the change:
> - Your morning briefing will be three bullet points instead of a page.
> - Weather moves to the end.
> Nothing else changes. Want me to apply it?"

**If the safety check printed anything**, start the summary with:

> "⚠️ This changes one of my safety rules: <one plain sentence saying what
> gets looser or tighter>."

and ask for an explicit yes ("Yes, change the safety rule"). Anything short
of a clear yes is a no. On a no, switch back to `main` and leave the branch.

### 6. Apply — only after their yes

```bash
cd ~/project/aos
git switch main
git merge --ff-only change/<slug>
git push origin main                 # their own repo — never --force
```

Then tell them: "I'm installing it now — you'll get a prompt asking you to
approve the update. Say yes." and run:

```bash
~/aos/core/bin/cli/aos update
```

The guard asks them to approve this — that's expected and must stay that way.
If they decline, the change is saved on GitHub but not running; say so.

### 7. Verify

```bash
~/aos/core/bin/cli/aos self-test
```

Then check the actual thing changed (read the deployed file under `~/aos/`, or
trigger the behaviour). Tell them in one line that it's live. If anything
failed, say so plainly and offer to undo it.

## Undoing a change

"Undo that change" / "undo my last change to the system":

```bash
cd ~/project/aos
git fetch origin && git switch main && git pull --ff-only origin main
git log --oneline -10
```

Pick the change commit(s) — confirm with them in plain words which change
you're undoing ("the shorter morning briefing from Tuesday — that one?").
Then:

```bash
git revert --no-edit <commit> [<commit> ...]
git push origin main
~/aos/core/bin/cli/aos update        # they approve again
~/aos/core/bin/cli/aos self-test
```

A revert adds a new commit that cancels the old one — history is never
rewritten.

## Improvements from the original copy — only when asked

"Check if Rob has improvements" / "check for improvements from the original
copy". **Never automatic** — no cron, no checking on your own, no merging
without a yes.

### 1. Look

```bash
cd ~/project/aos
git fetch --no-tags upstream
git switch main && git pull --ff-only origin main
git log --oneline main..upstream/main
```

Nothing new → tell them in one line and stop.

### 2. Summarize and safety-check

For each new commit (or group of related ones), 1-2 plain lines on what it
would change for them. Then:

```bash
~/aos/core/bin/internal/workshop-safety-check -C ~/project/aos main...upstream/main
```

Prefix any safety-rule changes with "⚠️ This changes one of my safety rules:"
and a plain sentence each. Ask once: "Want me to bring these in?" (On
safety-rule changes, require an explicit yes to those too.) They can also
pick only some — then cherry-pick just those commits in step 3.

### 3. Bring them in on a branch

```bash
git switch -c change/upstream-<date> main
git merge --no-edit upstream/main      # or: git cherry-pick <commit> ...
```

If there are conflicts — the same part of a file changed on both sides —
explain each one plainly ("Rob changed how the briefing starts; you'd changed
it to three bullet points. Keep yours, take his, or combine them?"), let them
choose, resolve accordingly, `git add <those files>` explicitly, and finish
the merge. If it gets tangled, `git merge --abort` and say so — nothing is
lost.

### 4. Check, apply, verify

Run the checks from "Making a change" step 3, then:

```bash
git switch main
git merge --ff-only change/upstream-<date>
git push origin main
~/aos/core/bin/cli/aos update        # they approve
~/aos/core/bin/cli/aos self-test
```

Undo works the same as any other change (`git revert -m 1 <merge commit>` for
a merge).

## Rules

- Edit only in `~/project/aos`. Never in `~/aos` — it's wiped every 30 minutes.
- Never push without the operator's yes. Never force-push. Never push to `upstream`.
- Stage files explicitly; never `git add -A` / `git add .`.
- Never commit secrets or runtime data.
- Safety-rule changes need the ⚠️ warning and an explicit yes.
- Every change is applied with `aos update` (operator approves) and verified.
- Undo with `git revert`, never `reset --hard` on main.
- Never fetch `upstream` unless the operator asked; always `--no-tags` (a
  `stable` tag from upstream would pin their updates to an old commit).
