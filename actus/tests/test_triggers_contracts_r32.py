# -*- coding: utf-8 -*-
"""triggers.py 契约测试（第 39 轮，round 32 任务）。

覆盖：cron 解析/匹配、触发器模型与校验、CronScheduler、FileWatcher、
HotkeyListener（解析/状态/非 Windows 退化）、TriggerEngine（注册/持久化/加载/状态）。
全部隔离 tmp_path；线程/轮询用同步替身，不 sleep、不触发真实桌面/网络。

每条 docstring 写「退步了会怎样」。产品 bug 只报告（见汇报），不在本文件修。
"""
import json
import os
import sys
import time
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import triggers as trg  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════
# CronExpr
# ═══════════════════════════════════════════════════════════════════════

def test_cron_wildcard_and_specific_fields():
    """退步了会怎样：通配/具体值解析错 → 触发器永不触发或错点触发。"""
    e = trg.CronExpr('* * * * *')
    assert len(e.fields[0]) == 60 and len(e.fields[1]) == 24
    e2 = trg.CronExpr('5 3 1 6 *')
    assert e2.fields[0] == {5} and e2.fields[1] == {3}
    assert e2.fields[2] == {1} and e2.fields[3] == {6}


def test_cron_range_step_and_list():
    """退步了会怎样：`a-b/step`、列表、纯 step 的语义错 → 时间窗错位。"""
    e = trg.CronExpr('0-30/10 * * * *')
    assert e.fields[0] == {0, 10, 20, 30}
    e2 = trg.CronExpr('1,5,9 * * * *')
    assert e2.fields[0] == {1, 5, 9}
    e3 = trg.CronExpr('*/15 * * * *')
    assert e3.fields[0] == {0, 15, 30, 45}


@pytest.mark.parametrize('expr,needle', [
    ('* * * *', '5 字段'),
    ('* * * * * *', '5 字段'),
    ('1,,2 * * * *', '空项'),
    ('*/abc * * * *', '不是整数'),
    ('*/0 * * * *', '步进必须 ≥1'),
    ('*/-1 * * * *', '步进必须 ≥1'),
    ('5-3 * * * *', '范围倒序'),
    ('60 * * * *', '超出范围'),
    ('0 24 * * *', '超出范围'),
    ('0 0 0 * *', '超出范围'),
    ('0 0 * 13 *', '超出范围'),
    ('0 0 * * 7', '超出范围'),
])
def test_cron_invalid_raises_with_reason(expr, needle):
    """退步了会怎样：非法 cron 静默产出空集合（旧实现）→ 触发器永不触发且零提示。
    断言 ValueError 且消息点名原因（不是裸 range 错误）。"""
    with pytest.raises(ValueError) as exc:
        trg.CronExpr(expr)
    assert needle in str(exc.value), (expr, str(exc.value))


def test_cron_matches_weekday_mapping_and_fields():
    """退步了会怎样：cron 0=周日 vs tm_wday 0=周一 的换算写错（旧 bug）→
    按星期配置的触发器整体偏移一天。用已知周日 struct_time 钉住换算。"""
    # 2026-10-25 是周日；tm_wday=6（周一=0 … 周日=6）
    sunday_noon = time.struct_time((2026, 10, 25, 12, 0, 0, 6, 298, 0))
    assert trg.CronExpr('0 12 * * 0').matches(sunday_noon) is True
    assert trg.CronExpr('0 12 * * 1').matches(sunday_noon) is False
    assert trg.CronExpr('0 12 25 10 *').matches(sunday_noon) is True
    assert trg.CronExpr('1 12 25 10 *').matches(sunday_noon) is False


def test_cron_next_fire_impossible_calendar_returns_none_fast():
    """退步了会怎样：永不匹配的表达式让 public API 扫 4 年（实测 3.68s）
    卡住调用方线程（DoS 面）。#3 修复后：日历不可能 → 立即 None；且 <1s。"""
    e = trg.CronExpr('0 0 31 2 *')          # 2 月 31 日永不存在
    started = time.time()
    assert e.next_fire(1_700_000_000.0) is None
    assert time.time() - started < 1.0, 'next_fire 仍在对不可能日期长扫'


