from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
from uuid import uuid4

from .client import RuntimeClient, artifact_ref_from_path, require_existing_file
from .dependencies import resolve_ffmpeg, resolve_ffprobe
from .errors import CliError
from .local_tools import _video_encoder_args


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_REPLACEMENT_ROLES = {"person", "product", "scene"}


def deconstruct_video(
    client: RuntimeClient,
    video_path: Path,
    *,
    out: Path | None = None,
    replacement_references: list[dict[str, str]] | None = None,
    language: str = "zh-Hans",
    analysis_scope: str = "",
    scene_threshold: float = 0.28,
    max_shots: int = 120,
) -> dict[str, Any]:
    video = require_existing_file(video_path)
    normalized_language = language.strip() or "zh-Hans"
    normalized_scope = analysis_scope.strip()
    if len(normalized_language) > 32:
        raise CliError("invalid_input", "Deconstruction language must be at most 32 characters.")
    if len(normalized_scope) > 2000:
        raise CliError("invalid_input", "Deconstruction analysis scope must be at most 2000 characters.")
    ffmpeg, ffprobe = _required_ffmpeg()
    metadata = _probe_video(ffprobe, video)
    duration = metadata["duration_sec"]
    workspace, plan_path = _plan_destinations(video, out)
    frames_dir = workspace / "reference-frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    cut_points = _detect_scene_cuts(
        ffmpeg,
        video,
        duration,
        threshold=scene_threshold,
        max_count=max(0, min(int(max_shots) - 1, 119)),
    )
    segments = generation_segments(duration, cut_points)[: max(1, min(int(max_shots), 120))]
    shots: list[dict[str, Any]] = []
    for index, segment in enumerate(segments, start=1):
        frame_paths = _extract_reference_frames(
            ffmpeg,
            video,
            segment,
            frames_dir,
            index,
        )
        shots.append(
            {
                "index": index,
                "start_sec": segment["start_sec"],
                "end_sec": segment["end_sec"],
                "generation_duration_sec": max(
                    3,
                    min(15, int(math.floor(segment["duration_sec"] + 0.5))),
                ),
                "continues_previous": segment["continues_previous"],
                "reference_frame_paths": [str(path) for path in frame_paths],
            }
        )

    payloads: list[dict[str, Any]] = []
    batches = [shots[index : index + 8] for index in range(0, len(shots), 8)]
    for batch_index, batch in enumerate(batches, start=1):
        payloads.append(
            client.deconstruct_frames(
                _deconstruct_request(
                    video,
                    duration,
                    metadata["aspect_ratio"],
                    batch,
                    batch_index=batch_index,
                    batch_count=len(batches),
                    language=normalized_language,
                    analysis_scope=normalized_scope,
                )
            )
        )

    plan = _make_plan(
        video,
        workspace,
        duration,
        metadata["aspect_ratio"],
        shots,
        payloads,
        language=normalized_language,
        analysis_scope=normalized_scope,
    )
    if replacement_references:
        plan["replacement_references"] = _import_replacement_references(
            replacement_references,
            workspace,
            existing=[],
        )
    _write_json(plan_path, plan)
    return {
        "status": "done",
        "source_video_path": str(video),
        "plan_path": str(plan_path),
        "workspace_path": str(workspace),
        "shot_count": len(shots),
        "aspect_ratio": metadata["aspect_ratio"],
        "duration_sec": duration,
        "language": normalized_language,
        "analysis_scope": normalized_scope,
        "replacement_reference_count": len(plan.get("replacement_references") or []),
        "artifacts": [
            artifact_ref_from_path(
                plan_path,
                metadata={
                    "artifact_role": "deconstruction_plan",
                    "producer_step": "deconstruct_video",
                    "source_video_name": video.name,
                    "delivery_role": "primary",
                },
            )
        ],
        "privacy_receipt": {
            "source_video": "stayed_local",
            "hosted_inputs": ["sampled_frames"],
            "local_steps": ["probe_video", "detect_scene_cuts", "extract_video_frames"],
            "cloud_steps": ["deconstruct_video"],
            "local_final_video_processing": False,
        },
    }


