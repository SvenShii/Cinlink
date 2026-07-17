from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from .client import RuntimeClient
from .config import Settings, load_settings, save_settings
from .dependencies import local_dependency_report, require_local_voice_separation_if_requested
from .errors import CliError
from .local_setup import setup_local_dependencies
from .local_tools import burn_subtitles, mix_dubbed_audio
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
            interactive=False,
        )
    settings = load_settings(allow_missing_api_key=name in {"doctor", "burn", "mix_dubbed_audio"})
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
        return add_subtitles(
            client,
            Path(args["video_path"]),
            subtitle_path=_path(args.get("subtitle_path")),
            source_lang=args.get("source_lang", "auto"),
            target_lang=args.get("target_lang"),
            bilingual=bool(args.get("bilingual", False)),
            out=_path(args.get("out")),
            timeout=args.get("timeout"),
            font_size=args.get("font_size"),
            font_name=args.get("font_name"),
            font_color=args.get("font_color"),
            outline_color=args.get("outline_color"),
            outline_width=args.get("outline_width"),
            margin_v=args.get("margin_v"),
            position=args.get("position", "bottom"),
            watermark_text=args.get("watermark_text"),
            watermark_position=args.get("watermark_position", "top-right"),
            watermark_font_size=args.get("watermark_font_size"),
            watermark_color=args.get("watermark_color"),
            watermark_opacity=float(args.get("watermark_opacity", 0.72)),
            watermark_margin=int(args.get("watermark_margin", 24)),
            watermark_image_path=_path(args.get("watermark_image_path")),
            watermark_image_position=args.get("watermark_image_position", "top-right"),
            watermark_image_width=args.get("watermark_image_width"),
            watermark_image_opacity=float(args.get("watermark_image_opacity", 0.72)),
            watermark_image_margin=int(args.get("watermark_image_margin", 24)),
        )
    if name == "dub":
        return client.dub(
            Path(args["video_path"]),
            Path(args["subtitle_path"]),
            reference_subtitle_path=_path(args.get("reference_subtitle_path")),
            voice=args.get("voice"),
            language=args.get("language", "zh"),
            out=_path(args.get("out")),
            timeout=args.get("timeout"),
        )
    if name == "burn":
        return burn_subtitles(
            Path(args["video_path"]),
            Path(args["subtitle_path"]),
            out=_path(args.get("out")),
            font_size=args.get("font_size"),
            font_name=args.get("font_name"),
            font_color=args.get("font_color"),
            outline_color=args.get("outline_color"),
            outline_width=args.get("outline_width"),
            margin_v=args.get("margin_v"),
            position=args.get("position", "bottom"),
            watermark_text=args.get("watermark_text"),
            watermark_position=args.get("watermark_position", "top-right"),
            watermark_font_size=args.get("watermark_font_size"),
            watermark_color=args.get("watermark_color"),
            watermark_opacity=float(args.get("watermark_opacity", 0.72)),
            watermark_margin=int(args.get("watermark_margin", 24)),
            watermark_image_path=_path(args.get("watermark_image_path")),
            watermark_image_position=args.get("watermark_image_position", "top-right"),
            watermark_image_width=args.get("watermark_image_width"),
            watermark_image_opacity=float(args.get("watermark_image_opacity", 0.72)),
            watermark_image_margin=int(args.get("watermark_image_margin", 24)),
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
        )
    if name == "image":
        return client.image(args["prompt"], out=_path(args.get("out")), aspect_ratio=args.get("aspect_ratio", "1:1"), image_size=args.get("image_size", "1K"), model=args.get("model"))
    if name == "video":
        return client.video(
            args["prompt"],
            out=_path(args.get("out")),
            aspect_ratio=args.get("aspect_ratio", "16:9"),
            resolution=args.get("resolution", "720P"),
            duration=int(args.get("duration", 5)),
            generate_audio=bool(args.get("generate_audio", True)),
            watermark=bool(args.get("watermark", False)),
            generation_mode=args.get("generation_mode", "text"),
            first_frame_image_url=args.get("first_frame_image_url"),
            reference_image_urls=args.get("reference_image_urls") or [],
            reference_video_urls=args.get("reference_video_urls") or [],
            reference_audio_urls=args.get("reference_audio_urls") or [],
            model=args.get("model"),
            model_name=args.get("model_name"),
            model_version=args.get("model_version"),
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
        created = client.create_agent_run(
            args["prompt"],
            conversation_id=args.get("conversation_id"),
            context_files=[Path(item) for item in args.get("context_file", [])],
            mode=args.get("mode", "execute"),
            task_intent=args.get("task_intent"),
            task_parameters=_string_dict(args.get("task_parameters")),
            conversation_state=_string_dict(args.get("conversation_state")),
        )
        if args.get("wait") and created.get("run_id"):
            return client.wait_for_agent_run(str(created["run_id"]), timeout=_float_or_none(args.get("timeout")))
        return created
    raise CliError("invalid_input", f"Unsupported tool: {name}")


def _path(value: str | None) -> Path | None:
    return Path(value) if value else None


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if item is not None}


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


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
