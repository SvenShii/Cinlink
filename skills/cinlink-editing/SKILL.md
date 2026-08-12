---
name: cinlink-editing
description: CinLink local media enhancement, video editing, and export workflows for agents. Use to enhance images/videos, remove long pauses, trim or montage clips, apply watermarks/Brand Kits, export media, and create editor handoff projects. These workflows are local-only and do not require a CinLink API key.
---

# CinLink Editing

Use this for local edits that do not need a hosted model. Read `/cinlink-cli` first when local dependency status is unknown.

## Image And Video Enhancement

Enhance a local image to a lossless PNG:

```bash
cinlink --json enhance-image /absolute/image.png --model photo --out /absolute/out
```

Supported image inputs are PNG, JPEG, WebP, HEIC, and GIF. HEIC and GIF use the first frame. Models are `photo`, `cunet`, and `anime`; scale is currently `2`, and noise level may be `-1`, `0`, `1`, `2`, or `3`.

Enhance a local video frame by frame while preserving its original audio:

```bash
cinlink --json enhance-video /absolute/video.mp4 --model photo --out /absolute/out
```

Both commands require the verified local `waifu2x-ncnn-vulkan` component and model directories. Video enhancement also requires `ffmpeg`/`ffprobe` and may use substantial time and disk space. Run `cinlink --json doctor`; if unavailable, ask before running `cinlink setup-local-deps --with-enhancement` or direct the user to install the CinLink app-managed enhancement bundle.

## Clean Cut

Remove long pauses while retaining a short natural pause at each edge:

```bash
cinlink --json clean-cut /absolute/video.mp4 --out /absolute/out
```

Defaults match the CinLink app workflow:

- minimum silence: `0.75` seconds
- noise threshold: `-35` dB
- retained pause: `0.24` seconds total
- minimum removal: `0.18` seconds

Override only when the user asks:

```bash
cinlink --json clean-cut /absolute/video.mp4 --minimum-silence 1.0 --retained-pause 0.3 --out /absolute/out
```

When `changed` is false, tell the user no qualifying pauses were found and do not claim a new video was created.

## Precise Clip

Cut a known range, including a matched range returned by video understanding or library search:

```bash
cinlink --json trim-video /absolute/video.mp4 --start 12.4 --end 18.8 --out /absolute/out
```

Use exact seconds from the matched result. Preserve a little surrounding context only when the user requests it or when the matching workflow explicitly supplies padded timestamps.

## Montage

Combine at least two selected ranges in the given order:

```bash
cinlink --json montage --clips-json '[{"path":"/absolute/a.mp4","start_sec":2.0,"end_sec":5.5},{"path":"/absolute/b.mp4","start_sec":8.0,"end_sec":11.0}]' --out /absolute/out
```

Do not silently reorder clips. Return `video_output_path`, `clip_count`, and the rendered duration.

## Brand Kit

Show the saved Brand Kit:

```bash
cinlink --json brand-kit show
```

Configure and enable it:

```bash
cinlink --json brand-kit set --enable --font-name Arial --font-color '#FFFFFF' --outline-color '#000000' --watermark-image /absolute/logo.png
```

The Brand Kit is stored in the user-level CinLink CLI config, not in `.env` or the skill directory. Enabled settings automatically apply to later `add-subtitles`, `burn`, and `apply-watermark` calls. Explicit per-command values override the saved kit.

Disable or clear it:

```bash
cinlink --json brand-kit set --disable
cinlink --json brand-kit clear
```

## Watermark Export

Apply the enabled Brand Kit:

```bash
cinlink --json apply-watermark /absolute/video.mp4 --out /absolute/out
```

Apply a one-off watermark while ignoring the saved kit:

```bash
cinlink --json apply-watermark /absolute/video.mp4 --watermark-text "Example" --watermark-position top-right --no-brand-kit --out /absolute/out
```

Image and text watermarks can be combined. Use absolute paths for local logo files.

## Video And Audio Export

Export a local video as MP4, MOV, AVI, or MKV:

```bash
cinlink --json export-video /absolute/video.mp4 --format mov --out /absolute/export
```

Export the video's audio as WAV or MP3:

```bash
cinlink --json export-audio /absolute/video.mp4 --format mp3 --out /absolute/export
```

When the workflow already produced a replacement/mixed audio track, pass it explicitly:

```bash
cinlink --json export-audio /absolute/video.mp4 --audio-source /absolute/mixed.wav --format wav --out /absolute/export
```

## Editor Project Handoff

Create local import assets for an editor:

```bash
cinlink --json export-editor-project /absolute/video.mp4 \
  --target final-cut \
  --subtitle /absolute/subtitles.srt \
  --audio-source /absolute/mixed.wav \
  --out /absolute/editor-handoff
```

Targets:

- `final-cut`: Final Cut Pro FCPXML
- `premiere`: Adobe Premiere Pro-compatible XML
- `resolve`: DaVinci Resolve-compatible XML
- `capcut`: portable folder with media, optional audio/SRT, and `timeline.json`

CinLink creates handoff assets but does not launch or control desktop editor applications. CapCut does not accept third-party project files, so import the media and optional SRT/audio from the returned package.

## Rules

- These tools are local-only: no CinLink API key or hosted upload is required.
- Local `ffmpeg` and `ffprobe` are required for video work. Enhancement additionally requires the local waifu2x model bundle. Run `cinlink --json doctor` and ask before installing missing dependencies.
- Return the typed artifact metadata and privacy receipt. The source video should report `stayed_local` and hosted inputs should be empty.
- For editor handoff, present `primary_artifacts` as the project file/package manifest and `supporting_artifacts` as optional media, audio, or subtitle companions.
- Use `/cinlink-subtitles` when the task also needs transcription or translation.
- Use `/cinlink-understanding` first when clip timestamps must be discovered from media content.
- Use `/cinlink-deconstruction` when the user wants visual shot analysis or hosted shot regeneration rather than a local edit/export.
