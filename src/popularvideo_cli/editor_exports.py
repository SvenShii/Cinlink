from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any
from uuid import uuid4
import xml.etree.ElementTree as ET

from .client import artifact_ref_from_path, require_existing_file
from .dependencies import resolve_ffmpeg, resolve_ffmpeg_with_encoder, resolve_ffprobe
from .errors import CliError
from .local_tools import _video_encoder_args


_VIDEO_FORMATS = {"mp4", "mov", "avi", "mkv"}
_AUDIO_FORMATS = {"wav", "mp3"}
_PROJECT_TARGETS = {"capcut", "premiere", "final-cut", "resolve"}


def export_video(
    video_path: Path,
    *,
    output_format: str = "mp4",
    out: Path | None = None,
) -> dict[str, Any]:
    video = require_existing_file(video_path)
    fmt = output_format.strip().lower()
    if fmt not in _VIDEO_FORMATS:
        raise CliError("invalid_input", "Video format must be mp4, mov, avi, or mkv.")
    ffmpeg = _required_ffmpeg(
        required_encoder="libmp3lame" if fmt == "avi" else None
    )
    output = _export_file(video, out, f"{video.stem}.edited.{fmt}")
    command = [
        str(ffmpeg),
        "-nostdin",
        "-y",
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
    ]
    if fmt == "avi":
        command.extend(["-c:v", "mpeg4", "-q:v", "3", "-c:a", "libmp3lame", "-q:a", "2"])
    else:
        command.extend(_video_encoder_args(ffmpeg))
        command.extend(["-c:a", "aac"])
        if fmt != "mkv":
            command.extend(["-movflags", "+faststart"])
    command.append(str(output))
    _run(command, "ffmpeg could not export the requested video format.")
    artifact = artifact_ref_from_path(
        output,
        metadata={
            "artifact_role": "edited_video",
            "delivery_role": "primary",
            "producer_step": "export_video",
            "source_video_name": video.name,
            "export_format": fmt,
        },
    )
    return {
        "status": "done",
        "video_output_path": str(output),
        "source_video_path": str(video),
        "format": fmt,
        "artifacts": [artifact],
        "privacy_receipt": _local_receipt("export_video"),
    }


def export_audio(
    video_path: Path,
    *,
    output_format: str = "wav",
    audio_path: Path | None = None,
    out: Path | None = None,
) -> dict[str, Any]:
    video = require_existing_file(video_path)
    source = require_existing_file(audio_path) if audio_path else video
    fmt = output_format.strip().lower()
    if fmt not in _AUDIO_FORMATS:
        raise CliError("invalid_input", "Audio format must be wav or mp3.")
    ffmpeg = _required_ffmpeg(
        required_encoder="libmp3lame" if fmt == "mp3" else None
    )
    output = _export_file(video, out, f"{video.stem}.audio.{fmt}")
    command = [
        str(ffmpeg),
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-map",
        "0:a:0",
    ]
    if fmt == "wav":
        command.extend(["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"])
    else:
        command.extend(["-c:a", "libmp3lame", "-q:a", "2"])
    command.append(str(output))
    _run(command, "ffmpeg could not export the requested audio format.")
    artifact = artifact_ref_from_path(
        output,
        metadata={
            "artifact_role": "exported_audio",
            "delivery_role": "primary",
            "producer_step": "export_audio",
            "source_video_name": video.name,
            "export_format": fmt,
        },
    )
    return {
        "status": "done",
        "audio_output_path": str(output),
        "source_video_path": str(video),
        "audio_source_path": str(source),
        "format": fmt,
        "artifacts": [artifact],
        "privacy_receipt": _local_receipt("export_audio"),
    }


