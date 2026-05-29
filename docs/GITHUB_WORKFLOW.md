# GitHub 仓库使用文档

这份文档说明如何用 GitHub Desktop 管理 `CodexStatusWidget` 仓库，以及如何构建并发布 Windows 便携包。

## 1. 本地仓库位置

| 项目 | 路径 |
| --- | --- |
| 本地仓库 | `H:\github\CodexStatusWidget` |
| 远程仓库 | `https://github.com/nobody96321/CodexStatusWidget` |
| Release 页面 | `https://github.com/nobody96321/CodexStatusWidget/releases` |

## 2. 用 GitHub Desktop 提交源码

1. 打开 GitHub Desktop。
2. 在左上角仓库列表选择 `CodexStatusWidget`。
3. 检查 Changes 面板中的变更文件。
4. 确认不要提交这些本地产物：
   - `dist/`
   - `build/`
   - `CodexStatusWidget.spec`
   - `codex_status_settings.json`
   - `__pycache__/`
5. 在 Summary 中填写提交信息，例如：

```text
Prepare v0.1.0 release package
```

6. 点击 `Commit to main`。
7. 点击 `Push origin` 推送到 GitHub。

## 3. 从源码运行

在仓库目录打开 PowerShell：

```powershell
cd H:\github\CodexStatusWidget
python -m pip install -e .
python -m codex_status_widget
```

只检查一次当前状态：

```powershell
python -m codex_status_widget --once
```

## 4. 构建 Windows 发布包

安装构建依赖：

```powershell
cd H:\github\CodexStatusWidget
python -m pip install -e ".[build]"
```

构建便携版 zip：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-release.ps1
```

成功后会生成：

| 产物 | 路径 |
| --- | --- |
| exe | `dist\CodexStatusWidget.exe` |
| zip | `dist\CodexStatusWidget-v0.1.0-win64.zip` |

`dist/` 已被 `.gitignore` 忽略，不需要提交到仓库。

## 5. 创建 GitHub Release

1. 打开仓库页面：`https://github.com/nobody96321/CodexStatusWidget`。
2. 进入右侧或顶部的 `Releases`。
3. 点击 `Draft a new release`。
4. Tag 填写：

```text
v0.1.0
```

5. Release title 填写：

```text
Codex Status Widget v0.1.0
```

6. Release description 可以复制 `RELEASE_NOTES.md` 的内容。
7. 上传附件：

```text
dist\CodexStatusWidget-v0.1.0-win64.zip
```

8. 点击 `Publish release`。

## 6. 后续更新流程

1. 修改代码和文档。
2. 在本地运行：

```powershell
python -m py_compile .\src\codex_status_widget\core.py .\src\codex_status_widget\app_qt.py
python -m codex_status_widget --once
```

3. 更新 `CHANGELOG.md` 和 `RELEASE_NOTES.md`。
4. 修改 `pyproject.toml` 中版本号。
5. 运行 `scripts\build-release.ps1` 生成新的 zip。
6. 用 GitHub Desktop 提交源码变更并推送。
7. 在 GitHub Releases 创建新版本，并上传新的 zip。

## 7. 常见注意事项

| 问题 | 建议 |
| --- | --- |
| GitHub Desktop 没显示 zip | 正常，`dist/` 被忽略；zip 应上传到 Release，不提交到 Git。 |
| exe 很大 | PyInstaller 单文件会打包 Python 和 PySide6，60MB 左右是正常体积。 |
| Windows 拦截 exe | v0.1.0 未签名，用户可在文件属性中解除锁定或选择仍要运行。 |
| 设置文件被生成 | `codex_status_settings.json` 是本地运行配置，已被忽略。 |
