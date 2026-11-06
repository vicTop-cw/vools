# -*- coding: utf-8 -*-
"""triggers.py 契约测试补充（第 39 轮，round 99 任务 T0r5）。

目标：把 r32 未覆盖的真实分支钉住 —— cron 范围步进/纯范围/next_fire 循环、
watch 路径空值与跨盘符、FileWatcher 单文件/递归/启动停止/派发失败/陈旧清理、
HotkeyListener win32 真启停与 _poll_loop、_fire 边界、TriggerEngine webhook
全通道与注册表异常通道。全部隔离 tmp_path；线程用同步/死亡替身；
不真跑重探测器；产品代码零修改。

每条 docstring 写「退步了会怎样」。
"""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import triggers as trg  # noqa: E402


class _SyncThread(object):
    def __init__(self, target=None, args=(), daemon=None, **kw):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class _DeadThread(object):
    def __init__(self, *a, **k):
        pass

    def start(self):
        raise RuntimeError('cannot start thread')


class _FakeKeyboardModule(object):
    @staticmethod
    def _name_to_vk_code(name):
        return {'k': 0x4B, 'j': 0x4A}.get(name, 0)


def _fake_keyboard(monkeypatch):
    monkeypatch.setitem(sys.modules, 'vools.reactive.monitoring.keyboard',
                        _FakeKeyboardModule)


# ═══════════════════════════════════════════════════════════════════════
# CronExpr：范围+步进 / 纯范围 / next_fire 循环与默认参
# ═══════════════════════════════════════════════════════════════════════

def test_cron_range_with_step_and_inverted_range():
    """退步了会怎样：`a-b/step` 没展开成 {a,a+step..b} → 命中点稀疏错位；
    倒序范围没报错 → 静默空集合（永不触发）。"""
    e = trg.CronExpr('10-20/5 * * * *')
    assert e.fields[0] == {10, 15, 20}
    with pytest.raises(ValueError, match='范围倒序'):
        trg.CronExpr('20-10/5 * * * *')


def test_cron_step_from_single_start_to_max():
    """退步了会怎样：`10/15`（起点+步进到上限）被当具体值 → 只命中 10 一点，
    命中窗整体丢失。"""
    assert trg.CronExpr('10/15 * * * *').fields[0] == {10, 25, 40, 55}


def test_cron_plain_range():
    """退步了会怎样：纯范围 `a-b` 解析错 → 时间窗整体偏移。"""
    assert trg.CronExpr('5-10 * * * *').fields[0] == {5, 6, 7, 8, 9, 10}


def test_cron_next_fire_default_after_is_now():
    """退步了会怎样：after 缺省没落到当前时间 → next_fire() 返回过去/None。"""
    e = trg.CronExpr('* * * * *')
    nxt = e.next_fire()
    assert nxt is not None and nxt > time.time() - 1


def test_cron_next_fire_walks_forward_to_matching_minute():
    """退步了会怎样：逐分钟递增循环缺失（只查一次）→ 错过下一个命中点，
    调度器整小时空转。断言：从非命中分钟搜到下一个 :30。"""
    e = trg.CronExpr('30 * * * *')
    after = 1_700_000_000.0            # 本地 06:13:2x（+8），非 30 分
    nxt = e.next_fire(after)
    assert nxt is not None and nxt > after
    assert e.matches(time.localtime(nxt)) is True
    assert nxt <= after + 3600


# ═══════════════════════════════════════════════════════════════════════
# validate_watch_path：空值 / 跨盘符逃逸
# ═══════════════════════════════════════════════════════════════════════

def test_validate_watch_path_rejects_empty_and_non_string():
    """退步了会怎样：空串/None 被当合法路径 → os.scandir('') 抛异常打断
    监控线程（或监控整个 cwd）。"""
    assert 'watch 路径为空' in trg.validate_watch_path('', 'C:/tmp')
    assert 'watch 路径为空' in trg.validate_watch_path(None, 'C:/tmp')
    assert 'watch 路径为空' in trg.validate_watch_path('   ', 'C:/tmp')


