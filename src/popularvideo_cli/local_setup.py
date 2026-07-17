from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import Any

from .dependencies import local_dependency_report


def setup_local_dependencies(
    *,
    assume_yes: bool = False,
    dry_run: bool = False,
    skip_ffmpeg: bool = False,
    with_voice_separation: bool = False,
    skip_voice_separation: bool = False,
    interactive: bool = True,
) -> dict[str, Any]:
    before = local_dependency_report()
    actions: list[dict[str, Any]] = []

    if not skip_ffmpeg:
        if before["ffmpeg"].get("subtitle_burn_available"):
            actions.append(
                {
                    "component": "ffmpeg",
                    "status": "already_available",
                    "path": before["ffmpeg"].get("subtitle_burn_path") or before["ffmpeg"].get("path"),
                }
            )
        else:
            actions.append(
                _maybe_install_component(
                    component="ffmpeg",
                    reason="CinLink uses ffmpeg for subtitle burn-in, local audio extraction, local audio mixing, ffprobe-style inspection, and local voice-separation preprocessing.",
                    commands=_ffmpeg_install_commands(),
                    assume_yes=assume_yes,
                    dry_run=dry_run,
                    interactive=interactive,
                    prompt="Install ffmpeg now?",
                )
            )

    if not skip_voice_separation:
        voice_ready = bool(before["local_voice_separation"].get("available"))
        if voice_ready:
            actions.append({"component": "voice_separation", "status": "already_available"})
        elif with_voice_separation or interactive:
            actions.append(
                _maybe_install_component(
                    component="voice_separation",
                    reason="Optional: local voice separation/background preservation needs demucs and soundfile. Hosted CinLink does not provide Demucs.",
                    commands=[_python_pip_command(["demucs", "soundfile"])],
                    assume_yes=assume_yes if with_voice_separation else False,
                    dry_run=dry_run,
                    interactive=interactive,
                    prompt="Install optional local voice-separation dependencies demucs and soundfile now?",
                )
            )
        else:
            actions.append(
                {
                    "component": "voice_separation",
                    "status": "skipped",
                    "reason": "Optional dependencies are installed only with user confirmation or --with-voice-separation.",
                }
            )

    after = local_dependency_report()
    failed = [item for item in actions if item.get("status") == "failed"]
    needs_confirmation = [item for item in actions if item.get("status") == "needs_confirmation"]
    manual = [item for item in actions if item.get("status") == "manual_required"]
    status = "done"
    if failed:
        status = "failed"
    elif manual:
        status = "manual_required"
    elif needs_confirmation:
        status = "needs_confirmation"

    return {
        "status": status,
        "platform": platform.system().lower(),
        "dry_run": dry_run,
        "actions": actions,
        "local_dependencies": after,
    }


def _maybe_install_component(
    *,
    component: str,
    reason: str,
    commands: list[list[str]],
    assume_yes: bool,
    dry_run: bool,
    interactive: bool,
    prompt: str,
) -> dict[str, Any]:
    if not commands:
        return {
            "component": component,
            "status": "manual_required",
            "reason": reason,
            "message": _manual_install_message(component),
        }

    if dry_run:
        return {
            "component": component,
            "status": "would_install",
            "reason": reason,
            "commands": [_format_command(command) for command in commands],
        }

    if not _confirm(prompt, assume_yes=assume_yes, interactive=interactive):
        return {
            "component": component,
            "status": "needs_confirmation",
            "reason": reason,
            "commands": [_format_command(command) for command in commands],
        }

    completed_commands: list[dict[str, Any]] = []
    for command in commands:
        completed = subprocess.run(command, text=True)
        completed_commands.append({"command": _format_command(command), "returncode": completed.returncode})
        if completed.returncode != 0:
            return {
                "component": component,
                "status": "failed",
                "reason": reason,
                "commands": completed_commands,
            }

    return {
        "component": component,
        "status": "installed",
        "reason": reason,
        "commands": completed_commands,
    }


def _confirm(prompt: str, *, assume_yes: bool, interactive: bool) -> bool:
    if assume_yes:
        return True
    if not interactive or not sys.stdin.isatty():
        return False
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes", "是", "好", "安装"}


def _ffmpeg_install_commands() -> list[list[str]]:
    system = platform.system().lower()
    if system == "darwin":
        brew = shutil.which("brew")
        return [[brew, "install", "ffmpeg"]] if brew else []
    if system == "windows":
        winget = shutil.which("winget")
        if not winget:
            return []
        return [
            [
                winget,
                "install",
                "--id",
                "Gyan.FFmpeg",
                "--exact",
                "--source",
                "winget",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ]
        ]
    if system == "linux":
        return _linux_ffmpeg_install_commands()
    return []


def _linux_ffmpeg_install_commands() -> list[list[str]]:
    prefix = _sudo_prefix()
    if prefix is None:
        return []
    if shutil.which("apt-get"):
        return [prefix + ["apt-get", "update"], prefix + ["apt-get", "install", "-y", "ffmpeg"]]
    if shutil.which("dnf"):
        return [prefix + ["dnf", "install", "-y", "ffmpeg"]]
    if shutil.which("yum"):
        return [prefix + ["yum", "install", "-y", "ffmpeg"]]
    if shutil.which("pacman"):
        return [prefix + ["pacman", "-S", "--noconfirm", "ffmpeg"]]
    if shutil.which("zypper"):
        return [prefix + ["zypper", "--non-interactive", "install", "ffmpeg"]]
    return []


def _sudo_prefix() -> list[str] | None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return []
    sudo = shutil.which("sudo")
    if sudo:
        return [sudo]
    return None


def _python_pip_command(packages: list[str]) -> list[str]:
    return [sys.executable, "-m", "pip", "install", "--upgrade", *packages]


def _manual_install_message(component: str) -> str:
    if component == "ffmpeg":
        return (
            "Install ffmpeg manually, then run `cinlink --json doctor`. "
            "macOS: `brew install ffmpeg`; Windows: `winget install --id Gyan.FFmpeg --exact`; "
            "Linux: use your distro package manager, for example `sudo apt-get install ffmpeg`."
        )
    if component == "voice_separation":
        return "Install optional voice-separation packages with `python -m pip install --upgrade demucs soundfile`."
    return "Install the missing component manually, then run `cinlink --json doctor`."


def _format_command(command: list[str]) -> str:
    return " ".join(_quote_part(part) for part in command)


def _quote_part(part: str) -> str:
    if not part or any(ch.isspace() for ch in part):
        return "'" + part.replace("'", "'\\''") + "'"
    return part
