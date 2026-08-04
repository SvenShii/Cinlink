---
name: cinlink-deconstruction
description: CinLink video deconstruction and reference-replacement workflows for agents. Use to split a local video into an editable shot plan, inspect or revise its prompts, replace a person/product/scene with reference images, and regenerate the plan shot by shot with continuity. Requires ffmpeg/ffprobe and a configured CinLink API key.
---

# CinLink Deconstruction

Use this when the user wants to understand a video's visual construction, edit the generated shot plan, replace visual subjects, or recreate the video shot by shot.

## Deconstruct

```bash
cinlink --json deconstruct-video /absolute/video.mp4 --out /absolute/deconstruction
```

CinLink detects cuts and extracts representative frames locally, then sends only sampled frames to the hosted deconstruction runtime. The source video remains local. The result includes an editable `deconstruction.json`.

Choose the language for human-readable analysis and optionally focus the analysis:

```bash
cinlink --json deconstruct-video /absolute/video.mp4 \
  --language en \
  --analysis-scope "camera movement, product presentation, lighting, and transitions" \
  --out /absolute/deconstruction
```

`--language` controls titles, summaries, style analysis, and the audio prompt. Generation and negative prompts remain concise model-friendly English.

Optional controls:

```bash
cinlink --json deconstruct-video /absolute/video.mp4 \
  --scene-threshold 0.28 \
  --max-shots 120 \
  --replacement-reference person=/absolute/person.png \
  --replacement-reference product=/absolute/product.png \
  --out /absolute/deconstruction
```

Replacement roles are `person`, `product`, and `scene`, with at most eight replacement images. Paths must be local image files.

## Review Or Edit

Before regeneration, inspect the plan's `global_prompt` and per-shot `prompt`, `camera`, `action`, `composition`, `lighting`, and `continues_previous` fields. Preserve shot order and timing unless the user explicitly requests structural changes.

Do not delete `source_path`, `workspace_path`, `reference_frame_paths`, or shot indexes. Those fields preserve continuity and local assembly.

## Regenerate

```bash
cinlink --json regenerate-deconstruction /absolute/deconstruction/deconstruction.json \
  --resolution 720P \
  --out /absolute/output
```

Add or override replacement references during regeneration:

```bash
cinlink --json regenerate-deconstruction /absolute/deconstruction/deconstruction.json \
  --replacement-reference person=/absolute/new-person.png \
  --replacement-reference scene=/absolute/new-location.png \
  --out /absolute/output
```

The CLI generates shots sequentially. It uses each generated tail frame as continuity input for the next connected shot, then assembles the final video locally. Original source audio is preserved by default; pass `--no-original-audio` only when requested.

## Rules

- Read `/cinlink-cli` first. Hosted deconstruction/generation requires the user's CinLink API key; local probing and assembly require `ffmpeg`/`ffprobe`.
- Use the direct command for a complete editable multi-shot plan. A broad `/cinlink-agent` run may use its server-side `deconstruct_video` node for one explicitly bound extracted frame, but that is not a replacement for local scene detection and multi-shot sampling.
- Never upload the full source video for deconstruction. Only sampled frames and explicit replacement references go to CinLink Cloud.
- Local reference images are uploaded through the authenticated CinLink reference-image endpoint.
- Return `plan_path` after deconstruction. After regeneration, return only `primary_artifacts` as the main result and mention the plan under `supporting_artifacts`.
- Use `/cinlink-generation` for a new prompt-only video. Use `/cinlink-editing` for local trim, montage, export, or editor handoff without visual regeneration.
