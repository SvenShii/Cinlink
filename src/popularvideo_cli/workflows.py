from __future__ import annotations

from pathlib import Path
from typing import Any

from .client import RuntimeClient, require_existing_file
from .dependencies import resolve_ffmpeg
from .errors import CliError
from .local_tools import burn_subtitles


APP_SUBTITLE_STYLE: dict[str, Any] = {
    "font_size": 18,
    "font_name": "Arial",
    "font_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 1.0,
    "margin_v": 20,
    "position": "bottom",
}


def add_subtitles(
    client: RuntimeClient,
    video_path: Path,
    *,
    subtitle_path: Path | None = None,
    source_lang: str = "auto",
    target_lang: str | None = None,
    bilingual: bool = False,
    out: Path | None = None,
    timeout: float | None = None,
    font_size: int | None = None,
    font_name: str | None = None,
    font_color: str | None = None,
    outline_color: str | None = None,
    outline_width: float | None = None,
    margin_v: int | None = None,
    position: str = "bottom",
    watermark_text: str | None = None,
    watermark_position: str = "top-right",
    watermark_font_size: int | None = None,
    watermark_color: str | None = None,
    watermark_opacity: float = 0.72,
    watermark_margin: int = 24,
    watermark_image_path: Path | None = None,
    watermark_image_position: str = "top-right",
    watermark_image_width: int | None = None,
    watermark_image_opacity: float = 0.72,
    watermark_image_margin: int = 24,
) -> dict[str, Any]:
    video = require_existing_file(video_path)
    if not resolve_ffmpeg(require_subtitles=True):
        raise CliError("dependency_missing", "No ffmpeg with subtitles/libass support was found. Install ffmpeg-full or use the CinLink app-managed ffmpeg bundle before running add-subtitles.")
    steps: list[dict[str, Any]] = []

    if subtitle_path:
        subtitle = require_existing_file(subtitle_path)
        source_payload: dict[str, Any] = {"subtitle_path": str(subtitle)}
        steps.append({"name": "use_existing_subtitle", "status": "done", "subtitle_path": str(subtitle)})
    elif target_lang and target_lang.strip():
        source_payload = client.translate(
            video,
            from_lang=source_lang,
            to_lang=target_lang,
            bilingual=bilingual,
            delivery="subtitle",
            out=out,
            timeout=timeout,
        )
        subtitle = _subtitle_path_from_payload(source_payload)
        steps.append(
            {
                "name": "translate_subtitles",
                "status": "done",
                "target_lang": target_lang,
                "subtitle_path": str(subtitle),
            }
        )
    else:
        source_payload = client.transcribe(video, lang=source_lang, out=out, timeout=timeout)
        subtitle = _subtitle_path_from_payload(source_payload)
        steps.append({"name": "transcribe", "status": "done", "subtitle_path": str(subtitle)})

    burn_payload = burn_subtitles(
        video,
        subtitle,
        out=out,
        font_size=font_size if font_size is not None else APP_SUBTITLE_STYLE["font_size"],
        font_name=font_name if font_name is not None else APP_SUBTITLE_STYLE["font_name"],
        font_color=font_color if font_color is not None else APP_SUBTITLE_STYLE["font_color"],
        outline_color=outline_color if outline_color is not None else APP_SUBTITLE_STYLE["outline_color"],
        outline_width=outline_width if outline_width is not None else APP_SUBTITLE_STYLE["outline_width"],
        margin_v=margin_v if margin_v is not None else APP_SUBTITLE_STYLE["margin_v"],
        position=position or APP_SUBTITLE_STYLE["position"],
        watermark_text=watermark_text,
        watermark_position=watermark_position,
        watermark_font_size=watermark_font_size,
        watermark_color=watermark_color,
        watermark_opacity=watermark_opacity,
        watermark_margin=watermark_margin,
        watermark_image_path=watermark_image_path,
        watermark_image_position=watermark_image_position,
        watermark_image_width=watermark_image_width,
        watermark_image_opacity=watermark_image_opacity,
        watermark_image_margin=watermark_image_margin,
    )
    steps.append({"name": "burn_subtitles", "status": "done", "video_output_path": burn_payload.get("video_output_path")})

    return {
        "status": "done",
        "workflow": "add_subtitles",
        "source_video_path": str(video),
        "subtitle_path": str(subtitle),
        "video_output_path": burn_payload.get("video_output_path"),
        "steps": steps,
        "source_payload": source_payload,
        "burn": burn_payload,
    }


def _subtitle_path_from_payload(payload: dict[str, Any]) -> Path:
    candidates = [
        payload.get("subtitle_path"),
        payload.get("translated_subtitle_path"),
        payload.get("output_subtitle_path"),
    ]
    outputs = payload.get("outputs")
    if isinstance(outputs, dict):
        candidates.extend(
            [
                outputs.get("subtitle_path"),
                outputs.get("translated_subtitle_path"),
                outputs.get("output_subtitle_path"),
            ]
        )
    artifact = _first_subtitle_artifact(payload.get("artifacts"))
    if artifact:
        candidates.append(artifact)
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return require_existing_file(Path(str(candidate)))
        except CliError:
            continue
    raise CliError(
        "invalid_response",
        "CinLink runtime did not return a local subtitle_path that can be burned.",
        {"payload_keys": sorted(payload.keys())},
    )


def _first_subtitle_artifact(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    for artifact in value:
        if not isinstance(artifact, dict):
            continue
        kind = str(artifact.get("kind") or "").lower()
        path = artifact.get("path") or artifact.get("local_path")
        name = str(artifact.get("name") or path or "")
        if path and (kind == "subtitle" or name.lower().endswith((".srt", ".ass", ".vtt"))):
            return str(path)
    return None
