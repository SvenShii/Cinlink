---
name: cinlink-cli
description: CinLink CLI setup, API-key onboarding, diagnostics, JSON tool bridge, MCP server, and tool schema inspection. Use before any hosted CinLink task, when configuring a user's CinLink API key, when checking local dependencies such as ffmpeg/Demucs, or when an agent needs exact command/tool contracts for CinLink capabilities.
---

# CinLink CLI

Everything runs through the standalone `cinlink` CLI. Hosted work uses `https://runtime.cinlink.ai` by default and requires a CinLink API key. Local-only work uses local tools such as `ffmpeg`.

## Install

For first-time install or reconnect, read the repo-root `install.md` when it is available. It is the install-time contract: install the CLI, register the skills if needed, ask for the CinLink API key once if missing, then save it with onboarding.

```bash
pip install "git+https://github.com/SvenShii/Cinlink.git"
cinlink --json doctor
```

Windows users can also run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
```

## Configure API Key

Hosted work should have a CinLink API key configured during install. Check with `cinlink --json doctor`. Ask the user for their key only when `doctor` says no API key is configured or a hosted task returns `auth_failed`.

Use onboarding as the primary storage path. It writes user-level config, so it works even when the user installed only the skills and has no repo checkout:

```bash
cinlink --json onboarding --api-key <cinlink_api_key>
```

Environment variables are also supported:

```bash
export CINLINK_API_KEY="ck_live_or_test_xxx"
export CINLINK_RUNTIME_BASE="https://runtime.cinlink.ai"
export CINLINK_BILLING_BASE="https://app.cinlink.ai"
```

Credential lookup order is: process environment, then the CLI user config written by `onboarding`. Never print the key back to the user or write it into tracked files.

## Diagnostics

Run this before local-only tasks or when a hosted request fails:

```bash
cinlink --json doctor
```

`doctor` reports API key presence, runtime health, local `ffmpeg`, Demucs, and `soundfile` status. If voice separation or background preservation is requested and dependencies are missing, ask before installing anything.

## JSON Tool Bridge

For agents that prefer one stable wrapper, use:

```bash
python <THIS_SKILL_DIR>/scripts/cinlink_tool.py <tool> --args-json '<json object>'
```

Read `references/tool-contract.md` for the full argument contract.

## MCP

Run the MCP server over stdio:

```bash
cinlink-mcp
```

MCP exposes the same tool names as `cinlink --json tools list`.

## Tool Schema

```bash
cinlink --json tools list
cinlink --json tools schema transcribe
cinlink --json tools schema dub
```

Use JSON mode for all agent/automation calls.
