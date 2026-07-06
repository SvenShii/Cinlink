---
name: cinlink
description: READ THIS FIRST for any request to use CinLink media capabilities from an agent: transcribe videos, generate subtitles, translate subtitles or media, dub/voice-translate videos, burn subtitles, mix dubbed audio, summarize video, shorten long videos into highlight plans, generate AI images/videos, route natural-language media tasks, or run hosted CinLink agent workflows. Router and capability map for the CinLink domain skills. Hosted capabilities require a user-provided CinLink API key.
---

# CinLink — Start Here

CinLink exposes the app's media workflows to coding agents through the standalone `cinlink` CLI plus focused skills. Use this router before choosing a concrete workflow.

## Capability Map

| You want to... | Skill |
| --- | --- |
| Install/configure the CLI, store an API key, check runtime/local dependencies, inspect tool schemas | `/cinlink-cli` |
| Add subtitles to a video, transcribe media, translate subtitles/media, burn styled subtitles into a local video | `/cinlink-subtitles` |
| Voice-translate/dub videos, generate dubbed audio, mix dubbed audio with the original video | `/cinlink-dubbing` |
| Summarize videos, extract highlights, plan short clips from long videos | `/cinlink-understanding` |
| Generate AI images or AI videos through the hosted runtime | `/cinlink-generation` |
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

### Dubbing Workflows

Route to `/cinlink-dubbing` for:

- "dub this video into Japanese"
- "voice translate this video"
- "make dubbed audio from this translated SRT"
- "mix this dubbed WAV back into the video"
- "preserve background music" or "separate vocals" (requires local dependency approval)

### Understanding Workflows

Route to `/cinlink-understanding` for:

- "summarize this video"
- "find the highlights"
- "make a 60 second cutdown plan"
- "turn this long video into short clips"

### Generation Workflows

Route to `/cinlink-generation` for:

- "generate an image"
- "generate a video"
- "use this reference image/video/audio URL"
- "make a Seedance-style video" or other hosted provider generation request

## API Key Rule

Hosted capabilities use the user's CinLink API key. Before the first hosted call, read `/cinlink-cli` and configure one of:

- `cinlink --json onboarding --api-key <key>`
- `CINLINK_API_KEY=<key>`

Never echo the API key back to the user. For local-only tasks such as subtitle burn or audio mixing, an API key is not required, but local `ffmpeg` may be.

## Dependency Rule

CinLink is hosted-first. Provider credentials stay on the server. Local dependencies are only for local capabilities:

- `ffmpeg`: subtitle burn, audio mix, local media probing
- `demucs` + `soundfile`: local voice separation/background preservation

Do not install local dependencies silently. Ask the user first.
