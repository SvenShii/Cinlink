# CinLinkCLI 使用说明

这份说明面向第一次把 CLI / skill / MCP 接进 OpenClaw、Hermes 或其他 agent 的使用者。

## 1. 这个 CLI 是什么

`CinLinkCLI` 是独立项目，位置：

```text
D:\工作\Video Agent\code\CinLinkCLI
```

它不修改、不导入下面两个项目：

```text
D:\工作\Video Agent\code\CinLink
D:\工作\Video Agent\code\CinLinkWindows
```

它的定位是给 agent 用的“工具协议层”：

```text
OpenClaw / Hermes / 其他 agent
  -> cinlink CLI 或 cinlink-mcp
      -> hosted runtime 服务
      -> 本地 ffmpeg 工具
```

也就是说，agent 不需要理解 Windows App 或 Mac App，只需要调用 CLI/MCP。

## 2. 安装

如果是 agent 第一次安装或重新连接，请优先让 agent 读取仓库根目录的 `install.md`。安装阶段就应该检查 API key：如果没有配置，向用户要一次 CinLink API key，然后运行 `cinlink --json onboarding --api-key <key>` 写入用户级 CLI 配置。

推荐像 `video-use` 一样，把下面这段直接粘给 Claude Code、Codex、Hermes、OpenClaw 或其他有 shell 权限的 agent：

```text
帮我设置 https://github.com/SvenShii/Cinlink。
先读取 install.md，安装 CinLink CLI，把 skills 注册到你当前所在的 agent，运行 setup-local-deps 来处理 ffmpeg 和可选的人声分离依赖，然后设置我的 CinLink API key；需要 key 时问我粘贴。请用 `cinlink --json onboarding --api-key <key>` 保存 key，不要把 key 打印出来。安装完成后不要主动跑转写、配音、图片生成或视频生成这种会消耗额度的任务，只运行 `cinlink --json doctor` 和 `cinlink --json tools list` 这类轻量检查，然后告诉我已经准备好，等待我的第一个媒体任务。
```

注意：`npx skills add SvenShii/Cinlink` 只会注册 skill 文件，不会自动执行 `install.md`，也不会自动安装 ffmpeg、安装 CLI 或弹出 API key 输入。第一次完整安装要用上面的 setup prompt 让 agent 继续执行 onboarding。

打开 PowerShell：

```powershell
cd "D:\工作\Video Agent\code\CinLinkCLI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

安装后会有三个命令：

```powershell
cinlink
addsubtitle
cinlink-mcp
```

??????? `cinlink`?MCP ??? `cinlink-mcp`?

Windows 一键安装脚本如果没有传 `-ApiKey`，并且环境变量里也没有 `CINLINK_API_KEY`，会在安装阶段提示输入一次 API key。也可以跳过提示：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows.ps1 -SkipApiKeyPrompt
```

## 3. 配置 API Key

安装时推荐直接写入 CLI 用户配置。这样用户只安装 skills、没有仓库目录时也能用：

```powershell
cinlink --json onboarding --api-key as_live_xxx
cinlink setup-local-deps
cinlink --json doctor
```

`cinlink setup-local-deps` 会检测并提示安装本地依赖：

- `ffmpeg`/`ffprobe`：字幕烧录、本地抽音频、音频混合、Clean Cut、精确裁剪、混剪、水印、视频拆解/拼接、音视频导出、剪辑工程交接和本地媒体检查。
- `demucs` + `soundfile`：可选，仅本地人声分离/保留背景音需要。

非交互安装时先展示 dry run：

```powershell
cinlink --json setup-local-deps --dry-run --with-voice-separation
```

用户确认后再执行：

```powershell
cinlink setup-local-deps --yes
cinlink setup-local-deps --yes --with-voice-separation
```

不要在日志或最终回复里打印 key，也不要把 key 写入 `SKILL.md` 或任何可提交文件。

也可以不写配置文件，直接给 agent 配环境变量：

```powershell
$env:CINLINK_API_KEY="as_live_xxx"
$env:CINLINK_RUNTIME_BASE="https://runtime.cinlink.ai"
$env:CINLINK_BILLING_BASE="https://app.cinlink.ai"
```

配置文件默认位置：

```text
Windows: %APPDATA%\CinLinkCLI\config.json
macOS/Linux: ~/.config/cinlink-cli/config.json
```

## 4. 先用命令行自测

先看工具列表：

```powershell
cinlink --json tools list
```

看某个工具 schema：

```powershell
cinlink --json tools schema transcribe
cinlink --json tools schema agent_run
cinlink --json tools schema agent_clarify
cinlink --json tools schema agent_cancel
cinlink --json tools schema setup_local_deps
cinlink --json tools schema clean_cut
cinlink --json tools schema brand_kit
cinlink --json tools schema deconstruct_video
cinlink --json tools schema export_editor_project
cinlink --json tools schema agent_events
```

跑一个 NLU：

```powershell
cinlink --json nlu "把这个视频翻译成英文字幕" --has-video
```

跑 agent：

