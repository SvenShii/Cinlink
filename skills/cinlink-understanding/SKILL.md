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

Return the summary, highlights, and artifact paths.

## Shorten

```bash
cinlink --json shorten /absolute/video.mp4 --target-duration 45 --max-clips 5 --out /absolute/out
```

The hosted runtime returns a highlight plan and artifact paths when available. Rendering the final cut may require local video tools or the hosted agent workflow.

Optional arguments:

- `--style-preset`
- `--music-mode none`
- `--music-prompt`

## NLU Routing

For ambiguous user wording:

```bash
cinlink --json nlu "<prompt>" --has-video --has-subtitle --context-file /absolute/video.mp4
```

Use the returned action and slots to pick `/cinlink-subtitles`, `/cinlink-dubbing`, `/cinlink-generation`, or `/cinlink-agent`.