def regenerate_deconstruction(
    client: RuntimeClient,
    plan_path: Path,
    *,
    out: Path | None = None,
    replacement_references: list[dict[str, str]] | None = None,
    resolution: str = "720P",
    preserve_original_audio: bool = True,
    model: str | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    checked_plan = require_existing_file(plan_path)
    plan = _read_plan(checked_plan)
    source = require_existing_file(Path(str(plan.get("source_path") or "")))
    workspace = Path(str(plan.get("workspace_path") or checked_plan.parent)).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if replacement_references:
        plan["replacement_references"] = _import_replacement_references(
            replacement_references,
            workspace,
            existing=list(plan.get("replacement_references") or []),
        )
        _write_json(checked_plan, plan)

    replacements = _available_replacements(plan)
    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        raise CliError("invalid_input", "The deconstruction plan has no shots to generate.")
    generated_dir = workspace / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    generated_clips: list[Path] = []
    previous_tail: Path | None = None
    ffmpeg, _ = _required_ffmpeg()

    for index, raw_shot in enumerate(shots, start=1):
        if not isinstance(raw_shot, dict):
            raise CliError("invalid_input", f"shots[{index - 1}] must be a JSON object.")
        continues = bool(raw_shot.get("continues_previous"))
        timeline_frame = previous_tail if continues and previous_tail else _first_frame(raw_shot)
        reference_paths = [timeline_frame] if timeline_frame else []
        reference_paths.extend(Path(item["path"]) for item in replacements)
        if replacements:
            mode = "reference"
            first_frame = None
            references = [str(path) for path in reference_paths[:9]]
        elif timeline_frame:
            mode = "first_frame"
            first_frame = str(timeline_frame)
            references = []
        else:
            mode = "text"
            first_frame = None
            references = []
        prompt = combined_generation_prompt(
            str(plan.get("global_prompt") or ""),
            raw_shot,
            continuing=continues and previous_tail is not None,
            has_timeline_reference=timeline_frame is not None,
            replacements=replacements,
        )
        result = client.video(
            prompt,
            out=generated_dir,
            aspect_ratio=str(plan.get("aspect_ratio") or "16:9"),
            resolution=resolution.strip().upper(),
            duration=max(3, min(15, int(raw_shot.get("generation_duration_sec") or 5))),
            generate_audio=False,
            generation_mode=mode,
            first_frame_image_url=first_frame,
            reference_image_urls=references,
            model=model,
            model_name=model_name,
            model_version=model_version,
            timeout=timeout,
        )
        clip = _generated_video_path(result)
        generated_clips.append(clip)
        previous_tail = _extract_tail_frame(ffmpeg, clip, generated_dir, index)

    output_path = _regenerated_output_path(source, workspace, out)
    _assemble_generated_video(
        ffmpeg,
        generated_clips,
        [item for item in shots if isinstance(item, dict)],
        source,
        output_path,
        resolution=resolution,
        aspect_ratio=str(plan.get("aspect_ratio") or "16:9"),
        preserve_original_audio=preserve_original_audio,
    )
    video_artifact = artifact_ref_from_path(
        output_path,
        metadata={
            "artifact_role": "generated_video",
            "delivery_role": "primary",
            "producer_step": "regenerate_deconstruction",
            "source_video_name": source.name,
            "deconstruction_plan_path": str(checked_plan),
        },
    )
    plan_artifact = artifact_ref_from_path(
        checked_plan,
        metadata={
            "artifact_role": "deconstruction_plan",
            "delivery_role": "supporting",
            "producer_step": "deconstruct_video",
            "source_video_name": source.name,
        },
    )
    return {
        "status": "done",
        "video_output_path": str(output_path),
        "source_video_path": str(source),
        "plan_path": str(checked_plan),
        "generated_clip_count": len(generated_clips),
        "replacement_reference_count": len(replacements),
        "preserved_original_audio": preserve_original_audio and _source_has_audio(source),
        "artifacts": [video_artifact, plan_artifact],
        "primary_artifacts": [video_artifact],
        "supporting_artifacts": [plan_artifact],
        "intermediate_artifacts": [],
        "privacy_receipt": {
            "source_video": "stayed_local",
            "hosted_inputs": [
                "sampled_frames",
                *(["reference_images"] if replacements else []),
            ],
            "local_steps": ["extract_video_frames", "merge_video_clips"],
            "cloud_steps": ["generate_video"],
            "local_final_video_processing": True,
        },
    }


def generation_segments(duration: float, cut_points: list[float]) -> list[dict[str, Any]]:
    boundaries = [0.0, *sorted(point for point in cut_points if 0 < point < duration), duration]
    split: list[dict[str, Any]] = []
    for start, end in zip(boundaries, boundaries[1:]):
        shot_duration = max(0.1, end - start)
        part_count = max(1, int(math.ceil(shot_duration / 15.0)))
        part_duration = shot_duration / part_count
        for part in range(part_count):
            part_start = start + part * part_duration
            part_end = end if part == part_count - 1 else start + (part + 1) * part_duration
            split.append(
                {
                    "start_sec": part_start,
                    "end_sec": part_end,
                    "duration_sec": part_end - part_start,
                    "continues_previous": part > 0,
                }
            )

    merged: list[dict[str, Any]] = []
    for segment in split:
        if (
            segment["duration_sec"] < 3
            and merged
            and merged[-1]["duration_sec"] + segment["duration_sec"] <= 15
        ):
            merged[-1]["end_sec"] = segment["end_sec"]
            merged[-1]["duration_sec"] = merged[-1]["end_sec"] - merged[-1]["start_sec"]
            continue
        merged.append(dict(segment))
    if (
        len(merged) > 1
        and merged[-1]["duration_sec"] < 3
        and merged[-2]["duration_sec"] + merged[-1]["duration_sec"] <= 15
    ):
        merged[-2]["end_sec"] = merged[-1]["end_sec"]
        merged[-2]["duration_sec"] = merged[-2]["end_sec"] - merged[-2]["start_sec"]
        merged.pop()
    return merged or [
        {
            "start_sec": 0.0,
            "end_sec": duration,
            "duration_sec": duration,
            "continues_previous": False,
        }
    ]


def combined_generation_prompt(
    global_prompt: str,
    shot: dict[str, Any],
    *,
    continuing: bool,
    has_timeline_reference: bool,
    replacements: list[dict[str, str]],
) -> str:
    if has_timeline_reference:
        continuity = (
            "Reference image 1 is the previous clip's final frame. Continue seamlessly from it "
            "without resetting the action phase, motion direction, camera trajectory, pose, or camera."
            if continuing
            else "Reference image 1 is the source shot's opening frame. Start as close as possible "
            "to its composition, pose, camera position, environment, and lighting."
        )
    else:
        continuity = "Build a coherent opening composition from the shot direction and supplied replacement references."
    replacement_start = 2 if has_timeline_reference else 1
    replacement_lines: list[str] = []
    targets = {
        "person": "the main person's identity, face, hair, and recognizable appearance",
        "product": "the featured product's shape, materials, colors, branding-free details, and recognizable appearance",
        "scene": "the environment, set design, spatial layout, color palette, and lighting mood",
    }
    for offset, reference in enumerate(replacements):
        replacement_lines.append(
            f"Reference image {replacement_start + offset}: replace {targets[reference['role']]} "
            "while preserving the source shot's action, framing, and pacing."
        )
    replacement_guidance = ""
    if replacement_lines:
        replacement_guidance = (
            "\n\nUser-requested visual replacements:\n"
            + "\n".join(replacement_lines)
            + "\nKeep each replacement consistent across the entire clip. Do not copy unwanted "
            "text, logos, borders, or backgrounds from the replacement images."
        )
    negative = str(
        shot.get("negative_prompt")
        or "text, subtitles, logo, watermark, identity drift, abrupt motion"
    )
    return (
        f"Global creative direction:\n{global_prompt}\n\n"
        f"Shot {shot.get('index')}, {shot.get('generation_duration_sec')} seconds:\n"
        f"{shot.get('generation_prompt') or global_prompt}\n\n"
        f"{continuity}{replacement_guidance}\n"
        "Keep motion temporally coherent and end on a stable natural frame suitable for the next shot.\n"
        f"Avoid: {negative}, captions, subtitles, logos, watermarks, duplicated subjects, "
        "identity drift, flicker, sudden camera jumps."
    )


def _required_ffmpeg() -> tuple[Path, Path]:
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    if not ffmpeg:
        raise CliError("dependency_missing", "ffmpeg is required for video deconstruction.")
    ffprobe = resolve_ffprobe(ffmpeg)
    if not ffprobe:
        raise CliError("dependency_missing", "ffprobe is required for video deconstruction.")
    return ffmpeg, ffprobe


def _probe_video(ffprobe: Path, video: Path) -> dict[str, Any]:
    completed = _run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(video),
        ],
        "ffprobe could not inspect the source video.",
    )
    try:
        payload = json.loads(completed.stdout)
        stream = payload["streams"][0]
        duration = float(payload["format"]["duration"])
        width = int(stream["width"])
        height = int(stream["height"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CliError("processing_failed", "The source video metadata is incomplete.") from exc
    if duration <= 0 or width <= 0 or height <= 0:
        raise CliError("processing_failed", "The source video has invalid duration or dimensions.")
    ratio = width / height
    aspect_ratio = (
        "16:9"
        if ratio > 1.45
        else "9:16"
        if ratio < 0.72
        else "4:3"
        if ratio > 1.15
        else "3:4"
        if ratio < 0.88
        else "1:1"
    )
    return {
        "duration_sec": duration,
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
    }


def _detect_scene_cuts(
    ffmpeg: Path,
    video: Path,
    duration: float,
    *,
    threshold: float,
    max_count: int,
) -> list[float]:
    safe_threshold = min(max(float(threshold), 0.01), 0.99)
    completed = _run(
        [
            str(ffmpeg),
            "-nostdin",
            "-hide_banner",
            "-i",
            str(video),
            "-filter:v",
            f"select='gt(scene,{safe_threshold:g})',showinfo",
            "-f",
            "null",
            "-",
        ],
        "ffmpeg scene detection failed.",
    )
    candidates = [
        float(value)
        for value in re.findall(r"pts_time:([0-9]+(?:\.[0-9]+)?)", completed.stderr)
        if 0.35 < float(value) < duration - 0.35
    ]
    result: list[float] = []
    for candidate in sorted(candidates):
        if result and candidate - result[-1] < 0.75:
            continue
        result.append(candidate)
        if len(result) >= max_count:
            break
    return result


def _extract_reference_frames(
    ffmpeg: Path,
    video: Path,
    segment: dict[str, Any],
    output_dir: Path,
    index: int,
) -> list[Path]:
    start = float(segment["start_sec"])
    end = float(segment["end_sec"])
    duration = end - start
    inset = min(0.12, max(0.03, duration * 0.05))
    timestamps = [min(end, start + inset), (start + end) / 2, max(start, end - inset)]
    paths: list[Path] = []
    for role, timestamp in zip(("first", "middle", "last"), timestamps):
        path = output_dir / f"shot-{index:03d}-{role}.jpg"
        _extract_frame(ffmpeg, video, timestamp, path)
        paths.append(path)
    return paths


def _extract_frame(ffmpeg: Path, video: Path, timestamp: float, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            str(ffmpeg),
            "-nostdin",
            "-y",
            "-ss",
            f"{max(timestamp, 0.0):.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale='min(960,iw)':-2",
            "-q:v",
            "3",
            "-update",
            "1",
            str(output),
        ],
        "ffmpeg could not extract a reference frame.",
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise CliError("processing_failed", f"Reference frame extraction produced no file: {output}")


def _deconstruct_request(
    video: Path,
    duration: float,
    aspect_ratio: str,
    shots: list[dict[str, Any]],
    *,
    batch_index: int,
    batch_count: int,
    language: str = "zh-Hans",
    analysis_scope: str = "",
) -> dict[str, Any]:
    frames: list[dict[str, Any]] = []
    shot_requests: list[dict[str, Any]] = []
    frame_index = 1
    for shot in shots:
        indexes: list[int] = []
        paths = [Path(value) for value in shot["reference_frame_paths"]]
        for offset, path in enumerate(paths):
            role = "first" if offset == 0 else "last" if offset == len(paths) - 1 else "middle"
            timestamp = (
                float(shot["start_sec"])
                if role == "first"
                else float(shot["end_sec"])
                if role == "last"
                else (float(shot["start_sec"]) + float(shot["end_sec"])) / 2
            )
            frames.append(
                {
                    "frame_index": frame_index,
                    "shot_index": int(shot["index"]),
                    "timestamp_sec": timestamp,
                    "role": role,
                    "image_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
                    "mime_type": "image/jpeg",
                }
            )
            indexes.append(frame_index)
            frame_index += 1
        shot_requests.append(
            {
                "shot_index": int(shot["index"]),
                "start_sec": float(shot["start_sec"]),
                "end_sec": float(shot["end_sec"]),
                "continues_previous": bool(shot["continues_previous"]),
                "frame_indexes": indexes,
            }
        )
    identity = f"{video.resolve()}:{video.stat().st_size}:{video.stat().st_mtime_ns}"
    return {
        "local_asset_id": f"local-{hashlib.sha256(identity.encode()).hexdigest()[:20]}",
        "name": video.name,
        "duration_sec": duration,
        "aspect_ratio": aspect_ratio,
        "language": language,
        "analysis_scope": analysis_scope,
        "batch_index": batch_index,
        "batch_count": batch_count,
        "frames": frames,
        "shots": shot_requests,
    }


def _make_plan(
    video: Path,
    workspace: Path,
    duration: float,
    aspect_ratio: str,
    source_shots: list[dict[str, Any]],
    payloads: list[dict[str, Any]],
    *,
    language: str,
    analysis_scope: str,
) -> dict[str, Any]:
    response_shots = {
        int(shot["shot_index"]): shot
        for payload in payloads
        for shot in payload.get("shots") or []
        if isinstance(shot, dict) and shot.get("shot_index") is not None
    }
    global_prompts = _unique_text(payload.get("global_prompt") for payload in payloads)
    styles = _unique_text(payload.get("style_summary") for payload in payloads)
    audio_prompts = _unique_text(payload.get("audio_prompt") for payload in payloads)
    global_prompt = "\n".join(global_prompts) or (
        "Recreate the source video's visible subjects, actions, camera language, lighting, "
        "color palette, pacing, and cinematic texture."
    )
    plan_shots: list[dict[str, Any]] = []
    for source in source_shots:
        payload = response_shots.get(int(source["index"]), {})
        plan_shots.append(
            {
                **source,
                "title": str(payload.get("title") or f"Shot {source['index']}"),
                "summary": str(payload.get("summary") or ""),
                "generation_prompt": str(payload.get("generation_prompt") or global_prompt),
                "negative_prompt": str(
                    payload.get("negative_prompt")
                    or "text, subtitles, logo, watermark, identity drift, abrupt motion"
                ),
                "subject": str(payload.get("subject") or ""),
                "action": str(payload.get("action") or ""),
                "camera": str(payload.get("camera") or ""),
                "lighting": str(payload.get("lighting") or ""),
                "visual_style": str(payload.get("visual_style") or (styles[0] if styles else "")),
                "transition_out": str(payload.get("transition_out") or "cut"),
                "tags": list(payload.get("tags") or []),
            }
        )
    return {
        "id": str(uuid4()),
        "source_path": str(video),
        "source_name": video.name,
        "duration_sec": duration,
        "aspect_ratio": aspect_ratio,
        "language": language,
        "analysis_scope": analysis_scope,
        "global_prompt": global_prompt,
        "style_summary": "\n".join(styles),
        "audio_prompt": "\n".join(audio_prompts),
        "shots": plan_shots,
        "replacement_references": [],
        "vision_model": str(payloads[-1].get("vision_model") or "") if payloads else "",
        "analyzed_at": str(payloads[-1].get("analyzed_at") or "") if payloads else "",
        "workspace_path": str(workspace),
    }


def _unique_text(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _plan_destinations(video: Path, out: Path | None) -> tuple[Path, Path]:
    if out:
        expanded = out.expanduser().resolve()
        if expanded.suffix.lower() == ".json":
            workspace = expanded.parent
            plan_path = expanded
        else:
            workspace = expanded
            plan_path = workspace / "deconstruction.json"
    else:
        workspace = video.parent / f"{video.stem}.deconstruction"
        plan_path = workspace / "deconstruction.json"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace, plan_path


def _import_replacement_references(
    references: list[dict[str, str]],
    workspace: Path,
    *,
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    imported = [
        item
        for item in existing
        if isinstance(item, dict)
        and item.get("path")
        and Path(str(item["path"])).expanduser().is_file()
        and str(item.get("role") or "") in _REPLACEMENT_ROLES
    ]
    directory = workspace / "replacement-references"
    directory.mkdir(parents=True, exist_ok=True)
    for item in references:
        if len(imported) >= 8:
            break
        path = require_existing_file(Path(str(item.get("path") or "")))
        if path.suffix.lower() not in _IMAGE_SUFFIXES:
            raise CliError("invalid_input", "Replacement references support PNG, JPEG, or WebP.")
        role = str(item.get("role") or "person").strip().lower()
        if role not in _REPLACEMENT_ROLES:
            raise CliError("invalid_input", "Replacement role must be person, product, or scene.")
        destination = directory / f"reference-{uuid4().hex}{path.suffix.lower()}"
        shutil.copy2(path, destination)
        imported.append({"id": str(uuid4()), "path": str(destination), "role": role})
    return imported[:8]


def _available_replacements(plan: dict[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in plan.get("replacement_references") or []:
        if not isinstance(item, dict):
            continue
        path = Path(str(item.get("path") or "")).expanduser().resolve()
        role = str(item.get("role") or "").lower()
        if path.is_file() and role in _REPLACEMENT_ROLES:
            result.append({"path": str(path), "role": role})
        if len(result) >= 8:
            break
    return result


def _first_frame(shot: dict[str, Any]) -> Path | None:
    for value in shot.get("reference_frame_paths") or []:
        path = Path(str(value)).expanduser().resolve()
        if path.is_file():
            return path
    return None


def _generated_video_path(result: dict[str, Any]) -> Path:
    outputs = result.get("outputs")
    value = result.get("video_path")
    if not value and isinstance(outputs, dict):
        value = outputs.get("video_path")
    if not value:
        raise CliError("invalid_response", "CinLink video generation returned no video_path.")
    return require_existing_file(Path(str(value)))


def _extract_tail_frame(
    ffmpeg: Path,
    video: Path,
    output_dir: Path,
    index: int,
) -> Path:
    _, ffprobe = _required_ffmpeg()
    duration = _probe_duration(ffprobe, video)
    output = output_dir / f"generated-{index:03d}-tail.jpg"
    failures: list[str] = []
    seen: set[float] = set()
    for offset in (0.06, 0.25, 1.0):
        timestamp = max(0.0, duration - offset)
        if round(timestamp, 3) in seen:
            continue
        seen.add(round(timestamp, 3))
        if output.exists():
            output.unlink()
        try:
            _extract_frame(ffmpeg, video, timestamp, output)
            return output
        except CliError as exc:
            failures.append(exc.message)
    raise CliError(
        "processing_failed",
        "Could not extract a stable tail frame from a generated clip.",
        {"failures": failures},
    )


def _probe_duration(ffprobe: Path, video: Path) -> float:
    completed = _run(
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
        "ffprobe could not read generated clip duration.",
    )
    try:
        return max(float(completed.stdout.strip()), 0.1)
    except ValueError as exc:
        raise CliError("processing_failed", "Generated clip duration was invalid.") from exc


def _assemble_generated_video(
    ffmpeg: Path,
    clips: list[Path],
    shots: list[dict[str, Any]],
    source: Path,
    output: Path,
    *,
    resolution: str,
    aspect_ratio: str,
    preserve_original_audio: bool,
) -> None:
    width, height = _target_dimensions(resolution, aspect_ratio)
    has_audio = preserve_original_audio and _source_has_audio(source)
    inputs: list[str] = []
    for clip in clips:
        inputs.extend(["-i", str(clip)])
    if has_audio:
        inputs.extend(["-i", str(source)])
    filters: list[str] = []
    concat_inputs = ""
    for index in range(len(clips)):
        remove_duplicate = index > 0 and index < len(shots) and bool(shots[index].get("continues_previous"))
        trim = "trim=start=0.034," if remove_duplicate else ""
        filters.append(
            f"[{index}:v]{trim}setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{index}]"
        )
        concat_inputs += f"[v{index}]"
    filters.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=0[outv]")
    if has_audio:
        filters.append(f"[{len(clips)}:a]aresample=48000,apad[aout]")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg),
        "-nostdin",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[outv]",
        *(["-map", "[aout]"] if has_audio else []),
        *_video_encoder_args(ffmpeg),
        *(["-c:a", "aac", "-b:a", "192k", "-shortest"] if has_audio else ["-an"]),
        "-movflags",
        "+faststart",
        str(output),
    ]
    _run(command, "ffmpeg could not assemble the regenerated video.")


def _target_dimensions(resolution: str, aspect_ratio: str) -> tuple[int, int]:
    base = {"1080P": 1080, "2K": 1440, "4K": 2160}.get(resolution.strip().upper(), 720)

    def even(value: float) -> int:
        integer = max(2, int(value))
        return integer // 2 * 2

    return {
        "9:16": (base, even(base * 16 / 9)),
        "1:1": (base, base),
        "3:4": (base, even(base * 4 / 3)),
        "4:3": (even(base * 4 / 3), base),
    }.get(aspect_ratio, (even(base * 16 / 9), base))


def _source_has_audio(video: Path) -> bool:
    ffmpeg = resolve_ffmpeg(require_subtitles=False)
    ffprobe = resolve_ffprobe(ffmpeg) if ffmpeg else None
    if not ffprobe:
        return False
    completed = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(video),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode == 0 and bool(completed.stdout.strip())


def _regenerated_output_path(source: Path, workspace: Path, out: Path | None) -> Path:
    if out:
        expanded = out.expanduser().resolve()
        if expanded.suffix.lower() in {".mp4", ".mov", ".mkv"}:
            expanded.parent.mkdir(parents=True, exist_ok=True)
            return expanded
        expanded.mkdir(parents=True, exist_ok=True)
        return expanded / f"{source.stem}.regenerated.mp4"
    return workspace / f"{source.stem}.regenerated.mp4"


def _read_plan(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError("invalid_input", f"Could not read deconstruction plan: {path}") from exc
    if not isinstance(payload, dict):
        raise CliError("invalid_input", "The deconstruction plan must be a JSON object.")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


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