def export_editor_project(
    video_path: Path,
    *,
    target: str,
    subtitle_path: Path | None = None,
    audio_path: Path | None = None,
    out: Path | None = None,
) -> dict[str, Any]:
    video = require_existing_file(video_path)
    subtitle = require_existing_file(subtitle_path) if subtitle_path else None
    audio = require_existing_file(audio_path) if audio_path else None
    normalized_target = _normalize_target(target)
    metadata = _probe_media(video)
    output_dir = _project_output_dir(video, out)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(video.stem)
    companions: list[Path] = []

    if normalized_target == "capcut":
        package = _unique_directory(output_dir, f"{stem}-CapCut.capcut-package")
        media_dir = package / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        media_copy = media_dir / f"source{video.suffix.lower()}"
        shutil.copy2(video, media_copy)
        package_audio: Path | None = None
        if audio and audio != video:
            package_audio = media_dir / f"translated-audio{audio.suffix.lower()}"
            shutil.copy2(audio, package_audio)
        package_subtitle: Path | None = None
        if subtitle:
            package_subtitle = package / "subtitles.srt"
            shutil.copy2(subtitle, package_subtitle)
        primary = package / "cinlink-timeline.json"
        _write_json(
            primary,
            {
                "format": "cinlink-capcut-transfer-package",
                "version": 1,
                "capcut_direct_project_import_supported": False,
                "video": {
                    "path": f"media/{media_copy.name}",
                    "offset_sec": 0,
                    "duration_sec": metadata["duration_sec"],
                    "width": metadata["width"],
                    "height": metadata["height"],
                    "frame_rate": metadata["fps"],
                },
                "audio": {
                    "path": (
                        f"media/{package_audio.name}" if package_audio else None
                    ),
                    "offset_sec": 0,
                },
                "subtitles": {
                    "path": package_subtitle.name if package_subtitle else None,
                    "offset_sec": 0,
                    "format": "srt",
                },
                "timeline_duration_sec": metadata["duration_sec"],
            },
        )
        readme = package / "README.txt"
        readme.write_text(
            "CinLink -> CapCut transfer package\n\n"
            "CapCut does not currently support importing third-party project files.\n"
            f"Import media/{media_copy.name}, then import subtitles.srt if present.\n"
            "If translated-audio is present, add it as a separate audio track and "
            "use cinlink-timeline.json for alignment.\n",
            encoding="utf-8",
        )
        companions = [
            path
            for path in (media_copy, package_audio, package_subtitle, readme)
            if path
        ]
        package_path: str | None = str(package)
    else:
        if subtitle:
            subtitle_copy = _unique_file(output_dir, f"{stem}-subtitles.srt")
            shutil.copy2(subtitle, subtitle_copy)
            companions.append(subtitle_copy)
        if normalized_target == "final-cut":
            primary = _unique_file(output_dir, f"{stem}-final-cut.fcpxml")
            _write_fcpxml(primary, video, metadata, audio=audio)
        else:
            suffix = "premiere" if normalized_target == "premiere" else "resolve"
            primary = _unique_file(output_dir, f"{stem}-{suffix}.xml")
            _write_fcp7_xml(primary, video, metadata, audio=audio)
        package_path = None

    primary_artifact = artifact_ref_from_path(
        primary,
        metadata={
            "artifact_role": "editor_project",
            "delivery_role": "primary",
            "producer_step": "export_editor_project",
            "source_video_name": video.name,
            "project_target": normalized_target,
            **({"package_path": package_path} if package_path else {}),
        },
    )
    supporting_artifacts = [
        artifact_ref_from_path(
            path,
            metadata={
                "artifact_role": (
                    "captions" if path.suffix.lower() in {".srt", ".vtt", ".ass", ".ssa"} else "supporting"
                ),
                "delivery_role": "supporting",
                "producer_step": "export_editor_project",
                "source_video_name": video.name,
                "project_target": normalized_target,
            },
        )
        for path in companions
        if path.is_file()
    ]
    return {
        "status": "done",
        "project_output_path": str(primary),
        "package_path": package_path,
        "source_video_path": str(video),
        "target": normalized_target,
        "companion_paths": [str(path) for path in companions],
        "artifacts": [primary_artifact, *supporting_artifacts],
        "primary_artifacts": [primary_artifact],
        "supporting_artifacts": supporting_artifacts,
        "intermediate_artifacts": [],
        "privacy_receipt": _local_receipt("export_editor_project"),
    }


