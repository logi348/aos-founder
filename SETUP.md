# Setting up the Mac mini

Step-by-step install of this hardened fork on a dedicated Mac mini. It takes
about an hour, plus the time macOS takes to erase and update. Background on
each safeguard is in HARDENING.md; updates are covered in UPSTREAM.md.

You install as an **admin** user, then remove admin rights afterwards. The
installer needs your password for system steps, and Homebrew has to be owned
by the user who runs AOS.

## Before you touch the Mac (on your laptop or phone)

1. **GitHub security**
   - Turn on 2FA for your GitHub account, if it isn't already.
   - In `logi348/aos-hardened`: Settings → Actions → General → tick **"Allow
     GitHub Actions to create and approve pull requests"**, then save.
   - Optional: branch protection on `main`, set to require a pull request. On
     a free plan GitHub doesn't offer this for private repos. The read-only
     token in step 2 is the control that matters.
2. **Create a read-only GitHub token**
   - GitHub → Settings → Developer settings → Fine-grained tokens → Generate.
   - Repository access: only `aos-hardened`. Permissions: **Contents →
     Read-only**. Expiry: one year. Set a calendar reminder to renew it.
   - Copy it somewhere temporary. You paste it once, in step 10.
3. **Create the Telegram bot** (on your phone)
   - In Telegram, open @BotFather and send `/newbot`.
   - Pick a name, and a username ending in `bot`.
   - Keep the message with the token.
4. **Router** (while the Mac mini shares your main network)
   - Turn off **UPnP**.
   - Change the default admin password.
   - Turn off WPS.
   - Update the firmware if an update is available.

## Reset and base macOS

5. On the Mac mini:
   - Sign out of the Apple ID (this turns off Find My).
   - Then System Settings → General → Transfer or Reset → **Erase All Content
     and Settings**.
6. **Setup Assistant**
   - Create the first account, e.g. **"Admin"**. This stays your admin
     account.
   - Apple ID: skip, or use the new dedicated email. Never your personal one.
   - **Turn FileVault on.** Save the recovery key somewhere off the Mac.
   - Install any pending macOS updates.
7. **Create the AOS account** (as Admin)
   - System Settings → Users & Groups → Add User → e.g. **"aos"**, type
     **Administrator** for now.
   - Check that it can unlock FileVault. In Terminal as Admin:
     ```bash
     sudo fdesetup list
     ```
     Both users should be listed.
8. **Network and sharing** (still as Admin)
   - Install Tailscale from tailscale.com or the App Store and sign in. In
     its settings, choose **Install CLI** so the AOS installer detects it and
     doesn't install a second copy.
   - System Settings → Network → **Firewall on**. Under Options, turn on
     **stealth mode**.
   - System Settings → General → Sharing:
     - turn off **AirPlay Receiver**, File Sharing, Media Sharing and
       everything else;
     - turn **Remote Login on**, with "Allow access for: Only these users" →
       **aos**;
     - leave Screen Sharing off unless you want it.
   - Time Machine: General → Time Machine → add a backup disk.

## Install AOS (logged in as "aos")

9. Open Terminal and run:
   ```bash
   xcode-select --install
   ```
   Click **Install** in the dialog and wait for it to finish.
10. Clone the fork:
    ```bash
    git clone https://github.com/logi348/aos-hardened.git ~/aos
    ```
    - Username: `logi348`. Password: **paste the token from step 2**.
    - macOS stores the token in the Keychain, so later update checks use it
      silently.
    - Delete your temporary copy of the token.
11. Run the installer:
    ```bash
    cd ~/aos && bash install.sh --always-on
    ```
    - It asks for a name and email for git, and for the aos user's password
      when it installs the Command Line Tools, Homebrew and the always-on
      settings. Allow 20–30 minutes.
    - At the end it opens cmux and Claude Code. **Sign in with your Claude
      account** in the browser.
12. **Onboarding with Skye** starts automatically. It's the setup
    conversation, and these are the parts to know about:
    - **Telegram:**
      1. Open a second Terminal window and run:
         ```bash
         ~/aos/core/bin/cli/agent-secret set TELEGRAM_BOT_TOKEN
         ```
         Paste the bot token at the hidden prompt.
      2. Then run:
         ```bash
         aos telegram-pair
         ```
         Type your Telegram @username, send the code it shows to your bot
         from your phone, and type the confirmation code.
    - **Remote access:** choose "SSH only" (or neither). Tailscale is already
      done.
    - **Trust:** choose **Copilot** (the default).
    - **iMessage:** AOS sees no threads until you add contacts to
      `~/.aos/config/comms.yaml`.

## Verify (still as "aos")

13. Health checks:
    ```bash
    aos self-test
    ```
    ```bash
    launchctl list | grep com.aos
    ```
14. Phone approvals:
    ```bash
    ~/aos/core/bin/cli/approval-smoke-test
    ```
    Your phone should get an Allow/Deny prompt. Tap **Allow**, and it should
    say the file was created.
15. Send your bot a message from your phone and check it answers. If you
    have a second Telegram account, message the bot from it too: that
    message should be ignored.

## Lock it down

16. **SSH keys only** (do this the same day you enabled Remote Login)
    - From your laptop, set up a key and test it:
      ```bash
      ssh-copy-id aos@<mac-mini-tailscale-name>
      ```
      ```bash
      ssh aos@<mac-mini-tailscale-name>
      ```
      The second command should log in without asking for a password.
    - Then, logged in as **Admin** on the Mac, switch off password login:
      ```bash
      printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' | sudo tee /etc/ssh/sshd_config.d/100-aos.conf
      ```
    - Turn Remote Login off and on again to apply it.
17. **Remove admin from "aos"**
    - As Admin: Users & Groups → aos → turn off "Allow this user to
      administer this computer".
    - Restart the Mac, unlock FileVault **as aos**, and check that Telegram
      answers again.
18. **Turn on the sandbox** after a day or two of normal use. Do it early
    while the Mac shares your main network: it limits agents' shell commands
    to an allowlist of internet domains, so they can't reach your other
    devices.
    ```bash
    aos claude-features enable sandbox
    ```
    If shell commands start failing:
    ```bash
    aos claude-features disable sandbox
    ```

## Ongoing

- **Updates.**
  1. Each Monday, an upstream-sync pull request appears on GitHub if
     upstream changed.
  2. Review it: read the ⚠️ sections first, or ask Claude to check it
     against HARDENING.md.
  3. Merge it.
  4. Tap **Apply update** in Telegram, or run `aos update`.
- **After a power cut,** unlock FileVault as **aos**. AOS starts once that
  user is logged in.
- **To change system settings,** log in as Admin. Re-running
  `install.sh --always-on` also needs the admin login.
- **To let agents reach one device on your network** (a printer, say), add
  its IP, CIDR or hostname to `~/.aos/config/lan-allow`, one per line.
- **Renew the GitHub token before it expires.** When it lapses, update
  checks quietly stop finding updates. To renew, delete the github.com entry
  in Keychain Access, run `git -C ~/aos fetch`, and paste the new token.
- **When you can, move the Mac mini to a guest network or its own VLAN.**
  Nothing in AOS changes when you do.

The GitHub token is stored in the aos user's Keychain, so an agent could
technically retrieve it with git's credential tools. That's why it has to
be **read-only**: the worst case is an agent reading your fork, which it
already has.
