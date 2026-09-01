---
name: cinlink-subtitles
description: CinLink subtitle workflows for agents. Use to transcribe video/audio into subtitles, translate subtitle or media files, produce bilingual subtitles, and burn styled subtitles/watermarks into local videos. Uses the CinLink hosted runtime for transcribe/translate and local ffmpeg for burn.
---

# CinLink Subtitles

Use this for caption/subtitle tasks. Read `/cinlink-cli` first if the CLI is not installed or the API key status is unknown.

## Workflows

### Add Subtitles To Video

For app-like "add subtitles" requests, use the composite workflow first:

```bash
cinlink --json add-subtitles /absolute/video.mp4 --source-lang auto --out /absolute/out
```

This matches the app flow: hosted transcribe creates a subtitle file, then local ffmpeg burns the subtitle into the video. If the user asks for translated subtitles, include `--target-lang`:

```bash
cinlink --json add-subtitles /absolute/video.mp4 --source-lang auto --target-lang en --out /absolute/out
```

If the user already provided a subtitle file, pass it instead of transcribing:

```bash
cinlink --json add-subtitles /absolute/video.mp4 --subtitle /absolute/subtitles.srt --out /absolute/out
```

Return both `video_output_path` and `subtitle_path` to the user.

### Transcribe

```bash
cinlink --json transcribe /absolute/video.mp4 --lang auto --out /absolute/out
```

Return `subtitle_path` and `preview_text` to the user.

### Translate

```bash
cinlink --json translate /absolute/input.srt --from auto --to en --bilingual --delivery subtitle --out /absolute/out
```

For a media file, CinLink may transcribe before translating. When the input is a video, the CLI keeps the full video local, extracts audio with `ffmpeg`, and uploads only that audio to the hosted runtime.

### Burn Subtitles

```bash
cinlink --json burn /absolute/video.mp4 --subtitle /absolute/subtitles.srt --font-size 22 --position bottom --out /absolute/out
```

Burn is local-only and requires `ffmpeg`. Optional styling includes font name, colors, outline, margin, text watermark, and image watermark. If `dependency_missing`, run `/cinlink-cli` doctor and ask before installing local dependencies.

Enabled Brand Kit settings are applied automatically to `add-subtitles` and `burn`. Explicit flags override the saved values. Use `--no-brand-kit` only when the user asks for a one-off export that must ignore their saved brand:

```bash
cinlink --json brand-kit show
cinlink --json burn /absolute/video.mp4 --subtitle /absolute/subtitles.srt --no-brand-kit --out /absolute/out
```

## Rules

- Use absolute paths for local files.
- For "给视频加字幕", "加个字幕", "add captions/subtitles", or similar app-like requests, prefer `add-subtitles` over manually calling `transcribe` then `burn`.
- Do not require a CinLink API key for burn-only tasks.
- Ask for/configure the API key for hosted transcribe/translate/add-subtitles tasks.
- Expect local `ffmpeg` for every hosted workflow that starts from a video, because the current runtime accepts extracted audio rather than a full video upload.
- For translated voice output, switch to `/cinlink-dubbing`.
- When a response contains multiple subtitle artifacts, choose `artifact_role=translated_subtitle` for translated output, `edited_subtitle` for shortened/edited output, and `source_subtitle` only when the original-language subtitle is requested. Do not select the first `.srt` blindly.
- Before reusing a subtitle with an Agent video context, honor `subtitle_reuse_eligible=false` and `subtitle_timeline_mismatch=true`. The CLI rejects cues whose starts exceed video duration by more than 1.5 seconds or whose ends exceed the dynamic 3-10 second grace window.
- Reuse requires stable source lineage, not just a matching filename or duration. Preserve full `id`, `entity_id`, `file_version`, `subtitle_source_video_*`, and `subtitle_timeline_*` metadata. If the runtime asks to confirm a conflicting subtitle/video pair, show the exact files and wait for explicit approval.
- Never burn an original-timeline subtitle into a trimmed/highlight video. Use the paired retimed subtitle produced for that edited video.
- Return the `privacy_receipt`: for video input, the source video stays local while extracted audio may be processed by CinLink Cloud; final subtitle burn remains local.
