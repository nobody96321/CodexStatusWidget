from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from codex_status_widget.core import CodexStatusDetector, codex_home_from_env


LIGHT_BY_MODE = {
    "working": "red",
    "error": "red",
    "tool": "yellow",
    "waiting": "green",
    "offline": "",
}

LIGHTS = {
    "red": {
        "active": "#ff6b6b",
        "core": "#ffa8a8",
        "dim": "#3c2025",
        "glass": "#6b2a31",
        "glow": "#ff6b6b",
    },
    "yellow": {
        "active": "#ffd43b",
        "core": "#fff3bf",
        "dim": "#3e351c",
        "glass": "#66521f",
        "glow": "#ffd43b",
    },
    "green": {
        "active": "#51cf66",
        "core": "#b2f2bb",
        "dim": "#1e3727",
        "glass": "#286442",
        "glow": "#51cf66",
    },
}

APP_NAME = "Codex Status Widget"
APP_VERSION = "0.1.0"


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    package_dir = Path(__file__).resolve().parent
    if package_dir.parent.name == "src":
        return package_dir.parent.parent
    return package_dir


SETTINGS_PATH = app_base_dir() / "codex_status_settings.json"


@dataclass
class WidgetSettings:
    refresh_interval: float = 0.5
    active_seconds: int = 5
    ui_active_seconds: int = 15 * 60
    tool_grace_seconds: int = 8
    stale_seconds: int = 15 * 60
    opacity: int = 94
    always_on_top: bool = True
    expanded: bool = True
    light_orientation: str = "vertical"


def load_widget_settings() -> WidgetSettings:
    if not SETTINGS_PATH.exists():
        return WidgetSettings()

    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return WidgetSettings()

    if not isinstance(data, dict):
        return WidgetSettings()

    defaults = asdict(WidgetSettings())
    clean: Dict[str, Any] = {}
    for key, default in defaults.items():
        value = data.get(key, default)
        if isinstance(default, bool):
            clean[key] = bool(value)
        elif isinstance(default, int):
            clean[key] = int(value)
        elif isinstance(default, float):
            clean[key] = float(value)
        elif isinstance(default, str):
            clean[key] = str(value)

    if clean.get("light_orientation") not in {"vertical", "horizontal"}:
        clean["light_orientation"] = "vertical"

    return WidgetSettings(**clean)


def save_widget_settings(settings: WidgetSettings) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def color(value: str, alpha: int = 255) -> QColor:
    qcolor = QColor(value)
    qcolor.setAlpha(alpha)
    return qcolor


