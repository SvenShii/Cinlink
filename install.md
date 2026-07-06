---
name: cinlink-install
description: Install CinLink skills and CLI into the current agent, register the skill directory, and collect the user's CinLink API key up front.
---

# CinLink install

Use this file only for first-time install or reconnect. For daily media work, read `skills/cinlink/SKILL.md` first.

## What you're doing

You're setting up CinLink for an agent so the user can run hosted media workflows without being asked for an API key in the middle of a task.

Four things must exist on this machine:

1. The `cinlink` CLI installed.
2. The CinLink skill folders registered with the current agent.
3. A CinLink API key saved in the user's CLI config before the first hosted task.

## Install prompt contract

- Do everything yourself where possible. Only ask the user for values you cannot generate: the CinLink API key and confirmation before installing system dependencies.
- Prefer a stable clone path such as `~/Developer/Cinlink`; do not install from `/tmp` or `~/Downloads`.
- Ask for the CinLink API key during install if it is not already configured.
- Save the key with `cinlink --json onboarding --api-key <key>`. This writes user-level config, so it also works when the user installed only the skills and does not have a repo checkout.
- Never echo the API key back to the user. Never write it into `SKILL.md` or any tracked file.
- Do not run hosted transcription, dubbing, image, or video generation as install verification unless the user explicitly asks; hosted work can spend credits.

## Steps

### 1. Clone to a stable path

Skip this step when the user installed the skills directly through their agent's skill installer. In that case, continue with CLI install/configuration.

For a full repo checkout:

```bash
test -d ~/Developer/Cinlink || git clone https://github.com/SvenShii/Cinlink.git ~/Developer/Cinlink
cd ~/Developer/Cinlink
```

If the repo already exists, run `git pull --ff-only` and continue.

### 2. Install the CLI

```bash
python -m pip install -e .
cinlink --json doctor
```

Windows users can run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1
```

### 3. Register the skills with the current agent

Skip this step when the current skill installer already registered the skills. Otherwise register the whole skill folders, not just one `SKILL.md`.

- **Codex** (`$CODEX_HOME` set, or `~/.codex/` present):

    ```bash
    mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
    ln -sfn ~/Developer/Cinlink/skills/cinlink "${CODEX_HOME:-$HOME/.codex}/skills/cinlink"
    ln -sfn ~/Developer/Cinlink/skills/cinlink-cli "${CODEX_HOME:-$HOME/.codex}/skills/cinlink-cli"
    ln -sfn ~/Developer/Cinlink/skills/cinlink-subtitles "${CODEX_HOME:-$HOME/.codex}/skills/cinlink-subtitles"
    ln -sfn ~/Developer/Cinlink/skills/cinlink-dubbing "${CODEX_HOME:-$HOME/.codex}/skills/cinlink-dubbing"
    ln -sfn ~/Developer/Cinlink/skills/cinlink-understanding "${CODEX_HOME:-$HOME/.codex}/skills/cinlink-understanding"
    ln -sfn ~/Developer/Cinlink/skills/cinlink-generation "${CODEX_HOME:-$HOME/.codex}/skills/cinlink-generation"
    ln -sfn ~/Developer/Cinlink/skills/cinlink-agent "${CODEX_HOME:-$HOME/.codex}/skills/cinlink-agent"
    ```

- **Claude Code** (`~/.claude/` present): symlink the same seven skill folders into `~/.claude/skills/`.
- **Hermes / Openclaw / another agent**: register the skill folders using that agent's skill directory or import mechanism.

If you cannot tell which agent is active, ask the user once which agent to install into.

### 4. CinLink API key

Hosted CinLink tools require the user's CinLink API key. Check existing state:

```bash
[ -n "$CINLINK_API_KEY" ] && echo "env"
cinlink --json doctor
```

If no key is configured, ask the user exactly once:

> I need your CinLink API key for hosted media workflows. Paste it here and I will save it with the local `cinlink` CLI. I will not print it back.

When the user provides the key, run onboarding:

```bash
cinlink --json onboarding --api-key "$KEY"
```

Optional endpoint overrides:

```bash
cinlink --json onboarding --api-key "$KEY" --runtime-base https://runtime.cinlink.ai --billing-base https://app.cinlink.ai
```

### 5. Verify

Run cheap checks only:

```bash
cinlink --json doctor
cinlink --json tools list
```

`doctor` should report `has_api_key: true`. If runtime health fails with a local network or sandbox error, do not treat that as an install failure; verify on the first real hosted task after network access is available.

### 6. Hand off

Tell the user:

- Where CinLink is installed.
- Whether the API key is configured.
- That a good first message is: "Using `/cinlink`, add subtitles to this video" or "Using `/cinlink`, generate a short product video."

## Cold-start reminders

- Read `skills/cinlink/SKILL.md` before routing a task.
- Hosted tasks require `CINLINK_API_KEY` from the environment or the `cinlink` user config written by onboarding.
- Local-only tasks such as subtitle burn and audio mix do not require a key, but they need local `ffmpeg`.
- Voice separation/background preservation is a local capability and needs `demucs` plus `soundfile`; ask before installing them.
