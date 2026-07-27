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

When reference URLs are present and `--generation-mode` is omitted, the CLI selects `reference`; otherwise it selects `text`.

For follow-up generation through `/cinlink-agent`, preserve the returned artifact identity instead of reducing it to a local path:

```bash
cinlink --json agent run "Animate this image." --app-language en --context-json '{"name":"generated.png","kind":"image","public_url":"https://...","cloud_file_id":"...","metadata":{"artifact_role":"generated_image","producer_step":"generate_image"}}' --task-intent generate_video --wait
```

## Rules

- Use hosted generation only after API key setup via `/cinlink-cli`.
- Reference inputs are remote URLs, not local paths, unless the hosted agent runtime has uploaded/presigned them.
- Reuse returned `public_url`, `cloud_file_id`, `artifact_role`, and `producer_step` in follow-up context so the runtime can preserve generated-media lineage.
- Return generated artifact paths/URLs and any job id in the final response.
