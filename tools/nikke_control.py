# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp==2.3.0"]
# ///
"""Standalone NIKKE MCP control using MaaFramework's AAA input configuration."""

import argparse
import asyncio
import base64
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any
import uuid

ROOT = Path(__file__).resolve().parents[1]
WINDOW_TITLE = re.compile(r"NIKKE|勝利女神：妮姬")
SCREEN_DC, INTERCEPTION, SEIZE = 32, 512, 1
P, B, I, U, ID = C.c_void_p, C.c_uint8, C.c_int32, C.c_uint64, C.c_int64
LOG = logging.getLogger("nikke-control")


class ControlError(Exception):
    def __init__(self, code: str, message: str, input_status: str = "not_sent"):
        super().__init__(message)
        self.code, self.input_status = code, input_status


@dataclass(frozen=True)
class Window:
    hwnd: int
    pid: int
    title: str
    class_name: str
    rect: tuple[int, int, int, int]
    visible: bool = True
    minimized: bool = False
    foreground: bool = True

    @property
    def matches(self) -> bool:
        return self.class_name == "UnityWndClass" and bool(WINDOW_TITLE.search(self.title))

    @property
    def identity(self) -> tuple[int, int]:
        return self.hwnd, self.pid

    def summary(self) -> dict:
        return {"window_id": hex(self.hwnd), "pid": self.pid, "title": self.title,
                "class_name": self.class_name, "client_rect": list(self.rect),
                "visible": self.visible, "minimized": self.minimized,
                "foreground": self.foreground}


@dataclass
class Result:
    data: dict
    image: bytes | None = None


def bind(lib, name, result_type, argument_types):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = result_type, argument_types
    return fn


