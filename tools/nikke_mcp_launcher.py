# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp==2.3.0"]
# ///
"""Launch a NIKKE control worker with Windows administrator privileges."""

import argparse
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
CONTROL = Path(__file__).with_name("nikke_control.py")
CLI = Path(__file__).with_name("nikke_cli.py")
WORKER_LOG = ROOT / ".cache/nikke-control/elevated-stderr.log"
READY = b"NIKKE-MCP-READY\n"


class LauncherError(Exception):
    pass


class ShellExecuteInfo(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("fMask", W.ULONG), ("hwnd", W.HWND),
                ("lpVerb", W.LPCWSTR), ("lpFile", W.LPCWSTR), ("lpParameters", W.LPCWSTR),
                ("lpDirectory", W.LPCWSTR), ("nShow", C.c_int), ("hInstApp", W.HINSTANCE),
                ("lpIDList", C.c_void_p), ("lpClass", W.LPCWSTR), ("hkeyClass", W.HANDLE),
                ("dwHotKey", W.DWORD), ("hMonitor", W.HANDLE), ("hProcess", W.HANDLE)]


def bind(lib, name, restype, argtypes):
    function = getattr(lib, name)
    function.restype, function.argtypes = restype, argtypes
    return function


class Native:
    def __init__(self):
        if os.name != "nt":
            raise LauncherError("NIKKE 提权启动器仅支持 Windows。")
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.shell = C.WinDLL("shell32", use_last_error=True)
        self.ole = C.WinDLL("ole32", use_last_error=True)
        bind(self.shell, "IsUserAnAdmin", W.BOOL, [])
        bind(self.shell, "ShellExecuteExW", W.BOOL, [C.POINTER(ShellExecuteInfo)])
        bind(self.ole, "CoInitializeEx", C.c_int32, [C.c_void_p, W.DWORD])
        bind(self.ole, "CoUninitialize", None, [])
        bind(self.kernel, "OpenProcess", W.HANDLE, [W.DWORD, W.BOOL, W.DWORD])
        bind(self.kernel, "GetCurrentProcess", W.HANDLE, [])
        bind(self.kernel, "DuplicateHandle", W.BOOL,
             [W.HANDLE, W.HANDLE, W.HANDLE, C.POINTER(W.HANDLE), W.DWORD, W.BOOL, W.DWORD])
        bind(self.kernel, "CloseHandle", W.BOOL, [W.HANDLE])
        bind(self.kernel, "WaitForSingleObject", W.DWORD, [W.HANDLE, W.DWORD])
        bind(self.kernel, "GetExitCodeProcess", W.BOOL, [W.HANDLE, C.POINTER(W.DWORD)])
        bind(self.kernel, "PeekNamedPipe", W.BOOL,
             [W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.POINTER(W.DWORD), C.POINTER(W.DWORD)])

    def is_admin(self):
        return bool(self.shell.IsUserAnAdmin())

    def elevate(self, arguments):
        info = ShellExecuteInfo()
        info.cbSize, info.fMask = C.sizeof(info), 0x140  # NOCLOSEPROCESS | NOASYNC
        info.lpVerb, info.lpFile = "runas", sys.executable
        info.lpParameters = subprocess.list2cmdline(arguments)
        info.lpDirectory, info.nShow = str(ROOT), 0  # SW_HIDE
        initialized = self.ole.CoInitializeEx(None, 6) >= 0
        try:
            if not self.shell.ShellExecuteExW(C.byref(info)):
                error = C.get_last_error()
                if error == 1223:
                    raise LauncherError("用户取消了 Windows UAC，NIKKE 控制进程未启动。")
                raise C.WinError(error)
            if not info.hProcess:
                raise LauncherError("Windows 未返回 NIKKE 控制进程句柄。")
            return info.hProcess
        finally:
            if initialized:
                self.ole.CoUninitialize()

    def duplicate_fd(self, parent_pid, source, mode):
        import msvcrt

        parent = self.kernel.OpenProcess(0x40, False, parent_pid)  # PROCESS_DUP_HANDLE
        if not parent:
            raise C.WinError(C.get_last_error())
        duplicate = W.HANDLE()
        try:
            if not self.kernel.DuplicateHandle(parent, source, self.kernel.GetCurrentProcess(),
                                               C.byref(duplicate), 0, False, 2):  # SAME_ACCESS
                raise C.WinError(C.get_last_error())
        finally:
            self.kernel.CloseHandle(parent)
        try:
            return msvcrt.open_osfhandle(duplicate.value, mode | os.O_BINARY)
        except BaseException:
            self.kernel.CloseHandle(duplicate)
            raise

    def available(self, fd):
        import msvcrt

        count = W.DWORD()
        if not self.kernel.PeekNamedPipe(msvcrt.get_osfhandle(fd), None, 0, None, C.byref(count), None):
            raise C.WinError(C.get_last_error())
        return count.value

    def exit_code(self, process):
        result = self.kernel.WaitForSingleObject(process, 0)
        if result == 258:  # WAIT_TIMEOUT
            return None
        if result != 0:
            raise C.WinError(C.get_last_error())
        code = W.DWORD()
        if not self.kernel.GetExitCodeProcess(process, C.byref(code)):
            raise C.WinError(C.get_last_error())
        return code.value

    def close(self, process):
        self.kernel.CloseHandle(process)


