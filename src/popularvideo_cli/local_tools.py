from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any

from .client import require_existing_file
from .errors import CliError


def burn_subtitles(
    video_path: Path,
    subtitle_path: Path,
    out: Path | None = None,
    font_size: int | None = None,
    position: str = "bottom",
) -> dict[str, Any]:
    video = require_existing_file(video_path)
    subtitle = require_existing_file(subtitle_path)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise CliError("dependency_missing", "ffmpeg was not found on PATH. Install ffmpeg with subtitles/libass support.")
    output_dir = (out.expanduser().resolve() if out else video.parent / f"{video.stem}.cinlink")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video.stem}.subtitled.mp4"
    margin_v = 24 if position == "bottom" else 48
    force_style = []
    if font_size:
        force_style.append(f"FontSize={font_size}")
    force_style.append(f"MarginV={margin_v}")
    escaped_subtitle = str(subtitle).replace("\\", "/").replace(":", "\\:")
    filter_arg = f"subtitles='{escaped_subtitle}'"
    if force_style:
        filter_arg += f":force_style='{','.join(force_style)}'"
    cmd = [
        ffmpeg,
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
        },
    }
