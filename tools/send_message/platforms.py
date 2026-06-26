"""HTTP and adapter senders for less stateful send_message platforms."""

from __future__ import annotations

import json
import os
import ssl
import time
from email.utils import formatdate
from pathlib import Path
from typing import Dict, Optional

from .common import _error


async def _send_slack(token, chat_id, message):
    """Send via Slack Web API."""
    try:
        import aiohttp
    except ImportError:
        return {"error": "aiohttp not installed. Run: pip install aiohttp"}
    try:
        from gateway.platforms.base import resolve_proxy_url, proxy_kwargs_for_aiohttp
        _proxy = resolve_proxy_url()
        _sess_kw, _req_kw = proxy_kwargs_for_aiohttp(_proxy)
        url = "https://slack.com/api/chat.postMessage"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), **_sess_kw) as session:
            payload = {"channel": chat_id, "text": message, "mrkdwn": True}
            async with session.post(url, headers=headers, json=payload, **_req_kw) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return {"success": True, "platform": "slack", "chat_id": chat_id, "message_id": data.get("ts")}
                return _error(f"Slack API error: {data.get('error', 'unknown')}")
    except Exception as e:
        return _error(f"Slack send failed: {e}")


async def _send_whatsapp(extra, chat_id, message):
    """Send via the local WhatsApp bridge HTTP API."""
    try:
        import aiohttp
    except ImportError:
        return {"error": "aiohttp not installed. Run: pip install aiohttp"}
    try:
        bridge_port = extra.get("bridge_port", 3000)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://localhost:{bridge_port}/send",
                json={"chatId": chat_id, "message": message},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "success": True,
                        "platform": "whatsapp",
                        "chat_id": chat_id,
                        "message_id": data.get("messageId"),
                    }
                body = await resp.text()
                return _error(f"WhatsApp bridge error ({resp.status}): {body}")
    except Exception as e:
        return _error(f"WhatsApp send failed: {e}")


async def _send_email(extra, chat_id, message):
    """Send via SMTP (one-shot, no persistent connection needed)."""
    import smtplib
    from email.mime.text import MIMEText
    from email.utils import formatdate

    address = extra.get("address") or os.getenv("EMAIL_ADDRESS", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    smtp_host = extra.get("smtp_host") or os.getenv("EMAIL_SMTP_HOST", "")
    try:
        smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    except (ValueError, TypeError):
        smtp_port = 587

    if not all([address, password, smtp_host]):
        return {"error": "Email not configured (EMAIL_ADDRESS, EMAIL_PASSWORD, EMAIL_SMTP_HOST required)"}

    try:
        msg = MIMEText(message, "plain", "utf-8")
        msg["From"] = address
        msg["To"] = chat_id
        msg["Subject"] = "Miho Agent"
        msg["Date"] = formatdate(localtime=True)

        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls(context=ssl.create_default_context())
        server.login(address, password)
        server.send_message(msg)
        server.quit()
        return {"success": True, "platform": "email", "chat_id": chat_id}
    except Exception as e:
        return _error(f"Email send failed: {e}")


async def _send_sms(auth_token, chat_id, message):
    """Send a single SMS via Twilio REST API.

    Uses HTTP Basic auth (Account SID : Auth Token) and form-encoded POST.
    Chunking is handled by _send_to_platform() before this is called.
    """
    try:
        import aiohttp
    except ImportError:
        return {"error": "aiohttp not installed. Run: pip install aiohttp"}

    import base64

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    from_number = os.getenv("TWILIO_PHONE_NUMBER", "")
    if not account_sid or not auth_token or not from_number:
        return {"error": "SMS not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER required)"}

    # Strip markdown — SMS renders it as literal characters
    message = re.sub(r"\*\*(.+?)\*\*", r"\1", message, flags=re.DOTALL)
    message = re.sub(r"\*(.+?)\*", r"\1", message, flags=re.DOTALL)
    message = re.sub(r"__(.+?)__", r"\1", message, flags=re.DOTALL)
    message = re.sub(r"_(.+?)_", r"\1", message, flags=re.DOTALL)
    message = re.sub(r"```[a-z]*\n?", "", message)
    message = re.sub(r"`(.+?)`", r"\1", message)
    message = re.sub(r"^#{1,6}\s+", "", message, flags=re.MULTILINE)
    message = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", message)
    message = re.sub(r"\n{3,}", "\n\n", message)
    message = message.strip()

    try:
        from gateway.platforms.base import resolve_proxy_url, proxy_kwargs_for_aiohttp
        _proxy = resolve_proxy_url()
        _sess_kw, _req_kw = proxy_kwargs_for_aiohttp(_proxy)
        creds = f"{account_sid}:{auth_token}"
        encoded = base64.b64encode(creds.encode("ascii")).decode("ascii")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        headers = {"Authorization": f"Basic {encoded}"}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), **_sess_kw) as session:
            form_data = aiohttp.FormData()
            form_data.add_field("From", from_number)
            form_data.add_field("To", chat_id)
            form_data.add_field("Body", message)

            async with session.post(url, data=form_data, headers=headers, **_req_kw) as resp:
                body = await resp.json()
                if resp.status >= 400:
                    error_msg = body.get("message", str(body))
                    return _error(f"Twilio API error ({resp.status}): {error_msg}")
                msg_sid = body.get("sid", "")
                return {"success": True, "platform": "sms", "chat_id": chat_id, "message_id": msg_sid}
    except Exception as e:
        return _error(f"SMS send failed: {e}")


