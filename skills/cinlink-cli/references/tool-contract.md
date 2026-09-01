# CinLink Tool Contract

All commands should use `--json`. Successful and failed calls print one JSON object. Hosted tools require a configured CinLink API key.

## CLI Commands

### onboarding

```bash
cinlink --json onboarding --api-key <key> [--runtime-base <url>] [--billing-base <url>]
```

Stores config in the user-level CinLink CLI config file.

### doctor

```bash
cinlink --json doctor
```

Reports API-key presence, runtime health, and local dependency status.

### setup-local-deps

```bash
cinlink setup-local-deps
cinlink --json setup-local-deps --dry-run --with-voice-separation --with-enhancement
cinlink setup-local-deps --yes
```

Prompts the user to install local dependencies. `ffmpeg`/`ffprobe` are recommended for subtitle burn-in, local audio extraction/mixing, Clean Cut, trim/montage, watermark export, video deconstruction/assembly, media export, editor project handoff, and local media inspection. `demucs` plus `soundfile` are optional for voice separation. The optional enhancement component contains `waifu2x-ncnn-vulkan` plus photo/cunet/anime model directories; use `--with-enhancement` only after confirmation. Do not run with `--yes` until the user has confirmed.

### transcribe

```bash
cinlink --json transcribe <input_path> --lang auto --out <dir> --timeout 1800
```

Output usually includes `subtitle_path`, `preview_text`, `engine`, and job status fields. For video input, the CLI extracts audio locally with `ffmpeg`; the hosted runtime does not receive the full video.

### translate

```bash
cinlink --json translate <input_path> --from auto --to en --bilingual --delivery subtitle --out <dir>
```

`input_path` may be a subtitle or media file. `delivery` is `subtitle` or `voice`. For video input, the CLI extracts audio locally with `ffmpeg` and uploads only the audio.

### add-subtitles

```bash
cinlink --json add-subtitles <video_path> --source-lang auto --target-lang en --out <dir>
```

App-parity composite workflow. If `--subtitle <path>` is provided, it burns that subtitle. Otherwise it uses hosted transcribe, or hosted translate when `--target-lang` is set, then burns the resulting subtitle locally. Supports the same subtitle style and watermark args as `burn`.

### dub

```bash
cinlink --json dub <video_or_audio_path> --subtitle <subtitle_path> --reference-subtitle <source_subtitle_path> --lang en --voice <voice> --reference-audio speaker_0=<ref_audio_path> --out <dir>
```

Generates dubbed speech/audio using an existing subtitle file. The hosted runtime accepts audio, not video uploads; when the first argument is a video, the CLI extracts audio locally with `ffmpeg` before calling `/v1/dub`. For speaker-aligned/voice-cloned output, pass an original-language timed `--reference-subtitle` whose usable cue count matches the translated subtitle. If omitted, the CLI checks sibling `source.reference.srt`, `subtitle.reference.srt`, then `source.srt`. Also optional: repeated `--reference-audio SPEAKER_ID=PATH`, `--timeout`.

### burn

```bash
cinlink --json burn <video_path> --subtitle <subtitle_path> --font-size 22 --position bottom --out <dir>
```

Local-only. Supports `--font-name`, `--font-color`, `--outline-color`, `--outline-width`, `--margin-v`, text watermark args, and image watermark args. Enabled Brand Kit settings apply automatically; use `--no-brand-kit` to ignore them for one render.

### apply-watermark

```bash
cinlink --json apply-watermark <video_path> --watermark-text "Example" --out <dir>
```

Local-only. Text/image watermark arguments match `burn`. When no one-off watermark is supplied, the enabled Brand Kit logo/text is used.

### enhance-image / enhance-video

```bash
cinlink --json enhance-image <image_path> --model photo --scale 2 --noise-level 1 --out <dir>
cinlink --json enhance-video <video_path> --model photo --scale 2 --noise-level 1 --out <dir>
```

Local-only and no API key is required. Image enhancement accepts PNG/JPEG/WebP/HEIC/GIF and writes lossless PNG. Video enhancement processes frames locally and preserves the original audio. Both need the verified waifu2x component; video also needs `ffmpeg`/`ffprobe`.

### trim-video

```bash
cinlink --json trim-video <video_path> --start 12.4 --end 18.8 --out <dir_or_mp4>
```

Local-only. Renders the exact supplied range and returns typed `edited_video` artifact metadata.

