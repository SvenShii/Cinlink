---
name: cinlink-agent
description: CinLink hosted agent runtime for multi-step media tasks. Use when the user gives a broad natural-language request that may require planning, multiple CinLink tools, local tool calls, context files, clarification, or recovery across transcription, translation, dubbing, summarization, short-video planning, and AI media generation.
---

# CinLink Agent

Use this when the request is broader than one direct command.

## Submit A Run

```bash
cinlink --json agent run "<prompt>" --context-file /absolute/video.mp4 --app-language zh --mode execute --wait
```

Use `--mode plan` when the user wants a plan before execution. Use `--wait` for short/medium jobs; otherwise return the `run_id` and poll later.

For app-parity routing, pass the explicit current task when it is known:

```bash
cinlink --json agent run "Add English subtitles and return the subtitled video." --context-file /absolute/video.mp4 --task-intent add_subtitles --task-param output_delivery=burned_video --task-param target_language=en --mode execute --wait
```

Useful `--task-intent` values include `add_subtitles`, `translate_and_burn_subtitles`, `dub_video`, `summarize_video`, `shorten_video`, `generate_image`, and `generate_video`. Useful `--task-param` keys include `output_delivery`, `target_language`, `source_language`, `subtitle_language`, and `translation_mode`.

Always pass `--app-language` when the caller knows the user's UI/conversation language (`zh`, `en`, or `ja`). This controls clarification, progress, failure, and completion messages even when the prompt itself is ambiguous.

If the current prompt names a target language, that current language wins over recent messages, saved conversation state, or historical defaults. For "add subtitles" requests, default `output_delivery` to `burned_video` unless the user explicitly asks for only an SRT/subtitle/transcript file.

Use `--client-request-id <id>` when the caller has a stable idempotency/correlation id. Use `--hidden-context` or `--hidden-context-file` only for invisible client UI state such as selected settings; never put secrets there, and do not copy hidden context into provider prompts or user-visible text.

For follow-up tasks, preserve rich artifact context from earlier output:

```bash
cinlink --json agent run "Use this generated image as the video reference." --app-language en --context-json '{"name":"generated.png","kind":"image","public_url":"https://...","cloud_file_id":"...","metadata":{"artifact_role":"generated_image","producer_step":"generate_image"}}' --task-intent generate_video --wait
```

Use `--context-file` for a plain local path. Use repeated `--context-json` when identity or lineage fields such as `id`, `entity_id`, `local_asset_id`, `cloud_file_id`, `public_url`, `artifact_role`, or `producer_step` are available.

## Poll

```bash
cinlink --json agent poll <run_id>
```

## Local Tool Calls

The hosted runtime may request local work when the user's machine owns the file, local `ffmpeg` is needed, or an app-local capability owns the state:

```bash
cinlink --json agent local-tools <run_id>
cinlink --json agent report-tool-result <run_id> --tool-call-id <id> --status done --artifact-path /absolute/out.mp4 --artifact-metadata-json '{"artifact_role":"edited_video","producer_step":"trim_video"}'
```

Current Hermes-first media tools include `stage_subtitle`, `search_analyzed_videos`, `extract_audio`, `extract_video_frames`, `probe_video`, `trim_video`, `crop_resize_video`, `transcode_video`, `apply_watermark`, `burn_subtitles`, `render_highlight_clips`, `render_visual_match_clips`, `render_styled_edit`, `mix_background_music`, `merge_video_clips`, `enhance_video`, and `compose_dubbed_video`. General local context tools include `local_file_search`, `local_file_read`, `local_clipboard_read`, `local_screenshot`, and `local_app_context`. Only advertise, execute, and report a local tool when the local environment actually has the matching capability and user authorization.

When reporting a local subtitle burn, include both the rendered video and the subtitle file when available, and preserve delivery metadata:

```bash
cinlink --json agent report-tool-result <run_id> --tool-call-id <id> --status done --artifact-json '{"path":"/absolute/subtitled.mp4","kind":"video","metadata":{"artifact_role":"burned_video","producer_step":"burn_subtitles"}}' --artifact-json '{"path":"/absolute/subtitles.srt","kind":"subtitle","metadata":{"artifact_role":"translated_subtitle","producer_step":"translate_subtitle"}}' --metadata-json '{"output_delivery":"burned_video"}'
```

`--artifact-path` now infers video/audio/subtitle/image/document kind from the extension. Prefer `--artifact-json` when individual artifacts need different roles or lineage metadata.

For hosted workflows starting from a video, keep the full video local and pass extracted audio to server tools. For typed dubbing/voice-translation plans, expect the split pipeline: local `extract_audio`, server `transcribe_audio` and `translate_subtitle`, server `synthesize_dub_audio`, then local `compose_dubbed_video` when `can_render_video_locally` and `split_dub_pipeline_v1` are available. Never send a local video artifact directly to a server transcription, translation, summary, shortening, or dubbing tool.

Return the run's `privacy_receipt` in user-facing terms: what stayed local, which derived inputs went to CinLink Cloud, and whether final video rendering happened locally.

## Routing Guidance

Use `/cinlink-agent` for:

- Multi-step media workflows
- Requests where the user describes the outcome but not exact operations
- Tasks involving multiple context files
- Workflows needing clarification or recovery
- App-like Hermes workflows that return `execute_plan`, request install/authorization cards, or need staged subtitles/local tool reporting

For a single explicit operation, prefer the direct domain skill.
