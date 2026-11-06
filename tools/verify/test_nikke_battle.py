"""Battle ownership/lifecycle regressions; never attaches to a game window."""

from dataclasses import replace
import threading
import time
import unittest

from tools.nikke_control import NikkeControl
from tools.nikke_battle import BattleRunner, CHAPTER, ENTRY, LOST, MAP, PROBE
from tools.verify.test_nikke_control import Desktop, Runtime


class BattleContractTests(unittest.TestCase):
    def test_cli_accepts_battle_and_stop(self):
        from tools.nikke_cli import parse_command

        self.assertEqual(parse_command('battle --snapshot abc'), ('battle', {'snapshot_id': 'abc'}))
        self.assertEqual(parse_command('{"op":"stop"}'), ('stop', {}))

    def test_battle_requires_a_connected_fresh_snapshot(self):
        desktop = Desktop()
        runtime = Runtime(desktop)
        control = NikkeControl(runtime, desktop)
        result = control.call('battle', snapshot_id='old')
        self.assertFalse(result.data['ok'])
        self.assertEqual(result.data['input_status'], 'not_sent')
        self.assertFalse(runtime.inputs)


class Engine:
    """Controllable native boundary; real graph semantics have a separate DLL replay."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.load_gate, self.finish_gate, self.drain_gate = (threading.Event() for _ in range(3))
        self.load_gate.set()
        self.drain_gate.set()
        self.entered = threading.Event()
        self.loaded = False
        self.resource_id = 0
        self.load_ms = 12
        self.task_id = 0
        self.stop_id = 0
        self.entry = None
        self.preparation = True
        self.hold_stop = False
        self.posts, self.destroyed = [], []
        self.result_nodes = [MAP]

    def prepare_step(self, cancelled=False):
        self.resource_id = 0 if self.load_gate.is_set() else 1
        if self.resource_id:
            return False
        if not cancelled:
            self.loaded = True
        return True

    def post(self, entry):
        self.entry = entry
        self.task_id += 1
        self.stop_id = 0
        self.posts.append(entry)
        if entry == ENTRY:
            self.finish_gate.clear()
            self.entered.set()
            self.runtime.inputs.append(('battle',))

    def task_status(self):
        if self.entry == PROBE:
            return 3000 if self.preparation else 4000
        return 2000 if self.running() else 3000

    def running(self):
        return self.entry == ENTRY and not self.finish_gate.is_set()

    def stopped(self):
        return not self.running()

    def stop(self):
        self.stop_id = 900
        if not self.hold_stop:
            self.finish_gate.set()

    def recent_nodes(self):
        return []

    def completed_nodes(self):
        if self.entry == PROBE:
            return ['NikkeCampaignBattlePreparation'] if self.preparation else []
        return list(self.result_nodes)

    def drain_step(self):
        return self.drain_gate.is_set()

    def close(self):
        if self.running() or self.resource_id:
            raise AssertionError('destroyed while native requests are pending')
        self.destroyed.append(True)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.desktop = Desktop()
        self.runtime = Runtime(self.desktop)
        self.control = NikkeControl(self.runtime, self.desktop)
        self.snapshot = self.control.call('connect').data['snapshot_id']
        self.engine = Engine(self.runtime)
        self.factories = []

        def factory(runtime):
            self.factories.append(runtime)
            return self.engine

        self.runner = BattleRunner(self.control, factory)
        self.runner.poll_interval = 0.002
        self.runner.stop_timeout = 0.03
        self.control.battle_runner = self.runner
        self.events = []
        self.control.event_sink = self.events.append
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.engine.hold_stop = False
        for gate in (self.engine.load_gate, self.engine.finish_gate, self.engine.drain_gate):
            gate.set()
        self.runner.cancel.set()
        if self.runner.thread:
            self.runner.thread.join(2)
            self.assertFalse(self.runner.thread.is_alive(), 'worker leaked')

    def wait_for(self, predicate):
        deadline = time.monotonic() + 2
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.002)
        self.assertTrue(predicate())

    def start(self):
        result = self.control.call('battle', snapshot_id=self.snapshot)
        self.assertTrue(result.data['ok'], result.data)
        self.assertEqual(result.data['status'], 'running')
        self.assertIsNone(self.control.snapshot)
        return result.data

    def finish(self):
        self.engine.finish_gate.set()
        self.runner.thread.join(2)
        self.assertFalse(self.runner.thread.is_alive())
        return self.events[-1].data

    def test_resources_are_lazy_and_load_does_not_block_status_or_stop(self):
        self.control.call('status')
        self.assertFalse(self.factories)
        self.engine.load_gate.clear()
        self.start()
        self.wait_for(lambda: self.engine.resource_id == 1)
        before = time.monotonic()
        status = self.control.call('status').data
        stop = self.control.call('stop').data
        self.assertLess(time.monotonic() - before, 0.2)
        self.assertEqual(status['controller_owner'], 'battle')
        self.assertEqual(stop['status'], 'stopping')
        self.assertFalse(stop['controller_idle'])
        self.assertFalse(self.runtime.inputs)
        self.wait_for(lambda: bool(self.events))
        self.assertEqual(self.events[0].data['type'], 'battle.stopping')
        self.engine.load_gate.set()
        self.runner.thread.join(2)
        self.assertEqual(self.events[-1].data['input_status'], 'not_sent')
        self.assertEqual(self.events[-1].data['status'], 'cancelled')
        self.assertFalse(self.engine.posts)
        self.assertTrue(self.engine.destroyed)

    def test_busy_operations_cannot_interleave_or_destroy_controller(self):
        self.start()
        self.assertTrue(self.engine.entered.wait(1))
        for operation, params in (
            ('observe', {}), ('click', {'snapshot_id': self.snapshot, 'x': 1, 'y': 1}),
            ('drag', {'snapshot_id': self.snapshot, 'from_x': 1, 'from_y': 1, 'to_x': 2, 'to_y': 2}),
            ('press_key', {'snapshot_id': self.snapshot, 'key': 'escape'}),
            ('connect', {}), ('disconnect', {}), ('battle', {'snapshot_id': self.snapshot}),
        ):
            result = self.control.call(operation, **params).data
            self.assertEqual(result['error']['code'], 'battle_busy', (operation, result))
            self.assertEqual(result['input_status'], 'not_sent')
        self.assertFalse(self.runtime.closes)
        self.assertEqual(self.runtime.inputs, [('battle',)])

    def test_task_success_and_map_are_not_victory_evidence(self):
        accepted = self.start()
        self.assertTrue(self.engine.entered.wait(1))
        self.engine.result_nodes = ['BattleConfirmOperationComplete', 'CommonEndTask', MAP]
        result = self.finish()
        self.assertEqual(result['battle_id'], accepted['battle_id'])
        self.assertTrue(result['ok'])
        self.assertEqual(result['outcome'], 'unknown')
        self.assertEqual(result['return_state'], 'campaign_map')
        self.assertEqual(result['input_status'], 'completed')
        self.assertEqual(result['observation_status'], 'completed')
        self.assertTrue(result['controller_idle'])
        self.assertNotEqual(result['snapshot_id'], self.snapshot)
        self.assertEqual(self.control.owner, 'manual')
        replay = self.control.call('battle', snapshot_id=self.snapshot).data
        self.assertEqual(replay['error']['code'], 'stale_snapshot')

    def test_defeat_and_handoff_are_independent(self):
        for nodes, ok, state in (([LOST, MAP], True, 'campaign_map'),
                                 ([LOST], False, 'result'), ([CHAPTER], True, 'chapter_transition')):
            with self.subTest(nodes=nodes):
                self.snapshot = self.control.call('observe').data['snapshot_id']
                self.engine.entered.clear()
                self.start()
                self.assertTrue(self.engine.entered.wait(1))
                self.engine.result_nodes = nodes
                result = self.finish()
                self.assertEqual(result['ok'], ok)
                self.assertEqual(result['return_state'], state)
                self.assertEqual(result['outcome'], 'lost' if LOST in nodes else 'unknown')

    def test_wrong_page_cannot_submit_battle_input(self):
        self.engine.preparation = False
        self.start()
        self.runner.thread.join(2)
        result = self.events[-1].data
        self.assertEqual(result['reason'], 'not_preparation')
        self.assertEqual(result['outcome'], 'not_started')
        self.assertEqual(result['input_status'], 'not_sent')
        self.assertFalse(self.runtime.inputs)

    def test_stop_pending_notifies_once_and_holds_ownership_until_drained(self):
        self.engine.hold_stop = True
        self.engine.drain_gate.clear()
        self.start()
        self.assertTrue(self.engine.entered.wait(1))
        self.control.call('stop')
        self.wait_for(lambda: bool(self.events))
        self.assertEqual(self.events[0].data['reason'], 'stop_pending')
        self.assertEqual(self.control.owner, 'stopping')
        self.assertIsNone(self.control.snapshot)
        self.engine.finish_gate.set()
        time.sleep(0.05)
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.control.owner, 'stopping')
        self.engine.drain_gate.set()
        self.runner.thread.join(2)
        self.assertEqual([e.data['type'] for e in self.events], ['battle.stopping', 'battle.finished'])
        self.assertEqual(self.events[-1].data['status'], 'cancelled')
        self.assertEqual(self.events[-1].data['input_status'], 'unknown')
        self.assertTrue(self.events[-1].data['controller_idle'])

    def test_focus_and_geometry_change_stop_without_reactivating(self):
        for change in ({'foreground': False}, {'rect': (1, 2, 1920, 1080)}, {'pid': 999}):
            with self.subTest(change=change):
                self.desktop.window = Desktop().window
                self.snapshot = self.control.call('observe').data['snapshot_id']
                activations = len(self.desktop.activations)
                self.engine.entered.clear()
                self.start()
                self.assertTrue(self.engine.entered.wait(1))
                self.desktop.window = replace(self.desktop.window, **change)
                self.runner.thread.join(2)
                self.assertFalse(self.runner.thread.is_alive())
                result = self.events[-1].data
                self.assertEqual(result['status'], 'blocked')
                self.assertEqual(result['input_status'], 'unknown')
                self.assertEqual(result['return_state'], 'unknown')
                self.assertEqual(len(self.desktop.activations), activations)

    def test_timeout_is_not_the_manual_ten_second_timeout(self):
        self.runner.timeout = 0.04
        self.start()
        self.assertTrue(self.engine.entered.wait(1))
        self.runner.thread.join(2)
        result = self.events[-1].data
        self.assertEqual(result['status'], 'timed_out')
        self.assertEqual(result['reason'], 'battle_timeout')
        self.assertEqual(result['input_status'], 'unknown')

    def test_second_battle_reuses_resources_without_inheriting_defeat(self):
        self.start()
        self.assertTrue(self.engine.entered.wait(1))
        self.engine.result_nodes = [LOST, MAP]
        first = self.finish()
        self.engine.entered.clear()
        self.snapshot = first['snapshot_id']
        self.start()
        self.assertTrue(self.engine.entered.wait(1))
        self.engine.result_nodes = [MAP]
        second = self.finish()
        self.assertEqual(len(self.factories), 1)
        self.assertTrue(second['resource_reused'])
        self.assertNotEqual(second['battle_id'], first['battle_id'])
        self.assertEqual(second['outcome'], 'unknown')
        self.assertEqual(first['outcome'], 'lost')

    def test_final_observation_failure_preserves_outcome(self):
        from tools.nikke_control import ControlError

        self.start()
        self.assertTrue(self.engine.entered.wait(1))
        self.engine.result_nodes = [LOST, MAP]
        self.runtime.capture_error = ControlError('screenshot_failed', 'fixture failure')
        result = self.finish()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['outcome'], 'lost')
        self.assertEqual(result['input_status'], 'completed')
        self.assertEqual(result['observation_status'], 'failed')
        self.assertFalse(result['ok'])
        self.assertNotIn('snapshot_id', result)

    def test_timed_out_final_capture_does_not_release_live_native_request(self):
        from tools.nikke_control import ControlError

        self.start()
        self.assertTrue(self.engine.entered.wait(1))

        def capture_timeout():
            self.runtime.pending_id = 77
            raise ControlError('request_timeout', 'pending capture')

        self.runtime.screenshot = capture_timeout
        self.engine.finish_gate.set()
        self.wait_for(lambda: bool(self.events))
        self.assertEqual(self.events[0].data['type'], 'battle.stopping')
        self.assertEqual(self.control.owner, 'stopping')
        self.assertIsNone(self.control.snapshot)
        self.assertFalse(self.control.call('disconnect').data['ok'])
        self.runtime.pending_id = 0
        self.runner.thread.join(2)
        result = self.events[-1].data
        self.assertEqual(result['type'], 'battle.finished')
        self.assertEqual(result['input_status'], 'completed')
        self.assertEqual(result['observation_status'], 'failed')
        self.assertTrue(result['controller_idle'])

    def test_initialization_failure_consumes_snapshot_without_input(self):
        def failed_factory(runtime):
            raise OSError('resource unavailable')

        self.runner.engine_factory = failed_factory
        with self.assertLogs('nikke-control.battle', level='ERROR'):
            self.start()
            self.runner.thread.join(2)
        result = self.events[-1].data
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['input_status'], 'not_sent')
        self.assertEqual(result['outcome'], 'not_started')
        self.assertFalse(self.runtime.inputs)
        replay = self.control.call('battle', snapshot_id=self.snapshot).data
        self.assertEqual(replay['error']['code'], 'stale_snapshot')

    def test_disconnect_releases_tasker_resources_before_controller(self):
        self.start()
        self.assertTrue(self.engine.entered.wait(1))
        self.finish()
        result = self.control.call('disconnect')
        self.assertTrue(result.data['ok'])
        self.assertTrue(self.engine.destroyed)
        self.assertEqual(self.runtime.closes, [0x100])


if __name__ == '__main__':
    unittest.main()
