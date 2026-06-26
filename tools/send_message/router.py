"""Platform router for send_message."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def send_to_platform(platform, pconfig, chat_id, message, thread_id=None, media_files=None, force_document=False, *, senders: dict[str, Any]):
    """Route a message to the appropriate platform sender.

    Long messages are automatically chunked to fit within platform limits
    using the same smart-splitting algorithm as the gateway adapters
    (preserves code-block boundaries, adds part indicators).
    """
    _send_telegram = senders["send_telegram"]
    _send_weixin = senders["send_weixin"]
    _send_via_adapter = senders["send_via_adapter"]
    _send_matrix_via_adapter = senders["send_matrix_via_adapter"]
    _send_signal = senders["send_signal"]
    _send_yuanbao = senders["send_yuanbao"]
    _send_feishu = senders["send_feishu"]
    _send_slack = senders["send_slack"]
    _send_whatsapp = senders["send_whatsapp"]
    _send_email = senders["send_email"]
    _send_sms = senders["send_sms"]
    _send_mattermost = senders["send_mattermost"]
    _send_matrix = senders["send_matrix"]
    _send_homeassistant = senders["send_homeassistant"]
    _send_dingtalk = senders["send_dingtalk"]
    _send_wecom = senders["send_wecom"]
    _send_bluebubbles = senders["send_bluebubbles"]
    _send_qqbot = senders["send_qqbot"]

    from gateway.config import Platform
    from gateway.platforms.base import BasePlatformAdapter, utf16_len
    from gateway.platforms.slack import SlackAdapter

    # Telegram adapter import is optional (requires python-telegram-bot)
    try:
        from gateway.platforms.telegram import TelegramAdapter
        _telegram_available = True
    except ImportError:
        _telegram_available = False

    # Feishu adapter import is optional (requires lark-oapi)
    try:
        from gateway.platforms.feishu import FeishuAdapter
        _feishu_available = True
    except ImportError:
        _feishu_available = False

    media_files = media_files or []

    if platform == Platform.SLACK and message:
        try:
            slack_adapter = SlackAdapter.__new__(SlackAdapter)
            message = slack_adapter.format_message(message)
        except Exception:
            logger.debug("Failed to apply Slack mrkdwn formatting in _send_to_platform", exc_info=True)

    # Platform message length limits (from adapter class attributes for
    # built-in platforms; from PlatformEntry.max_message_length for plugins).
    _MAX_LENGTHS = {
        Platform.TELEGRAM: TelegramAdapter.MAX_MESSAGE_LENGTH if _telegram_available else 4096,
        Platform.SLACK: SlackAdapter.MAX_MESSAGE_LENGTH,
    }
    if _feishu_available:
        _MAX_LENGTHS[Platform.FEISHU] = FeishuAdapter.MAX_MESSAGE_LENGTH

    # Check plugin registry for max_message_length
    if platform not in _MAX_LENGTHS:
        try:
            from gateway.platform_registry import platform_registry
            entry = platform_registry.get(platform.value)
            if entry and entry.max_message_length > 0:
                _MAX_LENGTHS[platform] = entry.max_message_length
        except Exception:
            pass

    # Smart-chunk the message to fit within platform limits.
    # For short messages or platforms without a known limit this is a no-op.
    # Telegram measures length in UTF-16 code units, not Unicode codepoints.
    max_len = _MAX_LENGTHS.get(platform)
    if max_len:
        _len_fn = utf16_len if platform == Platform.TELEGRAM else None
        chunks = BasePlatformAdapter.truncate_message(message, max_len, len_fn=_len_fn)
    else:
        chunks = [message]

    # --- Telegram: special handling for media attachments ---
    if platform == Platform.TELEGRAM:
        last_result = None
        disable_link_previews = bool(getattr(pconfig, "extra", {}) and pconfig.extra.get("disable_link_previews"))
        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            result = await _send_telegram(
                pconfig.token,
                chat_id,
                chunk,
                media_files=media_files if is_last else [],
                thread_id=thread_id,
                disable_link_previews=disable_link_previews,
                force_document=force_document,
            )
            if isinstance(result, dict) and result.get("error"):
                return result
            last_result = result
        return last_result

    # --- Weixin: use the native one-shot adapter helper for text + media ---
    if platform == Platform.WEIXIN:
        return await _send_weixin(pconfig, chat_id, message, media_files=media_files)

    # --- Discord: prefer the live gateway adapter, then fall back to the
    # registry standalone sender for out-of-process CLI/cron calls.
    if platform == Platform.DISCORD:
        last_result = None
        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            result = await _send_via_adapter(
                platform,
                pconfig,
                chat_id,
                chunk,
                thread_id=thread_id,
                media_files=media_files if is_last else [],
                force_document=force_document,
            )
            if isinstance(result, dict) and result.get("error"):
                return result
            last_result = result
        return last_result

    # --- Matrix: use the native adapter helper when media is present ---
    if platform == Platform.MATRIX and media_files:
        last_result = None
        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            result = await _send_matrix_via_adapter(
                pconfig,
                chat_id,
                chunk,
                media_files=media_files if is_last else [],
                thread_id=thread_id,
            )
            if isinstance(result, dict) and result.get("error"):
                return result
            last_result = result
        return last_result

    # --- Signal: native attachment support via JSON-RPC attachments param ---
    if platform == Platform.SIGNAL and media_files:
        last_result = None
        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            result = await _send_signal(
                pconfig.extra,
                chat_id,
                chunk,
                media_files=media_files if is_last else [],
            )
            if isinstance(result, dict) and result.get("error"):
                return result
            last_result = result
        return last_result

    # --- Yuanbao: native media attachment support via running gateway adapter ---
    if platform == Platform.YUANBAO and media_files:
        last_result = None
        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            result = await _send_yuanbao(
                chat_id,
                chunk,
                media_files=media_files if is_last else None,
            )
            if isinstance(result, dict) and result.get("error"):
                return result
            last_result = result
        return last_result

    # --- Feishu: native media attachment support via adapter ---
    if platform == Platform.FEISHU and media_files:
        last_result = None
        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            result = await _send_feishu(
                pconfig,
                chat_id,
                chunk,
                media_files=media_files if is_last else None,
                thread_id=thread_id,
            )
            if isinstance(result, dict) and result.get("error"):
                return result
            last_result = result
        return last_result

    # --- Non-media platforms ---
    if media_files and not message.strip():
        return {
            "error": (
                f"send_message MEDIA delivery is currently only supported for telegram, discord, matrix, weixin, signal, yuanbao and feishu; "
                f"target {platform.value} had only media attachments"
            )
        }
    warning = None
    if media_files:
        warning = (
            f"MEDIA attachments were omitted for {platform.value}; "
            "native send_message media delivery is currently only supported for telegram, discord, matrix, weixin, signal, yuanbao and feishu"
        )

    last_result = None
    for chunk in chunks:
        if platform == Platform.SLACK:
            result = await _send_slack(pconfig.token, chat_id, chunk)
        elif platform == Platform.WHATSAPP:
            result = await _send_whatsapp(pconfig.extra, chat_id, chunk)
        elif platform == Platform.SIGNAL:
            result = await _send_signal(pconfig.extra, chat_id, chunk)
        elif platform == Platform.EMAIL:
            result = await _send_email(pconfig.extra, chat_id, chunk)
        elif platform == Platform.SMS:
            result = await _send_sms(pconfig.api_key, chat_id, chunk)
        elif platform == Platform.MATTERMOST:
            result = await _send_mattermost(pconfig.token, pconfig.extra, chat_id, chunk)
        elif platform == Platform.MATRIX:
            result = await _send_matrix(pconfig.token, pconfig.extra, chat_id, chunk)
        elif platform == Platform.HOMEASSISTANT:
            result = await _send_homeassistant(pconfig.token, pconfig.extra, chat_id, chunk)
        elif platform == Platform.DINGTALK:
            result = await _send_dingtalk(pconfig.extra, chat_id, chunk)
        elif platform == Platform.FEISHU:
            result = await _send_feishu(pconfig, chat_id, chunk, thread_id=thread_id)
        elif platform == Platform.WECOM:
            result = await _send_wecom(pconfig.extra, chat_id, chunk)
        elif platform == Platform.BLUEBUBBLES:
            result = await _send_bluebubbles(pconfig.extra, chat_id, chunk)
        elif platform == Platform.QQBOT:
            result = await _send_qqbot(pconfig, chat_id, chunk)
        elif platform == Platform.YUANBAO:
            result = await _send_yuanbao(chat_id, chunk)
        else:
            # Plugin platform: route through the gateway's live adapter if
            # available, otherwise the plugin's standalone_sender_fn.
            result = await _send_via_adapter(
                platform,
                pconfig,
                chat_id,
                chunk,
                thread_id=thread_id,
                media_files=media_files,
                force_document=force_document,
            )

        if isinstance(result, dict) and result.get("error"):
            return result
        last_result = result

    if warning and isinstance(last_result, dict) and last_result.get("success"):
        warnings = list(last_result.get("warnings", []))
        warnings.append(warning)
        last_result["warnings"] = warnings
    return last_result