class Windows:
    def __init__(self):
        if os.name != "nt":
            raise ControlError("windows_required", "此工具仅支持 Windows。")
        self.user = C.WinDLL("user32", use_last_error=True)
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.shell = C.WinDLL("shell32", use_last_error=True)
        self.security = C.WinDLL("advapi32", use_last_error=True)
        for name, restype, args in (
            ("IsWindow", W.BOOL, [W.HWND]),
            ("IsWindowVisible", W.BOOL, [W.HWND]),
            ("IsIconic", W.BOOL, [W.HWND]),
            ("GetForegroundWindow", W.HWND, []),
            ("GetWindowThreadProcessId", W.DWORD, [W.HWND, C.POINTER(W.DWORD)]),
            ("GetClientRect", W.BOOL, [W.HWND, C.POINTER(W.RECT)]),
            ("ClientToScreen", W.BOOL, [W.HWND, C.POINTER(W.POINT)]),
            ("GetWindowTextW", I, [W.HWND, W.LPWSTR, I]),
            ("GetClassNameW", I, [W.HWND, W.LPWSTR, I]),
            ("ShowWindow", W.BOOL, [W.HWND, I]),
            ("SetForegroundWindow", W.BOOL, [W.HWND]),
            ("BringWindowToTop", W.BOOL, [W.HWND]),
            ("AttachThreadInput", W.BOOL, [W.DWORD, W.DWORD, W.BOOL]),
            ("PeekMessageW", W.BOOL, [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]),
            ("WindowFromPoint", W.HWND, [W.POINT]),
            ("IsChild", W.BOOL, [W.HWND, W.HWND]),
            ("SetProcessDpiAwarenessContext", W.BOOL, [P]),
        ):
            bind(self.user, name, restype, args)
        bind(self.kernel, "CreateFileW", W.HANDLE,
             [W.LPCWSTR, W.DWORD, W.DWORD, P, W.DWORD, W.DWORD, W.HANDLE])
        bind(self.kernel, "CloseHandle", W.BOOL, [W.HANDLE])
        bind(self.kernel, "GetCurrentThreadId", W.DWORD, [])
        bind(self.kernel, "OpenProcess", W.HANDLE, [W.DWORD, W.BOOL, W.DWORD])
        bind(self.security, "OpenProcessToken", W.BOOL, [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)])
        bind(self.security, "GetTokenInformation", W.BOOL, [W.HANDLE, W.DWORD, P, W.DWORD, C.POINTER(W.DWORD)])
        bind(self.shell, "IsUserAnAdmin", W.BOOL, [])
        # Set before creating framework worker threads or inspecting client geometry.
        self.user.SetProcessDpiAwarenessContext(P(-4))

    def inspect(self, hwnd: int) -> Window:
        if not self.user.IsWindow(hwnd):
            raise ControlError("window_closed", "游戏窗口已关闭，请重新连接。")
        pid, rect, point = W.DWORD(), W.RECT(), W.POINT()
        title, class_name = C.create_unicode_buffer(4096), C.create_unicode_buffer(256)
        self.user.GetWindowThreadProcessId(hwnd, C.byref(pid))
        self.user.GetWindowTextW(hwnd, title, len(title))
        self.user.GetClassNameW(hwnd, class_name, len(class_name))
        if not self.user.GetClientRect(hwnd, C.byref(rect)) or not self.user.ClientToScreen(hwnd, C.byref(point)):
            raise ControlError("window_unavailable", "无法读取游戏窗口客户区。")
        return Window(hwnd, pid.value, title.value, class_name.value,
                      (point.x, point.y, rect.right - rect.left, rect.bottom - rect.top),
                      bool(self.user.IsWindowVisible(hwnd)), bool(self.user.IsIconic(hwnd)),
                      self.user.GetForegroundWindow() == hwnd)

    def activate(self, hwnd: int):
        if self.user.IsIconic(hwnd):
            self.user.ShowWindow(hwnd, 9)  # SW_RESTORE
        if not self.user.SetForegroundWindow(hwnd):
            caller = self.kernel.GetCurrentThreadId()
            foreground = self.user.GetForegroundWindow()
            foreground_thread = self.user.GetWindowThreadProcessId(foreground, None) if foreground else 0
            target_thread = self.user.GetWindowThreadProcessId(hwnd, None)
            message, attached = W.MSG(), []
            self.user.PeekMessageW(C.byref(message), None, 0, 0, 0)
            try:
                for thread in dict.fromkeys((foreground_thread, target_thread)):
                    if thread and thread != caller and self.user.AttachThreadInput(caller, thread, True):
                        attached.append(thread)
                # Share both queues so activation of the target completes before detaching.
                top = bool(self.user.BringWindowToTop(hwnd))
                activated = bool(self.user.SetForegroundWindow(hwnd))
                LOG.info("Foreground activation: attached=%s raised=%s activated=%s", attached, top, activated)
            finally:
                for thread in reversed(attached):
                    self.user.AttachThreadInput(caller, thread, False)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            state = self.inspect(hwnd)
            if state.foreground and state.visible and not state.minimized:
                return
            time.sleep(0.02)
        target = self.inspect(hwnd)
        if self.process_elevated(os.getpid()) is False and self.process_elevated(target.pid) is True:
            raise ControlError("activation_failed", "NIKKE 正以管理员权限运行，当前控制进程为普通权限，Windows 拒绝激活窗口。"
                               "请通过 nikke_cli.py session 完成 UAC 管理员授权，再重新连接。")
        raise ControlError("activation_failed", "无法激活游戏窗口，请将 NIKKE 切到前台后重新观察。")

    def process_elevated(self, pid: int) -> bool | None:
        process = self.kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        token = W.HANDLE()
        try:
            if not process or not self.security.OpenProcessToken(process, 8, C.byref(token)):  # TOKEN_QUERY
                return None
            elevated, size = W.DWORD(), W.DWORD()
            if not self.security.GetTokenInformation(token, 20, C.byref(elevated), C.sizeof(elevated), C.byref(size)):
                return None
            return bool(elevated.value)  # TokenElevation
        finally:
            if token.value:
                self.kernel.CloseHandle(token)
            if process:
                self.kernel.CloseHandle(process)

    def diagnostics(self) -> dict:
        devices = {}
        for label, index in (("keyboard", 0), ("mouse", 10)):
            handle = self.kernel.CreateFileW(fr"\\.\interception{index:02}", 0x80000000, 0, None, 3, 0, None)
            accessible = handle != P(-1).value
            error = 0 if accessible else C.get_last_error()
            if accessible:
                self.kernel.CloseHandle(handle)
            devices[label] = {"accessible": accessible, "win32_error": error}
        return {"is_admin": bool(self.shell.IsUserAnAdmin()), "driver_access": devices}

    def point_belongs(self, window: Window, x: int, y: int, width: int, height: int) -> bool:
        left, top, raw_width, raw_height = window.rect
        # Hit-test only. Actual input still uses the unmodified screenshot coordinates.
        screen_x = left + (2 * x * raw_width + width) // (2 * width)
        screen_y = top + (2 * y * raw_height + height) // (2 * height)
        hit = self.user.WindowFromPoint(W.POINT(screen_x, screen_y))
        return hit == window.hwnd or bool(hit and self.user.IsChild(window.hwnd, hit))


