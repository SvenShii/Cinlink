from __future__ import annotations

import importlib.util
import shutil
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
    ffmpeg_path = shutil.which("ffmpeg")
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
            "path": ffmpeg_path,
            "used_for": ["subtitle_burn", "local_audio_extract", "local_mix", "local_voice_separation"],
            "install_hint": {
                "windows": "winget install Gyan.FFmpeg",
                "macos": "brew install ffmpeg",
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
    voice_separation_available = bool(report["local_voice_separation"]["available"])
    return {
        "can_extract_audio_locally": ffmpeg_available,
        "can_probe_video_locally": ffmpeg_available,
        "can_burn_subtitles_locally": ffmpeg_available,
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
            "doctor_command": "popularvideo --json doctor",
            "install_hints": {
                "windows_ffmpeg": "winget install Gyan.FFmpeg",
                "macos_ffmpeg": "brew install ffmpeg",
                "python_components": "pip install demucs soundfile",
            },
            "agent_policy": "Do not install automatically. Ask the user for explicit confirmation first.",
        },
    )
