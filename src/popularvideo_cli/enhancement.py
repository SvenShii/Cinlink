from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from typing import Any

from .client import artifact_ref_from_path, require_existing_file
from .dependencies import resolve_ffmpeg, resolve_ffprobe
from .errors import CliError


_MODEL_DIRECTORIES = {
    "photo": "models-upconv_7_photo",
    "cunet": "models-cunet",
    "anime": "models-upconv_7_anime_style_art_rgb",
}


def resolve_waifu2x() -> Path | None:
    candidates: list[Path] = []
    for name in ("CINLINK_WAIFU2X_BIN", "ADDSUBTITLE_WAIFU2X_BIN"):
        value = os.environ.get(name)
        if value:
            candidates.append(Path(value).expanduser())
    for name in ("CINLINK_WAIFU2X_DIR", "ADDSUBTITLE_WAIFU2X_DIR"):
        value = os.environ.get(name)
        if value:
            candidates.append(Path(value).expanduser() / "waifu2x-ncnn-vulkan")

    home = Path.home()
    for app_name in ("CinLink", "Addsubtitle"):
        root = home / "Library" / "Application Support" / app_name / "local-runtime"
        candidates.extend(
            [
                root / "current" / "waifu2x-ncnn-vulkan" / "waifu2x-ncnn-vulkan",
                root / "waifu2x-ncnn-vulkan" / "waifu2x-ncnn-vulkan",
            ]
        )
    for app_name in ("CinLink.app", "Addsubtitle.app"):
        for applications in (Path("/Applications"), home / "Applications"):
            resources = applications / app_name / "Contents" / "Resources"
            candidates.extend(
                [
                    resources / "waifu2x-ncnn-vulkan" / "waifu2x-ncnn-vulkan",
                    resources / "local-runtime" / "waifu2x-ncnn-vulkan" / "waifu2x-ncnn-vulkan",
                ]
            )
    which = shutil.which("waifu2x-ncnn-vulkan")
    if which:
        candidates.append(Path(which))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    return None


def waifu2x_dependency_report() -> dict[str, Any]:
    binary = resolve_waifu2x()
    models = {
        name: bool(binary and (binary.parent / directory).is_dir())
        for name, directory in _MODEL_DIRECTORIES.items()
    }
    return {
        "available": bool(binary and all(models.values())),
        "binary_available": bool(binary),
        "path": str(binary) if binary else None,
        "models": models,
        "used_for": ["local_image_enhancement", "local_video_enhancement"],
        "install_hint": (
            "Install the CinLink local enhancement component, install the CinLink app bundle, "
            "or set CINLINK_WAIFU2X_DIR to a verified waifu2x-ncnn-vulkan directory containing all model folders."
        ),
    }


def enhance_image(
    image_path: Path,
    *,
    out: Path | None = None,
    scale: int = 2,
    noise_level: int = 1,
    model: str = "photo",
) -> dict[str, Any]:
    image = require_existing_file(image_path)
    if image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".gif"}:
        raise CliError("invalid_input", "Image enhancement supports PNG, JPEG, WebP, HEIC, and GIF files.")
    binary, model_path = _require_waifu2x(model)
    _validate_options(scale, noise_level)
    output_dir = _output_dir(image, out)
    output_path = output_dir / f"{image.stem}.waifu2x-{scale}x.png"
    with tempfile.TemporaryDirectory(prefix="cinlink-waifu2x-image-") as raw_temp:
        prepared = _prepare_image(image, Path(raw_temp))
        _run(
            [
                str(binary), "-i", str(prepared), "-o", str(output_path),
                "-n", str(noise_level), "-s", str(scale), "-m", str(model_path),
                "-f", "png", "-j", "1:2:2",
            ],
            "waifu2x-ncnn-vulkan failed to enhance the image",
        )
    width, height = _png_dimensions(output_path)
    metadata = {
        "artifact_role": "enhanced_image",
        "producer_step": "enhance_image",
        "source_image_name": image.name,
        "model": model,
        "scale": str(scale),
    }
    return {
        "status": "done",
        "image_path": str(output_path),
        "width": width,
        "height": height,
        "scale": scale,
        "model": model,
        "artifacts": [artifact_ref_from_path(output_path, metadata=metadata)],
        "privacy_receipt": _privacy_receipt("enhance_image", source_video=False),
    }


