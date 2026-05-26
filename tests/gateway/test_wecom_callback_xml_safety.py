"""WeCom callback XML parsing safety checks."""

from __future__ import annotations

import pytest


def test_wecom_callback_uses_defused_xml_parser():
    from gateway.platforms import wecom_callback

    payload = """<?xml version="1.0"?>
<!DOCTYPE data [
<!ENTITY expand "blocked">
]>
<xml><ToUserName>&expand;</ToUserName></xml>
"""

    with pytest.raises(Exception):
        wecom_callback._parse_callback_xml(payload)


def test_wecom_callback_accepts_plain_xml():
    from gateway.platforms import wecom_callback

    root = wecom_callback._parse_callback_xml("<xml><MsgType>text</MsgType></xml>")

    assert root.findtext("MsgType") == "text"
