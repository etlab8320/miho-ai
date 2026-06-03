---
name: miho-agent
description: "Configure and troubleshoot Miho AI, the local Miho Agent-based CLI wrapper, including gateway messaging integrations."
version: 1.0.0
author: Miho Agent
license: MIT
platforms: [macos, linux, windows]
metadata:
  miho:
    tags: [miho, miho, gateway, discord, setup, configuration]
    related_skills: [miho-agent]
---

# Miho Agent

Use this skill when the user asks to configure, set up, run, troubleshoot, or integrate Miho AI itself. Miho is a local wrapper around the Miho Agent engine, so most Miho operational concepts apply, but commands and paths may use `miho` / `~/.miho` instead of `miho` / `~/.miho`.

## First step: verify the active CLI and home

Before giving commands, check which executable is available and what home directory it reports:

```bash
command -v miho || command -v miho || true
miho --version 2>/dev/null || miho --version 2>/dev/null || true
```

Then tailor commands to the detected binary. If `miho` is present, prefer `miho ...` commands and Miho's reported home directory. Do not blindly paste `miho ...` examples from upstream docs when the user's installed CLI is `miho`.

## Gateway setup pattern

For messaging platforms such as Discord, Telegram, Slack, and others:

1. Load the upstream `miho-agent` skill if the task concerns Miho/Miho setup or gateway behavior.
2. Verify whether the local command is `miho` or `miho`.
3. Give the interactive setup path first:
   ```bash
   miho gateway setup
   ```
   or, if only Miho is installed:
   ```bash
   miho gateway setup
   ```
4. Mention the manual `.env` path using the detected home directory, e.g. `/Users/.../.miho/.env` for Miho.
5. Start with foreground testing before recommending a persistent service:
   ```bash
   miho gateway run
   ```
6. For background operation:
   ```bash
   miho gateway install
   miho gateway start
   miho gateway status
   ```

## Discord integration checklist

Discord setup usually needs three things:

1. A Discord application/bot token from the Discord Developer Portal.
2. Privileged Gateway Intents enabled:
   - Server Members Intent
   - Message Content Intent
3. Authorization configured in Miho/Miho:
   - `DISCORD_BOT_TOKEN`
   - `DISCORD_ALLOWED_USERS` and/or `DISCORD_ALLOWED_ROLES`

Manual Miho `.env` example:

```bash
DISCORD_BOT_TOKEN=your-bot-token
DISCORD_ALLOWED_USERS=your-discord-user-id
```

Never ask the user to paste bot tokens into chat. Tell them to enter secrets through `miho gateway setup` or edit the local `.env` directly.

## Behavior notes for Discord

- DMs respond without `@mention`.
- Server channels require `@mention` by default.
- `DISCORD_FREE_RESPONSE_CHANNELS` can make chosen channels mention-free.
- `DISCORD_AUTO_THREAD=true` is the default; mentions in regular text channels may spawn threads.
- `DISCORD_HOME_CHANNEL` controls where proactive cron/reminder output can be delivered.

## Troubleshooting order

If the Discord bot is online but silent:

1. Confirm Message Content Intent is enabled in the Discord Developer Portal.
2. Confirm the user's Discord ID is in `DISCORD_ALLOWED_USERS` or their role is in `DISCORD_ALLOWED_ROLES`.
3. Confirm the gateway is running:
   ```bash
   miho gateway status
   ```
4. Check gateway logs in the detected home directory, e.g.:
   ```bash
   tail -100 ~/.miho/logs/gateway.log
   ```
5. If settings changed, restart the gateway:
   ```bash
   miho gateway restart
   ```

### Discord bot missing or offline

Distinguish these states before prescribing a fix:

- Gateway log says `Connected as 미호#...` but the bot is not in the Discord server member/channel list: the token is valid, but the bot was not guild-installed. Generate/verify the OAuth invite for the bot user configured in the active Miho home and re-invite it with `bot` + `applications.commands` scopes. In the Discord Developer Portal, turn off `Requires OAuth2 Code Grant` for normal bot invites and ensure Guild Install is allowed.
- Bot appears in the server but is offline: the Discord application was installed, but the Miho gateway process is not connected. Check `miho gateway status`, running processes, and `~/.miho/logs/gateway.log`. A healthy run logs `✓ discord connected`, `Gateway running with 1 platform(s)`, and a nonzero `Channel directory built: N target(s)` after the bot is in a server.
- Miho/Miho migration or wrapper environments can have two Discord tokens/homes (`~/.miho` and `~/.miho`). Verify the bot identity behind each configured token via Discord `/users/@me` before assuming the invite link matches the gateway currently being run.
- On macOS launchd, `miho gateway start` may report a stale service or `Bootstrap failed: 5: Input/output error`. Do not claim the bot is online from that command alone. Verify with `ps`, `launchctl print gui/$(id -u)/ai.miho.gateway`, and the Miho gateway log. For immediate testing, `miho gateway run` in the foreground is the clearest signal; for durable use, reinstall the service (`miho gateway uninstall`, `miho gateway install`, `miho gateway start`) and re-check status.

## Linked references

- `references/discord-gateway-setup.md` — concise Discord-specific setup notes adapted for Miho/Miho wrapper environments.
- `references/discord-bot-offline-diagnostics.md` — decision tree for Miho Discord bot missing/offline cases, including dual Miho/Miho token confusion and launchd verification.
