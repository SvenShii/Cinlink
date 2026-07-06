from __future__ import annotations

from pathlib import Path
import re
import subprocess
from typing import Any

from .client import require_existing_file
from .dependencies import resolve_ffmpeg
from .errors import CliError


def burn_subtitles(
    video_path: Path,
    subtitle_path: Path,
    out: Path | None = None,
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
    subtitle = require_existing_file(subtitle_path)
    watermark_image = require_existing_file(watermark_image_path) if watermark_image_path else None
    ffmpeg = resolve_ffmpeg(require_subtitles=True)
    if not ffmpeg:
        raise CliError("dependency_missing", "No ffmpeg with subtitles/libass support was found. Install ffmpeg-full or use the CinLink app-managed ffmpeg bundle.")
    output_dir = (out.expanduser().resolve() if out else video.parent / f"{video.stem}.cinlink")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video.stem}.subtitled.mp4"
    effective_margin_v = margin_v if margin_v is not None else (24 if position == "bottom" else 48)
    force_style = [f"Alignment={2 if position == 'bottom' else 8}", f"MarginV={effective_margin_v}"]
    if font_size:
        force_style.append(f"FontSize={font_size}")
    if font_name:
        force_style.append(f"FontName={font_name}")
    if font_color:
        force_style.append(f"PrimaryColour={_ass_color(font_color)}")
    if outline_color:
        force_style.append(f"OutlineColour={_ass_color(outline_color)}")
    if outline_width is not None:
        force_style.append(f"Outline={outline_width:g}")
    escaped_subtitle = _escape_filter_path(subtitle)
    filter_arg = f"subtitles=filename='{escaped_subtitle}'"
    if force_style:
        filter_arg += f":force_style='{','.join(force_style)}'"

    if watermark_text:
        filter_arg = f"{filter_arg},{_drawtext_filter(watermark_text, watermark_position, watermark_font_size, watermark_color, watermark_opacity, watermark_margin)}"

    if watermark_image:
        image_filter = _image_overlay_filter(filter_arg, watermark_image_position, watermark_image_width, watermark_image_opacity, watermark_image_margin)
        cmd = [
            str(ffmpeg),
            "-y",
            "-i",
            str(video),
            "-i",
            str(watermark_image),
            "-filter_complex",
            image_filter,
            "-map",
            "[vout]",
            "-map",
            "0:a?",
            "-c:a",
            "copy",
            str(output_path),
        ]
    else:
        cmd = [
            str(ffmpeg),
            "-y",
            "-i",
            str(video),
            "-vf",
            filter_arg,
            "-c:a",
            "copy",
            str(output_path),
        ]
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise CliError("processing_failed", "ffmpeg failed to burn subtitles.", {"stderr": completed.stderr[-2000:]})
    return {
        "status": "done",
        "video_output_path": str(output_path),
        "subtitle_path": str(subtitle),
        "render_profile": {
            "engine": "ffmpeg",
            "position": position,
            "font_size": font_size,
            "font_name": font_name,
            "font_color": font_color,
            "outline_color": outline_color,
            "outline_width": outline_width,
            "margin_v": effective_margin_v,
            "watermark_text": watermark_text,
            "watermark_image_path": str(watermark_image) if watermark_image else None,
        },
    }


