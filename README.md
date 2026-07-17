# CinLink Agent Skills & CLI

Standalone CinLink skills and CLI for agents. This project is intentionally separate from the desktop app repositories.

Product policy:

- Hosted-first for transcription, translation, dubbing, summarization, image generation, and video generation.
- Local dependencies are used only for local capabilities.
- The hosted server does not provide Demucs voice-separation runtime.
- If the user asks for voice separation, vocal removal, or preserving background music through local separation, the user must install local `ffmpeg`, `demucs`, and `soundfile`.
- Agents should never install local dependencies silently. They should ask for explicit user confirmation first.

## With an AI coding agent

### Setup prompt

Paste this into Claude Code, Codex, Hermes, OpenClaw, or any agent with shell access:

```text
Set up https://github.com/SvenShii/Cinlink for me.
Read install.md first to install the CinLink CLI, register the skills with whichever agent you're running under, run setup-local-deps so ffmpeg and optional local voice-separation dependencies are handled, and set up my CinLink API key — ask me to paste it when you need it. Save the key with `cinlink --json onboarding --api-key <key>` and never print it back. After install, don't run hosted transcription, dubbing, image, or video generation on your own — just run cheap checks like `cinlink --json doctor` and `cinlink --json tools list`, tell me it's ready, and wait for my first media task.
```

The agent handles the clone, CLI install, local dependency prompt, skill registration, and one-time CinLink API key onboarding.

If you only want to register the skills without full onboarding, run:

```bash
npx skills add SvenShii/Cinlink
```

`npx skills add` only installs the skill files. It does not execute `install.md`, install `ffmpeg`, install the `cinlink` CLI, or prompt for an API key. For first-time installs or reconnects, use the setup prompt above.

The install contract in `install.md` asks for the user's CinLink API key up front if it is not already configured, saves it with `cinlink --json onboarding`, and never prints or commits the key.

During install, the agent should also run:

```bash
cinlink setup-local-deps
```

This prompts the user to install local `ffmpeg` for subtitle burn-in, local audio extraction/mixing, and local media inspection. It also offers optional `demucs` and `soundfile` for local voice separation/background preservation.

Try prompts like:

> Using `/cinlink`, add subtitles to this video.

> Using `/cinlink`, dub this video into English and summarize the result.

The skills follow the Hyperframes-style package layout: a router skill plus focused domain skills. Hosted work uses your CinLink API key; local-only work uses local dependencies such as `ffmpeg`.

## Windows Install

Recommended one-command install from GitHub:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
```

Install from a specific Git URL:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1 -Source "git+https://github.com/SvenShii/Cinlink.git"
```

Install from the current checkout while developing:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1 -Editable
```

The installer:

- Installs or upgrades the package with `pip`.
- Finds Python's Scripts directory.
- Adds that directory to the user-level `PATH`.
- Updates the current PowerShell session `PATH`.
- Prompts to install local dependencies such as `ffmpeg`.
- Prompts for a CinLink API key during install when none is configured, unless `-SkipApiKeyPrompt` is passed.
- Writes the provided key to the CLI user config through onboarding.
- Runs `cinlink --json doctor`.

If you pass an API key, the installer uses it without prompting:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1 -ApiKey "ck_live_or_test_xxx"
```

To accept local dependency installation without an interactive prompt, pass `-InstallLocalDependencies`. To also install optional local voice-separation dependencies, pass `-InstallVoiceSeparationDependencies`.

## Manual Install

```powershell
pip install "git+https://github.com/SvenShii/Cinlink.git"
cinlink --json doctor
```

If `cinlink` is not found after manual install, use the installer above or add Python's Scripts directory to the user `PATH`.

## Configure

```powershell
cinlink --json onboarding --api-key ck_live_or_test_xxx
cinlink setup-local-deps
cinlink --json doctor
```

Environment variables can also be used:

```powershell
$env:CINLINK_API_KEY="ck_live_or_test_xxx"
$env:CINLINK_RUNTIME_BASE="https://runtime.cinlink.ai"
$env:CINLINK_BILLING_BASE="https://app.cinlink.ai"
```

## CLI Examples

