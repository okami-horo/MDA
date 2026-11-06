"""CLI lifecycle and output checks; no UAC or game input is sent."""

import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tools import nikke_cli as cli
from tools.nikke_control import NikkeControl, Result
from tools.verify.test_nikke_control import Desktop, PNG, Runtime


class CommandTests(unittest.TestCase):
    def test_shell_and_json_commands_use_the_same_operations(self):
        self.assertEqual(cli.parse_command('windows'), ('list_windows', {}))
        self.assertEqual(cli.parse_command('key escape --snapshot abc'),
                         ('press_key', {'key': 'escape', 'snapshot_id': 'abc'}))
        self.assertEqual(cli.parse_command('{"op":"click","snapshot_id":"abc","x":10,"y":20}'),
                         ('click', {'snapshot_id': 'abc', 'x': 10, 'y': 20}))

    def test_capture_controls_support_shell_and_json(self):
        self.assertEqual(cli.parse_command('observe --wait-ms 500'), ('observe', {'wait_ms': 500}))
        self.assertEqual(cli.parse_command('key escape --snapshot abc --no-screenshot --wait-ms 800'),
                         ('press_key', {'key': 'escape', 'snapshot_id': 'abc',
                                        'capture': False, 'wait_ms': 800}))
        self.assertEqual(cli.parse_command('{"op":"click","snapshot_id":"abc","x":10,"y":20,"capture":false}'),
                         ('click', {'snapshot_id': 'abc', 'x': 10, 'y': 20, 'capture': False}))

    def test_invalid_requests_are_rejected_before_dispatch(self):
        for line in ('click 10 20', 'unknown', '{', '{"op":[]}',
                     '{"op":"click","snapshot_id":"abc","x":true,"y":20}',
                     '{"op":"disconnect","extra":1}'):
            with self.subTest(line=line), self.assertRaises(cli.ControlError):
                cli.parse_command(line)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.desktop = Desktop()
        self.runtime = Runtime(self.desktop)
        self.control = NikkeControl(self.runtime, self.desktop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.images = Path(self.directory.name)
        self.output = io.StringIO()

    def run_session(self, lines):
        return cli.run_session(self.control, stdin=lines, stdout=self.output, image_dir=self.images)

    def messages(self):
        return [json.loads(line) for line in self.output.getvalue().splitlines()]

    def test_one_session_reuses_controller_and_quit_releases_it(self):
        def commands():
            yield 'connect\n'
            snapshot = self.messages()[-1]['snapshot_id']
            yield f'click 640 360 --snapshot {snapshot}\n'
            snapshot = self.messages()[-1]['snapshot_id']
            yield f'key escape --snapshot {snapshot}\n'
            yield 'quit\n'

        self.assertEqual(self.run_session(commands()), 0)
        self.assertEqual(self.runtime.connections, [0x100])
        self.assertEqual(self.runtime.inputs, [('click', 640, 360, 0), ('key', 0x1B)])
        self.assertEqual(self.runtime.closes, [0x100])
        messages = self.messages()
        self.assertEqual(messages[0]['session'], 'ready')
        self.assertEqual(messages[-1]['session'], 'closed')
        for result in messages[1:-1]:
            self.assertTrue(result['ok'], result)
            image = Path(result['image_path'])
            self.assertTrue(image.is_absolute())
            self.assertEqual(image.read_bytes(), PNG)
            self.assertNotIn('image', result)
        self.assertEqual(len(list(self.images.glob('*.png'))), 1)

    def test_eof_disconnects_and_invalid_command_does_not_end_session(self):
        self.assertEqual(self.run_session(iter(['connect\n', 'invalid\n', 'status\n'])), 0)
        messages = self.messages()
        self.assertEqual(messages[2]['input_status'], 'not_sent')
        self.assertEqual(messages[2]['error']['code'], 'invalid_command')
        self.assertTrue(messages[3]['connected'])
        self.assertEqual(messages[-1]['session'], 'closed')
        self.assertEqual(self.runtime.closes, [0x100])

    def test_old_snapshot_cannot_be_replayed_over_cli(self):
        def commands():
            yield 'connect\n'
            snapshot = self.messages()[-1]['snapshot_id']
            command = f'click 10 20 --snapshot {snapshot}\n'
            yield command
            yield command

        self.run_session(commands())
        self.assertEqual(self.messages()[-2]['error']['code'], 'stale_snapshot')
        self.assertEqual(self.runtime.inputs, [('click', 10, 20, 0)])

    def test_identical_frames_are_marked_without_rewriting_the_image(self):
        def commands():
            yield 'connect\n'
            first = self.messages()[-1]
            self.assertTrue(first['image_changed'])
            with patch.object(Path, 'write_bytes', side_effect=AssertionError('unchanged image rewritten')):
                yield 'observe\n'
            second = self.messages()[-1]
            self.assertFalse(second['image_changed'])
            self.assertEqual(second['image_path'], first['image_path'])
            self.assertNotEqual(second['snapshot_id'], first['snapshot_id'])
            yield f'click 10 20 --snapshot {second["snapshot_id"]} --no-screenshot\n'
            skipped = self.messages()[-1]
            self.assertEqual(skipped['observation_status'], 'skipped')
            self.assertNotIn('image_path', skipped)
            self.assertNotIn('snapshot_id', skipped)
            yield 'quit\n'

        self.assertEqual(self.run_session(commands()), 0)
        self.assertEqual(self.runtime.inputs, [('click', 10, 20, 0)])

    def test_missing_image_is_saved_again_even_when_the_frame_is_identical(self):
        def commands():
            yield 'connect\n'
            Path(self.messages()[-1]['image_path']).unlink()
            yield 'observe\n'
            result = self.messages()[-1]
            self.assertTrue(result['image_changed'])
            self.assertEqual(Path(result['image_path']).read_bytes(), PNG)

        self.assertEqual(self.run_session(commands()), 0)

    def test_session_returns_a_smaller_preview_without_another_command(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow is optional; only JPEG previews need it')
        source = io.BytesIO()
        Image.effect_noise((1280, 720), 96).save(source, format='PNG')
        original_capture = self.runtime.screenshot
        self.runtime.screenshot = lambda: (original_capture()[0], source.getvalue())
        self.assertEqual(self.run_session(iter(['connect\n', 'quit\n'])), 0)
        result = self.messages()[1]
        raw, rendered = Path(result['image_path']), Path(result['preview_path'])
        self.assertLess(rendered.stat().st_size, raw.stat().st_size)
        self.assertEqual(raw.read_bytes(), source.getvalue())
        with Image.open(rendered) as image:
            self.assertEqual(image.size, (result['width'], result['height']))

    def test_preview_failure_keeps_the_png_and_usable_snapshot(self):
        result = Result({'ok': True, 'snapshot_id': 'abc', 'input_status': 'completed'}, PNG)
        with patch.object(cli, 'preview', return_value=Result({'ok': False})):
            cli.emit(result, self.output, self.images)
        message = self.messages()[0]
        self.assertTrue(message['ok'])
        self.assertEqual(message['snapshot_id'], 'abc')
        self.assertEqual(message['input_status'], 'completed')
        self.assertEqual(Path(message['image_path']).read_bytes(), PNG)
        self.assertNotIn('preview_path', message)

    def test_image_save_failure_preserves_completed_input_status(self):
        result = Result({'ok': True, 'snapshot_id': 'abc', 'input_status': 'completed'}, PNG)
        with patch.object(Path, 'write_bytes', side_effect=OSError('disk full')):
            cli.emit(result, self.output, self.images)
        message = self.messages()[0]
        self.assertFalse(message['ok'])
        self.assertEqual(message['input_status'], 'completed')
        self.assertEqual(message['observation_status'], 'failed')
        self.assertEqual(message['error']['code'], 'image_save_failed')
        self.assertNotIn('image_path', message)
        self.assertNotIn('snapshot_id', message)

    def test_battle_acknowledgement_status_stop_and_quit_share_one_json_stream(self):
        from tools.nikke_battle import BattleRunner
        from tools.verify.test_nikke_battle import Engine

        engine = Engine(self.runtime)
        runner = BattleRunner(self.control, lambda runtime: engine)
        runner.poll_interval = 0.002
        self.control.battle_runner = runner

        def commands():
            yield 'connect\n'
            snapshot = self.messages()[-1]['snapshot_id']
            yield f'battle --snapshot {snapshot}\n'
            self.assertEqual(self.messages()[-1]['op'], 'battle')
            self.assertTrue(engine.entered.wait(1))
            yield 'status\n'
            self.assertEqual(self.messages()[-1]['controller_owner'], 'battle')
            yield 'quit\n'
            self.assertEqual(self.messages()[-1]['error']['code'], 'battle_busy')
            yield 'stop\n'
            self.assertEqual(self.messages()[-1]['status'], 'stopping')
            runner.thread.join(2)
            self.assertFalse(runner.thread.is_alive())
            event = self.messages()[-1]
            self.assertEqual(event['type'], 'battle.finished')
            self.assertEqual(event['status'], 'cancelled')
            self.assertTrue(Path(event['image_path']).is_file())
            yield 'quit\n'

        try:
            self.assertEqual(self.run_session(commands()), 0)
            self.assertEqual(self.messages()[-1]['session'], 'closed')
        finally:
            runner.cancel.set()
            if runner.thread:
                runner.thread.join(2)

    def test_eof_stops_battle_before_reporting_session_closed(self):
        from tools.nikke_battle import BattleRunner
        from tools.verify.test_nikke_battle import Engine

        engine = Engine(self.runtime)
        runner = BattleRunner(self.control, lambda runtime: engine)
        self.control.battle_runner = runner

        def commands():
            yield 'connect\n'
            yield f'battle --snapshot {self.messages()[-1]["snapshot_id"]}\n'
            self.assertTrue(engine.entered.wait(1))

        self.assertEqual(self.run_session(commands()), 0)
        messages = self.messages()
        self.assertEqual(messages[-2]['type'], 'battle.finished')
        self.assertEqual(messages[-2]['status'], 'cancelled')
        self.assertEqual(messages[-1]['session'], 'closed')
        self.assertTrue(engine.destroyed)
        self.assertFalse(runner.thread.is_alive())

    def test_command_after_finished_event_sees_manual_ownership(self):
        from tools.nikke_battle import BattleRunner
        from tools.verify.test_nikke_battle import Engine

        engine = Engine(self.runtime)
        runner = BattleRunner(self.control, lambda runtime: engine)
        runner.poll_interval = 0.002
        self.control.battle_runner = runner
        published, next_command = threading.Event(), threading.Event()
        original = runner._emit

        def pause_after_publication(result):
            original(result)
            if result.data['type'] == 'battle.finished':
                published.set()
                next_command.wait(1)
                time.sleep(0.03)  # Expose the gap between publishing and releasing ownership.

        runner._emit = pause_after_publication

        def commands():
            yield 'connect\n'
            yield f'battle --snapshot {self.messages()[-1]["snapshot_id"]}\n'
            self.assertTrue(engine.entered.wait(1))
            engine.finish_gate.set()
            self.assertTrue(published.wait(2))
            next_command.set()
            yield 'observe\n'
            self.assertTrue(self.messages()[-1]['ok'], self.messages()[-1])
            yield 'quit\n'

        try:
            self.assertEqual(self.run_session(commands()), 0)
        finally:
            next_command.set()
            runner.cancel.set()
            if runner.thread:
                runner.thread.join(2)

    def test_image_save_failure_does_not_erase_battle_result(self):
        result = Result({'type': 'battle.finished', 'ok': True, 'status': 'completed',
                         'outcome': 'lost', 'input_status': 'completed', 'controller_idle': True,
                         'snapshot_id': 'result'}, PNG)
        with patch.object(Path, 'write_bytes', side_effect=OSError('disk full')):
            cli.emit(result, self.output, self.images)
        message = self.messages()[0]
        self.assertEqual(message['status'], 'completed')
        self.assertEqual(message['outcome'], 'lost')
        self.assertEqual(message['input_status'], 'completed')
        self.assertTrue(message['controller_idle'])
        self.assertNotIn('snapshot_id', message)

    def test_pending_request_prevents_quit_until_the_controller_is_idle(self):
        def commands():
            yield 'connect\n'
            self.runtime.pending_id = 9
            yield 'quit\n'
            self.assertEqual(self.messages()[-1]['error']['code'], 'request_pending')
            self.assertIsNotNone(self.runtime.controller)
            self.runtime.pending_id = 0
            yield 'quit\n'

        self.assertEqual(self.run_session(commands()), 0)
        self.assertEqual(self.runtime.closes, [0x100])

    def test_real_cli_stdio_needs_no_site_packages_or_mcp(self):
        result = subprocess.run(
            [sys.executable, '-S', '-u', str(Path(cli.__file__).resolve()), 'session', '--no-elevate'],
            input='help\nquit\n', capture_output=True, text=True, encoding='utf-8',
            cwd=self.images, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        messages = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(messages[0]['session'], 'ready')
        self.assertIn('help', messages[1])
        self.assertEqual(messages[-1]['session'], 'closed')
        self.assertEqual(result.stderr, '')


class StartupTests(unittest.TestCase):
    def test_preview_without_pillow_does_not_load_runtime_or_request_uac(self):
        with patch.dict(sys.modules, {'PIL': None}), patch.object(cli, 'NikkeControl') as control_type, \
                patch.object(cli.launcher, 'Native') as native, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(cli.main(['preview', 'missing.png']), 1)
            message = json.loads(output.getvalue())
            self.assertEqual(message['error']['code'], 'preview_unavailable')
            control_type.assert_not_called()
            native.assert_not_called()

    def test_jpeg_preview_keeps_original_dimensions_and_source(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow is optional; only JPEG previews need it')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'latest.png'
            source.write_bytes(PNG)
            result = cli.preview(source)
            self.assertTrue(result.data['ok'], result.data)
            self.assertEqual((result.data['width'], result.data['height']), (1280, 720))
            self.assertEqual(source.read_bytes(), PNG)
            destination = Path(result.data['image_path'])
            self.assertTrue(destination.is_absolute())
            with Image.open(destination) as image:
                self.assertEqual(image.format, 'JPEG')
                self.assertEqual(image.size, (1280, 720))
            self.assertEqual(result.data['image_bytes'], destination.stat().st_size)

    def test_preview_failure_does_not_return_an_old_image(self):
        try:
            import PIL
        except ImportError:
            self.skipTest('Pillow is optional; only JPEG previews need it')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'latest.png'
            source.write_bytes(b'not an image')
            result = cli.preview(source)
            self.assertFalse(result.data['ok'])
            self.assertEqual(result.data['error']['code'], 'image_preview_failed')
            self.assertNotIn('image_path', result.data)

    def test_read_only_commands_never_request_elevation(self):
        for command, operation in (('status', 'status'), ('windows', 'list_windows')):
            with self.subTest(command=command), patch.object(cli, 'NikkeControl') as control_type, \
                    patch.object(cli.launcher, 'Native') as native, patch('sys.stdout', new_callable=io.StringIO):
                control_type.return_value.call.return_value = Result({'ok': True})
                self.assertEqual(cli.main([command]), 0)
                control_type.return_value.call.assert_any_call(operation)
                native.assert_not_called()

    def test_only_explicit_session_requests_the_elevated_cli_worker(self):
        with patch.object(cli.launcher, 'Native') as native, patch.object(cli.launcher, 'bridge') as bridge, \
                patch.object(cli, 'run_session') as run:
            native.return_value.is_admin.return_value = False
            self.assertEqual(cli.main(['session']), 0)
            bridge.assert_called_once_with(native.return_value, None, cli=True)
            run.assert_not_called()

    def test_already_elevated_session_does_not_request_uac_again(self):
        with patch.object(cli.launcher, 'Native') as native, patch.object(cli.launcher, 'bridge') as bridge, \
                patch.object(cli, 'run_session', return_value=0) as run:
            native.return_value.is_admin.return_value = True
            self.assertEqual(cli.main(['session']), 0)
            bridge.assert_not_called()
            run.assert_called_once()

    def test_diagnostic_session_can_inherit_current_privileges(self):
        with patch.object(cli.launcher, 'Native') as native, patch.object(cli, 'run_session', return_value=0):
            self.assertEqual(cli.main(['session', '--no-elevate']), 0)
            native.assert_not_called()


if __name__ == '__main__':
    unittest.main()
