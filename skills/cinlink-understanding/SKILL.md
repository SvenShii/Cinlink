---
name: cinlink-understanding
description: CinLink video-understanding workflows for agents. Use to summarize video/audio/subtitle content, extract highlights, generate a clip plan, shorten long videos into short-form plans, or ask CinLink NLU to route a natural-language media request.
---

# CinLink Understanding

Use this for analysis and planning of existing media.

## Summarize

```bash
cinlink --json summarize /absolute/video.mp4 --max-highlights 5 --out /absolute/out
```

For video input, the CLI extracts audio locally with `ffmpeg` and uploads only the audio. Return the summary, highlights, `source_video_path`, and artifact paths.

## Shorten

```bash
cinlink --json shorten /absolute/video.mp4 --target-duration 45 --max-clips 5 --output-language zh-Hans --out /absolute/out
```

Set `--output-language` to the user's conversation/UI language: `zh-Hans`, `en`, or `ja`. It controls generated clip titles, reasons, and plan presentation. The CLI keeps the full video local, uploads extracted audio through the account-scoped Agent file endpoint, and reuses the returned `cloud_file_id` for shortening when the runtime supports it. Older runtimes receive the same audio through compatibility multipart upload. The result preserves `source_video_path`, `output_language`, the highlight plan, and artifact paths when available.

Show the proposed clips and localized reasons before rendering. Ask the user to confirm, request a replan, or cancel. Do not render highlights from a default or merely proposed plan without explicit confirmation. A replan must preserve the requested `output_language`; cancel keeps the current edit plan and subtitle context available without producing a video. After confirmation, preserve `highlight_plan_revision`, `highlight_plan_status`, and `output_language` when handing the plan to `/cinlink-editing` or a `/cinlink-agent` `render_highlight_clips` call.

When the user already has a valid timed subtitle, pass both video and subtitle through `/cinlink-agent`; the CLI marks a single SRT/VTT/ASS reusable and binds it to the source video, avoiding unnecessary transcription. With several subtitles, preserve `artifact_role`, `target_language`, and source-video lineage in `--context-json` so the runtime can select the intended language.

For a short video that also needs translated voice, complete the full-length dubbing timeline first and shorten the composed dubbed video afterward.

Optional arguments:

- `--style-preset`
- `--music-mode none`
- `--music-prompt`
- `--output-language zh-Hans|en|ja`

## NLU Routing

For ambiguous user wording:

```bash
cinlink --json nlu "<prompt>" --has-video --has-subtitle --context-file /absolute/video.mp4
```

Use the returned action and slots to pick `/cinlink-subtitles`, `/cinlink-dubbing`, `/cinlink-editing`, `/cinlink-generation`, or `/cinlink-agent`.

Return the `privacy_receipt`: the full source video should stay local, while extracted audio may be processed by CinLink Cloud for understanding.