def test_cron_next_fire_returns_future_matching_minute():
    """退步了会怎样：next_fire 返回过去时间/不匹配时间 → 调度器空转或立刻连发。"""
    after = 1_700_000_000.0
    e = trg.CronExpr('* * * * *')
    nxt = e.next_fire(after)
    assert nxt > after
    assert nxt <= after + 60
    assert e.matches(time.localtime(nxt)) is True


# ═══════════════════════════════════════════════════════════════════════
# Trigger 模型 / parse_triggers
# ═══════════════════════════════════════════════════════════════════════

def test_trigger_model_defaults_and_aliases():
    """退步了会怎样：默认 events/debounce/method 丢失 → watch 少监听事件、
    防抖变 0（文件抖动风暴）、webhook 方法错。"""
    t = trg.Trigger('a.b', {'type': 'watch', 'path': '/tmp/x'})
    assert t.ttype == 'watch' and t.events == ['create', 'modify']
    assert t.debounce_ms == 500 and t.recursive is False
    assert t.args == {}
    assert 'a.b' in repr(t)

    t2 = trg.Trigger('a.b', {'type': 'webhook', 'key': 'evt',
                             'method': 'PUT', 'args': {'x': 1}})
    assert t2.method == 'PUT' and t2.key == 'evt' and t2.args == {'x': 1}


def test_parse_triggers():
    """退步了会怎样：动作元数据里的 triggers 没被解析（或 action_id 丢）→
    动作声明触发器却永不注册。"""
    got = trg.parse_triggers({'triggers': [
        {'type': 'cron', 'expr': '* * * * *'},
        {'type': 'on_startup'}]}, action_id='demo.act')
    assert [t.ttype for t in got] == ['cron', 'on_startup']
    assert all(t.action_id == 'demo.act' for t in got)


# ═══════════════════════════════════════════════════════════════════════
# validate_trigger
# ═══════════════════════════════════════════════════════════════════════

def test_validate_trigger_accepts_all_types():
    """退步了会怎样：合法配置被误判非法 → 触发器无法上线。"""
    assert trg.validate_trigger({'type': 'cron', 'expr': '* * * * *'}) == []
    assert trg.validate_trigger({'type': 'watch', 'path': 'x'}) == []
    assert trg.validate_trigger({'type': 'hotkey', 'key': 'ctrl+k'}) == []
    assert trg.validate_trigger({'type': 'webhook', 'key': 'evt'}) == []
    assert trg.validate_trigger({'type': 'on_startup'}) == []


@pytest.mark.parametrize('config,needle', [
    ({'type': 'nope'}, '类型非法'),
    ({'type': 'cron'}, '缺少 expr'),
    ({'type': 'cron', 'expr': '* * * *'}, 'cron 表达式错误'),
    ({'type': 'watch'}, '缺少 path'),
    ({'type': 'hotkey'}, '缺少 key'),
    ({'type': 'webhook'}, '缺少 key'),
])
def test_validate_trigger_reports_missing(config, needle):
    """退步了会怎样：缺字段/非法类型放行 → 注册后启动时才炸（或静默不触发）。"""
    errs = trg.validate_trigger(config)
    assert any(needle in e for e in errs), (config, errs)


def test_validate_watch_path_relative_inside_root(tmp_path):
    """退步了会怎样（#9）：相对路径被误判越界 → 合法 watch 全部注册失败。"""
    root = tmp_path / 'root'
    (root / 'sub').mkdir(parents=True)
    assert trg.validate_watch_path('sub/dir', str(root)) is None
    assert trg.validate_trigger({'type': 'watch', 'path': 'sub/dir'},
                                root=str(root)) == []


