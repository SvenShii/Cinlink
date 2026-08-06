---
name: cinlink-generation
description: CinLink hosted AI generation workflows for agents. Use to generate AI images or AI videos from prompts, aspect ratios, durations, models, local reference images, and remote reference image/video/audio URLs. Requires a configured CinLink API key.
---

# CinLink Generation

Use this for hosted image and video generation.

## Image

```bash
cinlink --json image "a clean product poster" --aspect-ratio 1:1 --image-size 1K --out /absolute/out
```

Generate from up to three reference images:

```bash
cinlink --json image "restyle this product as a clean studio poster" \
  --reference-image-url /absolute/product.png \
  --reference-image-url https://example.com/style.jpg \
  --out /absolute/out
```

Optional: repeated `--reference-image-url`, `--model`, and `--timeout`. Local references are uploaded through CinLink's authenticated reference-image endpoint. The command waits for the hosted job and downloads the completed image.

## Video

```bash
cinlink --json video "a 5 second cinematic product reveal" --aspect-ratio 16:9 --duration 5 --out /absolute/out
```

Optional:

- `--resolution 720P`
- `--no-audio`
- `--watermark`
- `--generation-mode text|first_frame|reference`
- `--first-frame-image-url <url-or-local-path>`
- repeated `--reference-image-url <url-or-local-path>` (up to nine)
- repeated `--reference-video-url <url>`
- repeated `--reference-audio-url <url>`
- `--model`, `--model-name`, `--model-version`

Local first-frame/reference images are uploaded through CinLink's authenticated reference-image endpoint. When references are present and `--generation-mode` is omitted, the CLI selects `first_frame` for only a first frame or `reference` for a reference set; otherwise it selects `text`. Generated videos are normalized by the hosted runtime to the requested aspect ratio and resolution.

For follow-up generation through `/cinlink-agent`, preserve the returned artifact identity instead of reducing it to a local path:

```bash
cinlink --json agent run "Animate this image." --app-language en --context-json '{"name":"generated.png","kind":"image","public_url":"https://...","cloud_file_id":"...","metadata":{"artifact_role":"generated_image","producer_step":"generate_image"}}' --task-intent generate_video --wait
```

## Rules

- Use hosted generation only after API key setup via `/cinlink-cli`.
- Local image paths are supported for first-frame and reference-image inputs. Reference video/audio inputs remain remote URLs.
- When several image artifacts are present, preserve and pass the exact selected artifact `id`, `cloud_file_id`, and `public_url`; do not let an unrelated URL override the explicitly bound image. If the selected reference cannot be resolved to an authorized public URL, stop and ask for that image again instead of substituting an older context image.
- Use `/cinlink-deconstruction` when the task starts from an existing video's shots or needs person/product/scene replacement with cross-shot continuity.
- Reuse returned `public_url`, `cloud_file_id`, `artifact_role`, and `producer_step` in follow-up context so the runtime can preserve generated-media lineage.
- On `content_ip_violation`, do not retry the same request. Ask for an original character description or a different reference image.
- Return generated artifact paths/URLs and any job id in the final response.
