from __future__ import annotations

import os

from .helpers import _clean_discord_user_ids, _discord_brand


def interactive_setup() -> None:
    """Guide the user through Discord bot setup.

    Mirrors Teams' ``interactive_setup`` shape: lazy-imports CLI helpers so
    the plugin's import surface stays small, prompts for the bot token,
    captures an allowlist, and offers to set a home channel.
    """
    from miho_cli.config import get_env_value, save_env_value
    from miho_cli.cli_output import (
        prompt,
        prompt_yes_no,
        print_header,
        print_info,
        print_success,
    )

    print_header("Discord")
    existing = get_env_value("DISCORD_BOT_TOKEN")
    if existing:
        print_info("Discord: already configured")
        if not prompt_yes_no("Reconfigure Discord?", False):
            if not get_env_value("DISCORD_ALLOWED_USERS"):
                print_info("⚠️  Discord has no user allowlist - anyone can use your bot!")
                if prompt_yes_no("Add allowed users now?", True):
                    print_info("   To find Discord ID: Enable Developer Mode, right-click name → Copy ID")
                    allowed_users = prompt("Allowed user IDs (comma-separated)")
                    if allowed_users:
                        cleaned_ids = _clean_discord_user_ids(allowed_users)
                        save_env_value("DISCORD_ALLOWED_USERS", ",".join(cleaned_ids))
                        print_success("Discord allowlist configured")
            return

    print_info("Create a bot at https://discord.com/developers/applications")
    token = prompt("Discord bot token", password=True)
    if not token:
        return
    save_env_value("DISCORD_BOT_TOKEN", token)
    print_success("Discord token saved")

    print()
    print_info("🔒 Security: Restrict who can use your bot")
    print_info("   To find your Discord user ID:")
    print_info("   1. Enable Developer Mode in Discord settings")
    print_info("   2. Right-click your name → Copy ID")
    print()
    print_info("   You can also use Discord usernames (resolved on gateway start).")
    print()
    allowed_users = prompt(
        "Allowed user IDs or usernames (comma-separated, leave empty for open access)"
    )
    if allowed_users:
        cleaned_ids = _clean_discord_user_ids(allowed_users)
        save_env_value("DISCORD_ALLOWED_USERS", ",".join(cleaned_ids))
        print_success("Discord allowlist configured")
    else:
        print_info("⚠️  No allowlist set - anyone in servers with your bot can use it!")

    print()
    print_info(f"📬 Home Channel: where {_discord_brand().short_name} delivers cron job results,")
    print_info("   cross-platform messages, and notifications.")
    print_info("   To get a channel ID: right-click a channel → Copy Channel ID")
    print_info("   (requires Developer Mode in Discord settings)")
    print_info("   You can also set this later by typing /set-home in a Discord channel.")
    home_channel = prompt("Home channel ID (leave empty to set later with /set-home)")
    if home_channel:
        save_env_value("DISCORD_HOME_CHANNEL", home_channel)

