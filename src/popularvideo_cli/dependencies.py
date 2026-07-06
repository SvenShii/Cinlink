from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .errors import CliError


VOICE_SEPARATION_KEYWORDS = (
    "人声分离",
    "分离人声",
    "去人声",
    "伴奏",
    "背景音",
    "保留背景音",
    "vocal separation",
    "separate vocals",
    "remove vocals",
    "instrumental",
    "accompaniment",
    "preserve bgm",
    "preserve background music",
)


def local_dependency_report() -> dict[str, Any]:
    ffmpeg_path = resolve_ffmpeg(require_subtitles=False)
    subtitle_ffmpeg_path = resolve_ffmpeg(require_subtitles=True)
    demucs_available = importlib.util.find_spec("demucs") is not None
    soundfile_available = importlib.util.find_spec("soundfile") is not None
    voice_ready = bool(ffmpeg_path and demucs_available and soundfile_available)
    return {
        "policy": {
            "hosted_first": True,
            "server_voice_separation_runtime": False,
            "local_dependencies_are_only_for_local_capabilities": True,
            "agent_may_install_only_after_user_confirmation": True,
        },
        "ffmpeg": {
            "available": bool(ffmpeg_path),
            "path": str(ffmpeg_path) if ffmpeg_path else None,
            "subtitles_filter": bool(subtitle_ffmpeg_path),
            "subtitle_burn_available": bool(subtitle_ffmpeg_path),
            "subtitle_burn_path": str(subtitle_ffmpeg_path) if subtitle_ffmpeg_path else None,
            "used_for": ["subtitle_burn", "local_audio_extract", "local_mix", "local_voice_separation"],
            "install_hint": {
                "windows": "winget install Gyan.FFmpeg",
                "macos": "brew install ffmpeg-full, or use the CinLink app-managed ffmpeg bundle",
            },
        },
        "demucs": {
            "available": demucs_available,
            "used_for": ["local_voice_separation", "preserve_background_music"],
            "install_hint": "pip install demucs soundfile",
        },
        "soundfile": {
            "available": soundfile_available,
            "used_for": ["local_voice_separation", "preserve_background_music"],
            "install_hint": "pip install soundfile",
        },
        "local_voice_separation": {
            "available": voice_ready,
            "requires": ["ffmpeg", "demucs", "soundfile"],
            "server_fallback": False,
            "message": (
                "Local voice separation is ready."
                if voice_ready
                else "Voice separation is a local capability. The hosted server does not provide Demucs, so the user must install the local voice separation components before this task can run."
            ),
        },
    }


def default_client_capabilities_from_dependencies() -> dict[str, bool]:
    report = local_dependency_report()
    ffmpeg_available = bool(report["ffmpeg"]["available"])
    subtitle_burn_available = bool(report["ffmpeg"].get("subtitle_burn_available"))
    voice_separation_available = bool(report["local_voice_separation"]["available"])
    return {
        "can_extract_audio_locally": ffmpeg_available,
        "can_probe_video_locally": ffmpeg_available,
        "can_burn_subtitles_locally": subtitle_burn_available,
        "can_render_video_locally": False,
        "can_separate_vocals_locally": voice_separation_available,
        "can_preserve_background_music_locally": voice_separation_available,
        "can_download_artifacts": True,
    }


def prompt_needs_voice_separation(prompt: str) -> bool:
    normalized = prompt.lower()
    return any(keyword.lower() in normalized for keyword in VOICE_SEPARATION_KEYWORDS)


def require_local_voice_separation_if_requested(prompt: str) -> None:
    if not prompt_needs_voice_separation(prompt):
        return
    report = local_dependency_report()
    if report["local_voice_separation"]["available"]:
        return
    missing = [
        name
        for name in ["ffmpeg", "demucs", "soundfile"]
        if not report[name]["available"]
    ]
    raise CliError(
        "dependency_missing",
        "Voice separation is a local capability. The hosted server does not provide Demucs, so ask the user to install local voice separation components before continuing.",
        {
            "capability": "local_voice_separation",
            "missing": missing,
            "server_fallback": False,
            "doctor_command": "cinlink --json doctor",
            "install_hints": {
                "windows_ffmpeg": "winget install Gyan.FFmpeg",
                "macos_ffmpeg": "brew install ffmpeg",
                "python_components": "pip install demucs soundfile",
            },
            "agent_policy": "Do not install automatically. Ask the user for explicit confirmation first.",
        },
    )


def resolve_ffmpeg(require_subtitles: bool = False) -> Path | None:
    for candidate in ffmpeg_candidates():
        if not _is_executable(candidate):
            continue
        if not _binary_works(candidate, ["-nostdin", "-version"]):
            continue
        if require_subtitles and not ffmpeg_supports_filter(candidate, "subtitles"):
            continue
        return candidate
    return None


def ffmpeg_candidates() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("CINLINK_FFMPEG", "ADDSUBTITLE_FFMPEG", "FFMPEG_BINARY"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value).expanduser())

    home = Path.home()
    app_support = home / "Library" / "Application Support"
    for app_name in ("CinLink", "Addsubtitle"):
        root = app_support / app_name / "ffmpeg"
        candidates.extend([root / "current" / "bin" / "ffmpeg", root / "bin" / "ffmpeg"])
        if root.exists():
            for child in sorted((item for item in root.iterdir() if item.is_dir()), reverse=True):
                candidates.append(child / "bin" / "ffmpeg")

    for app_name in ("CinLink.app", "Addsubtitle.app"):
        candidates.extend(
            [
                Path("/Applications") / app_name / "Contents" / "Resources" / "ffmpeg" / "bin" / "ffmpeg",
                home / "Applications" / app_name / "Contents" / "Resources" / "ffmpeg" / "bin" / "ffmpeg",
            ]
        )

    repo_root = Path(__file__).resolve().parents[2]
    for arch in ("arm64", "x86_64"):
        candidates.append(repo_root / "dist" / f"ffmpeg-{arch}" / "bin" / "ffmpeg")
        candidates.append(repo_root.parent / "PopularVideo" / "dist" / f"ffmpeg-{arch}" / "bin" / "ffmpeg")

    candidates.extend(
        [
            Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"),
            Path("/usr/local/opt/ffmpeg-full/bin/ffmpeg"),
            Path("/opt/homebrew/bin/ffmpeg"),
            Path("/usr/local/bin/ffmpeg"),
            Path("/usr/bin/ffmpeg"),
        ]
    )
    which = shutil.which("ffmpeg")
    if which:
        candidates.append(Path(which))
    return _unique_paths(candidates)


def ffmpeg_supports_filter(ffmpeg_path: Path, filter_name: str) -> bool:
    output = _run_and_capture(ffmpeg_path, ["-nostdin", "-hide_banner", "-filters"])
    if output is None:
        return False
    for line in output.splitlines():
        columns = line.split()
        if len(columns) >= 2 and columns[1] == filter_name:
            return True
    return False


def _unique_paths(candidates: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        normalized = str(candidate.expanduser())
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(Path(normalized))
    return unique


def _is_executable(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def _binary_works(path: Path, args: list[str]) -> bool:
    return _run_and_capture(path, args) is not None


def _run_and_capture(path: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            [str(path), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout
