from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .client import RuntimeClient, artifact_ref_from_path
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

    setup_deps = subparsers.add_parser("setup-local-deps", aliases=["install-local-deps"])
    setup_deps.add_argument("--yes", action="store_true", help="Install recommended local dependencies without prompting.")
    setup_deps.add_argument("--dry-run", action="store_true", help="Show what would be installed without running package-manager commands.")
    setup_deps.add_argument("--skip-ffmpeg", action="store_true")
    setup_deps.add_argument("--with-voice-separation", action="store_true", help="Also install optional Demucs/soundfile voice-separation dependencies.")
    setup_deps.add_argument("--skip-voice-separation", action="store_true")
    setup_deps.add_argument("--with-enhancement", action="store_true", help="Also configure the optional local waifu2x image/video enhancement component.")
    setup_deps.add_argument("--skip-enhancement", action="store_true")

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
    add_subtitles_parser.add_argument("--position", choices=["top", "bottom"])
    add_subtitles_parser.add_argument("--no-brand-kit", action="store_true")
    add_subtitles_parser.add_argument("--watermark-text")
    add_subtitles_parser.add_argument(
        "--watermark-position",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
    )
    add_subtitles_parser.add_argument("--watermark-font-size", type=int)
    add_subtitles_parser.add_argument("--watermark-color")
    add_subtitles_parser.add_argument("--watermark-opacity", type=float)
    add_subtitles_parser.add_argument("--watermark-margin", type=int)
    add_subtitles_parser.add_argument("--watermark-image", dest="watermark_image_path")
    add_subtitles_parser.add_argument(
        "--watermark-image-position",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
    )
    add_subtitles_parser.add_argument("--watermark-image-width", type=int)
    add_subtitles_parser.add_argument("--watermark-image-opacity", type=float)
    add_subtitles_parser.add_argument("--watermark-image-margin", type=int)

    dub = subparsers.add_parser("dub")
    dub.add_argument("video_path")
    dub.add_argument("--subtitle", required=True, dest="subtitle_path")
    dub.add_argument("--reference-subtitle", dest="reference_subtitle_path")
    dub.add_argument("--reference-audio", action="append", default=[], metavar="SPEAKER_ID=PATH")
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
    burn.add_argument("--position", choices=["top", "bottom"])
    burn.add_argument("--no-brand-kit", action="store_true")
    burn.add_argument("--watermark-text")
    burn.add_argument(
        "--watermark-position",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
    )
    burn.add_argument("--watermark-font-size", type=int)
    burn.add_argument("--watermark-color")
    burn.add_argument("--watermark-opacity", type=float)
    burn.add_argument("--watermark-margin", type=int)
    burn.add_argument("--watermark-image", dest="watermark_image_path")
    burn.add_argument(
        "--watermark-image-position",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
    )
    burn.add_argument("--watermark-image-width", type=int)
    burn.add_argument("--watermark-image-opacity", type=float)
    burn.add_argument("--watermark-image-margin", type=int)

    watermark = subparsers.add_parser("apply-watermark")
    watermark.add_argument("video_path")
    watermark.add_argument("--out")
    watermark.add_argument("--no-brand-kit", action="store_true")
    watermark.add_argument("--watermark-text")
    watermark.add_argument(
        "--watermark-position",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
    )
    watermark.add_argument("--watermark-font-size", type=int)
    watermark.add_argument("--watermark-color")
    watermark.add_argument("--watermark-opacity", type=float)
    watermark.add_argument("--watermark-margin", type=int)
    watermark.add_argument("--watermark-image", dest="watermark_image_path")
    watermark.add_argument(
        "--watermark-image-position",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
    )
    watermark.add_argument("--watermark-image-width", type=int)
    watermark.add_argument("--watermark-image-opacity", type=float)
    watermark.add_argument("--watermark-image-margin", type=int)

    enhance_image_parser = subparsers.add_parser("enhance-image")
    enhance_image_parser.add_argument("image_path")
    enhance_image_parser.add_argument("--out")
    enhance_image_parser.add_argument("--scale", type=int, choices=[2], default=2)
    enhance_image_parser.add_argument("--noise-level", type=int, choices=[-1, 0, 1, 2, 3], default=1)
    enhance_image_parser.add_argument("--model", choices=["photo", "cunet", "anime"], default="photo")

    enhance_video_parser = subparsers.add_parser("enhance-video")
    enhance_video_parser.add_argument("video_path")
    enhance_video_parser.add_argument("--out")
    enhance_video_parser.add_argument("--scale", type=int, choices=[2], default=2)
    enhance_video_parser.add_argument("--noise-level", type=int, choices=[-1, 0, 1, 2, 3], default=1)
    enhance_video_parser.add_argument("--model", choices=["photo", "cunet", "anime"], default="photo")

    trim = subparsers.add_parser("trim-video")
    trim.add_argument("video_path")
    trim.add_argument("--start", required=True, type=float, dest="start_sec")
    trim.add_argument("--end", required=True, type=float, dest="end_sec")
    trim.add_argument("--out")

    montage = subparsers.add_parser("montage")
    montage.add_argument("--clips-json", required=True, help="JSON array of {path,start_sec,end_sec} clip objects.")
    montage.add_argument("--out")

    clean = subparsers.add_parser("clean-cut")
    clean.add_argument("video_path")
    clean.add_argument("--out")
    clean.add_argument("--minimum-silence", type=float, default=0.75, dest="minimum_silence_sec")
    clean.add_argument("--noise-threshold-db", type=float, default=-35.0)
    clean.add_argument("--retained-pause", type=float, default=0.24, dest="retained_pause_sec")
    clean.add_argument("--minimum-removal", type=float, default=0.18, dest="minimum_removal_sec")

    brand_kit = subparsers.add_parser("brand-kit")
    brand_kit_subparsers = brand_kit.add_subparsers(dest="brand_kit_command", required=True)
    brand_kit_subparsers.add_parser("show")
    brand_kit_subparsers.add_parser("clear")
    brand_set = brand_kit_subparsers.add_parser("set")
    brand_enabled = brand_set.add_mutually_exclusive_group()
    brand_enabled.add_argument("--enable", action="store_true")
    brand_enabled.add_argument("--disable", action="store_true")
    brand_set.add_argument("--font-size", type=int)
    brand_set.add_argument("--font-name")
    brand_set.add_argument("--font-color")
    brand_set.add_argument("--outline-color")
    brand_set.add_argument("--outline-width", type=float)
    brand_set.add_argument("--margin-v", type=int)
    brand_set.add_argument("--position", choices=["top", "bottom"])
    brand_set.add_argument("--watermark-text")
    brand_set.add_argument("--watermark-position", choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"])
    brand_set.add_argument("--watermark-font-size", type=int)
    brand_set.add_argument("--watermark-color")
    brand_set.add_argument("--watermark-opacity", type=float)
    brand_set.add_argument("--watermark-margin", type=int)
    brand_set.add_argument("--watermark-image", dest="watermark_image_path")
    brand_set.add_argument("--clear-watermark-image", action="store_true")
    brand_set.add_argument("--watermark-image-position", choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"])
    brand_set.add_argument("--watermark-image-width", type=int)
    brand_set.add_argument("--watermark-image-opacity", type=float)
    brand_set.add_argument("--watermark-image-margin", type=int)

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
    image.add_argument(
        "--reference-image-url",
        action="append",
        default=[],
        dest="reference_image_urls",
    )
    image.add_argument("--model")
    image.add_argument("--timeout", type=float)

    video = subparsers.add_parser("video")
    video.add_argument("prompt")
    video.add_argument("--out")
    video.add_argument("--aspect-ratio", default="16:9")
    video.add_argument("--resolution", default="720P")
    video.add_argument("--duration", type=int, default=5)
    video.add_argument("--no-audio", action="store_false", dest="generate_audio")
    video.add_argument("--watermark", action="store_true")
    video.add_argument("--generation-mode", choices=["text", "first_frame", "reference"])
    video.add_argument("--first-frame-image-url")
    video.add_argument("--reference-image-url", action="append", default=[], dest="reference_image_urls")
    video.add_argument("--reference-video-url", action="append", default=[], dest="reference_video_urls")
    video.add_argument("--reference-audio-url", action="append", default=[], dest="reference_audio_urls")
    video.add_argument("--model")
    video.add_argument("--model-name")
    video.add_argument("--model-version")
    video.add_argument("--timeout", type=float)

    deconstruct = subparsers.add_parser("deconstruct-video")
    deconstruct.add_argument("video_path")
    deconstruct.add_argument("--out")
    deconstruct.add_argument(
        "--replacement-reference",
        action="append",
        default=[],
        metavar="ROLE=PATH",
        help="Optional person, product, or scene replacement reference.",
    )
    deconstruct.add_argument("--scene-threshold", type=float, default=0.28)
    deconstruct.add_argument("--max-shots", type=int, default=120)
    deconstruct.add_argument("--language", default="zh-Hans")
    deconstruct.add_argument("--analysis-scope", default="")

    regenerate = subparsers.add_parser("regenerate-deconstruction")
    regenerate.add_argument("plan_path")
    regenerate.add_argument("--out")
    regenerate.add_argument(
        "--replacement-reference",
        action="append",
        default=[],
        metavar="ROLE=PATH",
        help="Optional person, product, or scene replacement reference.",
    )
    regenerate.add_argument("--resolution", default="720P")
    regenerate.add_argument(
        "--no-original-audio",
        action="store_false",
        dest="preserve_original_audio",
    )
    regenerate.add_argument("--model")
    regenerate.add_argument("--model-name")
    regenerate.add_argument("--model-version")
    regenerate.add_argument("--timeout", type=float)

    export_video_parser = subparsers.add_parser("export-video")
    export_video_parser.add_argument("video_path")
    export_video_parser.add_argument(
        "--format",
        choices=["mp4", "mov", "avi", "mkv"],
        default="mp4",
        dest="output_format",
    )
    export_video_parser.add_argument("--out")

    export_audio_parser = subparsers.add_parser("export-audio")
    export_audio_parser.add_argument("video_path")
    export_audio_parser.add_argument(
        "--format",
        choices=["wav", "mp3"],
        default="wav",
        dest="output_format",
    )
    export_audio_parser.add_argument("--audio-source", dest="audio_path")
    export_audio_parser.add_argument("--out")

    export_project = subparsers.add_parser("export-editor-project")
    export_project.add_argument("video_path")
    export_project.add_argument(
        "--target",
        choices=["capcut", "premiere", "final-cut", "resolve"],
        required=True,
    )
    export_project.add_argument("--subtitle", dest="subtitle_path")
    export_project.add_argument("--audio-source", dest="audio_path")
    export_project.add_argument("--out")

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
    run.add_argument("--context-json", action="append", default=[], help="JSON context descriptor or array with public_url/cloud_file_id/metadata.")
    run.add_argument("--client-request-id")
    run.add_argument("--app-language")
    run.add_argument("--hidden-context")
    run.add_argument("--hidden-context-file")
    run.add_argument("--mode", choices=["plan", "execute"], default="execute")
    run.add_argument("--task-intent")
    run.add_argument("--task-param", action="append", default=[], metavar="KEY=VALUE")
    run.add_argument("--task-parameters-json", default="{}")
    run.add_argument("--conversation-state-json", default="{}")
    run.add_argument("--wait", action="store_true")
    run.add_argument(
        "--include-events",
        action="store_true",
        help="Include public planning and reasoning events in the completed response.",
    )
    run.add_argument("--timeout", type=float)
    clarify = agent_subparsers.add_parser("clarify")
    clarify.add_argument("run_id")
    clarify.add_argument("--clarification-id")
    clarify.add_argument("--value")
    clarify.add_argument("--answer")
    clarify.add_argument(
        "--response",
        action="append",
        default=[],
        metavar="ID_OR_SLOT=VALUE",
        help="Answer every clarification in one continuation. Repeat for multiple questions.",
    )
    clarify.add_argument("--answers-json", default="{}")
    clarify.add_argument("--client-request-id")
    clarify.add_argument("--wait", action="store_true")
    clarify.add_argument(
        "--include-events",
        action="store_true",
        help="Include public planning and reasoning events in the completed response.",
    )
    clarify.add_argument("--timeout", type=float)
    poll = agent_subparsers.add_parser("poll")
    poll.add_argument("run_id")
    events = agent_subparsers.add_parser("events")
    events.add_argument("run_id")
    events.add_argument("--last-event-id")
    events.add_argument("--timeout", type=float)
    local_tools = agent_subparsers.add_parser("local-tools")
    local_tools.add_argument("run_id")
    local_tools.add_argument("--device-id")
    report = agent_subparsers.add_parser("report-tool-result")
    report.add_argument("run_id")
    report.add_argument("--tool-call-id", required=True)
    report.add_argument("--status", choices=["done", "failed"], required=True)
    report.add_argument("--artifact-path", action="append", default=[])
    report.add_argument("--artifact-json", action="append", default=[], help="JSON artifact object or array.")
    report.add_argument("--artifact-metadata-json", default="{}")
    report.add_argument(
        "--upload-for-cloud-model-input",
        action="store_true",
        help="Upload non-video artifacts to the account-scoped Agent file endpoint before reporting them.",
    )
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
    setattr(args, "_json_output", json_output)
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
            brand_kit=existing.brand_kit,
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

    if args.command in {"setup-local-deps", "install-local-deps"}:
        return setup_local_dependencies(
            assume_yes=args.yes,
            dry_run=args.dry_run,
            skip_ffmpeg=args.skip_ffmpeg,
            with_voice_separation=args.with_voice_separation,
            skip_voice_separation=args.skip_voice_separation,
            with_enhancement=args.with_enhancement,
            skip_enhancement=args.skip_enhancement,
            interactive=not bool(getattr(args, "_json_output", False)),
        )

    if args.command == "brand-kit":
        settings = load_settings(allow_missing_api_key=True)
        if args.brand_kit_command == "show":
            return {"status": "done", "brand_kit": brand_kit_payload(settings)}
        if args.brand_kit_command == "clear":
            brand_kit = update_brand_kit(settings, {"enabled": False}, clear=True)
            return {"status": "done", "brand_kit": brand_kit}
        changes = _brand_kit_changes(args)
        brand_kit = update_brand_kit(settings, changes)
        return {"status": "done", "brand_kit": brand_kit}

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

    local_only_commands = {
        "apply-watermark",
        "brand-kit",
        "burn",
        "clean-cut",
        "export-audio",
        "export-editor-project",
        "export-video",
        "enhance-image",
        "enhance-video",
        "mix-dubbed-audio",
        "montage",
        "trim-video",
    }
    settings = load_settings(allow_missing_api_key=args.command in local_only_commands)
    client = RuntimeClient(settings)

    if args.command == "transcribe":
        return client.transcribe(Path(args.input_path), lang=args.lang, out=_path_or_none(args.out), timeout=args.timeout)
    if args.command == "translate":
        return client.translate(Path(args.input_path), from_lang=args.from_lang, to_lang=args.to_lang, bilingual=args.bilingual, delivery=args.delivery, out=_path_or_none(args.out), timeout=args.timeout)
    if args.command == "add-subtitles":
        render = _render_options_from_args(args, settings)
        return add_subtitles(
            client,
            Path(args.video_path),
            subtitle_path=_path_or_none(args.subtitle_path),
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            bilingual=args.bilingual,
            out=_path_or_none(args.out),
            timeout=args.timeout,
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
            watermark_image_path=_path_or_none(render["watermark_image_path"]),
            watermark_image_position=render["watermark_image_position"],
            watermark_image_width=render["watermark_image_width"],
            watermark_image_opacity=render["watermark_image_opacity"],
            watermark_image_margin=render["watermark_image_margin"],
        )
    if args.command == "dub":
        return client.dub(
            Path(args.video_path),
            Path(args.subtitle_path),
            reference_subtitle_path=_path_or_none(args.reference_subtitle_path),
            reference_audio_paths=_parse_path_dict(args.reference_audio, "--reference-audio"),
            voice=args.voice,
            language=args.lang,
            out=_path_or_none(args.out),
            timeout=args.timeout,
        )
    if args.command == "burn":
        render = _render_options_from_args(args, settings)
        return burn_subtitles(
            Path(args.video_path),
            Path(args.subtitle_path),
            out=_path_or_none(args.out),
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
            watermark_image_path=_path_or_none(render["watermark_image_path"]),
            watermark_image_position=render["watermark_image_position"],
            watermark_image_width=render["watermark_image_width"],
            watermark_image_opacity=render["watermark_image_opacity"],
            watermark_image_margin=render["watermark_image_margin"],
        )
    if args.command == "apply-watermark":
        render = _render_options_from_args(args, settings)
        return apply_watermark(
            Path(args.video_path),
            out=_path_or_none(args.out),
            watermark_text=render["watermark_text"],
            watermark_position=render["watermark_position"],
            watermark_font_size=render["watermark_font_size"],
            watermark_color=render["watermark_color"],
            watermark_opacity=render["watermark_opacity"],
            watermark_margin=render["watermark_margin"],
            watermark_image_path=_path_or_none(render["watermark_image_path"]),
            watermark_image_position=render["watermark_image_position"],
            watermark_image_width=render["watermark_image_width"],
            watermark_image_opacity=render["watermark_image_opacity"],
            watermark_image_margin=render["watermark_image_margin"],
        )
    if args.command == "enhance-image":
        return enhance_image(
            Path(args.image_path),
            out=_path_or_none(args.out),
            scale=args.scale,
            noise_level=args.noise_level,
            model=args.model,
        )
    if args.command == "enhance-video":
        return enhance_video(
            Path(args.video_path),
            out=_path_or_none(args.out),
            scale=args.scale,
            noise_level=args.noise_level,
            model=args.model,
        )
    if args.command == "trim-video":
        return trim_video(
            Path(args.video_path),
            start_sec=args.start_sec,
            end_sec=args.end_sec,
            out=_path_or_none(args.out),
        )
    if args.command == "montage":
        return create_montage(_parse_json_array(args.clips_json, "--clips-json"), out=_path_or_none(args.out))
    if args.command == "clean-cut":
        return clean_cut(
            Path(args.video_path),
            out=_path_or_none(args.out),
            minimum_silence_sec=args.minimum_silence_sec,
            noise_threshold_db=args.noise_threshold_db,
            retained_pause_sec=args.retained_pause_sec,
            minimum_removal_sec=args.minimum_removal_sec,
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
        return client.image(
            args.prompt,
            out=_path_or_none(args.out),
            aspect_ratio=args.aspect_ratio,
            image_size=args.image_size,
            reference_image_urls=args.reference_image_urls,
            model=args.model,
            timeout=args.timeout,
        )
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
    if args.command == "deconstruct-video":
        return deconstruct_video(
            client,
            Path(args.video_path),
            out=_path_or_none(args.out),
            replacement_references=_parse_replacement_references(
                args.replacement_reference
            ),
            language=args.language,
            analysis_scope=args.analysis_scope,
            scene_threshold=args.scene_threshold,
            max_shots=args.max_shots,
        )
    if args.command == "regenerate-deconstruction":
        return regenerate_deconstruction(
            client,
            Path(args.plan_path),
            out=_path_or_none(args.out),
            replacement_references=_parse_replacement_references(
                args.replacement_reference
            ),
            resolution=args.resolution,
            preserve_original_audio=args.preserve_original_audio,
            model=args.model,
            model_name=args.model_name,
            model_version=args.model_version,
            timeout=args.timeout,
        )
    if args.command == "export-video":
        return export_video(
            Path(args.video_path),
            output_format=args.output_format,
            out=_path_or_none(args.out),
        )
    if args.command == "export-audio":
        return export_audio(
            Path(args.video_path),
            output_format=args.output_format,
            audio_path=_path_or_none(args.audio_path),
            out=_path_or_none(args.out),
        )
    if args.command == "export-editor-project":
        return export_editor_project(
            Path(args.video_path),
            target=args.target,
            subtitle_path=_path_or_none(args.subtitle_path),
            audio_path=_path_or_none(args.audio_path),
            out=_path_or_none(args.out),
        )
    if args.command == "nlu":
        return client.nlu(args.prompt, has_video=args.has_video, has_subtitle=args.has_subtitle, pending_target_language=args.pending_target_language, context_files=args.context_file)
    if args.command == "agent":
        return run_agent_command(args, client)
    raise CliError("invalid_input", f"Unsupported command: {args.command}")


def run_agent_command(args: argparse.Namespace, client: RuntimeClient) -> dict[str, Any]:
    if args.agent_command == "run":
        task_parameters = _parse_string_dict(args.task_parameters_json, "--task-parameters-json")
        task_parameters.update(_parse_key_value_pairs(args.task_param, "--task-param"))
        conversation_state = _parse_string_dict(args.conversation_state_json, "--conversation-state-json")
        hidden_context = _combined_hidden_context(args.hidden_context, args.hidden_context_file)
        context_descriptors = _parse_json_objects(args.context_json, "--context-json")
        created = client.create_agent_run(
            args.prompt,
            conversation_id=args.conversation_id,
            context_files=[Path(item) for item in args.context_file],
            context_descriptors=context_descriptors,
            mode=args.mode,
            task_intent=args.task_intent,
            task_parameters=task_parameters,
            conversation_state=conversation_state,
            client_request_id=args.client_request_id,
            app_language=args.app_language,
            hidden_context=hidden_context,
        )
        if args.wait and created.get("run_id"):
            return client.wait_for_agent_run(
                str(created["run_id"]),
                timeout=args.timeout,
                include_events=args.include_events,
            )
        return created
    if args.agent_command == "clarify":
        answers = _parse_string_dict(args.answers_json, "--answers-json")
        answers.update(_parse_key_value_pairs(args.response, "--response"))
        return client.continue_agent_clarification(
            args.run_id,
            clarification_id=args.clarification_id,
            value=args.value,
            answer=args.answer,
            answers=answers,
            client_request_id=args.client_request_id,
            wait=args.wait,
            include_events=args.include_events,
            timeout=args.timeout,
        )
    if args.agent_command == "poll":
        return client.get_agent_run(args.run_id)
    if args.agent_command == "events":
        return client.stream_agent_events(
            args.run_id,
            last_event_id=args.last_event_id,
            timeout=args.timeout,
        )
    if args.agent_command == "local-tools":
        return client.list_local_tool_calls(args.run_id, device_id=args.device_id)
    if args.agent_command == "report-tool-result":
        metadata = _parse_json_object(args.metadata_json)
        artifact_metadata = _parse_json_object(args.artifact_metadata_json)
        for key in ("artifact_role", "producer_run_id", "producer_step", "source_language", "target_language"):
            if key in metadata and key not in artifact_metadata:
                artifact_metadata[key] = metadata[key]
        artifacts = [
            (
                client.upload_agent_artifact(Path(item), metadata=artifact_metadata)
                if args.upload_for_cloud_model_input
                else artifact_ref_from_path(Path(item), metadata=artifact_metadata)
            )
            for item in args.artifact_path
        ]
        artifacts.extend(_parse_report_artifacts(args.artifact_json, artifact_metadata))
        if args.upload_for_cloud_model_input:
            artifacts = [
                _upload_report_artifact(client, artifact)
                if not str((artifact.get("metadata") or {}).get("cloud_accessible") or "").lower() == "true"
                else artifact
                for artifact in artifacts
            ]
            metadata.update({"cloud_accessible": "true", "agent_server_input": "true"})
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


def _upload_report_artifact(
    client: RuntimeClient,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    path = artifact.get("path") or artifact.get("local_path")
    if not path:
        raise CliError(
            "invalid_input",
            "--upload-for-cloud-model-input requires a local path for every non-uploaded artifact.",
        )
    metadata = artifact.get("metadata")
    return client.upload_agent_artifact(
        Path(str(path)),
        kind=str(artifact.get("kind") or "").strip() or None,
        metadata=metadata if isinstance(metadata, dict) else None,
    )


def _path_or_none(value: str | None) -> Path | None:
    return Path(value) if value else None


def _parse_replacement_references(values: list[str]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for value in values:
        if "=" not in value:
            raise CliError(
                "invalid_input",
                "--replacement-reference must use ROLE=PATH.",
            )
        role, path = value.split("=", 1)
        normalized_role = role.strip().lower()
        normalized_path = path.strip()
        if normalized_role not in {"person", "product", "scene"}:
            raise CliError(
                "invalid_input",
                "Replacement reference role must be person, product, or scene.",
            )
        if not normalized_path:
            raise CliError(
                "invalid_input",
                "Replacement reference path cannot be empty.",
            )
        references.append({"role": normalized_role, "path": normalized_path})
    return references


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError("invalid_input", "--metadata-json must be a JSON object.") from exc
    if not isinstance(payload, dict):
        raise CliError("invalid_input", "--metadata-json must be a JSON object.")
    return payload


def _parse_json_array(text: str, flag: str) -> list[Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError("invalid_input", f"{flag} must be a JSON array.") from exc
    if not isinstance(payload, list):
        raise CliError("invalid_input", f"{flag} must be a JSON array.")
    return payload


def _parse_json_objects(values: list[str], flag: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for text in values:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CliError("invalid_input", f"{flag} must contain a JSON object or array.") from exc
        items = payload if isinstance(payload, list) else [payload]
        if not all(isinstance(item, dict) for item in items):
            raise CliError("invalid_input", f"{flag} must contain only JSON objects.")
        objects.extend(items)
    return objects


def _parse_report_artifacts(values: list[str], shared_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for item in _parse_json_objects(values, "--artifact-json"):
        raw_path = item.get("path") or item.get("local_path")
        item_metadata = item.get("metadata")
        if item_metadata is not None and not isinstance(item_metadata, dict):
            raise CliError("invalid_input", "--artifact-json metadata must be a JSON object.")
        metadata = {**shared_metadata, **(item_metadata or {})}
        if raw_path:
            artifact = artifact_ref_from_path(
                Path(str(raw_path)),
                kind=str(item["kind"]) if item.get("kind") else None,
                metadata=metadata,
            )
        else:
            name = str(item.get("name") or "")
            if not name:
                raise CliError("invalid_input", "--artifact-json requires path or name.")
            artifact = {
                "id": item.get("id"),
                "name": name,
                "kind": str(item.get("kind") or "other"),
                "metadata": {str(key): str(value) for key, value in metadata.items() if value is not None},
            }
        for key in ("id", "url", "cloud_file_id"):
            if item.get(key) is not None:
                artifact[key] = str(item[key])
        artifacts.append(artifact)
    return artifacts


def _parse_string_dict(text: str, flag: str) -> dict[str, str]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CliError("invalid_input", f"{flag} must be a JSON object.") from exc
    if not isinstance(payload, dict):
        raise CliError("invalid_input", f"{flag} must be a JSON object.")
    return {str(key): str(value) for key, value in payload.items() if value is not None}


def _parse_key_value_pairs(values: list[str], flag: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise CliError("invalid_input", f"{flag} must be formatted as KEY=VALUE.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise CliError("invalid_input", f"{flag} must include a non-empty key.")
        parsed[key] = value
    return parsed


def _parse_path_dict(values: list[str], flag: str) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for item in values:
        if "=" not in item:
            raise CliError("invalid_input", f"{flag} must be formatted as KEY=PATH.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise CliError("invalid_input", f"{flag} must include a non-empty key.")
        if not value:
            raise CliError("invalid_input", f"{flag} must include a non-empty path.")
        parsed[key] = Path(value)
    return parsed


def _render_options_from_args(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    overrides = {
        key: getattr(args, key, None)
        for key in (
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
    }
    return render_options(
        settings,
        overrides,
        use_brand_kit=not bool(getattr(args, "no_brand_kit", False)),
    )


def _brand_kit_changes(args: argparse.Namespace) -> dict[str, Any]:
    changes = {
        key: getattr(args, key)
        for key in (
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
        if getattr(args, key, None) is not None
    }
    if args.enable:
        changes["enabled"] = True
    elif args.disable:
        changes["enabled"] = False
    if args.clear_watermark_image:
        changes["watermark_image_path"] = None
    if changes.get("watermark_image_path"):
        changes["watermark_image_path"] = str(Path(str(changes["watermark_image_path"])).expanduser().resolve())
    if not changes:
        raise CliError("invalid_input", "Pass at least one Brand Kit setting.")
    return changes


def _combined_hidden_context(inline_context: str | None, context_file: str | None) -> str | None:
    parts: list[str] = []
    if inline_context:
        parts.append(inline_context)
    if context_file:
        try:
            parts.append(Path(context_file).expanduser().read_text(encoding="utf-8"))
        except OSError as exc:
            raise CliError("invalid_input", f"--hidden-context-file could not be read: {exc}") from exc
    return "\n".join(part for part in parts if part).strip() or None


if __name__ == "__main__":
    raise SystemExit(main())
