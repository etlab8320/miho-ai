# Discord Gateway Setup for Miho/Miho

Use this reference when adapting upstream Miho Discord instructions to a local Miho install.

## Core flow

1. Create an application in the Discord Developer Portal.
2. In the Bot tab, enable privileged intents:
   - Server Members Intent
   - Message Content Intent
3. Copy/reset the bot token. Do not expose it in chat.
4. Invite the bot with scopes:
   - `bot`
   - `applications.commands`
5. Recommended permissions integer: `274878286912`.
   Manual invite URL template:
   `https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&scope=bot+applications.commands&permissions=274878286912`
6. Copy the authorized user's Discord User ID using Discord Developer Mode.
7. Configure via the local wrapper:
   - Prefer `miho gateway setup` when `miho --version` reports Miho AI.
   - Use `miho gateway setup` only when the installed command is Miho.
8. Foreground test:
   - `miho gateway run`
9. Persistent service:
   - `miho gateway install`
   - `miho gateway start`
   - `miho gateway status`

## Manual `.env` keys

For Miho, use the Miho home reported by `miho --version` (commonly `~/.miho`):

```bash
DISCORD_BOT_TOKEN=your-bot-token
DISCORD_ALLOWED_USERS=your-discord-user-id
```

Optional behavior keys:

```bash
DISCORD_REQUIRE_MENTION=true
DISCORD_FREE_RESPONSE_CHANNELS=channel-id-1,channel-id-2
DISCORD_HOME_CHANNEL=channel-id
DISCORD_AUTO_THREAD=true
```

## Response behavior to explain to users

- DMs: respond to every message.
- Server channels: require `@mention` by default.
- Free-response channels: channel IDs in `DISCORD_FREE_RESPONSE_CHANNELS` respond without `@mention`.
- Threads: the bot replies in the same thread; thread session history is isolated.

## Common silent-bot diagnosis

If the bot appears online but does not respond, check in this order:

1. Discord Developer Portal → Bot → Privileged Gateway Intents → Message Content Intent ON.
2. User authorization: `DISCORD_ALLOWED_USERS` or `DISCORD_ALLOWED_ROLES` configured.
3. Gateway is actually running: `miho gateway status`.
4. Logs: `~/.miho/logs/gateway.log` or the home reported by the CLI.
5. Restart after config/env changes: `miho gateway restart`.