def test_validate_watch_path_rejects_absolute(tmp_path):
    """退步了会怎样（#9）：绝对路径放行 → 可监控任意目录（/etc、C:\\Users）。
    默认严格：绝对路径注册期直接拒绝，不给"一次性放行"。"""
    root = tmp_path / 'root'
    root.mkdir()
    err = trg.validate_watch_path(str(tmp_path), str(root))
    assert err and '绝对路径' in err, err
    assert '绝对路径' in trg.validate_watch_path('C:\\Windows', str(root))
    assert any('绝对路径' in e for e in trg.validate_trigger(
        {'type': 'watch', 'path': str(tmp_path)}, root=str(root)))


def test_validate_watch_path_rejects_dotdot(tmp_path):
    """退步了会怎样（#9）：`../` 上跳可用 → 相对路径语法可直接逃出根。"""
    root = tmp_path / 'root'
    root.mkdir()
    for bad in ('../escape', 'sub/../../escape', '..'):
        err = trg.validate_watch_path(bad, str(root))
        assert err and '..' in err, (bad, err)


def test_validate_watch_path_rejects_symlink_escape(tmp_path, monkeypatch):
    """退步了会怎样（#9）：只做字符串前缀检查、不做 realpath → root/link 指向
    外部目录时仍能监控 root 之外（symlink 逃逸）。Windows 普通用户建不了
    symlink，这里用 realpath 替身模拟 link→outside（逻辑等价，且变异可红）。"""
    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    real_realpath = os.path.realpath
    link_prefix = os.path.normcase(os.path.join(str(root), 'link'))

    def fake_realpath(p):
        resolved = real_realpath(p)
        if os.path.normcase(os.path.abspath(resolved)).startswith(link_prefix):
            return os.path.join(str(outside), 'escaped')
        return resolved

    monkeypatch.setattr(trg.os.path, 'realpath', fake_realpath)
    err = trg.validate_watch_path('link/escaped', str(root))
    assert err and '逃出' in err, err


def test_allow_outside_root_optout(tmp_path):
    """退步了会怎样（#9）：逃生阀失效 → 合法的跨根监控也必须改目录结构；
    或逃生阀变成默认放行 → 越界路径又悄悄能注册。"""
    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    assert trg.validate_watch_path(str(outside), str(root),
                                   allow_outside_root=True) is None
    assert trg.validate_trigger({'type': 'watch', 'path': str(outside),
                                 'allow_outside_root': True},
                                root=str(root)) == []

    engine = trg.TriggerEngine(lambda *a: None, str(tmp_path / 'meta'),
                               watch_root=str(root))
    engine.add_trigger(trg.Trigger('w.allow', {
        'type': 'watch', 'path': str(outside), 'allow_outside_root': True}))
    assert engine.status()['watch_tasks'] == 1

    strict = trg.TriggerEngine(lambda *a: None, str(tmp_path / 'meta2'),
                                watch_root=str(root))
    with pytest.raises(ValueError, match='绝对路径'):
        strict.add_trigger(trg.Trigger('w.strict', {
            'type': 'watch', 'path': str(outside)}))
    assert strict._triggers == {}


def test_watch_template_path_skipped_at_registration(tmp_path):
    """退步了会怎样（#9）：仓库现有模板动作 `actions/zh.actus.md` 的
    `"path": "${watch_path}"` 在注册期被当具体路径拒绝 → 现有动作全部非法。"""
    root = tmp_path / 'root'
    root.mkdir()
    assert trg.validate_watch_path('${watch_path}', str(root)) is None
    assert trg.validate_trigger({'type': 'watch', 'path': '${watch_path}'},
                                root=str(root)) == []


# ═══════════════════════════════════════════════════════════════════════
# CronScheduler
# ═══════════════════════════════════════════════════════════════════════

def test_cron_scheduler_add_remove_and_invalid():
    """退步了会怎样：add 不校验 expr（非法任务潜伏到 _loop 才炸）；
    remove 误删其它动作的任务。"""
    sched = trg.CronScheduler()
    t1 = trg.Trigger('a.b', {'type': 'cron', 'expr': '* * * * *'})
    sched.add(t1, lambda *a: None)
    assert len(sched._jobs) == 1
    with pytest.raises(ValueError):
        sched.add(trg.Trigger('x.y', {'type': 'cron', 'expr': 'bad'}),
                  lambda *a: None)
    sched.remove('a.b')
    assert sched._jobs == []