### montage

```bash
cinlink --json montage --clips-json '[{"path":"/a.mp4","start_sec":1,"end_sec":4},{"path":"/b.mp4","start_sec":8,"end_sec":10}]' --out <dir_or_mp4>
```

Local-only. Requires at least two ranges and preserves their supplied order.

### clean-cut

```bash
cinlink --json clean-cut <video_path> --plan-only
cinlink --json clean-cut <video_path> --selected-removals-json '[0,2]' --out <dir_or_mp4>
```

Local-only. First returns indexed `candidate_removed_ranges`; agents must present them and obtain explicit approval before export. The conservative app defaults are minimum silence `0.85`, noise threshold `-35`, retained pause `0.24`, and minimum removal `0.18`. Standard/aggressive minimum-silence presets are `0.60`/`0.40`. `selected_removal_indexes` exports only approved candidates; omit it only after approval of all candidates.

### brand-kit

```bash
cinlink --json brand-kit show
cinlink --json brand-kit set --enable --font-name Arial --font-color '#FFFFFF' --watermark-image /absolute/logo.png
cinlink --json brand-kit clear
```

Stored in the user-level CinLink CLI JSON config. Enabled values automatically apply to later `add-subtitles`, `burn`, and `apply-watermark` calls. Explicit command values win.

### mix-dubbed-audio

```bash
cinlink --json mix-dubbed-audio <video_path> --dubbed-audio <audio_path> --original-volume 0.65 --dubbed-volume 1.0
```

Local-only. Mixes original audio with dubbed audio and muxes the result into a video.

### summarize

```bash
cinlink --json summarize <input_path> --max-highlights 3 --out <dir>
```

Returns summary text, highlights, `source_video_path`, and artifact paths when available. For video input, the CLI keeps the video local and uploads extracted audio.

### shorten

```bash
cinlink --json shorten <video_path> --target-duration 45 --max-clips 5 --selection-instruction "Prefer product demonstrations" --output-language zh-Hans --out <dir>
```

Optional: `--style-preset`, `--music-mode`, `--music-prompt`, `--selection-instruction`, and `--output-language zh-Hans|en|ja`. Selection instructions express what to include or avoid; output language controls clip titles, reasons, and plan presentation. The CLI keeps the full video local, uploads extracted audio to the account-scoped Agent file endpoint, then submits its `cloud_file_id` for hosted analysis. It falls back to compatibility multipart upload when an older runtime does not support cloud audio references. The result returns `source_video_path` for later local rendering. Present the proposed plan and obtain explicit confirmation before `render_highlight_clips`; preserve its revision, selection intent, and output language across replan, render, or cancel.

### image

```bash
cinlink --json image "<prompt>" --aspect-ratio 1:1 --image-size 1K --reference-image-url <url_or_local_path> --out <dir>
```

Optional: up to three repeated `--reference-image-url` values, `--model`, and `--timeout`. Local reference images are uploaded through the authenticated reference-image endpoint. The command waits for the hosted job and downloads the final image.

Optional: `--model`.

### video

```bash
cinlink --json video "<prompt>" --aspect-ratio 16:9 --duration 5 --out <dir>
```

Optional: `--resolution`, `--no-audio`, `--watermark`, `--generation-mode`, `--first-frame-image-url`, repeated `--reference-image-url`, repeated `--reference-video-url`, repeated `--reference-audio-url`, `--model`, `--model-name`, `--model-version`, `--timeout`. First-frame and reference-image values may be remote URLs or local image paths; local paths are uploaded through the authenticated reference-image endpoint. Reference video/audio values remain remote URLs.

### deconstruct-video

```bash
cinlink --json deconstruct-video <video_path> --language zh-Hans --analysis-scope "camera and lighting" --scene-threshold 0.28 --max-shots 120 --out <dir_or_json>
```

Detects cuts and samples first/middle/last shot frames locally, then sends only those frames to hosted deconstruction. `--language` controls human-readable titles/summaries/style/audio analysis; `--analysis-scope` focuses the visual analysis. Optional repeated `--replacement-reference person|product|scene=<image_path>` values are stored in the editable plan.

### regenerate-deconstruction

```bash
cinlink --json regenerate-deconstruction <plan_path> --resolution 720P --out <dir_or_video>
```

Generates the plan sequentially with cross-shot tail-frame continuity and assembles the result locally. Optional repeated `--replacement-reference`, model selectors, `--timeout`, and `--no-original-audio`.

