# CinLink Tool Contract

All commands should use `--json`. Successful and failed calls print one JSON object. Hosted tools require a configured CinLink API key.

## CLI Commands

### onboarding

```bash
cinlink --json onboarding --api-key <key> [--runtime-base <url>] [--billing-base <url>]
```

Stores config in the user-level CinLink CLI config file.

### doctor

```bash
cinlink --json doctor
```

Reports API-key presence, runtime health, and local dependency status.

### setup-local-deps

```bash
cinlink setup-local-deps
cinlink --json setup-local-deps --dry-run --with-voice-separation
cinlink setup-local-deps --yes
```

Prompts the user to install local dependencies. `ffmpeg` is recommended for subtitle burn-in, local audio extraction/mixing, and local media inspection. `demucs` plus `soundfile` are optional and are only needed for local voice separation/background preservation. Do not run with `--yes` until the user has confirmed.

### transcribe

```bash
cinlink --json transcribe <input_path> --lang auto --out <dir> --timeout 1800
```

Output usually includes `subtitle_path`, `preview_text`, `engine`, and job status fields.

### translate

```bash
cinlink --json translate <input_path> --from auto --to en --bilingual --delivery subtitle --out <dir>
```

`input_path` may be a subtitle or media file. `delivery` is `subtitle` or `voice`.

### add-subtitles

```bash
cinlink --json add-subtitles <video_path> --source-lang auto --target-lang en --out <dir>
```

App-parity composite workflow. If `--subtitle <path>` is provided, it burns that subtitle. Otherwise it uses hosted transcribe, or hosted translate when `--target-lang` is set, then burns the resulting subtitle locally. Supports the same subtitle style and watermark args as `burn`.

### dub

```bash
cinlink --json dub <video_path> --subtitle <subtitle_path> --lang en --voice <voice> --out <dir>
```

Generates dubbed speech/audio for a video using an existing subtitle file. Optional: `--reference-subtitle`, `--timeout`.

### burn

```bash
cinlink --json burn <video_path> --subtitle <subtitle_path> --font-size 22 --position bottom --out <dir>
```

Local-only. Supports `--font-name`, `--font-color`, `--outline-color`, `--outline-width`, `--margin-v`, text watermark args, and image watermark args.

### mix-dubbed-audio

```bash
cinlink --json mix-dubbed-audio <video_path> --dubbed-audio <audio_path> --original-volume 0.65 --dubbed-volume 1.0
```

Local-only. Mixes original audio with dubbed audio and muxes the result into a video.

### summarize

```bash
cinlink --json summarize <input_path> --max-highlights 3 --out <dir>
```

Returns summary text, highlights, and artifact paths when available.

### shorten

```bash
cinlink --json shorten <video_path> --target-duration 45 --max-clips 5 --out <dir>
```

Optional: `--style-preset`, `--music-mode`, `--music-prompt`.

### image

```bash
cinlink --json image "<prompt>" --aspect-ratio 1:1 --image-size 1K --out <dir>
```

Optional: `--model`.

### video

```bash
cinlink --json video "<prompt>" --aspect-ratio 16:9 --duration 5 --out <dir>
```

Optional: `--resolution`, `--no-audio`, `--watermark`, `--generation-mode`, `--first-frame-image-url`, repeated `--reference-image-url`, repeated `--reference-video-url`, repeated `--reference-audio-url`, `--model`, `--model-name`, `--model-version`, `--timeout`.

### nlu

```bash
cinlink --json nlu "<prompt>" --has-video --context-file <path>
```

Routes a natural-language media task into an action and slots.

### agent run

```bash
cinlink --json agent run "<prompt>" --context-file <path> --mode execute --wait
```

Use for broad, multi-step media workflows. When the app surface action is known, pass it explicitly:

```bash
cinlink --json agent run "Add English subtitles and return the subtitled video." --context-file <path> --task-intent add_subtitles --task-param output_delivery=burned_video --task-param target_language=en --mode execute --wait
```

Use repeated `--task-param KEY=VALUE` or `--task-parameters-json '{"key":"value"}' for explicit slots such as `output_delivery`, `target_language`, `source_language`, `subtitle_language`, and `translation_mode`. Current prompt language and task parameters override historical conversation state.

Also available: `agent poll`, `agent local-tools`, `agent report-tool-result`.

## Error Codes

- `auth_failed`: ask for/configure the CinLink API key.
- `invalid_input`: fix file paths or unsupported formats.
- `dependency_missing`: run `doctor`; ask before installing local dependencies.
- `quota_exceeded`: tell the user to check billing/top up.
- `timeout`: report the job/run id if present and suggest polling again.
- `network_error` / `remote_error`: retry or inspect the runtime base.