def enhance_video(
    video_path: Path,
    *,
    out: Path | None = None,
    scale: int = 2,
    noise_level: int = 1,
    model: str = "photo",
) -> dict[str, Any]:
    video = require_existing_file(video_path)
    binary, model_path = _require_waifu2x(model)
    _validate_options(scale, noise_level)
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    ffprobe = resolve_ffprobe(ffmpeg)
    if not ffmpeg or not ffprobe:
        raise CliError("dependency_missing", "ffmpeg and ffprobe are required for local video enhancement.")
    source_metadata = _probe_video(ffprobe, video)
    output_dir = _output_dir(video, out)
    output_path = output_dir / f"{video.stem}.waifu2x-{scale}x.mp4"
    with tempfile.TemporaryDirectory(prefix="cinlink-waifu2x-video-") as raw_temp:
        temp = Path(raw_temp)
        input_frames = temp / "input_frames"
        output_frames = temp / "output_frames"
        input_frames.mkdir()
        output_frames.mkdir()
        _run(
            [
                str(ffmpeg), "-nostdin", "-y", "-i", str(video),
                "-q:v", "2", str(input_frames / "frame_%06d.jpg"),
            ],
            "ffmpeg failed to extract frames for enhancement",
        )
        frame_count = _count_frames(input_frames)
        if not frame_count:
            raise CliError("processing_failed", "No frames were extracted from the source video.")
        _run(
            [
                str(binary), "-i", str(input_frames), "-o", str(output_frames),
                "-n", str(noise_level), "-s", str(scale), "-m", str(model_path),
                "-f", "jpg", "-j", "1:2:2",
            ],
            "waifu2x-ncnn-vulkan failed to enhance the video frames",
        )
        enhanced_count = _count_frames(output_frames)
        if enhanced_count != frame_count:
            raise CliError(
                "processing_failed",
                "waifu2x produced an incomplete enhanced frame sequence.",
                {"expected_frames": frame_count, "enhanced_frames": enhanced_count},
            )
        filters = ["format=yuv420p"]
        if source_metadata.get("sample_aspect_ratio"):
            filters.insert(0, f"setsar={source_metadata['sample_aspect_ratio']}")
        _run(
            [
                str(ffmpeg), "-nostdin", "-y", "-framerate", source_metadata["fps"],
                "-i", str(output_frames / "frame_%06d.jpg"), "-i", str(video),
                "-map", "0:v:0", "-map", "1:a?", *_video_encoder_args(ffmpeg),
                "-vf", ",".join(filters), "-c:a", "copy", "-shortest", str(output_path),
            ],
            "ffmpeg failed to compose the enhanced video",
        )
    output_metadata = _probe_video(ffprobe, output_path)
    metadata = {
        "artifact_role": "enhanced_video",
        "producer_step": "enhance_video",
        "source_video_name": video.name,
        "model": model,
        "scale": str(scale),
        "has_audio": str(_has_audio(ffprobe, output_path)).lower(),
    }
    return {
        "status": "done",
        "video_path": str(output_path),
        "width": output_metadata["width"],
        "height": output_metadata["height"],
        "display_aspect_ratio": output_metadata.get("display_aspect_ratio"),
        "sample_aspect_ratio": output_metadata.get("sample_aspect_ratio"),
        "frame_count": frame_count,
        "fps": source_metadata["fps"],
        "model": model,
        "artifacts": [artifact_ref_from_path(output_path, metadata=metadata)],
        "privacy_receipt": _privacy_receipt("enhance_video", source_video=True),
    }