def _required_ffmpeg(*, required_encoder: str | None = None) -> Path:
    ffmpeg = (
        resolve_ffmpeg_with_encoder(required_encoder)
        if required_encoder
        else resolve_ffmpeg(require_subtitles=False)
    )
    if not ffmpeg:
        if required_encoder:
            raise CliError(
                "dependency_missing",
                f"ffmpeg with the {required_encoder} encoder is required for this export.",
                {
                    "required_encoder": required_encoder,
                    "doctor_command": "cinlink --json doctor",
                    "install_hints": {
                        "macos": "brew install ffmpeg",
                        "windows": "winget install Gyan.FFmpeg",
                        "linux": "Install a distro ffmpeg package with MP3 encoding support.",
                    },
                },
            )
        raise CliError("dependency_missing", "ffmpeg is required for editor exports.")
    return ffmpeg


def _probe_media(video: Path) -> dict[str, Any]:
    ffmpeg = _required_ffmpeg()
    ffprobe = resolve_ffprobe(ffmpeg)
    if not ffprobe:
        raise CliError("dependency_missing", "ffprobe is required for editor project exports.")
    completed = _run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate:format=duration",
            "-of",
            "json",
            str(video),
        ],
        "ffprobe could not inspect media for editor export.",
    )
    try:
        payload = json.loads(completed.stdout)
        stream = payload["streams"][0]
        duration = float(payload["format"]["duration"])
        width = int(stream["width"])
        height = int(stream["height"])
        fps = float(Fraction(str(stream.get("avg_frame_rate") or "30/1")))
    except (KeyError, IndexError, ValueError, ZeroDivisionError, json.JSONDecodeError) as exc:
        raise CliError("processing_failed", "Media metadata is incomplete for project export.") from exc
    if fps <= 0:
        fps = 30.0
    return {
        "duration_sec": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "timebase": max(1, round(fps)),
    }