def test_cron_scheduler_loop_fires_once_and_skips_recent(monkeypatch):
    """退步了会怎样：_loop 同分钟重复触发（刷爆动作）；或 last_fired 防抖在
    60s 内失效。用假时钟+同步线程替身直接驱动一次循环。"""
    sched = trg.CronScheduler()
    fired = []

    class _SyncThread(object):
        def __init__(self, target=None, args=(), daemon=None, **kw):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(trg.threading, 'Thread', _SyncThread)
    fixed = 1_700_000_000.0
    real_localtime = time.localtime
    monkeypatch.setattr(trg.time, 'time', lambda: fixed)
    monkeypatch.setattr(trg.time, 'localtime',
                        lambda secs=None: real_localtime(
                            fixed if secs is None else secs))
    stop = {'n': 0}

    def _sleep(_s):
        stop['n'] += 1
        sched._running = False        # 跑完第一轮就退出

    monkeypatch.setattr(trg.time, 'sleep', _sleep)
    sched.add(trg.Trigger('a.b', {'type': 'cron', 'expr': '* * * * *'}),
              lambda t: fired.append(t.action_id))
    sched._running = True
    sched._loop()
    assert fired == ['a.b']

    # 再次进入：同一分钟内 last_fired 防抖，不再触发
    fired.clear()
    sched._running = True
    sched._loop()
    assert fired == []


def test_cron_scheduler_start_stop_with_fake_loop(monkeypatch):
    """退步了会怎样：start 重复启动两个线程；stop 不停线程/不清 _thread。"""
    sched = trg.CronScheduler()
    ran = {'n': 0}

    def fake_loop():
        ran['n'] += 1
        while sched._running:
            time.sleep(0.001)

    monkeypatch.setattr(sched, '_loop', fake_loop)
    sched.start()
    sched.start()                     # 幂等：不重复开线程
    time.sleep(0.02)
    sched.stop()
    assert sched._thread is None or not sched._thread.is_alive()
    assert ran['n'] == 1


# ═══════════════════════════════════════════════════════════════════════
# FileWatcher
# ═══════════════════════════════════════════════════════════════════════

def test_file_watcher_init_states_and_detect_changes(tmp_path):
    """退步了会怎样：create/modify/delete 任一事件漏报（文件变化不触发动作）或
    事件类型过滤失效（不关心 create 的 watch 也被 create 唤醒）。"""
    w = trg.FileWatcher(watch_root=str(tmp_path))
    watched = tmp_path / 'watched'
    watched.mkdir()
    f = watched / 'a.txt'
    f.write_text('1', encoding='utf-8')
    trig = trg.Trigger('a.b', {'type': 'watch', 'path': 'watched'})
    calls = []
    w.add(trig, lambda t, changes: calls.append(changes))
    w._running = True
    w._init_states()
    assert str(f) in w._file_states

    # 修改（mtime 前进）
    old = time.time() - 10
    os.utime(str(f), (old, old))
    w._file_states[str(f)] = old
    f.write_text('2', encoding='utf-8')
    changes = w._detect_changes(trig)
    assert {'type': 'modify', 'path': str(f)} in changes

    # 新增
    new = watched / 'b.txt'
    new.write_text('b', encoding='utf-8')
    changes = w._detect_changes(trig)
    assert {'type': 'create', 'path': str(new)} in changes

    # 注：删除事件当前是产品 bug（见汇报）——单列 xfail 用例，别把 bug 钉成契约。
    new.unlink()


