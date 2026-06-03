"""Auto-approval classifier for read-only gateway terminal commands."""

from __future__ import annotations

import re
from collections.abc import Iterable


AUTO_APPROVABLE_WARNING_DESCRIPTIONS = frozenset({
    "shell command via -c/-lc flag",
    "script execution via -e/-c flag",
    "script execution via heredoc",
})

_MUTATING_COMMAND_RE = re.compile(
    r"\b("
    r"rm|mv|cp|install|chmod|chown|mkfs|dd|sudo|systemctl|service|"
    r"kill|pkill|killall|shutdown|reboot|halt|poweroff"
    r")\b",
    re.IGNORECASE,
)
_GIT_MUTATION_RE = re.compile(
    r"\bgit\s+(reset|push|clean|branch\s+-D|checkout|switch|merge|rebase)\b",
    re.IGNORECASE,
)
_SQL_MUTATION_RE = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|UPDATE|INSERT|ALTER|CREATE)\b",
    re.IGNORECASE,
)
_HTTP_MUTATION_RE = re.compile(
    r"(?:\brequests\.(?:post|put|patch|delete)\b|"
    r"\bcurl\b[^\n]*\s-X\s*(?:POST|PUT|PATCH|DELETE)\b|"
    r"\bwget\b[^\n]*\s--method\s*=\s*(?:POST|PUT|PATCH|DELETE)\b)",
    re.IGNORECASE,
)
_PYTHON_WRITE_API_RE = re.compile(
    r"\b(write_text|write_bytes|writelines|truncate|unlink|rename|replace|"
    r"mkdir|rmdir|remove|rmtree)\s*\(",
    re.IGNORECASE,
)
_PYTHON_OPEN_WRITE_RE = re.compile(
    r"\bopen\s*\([^\n)]*(?:,\s*['\"][wa+x]|mode\s*=\s*['\"][wa+x])",
    re.IGNORECASE,
)
_SHELL_REDIRECT_WRITE_RE = re.compile(
    r"(?<!<)>{1,2}\s*(?!&|/dev/null(?:\s|['\"]|$))",
    re.IGNORECASE,
)
_TEE_WRITE_RE = re.compile(r"\btee\b", re.IGNORECASE)
_SENSITIVE_PATH_RE = re.compile(
    r"(?:/etc/|/private/etc/|/dev/sd|/dev/nvme|"
    r"(?:~|\$HOME|\$\{HOME\})/\.ssh|"
    r"(?:~|\.{0,2}/|\$HOME|\$\{HOME\})?\.env(?:\.[^\s/'\"]*)?|"
    r"config\.yaml)",
    re.IGNORECASE,
)
_FILE_OUTPUT_API_RE = re.compile(
    r"\b(savefig|to_csv|to_excel|to_json|to_parquet|write_text|write_bytes|open)\s*\(",
    re.IGNORECASE,
)


def should_auto_approve_gateway_command(
    command: str,
    warning_descriptions: Iterable[str],
) -> bool:
    """Return True for gateway commands that are read-only/tool-output work.

    This intentionally handles only approval warnings caused by wrapper script
    execution. Real mutation findings must continue through normal approval.
    """
    descriptions = {str(desc) for desc in warning_descriptions}
    if not descriptions:
        return False
    if not descriptions <= AUTO_APPROVABLE_WARNING_DESCRIPTIONS:
        return False

    return not _contains_mutation_signal(command)


def _contains_mutation_signal(command: str) -> bool:
    if _MUTATING_COMMAND_RE.search(command):
        return True
    if _GIT_MUTATION_RE.search(command):
        return True
    if _SQL_MUTATION_RE.search(command):
        return True
    if _HTTP_MUTATION_RE.search(command):
        return True
    if _PYTHON_WRITE_API_RE.search(command):
        return True
    if _PYTHON_OPEN_WRITE_RE.search(command):
        return True
    if _SHELL_REDIRECT_WRITE_RE.search(command):
        return True
    if _TEE_WRITE_RE.search(command):
        return True
    if _SENSITIVE_PATH_RE.search(command) and _FILE_OUTPUT_API_RE.search(command):
        return True
    return False
