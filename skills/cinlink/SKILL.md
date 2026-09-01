---
name: cinlink
description: "READ THIS FIRST for any request to use CinLink media capabilities from an agent: transcribe videos, generate/translate/burn subtitles, dub videos, summarize or shorten media, deconstruct or recreate videos, replace visual references, enhance/edit/export media, generate AI images/videos, or run hosted CinLink agent workflows. Router and capability map for the CinLink domain skills. Hosted capabilities require a user-provided CinLink API key; local enhancement/editing/export does not."
---

# CinLink — Start Here

CinLink exposes the app's media workflows to coding agents through the standalone `cinlink` CLI plus focused skills. Use this router before choosing a concrete workflow.

## Capability Map

| You want to... | Skill |
| --- | --- |
| Install/configure the CLI, store an API key, check runtime/local dependencies, inspect tool schemas | `/cinlink-cli` |
| Add subtitles to a video, transcribe media, translate subtitles/media, burn styled subtitles into a local video | `/cinlink-subtitles` |
| Enhance images/videos, remove pauses, trim or montage clips, apply watermarks/Brand Kits, export media/editor projects | `/cinlink-editing` |
| Voice-translate/dub videos, generate dubbed audio, mix dubbed audio with the original video | `/cinlink-dubbing` |
| Summarize videos, extract highlights, plan short clips from long videos | `/cinlink-understanding` |
| Generate AI images or AI videos through the hosted runtime | `/cinlink-generation` |
| Deconstruct a video, edit its shot plan, replace a person/product/scene, regenerate with continuity | `/cinlink-deconstruction` |
| Submit broad natural-language media tasks to the hosted CinLink agent runtime | `/cinlink-agent` |

## Intent Routing

Use direct domain skills when the user asks for a specific operation. Use `/cinlink-agent` when the request is multi-step or loosely specified, such as "turn this video into a 45 second ad, add subtitles, generate a cover, and summarize the selling points."

### Subtitle Workflows

Route to `/cinlink-subtitles` for:

- "transcribe this video"
- "make captions/subtitles"
- "add subtitles to this video" or "给这个视频加字幕"
- "translate this SRT to English"
- "burn these subtitles into the MP4"
- "add a watermark while exporting subtitles"

For app-like "add subtitles" requests, `/cinlink-subtitles` should use `cinlink --json add-subtitles` instead of manually composing `transcribe` and `burn`.

For free-form video translation, use `/cinlink-agent` when `translation_mode` or the subtitle `output_delivery` is unresolved. Ask subtitles versus dubbing first; for subtitle mode, ask subtitle file versus burned video next. Do not execute a model-default choice.

For video transcription or translation, the current CLI keeps the full video local and uploads only audio extracted with local `ffmpeg`.

### Dubbing Workflows

Route to `/cinlink-dubbing` for:

- "dub this video into Japanese"
- "voice translate this video"
- "make dubbed audio from this translated SRT"
- "mix this dubbed WAV back into the video"
- "preserve background music" or "separate vocals" (requires local dependency approval)

For hosted dubbing, never upload a local video directly to `/v1/dub`; the current CLI extracts local audio first, then sends audio plus subtitles. Use `/cinlink-agent` for full app-style split dubbing plans that may need `synthesize_dub_audio` and local `compose_dubbed_video`.

When shortening and dubbing are combined, finish the full-length dubbed timeline first, then render highlights from the dubbed video.

### Understanding Workflows

Route to `/cinlink-understanding` for:

- "summarize this video"
- "find the highlights"
- "make a 60 second cutdown plan"
- "turn this long video into short clips"

For video summary and shortening, the current CLI also keeps the full video local, uploads extracted audio for hosted analysis, and preserves the local video path for rendering.

Local files passed to an Agent run are marked as the current submission, receive highest input priority, and carry stable path/content identity plus file-version evidence. Multiple current files remain ambiguous and may still require clarification; preserve complete ids rather than relying on filenames.

Agent results use canonical `workflow_decision.media_intent` (`operation`, `source`, `output`, `parameters`). Present server-localized structured clarifications according to `input_kind`; `file_select` and `image_select` require the user's exact authorized file. See `/cinlink-agent` for continuation and same-run clarification rules.

When the user asks to stop an active hosted task, route to `/cinlink-agent` and run `cinlink --json agent cancel <run_id>`.

### Local Editing Workflows

Route to `/cinlink-editing` for:

- "enhance/upscale this image or video"
- "remove the long pauses" or "Clean Cut" (review indexed candidates before export)
- "cut 12.4 to 18.8 seconds"
- "combine these selected ranges into a montage"
- "apply my logo/Brand Kit"
- "add a local text or image watermark without subtitles"
- "export this as MOV/AVI/MKV or WAV/MP3"
- "make a CapCut/Premiere/Final Cut/Resolve project handoff"

These operations are local-only and do not need an API key. Video operations require local `ffmpeg`/`ffprobe`; enhancement also requires the verified waifu2x binary and model directories. Enabled Brand Kit settings automatically apply to later subtitle and watermark exports.

### Deconstruction Workflows

Route to `/cinlink-deconstruction` for:

- "deconstruct this video's shots"
- "show me the prompts/camera/action for each shot"
- "replace the person, product, or scene in this video"
- "recreate this video while preserving shot continuity"

Deconstruction keeps the source video local and uploads only sampled frames. Shot regeneration is hosted, while continuity extraction and final assembly are local. Pass `--language` for human-readable analysis language and `--analysis-scope` when the user wants attention on camera, products, lighting, or another visual dimension.

### Generation Workflows

Route to `/cinlink-generation` for:

- "generate an image"
- "generate a video"
- "use this local reference image or reference image/video/audio URL"
- "make a Seedance-style video" or other hosted provider generation request

Image generation accepts up to three reference images; video generation accepts up to nine. Preserve exact artifact identity when the user selects one result among several.

## API Key Rule

Hosted capabilities use the user's CinLink API key. First-time installs should read repo-root `install.md` when available, ask for the key up front if missing, and run `cinlink --json onboarding --api-key <key>`. During normal use, before the first hosted call, read `/cinlink-cli` and verify `cinlink --json doctor`.

Supported credential sources:

- `cinlink --json onboarding --api-key <key>`
- `CINLINK_API_KEY=<key>`

Never echo the API key back to the user. For local-only tasks such as subtitle burn or audio mixing, an API key is not required, but local `ffmpeg` may be.

## Dependency Rule

CinLink is hosted-first. Provider credentials stay on the server. Local dependencies are only for local capabilities:

- `ffmpeg`/`ffprobe`: subtitle burn, local audio extraction/mix, Clean Cut, trimming, montage, watermarking, video deconstruction/assembly, media export, editor project handoff, local media probing
- `demucs` + `soundfile`: local voice separation/background preservation
- `waifu2x-ncnn-vulkan` + photo/cunet/anime model directories: local image/video enhancement

During install or reconnect, run `cinlink setup-local-deps` so the user is prompted to install local `ffmpeg` and offered optional voice-separation/enhancement components. In non-interactive contexts, show `cinlink --json setup-local-deps --dry-run --with-voice-separation --with-enhancement` first, then install only after explicit confirmation.

Do not install local dependencies silently. Ask the user first.