async def _send_mattermost(token, extra, chat_id, message):
    """Send via Mattermost REST API."""
    try:
        import aiohttp
    except ImportError:
        return {"error": "aiohttp not installed. Run: pip install aiohttp"}
    try:
        base_url = (extra.get("url") or os.getenv("MATTERMOST_URL", "")).rstrip("/")
        token = token or os.getenv("MATTERMOST_TOKEN", "")
        if not base_url or not token:
            return {"error": "Mattermost not configured (MATTERMOST_URL, MATTERMOST_TOKEN required)"}
        url = f"{base_url}/api/v4/posts"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.post(url, headers=headers, json={"channel_id": chat_id, "message": message}) as resp:
                if resp.status not in {200, 201}:
                    body = await resp.text()
                    return _error(f"Mattermost API error ({resp.status}): {body}")
                data = await resp.json()
        return {"success": True, "platform": "mattermost", "chat_id": chat_id, "message_id": data.get("id")}
    except Exception as e:
        return _error(f"Mattermost send failed: {e}")


async def _send_homeassistant(token, extra, chat_id, message):
    """Send via Home Assistant notify service."""
    try:
        import aiohttp
    except ImportError:
        return {"error": "aiohttp not installed. Run: pip install aiohttp"}
    try:
        hass_url = (extra.get("url") or os.getenv("HASS_URL", "")).rstrip("/")
        token = token or os.getenv("HASS_TOKEN", "")
        if not hass_url or not token:
            return {"error": "Home Assistant not configured (HASS_URL, HASS_TOKEN required)"}
        url = f"{hass_url}/api/services/notify/notify"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.post(url, headers=headers, json={"message": message, "target": chat_id}) as resp:
                if resp.status not in {200, 201}:
                    body = await resp.text()
                    return _error(f"Home Assistant API error ({resp.status}): {body}")
        return {"success": True, "platform": "homeassistant", "chat_id": chat_id}
    except Exception as e:
        return _error(f"Home Assistant send failed: {e}")


async def _send_dingtalk(extra, chat_id, message):
    """Send via DingTalk robot webhook.

    Note: The gateway's DingTalk adapter uses per-session webhook URLs from
    incoming messages (dingtalk-stream SDK).  For cross-platform send_message
    delivery we use a static robot webhook URL instead, which must be
    configured via ``DINGTALK_WEBHOOK_URL`` env var or ``webhook_url`` in the
    platform's extra config.
    """
    try:
        import httpx
    except ImportError:
        return {"error": "httpx not installed"}
    try:
        webhook_url = extra.get("webhook_url") or os.getenv("DINGTALK_WEBHOOK_URL", "")
        if not webhook_url:
            return {"error": "DingTalk not configured. Set DINGTALK_WEBHOOK_URL env var or webhook_url in dingtalk platform extra config."}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                webhook_url,
                json={"msgtype": "text", "text": {"content": message}},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode", 0) != 0:
                return _error(f"DingTalk API error: {data.get('errmsg', 'unknown')}")
        return {"success": True, "platform": "dingtalk", "chat_id": chat_id}
    except Exception as e:
        return _error(f"DingTalk send failed: {e}")


