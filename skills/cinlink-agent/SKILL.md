---
name: cinlink-agent
description: CinLink hosted agent runtime for multi-step media tasks. Use when the user gives a broad natural-language request that may require planning, multiple CinLink tools, local tool calls, context files, clarification, or recovery across transcription, translation, dubbing, summarization, short-video planning, and AI media generation.
---

# CinLink Agent

Use this when the request is broader than one direct command.

## Submit A Run

```bash
cinlink --json agent run "<prompt>" --context-file /absolute/video.mp4 --mode execute --wait
```

Use `--mode plan` when the user wants a plan before execution. Use `--wait` for short/medium jobs; otherwise return the `run_id` and poll later.

## Poll

```bash
cinlink --json agent poll <run_id>
```

## Local Tool Calls

The hosted runtime may request local work when the user's machine owns the file or local `ffmpeg` is needed:

```bash
cinlink --json agent local-tools <run_id>
cinlink --json agent report-tool-result <run_id> --tool-call-id <id> --status done --artifact-path /absolute/out.mp4
```

## Routing Guidance

Use `/cinlink-agent` for:

- Multi-step media workflows
- Requests where the user describes the outcome but not exact operations
- Tasks involving multiple context files
- Workflows needing clarification or recovery

For a single explicit operation, prefer the direct domain skill.