def test_validate_watch_path_detects_cross_drive_escape(tmp_path, monkeypatch):
    """退步了会怎样：commonpath 的跨盘符 ValueError 没被当成"逃出 root"
    → symlink 把监控指到另一个盘符也不拦。realpath 替身模拟 link→Q: 盘。"""
    root = tmp_path / 'root'
    root.mkdir()
    real_realpath = os.path.realpath
    link_prefix = os.path.normcase(os.path.join(str(root), 'link'))

    def fake_realpath(p):
        resolved = real_realpath(p)
        if os.path.normcase(os.path.abspath(resolved)).startswith(link_prefix):
            return 'Q:\\\\outside\\\\escaped'
        return resolved

    monkeypatch.setattr(trg.os.path, 'realpath', fake_realpath)
    err = trg.validate_watch_path('link/escaped', str(root))
    assert err and '盘符' in err, err


# ═══════════════════════════════════════════════════════════════════════
# FileWatcher：add 校验 / 启停 / 单文件 / 递归 / 派发失败 / 陈旧清理 / loop
# ═══════════════════════════════════════════════════════════════════════

def test_file_watcher_add_rejects_escape_path(tmp_path):
    """退步了会怎样：add 消费点复查缺失 → 模板占位符在运行期被换成越界路径
    后直接扫出去。"""
    w = trg.FileWatcher(watch_root=str(tmp_path))
    with pytest.raises(ValueError, match='watch 触发器 path 非法'):
        w.add(trg.Trigger('a.b', {'type': 'watch', 'path': '../escape'}),
              lambda *a: None)


def test_file_watcher_start_stop_with_fake_loop(tmp_path, monkeypatch):
    """退步了会怎样：start 重复开线程/stop 不停线程 → 监控双份轮询或线程泄漏。"""
    w = trg.FileWatcher(poll_interval=0.01, watch_root=str(tmp_path))
    ran = {'n': 0}

    def fake_loop():
        ran['n'] += 1
        while w._running:
            time.sleep(0.001)

    monkeypatch.setattr(w, '_loop', fake_loop)
    w.start()
    w.start()                          # 幂等
    time.sleep(0.02)
    w.stop()
    assert w._thread is None or not w._thread.is_alive()
    assert ran['n'] == 1


def test_file_watcher_init_states_single_file(tmp_path):
    """退步了会怎样：watch 目标是文件时被按目录扫描 → 永远监控不到。"""
    f = tmp_path / 'file.txt'
    f.write_text('x', encoding='utf-8')
    trig = trg.Trigger('a.b', {'type': 'watch', 'path': 'file.txt'})
    w = trg.FileWatcher(watch_root=str(tmp_path))
    w.add(trig, lambda *a: None)        # 相对路径按 watch_root 展开成绝对
    assert trig.path == str(f)
    w._init_states()                    # 文件（非目录）分支
    assert str(f) in w._file_states
    assert w._file_states[str(f)] > 0


def test_file_watcher_scan_dir_recursive_and_permission_error(tmp_path,
                                                              monkeypatch):
    """退步了会怎样：recursive=True 不下钻子目录（漏文件）；或一个无权限目录
    的 PermissionError 穿透 → 整个 _init_states 崩掉。"""
    w = trg.FileWatcher(watch_root=str(tmp_path))
    root = tmp_path / 'w'
    (root / 'sub').mkdir(parents=True)
    deep = root / 'sub' / 'deep.txt'
    deep.write_text('d', encoding='utf-8')
    out = {}
    w._scan_dir(str(root), True, out)
    assert str(deep) in out

    def boom(path):
        raise PermissionError('denied')

    monkeypatch.setattr(os, 'scandir', boom)
    out2 = {}
    w._scan_dir(str(root), False, out2)     # 必须吞掉 PermissionError
    assert out2 == {}


def test_file_watcher_loop_sleeps_and_exits(tmp_path, monkeypatch):
    """退步了会怎样：_loop 退出条件写错（不检查 _running）→ stop 后线程
    还在轮询。"""
    w = trg.FileWatcher(poll_interval=0.01, watch_root=str(tmp_path))
    w._running = True

    def fake_sleep(_s):
        w._running = False              # 第一轮 sleep 后退出

    monkeypatch.setattr(trg.time, 'sleep', fake_sleep)
    w._loop()                           # 正常返回即契约成立