async def _send_wecom(extra, chat_id, message):
    """Send via WeCom using the adapter's WebSocket send pipeline."""
    try:
        from gateway.platforms.wecom import WeComAdapter, check_wecom_requirements
        if not check_wecom_requirements():
            return {"error": "WeCom requirements not met. Need aiohttp + WECOM_BOT_ID/SECRET."}
    except ImportError:
        return {"error": "WeCom adapter not available."}

    try:
        from gateway.config import PlatformConfig
        pconfig = PlatformConfig(extra=extra)
        adapter = WeComAdapter(pconfig)
        connected = await adapter.connect()
        if not connected:
            return _error(f"WeCom: failed to connect - {adapter.fatal_error_message or 'unknown error'}")
        try:
            result = await adapter.send(chat_id, message)
            if not result.success:
                return _error(f"WeCom send failed: {result.error}")
            return {"success": True, "platform": "wecom", "chat_id": chat_id, "message_id": result.message_id}
        finally:
            await adapter.disconnect()
    except Exception as e:
        return _error(f"WeCom send failed: {e}")


async def _send_weixin(pconfig, chat_id, message, media_files=None):
    """Send via Weixin iLink using the native adapter helper."""
    try:
        from gateway.platforms.weixin import check_weixin_requirements, send_weixin_direct
        if not check_weixin_requirements():
            return {"error": "Weixin requirements not met. Need aiohttp + cryptography."}
    except ImportError:
        return {"error": "Weixin adapter not available."}

    try:
        return await send_weixin_direct(
            extra=pconfig.extra,
            token=pconfig.token,
            chat_id=chat_id,
            message=message,
            media_files=media_files,
        )
    except Exception as e:
        return _error(f"Weixin send failed: {e}")


async def _send_bluebubbles(extra, chat_id, message):
    """Send via BlueBubbles iMessage server using the adapter's REST API."""
    try:
        from gateway.platforms.bluebubbles import BlueBubblesAdapter, check_bluebubbles_requirements
        if not check_bluebubbles_requirements():
            return {"error": "BlueBubbles requirements not met (need aiohttp + httpx)."}
    except ImportError:
        return {"error": "BlueBubbles adapter not available."}

    try:
        from gateway.config import PlatformConfig
        pconfig = PlatformConfig(extra=extra)
        adapter = BlueBubblesAdapter(pconfig)
        connected = await adapter.connect()
        if not connected:
            return _error("BlueBubbles: failed to connect to server")
        try:
            result = await adapter.send(chat_id, message)
            if not result.success:
                return _error(f"BlueBubbles send failed: {result.error}")
            return {"success": True, "platform": "bluebubbles", "chat_id": chat_id, "message_id": result.message_id}
        finally:
            await adapter.disconnect()
    except Exception as e:
        return _error(f"BlueBubbles send failed: {e}")


async def _send_feishu(pconfig, chat_id, message, media_files=None, thread_id=None):
    """Send via Feishu/Lark using the adapter's send pipeline."""
    try:
        from gateway.platforms.feishu import FeishuAdapter, FEISHU_AVAILABLE
        if not FEISHU_AVAILABLE:
            return {"error": "Feishu dependencies not installed. Run: pip install 'miho-agent[feishu]'"}
        from gateway.platforms.feishu import FEISHU_DOMAIN, LARK_DOMAIN
    except ImportError:
        return {"error": "Feishu dependencies not installed. Run: pip install 'miho-agent[feishu]'"}

    media_files = media_files or []

    try:
        adapter = FeishuAdapter(pconfig)
        domain_name = getattr(adapter, "_domain_name", "feishu")
        domain = FEISHU_DOMAIN if domain_name != "lark" else LARK_DOMAIN
        adapter._client = adapter._build_lark_client(domain)
        metadata = {"thread_id": thread_id} if thread_id else None

        last_result = None
        if message.strip():
            last_result = await adapter.send(chat_id, message, metadata=metadata)
            if not last_result.success:
                return _error(f"Feishu send failed: {last_result.error}")

        for media_path, is_voice in media_files:
            if not os.path.exists(media_path):
                return _error(f"Media file not found: {media_path}")

            ext = os.path.splitext(media_path)[1].lower()
            if ext in _IMAGE_EXTS:
                last_result = await adapter.send_image_file(chat_id, media_path, metadata=metadata)
            elif ext in _VIDEO_EXTS:
                last_result = await adapter.send_video(chat_id, media_path, metadata=metadata)
            elif ext in _VOICE_EXTS and is_voice:
                last_result = await adapter.send_voice(chat_id, media_path, metadata=metadata)
            elif ext in _AUDIO_EXTS:
                last_result = await adapter.send_voice(chat_id, media_path, metadata=metadata)
            else:
                last_result = await adapter.send_document(chat_id, media_path, metadata=metadata)

            if not last_result.success:
                return _error(f"Feishu media send failed: {last_result.error}")

        if last_result is None:
            return {"error": "No deliverable text or media remained after processing MEDIA tags"}

        return {
            "success": True,
            "platform": "feishu",
            "chat_id": chat_id,
            "message_id": last_result.message_id,
        }
    except Exception as e:
        return _error(f"Feishu send failed: {e}")


