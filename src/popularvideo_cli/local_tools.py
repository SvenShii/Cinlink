from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

from .client import artifact_ref_from_path, require_existing_file
from .dependencies import resolve_ffmpeg, resolve_ffprobe
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
            *_video_encoder_args(ffmpeg),
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
            *_video_encoder_args(ffmpeg),
            "-c:a",
            "copy",
            str(output_path),
        ]
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise CliError("processing_failed", "ffmpeg failed to burn subtitles.", {"stderr": completed.stderr[-2000:]})
    artifact_metadata = {
        "artifact_role": "burned_video",
        "producer_step": "burn_subtitles",
        "source_video_name": video.name,
    }
    return {
        "status": "done",
        "video_output_path": str(output_path),
        "subtitle_path": str(subtitle),
        "artifacts": [artifact_ref_from_path(output_path, metadata=artifact_metadata)],
        "privacy_receipt": _local_privacy_receipt("burn_subtitles"),
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
    artifact_metadata = {
        "artifact_role": "dubbed_video",
        "producer_step": "compose_dubbed_video",
        "source_video_name": video.name,
    }
    return {
        "status": "done",
        "video_output_path": str(output_path),
        "source_video_path": str(video),
        "dubbed_audio_path": str(dubbed_audio),
        "artifacts": [artifact_ref_from_path(output_path, metadata=artifact_metadata)],
        "privacy_receipt": _local_privacy_receipt("compose_dubbed_video"),
        "render_profile": {
            "engine": "ffmpeg",
            "original_volume": original_volume,
            "dubbed_volume": dubbed_volume,
            "note": "This mixes the original audio track with dubbed audio. Use the hosted agent workflow plus local Demucs dependencies when true vocal separation/background preservation is required.",
        },
    }


def apply_watermark(
    video_path: Path,
    *,
    out: Path | None = None,
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
    watermark_image = require_existing_file(watermark_image_path) if watermark_image_path else None
    if not watermark_text and not watermark_image:
        raise CliError("invalid_input", "Provide watermark_text, watermark_image_path, or configure an enabled Brand Kit.")
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    if not ffmpeg:
        raise CliError("dependency_missing", "ffmpeg was not found. Install ffmpeg before applying a watermark.")
    output_path = _video_output_path(video, out, "watermarked")
    filter_arg = "null"
    if watermark_text:
        filter_arg = _drawtext_filter(
            watermark_text,
            watermark_position,
            watermark_font_size,
            watermark_color,
            watermark_opacity,
            watermark_margin,
        )
    if watermark_image:
        cmd = [
            str(ffmpeg),
            "-nostdin",
            "-y",
            "-i",
            str(video),
            "-i",
            str(watermark_image),
            "-filter_complex",
            _image_overlay_filter(
                filter_arg,
                watermark_image_position,
                watermark_image_width,
                watermark_image_opacity,
                watermark_image_margin,
            ),
            "-map",
            "[vout]",
            "-map",
            "0:a?",
            *_video_encoder_args(ffmpeg),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    else:
        cmd = [
            str(ffmpeg),
            "-nostdin",
            "-y",
            "-i",
            str(video),
            "-vf",
            filter_arg,
            *_video_encoder_args(ffmpeg),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    _run_ffmpeg(cmd, "ffmpeg failed to apply the watermark.")
    metadata = {
        "artifact_role": "watermarked_video",
        "producer_step": "apply_watermark",
        "source_video_name": video.name,
    }
    return {
        "status": "done",
        "video_output_path": str(output_path),
        "source_video_path": str(video),
        "artifacts": [artifact_ref_from_path(output_path, metadata=metadata)],
        "privacy_receipt": _local_privacy_receipt("apply_watermark"),
        "render_profile": {
            "engine": "ffmpeg",
            "watermark_text": watermark_text,
            "watermark_image_path": str(watermark_image) if watermark_image else None,
        },
    }


def trim_video(
    video_path: Path,
    *,
    start_sec: float,
    end_sec: float,
    out: Path | None = None,
) -> dict[str, Any]:
    video = require_existing_file(video_path)
    duration = probe_video_duration(video)
    start = max(float(start_sec), 0.0)
    end = min(float(end_sec), duration)
    if end <= start:
        raise CliError("invalid_input", "end_sec must be greater than start_sec and overlap the source video.")
    output_path = _video_output_path(video, out, "matched-clip")
    _render_segment(video, start, end, output_path)
    metadata = {
        "artifact_role": "edited_video",
        "producer_step": "trim_video",
        "source_video_name": video.name,
        "clip_start_sec": f"{start:.3f}",
        "clip_end_sec": f"{end:.3f}",
    }
    return {
        "status": "done",
        "video_output_path": str(output_path),
        "source_video_path": str(video),
        "start_sec": start,
        "end_sec": end,
        "duration_sec": end - start,
        "artifacts": [artifact_ref_from_path(output_path, metadata=metadata)],
        "privacy_receipt": _local_privacy_receipt("trim_video"),
    }


def create_montage(
    clips: list[dict[str, Any]],
    *,
    out: Path | None = None,
) -> dict[str, Any]:
    normalized = _normalize_montage_clips(clips)
    if len(normalized) < 2:
        raise CliError("invalid_input", "Select at least two valid clips to create a montage.")
    first_video = normalized[0]["path"]
    output_path = _video_output_path(first_video, out, "material-mix")
    with tempfile.TemporaryDirectory(prefix="cinlink-montage-") as temp_dir:
        temp_root = Path(temp_dir)
        segments: list[Path] = []
        for index, clip in enumerate(normalized, start=1):
            segment = temp_root / f"segment-{index:04d}.mp4"
            _render_segment(clip["path"], clip["start_sec"], clip["end_sec"], segment)
            segments.append(segment)
        _concat_segments(segments, output_path)
    total_duration = sum(float(item["end_sec"]) - float(item["start_sec"]) for item in normalized)
    metadata = {
        "artifact_role": "edited_video",
        "producer_step": "merge_video_clips",
        "source_video_name": first_video.name,
        "clip_count": str(len(normalized)),
    }
    return {
        "status": "done",
        "video_output_path": str(output_path),
        "clip_count": len(normalized),
        "duration_sec": total_duration,
        "clips": [
            {
                "path": str(item["path"]),
                "start_sec": item["start_sec"],
                "end_sec": item["end_sec"],
            }
            for item in normalized
        ],
        "artifacts": [artifact_ref_from_path(output_path, metadata=metadata)],
        "privacy_receipt": _local_privacy_receipt("merge_video_clips"),
    }


def clean_cut(
    video_path: Path,
    *,
    out: Path | None = None,
    minimum_silence_sec: float = 0.85,
    noise_threshold_db: float = -35.0,
    retained_pause_sec: float = 0.24,
    minimum_removal_sec: float = 0.18,
    plan_only: bool = False,
    selected_removal_indexes: list[int] | None = None,
) -> dict[str, Any]:
    video = require_existing_file(video_path)
    if plan_only and selected_removal_indexes is not None:
        raise CliError(
            "invalid_input",
            "plan_only cannot be combined with selected_removal_indexes.",
        )
    duration = probe_video_duration(video)
    silence_ranges = detect_silence(
        video,
        minimum_silence_sec=minimum_silence_sec,
        noise_threshold_db=noise_threshold_db,
        duration_sec=duration,
    )
    candidate_removed_ranges = _clean_cut_removals(
        silence_ranges,
        source_duration_sec=duration,
        retained_pause_sec=retained_pause_sec,
        minimum_removal_sec=minimum_removal_sec,
    )
    candidate_payloads = [
        {"index": index, **payload}
        for index, payload in enumerate(_range_payloads(candidate_removed_ranges))
    ]
    planned_removed_duration = sum(end - start for start, end in candidate_removed_ranges)
    if plan_only:
        return {
            "status": "planned",
            "changed": False,
            "has_candidates": bool(candidate_removed_ranges),
            "source_video_path": str(video),
            "video_output_path": None,
            "source_duration_sec": duration,
            "planned_output_duration_sec": duration - planned_removed_duration,
            "planned_removed_duration_sec": planned_removed_duration,
            "candidate_removed_ranges": candidate_payloads,
            "selected_removal_indexes": [],
            "removed_ranges": [],
            "keep_ranges": [{"start_sec": 0.0, "end_sec": duration, "duration_sec": duration}],
            "planned_keep_ranges": _range_payloads(_inverse_ranges(candidate_removed_ranges, duration)),
            "artifacts": [],
            "privacy_receipt": _local_privacy_receipt("clean_cut"),
        }

    if selected_removal_indexes is None:
        selected_indexes = list(range(len(candidate_removed_ranges)))
    else:
        selected_indexes = _validate_removal_indexes(
            selected_removal_indexes,
            candidate_count=len(candidate_removed_ranges),
        )
    removed_ranges = [candidate_removed_ranges[index] for index in selected_indexes]
    keep_ranges = _inverse_ranges(removed_ranges, duration)
    if not removed_ranges:
        return {
            "status": "done",
            "changed": False,
            "has_candidates": bool(candidate_removed_ranges),
            "source_video_path": str(video),
            "video_output_path": str(video),
            "source_duration_sec": duration,
            "output_duration_sec": duration,
            "removed_duration_sec": 0.0,
            "candidate_removed_ranges": candidate_payloads,
            "selected_removal_indexes": selected_indexes,
            "removed_ranges": [],
            "keep_ranges": [{"start_sec": 0.0, "end_sec": duration}],
            "artifacts": [],
            "privacy_receipt": _local_privacy_receipt("clean_cut"),
        }
    output_path = _video_output_path(video, out, "clean-cut")
    with tempfile.TemporaryDirectory(prefix="cinlink-clean-cut-") as temp_dir:
        temp_root = Path(temp_dir)
        segments: list[Path] = []
        for index, (start, end) in enumerate(keep_ranges, start=1):
            segment = temp_root / f"segment-{index:04d}.mp4"
            _render_segment(video, start, end, segment)
            segments.append(segment)
        _concat_segments(segments, output_path)
    removed_duration = sum(end - start for start, end in removed_ranges)
    metadata = {
        "artifact_role": "edited_video",
        "producer_step": "clean_cut",
        "source_video_name": video.name,
        "removed_pause_count": str(len(removed_ranges)),
    }
    return {
        "status": "done",
        "changed": True,
        "has_candidates": True,
        "source_video_path": str(video),
        "video_output_path": str(output_path),
        "source_duration_sec": duration,
        "output_duration_sec": duration - removed_duration,
        "removed_duration_sec": removed_duration,
        "candidate_removed_ranges": candidate_payloads,
        "selected_removal_indexes": selected_indexes,
        "removed_ranges": _range_payloads(removed_ranges),
        "keep_ranges": _range_payloads(keep_ranges),
        "artifacts": [artifact_ref_from_path(output_path, metadata=metadata)],
        "privacy_receipt": _local_privacy_receipt("clean_cut"),
    }


def detect_silence(
    video_path: Path,
    *,
    minimum_silence_sec: float = 0.85,
    noise_threshold_db: float = -35.0,
    duration_sec: float | None = None,
) -> list[tuple[float, float]]:
    video = require_existing_file(video_path)
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    if not ffmpeg:
        raise CliError("dependency_missing", "ffmpeg was not found. Install ffmpeg before running Clean Cut.")
    duration = duration_sec if duration_sec is not None else probe_video_duration(video)
    filter_arg = f"silencedetect=noise={float(noise_threshold_db):g}dB:d={max(float(minimum_silence_sec), 0.2):g}"
    completed = subprocess.run(
        [
            str(ffmpeg),
            "-nostdin",
            "-hide_banner",
            "-i",
            str(video),
            "-vn",
            "-af",
            filter_arg,
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise CliError("processing_failed", "ffmpeg failed to analyze video pauses.", {"stderr": completed.stderr[-2000:]})
    starts = [float(value) for value in re.findall(r"silence_start:\s*([0-9.]+)", completed.stderr)]
    ends = [float(value) for value in re.findall(r"silence_end:\s*([0-9.]+)", completed.stderr)]
    ranges: list[tuple[float, float]] = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else duration
        if end > start:
            ranges.append((max(start, 0.0), min(end, duration)))
    return ranges


def probe_video_duration(video_path: Path) -> float:
    video = require_existing_file(video_path)
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    if not ffmpeg:
        raise CliError("dependency_missing", "ffmpeg was not found. Install ffmpeg before editing video.")
    ffprobe = resolve_ffprobe(ffmpeg)
    if not ffprobe:
        raise CliError("dependency_missing", "ffprobe was not found next to ffmpeg or on PATH.")
    completed = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        duration = float(completed.stdout.strip())
    except ValueError as exc:
        raise CliError("processing_failed", "Could not read video duration.", {"stderr": completed.stderr[-1000:]}) from exc
    if completed.returncode != 0 or duration <= 0:
        raise CliError("processing_failed", "Could not read video duration.", {"stderr": completed.stderr[-1000:]})
    return duration


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
    font_file = _default_font_file()
    font_option = f":fontfile='{_escape_filter_path(font_file)}'" if font_file else ""
    return (
        "drawtext="
        f"text='{_escape_drawtext_text(text)}'"
        f"{font_option}"
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


def _default_font_file() -> Path | None:
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    return next((path for path in candidates if path.is_file()), None)


def _video_output_path(source: Path, out: Path | None, suffix: str) -> Path:
    if out:
        expanded = out.expanduser().resolve()
        if expanded.suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".webm"}:
            expanded.parent.mkdir(parents=True, exist_ok=True)
            return expanded
        output_dir = expanded
    else:
        output_dir = source.parent / f"{source.stem}.cinlink"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{source.stem}.{suffix}.mp4"


def _render_segment(source: Path, start_sec: float, end_sec: float, output_path: Path) -> None:
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    if not ffmpeg:
        raise CliError("dependency_missing", "ffmpeg was not found. Install ffmpeg before editing video.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(float(end_sec) - float(start_sec), 0.001)
    command = [
        str(ffmpeg),
        "-nostdin",
        "-y",
        "-ss",
        f"{max(float(start_sec), 0.0):.6f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.6f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        *_video_encoder_args(ffmpeg),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    _run_ffmpeg(command, "ffmpeg failed to render a video segment.")


def _concat_segments(segments: list[Path], output_path: Path) -> None:
    if not segments:
        raise CliError("invalid_input", "No video segments were available to concatenate.")
    if len(segments) == 1:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(segments[0], output_path)
        return
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    if not ffmpeg:
        raise CliError("dependency_missing", "ffmpeg was not found. Install ffmpeg before merging clips.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_path = segments[0].parent / "concat.txt"
    concat_path.write_text(
        "\n".join(f"file '{_concat_file_path(path)}'" for path in segments),
        encoding="utf-8",
    )
    command = [
        str(ffmpeg),
        "-nostdin",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    _run_ffmpeg(command, "ffmpeg failed to concatenate video segments.")


def _normalize_montage_clips(clips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(clips, list):
        raise CliError("invalid_input", "clips must be a JSON array.")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(clips):
        if not isinstance(item, dict):
            raise CliError("invalid_input", f"clips[{index}] must be a JSON object.")
        raw_path = item.get("path") or item.get("video_path")
        if not raw_path:
            raise CliError("invalid_input", f"clips[{index}] requires path.")
        source = require_existing_file(Path(str(raw_path)))
        duration = probe_video_duration(source)
        start = max(float(item.get("start_sec") or 0.0), 0.0)
        if item.get("end_sec") is not None:
            end = min(float(item["end_sec"]), duration)
        elif item.get("duration_sec") is not None:
            end = min(start + float(item["duration_sec"]), duration)
        else:
            end = duration
        if end <= start:
            raise CliError("invalid_input", f"clips[{index}] has an invalid time range.")
        normalized.append({"path": source, "start_sec": start, "end_sec": end})
    return normalized


def _clean_cut_removals(
    silence_ranges: list[tuple[float, float]],
    *,
    source_duration_sec: float,
    retained_pause_sec: float,
    minimum_removal_sec: float,
) -> list[tuple[float, float]]:
    retained_per_side = max(float(retained_pause_sec), 0.0) / 2.0
    removals: list[tuple[float, float]] = []
    for start, end in silence_ranges:
        removal_start = max(0.0, min(source_duration_sec, start + retained_per_side))
        removal_end = max(0.0, min(source_duration_sec, end - retained_per_side))
        if removal_end - removal_start >= max(float(minimum_removal_sec), 0.01):
            removals.append((removal_start, removal_end))
    return _merge_ranges(removals)


def _validate_removal_indexes(indexes: list[int], *, candidate_count: int) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for position, value in enumerate(indexes):
        if isinstance(value, bool) or not isinstance(value, int):
            raise CliError(
                "invalid_input",
                f"selected_removal_indexes[{position}] must be an integer.",
            )
        if value < 0 or value >= candidate_count:
            raise CliError(
                "invalid_input",
                f"selected_removal_indexes[{position}] is out of range for {candidate_count} candidates.",
            )
        if value in seen:
            raise CliError(
                "invalid_input",
                f"selected_removal_indexes contains duplicate index {value}.",
            )
        seen.add(value)
        normalized.append(value)
    return sorted(normalized)


def _inverse_ranges(ranges: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in _merge_ranges(ranges):
        if start > cursor:
            keep.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        keep.append((cursor, duration))
    return [(start, end) for start, end in keep if end - start >= 0.05]


def _merge_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(ranges):
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + 0.001:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _range_payloads(ranges: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [
        {"start_sec": start, "end_sec": end, "duration_sec": end - start}
        for start, end in ranges
    ]


def _concat_file_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "'\\''")


@lru_cache(maxsize=8)
def _video_encoder_args(ffmpeg: Path) -> list[str]:
    completed = subprocess.run(
        [str(ffmpeg), "-nostdin", "-hide_banner", "-encoders"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = completed.stdout
    if re.search(r"^\s*V\S*\s+libx264\s", output, flags=re.MULTILINE):
        return ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
    return ["-c:v", "mpeg4", "-q:v", "3"]


def _run_ffmpeg(command: list[str], message: str) -> None:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise CliError("processing_failed", message, {"stderr": completed.stderr[-2000:]})


def _local_privacy_receipt(step: str) -> dict[str, Any]:
    return {
        "source_video": "stayed_local",
        "hosted_inputs": [],
        "local_steps": [step],
        "cloud_steps": [],
        "local_final_video_processing": True,
    }
