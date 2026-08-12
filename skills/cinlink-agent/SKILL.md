---
name: cinlink-agent
description: CinLink hosted agent runtime for multi-step media tasks. Use when the user gives a broad natural-language request that may require planning, multiple CinLink tools, local tool calls, context files, clarification, or recovery across transcription, translation, dubbing, summarization, video deconstruction, short-video planning, web research, and AI media generation.
---

# CinLink Agent

Use this when the request is broader than one direct command.

## Submit A Run

```bash
cinlink --json agent run "<prompt>" --context-file /absolute/video.mp4 --app-language zh --mode execute --wait --include-events
```

Use `--mode plan` when the user wants a plan before execution. Use `--wait` for short/medium jobs; otherwise return the `run_id` and poll later.

`--include-events` collects the hosted runtime's public planning and reasoning events while waiting. It does not expose hidden model scratch work.

For app-parity routing, pass the explicit current task when it is known:

```bash
cinlink --json agent run "Add English subtitles and return the subtitled video." --context-file /absolute/video.mp4 --task-intent add_subtitles --task-param output_delivery=burned_video --task-param target_language=en --mode execute --wait
```

Useful `--task-intent` values include `add_subtitles`, `translate_and_burn_subtitles`, `dub_video`, `summarize_video`, `shorten_video`, `deconstruct_video`, `edit_video`, `watermark`, `enhance_video`, `multi_video_montage`, `generate_image`, and `generate_video`. Useful `--task-param` keys include `output_delivery`, `target_language`, `source_language`, `subtitle_language`, `translation_mode`, `analysis_scope`, `target_duration_sec`, `require_audio`, `reference_image_urls`, `watermark_text_position`, `watermark_image_position`, `watermark_font_size`, `watermark_opacity`, `watermark_margin`, `watermark_image_width`, `watermark_image_opacity`, and `watermark_image_margin`.

Always pass `--app-language` when the caller knows the user's UI/conversation language (`zh`, `en`, or `ja`). This controls clarification, progress, failure, and completion messages even when the prompt itself is ambiguous.

If the current prompt names a target language, that current language wins over recent messages, saved conversation state, or historical defaults. For "add subtitles" requests, default `output_delivery` to `burned_video` unless the user explicitly asks for only an SRT/subtitle/transcript file.

For free-form media translation, do not infer whether the user wants subtitles or dubbing, and do not infer subtitle-file versus burned-video delivery. Resolve `translation_mode=subtitle|voice` first. If subtitle mode is selected, resolve `output_delivery=subtitle_file|burned_video` next. Inspect `workflow_decision.slot_provenance`; `model_default` and `unknown` are not user-resolved choices.

Use `--client-request-id <id>` when the caller has a stable idempotency/correlation id. Use `--hidden-context` or `--hidden-context-file` only for invisible client UI state such as selected settings; never put secrets there, and do not copy hidden context into provider prompts or user-visible text.

For follow-up tasks, preserve rich artifact context from earlier output:

```bash
cinlink --json agent run "Use this generated image as the video reference." --app-language en --context-json '{"name":"generated.png","kind":"image","public_url":"https://...","cloud_file_id":"...","metadata":{"artifact_role":"generated_image","producer_step":"generate_image"}}' --task-intent generate_video --wait
```

Use `--context-file` for a plain local path. The CLI marks these files `selection_scope=current_submission` and `input_priority=highest`, so a single newly submitted file outranks stale conversation files. Use repeated `--context-json` when identity or lineage fields such as `id`, `entity_id`, `local_asset_id`, `cloud_file_id`, `public_url`, `artifact_role`, or `producer_step` are available. For an explicitly selected descriptor, set those two metadata fields yourself; historical descriptors are not elevated automatically.

When one video and a valid timed SRT/VTT/ASS are passed as local context files, the CLI marks the subtitle reusable and binds it to that video. For multiple subtitles or generated artifacts, use `--context-json` with explicit source lineage and language metadata so the runtime can select the exact target-language subtitle rather than retranscribing or translating it again.