def mix_dubbed_audio(
    video_path: Path,
    dubbed_audio_path: Path,
    out: Path | None = None,
    original_volume: float = 0.65,
    dubbed_volume: float = 1.0,
) -> dict[str, Any]:
    video = require_existing_file(video_path)
    dubbed_audio = require_existing_file(dubbed_audio_path)
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    if not ffmpeg:
        raise CliError("dependency_missing", "ffmpeg was not found. Install ffmpeg before mixing dubbed audio.")
    output_dir = (out.expanduser().resolve() if out else video.parent / f"{video.stem}.cinlink")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video.stem}.dubbed-mix.mp4"
    filter_arg = (
        f"[0:a]volume={float(original_volume):g}[base];"
        f"[1:a]volume={float(dubbed_volume):g}[dub];"
        "[base][dub]amix=inputs=2:duration=longest:normalize=0:dropout_transition=0[outa]"
    )
    cmd = [
        str(ffmpeg),
        "-y",
        "-i",
        str(video),
        "-i",
        str(dubbed_audio),
        "-filter_complex",
        filter_arg,
        "-map",
        "0:v:0",
        "-map",
        "[outa]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise CliError("processing_failed", "ffmpeg failed to mix dubbed audio.", {"stderr": completed.stderr[-2000:]})
    return {
        "status": "done",
        "video_output_path": str(output_path),
        "source_video_path": str(video),
        "dubbed_audio_path": str(dubbed_audio),
        "render_profile": {
            "engine": "ffmpeg",
            "original_volume": original_volume,
            "dubbed_volume": dubbed_volume,
            "note": "This mixes the original audio track with dubbed audio. Use the hosted agent workflow plus local Demucs dependencies when true vocal separation/background preservation is required.",
        },
    }


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", r"\'")


def _ass_color(value: str) -> str:
    normalized = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", normalized):
        raise CliError("invalid_input", f"Invalid color value: {value}. Use #RRGGBB.")
    rr = normalized[0:2]
    gg = normalized[2:4]
    bb = normalized[4:6]
    return f"&H00{bb}{gg}{rr}".upper()


def _drawtext_filter(text: str, position: str, font_size: int | None, color: str | None, opacity: float, margin: int) -> str:
    x_expr, y_expr = _position_expr(position, margin, width_symbol="w", height_symbol="h", item_width="tw", item_height="th")
    fontcolor = _drawtext_color(color or "#FFFFFF", opacity)
    return (
        "drawtext="
        f"text='{_escape_drawtext_text(text)}'"
        f":x={x_expr}:y={y_expr}"
        f":fontsize={max(int(font_size or 28), 1)}"
        f":fontcolor={fontcolor}"
        ":box=1:boxcolor=black@0.25:boxborderw=8"
    )


def _image_overlay_filter(base_filter: str, position: str, width: int | None, opacity: float, margin: int) -> str:
    safe_opacity = min(max(float(opacity), 0.0), 1.0)
    x_expr, y_expr = _position_expr(position, margin, width_symbol="W", height_symbol="H", item_width="w", item_height="h")
    scale_filter = f"scale={max(int(width), 1)}:-1," if width else ""
    return (
        f"[0:v]{base_filter}[base];"
        f"[1:v]format=rgba,{scale_filter}colorchannelmixer=aa={safe_opacity:g}[wm];"
        f"[base][wm]overlay=x={x_expr}:y={y_expr}:shortest=1:format=auto:eof_action=repeat[vout]"
    )


def _position_expr(position: str, margin: int, *, width_symbol: str, height_symbol: str, item_width: str, item_height: str) -> tuple[str, str]:
    safe_margin = max(int(margin), 0)
    positions = {
        "top-left": (str(safe_margin), str(safe_margin)),
        "top-right": (f"{width_symbol}-{item_width}-{safe_margin}", str(safe_margin)),
        "bottom-left": (str(safe_margin), f"{height_symbol}-{item_height}-{safe_margin}"),
        "bottom-right": (f"{width_symbol}-{item_width}-{safe_margin}", f"{height_symbol}-{item_height}-{safe_margin}"),
        "center": (f"({width_symbol}-{item_width})/2", f"({height_symbol}-{item_height})/2"),
    }
    if position not in positions:
        raise CliError("invalid_input", "Invalid watermark position. Use top-left, top-right, bottom-left, bottom-right, or center.")
    return positions[position]


def _escape_drawtext_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", r"\n")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
        .replace("%", r"\%")
    )


def _drawtext_color(value: str, opacity: float) -> str:
    normalized = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", normalized):
        raise CliError("invalid_input", f"Invalid color value: {value}. Use #RRGGBB.")
    safe_opacity = min(max(float(opacity), 0.0), 1.0)
    return f"#{normalized.upper()}@{safe_opacity:g}"
