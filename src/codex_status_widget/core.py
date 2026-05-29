from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


UUID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)
APP_SERVER_EVENT_RE = re.compile(r"app-server event:\s*([^\s]+)")
APP_SERVER_ACTIVE_EVENTS = {
    "item/started",
    "item/agentMessage/delta",
    "turn/diff/updated",
}
APP_SERVER_DONE_EVENTS = {
    "turn/completed",
    "turn/failed",
    "turn/cancelled",
    "turn/aborted",
}

MODE_STYLE = {
    "working": {
        "label": "正在思考",
        "color": "#ff6b6b",
        "detail": "任务已开始，尚未完成",
    },
    "tool": {
        "label": "工具执行中",
        "color": "#ffd43b",
        "detail": "工具调用尚未结束",
    },
    "waiting": {
        "label": "可以继续",
        "color": "#51cf66",
        "detail": "最近线程已静默",
    },
    "error": {
        "label": "需要查看",
        "color": "#ff6b6b",
        "detail": "最近日志里出现错误",
    },
    "offline": {
        "label": "未活动",
        "color": "#868e96",
        "detail": "没有找到活跃的 Codex 会话",
    },
}

SIGNAL_BY_MODE = {
    "error": "red",
    "tool": "yellow",
    "working": "red",
    "waiting": "green",
    "offline": "",
}

TRAFFIC_LIGHTS = {
    "red": {
        "active": "#ff6b6b",
        "core": "#ff8787",
        "dim": "#412226",
        "glass": "#6b2a31",
        "glow": "#7d2b33",
        "halo": "#3a171b",
    },
    "yellow": {
        "active": "#ffd43b",
        "core": "#ffe066",
        "dim": "#43391d",
        "glass": "#66521f",
        "glow": "#7a651f",
        "halo": "#362b13",
    },
    "green": {
        "active": "#51cf66",
        "core": "#69db7c",
        "dim": "#1f3b2a",
        "glass": "#286442",
        "glow": "#286b3d",
        "halo": "#142d20",
    },
}


@dataclass
class Snapshot:
    mode: str
    label: str
    color: str
    detail: str
    thread_id: str
    title: str
    age: str
    session_path: str
    source: str
    updated_at: Optional[float]


def codex_home_from_env(value: Optional[str]) -> Path:
    if value:
        return Path(value).expanduser()
    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / ".codex"


def parse_thread_id(path: Path) -> str:
    match = UUID_RE.search(path.name)
    return match.group(1) if match else ""


def safe_stat(path: Path) -> Optional[os.stat_result]:
    try:
        return path.stat()
    except OSError:
        return None


def list_session_files(sessions_dir: Path) -> Iterable[Path]:
    if not sessions_dir.exists():
        return []
    return sessions_dir.rglob("*.jsonl")


def newest_session_file(codex_home: Path, preferred_thread_id: str = "") -> Optional[Path]:
    sessions_dir = codex_home / "sessions"
    newest: Optional[Tuple[float, Path]] = None

    for path in list_session_files(sessions_dir):
        stat = safe_stat(path)
        if not stat:
            continue
        if preferred_thread_id and preferred_thread_id.lower() in path.name.lower():
            return path
        if newest is None or stat.st_mtime > newest[0]:
            newest = (stat.st_mtime, path)

    return newest[1] if newest else None