def resolve_runtime(directory: Path | None) -> Path:
    candidates = [Path(directory)] if directory is not None else [ROOT / "deps/bin", ROOT / "install/maafw"]
    required = ("MaaFramework.dll", "MaaToolkit.dll", "MaaWin32ControlUnit.dll")
    for candidate in candidates:
        if all((candidate / name).is_file() for name in required):
            return candidate.resolve()
    raise ControlError("runtime_missing", "找不到完整的 MaaFramework DLL 目录，请使用 --maa-dir 指定。")


class MaaRuntime:
    """Own one native controller; never enqueue behind a timed-out request."""

    def __init__(self, directory: Path | None = None):
        if os.name != "nt":
            raise ControlError("windows_required", "此工具仅支持 Windows。")
        self.directory = resolve_runtime(directory)
        self.cookie = os.add_dll_directory(str(self.directory))
        self.api = C.CDLL(str(self.directory / "MaaFramework.dll"))
        bind(self.api, "MaaGlobalSetOption", B, [I, P, U])
        level = I(0)
        if not self.api.MaaGlobalSetOption(4, C.byref(level), C.sizeof(level)):
            raise ControlError("log_setup_failed", "无法关闭框架 stdout 日志。")
        log_dir = ROOT / ".cache/nikke-control/logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        encoded_dir = str(log_dir).encode("utf-8")
        if not self.api.MaaGlobalSetOption(1, C.c_char_p(encoded_dir), len(encoded_dir)):
            raise ControlError("log_setup_failed", "无法设置框架日志目录。")
        self.toolkit = C.CDLL(str(self.directory / "MaaToolkit.dll"))
        signatures = {
            "MaaVersion": (C.c_char_p, []),
            "MaaWin32ControllerCreate": (P, [P, U, U, U]),
            "MaaControllerDestroy": (None, [P]),
            "MaaControllerSetOption": (B, [P, I, P, U]),
            "MaaControllerPostConnection": (ID, [P]),
            "MaaControllerPostScreencap": (ID, [P]),
            "MaaControllerPostClickV2": (ID, [P, I, I, I, I]),
            "MaaControllerPostSwipe": (ID, [P, I, I, I, I, I]),
            "MaaControllerPostClickKey": (ID, [P, I]),
            "MaaControllerPostInactive": (ID, [P]),
            "MaaControllerStatus": (I, [P, ID]),
            "MaaControllerConnected": (B, [P]),
            "MaaControllerCachedImage": (B, [P, P]),
            "MaaControllerGetResolution": (B, [P, C.POINTER(I), C.POINTER(I)]),
            "MaaImageBufferCreate": (P, []),
            "MaaImageBufferDestroy": (None, [P]),
            "MaaImageBufferWidth": (I, [P]),
            "MaaImageBufferHeight": (I, [P]),
            "MaaImageBufferGetEncoded": (P, [P]),
            "MaaImageBufferGetEncodedSize": (U, [P]),
        }
        for name, (result, args) in signatures.items():
            bind(self.api, name, result, args)
        for name, result, args in (
            ("ListCreate", P, []), ("ListDestroy", None, [P]),
            ("FindAll", B, [P]), ("ListSize", U, [P]),
            ("ListAt", P, [P, U]), ("GetHandle", P, [P]),
        ):
            bind(self.toolkit, "MaaToolkitDesktopWindow" + name, result, args)
        self.version = self.api.MaaVersion().decode("utf-8")
        self.controller = None
        self.pending_id = 0
        self.timeout = 10.0

    def window_handles(self) -> list[int]:
        api = self.toolkit
        buffer = api.MaaToolkitDesktopWindowListCreate()
        if not buffer:
            raise ControlError("window_list_failed", "无法创建窗口列表。")
        try:
            if not api.MaaToolkitDesktopWindowFindAll(buffer):
                raise ControlError("window_list_failed", "窗口枚举失败。")
            return [int(api.MaaToolkitDesktopWindowGetHandle(api.MaaToolkitDesktopWindowListAt(buffer, i)))
                    for i in range(api.MaaToolkitDesktopWindowListSize(buffer))]
        finally:
            api.MaaToolkitDesktopWindowListDestroy(buffer)

    def ensure_idle(self):
        if self.pending_id:
            status = self.api.MaaControllerStatus(self.controller, self.pending_id)
            if status in (1000, 2000):
                raise ControlError("request_pending", "上次框架请求仍在执行，请稍后重新观察；不要重发输入。")
            self.pending_id = 0

    def _post(self, name: str, *args, input_action: bool = False):
        self.ensure_idle()
        request_id = getattr(self.api, name)(self.controller, *args)
        if request_id <= 0:
            raise ControlError("request_rejected", "框架未接受请求。")
        self.pending_id = request_id
        deadline = time.monotonic() + self.timeout
        while True:
            status = self.api.MaaControllerStatus(self.controller, request_id)
            if status not in (1000, 2000):
                self.pending_id = 0
                if status != 3000:
                    raise ControlError("request_failed", "框架请求失败；输入可能已部分执行。" if input_action else "框架请求失败。",
                                       "unknown" if input_action else "not_sent")
                return
            if time.monotonic() >= deadline:
                raise ControlError("request_timeout", "框架请求超时；未取消原请求，不要重复输入。",
                                   "unknown" if input_action else "not_sent")
            time.sleep(0.01)

    def connected(self) -> bool:
        return bool(self.controller and self.api.MaaControllerConnected(self.controller))

    def connect(self, hwnd: int):
        self.ensure_idle()
        self.controller = self.api.MaaWin32ControllerCreate(hwnd, SCREEN_DC, INTERCEPTION, SEIZE)
        if not self.controller:
            raise ControlError("controller_create_failed", "创建 AAA 控制器失败，请检查驱动、DLL 与权限。")
        length, raw = I(1280), C.c_bool(False)
        if not (self.api.MaaControllerSetOption(self.controller, 1, C.byref(length), C.sizeof(length))
                and self.api.MaaControllerSetOption(self.controller, 3, C.byref(raw), C.sizeof(raw))):
            raise ControlError("controller_setup_failed", "无法设置截图坐标系。")
        self._post("MaaControllerPostConnection")

    def screenshot(self) -> tuple[dict, bytes]:
        self._post("MaaControllerPostScreencap")
        buffer = self.api.MaaImageBufferCreate()
        if not buffer:
            raise ControlError("screenshot_failed", "无法创建截图缓冲区。")
        try:
            if not self.api.MaaControllerCachedImage(self.controller, buffer):
                raise ControlError("screenshot_failed", "无法取得框架截图。")
            width, height = self.api.MaaImageBufferWidth(buffer), self.api.MaaImageBufferHeight(buffer)
            pointer = self.api.MaaImageBufferGetEncoded(buffer)
            size = self.api.MaaImageBufferGetEncodedSize(buffer)
            raw_width, raw_height = I(), I()
            if not pointer or not size or width <= 0 or height <= 0 or not self.api.MaaControllerGetResolution(
                    self.controller, C.byref(raw_width), C.byref(raw_height)):
                raise ControlError("screenshot_failed", "截图或原始分辨率无效。")
            return ({"width": width, "height": height, "raw_width": raw_width.value, "raw_height": raw_height.value},
                    C.string_at(pointer, size))
        finally:
            self.api.MaaImageBufferDestroy(buffer)

    def click(self, x: int, y: int, button: int):
        self._post("MaaControllerPostClickV2", x, y, button, 0, input_action=True)

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: int):
        self._post("MaaControllerPostSwipe", x1, y1, x2, y2, duration, input_action=True)

    def press_key(self, keycode: int):
        self._post("MaaControllerPostClickKey", keycode, input_action=True)

    def close(self):
        self.ensure_idle()
        if self.controller:
            try:
                self._post("MaaControllerPostInactive")
            finally:
                if not self.pending_id:
                    self.api.MaaControllerDestroy(self.controller)
                    self.controller = None


