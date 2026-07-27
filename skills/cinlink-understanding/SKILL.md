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
cinlink --json shorten /absolute/video.mp4 --target-duration 45 --max-clips 5 --out /absolute/out
```

The CLI keeps the full video local, uploads extracted audio for hosted analysis, and returns `source_video_path` with the highlight plan and artifact paths when available. Use `/cinlink-editing` to render known timestamp ranges with `trim-video` or combine selected ranges with `montage`; use `/cinlink-agent` when the plan requires broader orchestration.

Optional arguments:

- `--style-preset`
- `--music-mode none`
- `--music-prompt`

## NLU Routing

For ambiguous user wording:

```bash
cinlink --json nlu "<prompt>" --has-video --has-subtitle --context-file /absolute/video.mp4
```

Use the returned action and slots to pick `/cinlink-subtitles`, `/cinlink-dubbing`, `/cinlink-editing`, `/cinlink-generation`, or `/cinlink-agent`.

Return the `privacy_receipt`: the full source video should stay local, while extracted audio may be processed by CinLink Cloud for understanding.
