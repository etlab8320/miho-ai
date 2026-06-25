"""Shared attachment extension policy for gateway delivery paths."""

from __future__ import annotations

ATTACHMENT_EXTENSIONS = (
    # Images
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".svg",
    # Video
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    # Audio
    ".ogg",
    ".opus",
    ".mp3",
    ".wav",
    ".m4a",
    ".flac",
    # Documents
    ".epub",
    ".pdf",
    ".doc",
    ".docx",
    ".odt",
    ".rtf",
    ".txt",
    ".md",
    ".hwp",
    ".hwpx",
    ".pages",
    # Spreadsheets / data
    ".xls",
    ".xlsx",
    ".ods",
    ".csv",
    ".tsv",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".numbers",
    # Presentations
    ".ppt",
    ".pptx",
    ".odp",
    ".key",
    # Archives
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    # Mobile packages
    ".apk",
    ".ipa",
    # Web / rendered output
    ".html",
    ".htm",
    ".mhtml",
    ".mht",
)

ADDITIONAL_DOCUMENT_MIME_TYPES = {
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
    ".ppt": "application/vnd.ms-powerpoint",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".rtf": "application/rtf",
    ".tsv": "text/tab-separated-values",
    ".html": "text/html",
    ".htm": "text/html",
    ".mhtml": "message/rfc822",
    ".mht": "message/rfc822",
    ".hwp": "application/x-hwp",
    ".hwpx": "application/vnd.hancom.hwpx",
    ".pages": "application/vnd.apple.pages",
    ".numbers": "application/vnd.apple.numbers",
    ".key": "application/vnd.apple.keynote",
    ".epub": "application/epub+zip",
    ".rar": "application/vnd.rar",
    ".7z": "application/x-7z-compressed",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".tgz": "application/gzip",
    ".bz2": "application/x-bzip2",
    ".xz": "application/x-xz",
}

ATTACHMENT_EXTENSION_PATTERN = "|".join(
    sorted((extension.lstrip(".") for extension in ATTACHMENT_EXTENSIONS), key=len, reverse=True)
)