def test_file_watcher_dispatch_thread_start_failure_logged(tmp_path,
                                                           monkeypatch,
                                                           caplog):
    """退步了会怎样：派发线程启动失败被吞 → 文件事件静默丢失零感知。
    断言：WARNING 留痕。"""
    w = trg.FileWatcher(watch_root=str(tmp_path))
    d = tmp_path / 'd'
    d.mkdir()
    trig = trg.Trigger('a.b', {'type': 'watch', 'path': 'd'})
    w.add(trig, lambda *a: None)
    w._init_states()
    (d / 'new.txt').write_text('n', encoding='utf-8')
    monkeypatch.setattr(trg.threading, 'Thread', _DeadThread)
    with caplog.at_level('WARNING', logger='vools.actus.triggers'):
        w._check()
    assert any('watch 触发失败' in r.message for r in caplog.records), caplog.text


def test_file_watcher_single_file_detect_changes_modify(tmp_path):
    """退步了会怎样：单文件 watch 的 mtime 比对写错 → modify 事件漏报。"""
    f = tmp_path / 'file.txt'
    f.write_text('1', encoding='utf-8')
    trig = trg.Trigger('a.b', {'type': 'watch', 'path': 'file.txt'})
    w = trg.FileWatcher(watch_root=str(tmp_path))
    w.add(trig, lambda *a: None)
    w._init_states()
    old = time.time() - 10
    os.utime(str(f), (old, old))
    w._file_states[str(f)] = old
    f.write_text('2', encoding='utf-8')
    changes = w._detect_changes(trig)
    assert {'type': 'modify', 'path': str(f)} in changes


def test_file_watcher_prunes_stale_states_without_delete_event(tmp_path):
    """退步了会怎样：无 delete 事件的 watch 里，删除文件后 _file_states
    条目永不清理 → 快照无限增长（长跑进程内存泄漏）。"""
    w = trg.FileWatcher(watch_root=str(tmp_path))
    d = tmp_path / 'd'
    d.mkdir()
    f = d / 'x.txt'
    f.write_text('1', encoding='utf-8')
    trig = trg.Trigger('a.b', {'type': 'watch', 'path': 'd'})  # 默认无 delete
    w.add(trig, lambda *a: None)
    w._init_states()
    assert str(f) in w._file_states
    f.unlink()
    w._detect_changes(trig)
    assert str(f) not in w._file_states          # 陈旧条目被清理


# ═══════════════════════════════════════════════════════════════════════
# HotkeyListener：parse 边界 / win32 启停 / _poll_loop / _fire 边界
# ═══════════════════════════════════════════════════════════════════════

def test_parse_combo_no_main_key_reports_error():
    """退步了会怎样：只有修饰键的组合（'++' 拆出空段）不报错 → 用户以为
    注册成功，热键永不触发。"""
    monkeypatch = pytest.MonkeyPatch()
    try:
        _fake_keyboard(monkeypatch)
        _m, _k, errs = trg.HotkeyListener.parse_combo('++')
        assert any('热键组合非法' in e for e in errs), errs
    finally:
        monkeypatch.undo()


def test_hotkey_start_idempotent_and_win32_lifecycle(monkeypatch):
    """退步了会怎样：win32 上 start 重复开两个轮询线程（状态错乱），或 stop
    不 join/不清条目 → 进程退出后线程还按着全局键状态跑。"""
    _fake_keyboard(monkeypatch)
    hk = trg.HotkeyListener()
    hk.add(trg.Trigger('a.b', {'type': 'hotkey', 'key': 'ctrl+k'}),
           lambda *a: None)
    hk._running = True
    hk.start()                          # 已在跑 → 幂等返回，不开线程
    assert hk._thread is None

    hk._running = False

    def fake_loop():
        while hk._running:
            time.sleep(0.001)

    monkeypatch.setattr(hk, '_poll_loop', fake_loop)
    hk.start()
    assert hk._running is True and hk._thread is not None
    time.sleep(0.02)
    hk.stop()
    assert hk._thread is None
    assert hk._entries == [] and hk._key_was_down == {}
    assert hk.status()['running'] is False