### export-video

```bash
cinlink --json export-video <video_path> --format mp4|mov|avi|mkv --out <dir_or_file>
```

Local-only ffmpeg export.

### export-audio

```bash
cinlink --json export-audio <video_path> --format wav|mp3 --audio-source <optional_audio_path> --out <dir_or_file>
```

Local-only audio export. `--audio-source` selects a replacement/mixed track instead of the video's embedded audio.

### export-editor-project

```bash
cinlink --json export-editor-project <video_path> --target capcut|premiere|final-cut|resolve --subtitle <srt> --audio-source <audio> --out <dir>
```

Creates local XML/FCPXML or a portable CapCut media package. It does not launch a desktop editor.

### nlu

```bash
cinlink --json nlu "<prompt>" --has-video --context-file <path>
```

Routes a natural-language media task into an action and slots.

### agent run

```bash
cinlink --json agent run "<prompt>" --context-file <path> --app-language zh --mode execute --wait --include-events
```

Use for broad, multi-step media workflows. When the app surface action is known, pass it explicitly:

```bash
cinlink --json agent run "Add English subtitles and return the subtitled video." --context-file <path> --client-request-id <id> --task-intent add_subtitles --task-param output_delivery=burned_video --task-param target_language=en --mode execute --wait
```

Use repeated `--task-param KEY=VALUE` or `--task-parameters-json '{"key":"value"}'` for explicit slots such as `output_delivery`, `target_language`, `source_language`, `subtitle_language`, and `translation_mode`. Current prompt language and task parameters override historical conversation state. For free-form media translation, resolve `translation_mode=subtitle|voice` first; subtitle mode then requires `output_delivery=subtitle_file|burned_video`. Do not execute either choice from `workflow_decision.slot_provenance` sources `model_default` or `unknown`.

Pass `--app-language zh|en|ja` whenever the caller knows the user's language. Plain `--context-file` values are marked `selection_scope=current_submission` and `input_priority=highest`, and receive stable full-length path/content identities plus `file_version`. Use repeated `--context-json '<object>'` for follow-up artifacts carrying `public_url`, `cloud_file_id`, `artifact_role`, `producer_step`, source/timeline lineage, or other identity metadata; preserve complete ids without truncating them. Set the two priority fields in `metadata` only when a descriptor is explicitly selected for the current request.

Use `--hidden-context` or `--hidden-context-file` for invisible client UI context such as selected settings. Do not put secrets there, and do not copy hidden context into assistant-visible output or provider prompts.

The Hermes-first agent may return `execute_plan`, `research_capability`, or `propose_workaround`. Its local media tool set includes audio/subtitle staging, analyzed-video search, audio/frame extraction, probing, trim/crop/transcode, watermark/subtitle burn, highlight/visual/styled rendering, music mixing, clip merging, image/video enhancement, and dubbed-video composition. It can also request authorized local file search/read, clipboard, screenshot, or app context. Hosted nodes include transcription, translation, speech synthesis, summary, `shorten_video`, `plan_highlights`, frame/video deconstruction, image/video generation, and public web query. Web-only cloud executors may also expose Clean Cut/EDL render nodes; a CLI agent must not advertise `web_cloud_executor` and should keep renderer steps local. Only execute a local tool if the corresponding client capability and user authorization are present. Typed dubbing plans use local `extract_audio`, server `transcribe_audio`/`translate_subtitle`/`synthesize_dub_audio`, then local `compose_dubbed_video` when available. For shortened dubbed video, compose the full-length dubbed timeline before highlight rendering.

Agent tool arguments are string-only on the wire. Booleans use `true`/`false`; list-like values may use newline-delimited, comma-delimited, or JSON-array strings.

Use `input_collections` for ordered multi-artifact ports and resolve every binding. Do not comma-join collections into `inputs`. Preserve `kind=edit_plan` artifacts and their `highlight_plan_status`, `highlight_plan_revision`, and `target_duration_sec` metadata so approved plans can be rendered without replanning.

A valid local SRT/VTT/ASS passed with one video is marked reusable and linked to that video. When `ffprobe` is available, the CLI rejects reuse if cue starts exceed video duration plus 1.5 seconds or cue ends exceed the dynamic 3-10 second grace window. With multiple subtitles or images, preserve exact ids, language, artifact role, source lineage, `cloud_file_id`, and `public_url` through `--context-json` so the execution DAG binds the intended artifact.