```powershell
cinlink --json agent run "把这个视频总结成 5 条卖点" --context-file "D:\videos\demo.mp4" --app-language zh
cinlink --json agent run "给这个视频加英文字幕，并输出带字幕视频" --context-file "D:\videos\demo.mp4" --task-intent add_subtitles --task-param output_delivery=burned_video --task-param target_language=en --wait
```

如果结果为 `requires_user_input` 且包含 `clarifications`，先把问题和选项展示给用户，再用用户选择续跑原任务：

```powershell
cinlink --json agent clarify run_xxx --clarification-id translation_mode:0 --value voice --wait
```

用户要求停止任务时，取消原 run；取消后不要再上报迟到的本地结果：

```powershell
cinlink --json agent cancel run_xxx
```

文本澄清使用 `--answer`。只有一个澄清时可以省略 `--clarification-id`，多个澄清逐个回答。自由表述的视频翻译会先确认 `translation_mode=subtitle|voice`；选择字幕后，还可能继续确认 `output_delivery=subtitle_file|burned_video`。必须展示第二个问题，不能直接采用默认值。检查 `workflow_decision.slot_provenance`，来源为 `model_default` 或 `unknown` 的执行敏感字段不算用户已确认。该命令会保留原会话、任务框架、上下文文件和复合执行计划；没有 `clarifications` 的安装/授权确认不要调用它。

等待任务时可用 `--include-events` 收集公开的规划/推理进度，也可以单独读取 SSE：

```powershell
cinlink --json agent run \"分析并处理视频\" --wait --include-events
cinlink --json agent events run_xxx
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
cinlink --json agent local-tools run_xxx
```

## 5. 在 OpenClaw 这类 agent 里怎么用 CLI

最通用的方法是让 agent 调 shell 命令。

给 agent 的工具描述可以写成：

```text
当你需要处理视频、字幕、配音、总结、短视频、高亮、AI 图片或 AI 视频时，调用：
cinlink --json <command>

所有结果都是 JSON。不要解析普通文本。失败时读取 error.code 和 error.message。
```

示例工具命令：

```powershell
cinlink --json transcribe "D:\videos\demo.mp4"
cinlink --json translate "D:\videos\demo.srt" --to en
cinlink --json dub "D:\videos\demo.mp4" --subtitle "D:\videos\translated.srt" --reference-subtitle "D:\videos\source.reference.srt" --lang en
cinlink --json dub "D:\videos\demo.mp4" --subtitle "D:\videos\translated.srt" --lang en --reference-audio "speaker_0=D:\voices\speaker.wav"
cinlink --json burn "D:\videos\demo.mp4" --subtitle "D:\videos\translated.srt"
cinlink --json clean-cut "D:\videos\demo.mp4"
cinlink --json trim-video "D:\videos\demo.mp4" --start 12.4 --end 18.8
cinlink --json montage --clips-json "[{\"path\":\"D:\\videos\\demo.mp4\",\"start_sec\":0,\"end_sec\":4},{\"path\":\"D:\\videos\\demo.mp4\",\"start_sec\":8,\"end_sec\":12}]"
cinlink --json brand-kit set --enable --font-name Arial --watermark-image "D:\brand\logo.png"
cinlink --json apply-watermark "D:\videos\demo.mp4"
cinlink --json summarize "D:\videos\demo.mp4"
cinlink --json shorten "D:\videos\demo.mp4" --target-duration 45
cinlink --json image "把这个产品改成小红书风格封面图" --reference-image-url "D:\brand\product.png"
cinlink --json video "5 秒产品展示视频，干净背景"
cinlink --json agent run "把这个视频剪成 3 个 15 秒短视频" --context-file "D:\videos\demo.mp4"
cinlink --json agent run "给这个视频加英文字幕，并输出带字幕视频" --context-file "D:\videos\demo.mp4" --client-request-id request_123 --task-intent add_subtitles --task-param output_delivery=burned_video --task-param target_language=en --wait
```

新增的视频拆解、视觉替换和导出命令：

```powershell
cinlink --json video \"让这个产品动起来\" --first-frame-image-url \"D:\\brand\\product.png\"
cinlink --json deconstruct-video \"D:\\videos\\demo.mp4\" --language zh-Hans --analysis-scope \"镜头运动、产品展示和灯光\" --out \"D:\\videos\\deconstruction\"
cinlink --json regenerate-deconstruction \"D:\\videos\\deconstruction\\deconstruction.json\" --replacement-reference \"product=D:\\brand\\new-product.png\"
cinlink --json export-video \"D:\\videos\\demo.mp4\" --format mov
cinlink --json export-audio \"D:\\videos\\demo.mp4\" --format mp3
cinlink --json export-editor-project \"D:\\videos\\demo.mp4\" --target premiere --subtitle \"D:\\videos\\demo.srt\"
```

新版 hosted runtime 在转写、视频翻译、总结、短视频规划、配音和视觉拆解流程中都不接收完整视频。音频工作流只上传本地抽取的音频；缩短流程会先把音频注册为账号范围内的 Agent 文件，再用 `cloud_file_id` 提交分析，旧 runtime 不支持时自动退回 multipart 音频上传。视频拆解只上传采样帧。图片生成最多接收 3 张参考图，视频生成最多接收 9 张参考图；URL 或本地路径均可，本地图片会经鉴权的参考图接口上传。配音应携带与译文逐条对齐的原文参考字幕；未显式传入时 CLI 会依次寻找同目录下的 `source.reference.srt`、`subtitle.reference.srt`、`source.srt`。多说话人配音参考音频用重复的 `--reference-audio speaker_id=path`。