def test_hotkey_poll_loop_real_keys_not_pressed(monkeypatch):
    """退步了会怎样：_poll_loop 读键/防抖状态机写错 → 热键连发或永不触发。
    真实 GetAsyncKeyState（未按键）：跑两轮，验证循环与错误条目跳过不崩。"""
    _fake_keyboard(monkeypatch)
    hk = trg.HotkeyListener()
    hk.add(trg.Trigger('a.b', {'type': 'hotkey', 'key': 'ctrl+k'}),
           lambda *a: None)
    hk.add(trg.Trigger('c.d', {'type': 'hotkey', 'key': 'badkey'}),
           lambda *a: None)             # errors 条目 → continue 分支
    hk._running = True
    rounds = {'n': 0}

    def fake_sleep(_s):
        rounds['n'] += 1
        if rounds['n'] >= 2:
            hk._running = False

    monkeypatch.setattr(trg.time, 'sleep', fake_sleep)
    hk._poll_loop()
    assert hk._running is False         # 循环正常退出
    assert rounds['n'] == 2


def test_hotkey_fire_inflight_and_out_of_range():
    """退步了会怎样：inflight 防重入失效 → 回调风暴；越界索引炸 KeyError
    打断轮询线程。"""
    hk = trg.HotkeyListener()
    called = []
    hk._entries.append({'trigger': trg.Trigger('a.b', {'type': 'hotkey',
                                                       'key': 'ctrl+k'}),
                        'callback': lambda t: called.append(t),
                        'errors': [], 'mod_vks': [0x11], 'main_vk': 0x4B,
                        'armed': True})
    hk._inflight[0] = True
    hk._fire(0)                         # inflight 早退：回调不被调
    assert called == []

    hk._fire(99)                        # 越界：e=None，不抛
    assert called == []


