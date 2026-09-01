from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from .client import RuntimeClient
from .config import (
    Settings,
    brand_kit_payload,
    load_settings,
    render_options,
    save_settings,
    update_brand_kit,
)
from .dependencies import local_dependency_report, require_local_voice_separation_if_requested
from .deconstruction import deconstruct_video, regenerate_deconstruction
from .editor_exports import export_audio, export_editor_project, export_video
from .errors import CliError
from .enhancement import enhance_image, enhance_video
from .local_setup import setup_local_dependencies
from .local_tools import (
    apply_watermark,
    burn_subtitles,
    clean_cut,
    create_montage,
    mix_dubbed_audio,
    trim_video,
)
from .schemas import TOOL_SCHEMAS
from .workflows import add_subtitles


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
        except CliError as exc:
            response = _error_response(_request_id_from_line(line), exc.code, exc.message, exc.details)
        except Exception as exc:
            response = _error_response(_request_id_from_line(line), "internal_error", str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cinlink-cli", "version": "0.1.0"},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": name,
                        "description": schema["description"],
                        "inputSchema": schema["input_schema"],
                    }
                    for name, schema in TOOL_SCHEMAS.items()
                ]
            },
        }
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or name not in TOOL_SCHEMAS:
            raise CliError("invalid_input", f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            raise CliError("invalid_input", "Tool arguments must be a JSON object.")
        result = call_tool(name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                "isError": False,
            },
        }
    raise CliError("invalid_input", f"Unsupported MCP method: {method}")


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "agent_run":
        require_local_voice_separation_if_requested(args["prompt"])
    if name == "configure":
        existing = load_settings(allow_missing_api_key=True)
        settings = Settings(
            api_key=args.get("api_key") or existing.api_key,
            runtime_base=args.get("runtime_base") or existing.runtime_base,
            billing_base=args.get("billing_base") or existing.billing_base,
            timeout_sec=existing.timeout_sec,
            poll_interval_sec=existing.poll_interval_sec,
            brand_kit=existing.brand_kit,
        )
        if not settings.api_key:
            raise CliError("invalid_input", "Pass api_key or set CINLINK_API_KEY.")
        path = save_settings(settings)
        return {"status": "done", "config_path": str(path), "runtime_base": settings.runtime_base, "billing_base": settings.billing_base}
    if name == "setup_local_deps":
        return setup_local_dependencies(
            assume_yes=bool(args.get("yes", False)),
            dry_run=bool(args.get("dry_run", False)),
            skip_ffmpeg=bool(args.get("skip_ffmpeg", False)),
            with_voice_separation=bool(args.get("with_voice_separation", False)),
            skip_voice_separation=bool(args.get("skip_voice_separation", False)),
            with_enhancement=bool(args.get("with_enhancement", False)),
            skip_enhancement=bool(args.get("skip_enhancement", False)),
            interactive=False,
        )
    if name == "brand_kit":
        settings = load_settings(allow_missing_api_key=True)
        action = str(args.get("action") or "show")
        if action == "show":
            return {"status": "done", "brand_kit": brand_kit_payload(settings)}
        if action == "clear":
            return {"status": "done", "brand_kit": update_brand_kit(settings, {"enabled": False}, clear=True)}
        if action != "set":
            raise CliError("invalid_input", "brand_kit action must be show, set, or clear.")
        changes = {
            key: value
            for key, value in args.items()
            if key not in {"action"} and value is not None
        }
        if not changes:
            raise CliError("invalid_input", "Brand Kit set requires at least one setting.")
        return {"status": "done", "brand_kit": update_brand_kit(settings, changes)}
    local_only_tools = {
        "apply_watermark",
        "brand_kit",
        "burn",
        "clean_cut",
        "doctor",
        "export_audio",
        "export_editor_project",
        "export_video",
        "enhance_image",
        "enhance_video",
        "mix_dubbed_audio",
        "montage",
        "trim_video",
    }
    settings = load_settings(allow_missing_api_key=name in local_only_tools)
    client = RuntimeClient(settings)
    if name == "doctor":
        payload: dict[str, Any] = {"local_dependencies": local_dependency_report()}
        try:
            payload["runtime_health"] = client.health()
        except CliError as exc:
            payload["runtime_health"] = exc.to_payload()["error"]
        return payload
    if name == "transcribe":
        return client.transcribe(Path(args["input_path"]), lang=args.get("lang", "auto"), out=_path(args.get("out")), timeout=args.get("timeout"))
    if name == "translate":
        return client.translate(
            Path(args["input_path"]),
            from_lang=args.get("from_lang", "auto"),
            to_lang=args.get("to_lang", "zh"),
            bilingual=bool(args.get("bilingual", False)),
            delivery=args.get("delivery", "subtitle"),
            out=_path(args.get("out")),
            timeout=args.get("timeout"),
        )
    if name == "add_subtitles":
        render = _render_options(args, settings)
        return add_subtitles(
            client,
            Path(args["video_path"]),
            subtitle_path=_path(args.get("subtitle_path")),
            source_lang=args.get("source_lang", "auto"),
            target_lang=args.get("target_lang"),
            bilingual=bool(args.get("bilingual", False)),
            out=_path(args.get("out")),
            timeout=args.get("timeout"),
            font_size=render["font_size"],
            font_name=render["font_name"],
            font_color=render["font_color"],
            outline_color=render["outline_color"],
            outline_width=render["outline_width"],
            margin_v=render["margin_v"],
            position=render["position"],
            watermark_text=render["watermark_text"],
            watermark_position=render["watermark_position"],
            watermark_font_size=render["watermark_font_size"],
            watermark_color=render["watermark_color"],
            watermark_opacity=render["watermark_opacity"],
            watermark_margin=render["watermark_margin"],
            watermark_image_path=_path(render["watermark_image_path"]),
            watermark_image_position=render["watermark_image_position"],
            watermark_image_width=render["watermark_image_width"],
            watermark_image_opacity=render["watermark_image_opacity"],
            watermark_image_margin=render["watermark_image_margin"],
        )
    if name == "dub":
        return client.dub(
            Path(args["video_path"]),
            Path(args["subtitle_path"]),
            reference_subtitle_path=_path(args.get("reference_subtitle_path")),
            reference_audio_paths=_path_dict(args.get("reference_audio_paths")),
            voice=args.get("voice"),
            language=args.get("language", "zh"),
            out=_path(args.get("out")),
            timeout=args.get("timeout"),
        )
    if name == "burn":
        render = _render_options(args, settings)
        return burn_subtitles(
            Path(args["video_path"]),
            Path(args["subtitle_path"]),
            out=_path(args.get("out")),
            font_size=render["font_size"],
            font_name=render["font_name"],
            font_color=render["font_color"],
            outline_color=render["outline_color"],
            outline_width=render["outline_width"],
            margin_v=render["margin_v"],
            position=render["position"],
            watermark_text=render["watermark_text"],
            watermark_position=render["watermark_position"],
            watermark_font_size=render["watermark_font_size"],
            watermark_color=render["watermark_color"],
            watermark_opacity=render["watermark_opacity"],
            watermark_margin=render["watermark_margin"],
            watermark_image_path=_path(render["watermark_image_path"]),
            watermark_image_position=render["watermark_image_position"],
            watermark_image_width=render["watermark_image_width"],
            watermark_image_opacity=render["watermark_image_opacity"],
            watermark_image_margin=render["watermark_image_margin"],
        )
    if name == "apply_watermark":
        render = _render_options(args, settings)
        return apply_watermark(
            Path(args["video_path"]),
            out=_path(args.get("out")),
            watermark_text=render["watermark_text"],
            watermark_position=render["watermark_position"],
            watermark_font_size=render["watermark_font_size"],
            watermark_color=render["watermark_color"],
            watermark_opacity=render["watermark_opacity"],
            watermark_margin=render["watermark_margin"],
            watermark_image_path=_path(render["watermark_image_path"]),
            watermark_image_position=render["watermark_image_position"],
            watermark_image_width=render["watermark_image_width"],
            watermark_image_opacity=render["watermark_image_opacity"],
            watermark_image_margin=render["watermark_image_margin"],
        )
    if name == "trim_video":
        return trim_video(
            Path(args["video_path"]),
            start_sec=float(args["start_sec"]),
            end_sec=float(args["end_sec"]),
            out=_path(args.get("out")),
        )
    if name == "enhance_image":
        return enhance_image(
            Path(args["image_path"]),
            out=_path(args.get("out")),
            scale=int(args.get("scale", 2)),
            noise_level=int(args.get("noise_level", 1)),
            model=str(args.get("model", "photo")),
        )
    if name == "enhance_video":
        return enhance_video(
            Path(args["video_path"]),
            out=_path(args.get("out")),
            scale=int(args.get("scale", 2)),
            noise_level=int(args.get("noise_level", 1)),
            model=str(args.get("model", "photo")),
        )
    if name == "montage":
        clips = args.get("clips")
        if not isinstance(clips, list):
            raise CliError("invalid_input", "montage clips must be a JSON array.")
        return create_montage(clips, out=_path(args.get("out")))
    if name == "clean_cut":
        selected_removal_indexes = args.get("selected_removal_indexes")
        if selected_removal_indexes is not None and not isinstance(selected_removal_indexes, list):
            raise CliError("invalid_input", "selected_removal_indexes must be a JSON array.")
        return clean_cut(
            Path(args["video_path"]),
            out=_path(args.get("out")),
            minimum_silence_sec=float(args.get("minimum_silence_sec", 0.85)),
            noise_threshold_db=float(args.get("noise_threshold_db", -35.0)),
            retained_pause_sec=float(args.get("retained_pause_sec", 0.24)),
            minimum_removal_sec=float(args.get("minimum_removal_sec", 0.18)),
            plan_only=bool(args.get("plan_only", False)),
            selected_removal_indexes=selected_removal_indexes,
        )
    if name == "mix_dubbed_audio":
        return mix_dubbed_audio(
            Path(args["video_path"]),
            Path(args["dubbed_audio_path"]),
            out=_path(args.get("out")),
            original_volume=float(args.get("original_volume", 0.65)),
            dubbed_volume=float(args.get("dubbed_volume", 1.0)),
        )
    if name == "summarize":
        return client.summarize(Path(args["input_path"]), out=_path(args.get("out")), max_highlights=int(args.get("max_highlights", 3)))
    if name == "shorten":
        return client.shorten(
            Path(args["video_path"]),
            out=_path(args.get("out")),
            max_clips=int(args.get("max_clips", 5)),
            target_duration=int(args.get("target_duration", 45)),
            style_preset=args.get("style_preset"),
            music_mode=args.get("music_mode", "none"),
            music_prompt=args.get("music_prompt"),
            selection_instruction=args.get("selection_instruction"),
            output_language=args.get("output_language"),
        )
    if name == "image":
        return client.image(
            args["prompt"],
            out=_path(args.get("out")),
            aspect_ratio=args.get("aspect_ratio", "1:1"),
            image_size=args.get("image_size", "1K"),
            reference_image_urls=args.get("reference_image_urls") or [],
            model=args.get("model"),
            timeout=_float_or_none(args.get("timeout")),
        )
    if name == "video":
        return client.video(
            args["prompt"],
            out=_path(args.get("out")),
            aspect_ratio=args.get("aspect_ratio", "16:9"),
            resolution=args.get("resolution", "720P"),
            duration=int(args.get("duration", 5)),
            generate_audio=bool(args.get("generate_audio", True)),
            watermark=bool(args.get("watermark", False)),
            generation_mode=args.get("generation_mode"),
            first_frame_image_url=args.get("first_frame_image_url"),
            reference_image_urls=args.get("reference_image_urls") or [],
            reference_video_urls=args.get("reference_video_urls") or [],
            reference_audio_urls=args.get("reference_audio_urls") or [],
            model=args.get("model"),
            model_name=args.get("model_name"),
            model_version=args.get("model_version"),
            timeout=_float_or_none(args.get("timeout")),
        )
    if name == "deconstruct_video":
        return deconstruct_video(
            client,
            Path(args["video_path"]),
            out=_path(args.get("out")),
            replacement_references=_replacement_references(
                args.get("replacement_references")
            ),
            language=str(args.get("language", "zh-Hans")),
            analysis_scope=str(args.get("analysis_scope", "")),
            scene_threshold=float(args.get("scene_threshold", 0.28)),
            max_shots=int(args.get("max_shots", 120)),
        )
    if name == "regenerate_deconstruction":
        return regenerate_deconstruction(
            client,
            Path(args["plan_path"]),
            out=_path(args.get("out")),
            replacement_references=_replacement_references(
                args.get("replacement_references")
            ),
            resolution=str(args.get("resolution", "720P")),
            preserve_original_audio=bool(
                args.get("preserve_original_audio", True)
            ),
            model=args.get("model"),
            model_name=args.get("model_name"),
            model_version=args.get("model_version"),
            timeout=_float_or_none(args.get("timeout")),
        )
    if name == "export_video":
        return export_video(
            Path(args["video_path"]),
            output_format=str(args.get("output_format", "mp4")),
            out=_path(args.get("out")),
        )
    if name == "export_audio":
        return export_audio(
            Path(args["video_path"]),
            output_format=str(args.get("output_format", "wav")),
            audio_path=_path(args.get("audio_path")),
            out=_path(args.get("out")),
        )
    if name == "export_editor_project":
        return export_editor_project(
            Path(args["video_path"]),
            target=str(args["target"]),
            subtitle_path=_path(args.get("subtitle_path")),
            audio_path=_path(args.get("audio_path")),
            out=_path(args.get("out")),
        )
    if name == "nlu":
        return client.nlu(
            args["prompt"],
            has_video=bool(args.get("has_video", False)),
            has_subtitle=bool(args.get("has_subtitle", False)),
            pending_target_language=args.get("pending_target_language"),
            context_files=args.get("context_files") or [],
        )
    if name == "agent_run":
        context_descriptors = args.get("context_descriptors")
        if context_descriptors is not None and not isinstance(context_descriptors, list):
            raise CliError("invalid_input", "context_descriptors must be a JSON array.")
        created = client.create_agent_run(
            args["prompt"],
            conversation_id=args.get("conversation_id"),
            context_files=[Path(item) for item in args.get("context_file", [])],
            context_descriptors=context_descriptors or [],
            mode=args.get("mode", "execute"),
            task_intent=args.get("task_intent"),
            task_parameters=_string_dict(args.get("task_parameters")),
            conversation_state=_string_dict(args.get("conversation_state")),
            client_request_id=args.get("client_request_id"),
            app_language=args.get("app_language"),
            hidden_context=args.get("hidden_context"),
        )
        if args.get("wait") and created.get("run_id"):
            return client.wait_for_agent_run(
                str(created["run_id"]),
                timeout=_float_or_none(args.get("timeout")),
                include_events=bool(args.get("include_events", False)),
            )
        return created
    if name == "agent_clarify":
        return client.continue_agent_clarification(
            str(args["run_id"]),
            clarification_id=args.get("clarification_id"),
            value=args.get("value"),
            answer=args.get("answer"),
            answers=_string_dict(args.get("answers")),
            client_request_id=args.get("client_request_id"),
            wait=bool(args.get("wait", False)),
            include_events=bool(args.get("include_events", False)),
            timeout=_float_or_none(args.get("timeout")),
        )
    if name == "agent_cancel":
        return client.cancel_agent_run(str(args["run_id"]))
    if name == "agent_events":
        return client.stream_agent_events(
            str(args["run_id"]),
            last_event_id=args.get("last_event_id"),
            timeout=_float_or_none(args.get("timeout")),
        )
    raise CliError("invalid_input", f"Unsupported tool: {name}")


