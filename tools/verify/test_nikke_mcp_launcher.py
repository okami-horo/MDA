"""Elevation-bridge checks; none of these tests opens UAC or sends game input."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import nikke_mcp_launcher as launcher


class RelayTests(unittest.TestCase):
    def test_large_binary_stream_and_eof_are_preserved(self):
        source_read, source_write = os.pipe()
        output_read, output_write = os.pipe()
        payload = (bytes(range(256)) + 'NIKKE 截图\r\n'.encode()) * 4096

        def produce():
            try:
                launcher.write_all(source_write, payload)
            finally:
                os.close(source_write)

        def relay():
            try:
                launcher.copy_stream(source_read, output_write)
            finally:
                os.close(source_read)
                os.close(output_write)

        with ThreadPoolExecutor(max_workers=2) as pool:
            producer, transfer = pool.submit(produce), pool.submit(relay)
            received = bytearray()
            try:
                while data := os.read(output_read, 65536):
                    received.extend(data)
            finally:
                os.close(output_read)
            producer.result(timeout=5)
            transfer.result(timeout=5)
        self.assertEqual(received, payload)

    def test_partial_writes_do_not_drop_protocol_bytes(self):
        received = bytearray()

        def partial(fd, data):
            piece = bytes(data[:3])
            received.extend(piece)
            return len(piece)

        payload = b'{"content":"PNG\\r\\n"}\n'
        with patch.object(launcher.os, 'write', side_effect=partial):
            launcher.write_all(1, payload)
        self.assertEqual(received, payload)

    def test_worker_exit_before_handshake_reports_its_exit_code(self):
        native = SimpleNamespace(exit_code=lambda process: 7, available=Mock())
        with self.assertRaisesRegex(launcher.LauncherError, '代码 7'):
            launcher.wait_ready(native, 1, 0)
        native.available.assert_not_called()

    def test_invalid_handshake_is_not_forwarded_as_mcp(self):
        read, write = os.pipe()
        try:
            os.write(write, b'X' * len(launcher.READY))
            native = SimpleNamespace(exit_code=lambda process: None, available=lambda fd: len(launcher.READY))
            with self.assertRaisesRegex(launcher.LauncherError, '握手无效'):
                launcher.wait_ready(native, 1, read)
        finally:
            os.close(read)
            os.close(write)

    def test_admin_host_runs_server_without_another_uac_request(self):
        with patch.object(launcher, 'Native') as native, patch.object(launcher, 'run_server') as run:
            native.return_value.is_admin.return_value = True
            launcher.main([])
            run.assert_called_once_with(None)
            native.return_value.elevate.assert_not_called()

    def test_worker_refuses_to_run_without_elevation(self):
        native = SimpleNamespace(is_admin=lambda: False)
        with self.assertRaisesRegex(launcher.LauncherError, '未取得管理员权限'):
            launcher.serve_worker(native, SimpleNamespace())

    def test_cli_worker_selects_cli_session_and_restores_arguments(self):
        previous = sys.argv
        observed = []

        def run(path, run_name):
            observed.append((path, run_name, list(sys.argv)))

        with patch.object(launcher.runpy, 'run_path', side_effect=run):
            launcher.run_server(Path('fixture'), cli=True)
        self.assertIs(sys.argv, previous)
        self.assertEqual(observed, [(str(launcher.CLI), '__main__',
                                     [str(launcher.CLI), '--maa-dir', 'fixture', 'session'])])


@unittest.skipUnless(os.name == 'nt', 'Requires Windows handle APIs')
class WindowsBridgeTests(unittest.TestCase):
    def test_cli_worker_round_trip_uses_real_cross_process_handles_without_mcp(self):
        import msvcrt

        input_read, input_write = os.pipe()
        output_read, output_write = os.pipe()
        owned = {input_read, input_write, output_read, output_write}
        code = '''
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
import nikke_mcp_launcher as launcher
launcher.WORKER_LOG = Path(sys.argv[2])
launcher.Native.is_admin = lambda self: True
def unexpected_uac(*args):
    raise AssertionError('This test must never request real UAC')
launcher.Native.elevate = unexpected_uac
args = SimpleNamespace(parent_pid=int(sys.argv[3]), stdin_handle=int(sys.argv[4]),
                       stdout_handle=int(sys.argv[5]), maa_dir=None, cli=True)
launcher.serve_worker(launcher.Native(), args)
'''
        try:
            os.write(input_write, b'help\nquit\n')
            os.close(input_write)
            owned.remove(input_write)
            with tempfile.TemporaryDirectory() as directory:
                log = Path(directory) / 'worker.log'
                result = subprocess.run(
                    [sys.executable, '-S', '-u', '-c', code, str(launcher.ROOT / 'tools'), str(log),
                     str(os.getpid()), str(msvcrt.get_osfhandle(input_read)),
                     str(msvcrt.get_osfhandle(output_write))],
                    capture_output=True, text=True, encoding='utf-8', cwd=directory, timeout=10)
                self.assertEqual(result.returncode, 0, log.read_text(encoding='utf-8') if log.exists() else result.stderr)
                self.assertIn('NIKKE CLI worker', log.read_text(encoding='utf-8'))
                self.assertIn('stopped', log.read_text(encoding='utf-8'))
            for fd in (input_read, output_write):
                os.close(fd)
                owned.remove(fd)
            payload = os.read(output_read, 65536)
            self.assertTrue(payload.startswith(launcher.READY), payload)
            messages = [json.loads(line) for line in payload[len(launcher.READY):].decode('utf-8').splitlines()]
            self.assertEqual(messages[0]['session'], 'ready')
            self.assertIn('help', messages[1])
            self.assertEqual(messages[-1]['session'], 'closed')
            self.assertEqual(result.stdout, '')
        finally:
            for fd in owned:
                os.close(fd)

    def test_cli_mode_reaches_the_elevated_worker_arguments(self):
        native = SimpleNamespace(elevate=Mock(side_effect=launcher.LauncherError('cancelled')))
        with self.assertRaisesRegex(launcher.LauncherError, 'cancelled'):
            launcher.bridge(native, None, cli=True)
        self.assertIn('--cli', native.elevate.call_args.args[0])

    def test_cancelled_uac_closes_every_created_pipe(self):
        created, real_pipe = [], os.pipe

        def pipe():
            pair = real_pipe()
            created.extend(pair)
            return pair

        native = SimpleNamespace(elevate=Mock(side_effect=launcher.LauncherError('UAC cancelled')))
        with patch.object(launcher.os, 'pipe', side_effect=pipe):
            with self.assertRaisesRegex(launcher.LauncherError, 'UAC cancelled'):
                launcher.bridge(native, None)
        self.assertEqual(len(created), 4)
        for fd in created:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_native_pipe_handle_can_be_duplicated_and_survive_source_close(self):
        import msvcrt

        native = launcher.Native()
        read, write = os.pipe()
        duplicate = None
        try:
            duplicate = native.duplicate_fd(os.getpid(), msvcrt.get_osfhandle(read), os.O_RDONLY)
            os.close(read)
            read = None
            payload = '跨进程管道\n'.encode()
            os.write(write, payload)
            self.assertEqual(native.available(duplicate), len(payload))
            self.assertEqual(os.read(duplicate, len(payload)), payload)
            os.close(write)
            write = None
            self.assertEqual(os.read(duplicate, 1), b'')
        finally:
            for fd in (read, write, duplicate):
                if fd is not None:
                    os.close(fd)


if __name__ == '__main__':
    unittest.main()