```powershell
cinlink --json tools list
cinlink --json tools schema transcribe

cinlink --json add-subtitles "D:\videos\demo.mp4"
cinlink --json add-subtitles "D:\videos\demo.mp4" --target-lang en
cinlink --json transcribe "D:\videos\demo.mp4"
cinlink --json translate "D:\videos\demo.srt" --to en
cinlink --json dub "D:\videos\demo.mp4" --subtitle "D:\videos\translated.srt" --lang en
cinlink --json burn "D:\videos\demo.mp4" --subtitle "D:\videos\translated.srt"
cinlink --json mix-dubbed-audio "D:\videos\demo.mp4" --dubbed-audio "D:\videos\dubbed.wav"
cinlink --json summarize "D:\videos\demo.mp4"
cinlink --json shorten "D:\videos\demo.mp4" --target-duration 45
cinlink --json image "a clean product poster"
cinlink --json video "a 5 second cinematic product reveal"

cinlink --json agent run "Summarize this video into five selling points" --context-file "D:\videos\demo.mp4"
cinlink --json agent run "Add English subtitles and return the subtitled video" --context-file "D:\videos\demo.mp4" --task-intent add_subtitles --task-param output_delivery=burned_video --task-param target_language=en --wait
cinlink --json agent poll run_xxx
cinlink --json agent local-tools run_xxx
```

## Stable JSON Contract

Successful commands print one JSON object to stdout. Failed commands also print JSON:

```json
{
  "error": {
    "code": "auth_failed",
    "message": "API key is not configured. Run `cinlink onboarding --api-key <key>` first."
  }
}
```

Common error codes:

- `auth_failed`
- `invalid_input`
- `config_invalid`
- `dependency_missing`
- `network_error`
- `remote_error`
- `job_not_found`
- `processing_failed`
- `timeout`
- `internal_error`

## MCP

Run the MCP server over stdio:

```powershell
cinlink-mcp
```

Example MCP config:

```json
{
  "mcpServers": {
    "cinlink": {
      "command": "cinlink-mcp",
      "args": [],
      "env": {
        "CINLINK_API_KEY": "ck_live_or_test_xxx"
      }
    }
  }
}
```

## Skill Wrappers

The `skills/` directory contains installable skills for agent systems that prefer skill/plugin files instead of MCP. Read `/cinlink` first; it routes the request to focused domain skills.

### Router

| Skill | Use when |
| --- | --- |
| `/cinlink` | Read first for any CinLink media request. Capability map and intent router. |

### Domain skills

| Skill | Use when |
| --- | --- |
| `/cinlink-cli` | Install/configure CLI, store API key, run doctor, inspect tool schemas, use JSON bridge. |
| `/cinlink-subtitles` | Transcribe, translate subtitles/media, produce bilingual subtitles, burn styled subtitles/watermarks. |
| `/cinlink-dubbing` | Voice translation, dubbing, dubbed audio generation, local dubbed-audio mixing. |
| `/cinlink-understanding` | Summarize videos, extract highlights, shorten long videos into plans, NLU routing. |
| `/cinlink-generation` | Generate AI images and AI videos with hosted providers and remote references. |
| `/cinlink-agent` | Multi-step natural-language media workflows through the hosted CinLink agent runtime. |

### Compatibility wrappers

- `skills/openclaw/cinlink.skill.json` exposes the same tools through the existing OpenClaw wrapper.
- `skills/hermes/cinlink_tools.yaml` exposes the same tools for Hermes-style tool catalogs.
- `cinlink-mcp` exposes the same tools over MCP stdio.

Hosted capabilities require a CinLink API key, configured with:

```powershell
cinlink --json onboarding --api-key ck_live_or_test_xxx
```

For agent installs, prefer the install-time flow in `install.md`: collect the key once, run `cinlink --json onboarding --api-key <key>`, then use `cinlink --json doctor` to confirm `has_api_key: true`.

Local-only capabilities such as subtitle burn-in and dubbed-audio mixing require local `ffmpeg`. Voice separation or background-music preservation through separated stems also requires local `demucs` and `soundfile`; agents should ask the user before installing local dependencies.
