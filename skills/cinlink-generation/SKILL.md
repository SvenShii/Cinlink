---
name: cinlink-generation
description: CinLink hosted AI generation workflows for agents. Use to generate AI images or AI videos from prompts, aspect ratios, durations, models, and remote reference image/video/audio URLs. Requires a configured CinLink API key.
---

# CinLink Generation

Use this for hosted image and video generation.

## Image

```bash
cinlink --json image "a clean product poster" --aspect-ratio 1:1 --image-size 1K --out /absolute/out
```

Optional: `--model`.

## Video

```bash
cinlink --json video "a 5 second cinematic product reveal" --aspect-ratio 16:9 --duration 5 --out /absolute/out
```

Optional:

- `--resolution 720P`
- `--no-audio`
- `--watermark`
- `--generation-mode text|first_frame|reference`
- `--first-frame-image-url <url>`
- repeated `--reference-image-url <url>`
- repeated `--reference-video-url <url>`
- repeated `--reference-audio-url <url>`
- `--model`, `--model-name`, `--model-version`

## Rules

- Use hosted generation only after API key setup via `/cinlink-cli`.
- Reference inputs are remote URLs, not local paths, unless the hosted agent runtime has uploaded/presigned them.
- Return generated artifact paths/URLs and any job id in the final response.