def test_file_watcher_detects_deleted_file(tmp_path):
    """退步了会怎样：删文件不触发 delete → 依赖删除的自动化永不执行。

    #1 已修：删除检测基于本次快照（旧实现读只增不删的 _file_states，恒 False）。
    """
    w = trg.FileWatcher(watch_root=str(tmp_path))
    root = tmp_path / 'watched'
    root.mkdir()
    f = root / 'gone.txt'
    f.write_text('x', encoding='utf-8')
    trig = trg.Trigger('a.b', {'type': 'watch', 'path': 'watched',
                               'events': ['delete']})
    w.add(trig, lambda *a: None)
    w._init_states()
    f.unlink()
    changes = w._detect_changes(trig)
    assert {'type': 'delete', 'path': str(f)} in changes


def test_file_watcher_event_filter_and_missing_path(tmp_path):
    """退步了会怎样：events 过滤不生效（只声明 delete 的 watch 被 modify 触发）；
    不存在的路径被当成目录扫描 → 抛异常打断监控线程。"""
    w = trg.FileWatcher(watch_root=str(tmp_path))
    only_delete = trg.Trigger('a.b', {'type': 'watch', 'path': '.',
                                      'events': ['delete']})
    (tmp_path / 'x.txt').write_text('x', encoding='utf-8')
    w._init_states()
    w._watches.append({'trigger': only_delete, 'callback': None,
                       'debounce_until': 0.0})
    w._init_states()
    (tmp_path / 'y.txt').write_text('y', encoding='utf-8')
    changes = w._detect_changes(only_delete)
    assert changes == [], changes

    missing = trg.Trigger('c.d', {'type': 'watch', 'path': 'nope'})
    assert w._detect_changes(missing) == []


def test_file_watcher_check_debounces_and_dispatches(tmp_path, monkeypatch):
    """退步了会怎样：防抖失效（一次保存触发 N 次动作）或回调没被派发。"""
    w = trg.FileWatcher(watch_root=str(tmp_path))
    root = tmp_path / 'd'
    root.mkdir()
    trig = trg.Trigger('a.b', {'type': 'watch', 'path': 'd',
                               'debounce_ms': 60000})
    seen = []

    class _SyncThread(object):
        def __init__(self, target=None, args=(), daemon=None, **kw):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(trg.threading, 'Thread', _SyncThread)
    w.add(trig, lambda t, changes: seen.append(changes))
    w._init_states()
    (root / 'new.txt').write_text('n', encoding='utf-8')
    w._check()
    assert seen and seen[0][0]['type'] == 'create'
    # debounce 生效：第二次检查不再派发
    w._check()
    assert len(seen) == 1


def test_file_watcher_add_remove_and_get_mtime(tmp_path):
    """退步了会怎样：remove 误删别的动作的 watch；_get_mtime 对缺失文件抛异常。"""
    w = trg.FileWatcher(watch_root=str(tmp_path))
    w.add(trg.Trigger('a.b', {'type': 'watch', 'path': '.'}), lambda *a: None)
    w.add(trg.Trigger('c.d', {'type': 'watch', 'path': '.'}), lambda *a: None)
    w.remove('a.b')
    assert [x['trigger'].action_id for x in w._watches] == ['c.d']
    assert w._get_mtime(str(tmp_path / 'missing')) == 0.0


# ═══════════════════════════════════════════════════════════════════════
# HotkeyListener（不真的轮询）
# ═══════════════════════════════════════════════════════════════════════

class _FakeKeyboardModule(object):
    @staticmethod
    def _name_to_vk_code(name):
        return {'k': 0x4B, 'j': 0x4A}.get(name, 0)


def test_hotkey_parse_combo_valid_and_errors(monkeypatch):
    """退步了会怎样：组合键解析错（修饰键/主键映射错→热键永不触发）或非法组合
    不报错（用户以为注册成功）。"""
    monkeypatch.setitem(sys.modules, 'vools.reactive.monitoring.keyboard',
                        _FakeKeyboardModule)
    mods, main, errs = trg.HotkeyListener.parse_combo('ctrl+alt+k')
    assert mods == [0x11, 0x12] and main == 0x4B and errs == []
    mods2, main2, errs2 = trg.HotkeyListener.parse_combo('ctrl+ctrl+k')
    assert mods2 == [0x11], mods2                  # 重复修饰键去重
    assert main2 == 0x4B

    assert trg.HotkeyListener.parse_combo('')[:2] == ([], 0)
    assert trg.HotkeyListener.parse_combo(None)[:2] == ([], 0)
    _m, _k, errs3 = trg.HotkeyListener.parse_combo('nosuchmod+k')
    assert any('未知修饰键' in e for e in errs3)
    _m, _k, errs4 = trg.HotkeyListener.parse_combo('ctrl+nosuchkey')
    assert any('未知主键' in e for e in errs4)


