"""Governed media delivery contract tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gateway.platforms.base import resolve_media_delivery_path
from plugins.governance_os.final_delivery_repair import repair_artifact_delivery
from tools.registry import registry, tool_result


MEDIA_DELIVERY_CONTRACT_SCHEMA = {
    "name": "media_delivery_contract",
    "description": (
        "Validate a generated local artifact before Discord/gateway delivery. "
        "Returns a reviewed MEDIA directive and attachment_delivery_review payload."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "artifact_path": {
                "type": "string",
                "description": "Local artifact path to deliver as a native attachment.",
            },
            "caption": {
                "type": "string",
                "description": "Short Korean message to send with the attachment.",
            },
        },
        "required": ["artifact_path"],
    },
}


def media_delivery_contract_tool(args: dict[str, Any]) -> str:
    artifact_path = str(args.get("artifact_path") or "").strip()
    caption = str(args.get("caption") or "첨부 파일입니다.").strip()
    if not artifact_path:
        return _failed("첨부할 파일 경로가 비어 있습니다.")

    resolved_path = resolve_media_delivery_path(artifact_path)
    if not resolved_path:
        repair = repair_artifact_delivery(artifact_path, caption=caption)
        if repair.status == "blocked":
            return _failed(repair.message_ko, artifact_path=artifact_path)
        return tool_result(
            success=True,
            artifact_path=repair.artifact_path,
            file_name=Path(repair.artifact_path).name,
            media_tag=repair.media_tag,
            delivery_text=repair.delivery_text,
            delivery_repair=repair.to_dict(),
            reviewer=repair.reviewer,
            message_ko=repair.message_ko,
        )

    media_tag = f"MEDIA:`{resolved_path}`"
    return tool_result(
        success=True,
        artifact_path=resolved_path,
        file_name=Path(resolved_path).name,
        media_tag=media_tag,
        delivery_text=f"{caption}\n{media_tag}",
        reviewer={
            "name": "attachment_delivery_review",
            "status": "pass",
            "checked": [
                "artifact_path",
                "media_tag",
                "file_exists",
                "safe_delivery_path",
            ],
            "evidence_required": True,
        },
        message_ko="첨부 파일 경로와 미디어 전달 지시를 확인했습니다.",
    )


def _failed(message_ko: str, *, artifact_path: str = "") -> str:
    return tool_result(
        success=False,
        artifact_path=artifact_path,
        message_ko=message_ko,
        errors=[message_ko],
        reviewer={
            "name": "attachment_delivery_review",
            "status": "fail",
            "checked": ["artifact_path"],
        },
    )


def check_media_delivery_contract_requirements() -> bool:
    return True


registry.register(
    name="media_delivery_contract",
    toolset="governance",
    schema=MEDIA_DELIVERY_CONTRACT_SCHEMA,
    handler=lambda args, **kw: media_delivery_contract_tool(args),
    check_fn=check_media_delivery_contract_requirements,
    emoji="GOV",
)