KEYS = {"space": 0x20, "enter": 0x0D, "return": 0x0D, "escape": 0x1B, "esc": 0x1B,
        "tab": 0x09, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28}


def key_code(key: str) -> int:
    if not isinstance(key, str):
        raise ControlError("invalid_key", "key 必须是单个字母、数字或支持的按键名称。")
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key.upper())
    if key.lower() in KEYS:
        return KEYS[key.lower()]
    raise ControlError("invalid_key", "不支持该按键；可用字母、数字、space、enter、escape、tab 和方向键。")


class NikkeControl:
    def __init__(self, runtime=None, windows=None, maa_dir: Path | None = None):
        self.runtime, self.windows, self.maa_dir = runtime, windows, maa_dir
        self.window: Window | None = None
        self.snapshot: dict | None = None
        self.snapshot_window: Window | None = None
        self.lock = threading.RLock()
        self.event_lock = threading.RLock()
        self.owner = "manual"
        self.battle_runner = None
        self.event_sink = None

    def _load(self):
        if self.windows is None:
            self.windows = Windows()
        if self.runtime is None:
            self.runtime = MaaRuntime(self.maa_dir)

    def call(self, operation: str, **params) -> Result:
        with self.lock:
            try:
                if self.owner != "manual" and operation not in ("status", "stop"):
                    raise ControlError("battle_busy", "战斗正在运行或停止，请先 stop 并等待 battle.finished。")
                actions = {"status": self.status, "list_windows": self.list_windows, "connect": self.connect,
                           "observe": self.observe, "click": self.click, "drag": self.drag,
                           "press_key": self.press_key, "disconnect": self.disconnect,
                           "battle": self.battle, "stop": self.stop}
                return actions[operation](**params)
            except ControlError as exc:
                return Result({"ok": False, "error": {"code": exc.code, "message": str(exc)},
                               "input_status": exc.input_status})
            except (OSError, AttributeError) as exc:
                LOG.exception("Native runtime unavailable")
                return Result({"ok": False, "error": {"code": "runtime_unavailable", "message": str(exc)},
                               "input_status": "not_sent"})

    def status(self) -> Result:
        self._load()
        if self.owner == "manual":
            try:
                self.runtime.ensure_idle()
            except ControlError as exc:
                if exc.code != "request_pending":
                    raise
        current = None
        if self.window is not None:
            try:
                observed = self.windows.inspect(self.window.hwnd)
                if observed.identity == self.window.identity and observed.matches:
                    current = observed
            except ControlError:
                pass
        return Result({"ok": True, "framework_version": self.runtime.version,
                       "maa_dir": str(self.runtime.directory), "connected": self.runtime.connected(),
                       "pending_request": self.runtime.pending_id or None,
                       "controller_owner": self.owner,
                       "battle": dict(self.battle_runner.current) if self.battle_runner and self.battle_runner.current else None,
                       "last_battle": self.battle_runner.latest if self.battle_runner else None,
                       "window": current.summary() if current else None,
                       "target_elevated": self.windows.process_elevated(current.pid) if current else None,
                       "screencap": "ScreenDC", "mouse": "Interception", "keyboard": "Seize",
                       **self.windows.diagnostics()})

    def list_windows(self) -> Result:
        self._load()
        windows = []
        for hwnd in self.runtime.window_handles():
            try:
                window = self.windows.inspect(hwnd)
                if window.matches:
                    windows.append(window.summary())
            except ControlError:
                continue  # A window can close while the desktop list is being read.
        return Result({"ok": True, "windows": windows})

    def connect(self, window_id: str | None = None) -> Result:
        candidates = self.list_windows().data["windows"]
        if window_id is not None:
            candidates = [w for w in candidates if w["window_id"] == window_id]
        if len(candidates) != 1:
            raise ControlError("window_not_found" if not candidates else "multiple_windows",
                               "未找到目标 NIKKE 窗口。" if not candidates else "存在多个 NIKKE 窗口，请从窗口列表选择 window_id。")
        self.disconnect()
        self.window = self.windows.inspect(int(candidates[0]["window_id"], 16))
        self.runtime.connect(self.window.hwnd)
        return self.observe()

    def _current_window(self) -> Window:
        if self.window is None or not self.runtime.connected():
            raise ControlError("not_connected", "请先调用 nikke_connect。")
        self.runtime.ensure_idle()
        current = self.windows.inspect(self.window.hwnd)
        if current.identity != self.window.identity or not current.matches:
            self.snapshot = None
            raise ControlError("window_changed", "窗口身份已变化，请重新连接。")
        return current

    def _capture(self, activate: bool) -> Result:
        self.snapshot = None
        current = self._current_window()
        if activate:
            self.windows.activate(current.hwnd)
            current = self._current_window()
        self._check_visible(current)
        info, image = self.runtime.screenshot()
        after = self._current_window()
        if after.rect != current.rect:
            raise ControlError("window_changed", "截图期间窗口位置或尺寸变化，请重新观察。")
        self._check_visible(after)
        self.snapshot = {"snapshot_id": uuid.uuid4().hex, "window_id": hex(after.hwnd), **info,
                         "captured_at": datetime.now().astimezone().isoformat()}
        self.snapshot_window = after
        return Result({"ok": True, **self.snapshot}, image)

    @staticmethod
    def _check_visible(window: Window):
        if not window.visible or window.minimized or not window.foreground:
            raise ControlError("window_not_foreground", "游戏不在可见前台，请调用 nikke_observe 重新观察。")

    @staticmethod
    def _wait_seconds(wait_ms: int) -> float:
        if type(wait_ms) is not int or not 0 <= wait_ms <= 10000:
            raise ControlError("invalid_wait", "wait_ms 必须是 0～10000 的整数。")
        return wait_ms / 1000

    def observe(self, wait_ms: int = 0) -> Result:
        delay = self._wait_seconds(wait_ms)
        if delay:
            time.sleep(delay)
        return self._capture(True)

    def _validate(self, snapshot_id: str, points: tuple[tuple[int, int], ...] = ()):
        if not self.snapshot or snapshot_id != self.snapshot["snapshot_id"]:
            raise ControlError("stale_snapshot", "截图已过期，请调用 nikke_observe，不要重发旧操作。")
        for x, y in points:
            if type(x) is not int or type(y) is not int or not (0 <= x < self.snapshot["width"] and 0 <= y < self.snapshot["height"]):
                raise ControlError("invalid_coordinates", "坐标必须是返回截图范围内的整数。")
        current = self._current_window()
        if current.rect != self.snapshot_window.rect:
            self.snapshot = None
            raise ControlError("window_changed", "窗口移动或尺寸变化，请重新观察。")
        try:
            self._check_visible(current)
        except ControlError:
            self.snapshot = None
            raise
        for x, y in points:
            if not self.windows.point_belongs(current, x, y, self.snapshot["width"], self.snapshot["height"]):
                self.snapshot = None
                raise ControlError("point_obstructed", "目标坐标被其他窗口遮挡或不在可见屏幕内，请重新观察。")
        self.snapshot = None  # Consume before submitting; failure never permits blind replay.

    def _after_input(self) -> Result:
        try:
            result = self._capture(False)
            result.data.update(input_status="completed", observation_status="completed")
            return result
        except (ControlError, OSError, AttributeError) as exc:
            return Result({"ok": False, "input_status": "completed", "observation_status": "failed",
                           "error": {"code": getattr(exc, "code", "screenshot_failed"), "message": str(exc)}})

    def _send(self, snapshot_id, operation, *args, points=(), wait_ms=0, capture=True) -> Result:
        delay = self._wait_seconds(wait_ms)
        if type(capture) is not bool:
            raise ControlError("invalid_capture", "capture 必须是布尔值。")
        self._validate(snapshot_id, points)
        try:
            getattr(self.runtime, operation)(*args)
        except (OSError, AttributeError) as exc:
            raise ControlError("native_input_failed", str(exc), "unknown") from exc
        if delay:
            time.sleep(delay)
        if not capture:
            return Result({"ok": True, "input_status": "completed", "observation_status": "skipped"})
        return self._after_input()

    def click(self, snapshot_id: str, x: int, y: int, button: str = "left",
              wait_ms: int = 0, capture: bool = True) -> Result:
        buttons = {"left": 0, "right": 1, "middle": 2}
        if button not in buttons:
            raise ControlError("invalid_button", "button 必须是 left、right 或 middle。")
        return self._send(snapshot_id, "click", x, y, buttons[button], points=((x, y),),
                          wait_ms=wait_ms, capture=capture)

    def drag(self, snapshot_id: str, from_x: int, from_y: int, to_x: int, to_y: int,
             duration_ms: int = 500, wait_ms: int = 0, capture: bool = True) -> Result:
        if type(duration_ms) is not int or not 1 <= duration_ms <= 5000:
            raise ControlError("invalid_duration", "duration_ms 必须是 1～5000 的整数。")
        return self._send(snapshot_id, "drag", from_x, from_y, to_x, to_y, duration_ms,
                          points=((from_x, from_y), (to_x, to_y)), wait_ms=wait_ms, capture=capture)

    def press_key(self, snapshot_id: str, key: str, wait_ms: int = 0, capture: bool = True) -> Result:
        code = key_code(key)
        return self._send(snapshot_id, "press_key", code, wait_ms=wait_ms, capture=capture)

    def battle(self, snapshot_id: str) -> Result:
        self._validate(snapshot_id)
        if self.battle_runner is None:
            if __package__:
                from .nikke_battle import BattleRunner
            else:
                from nikke_battle import BattleRunner
            self.battle_runner = BattleRunner(self)
        return self.battle_runner.start(self.snapshot_window)

    def stop(self) -> Result:
        if self.battle_runner:
            return self.battle_runner.stop()
        return Result({"ok": True, "status": "idle", "controller_idle": not bool(self.runtime and self.runtime.pending_id)})

    def disconnect(self) -> Result:
        self.snapshot = None
        if self.battle_runner:
            self.battle_runner.close()
        if self.runtime is not None:
            try:
                self.runtime.close()
            finally:
                if not self.runtime.controller:
                    self.window = None
        return Result({"ok": True, "connected": False})