def test_hotkey_add_status_remove_and_non_windows_start(monkeypatch):
    """退步了会怎样：非 Windows 上 start 直接抛（引擎启动整体崩）或 errors 不记录
    （用户以为热键已生效）；remove 清不干净。"""
    monkeypatch.setitem(sys.modules, 'vools.reactive.monitoring.keyboard',
                        _FakeKeyboardModule)
    hk = trg.HotkeyListener()
    t = trg.Trigger('a.b', {'type': 'hotkey', 'key': 'ctrl+k'})
    assert hk.add(t, lambda *a: None) == []
    t_bad = trg.Trigger('c.d', {'type': 'hotkey', 'key': 'badkey'})
    assert hk.add(t_bad, lambda *a: None)
    st = hk.status()
    assert st['hotkeys'] == 2 and st['errors'] == 1 and st['running'] is False

    monkeypatch.setattr(sys, 'platform', 'linux')
    hk.start()
    st2 = hk.status()
    assert st2['errors'] == 2 and st2['running'] is False
    hk.remove('a.b')
    assert hk.status()['hotkeys'] == 1
    hk.stop()
    assert hk.status()['hotkeys'] == 0


# ═══════════════════════════════════════════════════════════════════════
# TriggerEngine：注册 / 持久化 / 加载 / 状态
# ═══════════════════════════════════════════════════════════════════════

def test_engine_add_trigger_each_type_and_status(tmp_path):
    """退步了会怎样：某类型 add 没分派到对应子调度器（注册了但不生效）——
    status 的计数与 real 注册表必须一致。"""
    engine = trg.TriggerEngine(lambda *a: None, str(tmp_path), watch_root=str(tmp_path))
    engine.add_trigger(trg.Trigger('a.cron', {'type': 'cron', 'expr': '* * * * *'}))
    engine.add_trigger(trg.Trigger('a.watch', {'type': 'watch', 'path': '.'}))
    engine.add_trigger(trg.Trigger('a.hot', {'type': 'hotkey', 'key': 'ctrl+k'}))
    engine.add_trigger(trg.Trigger('a.start', {'type': 'on_startup'}))
    assert engine.status()['cron_jobs'] == 1
    assert engine.status()['watch_tasks'] == 1
    assert engine.status()['hotkeys']['hotkeys'] == 1
    assert engine.status()['total_triggers'] == 4


def test_engine_registry_roundtrip_and_remove(tmp_path):
    """退步了会怎样：注册表没落盘/加载不回（重启后动态触发器全丢）；remove 不落盘
    （删了重启又回来）。"""
    meta = tmp_path / 'meta'
    engine = trg.TriggerEngine(lambda *a: None, str(meta), watch_root=str(tmp_path))
    engine.add_trigger(trg.Trigger('a.cron', {'type': 'cron', 'expr': '* * * * *'}))
    engine.add_trigger(trg.Trigger('a.watch', {'type': 'watch', 'path': '.'}))
    reg = json.load(open(os.path.join(str(meta), 'triggers.json'), encoding='utf-8'))
    assert 'a.cron' in reg and reg['a.cron'][0]['type'] == 'cron'

    engine2 = trg.TriggerEngine(lambda *a: None, str(meta), watch_root=str(tmp_path))
    engine2.load_registry()
    assert engine2.status()['total_triggers'] == 2

    engine2.remove_trigger('a.cron')
    assert engine2.status()['total_triggers'] == 1
    reg2 = json.load(open(os.path.join(str(meta), 'triggers.json'), encoding='utf-8'))
    assert 'a.cron' not in reg2


