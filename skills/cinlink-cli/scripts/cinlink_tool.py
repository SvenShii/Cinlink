from __future__ import annotations

import argparse
import json
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="call_cinlink_tool")
    parser.add_argument(
        "tool",
        choices=[
            "configure",
            "doctor",
            "setup_local_deps",
            "transcribe",
            "translate",
            "add_subtitles",
            "dub",
            "burn",
            "apply_watermark",
            "trim_video",
            "montage",
            "clean_cut",
            "brand_kit",
            "mix_dubbed_audio",
            "summarize",
            "shorten",
            "image",
            "video",
            "deconstruct_video",
            "regenerate_deconstruction",
            "export_video",
            "export_audio",
            "export_editor_project",
            "nlu",
            "agent_run",
            "agent_clarify",
            "agent_events",
        ],
    )
    parser.add_argument("--args-json", required=True, help="JSON object containing tool arguments.")
    ns = parser.parse_args()
    try:
        args = json.loads(ns.args_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": {"code": "invalid_input", "message": f"--args-json is invalid JSON: {exc}"}}, ensure_ascii=False))
        return 1
    if not isinstance(args, dict):
        print(json.dumps({"error": {"code": "invalid_input", "message": "--args-json must be a JSON object."}}, ensure_ascii=False))
        return 1

    command = build_command(ns.tool, args)
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    print(completed.stdout.strip())
    return completed.returncode


def build_command(tool: str, args: dict) -> list[str]:
    base = ["cinlink", "--json"]
    if tool == "configure":
        return base + ["onboarding", "--api-key", args["api_key"], *optional("--runtime-base", args.get("runtime_base")), *optional("--billing-base", args.get("billing_base"))]
    if tool == "doctor":
        return base + ["doctor"]
    if tool == "setup_local_deps":
        command = base + ["setup-local-deps"]
        if args.get("yes"):
            command.append("--yes")
        if args.get("dry_run"):
            command.append("--dry-run")
        if args.get("skip_ffmpeg"):
            command.append("--skip-ffmpeg")
        if args.get("with_voice_separation"):
            command.append("--with-voice-separation")
        if args.get("skip_voice_separation"):
            command.append("--skip-voice-separation")
        return command
    if tool == "transcribe":
        return base + ["transcribe", args["input_path"], "--lang", args.get("lang", "auto"), *optional("--out", args.get("out")), *optional("--timeout", args.get("timeout"))]
    if tool == "translate":
        command = base + ["translate", args["input_path"], "--from", args.get("from_lang", "auto"), "--to", args.get("to_lang", "zh"), "--delivery", args.get("delivery", "subtitle")]
        if args.get("bilingual"):
            command.append("--bilingual")
        return command + optional("--out", args.get("out")) + optional("--timeout", args.get("timeout"))
    if tool == "add_subtitles":
        command = base + [
            "add-subtitles",
            args["video_path"],
            "--source-lang",
            args.get("source_lang", "auto"),
            *optional("--subtitle", args.get("subtitle_path")),
            *optional("--target-lang", args.get("target_lang")),
            *optional("--out", args.get("out")),
            *optional("--timeout", args.get("timeout")),
            *optional("--font-size", args.get("font_size")),
            *optional("--font-name", args.get("font_name")),
            *optional("--font-color", args.get("font_color")),
            *optional("--outline-color", args.get("outline_color")),
            *optional("--outline-width", args.get("outline_width")),
            *optional("--margin-v", args.get("margin_v")),
            *optional("--position", args.get("position")),
            *optional("--watermark-text", args.get("watermark_text")),
            *optional("--watermark-position", args.get("watermark_position")),
            *optional("--watermark-font-size", args.get("watermark_font_size")),
            *optional("--watermark-color", args.get("watermark_color")),
            *optional("--watermark-opacity", args.get("watermark_opacity")),
            *optional("--watermark-margin", args.get("watermark_margin")),
            *optional("--watermark-image", args.get("watermark_image_path")),
            *optional("--watermark-image-position", args.get("watermark_image_position")),
            *optional("--watermark-image-width", args.get("watermark_image_width")),
            *optional("--watermark-image-opacity", args.get("watermark_image_opacity")),
            *optional("--watermark-image-margin", args.get("watermark_image_margin")),
        ]
        if args.get("bilingual"):
            command.append("--bilingual")
        if args.get("no_brand_kit"):
            command.append("--no-brand-kit")
        return command
    if tool == "dub":
        command = base + [
            "dub",
            args["video_path"],
            "--subtitle",
            args["subtitle_path"],
            "--lang",
            args.get("language", "zh"),
            *optional("--reference-subtitle", args.get("reference_subtitle_path")),
            *optional("--voice", args.get("voice")),
            *optional("--out", args.get("out")),
            *optional("--timeout", args.get("timeout")),
        ]
        for speaker_id, path in sorted((args.get("reference_audio_paths") or {}).items()):
            command.extend(["--reference-audio", f"{speaker_id}={path}"])
        return command
    if tool == "burn":
        command = base + [
            "burn",
            args["video_path"],
            "--subtitle",
            args["subtitle_path"],
            *optional("--out", args.get("out")),
            *optional("--font-size", args.get("font_size")),
            *optional("--font-name", args.get("font_name")),
            *optional("--font-color", args.get("font_color")),
            *optional("--outline-color", args.get("outline_color")),
            *optional("--outline-width", args.get("outline_width")),
            *optional("--margin-v", args.get("margin_v")),
            *optional("--position", args.get("position")),
            *optional("--watermark-text", args.get("watermark_text")),
            *optional("--watermark-position", args.get("watermark_position")),
            *optional("--watermark-font-size", args.get("watermark_font_size")),
            *optional("--watermark-color", args.get("watermark_color")),
            *optional("--watermark-opacity", args.get("watermark_opacity")),
            *optional("--watermark-margin", args.get("watermark_margin")),
            *optional("--watermark-image", args.get("watermark_image_path")),
            *optional("--watermark-image-position", args.get("watermark_image_position")),
            *optional("--watermark-image-width", args.get("watermark_image_width")),
            *optional("--watermark-image-opacity", args.get("watermark_image_opacity")),
            *optional("--watermark-image-margin", args.get("watermark_image_margin")),
        ]
        if args.get("no_brand_kit"):
            command.append("--no-brand-kit")
        return command
    if tool == "apply_watermark":
        command = base + [
            "apply-watermark",
            args["video_path"],
            *optional("--out", args.get("out")),
            *optional("--watermark-text", args.get("watermark_text")),
            *optional("--watermark-position", args.get("watermark_position")),
            *optional("--watermark-font-size", args.get("watermark_font_size")),
            *optional("--watermark-color", args.get("watermark_color")),
            *optional("--watermark-opacity", args.get("watermark_opacity")),
            *optional("--watermark-margin", args.get("watermark_margin")),
            *optional("--watermark-image", args.get("watermark_image_path")),
            *optional("--watermark-image-position", args.get("watermark_image_position")),
            *optional("--watermark-image-width", args.get("watermark_image_width")),
            *optional("--watermark-image-opacity", args.get("watermark_image_opacity")),
            *optional("--watermark-image-margin", args.get("watermark_image_margin")),
        ]
        if args.get("no_brand_kit"):
            command.append("--no-brand-kit")
        return command
    if tool == "trim_video":
        return base + [
            "trim-video",
            args["video_path"],
            "--start",
            str(args["start_sec"]),
            "--end",
            str(args["end_sec"]),
            *optional("--out", args.get("out")),
        ]
    if tool == "montage":
        return base + [
            "montage",
            "--clips-json",
            json.dumps(args["clips"], ensure_ascii=False),
            *optional("--out", args.get("out")),
        ]
    if tool == "clean_cut":
        return base + [
            "clean-cut",
            args["video_path"],
            "--minimum-silence",
            str(args.get("minimum_silence_sec", 0.75)),
            "--noise-threshold-db",
            str(args.get("noise_threshold_db", -35.0)),
            "--retained-pause",
            str(args.get("retained_pause_sec", 0.24)),
            "--minimum-removal",
            str(args.get("minimum_removal_sec", 0.18)),
            *optional("--out", args.get("out")),
        ]
    if tool == "brand_kit":
        action = args.get("action", "show")
        command = base + ["brand-kit", action]
        if action != "set":
            return command
        if args.get("enabled") is True:
            command.append("--enable")
        elif args.get("enabled") is False:
            command.append("--disable")
        for key, flag in (
            ("font_size", "--font-size"),
            ("font_name", "--font-name"),
            ("font_color", "--font-color"),
            ("outline_color", "--outline-color"),
            ("outline_width", "--outline-width"),
            ("margin_v", "--margin-v"),
            ("position", "--position"),
            ("watermark_text", "--watermark-text"),
            ("watermark_position", "--watermark-position"),
            ("watermark_font_size", "--watermark-font-size"),
            ("watermark_color", "--watermark-color"),
            ("watermark_opacity", "--watermark-opacity"),
            ("watermark_margin", "--watermark-margin"),
            ("watermark_image_path", "--watermark-image"),
            ("watermark_image_position", "--watermark-image-position"),
            ("watermark_image_width", "--watermark-image-width"),
            ("watermark_image_opacity", "--watermark-image-opacity"),
            ("watermark_image_margin", "--watermark-image-margin"),
        ):
            command.extend(optional(flag, args.get(key)))
        if args.get("clear_watermark_image"):
            command.append("--clear-watermark-image")
        return command
    if tool == "mix_dubbed_audio":
        return base + [
            "mix-dubbed-audio",
            args["video_path"],
            "--dubbed-audio",
            args["dubbed_audio_path"],
            *optional("--out", args.get("out")),
            "--original-volume",
            str(args.get("original_volume", 0.65)),
            "--dubbed-volume",
            str(args.get("dubbed_volume", 1.0)),
        ]
    if tool == "summarize":
        return base + ["summarize", args["input_path"], "--max-highlights", str(args.get("max_highlights", 3)), *optional("--out", args.get("out"))]
    if tool == "shorten":
        return base + [
            "shorten",
            args["video_path"],
            "--max-clips",
            str(args.get("max_clips", 5)),
            "--target-duration",
            str(args.get("target_duration", 45)),
            "--music-mode",
            args.get("music_mode", "none"),
            *optional("--style-preset", args.get("style_preset")),
            *optional("--music-prompt", args.get("music_prompt")),
            *optional("--out", args.get("out")),
        ]
    if tool == "image":
        command = base + ["image", args["prompt"], "--aspect-ratio", args.get("aspect_ratio", "1:1"), "--image-size", args.get("image_size", "1K")]
        for url in args.get("reference_image_urls", []):
            command.extend(["--reference-image-url", url])
        return command + optional("--model", args.get("model")) + optional("--out", args.get("out")) + optional("--timeout", args.get("timeout"))
    if tool == "video":
        command = base + ["video", args["prompt"], "--aspect-ratio", args.get("aspect_ratio", "16:9"), "--duration", str(args.get("duration", 5))]
        if not args.get("generate_audio", True):
            command.append("--no-audio")
        if args.get("watermark"):
            command.append("--watermark")
        command.extend(optional("--generation-mode", args.get("generation_mode")))
        command.extend(optional("--resolution", args.get("resolution")))
        command.extend(optional("--first-frame-image-url", args.get("first_frame_image_url")))
        for url in args.get("reference_image_urls", []):
            command.extend(["--reference-image-url", url])
        for url in args.get("reference_video_urls", []):
            command.extend(["--reference-video-url", url])
        for url in args.get("reference_audio_urls", []):
            command.extend(["--reference-audio-url", url])
        return command + optional("--model", args.get("model")) + optional("--model-name", args.get("model_name")) + optional("--model-version", args.get("model_version")) + optional("--out", args.get("out")) + optional("--timeout", args.get("timeout"))
    if tool == "deconstruct_video":
        command = base + [
            "deconstruct-video",
            args["video_path"],
            "--scene-threshold",
            str(args.get("scene_threshold", 0.28)),
            "--max-shots",
            str(args.get("max_shots", 120)),
            "--language",
            args.get("language", "zh-Hans"),
            *optional("--analysis-scope", args.get("analysis_scope")),
            *optional("--out", args.get("out")),
        ]
        for reference in args.get("replacement_references", []):
            command.extend(
                [
                    "--replacement-reference",
                    f"{reference['role']}={reference['path']}",
                ]
            )
        return command
    if tool == "regenerate_deconstruction":
        command = base + [
            "regenerate-deconstruction",
            args["plan_path"],
            "--resolution",
            args.get("resolution", "720P"),
            *optional("--model", args.get("model")),
            *optional("--model-name", args.get("model_name")),
            *optional("--model-version", args.get("model_version")),
            *optional("--out", args.get("out")),
            *optional("--timeout", args.get("timeout")),
        ]
        if args.get("preserve_original_audio") is False:
            command.append("--no-original-audio")
        for reference in args.get("replacement_references", []):
            command.extend(
                [
                    "--replacement-reference",
                    f"{reference['role']}={reference['path']}",
                ]
            )
        return command
    if tool == "export_video":
        return base + [
            "export-video",
            args["video_path"],
            "--format",
            args.get("output_format", "mp4"),
            *optional("--out", args.get("out")),
        ]
    if tool == "export_audio":
        return base + [
            "export-audio",
            args["video_path"],
            "--format",
            args.get("output_format", "wav"),
            *optional("--audio-source", args.get("audio_path")),
            *optional("--out", args.get("out")),
        ]
    if tool == "export_editor_project":
        return base + [
            "export-editor-project",
            args["video_path"],
            "--target",
            args["target"],
            *optional("--subtitle", args.get("subtitle_path")),
            *optional("--audio-source", args.get("audio_path")),
            *optional("--out", args.get("out")),
        ]
    if tool == "nlu":
        command = base + ["nlu", args["prompt"]]
        if args.get("has_video"):
            command.append("--has-video")
        if args.get("has_subtitle"):
            command.append("--has-subtitle")
        command.extend(optional("--pending-target-language", args.get("pending_target_language")))
        for path in args.get("context_files", []):
            command.extend(["--context-file", path])
        return command
    if tool == "agent_run":
        command = base + ["agent", "run", args["prompt"], "--mode", args.get("mode", "execute")]
        for path in args.get("context_file", []):
            command.extend(["--context-file", path])
        for descriptor in args.get("context_descriptors", []):
            command.extend(["--context-json", json.dumps(descriptor, ensure_ascii=False)])
        command.extend(optional("--conversation-id", args.get("conversation_id")))
        command.extend(optional("--client-request-id", args.get("client_request_id")))
        command.extend(optional("--app-language", args.get("app_language")))
        command.extend(optional("--task-intent", args.get("task_intent")))
        command.extend(optional("--hidden-context", args.get("hidden_context")))
        if args.get("task_parameters"):
            command.extend(["--task-parameters-json", json.dumps(args["task_parameters"], ensure_ascii=False)])
        if args.get("conversation_state"):
            command.extend(["--conversation-state-json", json.dumps(args["conversation_state"], ensure_ascii=False)])
        if args.get("wait"):
            command.append("--wait")
        if args.get("include_events"):
            command.append("--include-events")
        command.extend(optional("--timeout", args.get("timeout")))
        return command
    if tool == "agent_clarify":
        command = base + ["agent", "clarify", args["run_id"]]
        command.extend(optional("--clarification-id", args.get("clarification_id")))
        command.extend(optional("--value", args.get("value")))
        command.extend(optional("--answer", args.get("answer")))
        command.extend(optional("--client-request-id", args.get("client_request_id")))
        if args.get("wait"):
            command.append("--wait")
        if args.get("include_events"):
            command.append("--include-events")
        command.extend(optional("--timeout", args.get("timeout")))
        return command
    if tool == "agent_events":
        return base + [
            "agent",
            "events",
            args["run_id"],
            *optional("--last-event-id", args.get("last_event_id")),
            *optional("--timeout", args.get("timeout")),
        ]
    raise ValueError(f"Unsupported tool: {tool}")


def optional(flag: str, value) -> list[str]:
    return [flag, str(value)] if value is not None and value != "" else []


if __name__ == "__main__":
    raise SystemExit(main())
