# Codex Status Widget

Codex Status Widget 是一个桌面红绿灯状态组件，用来显示 Codex 当前大致处于“正在思考”“调用工具”“可以继续”“需要查看”或“未活动”等状态。它不连接硬件，不修改 Codex，只读取本机 Codex 的会话和日志元数据。

## 项目链接

| 项目 | 地址 |
| --- | --- |
| GitHub 仓库 | [nobody96321/CodexStatusWidget](https://github.com/nobody96321/CodexStatusWidget) |
| 下载发布包 | [GitHub Releases](https://github.com/nobody96321/CodexStatusWidget/releases) |
| 仓库操作文档 | [docs/GITHUB_WORKFLOW.md](docs/GITHUB_WORKFLOW.md) |
| 项目结构说明 | [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) |

## 功能

| 功能 | 说明 |
| --- | --- |
| 红绿灯状态 | 红灯表示正在思考或需要查看，黄灯表示工具执行中，绿灯表示可以继续 |
| 桌面浮窗 | 置顶、半透明、可拖动，支持折叠为只显示红绿灯 |
| 状态详情 | 展示当前对话名称和状态详情，例如“正在思考”“运行 shell_command 命令” |
| 设置窗口 | 支持刷新间隔、状态判定窗口、透明度、置顶、文字显示和灯方向 |
| 方向切换 | 支持竖向红绿灯和横向红绿灯 |
| 便携发布 | Windows Release 包内含 exe 和启动脚本，解压即可运行 |

## 仓库结构

| 路径 | 说明 |
| --- | --- |
| `src/codex_status_widget/` | 应用源码和 `python -m codex_status_widget` 入口 |
| `scripts/` | 构建 Release 包的 PowerShell 脚本 |
| `docs/` | GitHub Desktop、Release 发布等维护文档 |
| `.github/` | Issue 和 Pull Request 模板 |

## 下载 exe

1. 打开 GitHub Releases。
2. 下载 `CodexStatusWidget-v0.1.0-win64.zip`。
3. 解压到任意目录。
4. 双击 `CodexStatusWidget.exe` 或 `run-codex-status-widget-hidden.vbs`。

如果 Windows 安全提示拦截未签名程序，可以在文件属性里解除锁定，或选择“仍要运行”。v0.1.0 默认不提供代码签名。

## 源码运行

需要 Python 3.10+。

```powershell
python -m pip install -e .
python -m codex_status_widget
```

隐藏命令行窗口启动：

```powershell
.\run-codex-status-widget-hidden.vbs
```

查看一次当前状态：

```powershell
python -m codex_status_widget --once
```

指定某个线程：

```powershell
python -m codex_status_widget --thread-id 019e6503-4e2f-7d03-8650-4e0ff2dcb12f
```

## 构建发布包

安装构建依赖：

```powershell
python -m pip install -e ".[build]"
```

生成 Windows 便携包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-release.ps1
```

构建完成后会生成：

| 产物 | 路径 |
| --- | --- |
| exe | `dist/CodexStatusWidget.exe` |
| 便携目录 | `dist/CodexStatusWidget-v0.1.0-win64/` |
| Release zip | `dist/CodexStatusWidget-v0.1.0-win64.zip` |

## 状态来源

| 来源 | 用途 |
| --- | --- |
| `~/.codex/sessions/*.jsonl` | 识别任务开始、完成、工具调用 |
| `~/.codex/logs_2.sqlite` | 识别错误和 Codex app-server UI 事件 |
| `~/.codex/state_5.sqlite` | 读取对话标题和最后更新时间 |

组件会读取 `codex_app_server::outgoing_message` 事件；如果发现 `item/started` 或回复流式 delta，且后续没有 `turn/completed`，会优先显示“正在思考”红灯，减少正在思考时误亮绿灯的情况。

## 设置

展开浮窗后，点击右上角齿轮打开设置窗口。设置会保存到 `codex_status_settings.json`：

| 运行方式 | 设置文件位置 |
| --- | --- |
| exe | `CodexStatusWidget.exe` 同目录 |
| 源码 | 仓库根目录 |

本地设置文件不会提交到源码仓库，也不会打进 Release zip。

## 隐私说明

组件只读取本机 Codex 的 session/log 元数据，不展示对话正文，不上传数据，不调用网络接口。

## 常见问题

| 问题 | 说明 |
| --- | --- |
| 为什么状态偶尔有延迟？ | 当前实现是轮询本地文件和 SQLite 日志，默认刷新间隔为 `0.5` 秒。 |
| 为什么 exe 体积较大？ | PyInstaller 会把 Python 运行时和 PySide6 一起打包，这是单文件便携版的正常现象。 |
| 为什么没有托盘图标？ | v0.1.0 先提供桌面浮窗和设置窗口，托盘菜单留作后续功能。 |
| 是否支持 macOS/Linux？ | v0.1.0 的发布包只面向 Windows 64-bit，源码逻辑后续可以再适配。 |

## License

MIT License. See [LICENSE](LICENSE).
