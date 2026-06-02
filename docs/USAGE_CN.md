# PopularVideoCLI 使用说明

这份说明面向第一次把 CLI / skill / MCP 接进 OpenClaw、Hermes 或其他 agent 的使用者。

## 1. 这个 CLI 是什么

`PopularVideoCLI` 是独立项目，位置：

```text
D:\工作\Video Agent\code\PopularVideoCLI
```

它不修改、不导入下面两个项目：

```text
D:\工作\Video Agent\code\PopularVideo
D:\工作\Video Agent\code\PopularVideoWindows
```

它的定位是给 agent 用的“工具协议层”：

```text
OpenClaw / Hermes / 其他 agent
  -> popularvideo CLI 或 popularvideo-mcp
      -> hosted runtime 服务
      -> 本地 ffmpeg 工具
```

也就是说，agent 不需要理解 Windows App 或 Mac App，只需要调用 CLI/MCP。

## 2. 安装

打开 PowerShell：

```powershell
cd "D:\工作\Video Agent\code\PopularVideoCLI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

安装后会有三个命令：

```powershell
popularvideo
addsubtitle
popularvideo-mcp
```

`addsubtitle` 是兼容别名，推荐新 agent 使用 `popularvideo`。

## 3. 配置 API Key

```powershell
popularvideo --json onboarding --api-key ck_live_or_test_xxx
popularvideo --json doctor
```

也可以不写配置文件，直接给 agent 配环境变量：

```powershell
$env:CINLINK_API_KEY="ck_live_or_test_xxx"
$env:CINLINK_RUNTIME_BASE="https://runtime.cinlink.ai"
$env:CINLINK_BILLING_BASE="https://app.cinlink.ai"
```

配置文件默认位置：

```text
Windows: %APPDATA%\PopularVideoCLI\config.json
macOS/Linux: ~/.config/popularvideo-cli/config.json
```

## 4. 先用命令行自测

先看工具列表：

```powershell
popularvideo --json tools list
```

看某个工具 schema：

```powershell
popularvideo --json tools schema transcribe
popularvideo --json tools schema agent_run
```

跑一个 NLU：

```powershell
popularvideo --json nlu "把这个视频翻译成英文字幕" --has-video
```

跑 agent：

```powershell
popularvideo --json agent run "把这个视频总结成 5 条卖点" --context-file "D:\videos\demo.mp4"
```

如果返回：

```json
{
  "status": "waiting_for_local",
  "local_tool_calls": []
}
```

说明服务端 agent 认为需要本地工具，你可以继续：

```powershell
popularvideo --json agent local-tools run_xxx
```

## 5. 在 OpenClaw 这类 agent 里怎么用 CLI

最通用的方法是让 agent 调 shell 命令。

给 agent 的工具描述可以写成：

```text
当你需要处理视频、字幕、配音、总结、短视频、高亮、AI 图片或 AI 视频时，调用：
popularvideo --json <command>

