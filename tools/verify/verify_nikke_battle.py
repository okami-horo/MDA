"""Replay the CLI battle graph with the installed MaaFramework and a virtual controller.

Leaf recognition/action probes model pages. Compound recognition, JumpBack,
max_hit, task overrides, callbacks, native stop and resource reuse are real.
This does not validate OCR, click positions or live game acceptance.
"""

import ctypes as C
import json
import threading
import time
from unittest.mock import patch

from tools import nikke_battle as battle
from tools.nikke_control import B, I, P, U, MaaRuntime, NikkeControl, ROOT, bind
from tools.verify.test_nikke_control import Desktop, PNG
from tools.verify.verify_scene_navigation import (
    ACTION_NAME, RECO_NAME, ControllerCallbacks, probe_overrides, read_nodes,
)


class Replay:
    def __init__(self):
        self.runtime = MaaRuntime()
        self.api = self.runtime.api
        self.refs = []
        self.page = 'preparation'
        self.scenario = 'normal'
        self.actions, self.errors = [], []
        self.auto_aim = self.auto_burst = False
        self.combat_at = None
        self.events = []
        self.action_entered, self.action_release = threading.Event(), threading.Event()
        self.click_entered, self.click_release = threading.Event(), threading.Event()
        self.hold_click = False
        self.callbacks = ControllerCallbacks()
        bind(self.api, 'MaaCustomControllerCreate', P, [P, P])
        bind(self.api, 'MaaImageBufferSetEncoded', B, [P, P, U])
        bind(self.api, 'MaaStringBufferSet', B, [P, C.c_char_p])
        bind(self.api, 'MaaResourceRegisterCustomRecognition', B, [P, C.c_char_p, P, P])
        bind(self.api, 'MaaResourceRegisterCustomAction', B, [P, C.c_char_p, P, P])

        def callback(name, result, args, fn):
            cb = C.CFUNCTYPE(result, *args)(fn)
            self.refs.append(cb)
            setattr(self.callbacks, name, C.cast(cb, P).value)

        callback('connect', B, [P], lambda _: 1)
        callback('connected', B, [P], lambda _: 1)
        callback('request_uuid', B, [P, P], lambda _, buf: self.api.MaaStringBufferSet(buf, b'cli-battle-replay'))
        callback('get_features', U, [P], lambda _: 0)
        callback('screencap', B, [P, P], lambda _, buf: self.api.MaaImageBufferSetEncoded(buf, PNG, len(PNG)))
        callback('click', B, [I, I, P], self.click)
        callback('inactive', B, [P], lambda _: 1)
        self.runtime.controller = self.api.MaaCustomControllerCreate(C.byref(self.callbacks), None)
        assert self.runtime.controller
        self.runtime._post('MaaControllerPostConnection')
        self.engine = battle.NativeBattle(self.runtime)
        while not self.engine.prepare_step():
            time.sleep(0.005)
        reco = C.CFUNCTYPE(B, P, battle.ID, C.c_char_p, C.c_char_p, C.c_char_p, P, P, P, P, P)(self.recognize)
        action = C.CFUNCTYPE(B, P, battle.ID, C.c_char_p, C.c_char_p, C.c_char_p, battle.ID, P, P)(self.act)
        self.refs.extend([reco, action])
        assert self.api.MaaResourceRegisterCustomRecognition(self.engine.resource, RECO_NAME.encode(), C.cast(reco, P), None)
        assert self.api.MaaResourceRegisterCustomAction(self.engine.resource, ACTION_NAME.encode(), C.cast(action, P), None)
        self.desktop = Desktop()
        self.control = NikkeControl(self.runtime, self.desktop)
        self.control.window = self.desktop.window  # Never call Win32 connect in this harness.
        self.runner = battle.BattleRunner(self.control)
        self.runner.engine = self.engine
        self.runner.poll_interval = 0.005
        self.control.battle_runner = self.runner
        self.control.event_sink = self.events.append
        nodes = read_nodes(ROOT / 'assets/resource')
        nodes.update(read_nodes(ROOT / 'tools/nikke_resources'))
        self.override = probe_overrides(nodes)
        for name, value in battle.BATTLE_OVERRIDE.items():
            self.override[name].update(value)
        self.override['BattleInBattleFlow']['timeout'] = 200
        # Inline OCR is production evidence, not a fixture; do not execute it on a blank image.
        self.override['BattleCloseModeInfo']['enabled'] = False
        self.override['BattleSkipBossCutscene']['enabled'] = False

    def fail(self, text):
        self.errors.append(text)
        return 0

    def click(self, x, y, _):
        if not self.hold_click:
            return self.fail(f'unexpected native click: {x},{y}')
        self.click_entered.set()
        return int(self.click_release.wait(5))

    def visible(self, node):
        if self.page == 'combat' and self.combat_at is not None and time.monotonic() - self.combat_at > 0.04:
            self.page = 'defeat' if self.scenario == 'defeat' else 'result'
        if node == 'BattleEnableAutoAim':
            return self.page == 'combat' and not self.auto_aim
        if node == 'BattleEnableAutoCombat':
            return self.page == 'combat' and not self.auto_burst
        pages = {
            'BattleMainVisible': {'preparation', 'after_defeat'},
            'BattleAvailable': {'preparation'},
            'QuickBattleVisible': {'preparation'} if self.scenario in {'quick', 'multiple'} else set(),
            'QuickBattleAvailable': {'preparation'} if self.scenario in {'quick', 'multiple'} else set(),
            'BattleDesktopCombatHudVisible': {'combat'},
            'BattleSettlementEscVisible': {'result'},
            'BattleFailedVisible': {'defeat'},
            'CommonGoBack': {'defeat'},
            'BattleClosePage': {'after_defeat'},
            'MapPushingMinimapVisible': {'map', 'reward', 'chapter', 'blocked', 'multiple'},
            'CommonConfirmReward': {'reward'},
            'CommonClosePage': {'blocked'},
            'BattleFieldChanged': {'chapter'},
            'MultipleBattleDialogFlow': {'multiple'},
            'CommonGemCostNoticeVisible': {'gem'},
            'CommonCancelOptionVisible': {'gem'},
            'CommonConfirmAction': {'gem'},
        }
        return self.page in pages.get(node, set())

    def recognize(self, context, task_id, name, custom, params, image, roi, trans, box, detail):
        try:
            if not self.visible(json.loads(params)['node']):
                return 0
            C.cast(box, C.POINTER(I * 4)).contents[:] = (10, 10, 20, 20)
            return 1
        except Exception as error:
            return self.fail(str(error))

    def act(self, context, task_id, name, custom, params, reco_id, box, trans):
        try:
            node = json.loads(params)['node']
            self.actions.append(node)
            if node == 'BattleEnterQuickBattle':
                self.page = 'multiple' if self.scenario == 'multiple' else 'result'
            elif node == 'BattleEnterNormalBattle':
                if self.scenario == 'stalled':
                    self.action_entered.set()
                    if not self.action_release.wait(5):
                        return self.fail('stalled action was not released')
                self.page = 'gem' if self.scenario == 'gem' else 'combat'
                self.combat_at = time.monotonic()
            elif node == 'BattleEnableAutoAim':
                self.auto_aim = True
            elif node == 'BattleEnableAutoCombat':
                self.auto_burst = True
            elif node == 'BattleConfirmOperationComplete':
                self.page = {'reward': 'reward', 'chapter': 'chapter', 'blocked': 'blocked'}.get(self.scenario, 'map')
            elif node == 'CommonConfirmReward':
                self.page = 'map'
            elif node == 'NikkeCampaignBattleLeaveDefeat':
                self.page = 'after_defeat'
            elif node == 'NikkeCampaignBattleClosePreparation':
                self.page = 'map'
            elif node == 'CommonPurchaseGemBlocked':
                self.page = 'preparation'
            else:
                return self.fail(f'forbidden/unmodeled action: {node}')
            return 1
        except Exception as error:
            return self.fail(str(error))

    def run(self, scenario, auto_enabled=False):
        self.page = 'preparation'
        self.scenario = scenario
        self.auto_aim = self.auto_burst = auto_enabled
        self.combat_at = None
        self.actions.clear()
        self.errors.clear()
        self.events.clear()
        self.control.snapshot = None
        snapshot = self.control._capture(False).data['snapshot_id']
        with patch.object(battle, 'BATTLE_OVERRIDE', self.override):
            accepted = self.control.call('battle', snapshot_id=snapshot)
            assert accepted.data['ok'], accepted.data
            self.runner.thread.join(6)
            if self.runner.thread.is_alive():
                self.control.call('stop')
                self.runner.thread.join(3)
                raise AssertionError(f'replay did not terminate: {scenario}, {self.engine.recent_nodes()}')
        assert not self.errors, self.errors
        result = self.events[-1].data
        assert result['controller_idle'], result
        assert self.runtime.pending_id == 0
        assert result['resource_reused']
        return result

    def close(self):
        self.action_release.set()
        self.click_release.set()
        if self.runner.thread and self.runner.thread.is_alive():
            self.control.call('stop')
            self.runner.thread.join(10)
        self.engine.close()
        self.runtime.close()
        self.runtime.cookie.close()


