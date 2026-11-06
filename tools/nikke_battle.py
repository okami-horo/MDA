"""One asynchronous campaign encounter on the CLI's existing AAA controller.

Native callbacks only collect evidence. The worker owns every blocking operation;
the command lock is held only for short ownership/state transitions.
"""

import ctypes as C
import json
import logging
import threading
import time
import uuid

if __package__:
    from .nikke_control import B, I, ID, P, U, ControlError, Result, ROOT, bind
else:
    from nikke_control import B, I, ID, P, U, ControlError, Result, ROOT, bind

LOG = logging.getLogger('nikke-control.battle')
PENDING = (1000, 2000)
PROBE = 'NikkeCampaignBattleProbe'
ENTRY = 'NikkeCampaignBattleEntry'
MAP = 'NikkeCampaignBattleMapReturned'
CHAPTER = 'NikkeCampaignBattleChapterTransition'
LOST = 'NikkeCampaignBattleLost'
BLOCKED = 'NikkeCampaignBattleBlocked'

# Task-local control flow only. Recognition parameters remain in Pipeline JSON.
BATTLE_OVERRIDE = {
    'BattleEnterQuickBattle': {'max_hit': 1, 'next': ['BattleInBattleFlow']},
    'BattleEnterNormalBattle': {'max_hit': 1},
    'BattleEnterNormalBattleFlow': {'next': [
        'CommonPurchaseGemBlocked', 'NikkeCampaignBattleMultipleBlocked',
        'BattleEntered', '[JumpBack]CommonConfirmAction', '[JumpBack]BattleEnterNormalBattle',
    ], 'on_error': [BLOCKED]},
    'BattleInBattleFlow': {'next': [
        'CommonPurchaseGemBlocked', 'NikkeCampaignBattleMultipleBlocked', CHAPTER, LOST,
        '[JumpBack]BattleSkipBossCutscene', '[JumpBack]BattleEnableAutoAim',
        '[JumpBack]BattleEnableAutoCombat', '[JumpBack]DialoguesSkipStory',
        '[JumpBack]CommonConfirmReward', '[JumpBack]CommonConfirmAction',
        'BattleConfirmOperationComplete', 'NikkeCampaignBattleMapCheck',
    ], 'on_error': [BLOCKED]},
    'BattleConfirmOperationComplete': {'max_hit': 5, 'next': ['NikkeCampaignBattleReturn']},
    'CommonPurchaseGemBlocked': {'next': [BLOCKED]},
    # Keep subflow CommonEndTask untouched; never let a boss confirmation buy anything.
    'BattleSkipBossCutscene': {'next': [
        'CommonPurchaseGemBlocked', 'CommonConfirmAction', 'CommonEndTask',
    ]},
}