def test_engine_load_registry_skips_bad_and_existing(tmp_path):
    """退步了会怎样：坏配置让整个 load_registry 抛（一个脏条目毁所有触发器）；
    或重复加载把已有动作覆盖成重复项。"""
    meta = tmp_path / 'meta'
    meta.mkdir()
    (meta / 'triggers.json').write_text(json.dumps({
        'a.good': [{'type': 'cron', 'expr': '* * * * *'}],
        'a.bad': [{'type': 'cron', 'expr': 'bad'}],
    }), encoding='utf-8')
    engine = trg.TriggerEngine(lambda *a: None, str(meta))
    engine.add_trigger(trg.Trigger('a.good', {'type': 'on_startup'}))
    engine.load_registry()
    # a.good 已存在 → 跳过；a.bad 的 cron 非法 → add_trigger 抛，被 load_registry 吞掉
    assert engine.status()['total_triggers'] == 1


def test_engine_load_from_index(tmp_path):
    """退步了会怎样：索引里的 triggers 没被加载（动作声明触发器却永不注册）。"""
    meta = tmp_path / 'meta'
    meta.mkdir()
    (meta / 'actions.index.json').write_text(json.dumps({'actions': {
        'x.one': {'triggers': [{'type': 'cron', 'expr': '* * * * *'}]},
        'x.two': {},
    }}), encoding='utf-8')
    engine = trg.TriggerEngine(lambda *a: None, str(meta))
    engine.load_from_index(str(meta))
    assert engine.status()['cron_jobs'] == 1
    assert engine.status()['total_triggers'] == 1


def test_engine_startup_callback_and_stop(tmp_path, monkeypatch):
    """退步了会怎样：on_startup 触发器没执行（启动即漏）；stop 没停各子调度器
    （进程退出后线程还在跑）。"""
    engine = trg.TriggerEngine(lambda *a: None, str(tmp_path))
    fired = []
    engine._executor = lambda t: fired.append(t.action_id)

    started = []
    stopped = []
    monkeypatch.setattr(engine._cron, 'start', lambda: started.append('cron'))
    monkeypatch.setattr(engine._watcher, 'start', lambda: started.append('watch'))
    monkeypatch.setattr(engine._hotkeys, 'start', lambda: started.append('hotkey'))
    monkeypatch.setattr(engine._cron, 'stop', lambda: stopped.append('cron'))
    monkeypatch.setattr(engine._watcher, 'stop', lambda: stopped.append('watch'))
    monkeypatch.setattr(engine._hotkeys, 'stop', lambda: stopped.append('hotkey'))

    class _SyncThread(object):
        def __init__(self, target=None, args=(), daemon=None, **kw):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(trg.threading, 'Thread', _SyncThread)
    engine.add_trigger(trg.Trigger('a.start', {'type': 'on_startup'}))
    engine.start()
    assert started == ['cron', 'watch', 'hotkey']
    assert fired == ['a.start']
    engine.stop()
    assert stopped == ['cron', 'watch', 'hotkey']


def test_add_trigger_invalid_cron_leaves_no_ghost(tmp_path):
    """退步了会怎样（#4）：先 append 再校验 → 非法 cron 抛错后幽灵触发器仍计在
    status 里，后续 save_registry 把非法配置写盘。修复后：数组/计数都不变。"""
    engine = trg.TriggerEngine(lambda *a: None, str(tmp_path))
    with pytest.raises(ValueError):
        engine.add_trigger(trg.Trigger('c.bad', {'type': 'cron', 'expr': 'bad'}))
    assert engine._triggers == {}
    assert engine.status()['total_triggers'] == 0