For image/video generation, an explicitly bound reference must resolve to that exact authorized artifact. If its public URL or cloud identity is unavailable, ask for the selected image again; never substitute another image from conversation history.

For watermark requests, do not invent missing content: an image watermark requires the user's selected reference image, and a text watermark requires explicit watermark text. Ask for the missing input instead of substituting a Brand Kit value unless the user explicitly requested the saved Brand Kit.

The CLI checks a bound local subtitle timeline against the local video's duration when `ffprobe` is available. If cue starts or ends exceed the app's grace window, it marks `subtitle_reuse_eligible=false`; do not force reuse or bypass that mismatch.

## Poll

```bash
cinlink --json agent poll <run_id>
```

## Structured Clarifications

When a run returns `status=requires_user_input`, inspect `clarifications`. Present each `question` and its option labels to the user; never silently choose `is_default`.

Collect every visible clarification answer before continuing. Submit the complete set once, keyed by clarification id or `slot_key`:

```bash
cinlink --json agent clarify <run_id> --response translation_mode=subtitle --response output_delivery=burned_video --wait --include-events
```

For a single clarification, the compatible `--clarification-id <id> --value <value>` or `--answer "<text>"` form remains valid. Use `--answers-json '{"slot":"value"}'` when JSON is easier. `target_duration_sec` accepts an option or a custom duration from 10 to 600 seconds, including `90`, `1:30`, `00:01:30`, and localized units. Never start a continuation while another clarification from the same response is unresolved. `agent clarify` preserves the original workflow id, task frame, conversation, context files, app language, and compound execution plan; do not rebuild these fields manually.

For media/subtitle file-selection slots, pass the exact option value, stable context id, or exact context filename. The CLI resolves a unique name to its `entity_id` and elevates that descriptor to the current submission. If the name is ambiguous, unavailable, the wrong media kind, or an untimed TXT is offered where timed subtitles are required, ask the user to choose a valid exact file instead of guessing.

Some install or capability approvals use `requires_user_input` without a structured `clarifications` array. Ask for the requested authorization and follow the local install/tool flow instead of calling `agent clarify`.

## Public Event Stream

Read the agent's SSE progress stream:

```bash
cinlink --json agent events <run_id>
```

Resume after a known event when needed:

```bash
cinlink --json agent events <run_id> --last-event-id <event_id>
```

Treat `thinking_delta` as transient progress and `reasoning_delta` as a public explanation suitable for the user. Other events can include `status`, `tool_start`, `tool_complete`, `run`, `done`, and `error`. Never invent, request, or claim access to private chain-of-thought or hidden scratch work.

## Local Tool Calls

The hosted runtime may request local work when the user's machine owns the file, local `ffmpeg` is needed, or an app-local capability owns the state:

```bash
cinlink --json agent local-tools <run_id>
cinlink --json agent report-tool-result <run_id> --tool-call-id <id> --status done --artifact-path /absolute/out.mp4 --artifact-metadata-json '{"artifact_role":"edited_video","producer_step":"trim_video"}'
```

Current Hermes-first media tools include `stage_audio`, `stage_subtitle`, `search_analyzed_videos`, `extract_audio`, `extract_video_frames`, `probe_video`, `trim_video`, `crop_resize_video`, `transcode_video`, `apply_watermark`, `burn_subtitles`, `render_highlight_clips`, `render_visual_match_clips`, `render_styled_edit`, `mix_background_music`, `merge_video_clips`, `enhance_image`, `enhance_video`, and `compose_dubbed_video`. General local context tools include `local_file_search`, `local_file_read`, `local_clipboard_read`, `local_screenshot`, and `local_app_context`. Only advertise, execute, and report a local tool when the local environment actually has the matching capability and user authorization.

`stage_audio` makes an already authorized local audio file available to a later cloud model step. Report it with the account-scoped upload flag:

```bash
cinlink --json agent report-tool-result <run_id> --tool-call-id <id> --status done --artifact-path /absolute/source.m4a --artifact-metadata-json '{"producer_step":"stage_audio"}' --upload-for-cloud-model-input
```