If the runtime reports a subtitle/video source conflict, show the exact subtitle, requested video, and recorded source video, then require explicit pair confirmation through `agent clarify`. Never convert a filename similarity or matching duration into ownership evidence. A retimed subtitle belongs only to its paired edited timeline.

### agent clarify

When `agent run`, `agent poll`, or a waited result returns `status=requires_user_input` with structured `clarifications`, show every localized `question`, non-empty `assistant_hint`, option label, and option description to the user, then continue the original task. Honor `input_kind=single_select|text|file_select|image_select` and never silently select `is_default`:

```bash
cinlink --json agent clarify <run_id> --response <id_or_slot>=<value> --response <id_or_slot>=<value> --wait --include-events
```

Collect every clarification before continuing and send the complete answer set once. `--answers-json` is equivalent to repeated `--response`. The older `--clarification-id` plus `--value`/`--answer` form remains valid for one question. `target_duration_sec` accepts 10-600 seconds, `MM:SS`, `HH:MM:SS`, or localized units. The command carries forward the prior workflow id, canonical `media_intent`, conversation, task frame, context artifacts, app language, and compound execution plan. A `requires_user_input` result without `clarifications` is usually an install/authorization request and must not be sent to this command.

File/image selection clarifications accept an exact option value, stable context id, unique exact context filename, or authorized absolute local path. The continuation validates the required kind, resolves or creates the matching context descriptor, and marks it as the current submission. Ambiguous names or the wrong media kind fail instead of selecting another file.

For `metadata.reply_interpretation=semantic`, the answer remains the continuation prompt and is not asserted as an exact slot. This is required for free-form watermark content that also carries style or placement instructions.

When a clarification has `metadata.clarification_origin=dub_reference_quality`, `agent clarify` sends `merge_primary`, `continue`, or `cancel` to the original run's `/clarification-results` route. It resumes the same run in place and returns `clarification_resolution=in_place`; it does not create a continuation run.

### agent cancel

```bash
cinlink --json agent cancel <run_id>
```

Cancel a queued, running, or local-waiting run when the user asks to stop. A cancelled run returns `status=failed`, public `error.code=cancelled`, and `task_frame.status=cancelled`; do not report a later local result as completion.

Also available: `agent poll`, `agent events`, `agent local-tools`, `agent report-tool-result`. `agent events` reads public planning/reasoning progress over SSE; it never exposes hidden model scratch work. The report command infers artifact kind for `--artifact-path`. Use `--upload-for-cloud-model-input` when reporting `stage_audio`, `stage_image`, or another non-video local tool output explicitly requested as cloud-model input; it uploads through the authenticated account-scoped Agent file endpoint. It refuses full video uploads. Use repeated `--artifact-json` and `--artifact-metadata-json` to preserve per-artifact roles and lineage.

Completed agent results include `completion_message`, `primary_artifacts`, `supporting_artifacts`, and `intermediate_artifacts`. Deliver primary artifacts as the result, preserve citations and any voice-reference quality warning in the completion message, mention supporting artifacts when useful, and do not present intermediate artifacts as final output. `web_query_raw` is supporting-only and never primary. `source_reference_subtitle` and `plan_output_excluded=true` artifacts are internal sidecars.

Every media workflow returns canonical `workflow_decision.media_intent` with `operation`, `source`, `output`, and string-valued `parameters`. Entity bindings are under `source.bindings`; legacy subtitle-specific top-level fields are accepted only as compatibility input.

Agent and direct media results may include `privacy_receipt`, which records whether the source video stayed local, which derived inputs were processed by CinLink Cloud, and whether final rendering happened locally.

## Error Codes

- `auth_failed`: ask for/configure the CinLink API key.
- `invalid_input`: fix file paths or unsupported formats.
- `dependency_missing`: run `doctor`; ask before installing local dependencies.
- `quota_exceeded`: tell the user to check billing/top up.
- `timeout`: report the job/run id if present and suggest polling again.
- `network_error` / `remote_error`: retry or inspect the runtime base.

Failed jobs may include safe `details`: `processing_stage`, `error_type`, `error_code`, `provider`, `http_status`, `request_id`, and `retryable`. Show the public `code`/`message`, retain those details for diagnostics, and automatically retry only when `retryable` is `true`.
