"""Academy request rewrite guard.

Natural-language PACA/Peak requests must stay in the LLM loop so the model can
resolve intent and dates into explicit tool arguments. This module intentionally
does not parse Korean phrases or rewrite free-form messages.
"""

from __future__ import annotations


def quick_command_for(text: str) -> str:
    return ""


def classify_quick_operation(text: str) -> str:
    return ""