def _require_waifu2x(model: str) -> tuple[Path, Path]:
    binary = resolve_waifu2x()
    if not binary:
        raise CliError(
            "dependency_missing",
            "waifu2x-ncnn-vulkan is required for local image/video enhancement.",
            {"doctor_command": "cinlink --json doctor"},
        )
    model_path = binary.parent / _MODEL_DIRECTORIES.get(model, "")
    if model not in _MODEL_DIRECTORIES or not model_path.is_dir():
        raise CliError("dependency_missing", f"waifu2x model directory is missing for model: {model}")
    return binary, model_path


def _validate_options(scale: int, noise_level: int) -> None:
    if scale != 2 or noise_level not in {-1, 0, 1, 2, 3}:
        raise CliError("invalid_input", "Enhancement supports scale=2 and noise_level=-1,0,1,2,3.")


def _output_dir(input_path: Path, out: Path | None) -> Path:
    output = out.expanduser().resolve() if out else input_path.parent / f"{input_path.stem}.enhanced"
    output.mkdir(parents=True, exist_ok=True)
    return output


def _prepare_image(input_path: Path, temp_dir: Path) -> Path:
    if input_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        return input_path
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    if not ffmpeg:
        raise CliError("dependency_missing", "ffmpeg is required to prepare HEIC or GIF images for enhancement.")
    prepared = temp_dir / "source.png"
    _run(
        [str(ffmpeg), "-nostdin", "-y", "-i", str(input_path), "-frames:v", "1", str(prepared)],
        "ffmpeg failed to prepare the image for enhancement",
    )
    return prepared


def _probe_video(ffprobe: Path, path: Path) -> dict[str, Any]:
    completed = _run(
        [
            str(ffprobe), "-v", "error", "-select_streams", "v:0", "-show_entries",
            "stream=width,height,r_frame_rate,sample_aspect_ratio,display_aspect_ratio",
            "-of", "json", str(path),
        ],
        "ffprobe failed to inspect the video",
    )
    try:
        stream = json.loads(completed.stdout or "{}")["streams"][0]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise CliError("invalid_input", "Input file does not contain a readable video stream.") from exc
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "fps": str(stream.get("r_frame_rate") or "25/1"),
        "sample_aspect_ratio": _clean_ratio(stream.get("sample_aspect_ratio")),
        "display_aspect_ratio": _clean_ratio(stream.get("display_aspect_ratio")),
    }


def _has_audio(ffprobe: Path, path: Path) -> bool:
    completed = subprocess.run(
        [str(ffprobe), "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode == 0 and bool(completed.stdout.strip())


def _clean_ratio(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized if normalized and normalized not in {"0:1", "N/A"} else None


def _png_dimensions(path: Path) -> tuple[int, int]:
    if not path.is_file():
        raise CliError("processing_failed", "waifu2x did not produce the enhanced PNG image.")
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise CliError("processing_failed", "waifu2x produced an invalid PNG image.")
    return struct.unpack(">II", header[16:24])


def _count_frames(directory: Path) -> int:
    return sum(
        1
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )


def _video_encoder_args(ffmpeg: Path) -> list[str]:
    completed = subprocess.run(
        [str(ffmpeg), "-nostdin", "-hide_banner", "-encoders"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    encoders = {
        parts[1]
        for line in completed.stdout.splitlines()
        if len(parts := line.split()) >= 2 and parts[0].startswith("V")
    }
    if "libx264" in encoders:
        return ["-c:v", "libx264", "-preset", "slow", "-crf", "18"]
    if "h264_videotoolbox" in encoders:
        return ["-c:v", "h264_videotoolbox", "-b:v", "12000k"]
    return ["-c:v", "mpeg4", "-q:v", "3"]


def _run(command: list[str], message: str) -> subprocess.CompletedProcess[str]:
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
    return completed


def _privacy_receipt(step: str, *, source_video: bool) -> dict[str, Any]:
    return {
        "source_video": "stayed_local" if source_video else "not_included",
        "hosted_inputs": [],
        "local_steps": [step],
        "cloud_steps": [],
        "local_final_video_processing": source_video,
    }