class NativeBattle:
    """Lazy Resource/Tasker ownership. IDs belong to their respective native APIs."""

    def __init__(self, runtime):
        self.runtime, self.api = runtime, runtime.api
        self.resource = self.tasker = None
        self.resource_id = self.task_id = self.stop_id = self.drain_id = 0
        self.loaded = False
        self.bundle_index = 0
        self.load_started = time.monotonic()
        self.load_ms = None
        self.events = []
        self.event_lock = threading.Lock()
        self.callback = C.CFUNCTYPE(None, P, C.c_char_p, C.c_char_p, P)(self._event)
        for name, result, args in (
            ('MaaResourceCreate', P, []), ('MaaResourceDestroy', None, [P]),
            ('MaaResourcePostBundle', ID, [P, C.c_char_p]), ('MaaResourceStatus', I, [P, ID]),
            ('MaaTaskerCreate', P, []), ('MaaTaskerDestroy', None, [P]),
            ('MaaTaskerBindResource', B, [P, P]), ('MaaTaskerBindController', B, [P, P]),
            ('MaaTaskerPostTask', ID, [P, C.c_char_p, C.c_char_p]),
            ('MaaTaskerStatus', I, [P, ID]), ('MaaTaskerRunning', B, [P]),
            ('MaaTaskerPostStop', ID, [P]), ('MaaTaskerAddContextSink', ID, [P, P, P]),
            ('MaaTaskerGetTaskDetail', B, [P, ID, P, C.POINTER(ID), C.POINTER(U), C.POINTER(I)]),
            ('MaaTaskerGetNodeDetail', B, [P, ID, P, C.POINTER(ID), C.POINTER(ID), C.POINTER(B)]),
            ('MaaStringBufferCreate', P, []), ('MaaStringBufferDestroy', None, [P]),
            ('MaaStringBufferGet', C.c_char_p, [P]),
        ):
            bind(self.api, name, result, args)

    def _event(self, _, message, details, __):
        if message != b'Node.PipelineNode.Succeeded':
            return
        try:
            data = json.loads(details)
            name = data.get('node_details', {}).get('name', data.get('name'))
            with self.event_lock:
                self.events.append((data.get('task_id'), name))
        except (ValueError, TypeError, AttributeError):
            LOG.exception('Invalid battle callback payload')

    def prepare_step(self, cancelled=False):
        if self.loaded:
            return True
        if self.resource_id:
            status = self.api.MaaResourceStatus(self.resource, self.resource_id)
            if status in PENDING:
                return False
            self.resource_id = 0
            if status != 3000:
                raise ControlError('battle_resource_failed', '战斗资源加载失败。')
            self.bundle_index += 1
        if cancelled:
            return True  # A native load was drained; do not submit another one.
        if self.bundle_index < 2:
            if not self.resource:
                self.resource = self.api.MaaResourceCreate()
                if not self.resource:
                    raise ControlError('battle_resource_failed', '无法创建战斗资源。')
            path = (ROOT / 'assets/resource', ROOT / 'tools/nikke_resources')[self.bundle_index]
            self.resource_id = self.api.MaaResourcePostBundle(self.resource, str(path).encode('utf-8'))
            if self.resource_id <= 0:
                self.resource_id = 0
                raise ControlError('battle_resource_failed', '框架拒绝加载战斗资源。')
            return False
        self.tasker = self.api.MaaTaskerCreate()
        if not (self.tasker and self.api.MaaTaskerBindResource(self.tasker, self.resource)
                and self.api.MaaTaskerBindController(self.tasker, self.runtime.controller)
                and self.api.MaaTaskerAddContextSink(self.tasker, C.cast(self.callback, P), None) > 0):
            raise ControlError('battle_tasker_failed', '无法绑定战斗任务和现有控制器。')
        self.loaded = True
        self.load_ms = round((time.monotonic() - self.load_started) * 1000)
        LOG.info('Battle resources loaded in %s ms', self.load_ms)
        return True

    def post(self, entry):
        with self.event_lock:
            self.events.clear()
        self.stop_id = self.drain_id = 0
        self.task_id = self.api.MaaTaskerPostTask(
            self.tasker, entry.encode(), json.dumps(BATTLE_OVERRIDE).encode())
        if self.task_id <= 0:
            self.task_id = 0
            raise ControlError('battle_task_rejected', '框架未接受战斗任务。')

    def task_status(self):
        return self.api.MaaTaskerStatus(self.tasker, self.task_id) if self.task_id else 0

    def running(self):
        return bool(self.tasker and self.api.MaaTaskerRunning(self.tasker))

    def stop(self):
        if self.running() and not self.stop_id:
            self.stop_id = self.api.MaaTaskerPostStop(self.tasker)
            if self.stop_id <= 0:
                self.stop_id = 0
                raise ControlError('battle_stop_rejected', '框架未接受停止，控制器仍由战斗占用。', 'unknown')

    def stopped(self):
        return (not self.running() and (not self.task_id or self.task_status() in (3000, 4000))
                and (not self.stop_id or self.api.MaaTaskerStatus(self.tasker, self.stop_id) in (3000, 4000)))

    def recent_nodes(self):
        with self.event_lock:
            return [name for job, name in self.events if job == self.task_id]

    def completed_nodes(self):
        # Query this specific task rather than GetLatestNode, which can contain old battles.
        size, status = U(), I()
        if not self.api.MaaTaskerGetTaskDetail(self.tasker, self.task_id, None, None,
                                              C.byref(size), C.byref(status)):
            raise ControlError('battle_evidence_failed', '无法读取本次战斗的节点记录。', 'unknown')
        ids = (ID * size.value)()
        if not self.api.MaaTaskerGetTaskDetail(self.tasker, self.task_id, None, ids,
                                              C.byref(size), C.byref(status)):
            raise ControlError('battle_evidence_failed', '无法读取本次战斗的节点列表。', 'unknown')
        buffer = self.api.MaaStringBufferCreate()
        if not buffer:
            raise ControlError('battle_evidence_failed', '无法读取战斗证据。', 'unknown')
        nodes = []
        try:
            for node_id in ids:
                reco, action, completed = ID(), ID(), B()
                if self.api.MaaTaskerGetNodeDetail(self.tasker, node_id, buffer, C.byref(reco),
                                                 C.byref(action), C.byref(completed)) and completed.value:
                    nodes.append(self.api.MaaStringBufferGet(buffer).decode('utf-8'))
        finally:
            self.api.MaaStringBufferDestroy(buffer)
        return nodes

    def drain_step(self):
        # With Tasker stopped, a read-only queue fence proves all earlier inputs
        # have finished. Task/stop IDs must never enter runtime.pending_id.
        if not self.drain_id:
            try:
                self.runtime.ensure_idle()
            except ControlError as error:
                if error.code == 'request_pending':
                    return False
                raise
            self.drain_id = self.api.MaaControllerPostScreencap(self.runtime.controller)
            if self.drain_id <= 0:
                self.drain_id = 0
                raise ControlError('battle_drain_rejected', '无法确认输入队列已排空。', 'unknown')
            self.runtime.pending_id = self.drain_id
        status = self.api.MaaControllerStatus(self.runtime.controller, self.drain_id)
        if status in PENDING or status == 0:
            return False
        self.runtime.pending_id = 0
        return True  # A failed capture still proves the preceding queue was drained.

    def close(self):
        if self.resource_id or not self.stopped():
            raise ControlError('battle_busy', '战斗原生请求尚未停止。', 'unknown')
        if self.tasker:
            self.api.MaaTaskerDestroy(self.tasker)
            self.tasker = None
        if self.resource:
            self.api.MaaResourceDestroy(self.resource)
            self.resource = None


