"""Single-camera sports video analysis provider wrapper."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .catalog import normalize_exercise

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
DEFAULT_TIMEOUT_SECONDS = 900


def video_analysis_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    return json.dumps(build_video_analysis(args or {}), ensure_ascii=False)


def provider_status_payload() -> dict[str, Any]:
    providers = _provider_catalog()
    return {
        "ok": True,
        "schema_version": 1,
        "providers": providers,
        "recommended_default": "sports2d_rtmpose_2d",
        "single_camera_limitations": _single_camera_limitations(),
        "free_research_sources": _free_research_sources(),
    }


def build_video_analysis(
    args: dict[str, Any],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    student_name = str(args.get("student_name") or args.get("student_query") or "학생").strip()
    exercise = normalize_exercise(args.get("exercise"))
    video_path = _path_or_none(args.get("video_path"))
    provider_key = str(args.get("provider") or "auto").strip() or "auto"
    execute = _coerce_bool(args.get("execute"), default=False)

    errors = _validate_analysis_request(student_name, exercise, video_path)
    if errors:
        return {"ok": False, "errors": errors, "provider_status": provider_status_payload()}
    assert exercise is not None
    assert video_path is not None

    providers = _provider_catalog()
    selected_key = _select_provider(provider_key, providers)
    if selected_key is None:
        return {
            "ok": False,
            "errors": [_provider_error(provider_key, providers)],
            "provider_status": provider_status_payload(),
        }

    provider = providers[selected_key]
    output_dir = _output_dir(args, video_path)
    command = _sports2d_command(args, video_path=video_path, output_dir=output_dir)
    base_payload = _base_analysis_payload(
        student_name=student_name,
        exercise=exercise,
        video_path=video_path,
        output_dir=output_dir,
        provider=provider,
        command=command,
        execute=execute,
    )
    if not execute:
        return base_payload

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        base_payload["analysis_status"] = "failed"
        base_payload["ok"] = False
        base_payload["errors"] = [f"분석 결과 폴더를 만들 수 없다: {type(exc).__name__}"]
        return base_payload
    try:
        run = _run_command(command, runner=runner, timeout_seconds=_timeout_seconds(args))
    except subprocess.TimeoutExpired:
        base_payload["analysis_status"] = "failed"
        base_payload["ok"] = False
        base_payload["errors"] = ["영상 분석 시간이 초과됐다. 짧은 time_range를 지정하거나 영상 길이/해상도를 줄여야 한다."]
        return base_payload
    except OSError as exc:
        base_payload["analysis_status"] = "failed"
        base_payload["ok"] = False
        base_payload["errors"] = [f"영상 분석 실행 파일을 시작하지 못했다: {type(exc).__name__}"]
        return base_payload
    base_payload["analysis_status"] = "completed" if run.returncode == 0 else "failed"
    base_payload["ok"] = run.returncode == 0
    base_payload["diagnostics"] = _process_diagnostics(run)
    base_payload["output_files"] = _collect_output_files(output_dir)
    if run.returncode != 0:
        base_payload["errors"] = ["영상 분석 실행이 실패했다. 촬영 파일, 코덱, Sports2D 설치 상태를 확인해야 한다."]
    return base_payload


def _base_analysis_payload(
    *,
    student_name: str,
    exercise: dict[str, Any],
    video_path: Path,
    output_dir: Path,
    provider: dict[str, Any],
    command: list[str],
    execute: bool,
) -> dict[str, Any]:
    return {
        "ok": True,
        "schema_version": 1,
        "analysis_status": "ready_to_execute" if not execute else "running_or_completed",
        "student_name": student_name,
        "exercise": exercise,
        "video_path": str(video_path),
        "output_dir": str(output_dir),
        "provider": provider,
        "command_preview": command,
        "measurement_contract": {
            "dimension": "2d_single_camera",
            "camera_view": "side_or_front_fixed_plane",
            "warnings": ["not_3d_verified", "camera_angle_sensitive", "trend_more_reliable_than_absolute_value"],
            "required_result_use": "sports_motion_feedback로 넘기기 전 각도값과 촬영조건을 같이 보낸다.",
        },
        "single_camera_limitations": _single_camera_limitations(),
        "feedback_next_step": {
            "tool": "sports_motion_feedback",
            "source": "sports2d_rtmpose_2d",
            "note": "생성된 각도 파일 또는 수동 검토 지표를 metrics로 넣어 코치/리뷰어 검수를 태운다.",
        },
    }


def _provider_catalog() -> dict[str, dict[str, Any]]:
    sports2d_cli = _find_executable("sports2d")
    sports2d_ready = all(
        (
            _is_module_available("Sports2D"),
            _is_module_available("rtmlib"),
            _is_module_available("cv2"),
            bool(sports2d_cli),
        )
    )
    rtmpose_ready = _is_module_available("rtmlib") and _is_module_available("cv2")
    return {
        "sports2d_rtmpose_2d": {
            "key": "sports2d_rtmpose_2d",
            "available": sports2d_ready,
            "runnable": sports2d_ready,
            "cost": "free_open_source",
            "engine": "Sports2D CLI with RTMLib/RTMPose backend",
            "executable": sports2d_cli or "",
            "best_for": ["제자리멀리뛰기 측면", "좌전굴 측면", "기본 관절각/궤적 리포트"],
            "limitations": _single_camera_limitations(),
        },
        "rtmpose_keypoints_2d": {
            "key": "rtmpose_keypoints_2d",
            "available": rtmpose_ready,
            "runnable": False,
            "cost": "free_open_source",
            "engine": "RTMLib/RTMPose keypoint inference",
            "executable": "",
            "best_for": ["향후 커스텀 경량 분석", "실시간 키포인트 추출"],
            "limitations": ["현재 미호 도구에서는 Sports2D 파이프라인의 pose engine으로 우선 사용한다."],
        },
        "mmpose_full": {
            "key": "mmpose_full",
            "available": _is_module_available("mmpose"),
            "runnable": False,
            "cost": "free_open_source",
            "engine": "OpenMMLab MMPose",
            "executable": "",
            "best_for": ["연구/학습용 모델 교체", "커스텀 모델 실험"],
            "limitations": ["Mac mini 운영에는 무거워서 기본 설치 대상이 아니다."],
        },
        "vendor_api": {
            "key": "vendor_api",
            "available": False,
            "runnable": False,
            "cost": "contract_pending",
            "engine": "future external motion-analysis API",
            "executable": "",
            "best_for": ["업체 PDF/API 수신 후 학생별 자동 피드백"],
            "limitations": ["API 계약 전까지는 사용하지 않는다."],
        },
    }


def _sports2d_command(args: dict[str, Any], *, video_path: Path, output_dir: Path) -> list[str]:
    visible_side = _visible_side(args.get("visible_side") or args.get("camera_view"))
    pose_model = str(args.get("pose_model") or "body_with_feet")
    mode = _mode(args.get("mode"))
    person_ordering = str(args.get("person_ordering_method") or "highest_likelihood")
    nb_persons = str(args.get("nb_persons_to_detect") or "1")
    command = [
        _find_executable("sports2d") or "sports2d",
        "--video_input",
        str(video_path),
        "--result_dir",
        str(output_dir),
        "--show_realtime_results",
        "false",
        "--show_graphs",
        "false",
        "--save_vid",
        "false",
        "--save_img",
        "false",
        "--save_pose",
        "true",
        "--calculate_angles",
        "true",
        "--save_angles",
        "true",
        "--pose_model",
        pose_model,
        "--mode",
        mode,
        "--person_ordering_method",
        person_ordering,
        "--nb_persons_to_detect",
        nb_persons,
        "--visible_side",
        visible_side,
    ]
    time_range = args.get("time_range")
    if isinstance(time_range, list) and len(time_range) == 2:
        command.extend(["--time_range", str(time_range[0]), str(time_range[1])])
    return command


def _validate_analysis_request(
    student_name: str,
    exercise: dict[str, Any] | None,
    video_path: Path | None,
) -> list[str]:
    errors: list[str] = []
    if exercise is None:
        errors.append("지원하지 않는 종목이다. sports_motion_schema로 종목명을 확인해라.")
    if video_path is None:
        errors.append("video_path가 필요하다.")
    elif not video_path.exists():
        errors.append("영상 파일을 찾을 수 없다. 업로드된 로컬 경로나 첨부 저장 경로를 확인해라.")
    elif video_path.suffix.lower() not in VIDEO_EXTENSIONS:
        errors.append("지원하지 않는 영상 확장자다. mp4, mov, avi, mkv, webm 파일을 사용해라.")
    return errors


def _select_provider(provider_key: str, providers: dict[str, dict[str, Any]]) -> str | None:
    aliases = {
        "auto": "sports2d_rtmpose_2d",
        "sports2d": "sports2d_rtmpose_2d",
        "sports2d_2d": "sports2d_rtmpose_2d",
        "rtmpose": "rtmpose_keypoints_2d",
        "mmpose": "mmpose_full",
    }
    key = aliases.get(provider_key, provider_key)
    provider = providers.get(key)
    if provider and provider.get("available") and provider.get("runnable"):
        return key
    if provider_key == "auto":
        for candidate in ("sports2d_rtmpose_2d",):
            if providers[candidate]["available"] and providers[candidate]["runnable"]:
                return candidate
    return None


def _provider_error(provider_key: str, providers: dict[str, dict[str, Any]]) -> str:
    if provider_key in {"auto", ""}:
        return "사용 가능한 무료 영상분석 provider가 없다. sports-motion extra 설치 상태를 확인해라."
    aliases = {"sports2d": "sports2d_rtmpose_2d", "sports2d_2d": "sports2d_rtmpose_2d", "rtmpose": "rtmpose_keypoints_2d", "mmpose": "mmpose_full"}
    key = aliases.get(provider_key, provider_key)
    provider = providers.get(key)
    if provider:
        if provider.get("available") and not provider.get("runnable"):
            return f"{provider_key} provider는 설치 감지만 가능하고 아직 미호에서 직접 실행할 수 없다."
        return f"{provider_key} provider가 아직 사용할 수 없는 상태다."
    return f"알 수 없는 provider다: {provider_key}"


def _single_camera_limitations() -> list[str]:
    return [
        "단일카메라는 깊이축 움직임을 직접 검증하지 못한다.",
        "메디신볼·왕복달리기처럼 회전과 방향전환이 큰 종목은 절대각보다 반복 촬영 추세를 우선한다.",
        "제멀·좌전굴은 측면에서 수직으로 고정 촬영해야 관절각 신뢰도가 올라간다.",
    ]


def _free_research_sources() -> list[dict[str, str]]:
    return [
        {"name": "PubMed Central", "url": "https://pmc.ncbi.nlm.nih.gov/", "use": "무료 원문 논문"},
        {"name": "Google Scholar", "url": "https://scholar.google.com/", "use": "논문 제목/인용 추적과 PDF 링크 확인"},
        {"name": "Semantic Scholar", "url": "https://www.semanticscholar.org/", "use": "관련 논문과 공개 PDF 탐색"},
        {"name": "DOAJ", "url": "https://doaj.org/", "use": "오픈액세스 저널 검색"},
        {"name": "RISS", "url": "https://www.riss.kr/", "use": "국내 학위논문·학술자료 무료 원문 확인"},
    ]


def _path_or_none(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text).expanduser() if text else None


def _output_dir(args: dict[str, Any], video_path: Path) -> Path:
    explicit = _path_or_none(args.get("output_dir"))
    if explicit:
        return explicit
    return video_path.with_name(f"{video_path.stem}_miho_motion")


def _visible_side(value: Any) -> str:
    text = str(value or "").strip().lower()
    mapping = {"side": "auto", "측면": "auto", "front": "front", "정면": "front", "back": "back", "후면": "back"}
    return mapping.get(text, text if text in {"auto", "left", "right", "front", "back", "none"} else "auto")


def _mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"light", "lightweight"}:
        return "lightweight"
    return text if text in {"balanced", "performance"} else "balanced"


def _timeout_seconds(args: dict[str, Any]) -> int:
    try:
        value = int(args.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return max(30, min(value, 3600))


def _run_command(
    command: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    call = runner or subprocess.run
    return call(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)


def _collect_output_files(output_dir: Path) -> list[str]:
    if not output_dir.exists():
        return []
    suffixes = {".mot", ".trc", ".csv", ".json", ".txt", ".mp4", ".png"}
    return [str(path) for path in sorted(output_dir.rglob("*")) if path.is_file() and path.suffix.lower() in suffixes]


def _process_diagnostics(run: subprocess.CompletedProcess[str]) -> dict[str, int]:
    return {
        "returncode": int(run.returncode),
        "stdout_chars": len(str(run.stdout or "")),
        "stderr_chars": len(str(run.stderr or "")),
    }


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "실행"}:
        return True
    if text in {"0", "false", "no", "n", "off", "준비"}:
        return False
    return default


def _is_module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _find_executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    sibling = Path(sys.executable).parent / name
    return str(sibling) if sibling.exists() and sibling.is_file() else None