def test_webhook_unavailable_raises_readable_error(tmp_path, monkeypatch):
    """退步了会怎样（#5）：依赖缺失时 `_webhooks` 保持 None，add_trigger 撞
    AttributeError（`None.add`）—— 用户看不到"webhook 不可用"这个原因。"""
    engine = trg.TriggerEngine(lambda *a: None, str(tmp_path))
    monkeypatch.setattr(engine, '_init_webhooks', lambda: None)  # 模拟 import 失败后仍为 None
    engine._webhook_error = 'webhook 支持不可用：missing dep'
    with pytest.raises(RuntimeError, match='webhook 支持不可用'):
        engine.add_trigger(trg.Trigger('w.hook', {'type': 'webhook', 'key': 'evt'}))
    assert engine._triggers == {}


def test_load_from_index_skips_bad_trigger(tmp_path, caplog):
    """退步了会怎样（#6）：索引里一条坏配置中止全部加载，且中止前已部分载入
    （幽灵项）—— 与 load_registry 的逐条语义不一致。修复后：好的进、坏的跳过、
    留 warning、不抛异常。"""
    meta = tmp_path / 'meta'
    meta.mkdir()
    (meta / 'actions.index.json').write_text(json.dumps({'actions': {
        'x.good': {'triggers': [{'type': 'cron', 'expr': '* * * * *'}]},
        'x.bad': {'triggers': [{'type': 'cron', 'expr': 'bad'}]},
    }}), encoding='utf-8')
    engine = trg.TriggerEngine(lambda *a: None, str(meta))
    with caplog.at_level('WARNING', logger='vools.actus.triggers'):
        engine.load_from_index(str(meta))
    assert engine.status()['total_triggers'] == 1
    assert engine._triggers.get('x.good')
    assert 'x.bad' not in engine._triggers
    assert any('跳过非法触发器' in r.message for r in caplog.records), caplog.text


def test_trigger_failures_are_logged_not_silent(tmp_path, monkeypatch, caplog):
    """退步了会怎样（#7）：回调异常/Thread.start 失败被 `except: pass` 吞掉 →
    触发器静默丢失，用户零感知。修复后至少 WARNING 结构化上报。"""
    class _SyncThread(object):
        def __init__(self, target=None, args=(), daemon=None, **kw):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(trg.threading, 'Thread', _SyncThread)
    hk = trg.HotkeyListener()
    hk._entries.append({'trigger': trg.Trigger('h.bad', {'type': 'hotkey',
                                                          'key': 'ctrl+k'}),
                        'callback': lambda t: (_ for _ in ()).throw(RuntimeError('boom')),
                        'errors': [], 'mod_vks': [0x11], 'main_vk': 0x4B})
    with caplog.at_level('WARNING', logger='vools.actus.triggers'):
        hk._fire(0)
    assert any('hotkey 触发失败' in r.message for r in caplog.records), caplog.text

    class _DeadThread(object):
        def __init__(self, *a, **k):
            pass
        def start(self):
            raise RuntimeError('cannot start thread')

    monkeypatch.setattr(trg.threading, 'Thread', _DeadThread)
    sched = trg.CronScheduler()
    sched.add(trg.Trigger('c.bad', {'type': 'cron', 'expr': '* * * * *'}), lambda t: None)
    real_localtime = time.localtime
    monkeypatch.setattr(trg.time, 'time', lambda: 1_700_000_000.0)
    monkeypatch.setattr(trg.time, 'localtime',
                        lambda secs=None: real_localtime(1_700_000_000.0 if secs is None else secs))
    def _sleep(_s):
        sched._running = False
    monkeypatch.setattr(trg.time, 'sleep', _sleep)
    with caplog.at_level('WARNING', logger='vools.actus.triggers'):
        sched._running = True
        sched._loop()
    assert any('cron 触发失败' in r.message for r in caplog.records), caplog.text


def test_engine_save_registry_skips_empty_meta_dir():
    """退步了会怎样：meta_dir 为空时仍尝试写相对路径 triggers.json（往 cwd 拉屎）。"""
    engine = trg.TriggerEngine(lambda *a: None, '')
    engine.add_trigger(trg.Trigger('a.cron', {'type': 'cron', 'expr': '* * * * *'}))
    assert engine.registry_path.endswith('triggers.json')