Use the same upload flag when an authorized screenshot/image or subtitle/document local tool explicitly asks for cloud-model input. Never use it for a video; CinLink keeps full source videos local.

Local/server tool arguments use a string-only wire contract. Boolean values are `true`/`false`; list-like values may arrive as newline-delimited text, comma-delimited text, or a JSON array string. Parse those forms without corrupting Windows drive-letter paths.

Plan steps and local calls may contain `input_collections`, mapping one port to an ordered array of bindings. Resolve every binding in order. Never comma-join multiple bindings into `inputs`, and never collapse a collection to its first artifact.

Hosted plan nodes include `transcribe_audio`, `translate_subtitle`, `synthesize_dub_audio`, `summarize_video`, `shorten_video`, `deconstruct_video`, `generate_image`, `generate_video`, and `server_web_query`. Use `server_web_query` only for current public web information. For a complete editable multi-shot deconstruction, prefer `/cinlink-deconstruction`; the hosted Agent node analyzes an explicitly bound extracted frame.

When reporting a local subtitle burn, include both the rendered video and the subtitle file when available, and preserve delivery metadata:

```bash
cinlink --json agent report-tool-result <run_id> --tool-call-id <id> --status done --artifact-json '{"path":"/absolute/subtitled.mp4","kind":"video","metadata":{"artifact_role":"burned_video","producer_step":"burn_subtitles"}}' --artifact-json '{"path":"/absolute/subtitles.srt","kind":"subtitle","metadata":{"artifact_role":"translated_subtitle","producer_step":"translate_subtitle"}}' --metadata-json '{"output_delivery":"burned_video"}'
```

`--artifact-path` infers video/audio/subtitle/image/document kind from the extension. Prefer `--artifact-json` when individual artifacts need different roles or lineage metadata. Preserve `edit_plan` context and artifacts explicitly with `kind=edit_plan`, including `highlight_plan_status`, `highlight_plan_revision`, and `target_duration_sec`; an approved or modified plan should be reused for rendering instead of being regenerated.

For hosted workflows starting from a video, keep the full video local and pass extracted audio to server tools. For typed dubbing/voice-translation plans, expect the split pipeline: local `extract_audio`, server `transcribe_audio` and `translate_subtitle`, server `synthesize_dub_audio`, then local `compose_dubbed_video` when `can_render_video_locally` and `split_dub_pipeline_v1` are available. Never send a local video artifact directly to a server transcription, translation, summary, shortening, or dubbing tool.

For a shortened voice-dub video, synthesize against the original full-length audio timeline, compose the full-length dubbed video, and only then render the selected highlight clips. Never mix full-timeline dubbed audio directly into an already-shortened video.

When a user asks for the current project/workspace file list, issue a real `local_file_search` call with an empty query, `roots=project`, and an explicit `max_results`. Do not claim to have searched local files, read files, or captured a screenshot unless the corresponding local tool call exists and completed.

Return the run's `privacy_receipt` in user-facing terms: what stayed local, which derived inputs went to CinLink Cloud, and whether final video rendering happened locally.

When a run finishes, use `completion_message` as the user-facing completion text. Deliver `primary_artifacts` as the actual result, mention `supporting_artifacts` only when useful, and do not present `intermediate_artifacts` as final output. The raw `artifacts` list remains available for compatibility but should not drive final delivery.

On failure, show only the returned public `code` and `message`. Preserve safe `details` fields such as `processing_stage`, `provider`, `request_id`, and `retryable` for troubleshooting. Retry only when `retryable=true`; never expose or invent provider internals.

## Routing Guidance

Use `/cinlink-agent` for:

- Multi-step media workflows
- Requests where the user describes the outcome but not exact operations
- Tasks involving multiple context files
- Workflows needing clarification or recovery
- App-like Hermes workflows that return `execute_plan`, request install/authorization cards, or need staged subtitles/local tool reporting

For a single explicit operation, prefer the direct domain skill.