def _path(value: str | None) -> Path | None:
    return Path(value) if value else None


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if item is not None}


def _path_dict(value: Any) -> dict[str, Path]:
    if not isinstance(value, dict):
        return {}
    return {str(key): Path(str(item)) for key, item in value.items() if item is not None}


def _replacement_references(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CliError(
            "invalid_input",
            "replacement_references must be a JSON array.",
        )
    references: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise CliError(
                "invalid_input",
                f"replacement_references[{index}] must be a JSON object.",
            )
        role = str(item.get("role") or "").strip().lower()
        path = str(item.get("path") or "").strip()
        if role not in {"person", "product", "scene"} or not path:
            raise CliError(
                "invalid_input",
                f"replacement_references[{index}] requires role person/product/scene and a path.",
            )
        references.append({"role": role, "path": path})
    return references


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _render_options(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    keys = (
        "font_size",
        "font_name",
        "font_color",
        "outline_color",
        "outline_width",
        "margin_v",
        "position",
        "watermark_text",
        "watermark_position",
        "watermark_font_size",
        "watermark_color",
        "watermark_opacity",
        "watermark_margin",
        "watermark_image_path",
        "watermark_image_position",
        "watermark_image_width",
        "watermark_image_opacity",
        "watermark_image_margin",
    )
    return render_options(
        settings,
        {key: args.get(key) for key in keys},
        use_brand_kit=not bool(args.get("no_brand_kit", False)),
    )


def _error_response(request_id: Any, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {"code": code}
    if details:
        data["details"] = details
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": message, "data": data}}


def _request_id_from_line(line: str) -> Any:
    try:
        payload = json.loads(line)
        return payload.get("id")
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