class BattleRunner:
    def __init__(self, control, engine_factory=NativeBattle):
        self.control, self.engine_factory = control, engine_factory
        self.engine = self.thread = None
        self.cancel = threading.Event()
        self.current = None
        self.latest = None
        self.timeout = 300.0
        self.load_timeout = 30.0
        self.stop_timeout = 5.0
        self.poll_interval = 0.05

    def start(self, window):
        self.cancel.clear()
        self.current = {'battle_id': uuid.uuid4().hex, 'status': 'running', 'phase': 'preparing',
                        'tasker_running': False, 'controller_idle': False}
        self.control.owner = 'battle'
        self.thread = threading.Thread(target=self._run, args=(window,), name='nikke-battle')
        try:
            self.thread.start()
        except RuntimeError as error:
            self.current = None
            self.control.owner = 'manual'
            raise ControlError('battle_start_failed', str(error)) from error
        return Result({'type': 'response', 'op': 'battle', 'ok': True, **self.current})

    def stop(self):
        if self.control.owner == 'manual':
            return Result({'ok': True, 'status': 'idle',
                           'controller_idle': not bool(self.control.runtime.pending_id)})
        self.cancel.set()
        self.control.owner = 'stopping'
        self.current.update(status='stopping')
        return Result({'ok': True, **self.current})

    def _update(self, **values):
        with self.control.lock:
            self.current.update(values)

    def _check_window(self, expected):
        current = self.control.windows.inspect(expected.hwnd)
        if current.identity != expected.identity or current.rect != expected.rect or not current.matches:
            raise ControlError('window_changed', '战斗期间窗口身份、位置或尺寸变化。', 'unknown')
        self.control._check_visible(current)

    def _run(self, window):
        started = time.monotonic()
        submitted = False
        nodes = []
        reason = None
        stopping_since = None
        notified = False
        reused = bool(self.engine and self.engine.loaded)

        def guard():
            nonlocal reason, stopping_since, notified
            if reason is None:
                if self.cancel.is_set():
                    reason = ('cancelled', 'stop_requested')
                elif time.monotonic() - started >= self.timeout:
                    reason = ('timed_out', 'battle_timeout')
                else:
                    try:
                        self._check_window(window)
                    except (ControlError, OSError) as error:
                        reason = ('blocked', getattr(error, 'code', 'window_unavailable'))
            if reason:
                with self.control.lock:
                    self.control.owner = 'stopping'
                    self.current.update(status='stopping')
                stopping_since = stopping_since or time.monotonic()
                if not notified and time.monotonic() - stopping_since >= self.stop_timeout:
                    self._emit(Result({'type': 'battle.stopping', 'ok': False, **self.current,
                                       'reason': 'stop_pending', 'controller_idle': False}))
                    notified = True

        def wait_task():
            stop_error_logged = False
            while True:
                guard()
                recent = self.engine.recent_nodes()
                self._update(tasker_running=self.engine.running(), last_node=recent[-1] if recent else None)
                if reason:
                    try:
                        self.engine.stop()
                    except ControlError:
                        if not stop_error_logged:
                            LOG.exception('Battle stop request rejected; keeping ownership')
                            stop_error_logged = True
                if self.engine.stopped():
                    return
                time.sleep(self.poll_interval)

        try:
            guard()
            if not reason:
                if self.engine is None:
                    self.engine = self.engine_factory(self.control.runtime)
                while not self.engine.prepare_step(cancelled=bool(reason)):
                    guard()
                    if reason is None and time.monotonic() - started >= self.load_timeout:
                        reason = ('timed_out', 'resource_timeout')
                    time.sleep(self.poll_interval)
                guard()
            if not reason:
                self._update(phase='validating')
                self.engine.post(PROBE)
                wait_task()
                if not reason and (self.engine.task_status() != 3000 or
                                   'NikkeCampaignBattlePreparation' not in self.engine.completed_nodes()):
                    reason = ('blocked', 'not_preparation')
            if not reason:
                guard()
            if not reason:
                self._update(phase='battle')
                submitted = True
                try:
                    self.engine.post(ENTRY)
                except ControlError as error:
                    if error.code == 'battle_task_rejected':
                        submitted = False
                    raise
                wait_task()
                nodes = self.engine.completed_nodes()
                if not reason and (self.engine.task_status() != 3000 or
                                   not ({MAP, CHAPTER} & set(nodes)) or BLOCKED in nodes):
                    reason = ('blocked', 'handoff_blocked')
        except Exception as error:
            LOG.exception('Battle worker failed')
            reason = reason or ('failed', getattr(error, 'code', 'battle_failed'))
        finally:
            # Never release a controller while a native load/task/input can use it.
            # A stuck native request keeps this non-daemon worker and its resources alive.
            self._update(phase='returning')
            cleanup_error_logged = False
            while self.engine:
                guard()
                try:
                    if self.engine.resource_id:
                        if not self.engine.prepare_step(cancelled=True):
                            time.sleep(self.poll_interval)
                            continue
                    if not self.engine.stopped():
                        self.engine.stop()
                    elif self.engine.drain_step():
                        if not self.engine.loaded:
                            self.engine.close()
                            self.engine = None
                        break
                except Exception:
                    if not cleanup_error_logged:
                        LOG.exception('Battle cleanup pending; keeping ownership')
                        cleanup_error_logged = True
                    reason = reason or ('failed', 'cleanup_pending')
                stopping_since = stopping_since or time.monotonic()
                if time.monotonic() - stopping_since >= self.stop_timeout and not notified:
                    reason = reason or ('failed', 'stop_pending')
                time.sleep(self.poll_interval)
            if submitted and not nodes and self.engine:
                try:
                    nodes = self.engine.completed_nodes()
                except Exception:
                    LOG.exception('Battle evidence unavailable')
            state = ('chapter_transition' if CHAPTER in nodes else 'campaign_map' if MAP in nodes else
                     'result' if LOST in nodes or 'BattleConfirmOperationComplete' in nodes else
                     'combat' if 'BattleEntered' in nodes else 'unknown')
            if reason and reason[1] in ('window_changed', 'window_not_foreground', 'window_closed'):
                state = 'unknown'
            outcome = 'lost' if LOST in nodes else 'unknown' if submitted else 'not_started'
            data = {'type': 'battle.finished', 'battle_id': self.current['battle_id'],
                    'ok': reason is None, 'status': reason[0] if reason else 'completed',
                    'outcome': outcome, 'return_state': state, 'controller_idle': True,
                    'input_status': 'unknown' if submitted and reason else 'completed' if submitted else 'not_sent',
                    'resource_reused': reused, 'resource_load_ms': self.engine.load_ms if self.engine else None,
                    'elapsed_ms': round((time.monotonic() - started) * 1000)}
            if reason:
                data['reason'] = reason[1]
            try:
                result = self.control._capture(False)
                data.update(result.data, observation_status='completed')
                data['ok'] = reason is None
                result.data = data
            except Exception as error:
                self.control.snapshot = None
                result = Result({**data, 'ok': False, 'observation_status': 'failed',
                                 'error': {'code': getattr(error, 'code', 'screenshot_failed'), 'message': str(error)}})
            # Final capture uses the manual runtime's bounded wait. If it timed
            # out, that native request is still alive and ownership must stay here.
            capture_wait = time.monotonic()
            capture_error_logged = False
            while self.control.runtime.pending_id:
                try:
                    self.control.runtime.ensure_idle()
                except Exception as error:
                    if getattr(error, 'code', None) != 'request_pending' and not capture_error_logged:
                        LOG.exception('Cannot confirm final capture completion; keeping ownership')
                        capture_error_logged = True
                    with self.control.lock:
                        self.control.owner = 'stopping'
                        self.current.update(status='stopping')
                    if not notified and time.monotonic() - capture_wait >= self.stop_timeout:
                        self._emit(Result({'type': 'battle.stopping', 'ok': False, **self.current,
                                           'reason': 'stop_pending', 'controller_idle': False}))
                        notified = True
                    time.sleep(self.poll_interval)
            # Match the CLI's output-lock -> command-lock order. Publication and
            # handoff form one transaction: the next command after the event
            # cannot observe stale battle ownership or overwrite its image early.
            with self.control.event_lock:
                try:
                    self._emit(result)
                finally:
                    with self.control.lock:
                        self.latest = result.data
                        self.current = None
                        self.control.owner = 'manual'

    def _emit(self, result):
        if self.control.event_sink:
            self.control.event_sink(result)

    def close(self):
        if self.control.owner != 'manual':
            raise ControlError('battle_busy', '请先 stop 并等待 battle.finished。')
        if self.engine:
            self.engine.close()
            self.engine = None
