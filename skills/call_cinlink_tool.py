from __future__ import annotations

import argparse
import json
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="call_cinlink_tool")
    parser.add_argument("tool", choices=["doctor", "transcribe", "translate", "burn", "summarize", "shorten", "image", "video", "nlu", "agent_run"])
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
    if tool == "doctor":
        return base + ["doctor"]
    if tool == "transcribe":
        return base + ["transcribe", args["input_path"], "--lang", args.get("lang", "auto"), *optional("--out", args.get("out"))]
    if tool == "translate":
        command = base + ["translate", args["input_path"], "--from", args.get("from_lang", "auto"), "--to", args.get("to_lang", "zh"), "--delivery", args.get("delivery", "subtitle")]
        if args.get("bilingual"):
            command.append("--bilingual")
        return command + optional("--out", args.get("out"))
    if tool == "burn":
        return base + ["burn", args["video_path"], "--subtitle", args["subtitle_path"], *optional("--out", args.get("out"))]
    if tool == "summarize":
        return base + ["summarize", args["input_path"], "--max-highlights", str(args.get("max_highlights", 3)), *optional("--out", args.get("out"))]
    if tool == "shorten":
        return base + ["shorten", args["video_path"], "--max-clips", str(args.get("max_clips", 5)), "--target-duration", str(args.get("target_duration", 45)), *optional("--out", args.get("out"))]
    if tool == "image":
        return base + ["image", args["prompt"], "--aspect-ratio", args.get("aspect_ratio", "1:1"), "--image-size", args.get("image_size", "1K"), *optional("--out", args.get("out"))]
    if tool == "video":
        command = base + ["video", args["prompt"], "--aspect-ratio", args.get("aspect_ratio", "16:9"), "--duration", str(args.get("duration", 5))]
        if not args.get("generate_audio", True):
            command.append("--no-audio")
        return command + optional("--out", args.get("out"))
    if tool == "nlu":
        command = base + ["nlu", args["prompt"]]
        if args.get("has_video"):
            command.append("--has-video")
        if args.get("has_subtitle"):
            command.append("--has-subtitle")
        return command
    if tool == "agent_run":
        command = base + ["agent", "run", args["prompt"], "--mode", args.get("mode", "execute")]
        for path in args.get("context_file", []):
            command.extend(["--context-file", path])
        if args.get("wait"):
            command.append("--wait")
        return command
    raise ValueError(f"Unsupported tool: {tool}")


def optional(flag: str, value: str | None) -> list[str]:
    return [flag, str(value)] if value else []


if __name__ == "__main__":
    raise SystemExit(main())
