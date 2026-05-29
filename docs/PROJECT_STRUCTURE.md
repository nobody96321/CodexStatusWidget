# Project Structure

| Path | Purpose |
| --- | --- |
| `src/codex_status_widget/` | Application package and `python -m codex_status_widget` entry point |
| `scripts/` | Release build automation |
| `docs/` | Maintainer and GitHub workflow documentation |
| `.github/` | GitHub issue and pull request templates |
| `dist/` | Local build output, ignored by Git |
| `build/` | PyInstaller temporary output, ignored by Git |

## Source Package

| File | Purpose |
| --- | --- |
| `core.py` | Codex session/log detection and status snapshot logic |
| `app_qt.py` | PySide6 desktop widget, settings UI, and CLI parser |
| `__main__.py` | Module entry point for `python -m codex_status_widget` |
| `__init__.py` | Package exports and version metadata |