Agent 同时收到一个视频和一份有效的 SRT/VTT/ASS 时，CLI 会把字幕标记为可复用并绑定来源视频，避免重复转写。通过 `--context-file` 本次提交的本地文件会自动标记 `selection_scope=current_submission` 和 `input_priority=highest`，优先于会话里的旧文件；本次同时提交多个同类文件时仍会保留歧义。有多份字幕或图片时，应通过 `--context-json` 保留 id、语言、artifact role、来源 lineage、`cloud_file_id` 和 `public_url`；当前明确选中的 descriptor 才手动加上述两个 metadata，历史 descriptor 不自动提权。显式选中的生成参考图无法解析时，应要求重新提供，不能静默替换成旧图片。如果任务同时要求缩短和配音，要先在原始完整时间轴上完成配音合成，再剪高光，不能把完整配音音轨直接混入已经缩短的视频。

Agent 完成时优先把 `completion_message` 给用户，并把 `primary_artifacts` 作为最终结果；`supporting_artifacts` 只在有帮助时补充，`intermediate_artifacts` 不作为最终交付。

Agent 调用应该传 `--app-language zh|en|ja`。继续使用之前的生成结果时，用 `--context-json` 保留 `public_url`、`cloud_file_id`、`artifact_role` 和 `producer_step`，不要只留下一个本地文件名。

Brand Kit 保存在同一个用户级 JSON 配置里，不使用 `.env`。启用后会自动应用到后续 `add-subtitles`、`burn` 和 `apply-watermark`，单次显式参数优先。

如果 OpenClaw 支持 skill manifest，可以参考：

```text
D:\工作\Video Agent\code\CinLinkCLI\skills\openclaw\cinlink.skill.json
```

不同 OpenClaw 版本 manifest 字段可能不同。关键不是字段名，而是调用方式：

```powershell
python "D:\工作\Video Agent\code\CinLinkCLI\skills\call_cinlink_tool.py" transcribe --args-json "{\"input_path\":\"D:\\videos\\demo.mp4\"}"
```

## 6. 在 Hermes 里怎么用

Hermes 有两种接法。

第一种：CLI tool。让 Hermes 执行：

```powershell
cinlink --json agent run "{prompt}" --context-file "{file}"
```

如果调用方已经知道是 app 里的明确任务，可以追加：

```powershell
--task-intent add_subtitles --task-param output_delivery=burned_video
```

模板文件：

```text
D:\工作\Video Agent\code\CinLinkCLI\skills\hermes\cinlink_tools.yaml
```

第二种：MCP。只要 Hermes 支持 MCP stdio，配置：

```json
{
  "mcpServers": {
    "cinlink": {
      "command": "cinlink-mcp",
      "args": [],
      "env": {
        "CINLINK_API_KEY": "as_live_xxx"
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
apply_watermark
trim_video
montage
clean_cut
brand_kit
deconstruct_video
regenerate_deconstruction
export_video
export_audio
export_editor_project
agent_events
agent_clarify
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
你可以使用 CinLink 工具处理媒体任务。优先调用 agent_run 处理自然语言复杂任务；如果用户明确要转写、翻译、烧录、总结、缩短、生成图片或生成视频，也可以直接调用对应工具。所有工具返回 JSON。成功时读取输出路径和 artifacts；失败时读取 error.code。不要假设本地文件存在，调用前确认用户给了绝对路径。
```

## 8. 输出和错误

成功：

```json
{
  "status": "done",
  "subtitle_path": "D:/videos/demo.cinlink/subtitle.srt"
}
```

失败：

```json
{
  "error": {
    "code": "auth_failed",
    "message": "API key is not configured. Run `cinlink onboarding --api-key <key>` first."
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

托管任务失败时还可能包含安全的 `error.details`，例如 `processing_stage`、`provider`、`request_id` 和 `retryable`。向用户展示公开的 `code`/`message`，仅当 `retryable=true` 时自动重试。

## 9. 什么时候用 CLI，什么时候用 MCP

如果 agent 只能执行命令，用 CLI：

```powershell
cinlink --json tools list
cinlink --json agent run "..."
```

如果 agent 支持 MCP，用 MCP：

```powershell
cinlink-mcp
```

MCP 的好处是 agent 能自动读取工具 schema，不需要你手写很多命令模板。

## 10. 本地 ffmpeg

`burn`、`clean-cut`、`trim-video`、`montage` 和 `apply-watermark` 都是本地能力，需要 `ffmpeg`/`ffprobe`：

```powershell
ffmpeg -version
```

没有的话先安装 ffmpeg，再重试：

```powershell
cinlink --json burn "D:\videos\demo.mp4" --subtitle "D:\videos\demo.srt"
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
cinlink --json doctor
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
