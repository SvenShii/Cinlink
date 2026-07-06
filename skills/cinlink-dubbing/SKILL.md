---
name: cinlink-dubbing
description: CinLink dubbing and voice-translation workflows for agents. Use to create voice-translated outputs, generate dubbed speech/audio from a video plus subtitle file, run translate with voice delivery, mix dubbed audio into a local video, or handle user requests about vocal separation/background-music preservation.
---

# CinLink Dubbing

Use this for voice translation and dubbing. Hosted dubbing uses the user's CinLink API key; local mixing uses `ffmpeg`.

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

Optional: `--voice`, `--reference-subtitle`, `--timeout`.

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
