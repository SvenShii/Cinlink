---
name: cinlink-dubbing
description: CinLink dubbing and voice-translation workflows for agents. Use to create voice-translated outputs, generate dubbed speech/audio from a video plus subtitle file, run translate with voice delivery, mix dubbed audio into a local video, or handle user requests about vocal separation/background-music preservation.
---

# CinLink Dubbing

Use this for voice translation and dubbing. Hosted dubbing uses the user's CinLink API key; local extraction/mixing uses `ffmpeg`.

Important: the hosted `/v1/dub` runtime now accepts reference audio plus subtitles, not video uploads. The `cinlink dub` CLI still accepts a video path for convenience, but it first extracts audio locally with `ffmpeg` and uploads that audio to the hosted runtime.

## Voice Translation

For "translate this video with voice" from a media/subtitle input:

```bash
cinlink --json translate /absolute/video.mp4 --to en --delivery voice --out /absolute/out
```

## Dub From Existing Subtitle

For "dub this video using this SRT":

```bash
cinlink --json dub /absolute/video.mp4 --subtitle /absolute/translated.srt --lang en --out /absolute/out
```

Optional: `--voice`, `--reference-subtitle`, repeated `--reference-audio speaker_id=/absolute/ref.wav`, `--timeout`.

Use `--reference-subtitle` when the source subtitle carries speaker/timing information. Use `--reference-audio speaker_0=/absolute/ref.wav` or additional speaker ids when the user provides speaker-specific voice references.

For a complete dubbed MP4, generate dubbed audio first and then run `mix-dubbed-audio`, or route the broad request through `/cinlink-agent` so the hosted agent can plan `synthesize_dub_audio` followed by local `compose_dubbed_video` when that app-local capability is available.

When selecting outputs for the next step, prefer `artifact_role=dubbed_audio` for local composition and `artifact_role=dubbed_video` for a completed video. Preserve `producer_step` when reporting local results.

For a request that both shortens and dubs a video, preserve the original timeline through synthesis: extract/transcribe/translate/synthesize the full-length source, compose the full-length dubbed video, then render the selected highlight clips. Do not mix full-length dubbed audio into an already-shortened video.

## Mix Dubbed Audio

For "mix this dubbed audio back into the video":

```bash
cinlink --json mix-dubbed-audio /absolute/video.mp4 --dubbed-audio /absolute/dubbed.wav --out /absolute/out
```

This mixes the original audio track with dubbed audio. It does not separate vocals.

## Background Preservation

If the user asks for true vocal removal, voice separation, instrumental/accompaniment extraction, or preserving background music through separated stems, explain that it is local-only. It requires:

- `ffmpeg`
- `demucs`
- `soundfile`

Run `cinlink --json doctor` to check status. Do not install dependencies without explicit user approval.

Return the `privacy_receipt`: the source video remains local, extracted/reference audio and subtitles may be processed by CinLink Cloud, and final video composition runs locally.