def _probe_duration(path: Path, *, fallback: float) -> float:
    ffmpeg = _required_ffmpeg()
    ffprobe = resolve_ffprobe(ffmpeg)
    if not ffprobe:
        return fallback
    completed = _run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        "ffprobe could not inspect audio duration for editor export.",
    )
    try:
        duration = float(json.loads(completed.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return duration if duration > 0 else fallback


def _fcpxml_duration(duration_sec: float, fps: float) -> str:
    fps_fraction = Fraction(fps).limit_denominator(1001)
    duration_frames = max(1, round(duration_sec * fps))
    return (
        f"{duration_frames * fps_fraction.denominator}/"
        f"{fps_fraction.numerator}s"
    )


def _write_fcpxml(
    path: Path,
    video: Path,
    metadata: dict[str, Any],
    *,
    audio: Path | None = None,
) -> None:
    fps_fraction = Fraction(metadata["fps"]).limit_denominator(1001)
    frame_duration = f"{fps_fraction.denominator}/{fps_fraction.numerator}s"
    duration = _fcpxml_duration(metadata["duration_sec"], metadata["fps"])
    root = ET.Element("fcpxml", {"version": "1.10"})
    resources = ET.SubElement(root, "resources")
    ET.SubElement(
        resources,
        "format",
        {
            "id": "r1",
            "name": "CinLink Format",
            "frameDuration": frame_duration,
            "width": str(metadata["width"]),
            "height": str(metadata["height"]),
            "colorSpace": "1-1-1 (Rec. 709)",
        },
    )
    asset = ET.SubElement(
        resources,
        "asset",
        {
            "id": "r2",
            "name": video.name,
            "start": "0s",
            "duration": duration,
            "hasVideo": "1",
            "hasAudio": "1",
            "format": "r1",
        },
    )
    ET.SubElement(asset, "media-rep", {"kind": "original-media", "src": video.as_uri()})
    audio_duration = duration
    if audio and audio != video:
        audio_duration = _fcpxml_duration(
            _probe_duration(audio, fallback=metadata["duration_sec"]),
            metadata["fps"],
        )
        audio_asset = ET.SubElement(
            resources,
            "asset",
            {
                "id": "r3",
                "name": audio.name,
                "start": "0s",
                "duration": audio_duration,
                "hasAudio": "1",
                "audioSources": "1",
                "audioChannels": "2",
                "audioRate": "48000",
            },
        )
        ET.SubElement(
            audio_asset,
            "media-rep",
            {"kind": "original-media", "src": audio.as_uri()},
        )
    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", {"name": "CinLink Export"})
    project = ET.SubElement(event, "project", {"name": video.stem})
    sequence = ET.SubElement(
        project,
        "sequence",
        {"duration": duration, "format": "r1", "tcStart": "0s", "tcFormat": "NDF"},
    )
    spine = ET.SubElement(sequence, "spine")
    gap = ET.SubElement(
        spine,
        "gap",
        {"name": "CinLink Timeline", "offset": "0s", "start": "0s", "duration": duration},
    )
    ET.SubElement(
        gap,
        "asset-clip",
        {
            "name": video.name,
            "ref": "r2",
            "lane": "1",
            "offset": "0s",
            "start": "0s",
            "duration": duration,
        },
    )
    if audio and audio != video:
        ET.SubElement(
            gap,
            "asset-clip",
            {
                "name": audio.name,
                "ref": "r3",
                "lane": "-1",
                "offset": "0s",
                "start": "0s",
                "duration": audio_duration,
                "audioRole": "dialogue",
            },
        )
    _write_xml(path, root, doctype="<!DOCTYPE fcpxml>")


def _write_fcp7_xml(
    path: Path,
    video: Path,
    metadata: dict[str, Any],
    *,
    audio: Path | None = None,
) -> None:
    timebase = int(metadata["timebase"])
    duration_frames = max(1, round(metadata["duration_sec"] * timebase))
    root = ET.Element("xmeml", {"version": "5"})
    sequence = ET.SubElement(root, "sequence")
    ET.SubElement(sequence, "name").text = video.stem
    ET.SubElement(sequence, "duration").text = str(duration_frames)
    rate = ET.SubElement(sequence, "rate")
    ET.SubElement(rate, "timebase").text = str(timebase)
    ET.SubElement(rate, "ntsc").text = "FALSE"
    media = ET.SubElement(sequence, "media")
    video_node = ET.SubElement(media, "video")
    track = ET.SubElement(video_node, "track")
    clip = ET.SubElement(track, "clipitem", {"id": "clipitem-1"})
    ET.SubElement(clip, "name").text = video.name
    ET.SubElement(clip, "start").text = "0"
    ET.SubElement(clip, "end").text = str(duration_frames)
    ET.SubElement(clip, "in").text = "0"
    ET.SubElement(clip, "out").text = str(duration_frames)
    file_node = ET.SubElement(clip, "file", {"id": "file-1"})
    ET.SubElement(file_node, "name").text = video.name
    ET.SubElement(file_node, "pathurl").text = video.as_uri()
    ET.SubElement(file_node, "duration").text = str(duration_frames)
    file_rate = ET.SubElement(file_node, "rate")
    ET.SubElement(file_rate, "timebase").text = str(timebase)
    ET.SubElement(file_rate, "ntsc").text = "FALSE"
    file_media = ET.SubElement(file_node, "media")
    file_video = ET.SubElement(file_media, "video")
    sample = ET.SubElement(file_video, "samplecharacteristics")
    ET.SubElement(sample, "width").text = str(metadata["width"])
    ET.SubElement(sample, "height").text = str(metadata["height"])
    audio_source = audio if audio and audio != video else video
    audio_duration_sec = (
        _probe_duration(audio_source, fallback=metadata["duration_sec"])
        if audio_source != video
        else metadata["duration_sec"]
    )
    audio_duration_frames = max(1, round(audio_duration_sec * timebase))
    audio_node = ET.SubElement(media, "audio")
    audio_track = ET.SubElement(audio_node, "track")
    audio_clip = ET.SubElement(
        audio_track,
        "clipitem",
        {"id": "audio-clip-1"},
    )
    ET.SubElement(audio_clip, "name").text = audio_source.name
    ET.SubElement(audio_clip, "duration").text = str(audio_duration_frames)
    ET.SubElement(audio_clip, "start").text = "0"
    ET.SubElement(audio_clip, "end").text = str(
        min(duration_frames, audio_duration_frames)
    )
    ET.SubElement(audio_clip, "in").text = "0"
    ET.SubElement(audio_clip, "out").text = str(
        min(duration_frames, audio_duration_frames)
    )
    if audio_source == video:
        ET.SubElement(audio_clip, "file", {"id": "file-1"})
    else:
        audio_file = ET.SubElement(audio_clip, "file", {"id": "file-2"})
        ET.SubElement(audio_file, "name").text = audio_source.name
        ET.SubElement(audio_file, "pathurl").text = audio_source.as_uri()
        ET.SubElement(audio_file, "duration").text = str(audio_duration_frames)
    source_track = ET.SubElement(audio_clip, "sourcetrack")
    ET.SubElement(source_track, "mediatype").text = "audio"
    ET.SubElement(source_track, "trackindex").text = "1"
    _write_xml(path, root)


def _write_xml(path: Path, root: ET.Element, *, doctype: str | None = None) -> None:
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    prefix = '<?xml version="1.0" encoding="UTF-8"?>\n'
    if doctype:
        prefix += doctype + "\n"
    path.write_text(prefix + body + "\n", encoding="utf-8")


def _normalize_target(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "cap-cut": "capcut",
        "premiere-pro": "premiere",
        "adobe-premiere-pro": "premiere",
        "finalcut": "final-cut",
        "final-cut-pro": "final-cut",
        "davinci": "resolve",
        "davinci-resolve": "resolve",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in _PROJECT_TARGETS:
        raise CliError(
            "invalid_input",
            "Project target must be capcut, premiere, final-cut, or resolve.",
        )
    return normalized


def _project_output_dir(video: Path, out: Path | None) -> Path:
    if out:
        expanded = out.expanduser().resolve()
        if expanded.suffix:
            return expanded.parent
        return expanded
    return video.parent / f"{video.stem}.editor-export"


def _unique_file(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    return directory / f"{candidate.stem}-{uuid4().hex[:8]}{candidate.suffix}"


def _unique_directory(directory: Path, name: str) -> Path:
    candidate = directory / name
    if not candidate.exists():
        return candidate
    return directory / f"{name}-{uuid4().hex[:8]}"


def _export_file(video: Path, out: Path | None, filename: str) -> Path:
    if out:
        expanded = out.expanduser().resolve()
        if expanded.suffix:
            expanded.parent.mkdir(parents=True, exist_ok=True)
            return expanded
        output_dir = expanded
    else:
        output_dir = video.parent / f"{video.stem}.editor-export"
    output_dir.mkdir(parents=True, exist_ok=True)
    return _unique_file(output_dir, filename)


def _safe_stem(value: str) -> str:
    normalized = "".join(character if character.isalnum() or character in "-_." else "-" for character in value)
    return normalized.strip("-_.") or "cinlink-project"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
        raise CliError("processing_failed", message, {"stderr": completed.stderr[-3000:]})
    return completed


def _local_receipt(step: str) -> dict[str, Any]:
    return {
        "source_video": "stayed_local",
        "hosted_inputs": [],
        "local_steps": [step],
        "cloud_steps": [],
        "local_final_video_processing": True,
    }
