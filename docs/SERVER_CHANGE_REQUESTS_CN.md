# 服务端配合修改清单

本 CLI 没有修改主仓库和 Windows App。下面是为了让 agent 工具协议更完整，建议服务端同事后续在 `CinLink` 主仓中补的点。

## 1. `/v1/agent/events/{run_id}` SSE

## 0. 当前产品策略确认

CLI 已按下面策略实现：

- hosted-first：转写、翻译、配音、总结、生图、生视频优先走服务端。
- 本地依赖只服务本地能力：字幕烧录、本地抽音频、本地剪辑、本地人声分离 / 保留背景音。
- 服务端当前没有 Demucs，人声分离不走服务端兜底。
- 如果用户要求“人声分离 / 去人声 / 保留背景音 / preserve bgm”，CLI 会先检查用户本机 `ffmpeg + demucs + soundfile`，缺失时返回 `dependency_missing`，由 agent 提示用户安装。
- agent 不应自动安装依赖，必须先获得用户确认。

这意味着服务端同事不需要为了当前 CLI 立刻安装 Demucs；除非未来产品决定把人声分离也做成 hosted 能力。

当前 CLI 可以轮询：

```text
GET /v1/agent/runs/{run_id}
```

建议服务端补 SSE：

```text
GET /v1/agent/events/{run_id}
```

事件类型建议：

```text
message_delta
plan_updated
tool_call_created
artifact_created
progress
done
failed
requires_user_input
```

这样 CLI 可以加：

```powershell
cinlink --json agent stream run_xxx
```

## 2. Agent run 支持上传本地文件

当前 `/v1/agent/runs` 接收的是 `context_files` 元数据：

```json
{
  "name": "demo.mp4",
  "kind": "video",
  "local_hint": "D:/videos/demo.mp4"
}
```

这适合 desktop app 的 local tool bridge，但外部 agent 如果只有 CLI，通常希望直接上传文件。

建议新增：

```text
POST /v1/agent/runs/multipart
```

字段：

```text
prompt
conversation_id
mode
file[]
client_capabilities
```

返回仍然是 `AgentRunRecord`。

## 3. 统一 artifact 下载接口

当前 CLI 可以读服务端返回的路径/URL，但 agent 最好拿到稳定 artifact 字段。

建议所有任务返回：

```json
{
  "artifacts": [
    {
      "id": "artifact_xxx",
      "name": "translated.srt",
      "kind": "subtitle",
      "download_url": "https://...",
      "expires_at": "..."
    }
  ]
}
```

CLI 可增加：

```powershell
cinlink --json artifacts download artifact_xxx --out D:\out
```

## 4. Tool schema 服务端接口

CLI 本地已有：

```powershell
cinlink --json tools list
cinlink --json tools schema transcribe
```

建议服务端也暴露：

```text
GET /v1/tools
GET /v1/tools/{name}/schema
```

这样 CLI 与服务端 schema 可以自动对齐，避免手工同步。

## 5. 本地工具调用执行协议细化

当前服务端已有：

```text
GET  /v1/agent/runs/{run_id}/local-tool-calls
POST /v1/agent/runs/{run_id}/local-tool-results
```

建议把每个 local tool 的 arguments 约定固定下来，例如：

```text
extract_audio:
  input_path
  output_format

burn_subtitles:
  video_path
  subtitle_path
  style

render_highlight_clips:
  video_path
  clips
  target_duration_sec
```

CLI 后续可加：

```powershell
cinlink --json agent execute-local-tools run_xxx
```

自动执行服务端要求的本地工具并回报结果。

## 6. 错误码统一

建议服务端所有接口统一：

```json
{
  "error": {
    "code": "invalid_input",
    "message": "..."
  }
}
```

CLI 当前会兼容这个形状，并把非标准 HTTP 错误归一化为：

```text
remote_error
network_error
job_not_found
auth_failed
```

## 7. NLU/Agent planner 能力声明

建议服务端 `/v1/agent/runs` 返回本次 planner 使用情况：

```json
{
  "planner": {
    "backend": "gpt|hermes|deterministic",
    "model": "gpt-5.4",
    "fallback_used": false
  }
}
```

这样 agent 可以在结果里解释“这次是服务端 agent 规划”还是“固定路由”。