def main():
    replay = Replay()
    try:
        print(f'MaaFramework {replay.runtime.version}; virtual controller only; load {replay.engine.load_ms} ms')
        for scenario in ('quick', 'normal', 'defeat', 'reward', 'chapter', 'blocked', 'multiple', 'gem'):
            result = replay.run(scenario)
            assert result['ok'] == (scenario not in {'blocked', 'multiple', 'gem'}), (scenario, result)
            assert result['outcome'] == ('lost' if scenario == 'defeat' else 'unknown'), result
            expected = ('chapter_transition' if scenario == 'chapter' else
                        'unknown' if scenario in {'blocked', 'multiple', 'gem'} else 'campaign_map')
            if scenario not in {'blocked', 'multiple', 'gem'}:
                assert result['return_state'] == expected, result
            assert not {'BattleEnterCharacterPage', 'MultipleBattleClickMax',
                        'MultipleBattleClickStartBattle', 'BattleClickNextStage'} & set(replay.actions), replay.actions
            if scenario == 'blocked':
                assert battle.MAP not in replay.engine.completed_nodes(), result
            if scenario == 'gem':
                assert 'CommonPurchaseGemBlocked' in replay.actions and 'CommonConfirmAction' not in replay.actions
            if scenario == 'normal':
                assert replay.actions.count('BattleEnableAutoAim') == 1, replay.actions
                assert replay.actions.count('BattleEnableAutoCombat') == 1, replay.actions
            print(f'[PASS] {scenario}: {result["status"]}, {result["outcome"]}, {result["return_state"]}')
        result = replay.run('normal', auto_enabled=True)
        assert result['ok'] and not {'BattleEnableAutoAim', 'BattleEnableAutoCombat'} & set(replay.actions)
        print('[PASS] enabled auto controls are not toggled off')
        assert replay.run('defeat')['outcome'] == 'lost'
        assert replay.run('quick')['outcome'] == 'unknown'
        print('[PASS] resource reuse does not inherit prior outcome')

        # A task without the probe overrides must see the real blank frame and
        # fail preparation, even after many tasks reused the same Tasker.
        replay.engine.post(battle.PROBE)
        while not replay.engine.stopped():
            time.sleep(0.005)
        assert 'NikkeCampaignBattlePreparation' not in replay.engine.completed_nodes()
        assert replay.engine.task_status() == 4000
        print('[PASS] task overrides do not leak to subsequent tasks or Resource')

        replay.scenario, replay.page = 'stalled', 'preparation'
        replay.events.clear()
        replay.runner.stop_timeout = 0.03
        snapshot = replay.control._capture(False).data['snapshot_id']
        with patch.object(battle, 'BATTLE_OVERRIDE', replay.override):
            assert replay.control.call('battle', snapshot_id=snapshot).data['ok']
            assert replay.action_entered.wait(2)
            assert replay.control.call('stop').data['status'] == 'stopping'
            deadline = time.monotonic() + 2
            while not replay.events and time.monotonic() < deadline:
                time.sleep(0.005)
            assert replay.events and replay.events[-1].data['type'] == 'battle.stopping'
            assert replay.runtime.pending_id == 0, 'Tasker/stop IDs leaked into Controller pending_id'
            assert replay.control.call('observe').data['error']['code'] == 'battle_busy'
            replay.action_release.set()
            replay.runner.thread.join(3)
        assert not replay.runner.thread.is_alive()
        assert replay.events[-1].data['status'] == 'cancelled'
        assert replay.events[-1].data['input_status'] == 'unknown'
        print('[PASS] native stop remains pending until the in-flight action ends')

        # A queued virtual input deliberately outlives Tasker. The read fence
        # must wait for it without treating a task ID as a Controller request.
        replay.hold_click = True
        job = replay.api.MaaControllerPostClickV2(replay.runtime.controller, 1, 1, 0, 0)
        assert job > 0 and replay.click_entered.wait(1)
        replay.engine.drain_id = 0
        assert not replay.engine.drain_step()
        assert replay.runtime.pending_id == replay.engine.drain_id
        replay.click_release.set()
        deadline = time.monotonic() + 2
        while not replay.engine.drain_step() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert replay.engine.drain_step() and replay.runtime.pending_id == 0
        print('[PASS] Controller queue fence waits for older virtual inputs')
        print('13 native replay checks passed; OCR/assets and live game behavior remain unverified.')
    finally:
        replay.close()


if __name__ == '__main__':
    main()