def read_tail_lines(path: Path, max_lines: int = 120, max_bytes: int = 96 * 1024) -> List[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            data = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []

    return data.splitlines()[-max_lines:]


def load_tail_events(path: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for line in read_tail_lines(path):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def sqlite_connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=0.25)


def load_thread_info(codex_home: Path, thread_id: str) -> Dict[str, Any]:
    db_path = codex_home / "state_5.sqlite"
    if not thread_id or not db_path.exists():
        return {}

    try:
        with sqlite_connect_readonly(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT title, preview, cwd, updated_at_ms
                FROM threads
                WHERE id = ?
                """,
                (thread_id,),
            ).fetchone()
    except sqlite3.Error:
        return {}

    return dict(row) if row else {}


def load_thread_name(codex_home: Path, thread_id: str) -> str:
    index_path = codex_home / "session_index.jsonl"
    if not thread_id or not index_path.exists():
        return ""

    thread_name = ""
    try:
        with index_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("id") == thread_id:
                    thread_name = str(item.get("thread_name") or "").strip()
    except OSError:
        return ""

    return thread_name


def load_latest_log(codex_home: Path, thread_id: str) -> Dict[str, Any]:
    db_path = codex_home / "logs_2.sqlite"
    if not thread_id or not db_path.exists():
        return {}

    try:
        with sqlite_connect_readonly(db_path) as conn:
            conn.row_factory = sqlite3.Row
            latest = conn.execute(
                """
                SELECT ts, level, target, feedback_log_body
                FROM logs
                WHERE thread_id = ?
                ORDER BY ts DESC, ts_nanos DESC, id DESC
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
            error = conn.execute(
                """
                SELECT ts, level, target, feedback_log_body
                FROM logs
                WHERE thread_id = ? AND level = 'ERROR'
                ORDER BY ts DESC, ts_nanos DESC, id DESC
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
    except sqlite3.Error:
        return {}

    result: Dict[str, Any] = {}
    if latest:
        result["latest"] = dict(latest)
    if error:
        result["error"] = dict(error)
    return result


def parse_app_server_event(body: str) -> str:
    match = APP_SERVER_EVENT_RE.search(body or "")
    return match.group(1) if match else ""


def load_app_server_activity(codex_home: Path, max_rows: int = 160) -> Dict[str, Any]:
    db_path = codex_home / "logs_2.sqlite"
    if not db_path.exists():
        return {}

    try:
        with sqlite_connect_readonly(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT ts, ts_nanos, thread_id, feedback_log_body
                FROM logs
                WHERE target = 'codex_app_server::outgoing_message'
                ORDER BY ts DESC, ts_nanos DESC, id DESC
                LIMIT ?
                """,
                (max_rows,),
            ).fetchall()
    except sqlite3.Error:
        return {}

    latest_event = ""
    latest_ts = 0.0
    last_active_event = ""
    last_active_ts = 0.0
    last_done_event = ""
    last_done_ts = 0.0

    for row in reversed(rows):
        body = str(row["feedback_log_body"] or "")
        event = parse_app_server_event(body)
        ts = float(row["ts"] or 0) + float(row["ts_nanos"] or 0) / 1_000_000_000
        if not event or not ts:
            continue

        latest_event = event
        latest_ts = ts

        if event in APP_SERVER_DONE_EVENTS:
            last_done_event = event
            last_done_ts = ts
        elif event in APP_SERVER_ACTIVE_EVENTS:
            last_active_event = event
            last_active_ts = ts

    active = bool(last_active_ts and last_active_ts > last_done_ts)
    return {
        "active": active,
        "latest_event": latest_event,
        "latest_ts": latest_ts,
        "last_active_event": last_active_event,
        "last_active_ts": last_active_ts,
        "last_done_event": last_done_event,
        "last_done_ts": last_done_ts,
    }


def summarize_events(events: List[Dict[str, Any]]) -> Dict[str, str]:
    open_calls: Dict[str, str] = {}
    last_kind = ""
    last_tool = ""
    last_task_event = ""
    active_turn_id = ""
    completed_turn_ids: set[str] = set()

    for event in events:
        event_type = str(event.get("type") or "")
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}

        if event_type == "event_msg":
            payload_type = str(payload.get("type") or "")
            last_kind = payload_type or event_type

            if payload_type == "task_started":
                active_turn_id = str(payload.get("turn_id") or "")
                last_task_event = "task_started"
                open_calls.clear()
            elif payload_type == "task_complete":
                completed_turn_id = str(payload.get("turn_id") or "")
                if completed_turn_id:
                    completed_turn_ids.add(completed_turn_id)
                if completed_turn_id == active_turn_id or not completed_turn_id:
                    active_turn_id = ""
                last_task_event = "task_complete"
                open_calls.clear()
            continue

        if event_type == "response_item":
            item_type = str(payload.get("type") or "")
            last_kind = item_type or event_type

            if item_type in {"function_call", "custom_tool_call"}:
                call_id = str(payload.get("call_id") or payload.get("id") or len(open_calls))
                tool_name = str(payload.get("name") or "tool")
                if str(payload.get("status") or "").lower() == "completed":
                    open_calls.pop(call_id, None)
                else:
                    open_calls[call_id] = tool_name
                last_tool = tool_name
            elif item_type in {"function_call_output", "custom_tool_call_output"}:
                call_id = str(payload.get("call_id") or "")
                open_calls.pop(call_id, None)
            elif item_type:
                last_tool = ""
        elif event_type:
            payload_type = str(payload.get("type") or "")
            last_kind = payload_type or event_type

    if open_calls:
        last_tool = next(reversed(open_calls.values()))

    if active_turn_id and active_turn_id in completed_turn_ids:
        active_turn_id = ""

    return {
        "last_kind": last_kind,
        "open_tool": last_tool,
        "last_task_event": last_task_event,
        "turn_active": "1" if active_turn_id else "",
    }


def format_age(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    if seconds < 1:
        return "刚刚"
    if seconds < 60:
        return f"{int(seconds)} 秒前"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} 分钟前"
    hours = int(minutes // 60)
    if hours < 24:
        return f"{hours} 小时前"
    return f"{int(hours // 24)} 天前"


def short_id(thread_id: str) -> str:
    if not thread_id:
        return ""
    return f"{thread_id[:8]}...{thread_id[-4:]}"


def trim_text(value: str, limit: int) -> str:
    value = " ".join((value or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def clean_windows_path(value: str) -> str:
    return value.replace("\\\\?\\", "").strip()


def workspace_label(cwd: str, fallback: str) -> str:
    cwd = clean_windows_path(cwd)
    if cwd:
        name = Path(cwd).name
        if name:
            return f"工作区：{name}"
    if fallback:
        return f"线程：{fallback}"
    return "Codex"


def describe_tool_action(tool_name: str) -> str:
    tool_name = " ".join((tool_name or "").split())
    if not tool_name:
        return "调用工具"
    if tool_name in {"shell_command", "functions.shell_command"} or tool_name.endswith("_command"):
        return f"运行 {tool_name} 命令"
    return f"调用 {tool_name} 工具"


class CodexStatusDetector:
    def __init__(
        self,
        codex_home: Path,
        thread_id: str = "",
        active_seconds: int = 5,
        ui_active_seconds: int = 15 * 60,
        tool_grace_seconds: int = 8,
        stale_seconds: int = 15 * 60,
    ) -> None:
        self.codex_home = codex_home
        self.thread_id = thread_id
        self.active_seconds = active_seconds
        self.ui_active_seconds = ui_active_seconds
        self.tool_grace_seconds = tool_grace_seconds
        self.stale_seconds = stale_seconds

    def snapshot(self) -> Snapshot:
        style = MODE_STYLE["offline"]
        session = newest_session_file(self.codex_home, self.thread_id)
        if not session:
            return Snapshot(
                mode="offline",
                label=style["label"],
                color=style["color"],
                detail=style["detail"],
                thread_id="",
                title="",
                age="",
                session_path="",
                source="none",
                updated_at=None,
            )

        stat = safe_stat(session)
        session_mtime = stat.st_mtime if stat else 0
        thread_id = self.thread_id or parse_thread_id(session)
        thread_info = load_thread_info(self.codex_home, thread_id)
        log_info = load_latest_log(self.codex_home, thread_id)
        app_activity = load_app_server_activity(self.codex_home)
        events = summarize_events(load_tail_events(session))

        state_mtime = 0.0
        updated_at_ms = thread_info.get("updated_at_ms")
        if isinstance(updated_at_ms, (int, float)):
            state_mtime = float(updated_at_ms) / 1000

        latest_log = log_info.get("latest") or {}
        log_mtime = float(latest_log.get("ts") or 0)
        app_log_mtime = float(app_activity.get("latest_ts") or 0)
        app_active_ts = float(app_activity.get("last_active_ts") or 0)
        last_update = max(session_mtime, state_mtime, log_mtime, app_log_mtime)
        age_seconds = max(0.0, time.time() - last_update) if last_update else None

        mode = "waiting"
        source = "session"

        recent_error = False
        error_log = log_info.get("error") or {}
        if error_log:
            error_age = time.time() - float(error_log.get("ts") or 0)
            recent_error = error_age < max(self.active_seconds * 4, 45)

        has_task_markers = bool(events.get("last_task_event"))
        turn_active = events.get("turn_active") == "1"
        open_tool = events.get("open_tool")
        app_activity_age = time.time() - app_active_ts if app_active_ts else None
        app_turn_active = bool(
            app_activity.get("active")
            and app_activity_age is not None
            and app_activity_age <= self.ui_active_seconds
        )

        if recent_error:
            mode = "error"
            source = "logs"
        elif open_tool and (turn_active or (not has_task_markers and age_seconds is not None and age_seconds < self.tool_grace_seconds)):
            mode = "tool"
            source = "session"
        elif app_turn_active:
            mode = "working"
            source = "app_server"
        elif turn_active:
            mode = "working"
            source = "session"
        elif not has_task_markers and age_seconds is not None and age_seconds <= self.active_seconds:
            mode = "working"
            source = "logs" if log_mtime >= session_mtime else "session"
        elif age_seconds is not None and age_seconds > self.stale_seconds:
            mode = "offline"
            source = "session"

        style = MODE_STYLE[mode]
        title = (
            load_thread_name(self.codex_home, thread_id)
            or str(thread_info.get("title") or thread_info.get("preview") or "").strip()
            or short_id(thread_id)
        )
        age = format_age(age_seconds)
        detail = style["detail"]

        if mode == "tool" and open_tool:
            detail = describe_tool_action(open_tool)
        elif mode == "working":
            detail = "正在思考"
        elif mode == "waiting":
            detail = "已完成，等待你"
        elif mode == "error":
            detail = "需要查看错误"
        elif mode == "offline":
            detail = "未活动"

        return Snapshot(
            mode=mode,
            label=style["label"],
            color=style["color"],
            detail=detail,
            thread_id=thread_id,
            title=trim_text(title, 22),
            age=age,
            session_path=str(session),
            source=source,
            updated_at=last_update or None,
        )


class StatusWidget:
    def __init__(self, detector: CodexStatusDetector, interval_ms: int) -> None:
        import tkinter as tk

        self.tk = tk
        self.detector = detector
        self.interval_ms = interval_ms
        self.drag_x = 0
        self.drag_y = 0
        self.press_x = 0
        self.press_y = 0
        self.pulse = 0
        self.expanded = True
        self.expanded_width = 304
        self.collapsed_width = 64
        self.expanded_height = 112
        self.collapsed_height = 96
        self.window_height = self.expanded_height
        self.signal_width = 52
        self.signal_height = 84
        self.panel_color = "#17191c"
        self.transparent_color = "#010203"
        self.panel_items: List[int] = []
        self.panel_image = None
        self.signal_image = None

        from PIL import Image, ImageDraw, ImageTk

        self.Image = Image
        self.ImageDraw = ImageDraw
        self.ImageTk = ImageTk

        self.root = tk.Tk()
        self.root.title("Codex Status")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=self.transparent_color)
        try:
            self.root.attributes("-transparentcolor", self.transparent_color)
            self.root.attributes("-alpha", 0.94)
        except tk.TclError:
            self.root.attributes("-alpha", 0.94)

        screen_w = self.root.winfo_screenwidth()
        self.root.geometry(f"{self.expanded_width}x{self.window_height}+{screen_w - self.expanded_width - 24}+24")

        self.frame = tk.Canvas(self.root, bg=self.transparent_color, highlightthickness=0, bd=0)
        self.frame.pack(fill="both", expand=True)

        self.signal = tk.Canvas(
            self.frame,
            width=self.signal_width,
            height=self.signal_height,
            bg=self.panel_color,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.signal.place(x=16, y=14)
        self.signal_item = self.signal.create_image(0, 0, anchor="nw")

        self.label_var = tk.StringVar(value="Codex")
        self.title_var = tk.StringVar(value="")
        self.detail_var = tk.StringVar(value="")

        font_main = ("Microsoft YaHei UI", 12, "bold")
        font_sub = ("Microsoft YaHei UI", 9)

        self.label = tk.Label(
            self.frame,
            textvariable=self.label_var,
            bg=self.panel_color,
            fg="#f8f9fa",
            font=font_main,
            anchor="w",
        )
        self.label.place(x=94, y=20, width=166, height=24)

        self.title = tk.Label(
            self.frame,
            textvariable=self.title_var,
            bg=self.panel_color,
            fg="#ced4da",
            font=font_sub,
            anchor="w",
        )
        self.title.place(x=94, y=48, width=178, height=18)

        self.detail = tk.Label(
            self.frame,
            textvariable=self.detail_var,
            bg=self.panel_color,
            fg="#868e96",
            font=font_sub,
            anchor="w",
        )
        self.detail.place(x=94, y=70, width=178, height=18)

        self.close = tk.Label(
            self.frame,
            text="×",
            bg=self.panel_color,
            fg="#868e96",
            font=("Segoe UI", 13),
            cursor="hand2",
        )
        self.close.place(x=276, y=8, width=18, height=18)
        self.close.bind("<Button-1>", lambda _event: self.root.destroy())

        for widget in (self.root, self.frame, self.signal, self.label, self.title, self.detail):
            widget.bind("<ButtonPress-1>", self.begin_drag)
            widget.bind("<B1-Motion>", self.drag)
        self.signal.bind("<ButtonRelease-1>", self.toggle_on_signal_click)

        self.apply_layout()
        self.refresh()

    def rounded_rect(
        self,
        canvas: Any,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        radius: int,
        **kwargs: Any,
    ) -> List[int]:
        items = [
            canvas.create_arc(x1, y1, x1 + radius * 2, y1 + radius * 2, start=90, extent=90, **kwargs),
            canvas.create_arc(x2 - radius * 2, y1, x2, y1 + radius * 2, start=0, extent=90, **kwargs),
            canvas.create_arc(x2 - radius * 2, y2 - radius * 2, x2, y2, start=270, extent=90, **kwargs),
            canvas.create_arc(x1, y2 - radius * 2, x1 + radius * 2, y2, start=180, extent=90, **kwargs),
            canvas.create_rectangle(x1 + radius, y1, x2 - radius, y2, **kwargs),
            canvas.create_rectangle(x1, y1 + radius, x2, y2 - radius, **kwargs),
        ]
        return items

    def rgba(self, color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
        color = color.lstrip("#")
        return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16), alpha)

    def render_panel_image(self, width: int, height: int) -> Any:
        scale = 4
        image = self.Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
        draw = self.ImageDraw.Draw(image)

        def box(values: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
            return tuple(v * scale for v in values)

        draw.rounded_rectangle(
            box((2, 4, width - 2, height - 2)),
            radius=16 * scale,
            fill=(0, 0, 0, 76),
        )
        draw.rounded_rectangle(
            box((1, 1, width - 3, height - 4)),
            radius=15 * scale,
            fill=self.rgba(self.panel_color, 226),
            outline=self.rgba("#3b424c", 210),
            width=scale,
        )
        draw.rounded_rectangle(
            box((5, 5, width - 6, height - 7)),
            radius=12 * scale,
            outline=self.rgba("#252c35", 170),
            width=scale,
        )
        draw.line(
            (18 * scale, 6 * scale, max(18, width - 24) * scale, 6 * scale),
            fill=self.rgba("#4b5561", 125),
            width=scale,
        )

        image = image.resize((width, height), self.Image.Resampling.LANCZOS)
        return self.ImageTk.PhotoImage(image)

    def draw_panel(self, width: int, height: int) -> None:
        for item in self.panel_items:
            self.frame.delete(item)

        self.panel_items = []
        self.panel_image = self.render_panel_image(width, height)
        self.panel_items.append(self.frame.create_image(0, 0, image=self.panel_image, anchor="nw"))
        self.frame.tag_lower(self.panel_items[-1])

    def render_signal_image(self, active_light: str, pulse_on: bool) -> Any:
        scale = 4
        width = self.signal_width
        height = self.signal_height
        image = self.Image.new("RGBA", (width * scale, height * scale), self.rgba(self.panel_color, 255))
        draw = self.ImageDraw.Draw(image)

        def box(values: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
            return tuple(v * scale for v in values)

        draw.rounded_rectangle(box((4, 1, width - 4, height - 1)), radius=12 * scale, fill=self.rgba("#07090c"), outline=self.rgba("#262d36"), width=scale)
        draw.rounded_rectangle(box((7, 4, width - 7, height - 4)), radius=10 * scale, fill=self.rgba("#10151b"), outline=self.rgba("#3b444f"), width=scale)
        draw.rounded_rectangle(box((11, 8, width - 11, height - 8)), radius=8 * scale, fill=self.rgba("#151b22"), outline=self.rgba("#07090c"), width=scale)
        draw.line((15 * scale, 10 * scale, (width - 15) * scale, 10 * scale), fill=self.rgba("#47525f"), width=scale)
        draw.line((15 * scale, (height - 10) * scale, (width - 15) * scale, (height - 10) * scale), fill=self.rgba("#050607"), width=scale)

        for name, center_y in (("red", 18), ("yellow", 42), ("green", 66)):
            colors = TRAFFIC_LIGHTS[name]
            is_active = name == active_light
            center_x = width // 2

            if is_active and pulse_on:
                draw.ellipse(box((center_x - 13, center_y - 13, center_x + 13, center_y + 13)), fill=self.rgba(colors["glow"], 95))

            draw.ellipse(box((center_x - 11, center_y - 11, center_x + 11, center_y + 11)), fill=self.rgba("#07090b"), outline=self.rgba("#040506"), width=scale)
            draw.ellipse(box((center_x - 9, center_y - 9, center_x + 9, center_y + 9)), fill=self.rgba("#121820"), outline=self.rgba("#3b444e"), width=scale)
            draw.ellipse(
                box((center_x - 7, center_y - 7, center_x + 7, center_y + 7)),
                fill=self.rgba(colors["active" if is_active else "dim"]),
                outline=self.rgba("#fff3bf" if is_active and name == "yellow" else "#08090b"),
                width=scale,
            )
            draw.ellipse(
                box((center_x - 4, center_y - 4, center_x + 4, center_y + 4)),
                fill=self.rgba(colors["core" if is_active else "glass"]),
            )
            draw.ellipse(box((center_x - 5, center_y - 6, center_x + 1, center_y)), fill=self.rgba("#fff9db" if is_active else "#59616b", 210))
            draw.ellipse(box((center_x - 3, center_y - 4, center_x - 1, center_y - 2)), fill=self.rgba("#ffffff" if is_active else "#858b94", 210))

        image = image.resize((width, height), self.Image.Resampling.LANCZOS)
        return self.ImageTk.PhotoImage(image)

    def begin_drag(self, event: Any) -> None:
        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()
        self.press_x = event.x_root
        self.press_y = event.y_root

    def drag(self, event: Any) -> None:
        self.root.geometry(f"+{event.x_root - self.drag_x}+{event.y_root - self.drag_y}")

    def apply_layout(self) -> None:
        width = self.expanded_width if self.expanded else self.collapsed_width
        height = self.expanded_height if self.expanded else self.collapsed_height
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        screen_w = self.root.winfo_screenwidth()
        x = min(max(0, x), max(0, screen_w - width - 8))
        self.window_height = height
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.frame.config(width=width, height=height)
        self.draw_panel(width, height)

        if self.expanded:
            self.signal.place(x=16, y=14)
            self.label.place(x=94, y=20, width=166, height=24)
            self.title.place(x=94, y=48, width=178, height=18)
            self.detail.place(x=94, y=70, width=178, height=18)
            self.close.place(x=276, y=8, width=18, height=18)
        else:
            self.signal.place(x=(width - self.signal_width) // 2, y=(height - self.signal_height) // 2)
            self.label.place_forget()
            self.title.place_forget()
            self.detail.place_forget()
            self.close.place_forget()

    def toggle_on_signal_click(self, event: Any) -> None:
        moved_x = abs(event.x_root - self.press_x)
        moved_y = abs(event.y_root - self.press_y)
        if moved_x > 4 or moved_y > 4:
            return

        self.expanded = not self.expanded
        self.apply_layout()

    def update_signal(self, mode: str) -> None:
        active_light = SIGNAL_BY_MODE.get(mode, "")
        pulse_on = self.pulse % 2 == 0 and mode in {"working", "tool"}
        self.signal_image = self.render_signal_image(active_light, pulse_on)
        self.signal.itemconfig(self.signal_item, image=self.signal_image)

    def refresh(self) -> None:
        snapshot = self.detector.snapshot()
        self.label_var.set(snapshot.label)
        self.title_var.set(snapshot.title or "Codex")
        self.detail_var.set(snapshot.detail)

        self.update_signal(snapshot.mode)
        self.pulse += 1

        self.root.after(self.interval_ms, self.refresh)

    def run(self) -> None:
        self.root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex desktop status light widget")
    parser.add_argument("--codex-home", default="", help="Codex home directory, defaults to %%USERPROFILE%%\\.codex")
    parser.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID", ""), help="Thread id to follow")
    parser.add_argument("--interval", type=float, default=0.5, help="Refresh interval in seconds")
    parser.add_argument("--active-seconds", type=int, default=5, help="Recent activity window for working state")
    parser.add_argument("--ui-active-seconds", type=int, default=15 * 60, help="Maximum time to trust unfinished app-server activity")
    parser.add_argument("--tool-grace-seconds", type=int, default=8, help="Maximum time to keep a stale tool state")
    parser.add_argument("--stale-seconds", type=int, default=15 * 60, help="Window before a thread is considered inactive")
    parser.add_argument("--once", action="store_true", help="Print one status snapshot as JSON and exit")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
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

    try:
        widget = StatusWidget(detector, max(250, int(args.interval * 1000)))
    except Exception as exc:
        print(f"Failed to start widget: {exc}", file=sys.stderr)
        return 1

    widget.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