async def _send_qqbot(pconfig, chat_id, message):
    """Send via QQBot using the REST API directly (no WebSocket needed).

    Uses the QQ Bot Open Platform REST endpoints to get an access token
    and post a message. Supports guild channels, C2C (private) chats,
    and group chats by trying the appropriate endpoints.
    """
    try:
        import httpx
    except ImportError:
        return _error("QQBot direct send requires httpx. Run: pip install httpx")

    extra = pconfig.extra or {}
    appid = extra.get("app_id") or os.getenv("QQ_APP_ID", "")
    secret = (pconfig.token or extra.get("client_secret")
              or os.getenv("QQ_CLIENT_SECRET", ""))
    if not appid or not secret:
        return _error("QQBot: QQ_APP_ID / QQ_CLIENT_SECRET not configured.")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Step 1: Get access token
            token_resp = await client.post(
                "https://bots.qq.com/app/getAppAccessToken",
                json={"appId": str(appid), "clientSecret": str(secret)},
            )
            if token_resp.status_code != 200:
                return _error(f"QQBot token request failed: {token_resp.status_code}")
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                return _error(f"QQBot: no access_token in response")

            # Step 2: Send message via REST
            # QQ Bot API has separate endpoints for channels, C2C, and groups.
            # We try them in order: channel first, then fallback to C2C.
            headers = {
                "Authorization": f"QQBot {access_token}",
                "Content-Type": "application/json",
            }
            payload = {"content": message[:4000], "msg_type": 0}

            # Try channel endpoint first (works for guild channels)
            url = f"https://api.sgroup.qq.com/channels/{chat_id}/messages"
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in {200, 201}:
                data = resp.json()
                return {"success": True, "platform": "qqbot", "chat_id": chat_id,
                        "message_id": data.get("id")}

            # If channel endpoint failed (likely "频道不存在"), try C2C endpoint
            url_c2c = f"https://api.sgroup.qq.com/v2/users/{chat_id}/messages"
            resp_c2c = await client.post(url_c2c, json=payload, headers=headers)
            if resp_c2c.status_code in {200, 201}:
                data = resp_c2c.json()
                return {"success": True, "platform": "qqbot", "chat_id": chat_id,
                        "message_id": data.get("id")}

            # If C2C also failed, try group endpoint
            url_group = f"https://api.sgroup.qq.com/v2/groups/{chat_id}/messages"
            resp_group = await client.post(url_group, json=payload, headers=headers)
            if resp_group.status_code in {200, 201}:
                data = resp_group.json()
                return {"success": True, "platform": "qqbot", "chat_id": chat_id,
                        "message_id": data.get("id")}

            # All endpoints failed — return the most informative error
            return _error(f"QQBot send failed: channel={resp.status_code} c2c={resp_c2c.status_code} group={resp_group.status_code}")
    except Exception as e:
        return _error(f"QQBot send failed: {e}")


async def _send_yuanbao(chat_id, message, media_files=None):
    """Send via Yuanbao using the running gateway adapter's WebSocket connection.

    Yuanbao uses a persistent WebSocket — unlike HTTP-based platforms, we
    cannot create a throwaway client.  We obtain the running singleton from
    the adapter module itself (``get_active_adapter``).

    chat_id format:
      - Group: "group:<group_code>"
      - DM:    "direct:<account_id>" or just "<account_id>"
    """
    try:
        from gateway.platforms.yuanbao import get_active_adapter, send_yuanbao_direct
    except ImportError:
        return _error("Yuanbao adapter module not available.")

    adapter = get_active_adapter()
    if adapter is None:
        return _error(
            "Yuanbao adapter is not running. "
            "Start the gateway with yuanbao platform enabled first."
        )

    try:
        return await send_yuanbao_direct(adapter, chat_id, message, media_files=media_files)
    except Exception as e:
        return _error(f"Yuanbao send failed: {e}")