def create_server(control: NikkeControl):
    # Keep the controller and regression tests usable without importing the MCP SDK.
    from mcp.server import MCPServer
    from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
    from pydantic import StrictInt
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(server):
        try:
            yield
        finally:
            result = await asyncio.to_thread(control.call, "disconnect")
            if not result.data["ok"]:
                LOG.error("Controller cleanup: %s", result.data)

    server = MCPServer(
        "nikke-control",
        instructions=("Control NIKKE through this server's own screenshots and AAA input, without a separate desktop tool. "
                      "Connect first, inspect the returned image, then use its latest snapshot_id for one input. "
                      "All coordinates refer to that image. Reobserve after focus or geometry changes. "
                      "completed means the framework finished input, not that the game accepted it. "
                      "Never blindly replay unknown input or completed input whose follow-up screenshot failed."),
        lifespan=lifespan,
    )

    async def invoke(operation: str, **params) -> Any:
        result = await asyncio.to_thread(control.call, operation, **params)
        content = [TextContent(type="text", text=json.dumps(result.data, ensure_ascii=False))]
        if result.image is not None:
            content.append(ImageContent(type="image", data=base64.b64encode(result.image).decode("ascii"), mimeType="image/png"))
        return CallToolResult(content=content, structuredContent=result.data, isError=not result.data["ok"])

    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
    control_hint = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
    input_hint = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)

    @server.tool(annotations=read_only)
    async def nikke_status() -> Any:
        """检查 NIKKE AAA 运行库、驱动可访问性、权限和控制会话；不发送输入。"""
        return await invoke("status")

    @server.tool(annotations=read_only)
    async def nikke_list_windows() -> Any:
        """列出可连接的 NIKKE 窗口；多个窗口时根据返回的 window_id 选择。"""
        return await invoke("list_windows")

    @server.tool(annotations=control_hint)
    async def nikke_connect(window_id: str | None = None) -> Any:
        """连接 NIKKE 并激活窗口、返回首张截图；只有唯一候选时可省略 window_id。"""
        return await invoke("connect", window_id=window_id)

    @server.tool(annotations=control_hint)
    async def nikke_observe() -> Any:
        """激活已连接的游戏并返回截图及新 snapshot_id；观察图片后再决定输入。"""
        return await invoke("observe")

    @server.tool(annotations=input_hint)
    async def nikke_click(snapshot_id: str, x: StrictInt, y: StrictInt, button: str = "left") -> Any:
        """按最新截图坐标点击一次并返回新截图。unknown 或回图失败时不要直接重发。"""
        return await invoke("click", snapshot_id=snapshot_id, x=x, y=y, button=button)

    @server.tool(annotations=input_hint)
    async def nikke_drag(snapshot_id: str, from_x: StrictInt, from_y: StrictInt, to_x: StrictInt, to_y: StrictInt,
                         duration_ms: StrictInt = 500) -> Any:
        """按最新截图坐标拖动一次，持续 1～5000 毫秒；返回操作后的截图。"""
        return await invoke("drag", snapshot_id=snapshot_id, from_x=from_x, from_y=from_y,
                            to_x=to_x, to_y=to_y, duration_ms=duration_ms)

    @server.tool(annotations=input_hint)
    async def nikke_press_key(snapshot_id: str, key: str) -> Any:
        """单键按下并释放。支持字母、数字、space、enter、escape、tab、left/up/right/down。"""
        return await invoke("press_key", snapshot_id=snapshot_id, key=key)

    @server.tool(annotations=control_hint)
    async def nikke_disconnect() -> Any:
        """释放 AAA 控制器并清理置顶状态；请求仍在执行时不会强行销毁控制器。"""
        return await invoke("disconnect")

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maa-dir", type=Path, help="Directory containing the MaaFramework DLLs")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    create_server(NikkeControl(maa_dir=args.maa_dir)).run(transport="stdio")


if __name__ == "__main__":
    main()