所有结果都是 JSON。不要解析普通文本。失败时读取 error.code 和 error.message。
```

示例工具命令：

```powershell
popularvideo --json transcribe "D:\videos\demo.mp4"
popularvideo --json translate "D:\videos\demo.srt" --to en
popularvideo --json burn "D:\videos\demo.mp4" --subtitle "D:\videos\translated.srt"
popularvideo --json summarize "D:\videos\demo.mp4"
popularvideo --json shorten "D:\videos\demo.mp4" --target-duration 45
popularvideo --json image "小红书风格的美食封面图"
popularvideo --json video "5 秒产品展示视频，干净背景"
popularvideo --json agent run "把这个视频剪成 3 个 15 秒短视频" --context-file "D:\videos\demo.mp4"
```

如果 OpenClaw 支持 skill manifest，可以参考：

```text
D:\工作\Video Agent\code\PopularVideoCLI\skills\openclaw\popularvideo.skill.json
```

不同 OpenClaw 版本 manifest 字段可能不同。关键不是字段名，而是调用方式：

```powershell
python "D:\工作\Video Agent\code\PopularVideoCLI\skills\call_popularvideo_tool.py" transcribe --args-json "{\"input_path\":\"D:\\videos\\demo.mp4\"}"
```

## 6. 在 Hermes 里怎么用

Hermes 有两种接法。

第一种：CLI tool。让 Hermes 执行：

```powershell
popularvideo --json agent run "{prompt}" --context-file "{file}"
```

模板文件：

```text
D:\工作\Video Agent\code\PopularVideoCLI\skills\hermes\popularvideo_tools.yaml
```

第二种：MCP。只要 Hermes 支持 MCP stdio，配置：

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

MCP 启动后，Hermes 会看到这些工具：

```text
transcribe
translate
burn
summarize
shorten
image
video
nlu
agent_run
```

## 7. 推荐给 agent 的系统提示

可以把这段放进 OpenClaw/Hermes 的工具说明里：

```text
你可以使用 PopularVideo 工具处理媒体任务。优先调用 agent_run 处理自然语言复杂任务；如果用户明确要转写、翻译、烧录、总结、缩短、生成图片或生成视频，也可以直接调用对应工具。所有工具返回 JSON。成功时读取输出路径和 artifacts；失败时读取 error.code。不要假设本地文件存在，调用前确认用户给了绝对路径。
```

## 8. 输出和错误

成功：

```json
{
  "status": "done",
  "subtitle_path": "D:/videos/demo.popularvideo/subtitle.srt"
}
```

失败：

```json
{
  "error": {
    "code": "auth_failed",
    "message": "API key is not configured. Run `popularvideo onboarding --api-key <key>` first."
  }
}
```

常见错误码：

```text
auth_failed          没有 API key 或 key 无效
invalid_input        参数不对、文件不存在
config_invalid       配置文件坏了
dependency_missing   本地缺 ffmpeg
network_error        连不到服务
remote_error         服务端返回非预期错误
job_not_found        run_id/job_id 不存在
processing_failed    任务失败
timeout              等待超时
internal_error       CLI 内部异常
```

## 9. 什么时候用 CLI，什么时候用 MCP

如果 agent 只能执行命令，用 CLI：

```powershell
popularvideo --json tools list
popularvideo --json agent run "..."
```

如果 agent 支持 MCP，用 MCP：

```powershell
popularvideo-mcp
```

MCP 的好处是 agent 能自动读取工具 schema，不需要你手写很多命令模板。

## 10. 本地 ffmpeg

`burn` 是本地能力，需要 `ffmpeg` 在 PATH 里：

```powershell
ffmpeg -version
```

没有的话先安装 ffmpeg，再重试：

```powershell
popularvideo --json burn "D:\videos\demo.mp4" --subtitle "D:\videos\demo.srt"
```

## 11. hosted-first 和人声分离策略

当前产品策略：

```text
转写、翻译、配音、总结、生图、生视频：优先走 hosted 服务端。
字幕烧录、本地剪辑、本地抽音频：使用用户电脑上的本地 ffmpeg。
人声分离 / 去人声 / 保留背景音：仍然是本地能力。
服务端当前没有安装 Demucs，不做人声分离兜底。
```

所以如果用户让 agent 做：

```text
人声分离
去人声
提取伴奏
保留原背景音乐再配音
preserve bgm
separate vocals
```

agent 应先调用：

```powershell
popularvideo --json doctor
```

检查：

```text
local_dependencies.ffmpeg.available
local_dependencies.demucs.available
local_dependencies.soundfile.available
local_dependencies.local_voice_separation.available
```

如果缺依赖，CLI 会返回 `dependency_missing`。agent 应该提示用户：

```text
这个任务需要在你的电脑上安装本地人声分离组件。服务端没有 Demucs，不能代替本机完成。
需要安装 ffmpeg、demucs、soundfile。是否允许我继续安装？
```

不要让 agent 在未确认时自动安装。

安装参考：

```powershell
winget install Gyan.FFmpeg
pip install demucs soundfile
```

macOS：

```bash
brew install ffmpeg
pip install demucs soundfile
```