def test_hotkey_fire_thread_start_failure_resets_inflight(monkeypatch,
                                                          caplog):
    """退步了会怎样：Thread.start 失败后 inflight 不复位 → 该热键从此永久
    卡死（再也触发不了）。断言：复位 + WARNING 留痕。"""
    monkeypatch.setattr(trg.threading, 'Thread', _DeadThread)
    hk = trg.HotkeyListener()
    hk._entries.append({'trigger': trg.Trigger('a.b', {'type': 'hotkey',
                                                       'key': 'ctrl+k'}),
                        'callback': lambda t: None,
                        'errors': [], 'mod_vks': [0x11], 'main_vk': 0x4B,
                        'armed': True})
    with caplog.at_level('WARNING', logger='vools.actus.triggers'):
        hk._fire(0)
    assert hk._inflight.get(0) is False
    assert any('hotkey 触发线程启动失败' in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════
# TriggerEngine：webhook 通道 / 注册表异常通道 / on_startup 失败留痕
# ═══════════════════════════════════════════════════════════════════════

class _FakeWebhooks(object):
    def __init__(self):
        self.added, self.removed = [], []
        self.started = self.stopped = 0

    def add(self, t, cb):
        self.added.append(t.action_id)

    def remove(self, aid):
        self.removed.append(aid)

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1

    def status(self):
        return {'ok': True}


def test_engine_webhook_lifecycle_with_fake_server(tmp_path, monkeypatch):
    """退步了会怎样：webhook 的 add/remove/start/stop 任一没接到 _webhooks →
    注册了却不上线（或引擎停了 webhook 还在收请求）。"""
    engine = trg.TriggerEngine(lambda *a: None, str(tmp_path / 'meta'),
                               watch_root=str(tmp_path))
    fake = _FakeWebhooks()
    monkeypatch.setattr(engine, '_webhooks', fake)
    engine.add_trigger(trg.Trigger('w.h', {'type': 'webhook', 'key': 'evt'}))
    assert fake.added == ['w.h']
    engine.remove_trigger('w.h')
    assert fake.removed == ['w.h']

    monkeypatch.setattr(engine._cron, 'start', lambda: None)
    monkeypatch.setattr(engine._watcher, 'start', lambda: None)
    monkeypatch.setattr(engine._hotkeys, 'start', lambda: None)
    monkeypatch.setattr(engine._cron, 'stop', lambda: None)
    monkeypatch.setattr(engine._watcher, 'stop', lambda: None)
    monkeypatch.setattr(engine._hotkeys, 'stop', lambda: None)
    engine.start()
    engine.stop()
    assert fake.started == 1 and fake.stopped == 1
    assert engine.status()['webhooks'] == {'ok': True}


def test_engine_init_webhooks_dependency_failure_keeps_reason(tmp_path,
                                                              monkeypatch):
    """退步了会怎样：webhook 依赖缺失时把 ImportError 抛出去 → 引擎启动整体崩。
    断言：_webhooks 保持 None + _webhook_error 带可读原因。"""

    class BadWb(object):
        def __getattr__(self, name):
            raise ImportError('no webhook dep')

    monkeypatch.setitem(sys.modules, 'vools.actus.webhook_server', BadWb())
    engine = trg.TriggerEngine(lambda *a: None, str(tmp_path / 'meta1'))
    engine._init_webhooks()
    assert engine._webhooks is None
    assert 'webhook 支持不可用' in engine._webhook_error


def test_engine_init_webhooks_success_real_import(tmp_path):
    """退步了会怎样：依赖可用的机器上 _init_webhooks 反而建不出实例
    （误把成功当失败）→ webhook 触发器永远 RuntimeError。"""
    engine = trg.TriggerEngine(lambda *a: None, str(tmp_path / 'meta2'))
    engine._init_webhooks()
    assert engine._webhooks is not None
    assert engine._webhook_error is None


def test_engine_on_startup_thread_start_failure_logged(tmp_path, monkeypatch,
                                                       caplog):
    """退步了会怎样：on_startup 的线程启动失败被吞 → 启动动作静默丢失。
    断言：WARNING 留痕，引擎不崩。"""
    engine = trg.TriggerEngine(lambda *a: None, str(tmp_path))
    engine.add_trigger(trg.Trigger('a.start', {'type': 'on_startup'}))
    for sub in (engine._cron, engine._watcher, engine._hotkeys):
        monkeypatch.setattr(sub, 'start', lambda: None)
        monkeypatch.setattr(sub, 'stop', lambda: None)
    monkeypatch.setattr(trg.threading, 'Thread', _DeadThread)
    with caplog.at_level('WARNING', logger='vools.actus.triggers'):
        engine.start()
    assert any('on_startup 触发失败' in r.message for r in caplog.records)


def test_engine_save_registry_swallows_unwritable_meta_dir(tmp_path):
    """退步了会怎样：meta_dir 不可写（路径被文件占用）时 save_registry 抛出
    → add_trigger 连带崩。断言：OSError 被吞、无异常。"""
    blocker = tmp_path / 'blocker'
    blocker.write_text('not a dir', encoding='utf-8')
    engine = trg.TriggerEngine(lambda *a: None, str(blocker))
    engine.add_trigger(trg.Trigger('a.cron',
                                   {'type': 'cron', 'expr': '* * * * *'}))
    assert engine.status()['total_triggers'] == 1   # 注册成功，只是没落盘


def test_engine_load_registry_missing_file_and_bad_json(tmp_path):
    """退步了会怎样：注册表缺失/坏 JSON 让 load_registry 抛 → 引擎初始化
    连带崩（或半加载出幽灵触发器）。断言：两条通道都安静返回空。"""
    engine = trg.TriggerEngine(lambda *a: None, str(tmp_path / 'no_meta'))
    engine.load_registry()              # 文件不存在 → 早退
    assert engine._triggers == {}

    meta = tmp_path / 'meta'
    meta.mkdir()
    (meta / 'triggers.json').write_text('{not json', encoding='utf-8')
    engine2 = trg.TriggerEngine(lambda *a: None, str(meta))
    engine2.load_registry()             # 坏 JSON → 吞掉
    assert engine2._triggers == {}


def test_engine_load_registry_bad_cfg_entry_skipped(tmp_path):
    """退步了会怎样：注册表里一条坏配置让 load_registry 抛/中止 → 好条目
    也丢。断言：坏条目被逐条吞掉、不留幽灵。"""
    meta = tmp_path / 'meta'
    meta.mkdir()
    (meta / 'triggers.json').write_text(json.dumps({
        'a.bad': [{'type': 'cron', 'expr': 'bad'}],
    }), encoding='utf-8')
    engine = trg.TriggerEngine(lambda *a: None, str(meta))
    engine.load_registry()
    assert engine._triggers == {}       # add_trigger 抛错被吞、不进注册表


def test_engine_load_from_index_missing_index_is_noop(tmp_path):
    """退步了会怎样：索引文件不存在时 load_from_index 抛 FileNotFoundError
    → 引擎初始化崩。断言：安静返回。"""
    engine = trg.TriggerEngine(lambda *a: None, str(tmp_path / 'no_meta'))
    engine.load_from_index(str(tmp_path / 'no_meta'))
    assert engine._triggers == {}
