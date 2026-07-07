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
            "transcribe",
            "translate",
            "add_subtitles",
            "dub",
            "burn",
            "mix_dubbed_audio",
            "summarize",
            "shorten",
            "image",
            "video",
            "nlu",
            "agent_run",
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
            "--position",
            args.get("position", "bottom"),
            *optional("--watermark-text", args.get("watermark_text")),
            "--watermark-position",
            args.get("watermark_position", "top-right"),
            *optional("--watermark-font-size", args.get("watermark_font_size")),
            *optional("--watermark-color", args.get("watermark_color")),
            "--watermark-opacity",
            str(args.get("watermark_opacity", 0.72)),
            "--watermark-margin",
            str(args.get("watermark_margin", 24)),
            *optional("--watermark-image", args.get("watermark_image_path")),
            "--watermark-image-position",
            args.get("watermark_image_position", "top-right"),
            *optional("--watermark-image-width", args.get("watermark_image_width")),
            "--watermark-image-opacity",
            str(args.get("watermark_image_opacity", 0.72)),
            "--watermark-image-margin",
            str(args.get("watermark_image_margin", 24)),
        ]
        if args.get("bilingual"):
            command.append("--bilingual")
        return command
    if tool == "dub":
        return base + [
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
    if tool == "burn":
        return base + [
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
            "--position",
            args.get("position", "bottom"),
            *optional("--watermark-text", args.get("watermark_text")),
            "--watermark-position",
            args.get("watermark_position", "top-right"),
            *optional("--watermark-font-size", args.get("watermark_font_size")),
            *optional("--watermark-color", args.get("watermark_color")),
            "--watermark-opacity",
            str(args.get("watermark_opacity", 0.72)),
            "--watermark-margin",
            str(args.get("watermark_margin", 24)),
            *optional("--watermark-image", args.get("watermark_image_path")),
            "--watermark-image-position",
            args.get("watermark_image_position", "top-right"),
            *optional("--watermark-image-width", args.get("watermark_image_width")),
            "--watermark-image-opacity",
            str(args.get("watermark_image_opacity", 0.72)),
            "--watermark-image-margin",
            str(args.get("watermark_image_margin", 24)),
        ]
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
        return base + ["image", args["prompt"], "--aspect-ratio", args.get("aspect_ratio", "1:1"), "--image-size", args.get("image_size", "1K"), *optional("--model", args.get("model")), *optional("--out", args.get("out"))]
    if tool == "video":
        command = base + ["video", args["prompt"], "--aspect-ratio", args.get("aspect_ratio", "16:9"), "--duration", str(args.get("duration", 5))]
        if not args.get("generate_audio", True):
            command.append("--no-audio")
        if args.get("watermark"):
            command.append("--watermark")
        command.extend(["--generation-mode", args.get("generation_mode", "text")])
        command.extend(optional("--resolution", args.get("resolution")))
        command.extend(optional("--first-frame-image-url", args.get("first_frame_image_url")))
        for url in args.get("reference_image_urls", []):
            command.extend(["--reference-image-url", url])
        for url in args.get("reference_video_urls", []):
            command.extend(["--reference-video-url", url])
        for url in args.get("reference_audio_urls", []):
            command.extend(["--reference-audio-url", url])
        return command + optional("--model", args.get("model")) + optional("--model-name", args.get("model_name")) + optional("--model-version", args.get("model_version")) + optional("--out", args.get("out")) + optional("--timeout", args.get("timeout"))
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
        command.extend(optional("--conversation-id", args.get("conversation_id")))
        command.extend(optional("--task-intent", args.get("task_intent")))
        if args.get("task_parameters"):
            command.extend(["--task-parameters-json", json.dumps(args["task_parameters"], ensure_ascii=False)])
        if args.get("conversation_state"):
            command.extend(["--conversation-state-json", json.dumps(args["conversation_state"], ensure_ascii=False)])
        if args.get("wait"):
            command.append("--wait")
        command.extend(optional("--timeout", args.get("timeout")))
        return command
    raise ValueError(f"Unsupported tool: {tool}")


def optional(flag: str, value) -> list[str]:
    return [flag, str(value)] if value else []


if __name__ == "__main__":
    raise SystemExit(main())