def _apply_yaml_config(yaml_cfg: dict, discord_cfg: dict) -> dict | None:
    """Translate ``config.yaml`` ``discord:`` keys into env vars.

    Implements the ``apply_yaml_config_fn`` contract (#24836).  Mirrors the
    legacy ``discord_cfg`` block that used to live in
    ``gateway/config.py::load_gateway_config()`` before this migration.

    The DiscordAdapter reads its runtime configuration via ``os.getenv()``
    throughout the connect / handle code paths (``DISCORD_REQUIRE_MENTION``,
    ``DISCORD_FREE_RESPONSE_CHANNELS``, ``DISCORD_AUTO_THREAD``,
    ``DISCORD_REACTIONS``, ``DISCORD_IGNORED_CHANNELS``,
    ``DISCORD_ALLOWED_CHANNELS``, ``DISCORD_NO_THREAD_CHANNELS``,
    ``DISCORD_HISTORY_BACKFILL``, ``DISCORD_HISTORY_BACKFILL_LIMIT``,
    ``DISCORD_ALLOW_MENTION_*``, ``DISCORD_REPLY_TO_MODE``,
    ``DISCORD_THREAD_REQUIRE_MENTION``).  Rather than rewrite ~50 call sites
    inside the adapter to read from ``PlatformConfig.extra`` instead, this
    hook keeps the existing env-driven model and merely owns the
    YAML→env translation here, next to the adapter that consumes it.

    Env vars take precedence over YAML — every assignment is guarded by
    ``not os.getenv(...)`` so explicit env vars survive a config.yaml
    update.  Returns ``None`` because no extras are seeded into
    ``PlatformConfig.extra`` directly (everything flows through env).
    """
    if "require_mention" in discord_cfg and not os.getenv("DISCORD_REQUIRE_MENTION"):
        os.environ["DISCORD_REQUIRE_MENTION"] = str(discord_cfg["require_mention"]).lower()
    if "thread_require_mention" in discord_cfg and not os.getenv("DISCORD_THREAD_REQUIRE_MENTION"):
        os.environ["DISCORD_THREAD_REQUIRE_MENTION"] = str(discord_cfg["thread_require_mention"]).lower()
    status_text = discord_cfg.get("status_text")
    if status_text is not None and not os.getenv("DISCORD_STATUS_TEXT"):
        os.environ["DISCORD_STATUS_TEXT"] = str(status_text)
    frc = discord_cfg.get("free_response_channels")
    if frc is not None and not os.getenv("DISCORD_FREE_RESPONSE_CHANNELS"):
        if isinstance(frc, list):
            frc = ",".join(str(v) for v in frc)
        os.environ["DISCORD_FREE_RESPONSE_CHANNELS"] = str(frc)
    if "auto_thread" in discord_cfg and not os.getenv("DISCORD_AUTO_THREAD"):
        os.environ["DISCORD_AUTO_THREAD"] = str(discord_cfg["auto_thread"]).lower()
    if "reactions" in discord_cfg and not os.getenv("DISCORD_REACTIONS"):
        os.environ["DISCORD_REACTIONS"] = str(discord_cfg["reactions"]).lower()
    # ignored_channels: channels where bot never responds (even when mentioned)
    ic = discord_cfg.get("ignored_channels")
    if ic is not None and not os.getenv("DISCORD_IGNORED_CHANNELS"):
        if isinstance(ic, list):
            ic = ",".join(str(v) for v in ic)
        os.environ["DISCORD_IGNORED_CHANNELS"] = str(ic)
    # allowed_channels: if set, bot ONLY responds in these channels (whitelist)
    ac = discord_cfg.get("allowed_channels")
    if ac is not None and not os.getenv("DISCORD_ALLOWED_CHANNELS"):
        if isinstance(ac, list):
            ac = ",".join(str(v) for v in ac)
        os.environ["DISCORD_ALLOWED_CHANNELS"] = str(ac)
    # no_thread_channels: channels where bot responds directly without creating thread
    ntc = discord_cfg.get("no_thread_channels")
    if ntc is not None and not os.getenv("DISCORD_NO_THREAD_CHANNELS"):
        if isinstance(ntc, list):
            ntc = ",".join(str(v) for v in ntc)
        os.environ["DISCORD_NO_THREAD_CHANNELS"] = str(ntc)
    # history_backfill: recover missed channel messages for shared sessions
    # when require_mention is active.  Fetches messages between bot turns
    # and prepends them to the user message for context.
    if "history_backfill" in discord_cfg and not os.getenv("DISCORD_HISTORY_BACKFILL"):
        os.environ["DISCORD_HISTORY_BACKFILL"] = str(discord_cfg["history_backfill"]).lower()
    hbl = discord_cfg.get("history_backfill_limit")
    if hbl is not None and not os.getenv("DISCORD_HISTORY_BACKFILL_LIMIT"):
        os.environ["DISCORD_HISTORY_BACKFILL_LIMIT"] = str(hbl)
    # allow_mentions: granular control over what the bot can ping.
    # Safe defaults (no @everyone/roles) are applied in the adapter;
    # these YAML keys only override when set and let users opt back
    # into unsafe modes (e.g. roles=true) if they actually want it.
    allow_mentions_cfg = discord_cfg.get("allow_mentions")
    if isinstance(allow_mentions_cfg, dict):
        for yaml_key, env_key in (
            ("everyone", "DISCORD_ALLOW_MENTION_EVERYONE"),
            ("roles", "DISCORD_ALLOW_MENTION_ROLES"),
            ("users", "DISCORD_ALLOW_MENTION_USERS"),
            ("replied_user", "DISCORD_ALLOW_MENTION_REPLIED_USER"),
        ):
            if yaml_key in allow_mentions_cfg and not os.getenv(env_key):
                os.environ[env_key] = str(allow_mentions_cfg[yaml_key]).lower()
    # reply_to_mode: top-level preferred, falls back to extra.reply_to_mode.
    # YAML 1.1 parses bare 'off' as boolean False — coerce to string "off".
    _discord_extra = discord_cfg.get("extra") if isinstance(discord_cfg.get("extra"), dict) else {}
    _discord_rtm = (
        discord_cfg["reply_to_mode"] if "reply_to_mode" in discord_cfg
        else _discord_extra.get("reply_to_mode")
    )
    if _discord_rtm is not None and not os.getenv("DISCORD_REPLY_TO_MODE"):
        _rtm_str = "off" if _discord_rtm is False else str(_discord_rtm).lower()
        os.environ["DISCORD_REPLY_TO_MODE"] = _rtm_str
    return None  # all settings flow through env; nothing to merge into extras

def _is_connected(config) -> bool:
    """Discord is considered connected when DISCORD_BOT_TOKEN is set.

    Looks up via ``miho_cli.gateway.get_env_value`` at call time (not via
    the plugin's own bound import) so tests that patch ``gateway_mod.get_env_value``
    — including ``test_setup_openclaw_migration`` — can suppress ambient
    ``DISCORD_BOT_TOKEN`` env vars. Matches what the legacy
    ``_PLATFORMS["discord"]`` dispatch did before this migration.
    """
    import miho_cli.gateway as gateway_mod
    return bool((gateway_mod.get_env_value("DISCORD_BOT_TOKEN") or "").strip())
