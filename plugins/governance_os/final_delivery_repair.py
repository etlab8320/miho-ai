"""Physical delivery repair executor for Governance OS artifacts."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from miho_constants import get_miho_home

RepairStatus = Literal["already_allowed", "repaired", "blocked"]
_MAX_REPAIR_BYTES = 100 * 1024 * 1024
_SENSITIVE_NAMES = {
    ".env",
    ".ssh",
    ".aws",
    ".gnupg",
    ".kube",
    ".docker",
    "credentials",
    "keychains",
}


@dataclass(frozen=True)
class FinalDeliveryRepairResult:
    status: RepairStatus
    artifact_path: str = ""
    staged_path: str = ""
    media_tag: str = ""
    delivery_text: str = ""
    message_ko: str = ""
    reviewer: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "artifact_path": self.artifact_path,
            "staged_path": self.staged_path,
            "media_tag": self.media_tag,
            "delivery_text": self.delivery_text,
            "message_ko": self.message_ko,
            "reviewer": self.reviewer,
        }


def repair_artifact_delivery(
    artifact_path: str,
    *,
    caption: str = "첨부 파일입니다.",
    staging_dir: Path | None = None,
) -> FinalDeliveryRepairResult:
    """Stage a real local artifact into Miho's media cache when needed."""

    clean_caption = caption.strip() or "첨부 파일입니다."
    already_allowed = _resolve_allowed(artifact_path)
    if already_allowed:
        return _passed(
            status="already_allowed",
            artifact_path=already_allowed,
            staged_path="",
            caption=clean_caption,
            checked=("artifact_path", "media_tag", "file_exists", "safe_delivery_path"),
        )

    source = _resolve_source_file(artifact_path)
    if source is None:
        return _blocked("첨부할 파일을 확인할 수 없습니다. 파일이 존재하고 일반 파일이어야 합니다.")
    if _is_sensitive_path(source):
        return _blocked("보안상 첨부할 수 없는 위치의 파일입니다.")
    try:
        size = source.stat().st_size
    except OSError:
        return _blocked("첨부할 파일 정보를 읽을 수 없습니다.")
    if size > _MAX_REPAIR_BYTES:
        return _blocked("첨부 파일이 너무 커서 자동 복구로 보낼 수 없습니다.")

    target_dir = staging_dir or get_miho_home() / "cache" / "media" / "governance_delivery"
    staged = _stage_file(source, target_dir)
    allowed_staged = _resolve_allowed(str(staged))
    if not allowed_staged:
        return _blocked("첨부 파일을 안전한 전송 폴더로 옮겼지만 전달 경로 검증에 실패했습니다.")
    return _passed(
        status="repaired",
        artifact_path=allowed_staged,
        staged_path=allowed_staged,
        caption=clean_caption,
        checked=(
            "artifact_path",
            "artifact_staged",
            "media_tag",
            "file_exists",
            "safe_delivery_path",
        ),
    )


def _resolve_allowed(path: str) -> str:
    try:
        from gateway.platforms.base import resolve_media_delivery_path

        return str(resolve_media_delivery_path(path) or "")
    except Exception:
        return ""


def _resolve_source_file(path: str) -> Path | None:
    raw = str(path or "").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "`\"'":
        raw = raw[1:-1].strip()
    if not raw:
        return None
    try:
        source = Path(raw).expanduser()
        if not source.is_absolute():
            return None
        if source.is_symlink():
            return None
        resolved = source.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _is_sensitive_path(path: Path) -> bool:
    lowered_parts = {part.casefold() for part in path.parts}
    if lowered_parts & _SENSITIVE_NAMES:
        return True
    if path.name.casefold().endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    return False


def _stage_file(source: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _staged_name(source)
    shutil.copy2(source, target)
    return target.resolve(strict=True)


def _staged_name(source: Path) -> str:
    stat = source.stat()
    digest = hashlib.sha256(
        f"{source.resolve(strict=False)}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()[:12]
    stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in source.stem)
    clean_stem = stem[:80].strip("._") or "artifact"
    suffix = source.suffix if len(source.suffix) <= 20 else ""
    return f"{clean_stem}-{digest}{suffix}"


def _passed(
    *,
    status: RepairStatus,
    artifact_path: str,
    staged_path: str,
    caption: str,
    checked: tuple[str, ...],
) -> FinalDeliveryRepairResult:
    media_tag = f"MEDIA:`{artifact_path}`"
    return FinalDeliveryRepairResult(
        status=status,
        artifact_path=artifact_path,
        staged_path=staged_path,
        media_tag=media_tag,
        delivery_text=f"{caption}\n{media_tag}",
        message_ko="첨부 파일 경로와 미디어 전달 지시를 복구했습니다.",
        reviewer={
            "name": "final_delivery_repair",
            "status": "pass",
            "checked": list(checked),
        },
    )


def _blocked(message_ko: str) -> FinalDeliveryRepairResult:
    return FinalDeliveryRepairResult(
        status="blocked",
        message_ko=message_ko,
        reviewer={
            "name": "final_delivery_repair",
            "status": "fail",
            "checked": ["artifact_path"],
        },
    )
