# Start here

This sets up **Skye**, your thinking and building partner, on your Mac.
You'll paste one line, wait while it installs, and then Skye takes over and
talks you through the rest.

**Time:** about 45 minutes. Most of it is waiting.

---

## Before you start

You need:

- **A Mac** with an Apple chip (M1 or newer) and a recent macOS (14 Sonoma or
  newer). To check: Apple menu → **About This Mac**.
- **A paid Claude plan** (Pro or Max) at [claude.ai](https://claude.ai).
  Skye runs on Claude, and the free plan can't run it.
- **Your Mac's password**, the one you type to unlock it.
- **A charger plugged in** and a steady internet connection.

You don't need to know anything technical. If a step doesn't look like what's
described here, stop and take a screenshot (see the end of this page).

---

## Step 1: Open Terminal

Terminal is an app that's already on your Mac. You'll only use it for this one
step.

1. Press **Command (⌘) + Space**.
2. Type **Terminal** and press **Return**.

A window with plain text opens. That's it.

## Step 2: Paste one line

Copy this whole line, paste it into the Terminal window with **⌘ + V**, then
press **Return**:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/logi348/aos-founder/main/bootstrap.sh)"
```

## Step 3: Answer the few questions it asks

Here is everything that may come up:

- **A pop-up asks to install "command line developer tools."** Click
  **Install**, then **Agree**. That's Apple's own tool and it's safe. It takes a
  few minutes.
- **It asks for your password.** Type your Mac password and press Return.
  **Nothing shows up while you type**, not even dots. That's normal, so keep typing.
- **It asks for your name and email.** Use your normal name, and the email you plan to use for GitHub.
- **Anything else asking yes or no:** pressing Return accepts the suggested
  answer, which is the right one.

Then **leave it running for 20–30 minutes**. Lots of text will scroll by. Don't
close the window, and don't let the Mac go to sleep.

## Step 4: Sign in to Claude

When it's done, a new app called **cmux** opens, and your web browser asks you
to sign in to Claude. Sign in with the account that has the paid plan, then
come back to cmux.

## Step 5: Say hi to Skye

Skye starts the conversation in cmux. From here you just talk, by typing in
plain words, the way you'd text a person. Skye will:

- get to know you, your background and what you're working toward;
- help you get everything you know out of your head and into notes it can use
  later;
- offer to connect the tools you'll need to build an app (GitHub, Vercel and
  Supabase), with the clicks explained one by one;
- set up anything else only if you want it.

Skip anything you're unsure about. You can say "later" to any question.

---

## Every day after that

Open the **cmux** app (it's in your Applications folder and Launchpad) and
start typing. Skye remembers your notes, ideas and tasks between sessions.

A few things you can say:

- "Let me brain dump."
- "Here's an idea. Poke holes in it."
- "What should I work on today?"
- "Help me build a first version of this."

Skye is set up to **disagree with you when it thinks you're wrong**, and to
push you to test ideas cheaply before building them. That's on purpose.

---

## If something goes wrong

1. **Paste the same line from Step 2 again.** It picks up where it stopped
   and doesn't redo what already worked.
2. Still stuck? **Take a screenshot** (press **⌘ + Shift + 3**) and send it to
   the person who gave you this link.

Running the line again is always safe.
