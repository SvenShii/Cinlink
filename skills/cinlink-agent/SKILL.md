---
name: cinlink-agent
description: CinLink hosted agent runtime for multi-step media tasks. Use when the user gives a broad natural-language request that may require planning, multiple CinLink tools, local tool calls, context files, clarification, or recovery across transcription, translation, dubbing, summarization, short-video planning, and AI media generation.
---

# CinLink Agent

Use this when the request is broader than one direct command.

## Submit A Run

```bash
cinlink --json agent run "<prompt>" --context-file /absolute/video.mp4 --mode execute --wait
```

Use `--mode plan` when the user wants a plan before execution. Use `--wait` for short/medium jobs; otherwise return the `run_id` and poll later.

For app-parity routing, pass the explicit current task when it is known:

```bash
cinlink --json agent run "Add English subtitles and return the subtitled video." --context-file /absolute/video.mp4 --task-intent add_subtitles --task-param output_delivery=burned_video --task-param target_language=en --mode execute --wait
```

Useful `--task-intent` values include `add_subtitles`, `translate_and_burn_subtitles`, `dub_video`, `summarize_video`, `shorten_video`, `generate_image`, and `generate_video`. Useful `--task-param` keys include `output_delivery`, `target_language`, `source_language`, `subtitle_language`, and `translation_mode`.

If the current prompt names a target language, that current language wins over recent messages, saved conversation state, or historical defaults. For "add subtitles" requests, default `output_delivery` to `burned_video` unless the user explicitly asks for only an SRT/subtitle/transcript file.

## Poll

```bash
cinlink --json agent poll <run_id>
```

## Local Tool Calls

The hosted runtime may request local work when the user's machine owns the file or local `ffmpeg` is needed:

```bash
cinlink --json agent local-tools <run_id>
cinlink --json agent report-tool-result <run_id> --tool-call-id <id> --status done --artifact-path /absolute/out.mp4
```

When reporting a local subtitle burn, include both the rendered video and the subtitle file when available, and preserve delivery metadata:

```bash
cinlink --json agent report-tool-result <run_id> --tool-call-id <id> --status done --artifact-path /absolute/subtitled.mp4 --artifact-path /absolute/subtitles.srt --metadata-json '{"output_delivery":"burned_video"}'
```

## Routing Guidance

Use `/cinlink-agent` for:

- Multi-step media workflows
- Requests where the user describes the outcome but not exact operations
- Tasks involving multiple context files
- Workflows needing clarification or recovery

For a single explicit operation, prefer the direct domain skill.