def write_all(fd, data):
    remaining = memoryview(data)
    while remaining:
        count = os.write(fd, remaining)
        if count <= 0:
            raise BrokenPipeError("管道写入已停止。")
        remaining = remaining[count:]


def copy_stream(source, destination):
    while data := os.read(source, 65536):
        write_all(destination, data)


def wait_ready(native, process, fd, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code = native.exit_code(process)
        if code is not None:
            raise LauncherError(f"提权进程在启动完成前退出（代码 {code}），日志：{WORKER_LOG}")
        if native.available(fd) >= len(READY):
            if os.read(fd, len(READY)) != READY:
                raise LauncherError(f"提权进程握手无效，日志：{WORKER_LOG}")
            return
        time.sleep(0.02)
    raise LauncherError(f"提权进程启动超时，日志：{WORKER_LOG}")


def run_server(maa_dir, cli=False):
    previous = sys.argv
    target = CLI if cli else CONTROL
    sys.argv = [str(target)] + (["--maa-dir", str(maa_dir)] if maa_dir else []) + (["session"] if cli else [])
    try:
        runpy.run_path(str(target), run_name="__main__")
    finally:
        sys.argv = previous


def serve_worker(native, args):
    if not native.is_admin():
        raise LauncherError("NIKKE 控制进程未取得管理员权限。")
    WORKER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with WORKER_LOG.open("a", encoding="utf-8", buffering=1) as log:
        os.dup2(log.fileno(), 2)
    sys.stderr = open(2, "w", encoding="utf-8", buffering=1, closefd=False)
    for source, standard, mode in ((args.stdin_handle, 0, os.O_RDONLY), (args.stdout_handle, 1, os.O_WRONLY)):
        fd = native.duplicate_fd(args.parent_pid, source, mode)
        try:
            os.dup2(fd, standard, inheritable=False)
        finally:
            os.close(fd)
    sys.stdin = open(0, "r", encoding="utf-8", closefd=False)
    sys.stdout = open(1, "w", encoding="utf-8", closefd=False)
    mode = "CLI" if getattr(args, "cli", False) else "MCP"
    print(f"NIKKE {mode} worker pid={os.getpid()} parent_pid={args.parent_pid} elevated=true", file=sys.stderr, flush=True)
    write_all(1, READY)
    try:
        if getattr(args, "cli", False):
            run_server(args.maa_dir, cli=True)
        else:
            run_server(args.maa_dir)
    finally:
        print(f"NIKKE {mode} worker pid={os.getpid()} stopped", file=sys.stderr, flush=True)


def bridge(native, maa_dir, cli=False):
    import msvcrt

    owned, process = set(), None
    WORKER_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        input_read, input_write = os.pipe()
        owned.update((input_read, input_write))
        output_read, output_write = os.pipe()
        owned.update((output_read, output_write))
        arguments = [str(Path(__file__).resolve()), "--worker", "--parent-pid", str(os.getpid()),
                     "--stdin-handle", str(msvcrt.get_osfhandle(input_read)),
                     "--stdout-handle", str(msvcrt.get_osfhandle(output_write))]
        if cli:
            arguments.append("--cli")
        if maa_dir:
            arguments.extend(("--maa-dir", str(maa_dir)))
        mode = "CLI" if cli else "MCP"
        print(f"NIKKE {mode} 请求 Windows UAC，仅提升控制进程；日志：{WORKER_LOG}", file=sys.stderr, flush=True)
        process = native.elevate(arguments)
        wait_ready(native, process, output_read)
        for fd in (input_read, output_write):
            os.close(fd)
            owned.remove(fd)
        msvcrt.setmode(0, os.O_BINARY)
        msvcrt.setmode(1, os.O_BINARY)

        def forward_input():
            try:
                copy_stream(0, input_write)
            except OSError:
                pass  # The worker may already have exited.
            finally:
                os.close(input_write)  # EOF reaches the worker and runs controller cleanup.

        owned.remove(input_write)  # The input thread owns this descriptor until EOF.
        threading.Thread(target=forward_input, daemon=True).start()
        copy_stream(output_read, 1)
    finally:
        for fd in owned:
            os.close(fd)
        if process is not None:
            native.close(process)


def main(argv=None):
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maa-dir", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cli", action="store_true", help=argparse.SUPPRESS)
    for name in ("parent-pid", "stdin-handle", "stdout-handle"):
        parser.add_argument("--" + name, type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    native = Native()
    if args.worker:
        if any(value is None for value in (args.parent_pid, args.stdin_handle, args.stdout_handle)):
            raise LauncherError("内部控制进程参数不完整。")
        serve_worker(native, args)
    elif native.is_admin():
        if args.cli:
            run_server(args.maa_dir, cli=True)
        else:
            run_server(args.maa_dir)
    else:
        if args.cli:
            bridge(native, args.maa_dir, cli=True)
        else:
            bridge(native, args.maa_dir)


if __name__ == "__main__":
    try:
        main()
    except (LauncherError, OSError) as error:
        print(f"NIKKE 控制进程启动失败：{error}", file=sys.stderr, flush=True)
        sys.exit(1)
