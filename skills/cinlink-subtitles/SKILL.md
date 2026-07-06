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

For a media file, CinLink may transcribe before translating.

### Burn Subtitles

```bash
cinlink --json burn /absolute/video.mp4 --subtitle /absolute/subtitles.srt --font-size 22 --position bottom --out /absolute/out
```

Burn is local-only and requires `ffmpeg`. Optional styling includes font name, colors, outline, margin, text watermark, and image watermark. If `dependency_missing`, run `/cinlink-cli` doctor and ask before installing local dependencies.

## Rules

- Use absolute paths for local files.
- For "给视频加字幕", "加个字幕", "add captions/subtitles", or similar app-like requests, prefer `add-subtitles` over manually calling `transcribe` then `burn`.
- Do not require a CinLink API key for burn-only tasks.
- Ask for/configure the API key for hosted transcribe/translate/add-subtitles tasks.
- For translated voice output, switch to `/cinlink-dubbing`.
