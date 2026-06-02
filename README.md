<<<<<<< HEAD
cinlink cli
=======
# PopularVideoCLI

Standalone PopularVideo/CinLink CLI for agents. This project is intentionally separate from:

- `D:\工作\Video Agent\code\PopularVideo`
- `D:\工作\Video Agent\code\PopularVideoWindows`

It does not import or modify either repository. Hosted media work is called through HTTP. Local-only work, such as burning subtitles into a video, uses local `ffmpeg`.

Product policy:

- Hosted-first for transcription, translation, dubbing, summarization, image generation, and video generation.
- Local dependencies are used only for local capabilities.
- The hosted server does not provide Demucs voice-separation runtime.
- If the user asks for voice separation, vocal removal, or preserving background music through local separation, the user must install local `ffmpeg`, `demucs`, and `soundfile`.
- Agents should never install local dependencies silently. They should ask for explicit user confirmation first.

## Install

```powershell
cd "D:\工作\Video Agent\code\PopularVideoCLI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

## Configure

```powershell
popularvideo --json onboarding --api-key ck_live_or_test_xxx
popularvideo --json doctor
```

`doctor` reports both hosted health and local dependency status.

Environment variables can also be used:

```powershell
$env:CINLINK_API_KEY="ck_live_or_test_xxx"
$env:CINLINK_RUNTIME_BASE="https://runtime.cinlink.ai"
$env:CINLINK_BILLING_BASE="https://app.cinlink.ai"
```

## CLI Examples

```powershell
popularvideo --json tools list
popularvideo --json tools schema transcribe

popularvideo --json transcribe "D:\videos\demo.mp4"
popularvideo --json translate "D:\videos\demo.srt" --to en
popularvideo --json burn "D:\videos\demo.mp4" --subtitle "D:\videos\translated.srt"
popularvideo --json summarize "D:\videos\demo.mp4"
popularvideo --json shorten "D:\videos\demo.mp4" --target-duration 45
popularvideo --json image "a clean product poster"
popularvideo --json video "a 5 second cinematic product reveal"

popularvideo --json agent run "把这个视频总结成 5 条卖点，再生成一个封面图" --context-file "D:\videos\demo.mp4"
popularvideo --json agent poll run_xxx
popularvideo --json agent local-tools run_xxx
```

## Stable JSON Contract

Successful commands print one JSON object to stdout:

```json
{
  "status": "done",
  "subtitle_path": "D:/videos/demo.popularvideo/subtitle.srt"
}
```

Failed commands also print JSON:

```json
{
  "error": {
    "code": "auth_failed",
    "message": "API key is not configured. Run `popularvideo onboarding --api-key <key>` first."
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

For voice separation requests, a missing local runtime returns:

```json
{
  "error": {
    "code": "dependency_missing",
    "message": "Voice separation is a local capability. The hosted server does not provide Demucs, so ask the user to install local voice separation components before continuing."
  }
}
```

## MCP

Run the MCP server over stdio:

```powershell
popularvideo-mcp
```

Example MCP config:

```json
{
  "mcpServers": {
    "popularvideo": {
      "command": "popularvideo-mcp",
      "args": [],
      "env": {
        "CINLINK_API_KEY": "ck_live_or_test_xxx"
      }
    }
  }
}
```

See `examples/mcp-config.json`.

## Skill Wrappers

The `skills/` directory contains thin wrappers for agent systems that prefer skill/plugin files instead of MCP:

- `skills/call_popularvideo_tool.py`
- `skills/openclaw/popularvideo.skill.json`
- `skills/hermes/popularvideo_tools.yaml`

These files are templates. Different OpenClaw/Hermes builds may use different manifest field names, so keep the command shape but adjust manifest metadata to match the agent version you run.
>>>>>>> 3e2c153 (Initial PopularVideo CLI agent protocol)
