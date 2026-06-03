# Discord bot missing/offline diagnostics for Miho

Use this when a user has configured Discord but says the bot is not visible, not online, or not responding.

## Decision tree

### 1. Gateway connects but bot is not in the server

Symptom:

- Logs contain `Connected as <bot>#...` / `✓ discord connected`.
- Discord server member/channel list does not show the bot.

Meaning:

- The token is valid and the gateway can log in to Discord.
- The bot application was not guild-installed into the target server, or the user invited a different Discord application.

Checks:

```bash
# Do not print the token. Use it only as an Authorization header.
# Compare the returned bot id/name to the client_id used in the invite URL.
curl -sS -H "Authorization: Bot $DISCORD_BOT_TOKEN" https://discord.com/api/v10/users/@me
```

Fix:

- Build an invite URL for the returned bot ID/client ID.
- Use scopes: `bot applications.commands`.
- Use Guild/Server Install, not just User Install.
- In Discord Developer Portal → OAuth2 → General, turn `Requires OAuth2 Code Grant` OFF for normal bot invite flows.
- Ensure Guild Install is enabled in installation settings.

### 2. Bot is in the server but offline

Symptom:

- The bot appears in the Discord server, but the member list shows it offline.

Meaning:

- The Discord application is installed, but no Miho gateway process is currently connected for that token.

Checks:

```bash
miho gateway status
ps aux | grep -i '[m]iho gateway\|[h]ermes gateway'
tail -80 ~/.miho/logs/gateway.log
```

Healthy log signals:

```text
Connecting to discord...
Connected as 미호#...
✓ discord connected
Gateway running with 1 platform(s)
Channel directory built: 1 target(s)
```

If `Channel directory built: 0 target(s)` appears before the bot was added to the server, restart/re-run the gateway after invitation so the channel directory is rebuilt.

### 3. Miho/Miho token or home confusion

Symptom:

- The user has both `~/.miho` and `~/.miho`, or a Miho wrapper plus an older Miho service.
- One bot name is connected in logs, but another bot/application was invited.

Checks:

```bash
miho --version
miho config path
miho config env-path
miho config path 2>/dev/null || true
miho config env-path 2>/dev/null || true
```

Then inspect only variable names and bot identity; never print tokens in chat.

Common pattern:

- `~/.miho/.env` holds the Miho Discord token.
- `~/.miho/.env` may hold an older Miho Discord token.
- `miho gateway run` should use Miho's home, but a stale launchd service may still run the old Miho install.

### 4. macOS launchd service says started but bot stays offline

Symptoms:

- `miho gateway start` prints `✓ Service started`, but `miho gateway status` says service is not loaded.
- `Bootstrap failed: 5: Input/output error` appears.
- `gateway status` reports a stale service definition or an old Miho venv/path.

Checks:

```bash
miho gateway status
plutil -p ~/Library/LaunchAgents/ai.miho.gateway.plist
launchctl print gui/$(id -u)/ai.miho.gateway
```

Immediate test path:

```bash
miho gateway run
```

Durable service reset:

```bash
miho gateway stop
miho gateway uninstall
miho gateway install
miho gateway start
miho gateway status
```

Do not conclude the bot is online from `✓ Service started` alone. Verify process presence and gateway logs.

## User-facing explanation pattern

Keep it short:

- “Connected as bot” means the token logged in; it does not prove the bot is installed in the server.
- “Bot in server but offline” means the gateway process is not connected.
- Foreground `miho gateway run` is the fastest truth test.
