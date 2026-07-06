from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .client import RuntimeClient
from .config import Settings, load_settings, save_settings
from .dependencies import local_dependency_report, require_local_voice_separation_if_requested
from .errors import CliError
from .local_tools import burn_subtitles, mix_dubbed_audio
from .schemas import TOOL_SCHEMAS, list_tools
from .workflows import add_subtitles


def emit(payload: Any, json_output: bool = True) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}: {value}")
    else:
        print(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cinlink")
    parser.add_argument("--json", action="store_true", default=False, help="Emit JSON. Agent commands should always use this.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    onboarding = subparsers.add_parser("onboarding")
    onboarding.add_argument("--api-key")
    onboarding.add_argument("--runtime-base", default=None)
    onboarding.add_argument("--billing-base", default=None)

    doctor = subparsers.add_parser("doctor")

    tools = subparsers.add_parser("tools")
    tool_subparsers = tools.add_subparsers(dest="tools_command", required=True)
    tool_subparsers.add_parser("list")
    schema = tool_subparsers.add_parser("schema")
    schema.add_argument("name", nargs="?")

    transcribe = subparsers.add_parser("transcribe")
    transcribe.add_argument("input_path")
    transcribe.add_argument("--lang", default="auto")
    transcribe.add_argument("--out")
    transcribe.add_argument("--timeout", type=float)

    translate = subparsers.add_parser("translate")
    translate.add_argument("input_path")
    translate.add_argument("--from", dest="from_lang", default="auto")
    translate.add_argument("--to", dest="to_lang", default="zh")
    translate.add_argument("--bilingual", action="store_true")
    translate.add_argument("--delivery", choices=["subtitle", "voice"], default="subtitle")
    translate.add_argument("--out")
    translate.add_argument("--timeout", type=float)

    add_subtitles_parser = subparsers.add_parser("add-subtitles")
    add_subtitles_parser.add_argument("video_path")
    add_subtitles_parser.add_argument("--subtitle", dest="subtitle_path")
    add_subtitles_parser.add_argument("--source-lang", default="auto")
    add_subtitles_parser.add_argument("--target-lang")
    add_subtitles_parser.add_argument("--bilingual", action="store_true")
    add_subtitles_parser.add_argument("--out")
    add_subtitles_parser.add_argument("--timeout", type=float)
    add_subtitles_parser.add_argument("--font-size", type=int)
    add_subtitles_parser.add_argument("--font-name")
    add_subtitles_parser.add_argument("--font-color")
    add_subtitles_parser.add_argument("--outline-color")
    add_subtitles_parser.add_argument("--outline-width", type=float)
    add_subtitles_parser.add_argument("--margin-v", type=int)
    add_subtitles_parser.add_argument("--position", choices=["top", "bottom"], default="bottom")
    add_subtitles_parser.add_argument("--watermark-text")
    add_subtitles_parser.add_argument(
        "--watermark-position",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
        default="top-right",
    )
    add_subtitles_parser.add_argument("--watermark-font-size", type=int)
    add_subtitles_parser.add_argument("--watermark-color")
    add_subtitles_parser.add_argument("--watermark-opacity", type=float, default=0.72)
    add_subtitles_parser.add_argument("--watermark-margin", type=int, default=24)
    add_subtitles_parser.add_argument("--watermark-image", dest="watermark_image_path")
    add_subtitles_parser.add_argument(
        "--watermark-image-position",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
        default="top-right",
    )
    add_subtitles_parser.add_argument("--watermark-image-width", type=int)
    add_subtitles_parser.add_argument("--watermark-image-opacity", type=float, default=0.72)
    add_subtitles_parser.add_argument("--watermark-image-margin", type=int, default=24)

    dub = subparsers.add_parser("dub")
    dub.add_argument("video_path")
    dub.add_argument("--subtitle", required=True, dest="subtitle_path")
    dub.add_argument("--reference-subtitle", dest="reference_subtitle_path")
    dub.add_argument("--voice")
    dub.add_argument("--lang", default="zh")
    dub.add_argument("--out")
    dub.add_argument("--timeout", type=float)

    burn = subparsers.add_parser("burn")
    burn.add_argument("video_path")
    burn.add_argument("--subtitle", required=True, dest="subtitle_path")
    burn.add_argument("--out")
    burn.add_argument("--font-size", type=int)
    burn.add_argument("--font-name")
    burn.add_argument("--font-color")
    burn.add_argument("--outline-color")
    burn.add_argument("--outline-width", type=float)
    burn.add_argument("--margin-v", type=int)
    burn.add_argument("--position", choices=["top", "bottom"], default="bottom")
    burn.add_argument("--watermark-text")
    burn.add_argument(
        "--watermark-position",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
        default="top-right",
    )
    burn.add_argument("--watermark-font-size", type=int)
    burn.add_argument("--watermark-color")
    burn.add_argument("--watermark-opacity", type=float, default=0.72)
    burn.add_argument("--watermark-margin", type=int, default=24)
    burn.add_argument("--watermark-image", dest="watermark_image_path")
    burn.add_argument(
        "--watermark-image-position",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
        default="top-right",
    )
    burn.add_argument("--watermark-image-width", type=int)
    burn.add_argument("--watermark-image-opacity", type=float, default=0.72)
    burn.add_argument("--watermark-image-margin", type=int, default=24)

    mix_dubbed = subparsers.add_parser("mix-dubbed-audio")
    mix_dubbed.add_argument("video_path")
    mix_dubbed.add_argument("--dubbed-audio", required=True, dest="dubbed_audio_path")
    mix_dubbed.add_argument("--out")
    mix_dubbed.add_argument("--original-volume", type=float, default=0.65)
    mix_dubbed.add_argument("--dubbed-volume", type=float, default=1.0)

    summarize = subparsers.add_parser("summarize")
    summarize.add_argument("input_path")
    summarize.add_argument("--out")
    summarize.add_argument("--max-highlights", type=int, default=3)

    shorten = subparsers.add_parser("shorten")
    shorten.add_argument("video_path")
    shorten.add_argument("--out")
    shorten.add_argument("--max-clips", type=int, default=5)
    shorten.add_argument("--target-duration", type=int, default=45)
    shorten.add_argument("--style-preset")
    shorten.add_argument("--music-mode", default="none")
    shorten.add_argument("--music-prompt")

    image = subparsers.add_parser("image")
    image.add_argument("prompt")
    image.add_argument("--out")
    image.add_argument("--aspect-ratio", default="1:1")
    image.add_argument("--image-size", default="1K")
    image.add_argument("--model")

    video = subparsers.add_parser("video")
    video.add_argument("prompt")
    video.add_argument("--out")
    video.add_argument("--aspect-ratio", default="16:9")
    video.add_argument("--resolution", default="720P")
    video.add_argument("--duration", type=int, default=5)
    video.add_argument("--no-audio", action="store_false", dest="generate_audio")
    video.add_argument("--watermark", action="store_true")
    video.add_argument("--generation-mode", choices=["text", "first_frame", "reference"], default="text")
    video.add_argument("--first-frame-image-url")
    video.add_argument("--reference-image-url", action="append", default=[], dest="reference_image_urls")
    video.add_argument("--reference-video-url", action="append", default=[], dest="reference_video_urls")
    video.add_argument("--reference-audio-url", action="append", default=[], dest="reference_audio_urls")
    video.add_argument("--model")
    video.add_argument("--model-name")
    video.add_argument("--model-version")
    video.add_argument("--timeout", type=float)

    nlu = subparsers.add_parser("nlu")
    nlu.add_argument("prompt")
    nlu.add_argument("--has-video", action="store_true")
    nlu.add_argument("--has-subtitle", action="store_true")
    nlu.add_argument("--pending-target-language")
    nlu.add_argument("--context-file", action="append", default=[])

    agent = subparsers.add_parser("agent")
    agent_subparsers = agent.add_subparsers(dest="agent_command", required=True)
    run = agent_subparsers.add_parser("run")
    run.add_argument("prompt")
    run.add_argument("--conversation-id")
    run.add_argument("--context-file", action="append", default=[])
    run.add_argument("--mode", choices=["plan", "execute"], default="execute")
    run.add_argument("--wait", action="store_true")
    run.add_argument("--timeout", type=float)
    poll = agent_subparsers.add_parser("poll")
    poll.add_argument("run_id")
    local_tools = agent_subparsers.add_parser("local-tools")
    local_tools.add_argument("run_id")
    local_tools.add_argument("--device-id")
    report = agent_subparsers.add_parser("report-tool-result")
    report.add_argument("run_id")
    report.add_argument("--tool-call-id", required=True)
    report.add_argument("--status", choices=["done", "failed"], required=True)
    report.add_argument("--artifact-path", action="append", default=[])
    report.add_argument("--metadata-json", default="{}")
    report.add_argument("--error-code")
    report.add_argument("--error-message")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    json_flag = "--json" in raw_argv
    raw_argv = [item for item in raw_argv if item != "--json"]
    args = parser.parse_args(raw_argv)
    json_output = bool(json_flag or args.json or args.command in {"tools", "agent"})
    try:
        payload = run_command(args)
        emit(payload, json_output=json_output)
        return 0
    except CliError as exc:
        emit(exc.to_payload(), json_output=True)
        return exc.exit_code
    except Exception as exc:
        emit({"error": {"code": "internal_error", "message": str(exc)}}, json_output=True)
        return 1


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "onboarding":
        existing = load_settings(allow_missing_api_key=True)
        settings = Settings(
            api_key=args.api_key or existing.api_key,
            runtime_base=args.runtime_base or existing.runtime_base,
            billing_base=args.billing_base or existing.billing_base,
            timeout_sec=existing.timeout_sec,
            poll_interval_sec=existing.poll_interval_sec,
        )
        if not settings.api_key:
            raise CliError("invalid_input", "Pass --api-key or set CINLINK_API_KEY.")
        path = save_settings(settings)
        return {"status": "done", "config_path": str(path), "runtime_base": settings.runtime_base, "billing_base": settings.billing_base}

    if args.command == "doctor":
        settings = load_settings(allow_missing_api_key=True)
        payload: dict[str, Any] = {
            "status": "done",
            "config": {
                "has_api_key": bool(settings.api_key),
                "runtime_base": settings.runtime_base,
                "billing_base": settings.billing_base,
            },
            "local_dependencies": local_dependency_report(),
        }
        try:
            payload["runtime_health"] = RuntimeClient(settings).health()
        except CliError as exc:
            payload["runtime_health"] = exc.to_payload()["error"]
        return payload

    if args.command == "tools":
        if args.tools_command == "list":
            return {"tools": list_tools()}
        if args.tools_command == "schema":
            if args.name:
                if args.name not in TOOL_SCHEMAS:
                    raise CliError("invalid_input", f"Unknown tool: {args.name}")
                return {"name": args.name, **TOOL_SCHEMAS[args.name]}
            return {"tools": TOOL_SCHEMAS}

    if args.command == "agent" and args.agent_command == "run":
        require_local_voice_separation_if_requested(args.prompt)

    settings = load_settings(allow_missing_api_key=args.command in {"burn", "mix-dubbed-audio"})
    client = RuntimeClient(settings)

    if args.command == "transcribe":
        return client.transcribe(Path(args.input_path), lang=args.lang, out=_path_or_none(args.out), timeout=args.timeout)
    if args.command == "translate":
        return client.translate(Path(args.input_path), from_lang=args.from_lang, to_lang=args.to_lang, bilingual=args.bilingual, delivery=args.delivery, out=_path_or_none(args.out), timeout=args.timeout)
    if args.command == "add-subtitles":
        return add_subtitles(
            client,
            Path(args.video_path),
            subtitle_path=_path_or_none(args.subtitle_path),
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            bilingual=args.bilingual,
            out=_path_or_none(args.out),
            timeout=args.timeout,
            font_size=args.font_size,
            font_name=args.font_name,
            font_color=args.font_color,
            outline_color=args.outline_color,
            outline_width=args.outline_width,
            margin_v=args.margin_v,
            position=args.position,
            watermark_text=args.watermark_text,
            watermark_position=args.watermark_position,
            watermark_font_size=args.watermark_font_size,
            watermark_color=args.watermark_color,
            watermark_opacity=args.watermark_opacity,
            watermark_margin=args.watermark_margin,
            watermark_image_path=_path_or_none(args.watermark_image_path),
            watermark_image_position=args.watermark_image_position,
            watermark_image_width=args.watermark_image_width,
            watermark_image_opacity=args.watermark_image_opacity,
            watermark_image_margin=args.watermark_image_margin,
        )
    if args.command == "dub":
        return client.dub(
            Path(args.video_path),
            Path(args.subtitle_path),
            reference_subtitle_path=_path_or_none(args.reference_subtitle_path),
            voice=args.voice,
            language=args.lang,
            out=_path_or_none(args.out),
            timeout=args.timeout,
        )
    if args.command == "burn":
        return burn_subtitles(
            Path(args.video_path),
            Path(args.subtitle_path),
            out=_path_or_none(args.out),
            font_size=args.font_size,
            font_name=args.font_name,
            font_color=args.font_color,
            outline_color=args.outline_color,
            outline_width=args.outline_width,
            margin_v=args.margin_v,
            position=args.position,
            watermark_text=args.watermark_text,
            watermark_position=args.watermark_position,
            watermark_font_size=args.watermark_font_size,
            watermark_color=args.watermark_color,
            watermark_opacity=args.watermark_opacity,
            watermark_margin=args.watermark_margin,
            watermark_image_path=_path_or_none(args.watermark_image_path),
            watermark_image_position=args.watermark_image_position,
            watermark_image_width=args.watermark_image_width,
            watermark_image_opacity=args.watermark_image_opacity,
            watermark_image_margin=args.watermark_image_margin,
        )
    if args.command == "mix-dubbed-audio":
        return mix_dubbed_audio(
            Path(args.video_path),
            Path(args.dubbed_audio_path),
            out=_path_or_none(args.out),
            original_volume=args.original_volume,
            dubbed_volume=args.dubbed_volume,
        )
    if args.command == "summarize":
        return client.summarize(Path(args.input_path), out=_path_or_none(args.out), max_highlights=args.max_highlights)
    if args.command == "shorten":
        return client.shorten(
            Path(args.video_path),
            out=_path_or_none(args.out),
            max_clips=args.max_clips,
            target_duration=args.target_duration,
            style_preset=args.style_preset,
            music_mode=args.music_mode,
            music_prompt=args.music_prompt,
        )
    if args.command == "image":
        return client.image(args.prompt, out=_path_or_none(args.out), aspect_ratio=args.aspect_ratio, image_size=args.image_size, model=args.model)
    if args.command == "video":
        return client.video(
            args.prompt,
            out=_path_or_none(args.out),
            aspect_ratio=args.aspect_ratio,
            resolution=args.resolution,
            duration=args.duration,
            generate_audio=args.generate_audio,
            watermark=args.watermark,
            generation_mode=args.generation_mode,
            first_frame_image_url=args.first_frame_image_url,
            reference_image_urls=args.reference_image_urls,
            reference_video_urls=args.reference_video_urls,
            reference_audio_urls=args.reference_audio_urls,
            model=args.model,
            model_name=args.model_name,
            model_version=args.model_version,
            timeout=args.timeout,
        )
    if args.command == "nlu":
        return client.nlu(args.prompt, has_video=args.has_video, has_subtitle=args.has_subtitle, pending_target_language=args.pending_target_language, context_files=args.context_file)
    if args.command == "agent":
        return run_agent_command(args, client)
    raise CliError("invalid_input", f"Unsupported command: {args.command}")


def run_agent_command(args: argparse.Namespace, client: RuntimeClient) -> dict[str, Any]:
    if args.agent_command == "run":
        created = client.create_agent_run(
            args.prompt,
            conversation_id=args.conversation_id,
            context_files=[Path(item) for item in args.context_file],
            mode=args.mode,
        )
        if args.wait and created.get("run_id"):
            return client.wait_for_agent_run(str(created["run_id"]), timeout=args.timeout)
        return created
    if args.agent_command == "poll":
        return client.get_agent_run(args.run_id)
    if args.agent_command == "local-tools":
        return client.list_local_tool_calls(args.run_id, device_id=args.device_id)
    if args.agent_command == "report-tool-result":
        metadata = _parse_json_object(args.metadata_json)
        artifacts = [
            {"id": None, "name": Path(item).name, "kind": "file", "path": str(Path(item).expanduser().resolve()), "metadata": {}}
            for item in args.artifact_path
        ]
        result = {
            "tool_call_id": args.tool_call_id,
            "status": args.status,
            "output_metadata": metadata,
            "artifacts": artifacts,
            "logs": [],
            "error": {"code": args.error_code or "processing_failed", "message": args.error_message or "Local tool failed."} if args.status == "failed" else None,
        }
        return client.report_local_tool_result(args.run_id, result)
    raise CliError("invalid_input", f"Unsupported agent command: {args.agent_command}")


def _path_or_none(value: str | None) -> Path | None:
    return Path(value) if value else None


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError("invalid_input", "--metadata-json must be a JSON object.") from exc
    if not isinstance(payload, dict):
        raise CliError("invalid_input", "--metadata-json must be a JSON object.")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
