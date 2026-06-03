# CinLinkCLI

Standalone CinLink CLI for agents. This project is intentionally separate from the desktop app repositories.

Product policy:

- Hosted-first for transcription, translation, dubbing, summarization, image generation, and video generation.
- Local dependencies are used only for local capabilities.
- The hosted server does not provide Demucs voice-separation runtime.
- If the user asks for voice separation, vocal removal, or preserving background music through local separation, the user must install local `ffmpeg`, `demucs`, and `soundfile`.
- Agents should never install local dependencies silently. They should ask for explicit user confirmation first.

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
- Runs `cinlink --json doctor`.

If you pass an API key, the installer also writes CLI config:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1 -ApiKey "ck_live_or_test_xxx"
```

## Manual Install

```powershell
pip install "git+https://github.com/SvenShii/Cinlink.git"
cinlink --json doctor
```

If `cinlink` is not found after manual install, use the installer above or add Python's Scripts directory to the user `PATH`.

## Configure

```powershell
cinlink --json onboarding --api-key ck_live_or_test_xxx
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

cinlink --json transcribe "D:\videos\demo.mp4"
cinlink --json translate "D:\videos\demo.srt" --to en
cinlink --json burn "D:\videos\demo.mp4" --subtitle "D:\videos\translated.srt"
cinlink --json summarize "D:\videos\demo.mp4"
cinlink --json shorten "D:\videos\demo.mp4" --target-duration 45
cinlink --json image "a clean product poster"
cinlink --json video "a 5 second cinematic product reveal"

cinlink --json agent run "Summarize this video into five selling points" --context-file "D:\videos\demo.mp4"
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

The `skills/` directory contains thin wrappers for agent systems that prefer skill/plugin files instead of MCP.
