"""Behavioral checks for NIKKE control; no native input is sent."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import base64
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from tools.nikke_control import ControlError, MaaRuntime, NikkeControl, ROOT, Window, Windows, create_server, key_code


def png(width, height):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff\xff\xff" * width) * height)) + chunk(b"IEND", b""))


PNG = png(1280, 720)


class Desktop:
    def __init__(self):
        self.window = Window(0x100, 7, "NIKKE", "UnityWndClass", (100, 100, 1920, 1080))
        self.extra = []
        self.activations = []
        self.point_visible = True
        self.target_elevated = False

    def inspect(self, hwnd):
        for window in [self.window, *self.extra]:
            if window.hwnd == hwnd:
                return window
        raise ControlError("window_closed", "closed")

    def activate(self, hwnd):
        self.activations.append(hwnd)
        self.window = replace(self.window, visible=True, minimized=False, foreground=True)

    def diagnostics(self):
        return {"is_admin": False, "driver_access": {"mouse": {"accessible": True}}}

    def process_elevated(self, pid):
        return self.target_elevated

    def point_belongs(self, window, x, y, width, height):
        return self.point_visible


class Runtime:
    def __init__(self, desktop):
        self.desktop = desktop
        self.version, self.directory = "fixture", Path("fixture")
        self.controller, self.pending_id = None, 0
        self.inputs, self.connections, self.closes = [], [], []
        self.capture_error = None
        self.input_error = None
        self.capture_hook = None

    def window_handles(self):
        return [self.desktop.window.hwnd, *[w.hwnd for w in self.desktop.extra]]

    def connected(self):
        return self.controller is not None

    def ensure_idle(self):
        if self.pending_id:
            raise ControlError("request_pending", "pending")

    def connect(self, hwnd):
        self.controller = hwnd
        self.connections.append(hwnd)

    def screenshot(self):
        if self.capture_error:
            raise self.capture_error
        if self.capture_hook:
            self.capture_hook()
        return {"width": 1280, "height": 720, "raw_width": 1920, "raw_height": 1080}, PNG

    def _input(self, *action):
        self.inputs.append(action)
        if self.input_error:
            raise self.input_error

    def click(self, *args):
        self._input("click", *args)

    def drag(self, *args):
        self._input("drag", *args)

    def press_key(self, *args):
        self._input("key", *args)

    def close(self):
        self.ensure_idle()
        if self.controller is not None:
            self.closes.append(self.controller)
            self.controller = None


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.attached, self.detached = set(), []
        self.foreground, self.queue_ready = 0x200, False
        self.activation_error = None
        self.windows = object.__new__(Windows)

        def attach(caller, thread, enabled):
            self.assertEqual(caller, 10)
            if enabled:
                self.assertTrue(self.queue_ready)
                self.attached.add(thread)
            else:
                self.attached.remove(thread)
                self.detached.append(thread)
            return True

        def raise_window(hwnd):
            if self.activation_error:
                raise self.activation_error
            if self.attached == {20, 30}:
                self.foreground = hwnd
                return True
            return False

        self.windows.user = SimpleNamespace(
            IsIconic=lambda hwnd: False, SetForegroundWindow=lambda hwnd: self.foreground == hwnd,
            GetForegroundWindow=lambda: self.foreground,
            GetWindowThreadProcessId=lambda hwnd, pid: 20 if hwnd == 0x200 else 30,
            PeekMessageW=lambda *args: setattr(self, 'queue_ready', True),
            AttachThreadInput=attach, BringWindowToTop=raise_window)
        self.windows.kernel = SimpleNamespace(GetCurrentThreadId=lambda: 10)
        self.windows.inspect = lambda hwnd: Window(hwnd, 7, 'NIKKE', 'UnityWndClass', (0, 0, 1280, 720),
                                                   foreground=self.foreground == hwnd)
        self.windows.process_elevated = lambda pid: False

    def test_denied_direct_activation_uses_both_queues_and_detaches(self):
        self.windows.activate(0x100)
        self.assertEqual(self.foreground, 0x100)
        self.assertFalse(self.attached)
        self.assertEqual(self.detached, [30, 20])

    def test_activation_exception_still_detaches_all_queues(self):
        self.activation_error = OSError('native activation error')
        with self.assertRaises(OSError):
            self.windows.activate(0x100)
        self.assertFalse(self.attached)
        self.assertEqual(self.detached, [30, 20])

    def test_already_foreground_does_not_attach_or_raise_the_window(self):
        self.foreground = 0x100
        self.windows.activate(0x100)
        self.assertFalse(self.detached)
        self.assertFalse(self.queue_ready)

    def test_activation_failure_identifies_elevated_game(self):
        self.windows.user.AttachThreadInput = lambda *args: False
        self.windows.process_elevated = lambda pid: pid == 7
        with patch('tools.nikke_control.time.monotonic', side_effect=(0, 0, 2)):
            with self.assertRaises(ControlError) as raised:
                self.windows.activate(0x100)
        self.assertIn('管理员', str(raised.exception))
        self.assertEqual(raised.exception.input_status, 'not_sent')


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.desktop = Desktop()
        self.runtime = Runtime(self.desktop)
        self.control = NikkeControl(self.runtime, self.desktop)
        connected = self.control.call("connect")
        self.assertTrue(connected.data["ok"], connected.data)
        self.snapshot_id = connected.data["snapshot_id"]

    def click(self, **kwargs):
        return self.control.call("click", **{"snapshot_id": self.snapshot_id, "x": 640, "y": 360, **kwargs})

    def test_coordinates_use_returned_image_without_double_scaling(self):
        result = self.click()
        self.assertTrue(result.data["ok"])
        self.assertEqual(self.runtime.inputs, [("click", 640, 360, 0)])
        self.assertEqual(result.image, PNG)
        self.assertEqual(result.data["input_status"], "completed")
        self.assertNotEqual(result.data["snapshot_id"], self.snapshot_id)

    def test_input_without_connection_still_requires_a_snapshot(self):
        disconnected = NikkeControl()
        result = disconnected.call("click", snapshot_id="old", x=640, y=360)
        self.assertEqual(result.data["error"]["code"], "stale_snapshot")

    def test_same_snapshot_cannot_submit_twice(self):
        self.click()
        replay = self.click()
        self.assertEqual(replay.data["error"]["code"], "stale_snapshot")
        self.assertEqual(len(self.runtime.inputs), 1)

    def test_input_waits_before_its_only_follow_up_capture(self):
        with patch.object(self.runtime, "screenshot", wraps=self.runtime.screenshot) as capture:
            def settled(delay):
                self.assertEqual(delay, 0.8)
                self.assertEqual(self.runtime.inputs, [("click", 640, 360, 0)])
                self.assertEqual(capture.call_count, 0)

            with patch("tools.nikke_control.time.sleep", side_effect=settled):
                result = self.click(wait_ms=800)
            self.assertTrue(result.data["ok"], result.data)
            self.assertEqual(capture.call_count, 1)

    def test_skipping_capture_consumes_snapshot_until_reobservation(self):
        with patch.object(self.runtime, "screenshot", wraps=self.runtime.screenshot) as capture:
            result = self.click(capture=False)
            self.assertTrue(result.data["ok"], result.data)
            self.assertEqual(result.data["input_status"], "completed")
            self.assertEqual(result.data["observation_status"], "skipped")
            self.assertNotIn("snapshot_id", result.data)
            self.assertIsNone(result.image)
            self.assertIsNone(self.control.snapshot)
            self.assertEqual(self.click().data["error"]["code"], "stale_snapshot")
            self.assertEqual(capture.call_count, 0)
            with patch("tools.nikke_control.time.sleep") as sleep:
                observed = self.control.call("observe", wait_ms=500)
            sleep.assert_called_once_with(0.5)
            self.assertEqual(capture.call_count, 1)
        self.assertTrue(self.click(snapshot_id=observed.data["snapshot_id"]).data["ok"])

    def test_invalid_capture_options_never_send_or_consume_snapshot(self):
        for options in ({"wait_ms": -1}, {"wait_ms": 10001}, {"wait_ms": True},
                        {"wait_ms": 1.5}, {"capture": "false"}):
            with self.subTest(options=options):
                result = self.click(**options)
                self.assertFalse(result.data["ok"], result.data)
                self.assertEqual(result.data["input_status"], "not_sent")
                self.assertEqual(self.control.snapshot["snapshot_id"], self.snapshot_id)
        self.assertFalse(self.runtime.inputs)

    def test_skipping_capture_preserves_unknown_input_and_does_not_wait(self):
        self.runtime.input_error = ControlError("request_timeout", "timeout", "unknown")
        with patch("tools.nikke_control.time.sleep") as sleep:
            result = self.click(capture=False, wait_ms=800)
        self.assertEqual(result.data["input_status"], "unknown")
        self.assertIsNone(self.control.snapshot)
        sleep.assert_not_called()

    def test_concurrent_calls_cannot_reuse_the_snapshot(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.click(), range(2)))
        self.assertEqual(sum(r.data["ok"] for r in results), 1)
        self.assertEqual(len(self.runtime.inputs), 1)

    def test_invalid_coordinates_and_buttons_do_not_send_or_consume(self):
        for coordinates in ((-1, 0), (1280, 0), (0, 720), (1.5, 0), (True, 0)):
            with self.subTest(coordinates=coordinates):
                self.assertEqual(self.click(x=coordinates[0], y=coordinates[1]).data["input_status"], "not_sent")
        self.assertFalse(self.click(button="extra").data["ok"])
        self.assertFalse(self.runtime.inputs)
        self.assertTrue(self.click(x=1279, y=719, button="right").data["ok"])
        self.assertEqual(self.runtime.inputs, [("click", 1279, 719, 1)])

    def test_resize_move_and_process_replacement_require_new_observation(self):
        for change in ({"rect": (100, 100, 2560, 1440)}, {"rect": (150, 100, 1920, 1080)}, {"pid": 8}):
            with self.subTest(change=change):
                self.setUp()
                self.desktop.window = replace(self.desktop.window, **change)
                self.assertFalse(self.click().data["ok"])
                self.assertFalse(self.runtime.inputs)
                self.assertIsNone(self.control.snapshot)

    def test_focus_loss_never_activates_and_clicks_old_coordinates(self):
        activation_count = len(self.desktop.activations)
        self.desktop.window = replace(self.desktop.window, foreground=False)
        result = self.click()
        self.assertEqual(result.data["error"]["code"], "window_not_foreground")
        self.assertEqual(len(self.desktop.activations), activation_count)
        self.assertFalse(self.runtime.inputs)
        observed = self.control.call("observe")
        self.assertTrue(observed.data["ok"])
        self.assertTrue(self.click(snapshot_id=observed.data["snapshot_id"]).data["ok"])

    def test_failed_activation_keeps_connection_without_a_usable_snapshot(self):
        self.desktop.window = replace(self.desktop.window, foreground=False)
        activate = self.desktop.activate

        def denied(hwnd):
            raise ControlError('activation_failed', 'activation denied')

        self.desktop.activate = denied
        result = self.control.call('connect')
        self.assertEqual(result.data['error']['code'], 'activation_failed')
        self.assertTrue(self.control.call('status').data['connected'])
        self.assertIsNone(self.control.snapshot)
        self.assertFalse(self.click().data['ok'])
        self.assertFalse(self.runtime.inputs)
        self.desktop.activate = activate
        self.assertTrue(self.control.call('observe').data['ok'])

    def test_minimized_window_requires_observe(self):
        self.desktop.window = replace(self.desktop.window, minimized=True)
        self.assertFalse(self.click().data["ok"])
        self.assertTrue(self.control.call("observe").data["ok"])

    def test_obstructed_target_does_not_click_another_window(self):
        self.desktop.point_visible = False
        result = self.click()
        self.assertEqual(result.data["error"]["code"], "point_obstructed")
        self.assertFalse(self.runtime.inputs)
        self.assertIsNone(self.control.snapshot)

    def test_geometry_change_during_capture_does_not_publish_snapshot(self):
        self.runtime.capture_hook = lambda: setattr(self.desktop, "window", replace(self.desktop.window, rect=(0, 0, 1920, 1080)))
        result = self.control.call("observe")
        self.assertEqual(result.data["error"]["code"], "window_changed")
        self.assertIsNone(self.control.snapshot)

    def test_completed_input_with_failed_screenshot_is_not_reported_unsent(self):
        self.runtime.capture_error = ControlError("screenshot_failed", "capture failed")
        result = self.click()
        self.assertEqual(result.data["input_status"], "completed")
        self.assertEqual(result.data["observation_status"], "failed")
        self.assertIsNone(result.image)
        self.assertEqual(self.click().data["error"]["code"], "stale_snapshot")
        self.assertEqual(len(self.runtime.inputs), 1)

    def test_unknown_input_is_never_automatically_retried(self):
        self.runtime.input_error = ControlError("request_timeout", "timeout", "unknown")
        result = self.click()
        self.assertEqual(result.data["input_status"], "unknown")
        self.assertEqual(self.click().data["error"]["code"], "stale_snapshot")
        self.assertEqual(len(self.runtime.inputs), 1)

    def test_native_exception_during_input_preserves_unknown_outcome(self):
        self.runtime.input_error = OSError("native input failed")
        result = self.click()
        self.assertEqual(result.data["input_status"], "unknown")
        self.assertIsNone(self.control.snapshot)

    def test_native_exception_after_input_preserves_completed_outcome(self):
        self.runtime.capture_error = AttributeError("native image API failed")
        result = self.click()
        self.assertEqual(result.data["input_status"], "completed")
        self.assertEqual(result.data["observation_status"], "failed")

    def test_pending_request_blocks_capture_new_input_and_destroy(self):
        self.runtime.pending_id = 23
        self.assertFalse(self.click().data["ok"])
        self.assertFalse(self.control.call("observe").data["ok"])
        self.assertFalse(self.control.call("disconnect").data["ok"])
        self.assertFalse(self.runtime.inputs)
        self.assertFalse(self.runtime.closes)

    def test_drag_duration_and_endpoints_are_validated(self):
        args = dict(snapshot_id=self.snapshot_id, from_x=10, from_y=10, to_x=200, to_y=100)
        for duration in (0, 5001, True):
            self.assertFalse(self.control.call("drag", **args, duration_ms=duration).data["ok"])
        self.assertFalse(self.runtime.inputs)
        self.assertTrue(self.control.call("drag", **args, duration_ms=1000).data["ok"])
        self.assertEqual(self.runtime.inputs, [("drag", 10, 10, 200, 100, 1000)])

    def test_key_names_are_mapped_and_combinations_rejected(self):
        for key in ("Win", "Ctrl+a", "你好", "", 13):
            self.assertFalse(self.control.call("press_key", snapshot_id=self.snapshot_id, key=key).data["ok"])
        self.assertFalse(self.runtime.inputs)
        self.assertTrue(self.control.call("press_key", snapshot_id=self.snapshot_id, key="Esc").data["ok"])
        self.assertEqual(self.runtime.inputs, [("key", 0x1B)])
        self.assertEqual(key_code("a"), 0x41)

    def test_multiple_matching_windows_require_explicit_selection(self):
        self.desktop.extra.append(replace(self.desktop.window, hwnd=0x200, pid=8))
        result = self.control.call("connect")
        self.assertEqual(result.data["error"]["code"], "multiple_windows")
        self.assertEqual(self.runtime.connections, [0x100])

    def test_non_game_window_is_not_a_connection_candidate(self):
        self.desktop.window = replace(self.desktop.window, title="Other app")
        self.assertEqual(self.control.call("connect").data["error"]["code"], "window_not_found")

    def test_reconnect_invalidates_previous_snapshot(self):
        fresh = self.control.call("connect", window_id="0x100")
        self.assertTrue(fresh.data["ok"])
        self.assertFalse(self.click().data["ok"])

    def test_disconnect_is_idempotent_and_observe_requires_connection(self):
        self.assertTrue(self.control.call("disconnect").data["ok"])
        self.assertTrue(self.control.call("disconnect").data["ok"])
        self.assertEqual(self.runtime.closes, [0x100])
        self.assertEqual(self.control.call("observe").data["error"]["code"], "not_connected")

    def test_status_never_sends_input_or_requires_admin(self):
        result = self.control.call("status")
        self.assertTrue(result.data["ok"])
        self.assertFalse(result.data["is_admin"])
        self.assertFalse(self.runtime.inputs)

    def test_status_reports_live_focus_and_target_elevation(self):
        self.desktop.window = replace(self.desktop.window, foreground=False)
        self.desktop.target_elevated = True
        result = self.control.call('status')
        self.assertTrue(result.data['connected'])
        self.assertFalse(result.data['window']['foreground'])
        self.assertTrue(result.data['target_elevated'])
        self.assertFalse(self.runtime.inputs)


class NativeQueue:
    def __init__(self):
        self.status, self.posts, self.destroyed = 2000, [], []
        self.created = None
        self.request_id = 42

    def MaaControllerStatus(self, controller, request_id):
        return self.status

    def MaaControllerPostClickV2(self, controller, *args):
        self.posts.append((controller, *args))
        return self.request_id

    def MaaControllerPostInactive(self, controller):
        return self.request_id

    def MaaControllerDestroy(self, controller):
        self.destroyed.append(controller)

    def MaaWin32ControllerCreate(self, *args):
        self.created = args
        return 100

    def MaaControllerSetOption(self, *args):
        return True

    def MaaControllerPostConnection(self, controller):
        return self.request_id


class NativeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.runtime = object.__new__(MaaRuntime)
        self.api = NativeQueue()
        self.runtime.api, self.runtime.controller = self.api, 100
        self.runtime.pending_id, self.runtime.timeout = 0, 0

    def test_timeout_retains_pending_request_and_blocks_followup_submission(self):
        with self.assertRaises(ControlError) as raised:
            self.runtime.click(10, 20, 0)
        self.assertEqual(raised.exception.input_status, "unknown")
        self.assertEqual(self.runtime.pending_id, 42)
        with self.assertRaises(ControlError):
            self.runtime.click(30, 40, 0)
        self.assertEqual(len(self.api.posts), 1)
        self.api.status = 3000
        self.runtime.ensure_idle()
        self.assertEqual(self.runtime.pending_id, 0)

    def test_partial_failure_and_rejected_request_have_distinct_outcomes(self):
        self.api.status = 4000
        with self.assertRaises(ControlError) as failed:
            self.runtime.click(10, 20, 0)
        self.assertEqual(failed.exception.input_status, "unknown")
        self.api.request_id = 0
        with self.assertRaises(ControlError) as rejected:
            self.runtime.click(10, 20, 0)
        self.assertEqual(rejected.exception.input_status, "not_sent")

    def test_pending_cleanup_does_not_destroy_live_controller(self):
        with self.assertRaises(ControlError):
            self.runtime.close()
        self.assertEqual(self.runtime.controller, 100)
        self.assertFalse(self.api.destroyed)
        self.api.status = 3000
        self.runtime.close()
        self.assertEqual(self.api.destroyed, [100])
        self.assertIsNone(self.runtime.controller)

    def test_native_configuration_matches_project_aaa(self):
        self.api.status = 3000
        self.runtime.controller = None
        self.runtime.connect(0x100)
        self.assertEqual(self.api.created, (0x100, 32, 512, 1))
        interface = json.loads((ROOT / "assets/interface.json").read_text(encoding="utf-8"))
        aaa = next(c["win32"] for c in interface["controller"] if c["name"] == "AAA")
        self.assertEqual((aaa["screencap"], aaa["mouse"], aaa["keyboard"]), ("ScreenDC", "Interception", "Seize"))


@unittest.skipUnless(importlib.util.find_spec("mcp"), "Run with mcp==2.3.0 to check the protocol")
class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from mcp import Client

        self.desktop = Desktop()
        self.runtime = Runtime(self.desktop)
        self.client = Client(create_server(NikkeControl(self.runtime, self.desktop)))

    async def test_tools_and_real_mcp_image_delivery(self):
        async with self.client:
            tools = await self.client.list_tools()
            expected = {"nikke_status", "nikke_list_windows", "nikke_connect", "nikke_observe", "nikke_click",
                        "nikke_drag", "nikke_press_key", "nikke_disconnect"}
            self.assertEqual({t.name for t in tools.tools}, expected)
            connected = await self.client.call_tool("nikke_connect")
            self.assertFalse(connected.is_error)
            metadata = connected.structured_content
            image = next(c for c in connected.content if c.type == "image")
            data = base64.b64decode(image.data)
            self.assertEqual(data, PNG)
            self.assertEqual(struct.unpack(">II", data[16:24]), (metadata["width"], metadata["height"]))
            result = await self.client.call_tool("nikke_click", {"snapshot_id": metadata["snapshot_id"], "x": 640, "y": 360})
            self.assertEqual(result.structured_content["input_status"], "completed")
            self.assertEqual(self.runtime.inputs, [("click", 640, 360, 0)])
        self.assertFalse(self.runtime.connected())

    async def test_schema_rejects_non_integer_coordinates_before_input(self):
        async with self.client:
            connected = await self.client.call_tool("nikke_connect")
            for value in (True, 1.5, "640"):
                with self.subTest(value=value):
                    result = await self.client.call_tool("nikke_click", {"snapshot_id": connected.structured_content["snapshot_id"], "x": value, "y": 100})
                    self.assertTrue(result.is_error)
            self.assertFalse(self.runtime.inputs)

    async def test_stale_frame_is_an_mcp_error_with_no_second_click(self):
        async with self.client:
            connected = await self.client.call_tool("nikke_connect")
            args = {"snapshot_id": connected.structured_content["snapshot_id"], "x": 100, "y": 100}
            await self.client.call_tool("nikke_click", args)
            result = await self.client.call_tool("nikke_click", args)
            self.assertTrue(result.is_error)
            self.assertEqual(result.structured_content["error"]["code"], "stale_snapshot")
            self.assertEqual(len(self.runtime.inputs), 1)

    async def test_capture_failure_keeps_input_outcome_over_protocol(self):
        async with self.client:
            connected = await self.client.call_tool("nikke_connect")
            self.runtime.capture_error = ControlError("screenshot_failed", "failed")
            result = await self.client.call_tool("nikke_press_key", {"snapshot_id": connected.structured_content["snapshot_id"], "key": "a"})
            self.assertTrue(result.is_error)
            self.assertEqual(result.structured_content["input_status"], "completed")
            self.assertFalse(any(c.type == "image" for c in result.content))

    @unittest.skipUnless(os.name == "nt" and (ROOT / "deps/bin/MaaFramework.dll").exists(), "Requires the local Windows runtime")
    async def test_real_stdio_discovery_status_and_unconnected_error(self):
        from mcp import Client, StdioServerParameters

        params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "tools/nikke_control.py")], cwd=str(ROOT))
        async with Client(params, read_timeout_seconds=20) as client:
            listing = await client.list_tools()
            self.assertEqual(len(listing.tools), 8)
            result = await client.call_tool("nikke_status")
            self.assertFalse(result.is_error, result.content)
            self.assertEqual(result.structured_content["mouse"], "Interception")
            self.assertFalse(result.structured_content["connected"])
            windows = await client.call_tool("nikke_list_windows")
            self.assertFalse(windows.is_error)
            self.assertIsInstance(windows.structured_content["windows"], list)
            result = await client.call_tool("nikke_observe")
            self.assertTrue(result.is_error)
            self.assertEqual(result.structured_content["error"]["code"], "not_connected")


if __name__ == "__main__":
    unittest.main()