def elide(value: str, limit: int) -> str:
    value = " ".join((value or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


class SettingsDialog(QDialog):
    def __init__(self, owner: "CodexStatusQtWidget") -> None:
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("状态组件设置")
        self.setMinimumSize(468, 430)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, owner.settings.always_on_top)
        self.setStyleSheet(
            """
            QDialog { background: #15181d; color: #edf2f7; }
            QTabWidget::pane { border: 1px solid #323a45; border-radius: 8px; top: -1px; }
            QTabBar::tab {
                background: #20262e;
                color: #aeb8c4;
                border: 1px solid #323a45;
                padding: 8px 14px;
                margin-right: 4px;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
            }
            QTabBar::tab:selected { background: #2a313b; color: #ffffff; }
            QLabel { color: #d7dde5; }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background: #0f1318;
                color: #edf2f7;
                border: 1px solid #3a4450;
                border-radius: 6px;
                padding: 4px 8px;
                min-height: 24px;
            }
            QCheckBox { color: #d7dde5; spacing: 8px; }
            QPushButton {
                background: #2b333d;
                color: #edf2f7;
                border: 1px solid #46515f;
                border-radius: 7px;
                padding: 7px 14px;
            }
            QPushButton:hover { background: #35404c; }
            QPushButton:pressed { background: #1f252d; }
            QPushButton:checked {
                background: #223747;
                border-color: #2f9eeb;
                color: #ffffff;
            }
            QListWidget {
                background: #0f1318;
                color: #aeb8c4;
                border: 1px solid #303844;
                border-radius: 8px;
                padding: 6px;
            }
            QSlider::groove:horizontal {
                height: 5px;
                background: #303844;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #51cf66;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(12)

        title = QLabel("状态组件设置")
        title_font = QFont("Microsoft YaHei UI", 13)
        title_font.setBold(True)
        title.setFont(title_font)
        root.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_general_tab(), "常规")
        self.tabs.addTab(self.build_status_tab(), "状态")
        self.tabs.addTab(self.build_appearance_tab(), "外观")
        self.tabs.addTab(self.build_future_tab(), "拓展")
        root.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel("设置会保存到本地，下次启动继续使用")
        self.status_label.setStyleSheet("color: #8d96a3;")
        footer.addWidget(self.status_label, 1)

        reset_button = QPushButton("恢复默认")
        reset_button.clicked.connect(self.reset_defaults)
        footer.addWidget(reset_button)

        apply_button = QPushButton("应用")
        apply_button.clicked.connect(self.apply_changes)
        footer.addWidget(apply_button)

        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.close)
        footer.addWidget(close_button)
        root.addLayout(footer)

    def build_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.interval_input = QDoubleSpinBox()
        self.interval_input.setRange(0.1, 5.0)
        self.interval_input.setSingleStep(0.1)
        self.interval_input.setDecimals(1)
        self.interval_input.setSuffix(" 秒")
        self.interval_input.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.interval_input.setValue(self.owner.settings.refresh_interval)
        layout.addRow("刷新间隔", self.interval_input)

        self.topmost_check = QCheckBox("始终置顶")
        self.topmost_check.setChecked(self.owner.settings.always_on_top)
        layout.addRow("窗口", self.topmost_check)

        self.expanded_check = QCheckBox("显示右侧文字区域")
        self.expanded_check.setChecked(self.owner.settings.expanded)
        layout.addRow("显示", self.expanded_check)

        return widget

    def build_status_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.active_input = self.make_seconds_spin(1, 60, self.owner.settings.active_seconds)
        layout.addRow("普通活动窗口", self.active_input)

        self.ui_active_input = self.make_seconds_spin(10, 3600, self.owner.settings.ui_active_seconds)
        layout.addRow("界面思考保持", self.ui_active_input)

        self.tool_grace_input = self.make_seconds_spin(1, 60, self.owner.settings.tool_grace_seconds)
        layout.addRow("工具宽限时间", self.tool_grace_input)

        self.stale_input = self.make_seconds_spin(60, 24 * 60 * 60, self.owner.settings.stale_seconds)
        layout.addRow("未活动阈值", self.stale_input)

        return widget

    def build_appearance_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(75, 100)
        self.opacity_slider.setValue(self.owner.settings.opacity)
        self.opacity_label = QLabel(f"{self.owner.settings.opacity}%")
        self.opacity_slider.valueChanged.connect(lambda value: self.opacity_label.setText(f"{value}%"))

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_label)
        layout.addRow("透明度", opacity_row)

        self.orientation_group = QButtonGroup(self)
        self.orientation_group.setExclusive(True)
        self.vertical_orientation_button = QPushButton("竖向红绿灯")
        self.horizontal_orientation_button = QPushButton("横向红绿灯")
        for button in (self.vertical_orientation_button, self.horizontal_orientation_button):
            button.setCheckable(True)

        self.orientation_group.addButton(self.vertical_orientation_button, 0)
        self.orientation_group.addButton(self.horizontal_orientation_button, 1)
        if self.owner.settings.light_orientation == "horizontal":
            self.horizontal_orientation_button.setChecked(True)
        else:
            self.vertical_orientation_button.setChecked(True)

        orientation_row = QHBoxLayout()
        orientation_row.addWidget(self.vertical_orientation_button)
        orientation_row.addWidget(self.horizontal_orientation_button)
        layout.addRow("灯方向", orientation_row)

        theme_note = QLabel("主题、尺寸、托盘图标会在后续版本接入")
        theme_note.setStyleSheet("color: #8d96a3;")
        layout.addRow("预留", theme_note)

        return widget

    def build_future_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        list_widget = QListWidget()
        for text in (
            "系统托盘菜单：退出、置顶、打开设置",
            "开机自启：写入 Windows Startup",
            "线程选择：固定某个对话或自动跟随最近对话",
            "状态规则：为不同工具指定自定义文案",
            "主题方案：亮色、深色、紧凑模式",
        ):
            item = QListWidgetItem(text)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            list_widget.addItem(item)

        layout.addWidget(list_widget)
        return widget

    def make_seconds_spin(self, minimum: int, maximum: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSuffix(" 秒")
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        spin.setValue(value)
        return spin

    def apply_changes(self) -> None:
        settings = self.owner.settings
        settings.refresh_interval = round(float(self.interval_input.value()), 1)
        settings.active_seconds = int(self.active_input.value())
        settings.ui_active_seconds = int(self.ui_active_input.value())
        settings.tool_grace_seconds = int(self.tool_grace_input.value())
        settings.stale_seconds = int(self.stale_input.value())
        settings.opacity = int(self.opacity_slider.value())
        settings.always_on_top = self.topmost_check.isChecked()
        settings.expanded = self.expanded_check.isChecked()
        settings.light_orientation = "horizontal" if self.horizontal_orientation_button.isChecked() else "vertical"

        self.owner.apply_runtime_settings()
        save_widget_settings(settings)
        self.status_label.setText("已应用")

    def reset_defaults(self) -> None:
        defaults = WidgetSettings()
        self.interval_input.setValue(defaults.refresh_interval)
        self.active_input.setValue(defaults.active_seconds)
        self.ui_active_input.setValue(defaults.ui_active_seconds)
        self.tool_grace_input.setValue(defaults.tool_grace_seconds)
        self.stale_input.setValue(defaults.stale_seconds)
        self.opacity_slider.setValue(defaults.opacity)
        self.topmost_check.setChecked(defaults.always_on_top)
        self.expanded_check.setChecked(defaults.expanded)
        self.vertical_orientation_button.setChecked(defaults.light_orientation == "vertical")
        self.horizontal_orientation_button.setChecked(defaults.light_orientation == "horizontal")
        self.status_label.setText("已恢复默认值，点击应用后生效")


class CodexStatusQtWidget(QWidget):
    vertical_expanded_size = (304, 112)
    horizontal_expanded_size = (200, 136)
    vertical_collapsed_size = (58, 90)
    horizontal_collapsed_size = (92, 58)

    def __init__(self, detector: CodexStatusDetector, settings: WidgetSettings) -> None:
        super().__init__()
        self.detector = detector
        self.settings = settings
        self.interval_ms = max(100, int(settings.refresh_interval * 1000))
        self.expanded = settings.expanded
        self.settings_dialog: Optional[SettingsDialog] = None
        self.snapshot = self.detector.snapshot()
        self.drag_start = QPoint()
        self.window_start = QPoint()
        self.press_pos = QPoint()
        self.dragging = False
        self.pulse = False

        self.setWindowTitle("Codex Status")
        self.set_widget_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowOpacity(self.settings.opacity / 100)
        self.setMouseTracking(True)
        self.apply_size(initial=True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(self.interval_ms)

    def set_widget_flags(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.settings.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def apply_runtime_settings(self) -> None:
        self.detector.active_seconds = self.settings.active_seconds
        self.detector.ui_active_seconds = self.settings.ui_active_seconds
        self.detector.tool_grace_seconds = self.settings.tool_grace_seconds
        self.detector.stale_seconds = self.settings.stale_seconds

        self.interval_ms = max(100, int(self.settings.refresh_interval * 1000))
        self.timer.setInterval(self.interval_ms)
        self.setWindowOpacity(self.settings.opacity / 100)

        self.expanded = self.settings.expanded
        self.apply_size()

        visible = self.isVisible()
        self.set_widget_flags()
        if visible:
            self.show()
        self.update()

    def apply_size(self, initial: bool = False) -> None:
        width, height = self.current_size()
        old_right = self.geometry().right()
        old_top = self.geometry().top()
        self.resize(width, height)

        if initial:
            screen = QGuiApplication.primaryScreen().availableGeometry()
            self.move(screen.right() - width - 24, screen.top() + 24)
        else:
            self.move(max(0, old_right - width + 1), max(0, old_top))

        self.update()

    def is_horizontal(self) -> bool:
        return self.settings.light_orientation == "horizontal"

    def current_size(self) -> tuple[int, int]:
        if self.expanded:
            return self.horizontal_expanded_size if self.is_horizontal() else self.vertical_expanded_size
        return self.horizontal_collapsed_size if self.is_horizontal() else self.vertical_collapsed_size

    def signal_rect(self) -> QRectF:
        if self.is_horizontal():
            if self.expanded:
                return QRectF((self.width() - 84) / 2, 14, 84, 44)
            return QRectF(4, 4, 84, 50)
        if self.expanded:
            return QRectF(16, 14, 50, 84)
        return QRectF(4, 4, 50, 82)

    def close_rect(self) -> QRect:
        return QRect(self.width() - 31, 8, 22, 22)

    def settings_rect(self) -> QRect:
        return QRect(self.width() - 58, 8, 22, 22)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.press_pos = event.globalPosition().toPoint()
        self.drag_start = self.press_pos
        self.window_start = self.pos()
        self.dragging = False

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not event.buttons() & Qt.MouseButton.LeftButton:
            return
        current = event.globalPosition().toPoint()
        delta = current - self.drag_start
        if abs(delta.x()) > 4 or abs(delta.y()) > 4:
            self.dragging = True
            self.move(self.window_start + delta)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() != Qt.MouseButton.LeftButton or self.dragging:
            return

        local = event.position().toPoint()
        if self.expanded and self.close_rect().contains(local):
            self.close()
            return

        if self.expanded and self.settings_rect().contains(local):
            self.open_settings()
            return

        if self.signal_rect().contains(local):
            self.expanded = not self.expanded
            self.settings.expanded = self.expanded
            save_widget_settings(self.settings)
            self.apply_size()

    def open_settings(self) -> None:
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return

        self.settings_dialog = SettingsDialog(self)
        self.settings_dialog.show()

    def refresh(self) -> None:
        self.snapshot = self.detector.snapshot()
        self.pulse = not self.pulse
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        self.paint_panel(painter)
        self.paint_signal(painter)
        if self.expanded:
            self.paint_text(painter)
            self.paint_settings(painter)
            self.paint_close(painter)

    def paint_panel(self, painter: QPainter) -> None:
        rect = QRectF(0.75, 0.75, self.width() - 1.5, self.height() - 1.5)
        shadow = QRectF(2.5, 4.0, self.width() - 5.0, self.height() - 5.0)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color("#000000", 64))
        painter.drawRoundedRect(shadow, 16, 16)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, color("#1d2025", 236))
        gradient.setColorAt(1.0, color("#121419", 228))
        painter.setBrush(gradient)
        painter.setPen(QPen(color("#48505b", 210), 1.0))
        painter.drawRoundedRect(rect, 15, 15)

        inner = rect.adjusted(4, 4, -4, -4)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color("#222832", 170), 1.0))
        painter.drawRoundedRect(inner, 12, 12)

    def paint_signal(self, painter: QPainter) -> None:
        rect = self.signal_rect()
        active = LIGHT_BY_MODE.get(self.snapshot.mode, "")

        shell = QRectF(rect.x() + 3, rect.y(), rect.width() - 6, rect.height())
        painter.setPen(QPen(color("#2d3540"), 1.0))
        painter.setBrush(color("#07090c"))
        painter.drawRoundedRect(shell, 13, 13)

        body = shell.adjusted(3, 3, -3, -3)
        body_gradient = QLinearGradient(body.topLeft(), body.bottomLeft())
        body_gradient.setColorAt(0, color("#151b22"))
        body_gradient.setColorAt(1, color("#0d1117"))
        painter.setBrush(body_gradient)
        painter.setPen(QPen(color("#3a4450"), 1.0))
        painter.drawRoundedRect(body, 10, 10)

        slot = body.adjusted(4, 5, -4, -5)
        painter.setBrush(color("#111720"))
        painter.setPen(QPen(color("#07090c"), 1.0))
        painter.drawRoundedRect(slot, 8, 8)

        if self.is_horizontal():
            centers = (
                ("red", rect.x() + 18, rect.center().y()),
                ("yellow", rect.x() + 42, rect.center().y()),
                ("green", rect.x() + 66, rect.center().y()),
            )
            for name, cx, cy in centers:
                self.paint_lamp(painter, QPoint(int(cx), int(cy)), name, name == active)
        else:
            for name, cy in (("red", rect.y() + 18), ("yellow", rect.y() + 42), ("green", rect.y() + 66)):
                self.paint_lamp(painter, QPoint(int(rect.center().x()), int(cy)), name, name == active)

    def paint_lamp(self, painter: QPainter, center: QPoint, name: str, active: bool) -> None:
        colors = LIGHTS[name]
        cx, cy = center.x(), center.y()

        if active and self.pulse:
            glow = QRadialGradient(cx, cy, 15)
            glow.setColorAt(0.0, color(colors["glow"], 110))
            glow.setColorAt(1.0, color(colors["glow"], 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QRectF(cx - 15, cy - 15, 30, 30))

        painter.setPen(QPen(color("#050607"), 1.0))
        painter.setBrush(color("#050607"))
        painter.drawEllipse(QRectF(cx - 12, cy - 12, 24, 24))

        rim_gradient = QLinearGradient(cx, cy - 10, cx, cy + 10)
        rim_gradient.setColorAt(0, color("#313a45"))
        rim_gradient.setColorAt(1, color("#0b0f14"))
        painter.setBrush(rim_gradient)
        painter.setPen(QPen(color("#3f4853"), 1.0))
        painter.drawEllipse(QRectF(cx - 10, cy - 10, 20, 20))

        lamp_gradient = QRadialGradient(cx - 3, cy - 4, 13)
        lamp_gradient.setColorAt(0.0, color(colors["core"] if active else colors["glass"]))
        lamp_gradient.setColorAt(0.55, color(colors["active"] if active else colors["dim"]))
        lamp_gradient.setColorAt(1.0, color("#121820"))
        painter.setBrush(lamp_gradient)
        painter.setPen(QPen(color("#fff3bf" if active and name == "yellow" else "#08090b"), 1.0))
        painter.drawEllipse(QRectF(cx - 7, cy - 7, 14, 14))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color("#ffffff" if active else "#7d8792", 190))
        painter.drawEllipse(QRectF(cx - 5, cy - 6, 5.5, 5.5))

    def paint_text(self, painter: QPainter) -> None:
        if self.is_horizontal():
            text_x = 26
            label_y = 66
            title_y = 91
            detail_y = 112
            text_width = max(120, self.width() - 52)
        else:
            text_x = 92
            label_y = 20
            title_y = 48
            detail_y = 70
            text_width = max(120, self.settings_rect().left() - text_x - 10)

        painter.setPen(color("#f8f9fa"))
        font = QFont("Microsoft YaHei UI", 13)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(text_x, label_y, text_width, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.snapshot.label)

        painter.setPen(color("#d0d6dd"))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(QRectF(text_x, title_y, text_width, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elide(self.snapshot.title or "Codex", 18))

        painter.setPen(color("#8d96a3"))
        painter.drawText(QRectF(text_x, detail_y, text_width, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.snapshot.detail)

    def paint_close(self, painter: QPainter) -> None:
        rect = self.close_rect()
        painter.setPen(QPen(color("#8d96a3"), 1.8))
        painter.drawLine(rect.left() + 7, rect.top() + 7, rect.right() - 7, rect.bottom() - 7)
        painter.drawLine(rect.right() - 7, rect.top() + 7, rect.left() + 7, rect.bottom() - 7)

    def paint_settings(self, painter: QPainter) -> None:
        rect = self.settings_rect()
        cx = rect.center().x()
        cy = rect.center().y()

        painter.save()
        painter.setPen(QPen(color("#8d96a3"), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - 4, cy - 4, 8, 8))

        for index in range(8):
            angle = math.radians(index * 45)
            inner_x = cx + math.cos(angle) * 6
            inner_y = cy + math.sin(angle) * 6
            outer_x = cx + math.cos(angle) * 8
            outer_y = cy + math.sin(angle) * 8
            painter.drawLine(int(inner_x), int(inner_y), int(outer_x), int(outer_y))

        painter.restore()


def build_parser(settings: Optional[WidgetSettings] = None) -> argparse.ArgumentParser:
    settings = settings or WidgetSettings()
    parser = argparse.ArgumentParser(description="Codex desktop status light widget, Qt renderer")
    parser.add_argument("--codex-home", default="", help="Codex home directory, defaults to %%USERPROFILE%%\\.codex")
    parser.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID", ""), help="Thread id to follow")
    parser.add_argument("--interval", type=float, default=settings.refresh_interval, help="Refresh interval in seconds")
    parser.add_argument("--active-seconds", type=int, default=settings.active_seconds, help="Recent activity window for fallback working state")
    parser.add_argument("--ui-active-seconds", type=int, default=settings.ui_active_seconds, help="Maximum time to trust unfinished app-server activity")
    parser.add_argument("--tool-grace-seconds", type=int, default=settings.tool_grace_seconds, help="Maximum time to keep a stale tool state")
    parser.add_argument("--stale-seconds", type=int, default=settings.stale_seconds, help="Window before a thread is considered inactive")
    parser.add_argument("--light-orientation", choices=("vertical", "horizontal"), default=settings.light_orientation, help="Traffic light direction")
    parser.add_argument("--once", action="store_true", help="Print one status snapshot as JSON and exit")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    settings = load_widget_settings()
    args = build_parser(settings).parse_args(argv)
    settings.refresh_interval = args.interval
    settings.active_seconds = args.active_seconds
    settings.ui_active_seconds = args.ui_active_seconds
    settings.tool_grace_seconds = args.tool_grace_seconds
    settings.stale_seconds = args.stale_seconds
    settings.light_orientation = args.light_orientation

    detector = CodexStatusDetector(
        codex_home=codex_home_from_env(args.codex_home),
        thread_id=args.thread_id,
        active_seconds=args.active_seconds,
        ui_active_seconds=args.ui_active_seconds,
        tool_grace_seconds=args.tool_grace_seconds,
        stale_seconds=args.stale_seconds,
    )

    if args.once:
        print(json.dumps(asdict(detector.snapshot()), ensure_ascii=False, indent=2))
        return 0

    app = QApplication(sys.argv[:1])
    widget = CodexStatusQtWidget(detector, settings)
    widget.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
