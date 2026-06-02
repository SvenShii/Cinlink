from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from .client import RuntimeClient
from .config import load_settings
from .dependencies import local_dependency_report, require_local_voice_separation_if_requested
from .errors import CliError
from .local_tools import burn_subtitles
from .schemas import TOOL_SCHEMAS


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
                "serverInfo": {"name": "popularvideo-cli", "version": "0.1.0"},
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
    settings = load_settings(allow_missing_api_key=name == "doctor")
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
    if name == "burn":
        return burn_subtitles(Path(args["video_path"]), Path(args["subtitle_path"]), out=_path(args.get("out")), font_size=args.get("font_size"), position=args.get("position", "bottom"))
    if name == "summarize":
        return client.summarize(Path(args["input_path"]), out=_path(args.get("out")), max_highlights=int(args.get("max_highlights", 3)))
    if name == "shorten":
        return client.shorten(Path(args["video_path"]), out=_path(args.get("out")), max_clips=int(args.get("max_clips", 5)), target_duration=int(args.get("target_duration", 45)))
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
            first_frame_image_url=args.get("first_frame_image_url"),
            reference_image_urls=args.get("reference_image_urls") or [],
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
        )
        if args.get("wait") and created.get("run_id"):
            return client.wait_for_agent_run(str(created["run_id"]))
        return created
    raise CliError("invalid_input", f"Unsupported tool: {name}")


def _path(value: str | None) -> Path | None:
    return Path(value) if value else None


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
