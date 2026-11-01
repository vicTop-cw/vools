# -*- coding: utf-8 -*-
"""probe/system_tools.py 契约测试 r95：补覆盖率 → ≥90%（单模块 --cov 口径）。

被测对象：``vools/actus/probe/system_tools.py`` —— 系统工具探测（PATH 索引
加速 + 两阶段并发查找/取版本 + 版本失败留痕 + 总预算兜底）。

退步会怎样（每条契约破坏时对应红灯）：
  * _path_dirs / PATH='' 语义漂移 → which 判据与真实 which 分歧，
    「装了但没探到」假阴性；
  * _dirs_possibly_containing 不保序 → 优先级顺序改变，同一命令多候选时
    选错二进制；
  * _find_tool_with_meta 的 prefer_non_wrapper 不再绕过 .CMD/.BAT wrapper
    → 版本探测永远走 cmd.exe shim，墙钟回退到秒级长尾；
  * _get_version_detail 失败不再留痕（error=None / extra 缺 kind）
    → 「版本号为空」在报告里看不出原因，回归 8 次并行探测 1 次静默空的旧病；
  * 版本截断 [:200] / 用法文本不当版本号契约漂移 → 下游解析崩或假版本号；
  * _crash_marker 命中后 extra 不带 version_error_kind=crashed
    → JVM 崩溃输出被当成正常版本号；
  * _lookup_one 对坏 TOOL_TABLE 条目不落 invalid 状态 → 一个坏条目炸整批探测；
  * _wait_for 超预算不 cancel 排队 future → 卡死工具把整批拖回串行耗时；
  * probe() 结果不按 TOOL_TABLE 原下标保序 → 报告条目错位；
  * probe() 对预算耗尽不显式标 "not probed" → 「没探到」与「探到没装」混淆；
  * wrapper_timeout_cap 不作用于 .CMD/.BAT → pnpm 类 shim 单工具超时失控。

隔离：全部真实子进程探测只允许用 sys.executable（python 本身），禁真网络；
PATH 篡改走 monkeypatch（自动还原）；TOOL_TABLE 不可变，端到端慢路径用
monkeypatch 字符串寻址替身 _lookup_one/_version_one。
"""

import _ai_local_bootstrap  # noqa: F401  (必须在 import vools.actus 之前)

import concurrent.futures
import os
import sys
import threading
import time

import pytest

from vools.actus.probe import system_tools as S
from vools.actus.probe.base import ProbeItem
from vools.actus.probe.TOOL_TABLE import TOOL_TABLE


@pytest.fixture(autouse=True)
def _rebind_system_tools_identity():
    """bootstrap 身份对齐：monkeypatch 字符串寻址解析 sys.modules 最新条目，
    而模块顶层 import 的 S 可能是被 bootstrap/重装流程替换掉的旧身份。
    每个测试前把模块级 S 重绑到 sys.modules 现值，保证 patch 与调用同一对象。"""
    global S
    import importlib as _il
    S = _il.import_module('vools.actus.probe.system_tools')
    yield



# ---------------------------------------------------------------- path 基元

def test_path_dirs_semantics(monkeypatch):
    # PATH 正常 → split(pathsep)
    monkeypatch.setenv('PATH', os.pathsep.join(['C:\\a', 'C:\\b']))
    assert S._path_dirs() == ['C:\\a', 'C:\\b']
    # PATH='' → which 同口径：找不到任何东西
    monkeypatch.setenv('PATH', '')
    assert S._path_dirs() == []
    # PATH 未设 → os.defpath
    monkeypatch.delenv('PATH')
    monkeypatch.delattr(os, 'PATH') if hasattr(os, 'PATH') else None
    assert S._path_dirs() == os.defpath.split(os.pathsep)


def test_build_path_index_lists_and_keeps_order(tmp_path, monkeypatch):
    d1 = tmp_path / 'a'; d1.mkdir()
    (d1 / 'Tool.EXE').write_bytes(b'x')
    (d1 / 'other.txt').write_bytes(b'x')
    d2 = tmp_path / 'b'; d2.mkdir()
    missing = tmp_path / 'gone'
    monkeypatch.setenv('PATH', os.pathsep.join([str(d1), str(missing), str(d2)]))
    idx = S._build_path_index()
    # 保序；listdir 小写排序；OSError 目录 → 空名元组
    assert [d for d, _ in idx] == [str(d1), str(missing), str(d2)]
    assert idx[0][1] == ('other.txt', 'tool.exe')
    assert idx[1][1] == () and idx[2][1] == ()


def test_dirs_possibly_containing_prefix_and_order(tmp_path, monkeypatch):
    d1 = tmp_path / 'a'; d1.mkdir(); (d1 / 'git.exe').write_bytes(b'x')
    d2 = tmp_path / 'b'; d2.mkdir(); (d2 / 'github.exe').write_bytes(b'x')
    monkeypatch.setenv('PATH', os.pathsep.join([str(d1), str(d2)]))
    idx = S._build_path_index()
    # 前缀筛是超集（git 命中两个目录），保序
    assert S._dirs_possibly_containing('git', idx) == [str(d1), str(d2)]
    # 无 names 的目录被跳过
    monkeypatch.setenv('PATH', str(tmp_path / 'gone'))
    assert S._dirs_possibly_containing('git', S._build_path_index()) == []
    # 不存在的前缀 → 空
    monkeypatch.setenv('PATH', str(d1))
    assert S._dirs_possibly_containing('zzz', S._build_path_index()) == []


def test_lookup_in_path_index_special_cases(tmp_path, monkeypatch):
    exe = tmp_path / 'foo.exe'; exe.write_bytes(b'x')
    monkeypatch.setenv('PATH', str(tmp_path))
    idx = S._build_path_index()
    # 含目录成分：which 直接查该路径，索引不参与
    assert S._lookup_in_path_index(str(exe), idx).lower() == str(exe).lower()
    # 空 cmd → None
    assert S._lookup_in_path_index('', idx) is None
    # 命中：索引缩目录后 which 仍给结果（win32 which 会返回大写扩展名形态）
    found = S._lookup_in_path_index('foo', idx)
    assert found and found.lower() == str(exe).lower()
    # 未命中 → None
    assert S._lookup_in_path_index('zzz', idx) is None


def test_path_candidates_multi_hit_dedup(tmp_path, monkeypatch):
    d1 = tmp_path / 'a'; d1.mkdir(); (d1 / 'x.exe').write_bytes(b'1')
    d2 = tmp_path / 'b'; d2.mkdir(); (d2 / 'x.exe').write_bytes(b'2')
    monkeypatch.setenv('PATH', os.pathsep.join([str(d1), str(d2)]))
    idx = S._build_path_index()
    hits = S._path_candidates('x', idx)
    # 保序 + 去重（win32 which 返回大写扩展名形态，casefold 比较）
    assert [h.lower() for h in hits] == [str(d1 / 'x.exe').lower(), str(d2 / 'x.exe').lower()]
    assert len(hits) == len(set(hits))
    # dirname 成分 → 单命中
    assert [h.lower() for h in S._path_candidates(str(d1 / 'x.exe'), idx)] == [str(d1 / 'x.exe').lower()]
    # 空 cmd → []
    assert S._path_candidates('', idx) == []
    # path_index=None → 全 PATH 扫描仍命中
    assert [h.lower() for h in S._path_candidates('x', None)] == [str(d1 / 'x.exe').lower(), str(d2 / 'x.exe').lower()]


# ---------------------------------------------------------------- _find_tool 契约

def test_find_tool_with_meta_prefer_non_wrapper(tmp_path, monkeypatch):
    wrap = tmp_path / 'w'; wrap.mkdir(); (wrap / 'foo.cmd').write_text('x')
    native = tmp_path / 'n'; native.mkdir(); (native / 'foo.exe').write_bytes(b'x')
    # PATH 先 wrapper 后 native：prefer_non_wrapper 绕过 wrapper
    monkeypatch.setenv('PATH', os.pathsep.join([str(wrap), str(native)]))
    idx = S._build_path_index()
    path, meta = S._find_tool_with_meta('foo', [], {}, idx,
                                        prefer_non_wrapper=True)
    assert path.lower() == str(native / 'foo.exe').lower()
    assert meta['preferred_non_wrapper'] is True
    assert [w.lower() for w in meta['skipped_wrappers']] == [str(wrap / 'foo.cmd').lower()]
    # 候选全是 wrapper → 取第一个（不发明新顺序）
    monkeypatch.setenv('PATH', str(wrap))
    path2, meta2 = S._find_tool_with_meta('foo', [], {}, S._build_path_index(),
                                          prefer_non_wrapper=True)
    assert path2.lower() == str(wrap / 'foo.cmd').lower()
    assert meta2['preferred_non_wrapper'] is False and meta2['skipped_wrappers'] == []
    # 默认（False）→ 与改前逐字等价：取第一个候选
    monkeypatch.setenv('PATH', os.pathsep.join([str(wrap), str(native)]))
    path3, _ = S._find_tool_with_meta('foo', [], {}, S._build_path_index())
    assert path3.lower() == str(wrap / 'foo.cmd').lower()


def test_find_tool_aliases_and_well_known_paths(tmp_path, monkeypatch):
    # PATH 未命中 → alias 兜底
    a = tmp_path / 'bin'; a.mkdir(); (a / 'py.exe').write_bytes(b'x')
    monkeypatch.setenv('PATH', str(a))
    path, meta = S._find_tool_with_meta('python3', ['py'], {},
                                        S._build_path_index())
    assert path.lower() == str(a / 'py.exe').lower()
    assert meta == {'preferred_non_wrapper': False, 'skipped_wrappers': []}
    # PATH='' + well_known glob 命中
    monkeypatch.setenv('PATH', '')
    hit = S._find_tool('zzz', [], {'win32': [str(a / 'py*')]})
    assert hit and hit.lower() == str(a / 'py.exe').lower()
    # well_known 未命中 → None
    assert S._find_tool('zzz', [], {'win32': [str(a / 'nope*')]}) is None
    # well_known 首个命中优先
    hit2 = S._find_tool('zzz', [], {'win32': [str(a / 'nope*'),
                                              str(a / 'py*')]})
    assert hit2 and hit2.lower() == str(a / 'py.exe').lower()
    # _find_tool 是 _find_tool_with_meta 的薄壳（platform_tools 依赖的三参契约）：
    # well_known={} 且 PATH 里没有裸 'py' 可执行（py.exe 名字不同）→ None
    assert S._find_tool('py', [], {}) is None
    hit4 = S._find_tool('py', [], {'win32': [str(a / 'py*')]})
    assert hit4 and hit4.lower() == str(a / 'py.exe').lower()


def test_find_tool_lookup_crash_reported(tmp_path, monkeypatch):
    monkeypatch.setenv('PATH', str(tmp_path))

    def boom(cmd, path_index):
        raise RuntimeError('boom-lookup')

    monkeypatch.setattr('vools.actus.probe.system_tools._path_candidates', boom)
    info = S._lookup_one(('gcc', [], ['--version'], {}, 5), None, True)
    # 单工具异常关在自己的 future 里（state=error），不炸整批
    assert info['state'] == 'error'
    assert 'boom-lookup' in info['error'] and info['name'] == 'gcc'


# ---------------------------------------------------------------- 版本探测

PY = sys.executable


def test_get_version_detail_success_and_later_line():
    v, e, x = S._get_version_detail(PY, ['--version'])
    assert e is None and 'Python' in v and x == {}
    # stdout 首行是横幅、版本在后面行 → 取那一行
    v2, e2, x2 = S._get_version_detail(
        PY, ['-c', 'print("banner"); print("mytool 2.3.4")'])
    assert e2 is None and v2 == 'mytool 2.3.4'


def test_get_version_detail_stderr_version_and_truncation():
    # stderr 带版本号 → 用 stderr 那行
    v, e, x = S._get_version_detail(
        PY, ['-c', 'import sys; sys.stderr.write("javac 11.0.2\\n")'])
    assert e is None and v.startswith('javac 11.0.2')
    # 长版本串截断到 200
    v2, e2, _ = S._get_version_detail(
        PY, ['-c', 'print("9." * 200 + "1")'])
    assert len(v2) == 200


def test_get_version_detail_no_version_pattern_not_usage_text():
    # 有输出但无版本号形态：version 必须为空串（不把 usage 塞进去），留痕 kind
    v, e, x = S._get_version_detail(PY, ['-c', 'print("hello no version")'])
    assert v == ''
    assert e == 'no version pattern in stdout/stderr (usage text not used as version)'
    assert x['version_error_kind'] == 'no_version_pattern'
    assert x['version_stdout_sample'] == 'hello no version'
    assert x['version_stderr_sample'] == ''


def test_get_version_detail_nonzero_exit_kinds():
    # 非零退出 + 有版本号：版本仍返回，但 extra 留 returncode
    v, e, x = S._get_version_detail(
        PY, ['-c', 'import sys; sys.stderr.write("javac 11.0.2\\n"); sys.exit(1)'])
    assert e is None and v.startswith('javac 11.0.2')
    assert x['version_returncode'] == 1
    # 非零退出 + 无版本号 → nonzero_exit（比 no_version_pattern 更准）
    v2, e2, x2 = S._get_version_detail(
        PY, ['-c', 'import sys; print("usage"); sys.exit(2)'])
    assert v2 == '' and x2['version_error_kind'] == 'nonzero_exit'
    assert 'exit=2' in e2


def test_get_version_detail_empty_output():
    v, e, x = S._get_version_detail(PY, ['-c', 'pass'])
    assert v == '' and x['version_error_kind'] == 'empty_output'
    assert 'exit=0' in e


def test_get_version_detail_crash_marker():
    v, e, x = S._get_version_detail(
        PY, ['-c', 'import sys; sys.stdout.write("see hs_err_pid1.log"); sys.exit(1)'])
    assert x['version_error_kind'] == 'crashed'
    assert x['version_crash_marker'] == 'hs_err_pid'
    assert x['version_returncode'] == 1
    assert 'crashed' in e
    # 即使崩溃输出里带版本号形态也照样返回 hit（截 200），error 同时留痕
    v2, _, x2 = S._get_version_detail(
        PY, ['-c', 'import sys; sys.stdout.write("A fatal error has been detected ver 1.2.3")'])
    assert x2['version_error_kind'] == 'crashed'
    assert '1.2.3' in v2


def test_get_version_detail_spawn_error():
    v, e, x = S._get_version_detail(r'C:\definitely\not\here.exe', ['--version'])
    assert v == '' and x['version_error_kind'] == 'spawn_error'
    assert 'failed to run' in e


def test_get_version_detail_timeout_kills_tree():
    t0 = time.monotonic()
    v, e, x = S._get_version_detail(
        PY, ['-c', 'import time; time.sleep(6); print("x 1.0")'], timeout=1)
    elapsed = time.monotonic() - t0
    # 超时即时生效（tree-kill），不能拖满 sleep
    assert elapsed < 5
    assert v == '' and x['version_error_kind'] == 'timeout'
    assert x['version_timeout_s'] == 1
    assert 'timeout after 1s' in e
    assert 'version_kill_ms' in x


def test_get_version_detail_decode_degradation():
    # GBK 编码输出版本号 → locale 解码降级并留痕
    v, e, x = S._get_version_detail(
        PY, ['-c', 'import sys; sys.stdout.buffer.write("版本 1.2.3".encode("gbk"))'])
    assert e is None and v.endswith('1.2.3')
    assert x.get('version_decode') == 'locale'
    # 两边都解不动的字节 → replace 档位
    assert S._decode_output(b'\xff\xfe\xff 1.2')[1] == 'replace'
    # None / str 直通
    assert S._decode_output(None) == ('', 'utf-8')
    assert S._decode_output('plain')[0] == 'plain'


def test_get_version_wrapper_contract():
    """platform_tools.py 依赖的冻结契约：失败返回 ""，成功返回 str。"""
    assert S._get_version(PY, ['--version']).startswith('Python')
    assert S._get_version(r'C:\definitely\not\here.exe', ['--version']) == ''
    assert isinstance(S._get_version(PY, ['-c', 'print("no pattern")']), str)


# ---------------------------------------------------------------- 小工具函数

def test_first_line_with_version_and_crash_marker():
    assert S._first_line_with_version(
        ['banner', '  tool 1.2.3  ', 'other']) == 'tool 1.2.3'
    assert S._first_line_with_version(['no version', '']) is None
    assert S._first_line_with_version([]) is None
    assert S._crash_marker('hello hs_err_pid123.log') == 'hs_err_pid'
    assert S._crash_marker(None, 'Could not reserve enough space') == \
        'Could not reserve enough space'
    assert S._crash_marker('clean output') is None
    assert S._crash_marker(None, '') is None


def test_is_script_wrapper_and_entry_label():
    assert S._is_script_wrapper(r'C:\x.CMD')
    assert S._is_script_wrapper('/x.bat')
    assert not S._is_script_wrapper('/x.sh')
    assert not S._is_script_wrapper(None)
    # 表项坏掉也不能让整批炸
    assert S._entry_label(('gcc', [], [], {}, 5)) == 'gcc'
    assert S._entry_label(None) == '<invalid TOOL_TABLE entry>'
    assert S._entry_label(()) == '<invalid TOOL_TABLE entry>'


def test_lookup_one_invalid_and_ok_entries(tmp_path, monkeypatch):
    # 非五元组条目 → invalid 状态（一个坏条目不炸整批）
    info = S._lookup_one(('only-name',))
    assert info['state'] == 'invalid' and 'ValueError' in info['error']
    info2 = S._lookup_one(None)
    assert info2['state'] == 'invalid' and 'TypeError' in info2['error']
    # 正常条目
    a = tmp_path / 'bin'; a.mkdir(); (a / 'foo.exe').write_bytes(b'x')
    monkeypatch.setenv('PATH', str(a))
    ok = S._lookup_one(('foo', [], ['--version'], {}, 5),
                       S._build_path_index(), True)
    assert ok['state'] == 'ok'
    assert ok['path'].lower() == str(a / 'foo.exe').lower()
    assert ok['version_cmd'] == ['--version'] and ok['timeout'] == 5
    assert ok['preferred_non_wrapper'] is False


# ---------------------------------------------------------------- 并发原语

def test_resolve_workers_adaptive():
    # 主线程 16 / 显式 override 优先
    assert S._resolve_workers(None) == S._DEFAULT_MAX_WORKERS
    assert S._resolve_workers(3) == 3

    result = {}

    def worker():
        result['w'] = S._resolve_workers(None)

    t = threading.Thread(target=worker); t.start(); t.join()
    # 非主线程降档到 8
    assert result['w'] == S._NESTED_MAX_WORKERS


def test_inner_slot_gate_on_and_off():
    # 闸门关闭（默认）：空操作
    S.set_inner_concurrency_limit(0)
    acquired = []
    def worker():
        with S._inner_slot():
            acquired.append(1)
    ts = [threading.Thread(target=worker) for _ in range(4)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert len(acquired) == 4
    # 闸门开启：BoundedSemaphore 限流仍不丢失任务
    S.set_inner_concurrency_limit(2)
    try:
        acquired = []
        ts = [threading.Thread(target=worker) for _ in range(4)]
        for t in ts: t.start()
        for t in ts: t.join()
        assert len(acquired) == 4
    finally:
        S.set_inner_concurrency_limit(0)


def test_wait_for_results_failures_and_cancel():
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    try:
        ok = ex.submit(lambda: 'v')
        res, fails, expired = S._wait_for({ok: 'k'}, deadline=None)
        assert res == {'k': 'v'} and fails == {} and expired == []
        boom = ex.submit(lambda: 1 / 0)
        res2, fails2, _ = S._wait_for({boom: 'b'}, deadline=None)
        assert 'b' in fails2 and isinstance(fails2['b'], ZeroDivisionError)
        # deadline 已过 → 未完成 future 被 cancel 并回报 expired
        slow = ex.submit(time.sleep, 2)
        res3, fails3, expired3 = S._wait_for({slow: 's'}, deadline=0.0)
        assert res3 == {} and expired3 == ['s'] and slow.cancelled()
    finally:
        ex.shutdown(wait=False)


def test_wait_for_empty_map():
    assert S._wait_for({}, deadline=1.0) == ({}, {}, [])


# ---------------------------------------------------------------- prober 端到端

def _fake_lookup():
    """替身 _lookup_one：全表「找到」且带 wrapper 偏好。"""
    def fake(entry, path_index=None, prefer_non_wrapper=False):
        return {'name': entry[0], 'state': 'ok', 'path': r'C:\fake\tool.exe',
                'version_cmd': ['--version'], 'timeout': 5,
                'preferred_non_wrapper': False, 'skipped_wrappers': []}
    return fake


def test_prober_version_expired_marks_budget_note(monkeypatch):
    # 阶段 2 全部超预算：显式 "version not probed"（不静默）
    import time as _time

    def slow_version_one(path, version_args, timeout):
        _time.sleep(1.0)
        return {'version': '1.0', 'error': None, 'extra': {}, 'elapsed_ms': 1.0}

    monkeypatch.setattr('vools.actus.probe.system_tools._lookup_one', _fake_lookup())
    monkeypatch.setattr('vools.actus.probe.system_tools._version_one',
                        slow_version_one)
    monkeypatch.setenv('PATH', '')
    p = S.SystemToolsProber(timeout=1, total_budget=0.3)
    items = p.probe()
    st = p.last_stats
    assert st['lookup_ok'] == len(TOOL_TABLE) and st['version_expired'] == len(TOOL_TABLE)
    assert all(i.available and i.path == r'C:\fake\tool.exe' for i in items)
    assert all('version not probed' in (i.error or '') for i in items)
    # 保序契约：结果按 TOOL_TABLE 原下标
    assert [i.name for i in items] == [e[0] for e in TOOL_TABLE]


def test_prober_version_ok_failed_slow_and_gating(monkeypatch):
    calls = []

    def fake_version_one(path, version_args, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            return {'version': '1.2.3', 'error': None,
                    'extra': {'version_returncode': 0}, 'elapsed_ms': 900.0}
        if len(calls) == 2:
            return {'version': '', 'error': 'no version', 'extra': {},
                    'elapsed_ms': 5.0}
        raise RuntimeError('boom-version')

    monkeypatch.setattr('vools.actus.probe.system_tools._lookup_one', _fake_lookup())
    # 计数器用原子方式：阶段 2 并发，len(calls) 判定会撞车
    counter = {'n': 0}
    lock = threading.Lock()

    def fake_version_one(path, version_args, timeout):
        with lock:
            counter['n'] += 1
            n = counter['n']
        calls.append(timeout)
        if n == 1:
            return {'version': '1.2.3', 'error': None,
                    'extra': {'version_returncode': 0}, 'elapsed_ms': 900.0}
        if n == 2:
            return {'version': '', 'error': 'no version', 'extra': {},
                    'elapsed_ms': 5.0}
        raise RuntimeError('boom-version')

    monkeypatch.setattr('vools.actus.probe.system_tools._version_one',
                        fake_version_one)
    monkeypatch.setenv('PATH', '')
    p = S.SystemToolsProber(timeout=1, total_budget=10.0, wrapper_timeout_cap=0)
    items = p.probe()
    st = p.last_stats
    # 恰好一个成功、一个 no-version、其余 boom（并发下 1/2 号角色不定）
    assert st['version_ok'] == 1
    winner = [i for i in items if i.version == '1.2.3']
    novers = [i for i in items if i.available and i.error == 'no version']
    booms = [i for i in items if 'boom-version' in (i.error or '')]
    assert len(winner) == 1 and len(novers) == 1
    assert len(booms) == len(TOOL_TABLE) - 2
    # 慢工具（>=800ms）在 extra 与 stats 双留痕；gating = 最慢者
    assert winner[0].extra['version_probe_ms'] == 900
    assert st['slow_tools'] and st['gating_tool'] == winner[0].name
    assert st['version_max_ms'] == 900
    # 版本取不到：available 仍 True（path 有效），error 留痕
    assert novers[0].available and novers[0].version == ''
    # version one 收到的 timeout 用表内值
    assert set(calls) == {5}


def test_prober_wrapper_timeout_cap_applies(monkeypatch):
    """wrapper_timeout_cap 只作用于 .CMD/.BAT 路径（pnpm 类 shim 长尾收口）。"""
    seen = []

    def fake_version_one(path, version_args, timeout):
        seen.append((path, timeout))
        return {'version': '1.0', 'error': None, 'extra': {}, 'elapsed_ms': 3.0}

    def fake_wrapper_lookup(entry, path_index=None, prefer_non_wrapper=False):
        return {'name': entry[0], 'state': 'ok', 'path': r'C:\fake\tool.CMD',
                'version_cmd': ['--version'], 'timeout': 5,
                'preferred_non_wrapper': False, 'skipped_wrappers': []}

    monkeypatch.setattr('vools.actus.probe.system_tools._lookup_one',
                        fake_wrapper_lookup)
    monkeypatch.setattr('vools.actus.probe.system_tools._version_one',
                        fake_version_one)
    monkeypatch.setenv('PATH', '')
    p = S.SystemToolsProber(timeout=5, total_budget=10.0, wrapper_timeout_cap=2.0)
    items = p.probe()
    # min(5, 2.0) = 2.0
    assert {t for _, t in seen} == {2.0}
    assert items[0].version == '1.0'
    # cap<=0 → 关闭，按表内 timeout
    p2 = S.SystemToolsProber(timeout=5, total_budget=10.0, wrapper_timeout_cap=0)
    assert p2.wrapper_timeout_cap is None


def test_prober_not_found_and_invalid_entries(monkeypatch):
    # PATH 空 → 全部 not found（与串行版逐字一致）
    monkeypatch.setenv('PATH', '')
    p = S.SystemToolsProber(timeout=1, max_workers=8, total_budget=3.0)
    items = p.probe()
    st = p.last_stats
    assert st['lookup_missing'] == len(TOOL_TABLE) and st['lookup_ok'] == 0
    assert all(not i.available and i.error == 'not found' for i in items)
    # 保序
    assert [i.name for i in items] == [e[0] for e in TOOL_TABLE]
    # invalid 条目：available=False 且 error 带 invalid
    broken = ('only-two',)
    monkeypatch.setattr('vools.actus.probe.system_tools.TOOL_TABLE',
                        [broken, TOOL_TABLE[0]])
    p2 = S.SystemToolsProber(timeout=1, total_budget=3.0)
    items2 = p2.probe()
    assert items2[0].available is False and 'invalid TOOL_TABLE entry' in items2[0].error
    assert st is not p2.last_stats


def test_prober_lookup_crash_marks_item(monkeypatch):
    # _lookup_one future 抛异常（双保险分支）：item 落 error，不炸整批
    def crashing(entry, path_index=None, prefer_non_wrapper=False):
        raise RuntimeError('future-boom')

    monkeypatch.setattr('vools.actus.probe.system_tools._lookup_one', crashing)
    monkeypatch.setenv('PATH', '')
    p = S.SystemToolsProber(timeout=1, total_budget=3.0)
    items = p.probe()
    st = p.last_stats
    assert st['lookup_failed'] == len(TOOL_TABLE)
    assert all('future-boom' in (i.error or '') for i in items)


def test_prober_budget_zero_disables_deadline(monkeypatch):
    # budget<=0 → 无 deadline（deadline=None 分支），靠单工具超时兜底
    monkeypatch.setattr('vools.actus.probe.system_tools._lookup_one', _fake_lookup())
    monkeypatch.setattr(
        'vools.actus.probe.system_tools._version_one',
        lambda path, args, timeout: {'version': '1.0', 'error': None,
                                     'extra': {}, 'elapsed_ms': 1.0})
    monkeypatch.setenv('PATH', '')
    p = S.SystemToolsProber(timeout=1, total_budget=0)
    items = p.probe()
    assert p.last_stats['version_ok'] == len(TOOL_TABLE)
    assert all(i.version == '1.0' for i in items)
    assert p.last_stats['budget_s'] == 0


def test_version_one_wrapper_crash(monkeypatch):
    # _get_version_detail 自己抛异常（不可能但兜底）→ wrapper crashed 留痕
    def boom(path, args, timeout):
        raise ValueError('detail-boom')

    monkeypatch.setattr('vools.actus.probe.system_tools._get_version_detail', boom)
    out = S._version_one('p', ['--version'], 5)
    assert out['version'] == '' and 'detail-boom' in out['error']
    assert out['extra'] == {} and out['elapsed_ms'] >= 0


def test_prober_total_zero_entries(monkeypatch):
    # TOOL_TABLE 空 → 直接返回 []（total==0 分支）
    monkeypatch.setattr('vools.actus.probe.system_tools.TOOL_TABLE', [])
    p = S.SystemToolsProber(timeout=1, total_budget=1.0)
    assert p.probe() == []
    assert p.last_stats['entries'] == 0


def test_prober_lookup_expired_marks_not_probed(monkeypatch):
    """lookup_expired 分支：阶段 1 有条目没跑完 → "not probed"（不静默）。

    确定性构造：max_workers=1、budget≈0、fake lookup 各睡 1s →
    阶段 1 的 wait 立刻超时，65 个 future 全部未完成（cancel 掉）。
    不依赖「部分完成/部分过期」的时间窗口（合跑真 probe() 后系统负载抖动
    曾让窗口判断翻转）。
    """
    import time as _time

    def slow_lookup(entry, path_index=None, prefer_non_wrapper=False):
        _time.sleep(1.0)
        return {'name': entry[0], 'state': 'ok', 'path': r'C:\fake\t.exe',
                'version_cmd': [], 'timeout': 1,
                'preferred_non_wrapper': False, 'skipped_wrappers': []}

    monkeypatch.setattr('vools.actus.probe.system_tools._lookup_one', slow_lookup)
    monkeypatch.setattr('vools.actus.probe.system_tools._version_one',
                        lambda *a: {'version': '1', 'error': None,
                                    'extra': {}, 'elapsed_ms': 1.0})
    monkeypatch.setenv('PATH', '')
    p = S.SystemToolsProber(timeout=1, max_workers=1, total_budget=0.001)
    items = p.probe()
    st = p.last_stats
    assert st['lookup_expired'] == len(TOOL_TABLE)
    assert all((i.error or '').startswith('not probed: ') for i in items)
    assert all(not i.available for i in items)
    assert 'budget exhausted' in items[0].error
    # 每条必有归宿：expired 计入 resolved 总数
    st_resolved = (st['lookup_ok'] + st['lookup_missing']
                   + st['lookup_failed'] + st['lookup_expired'])
    assert st_resolved == len(TOOL_TABLE)
def test_prober_defensive_none_slots_filled(monkeypatch):
    # 防御分支：任何漏网槽位落成显式条目，绝不返回 None
    def half_lookup(entry, path_index=None, prefer_non_wrapper=False):
        return {'name': entry[0], 'state': 'ok', 'path': r'C:\fake\t.exe',
                'version_cmd': [], 'timeout': 1,
                'preferred_non_wrapper': False, 'skipped_wrappers': []}

    monkeypatch.setattr('vools.actus.probe.system_tools._lookup_one', half_lookup)
    monkeypatch.setattr('vools.actus.probe.system_tools._version_one',
                        lambda *a: {'version': '1', 'error': None,
                                    'extra': {}, 'elapsed_ms': 1.0})
    monkeypatch.setenv('PATH', '')
    p = S.SystemToolsProber(timeout=1, total_budget=10.0)
    items = p.probe()
    assert all(i is not None for i in items)
    assert len(items) == len(TOOL_TABLE)


def test_prober_real_end_to_end_smoke():
    """真实端到端冒烟（真 PATH）：不依赖任何具体工具在不在，只验证结构契约。"""
    p = S.SystemToolsProber(timeout=2, total_budget=10.0)
    items = p.run()
    assert len(items) == len(TOOL_TABLE)
    assert [i.name for i in items] == [e[0] for e in TOOL_TABLE]
    # bootstrap 重装模块身份时 ProbeItem 类对象可能被换——按现取身份比对，
    # 不用文件顶层 import 的旧类（isinstance 跨身份会 False）
    import importlib as _il
    _base = _il.import_module('vools.actus.probe.base')
    assert all(type(i) is _base.ProbeItem for i in items)
    assert all(i.category == 'system_tools' for i in items)
    st = p.last_stats
    assert st['entries'] == len(TOOL_TABLE)
    assert st['workers'] >= 1
    assert st['elapsed_ms'] > 0


# ---------------------------------------------------------------- 探测临时目录

def test_probe_tmpdir_lazy_create_and_cleanup():
    # 懒创建 + 进程级复用
    d1 = S._probe_tmpdir()
    assert d1 and os.path.isdir(d1)
    assert S._probe_tmpdir() == d1
    # cleanup 后下次重建
    S.cleanup_probe_tmpdir()
    d2 = S._probe_tmpdir()
    assert d2 and d2 != d1
    assert not os.path.isdir(d1)
    S.cleanup_probe_tmpdir()


def test_probe_tmpdir_oserror_fallback(monkeypatch):
    # mkdtemp 失败 → 返回 None（退回继承 cwd，不阻塞探测）
    def boom(prefix):
        raise OSError('disk full')

    monkeypatch.setattr('vools.actus.probe.system_tools.tempfile.mkdtemp', boom)
    monkeypatch.setattr('vools.actus.probe.system_tools._PROBE_TMPDIR', None)
    assert S._probe_tmpdir() is None
    S.cleanup_probe_tmpdir()


def test_get_version_detail_unexpected_exception_branch(monkeypatch):
    # Popen 抛出非 SubprocessError/OSError 的未知异常 → "unexpected" 留痕
    class Weird(Exception):
        pass

    def boom(*args, **kwargs):
        raise Weird('mystery')

    monkeypatch.setattr('vools.actus.probe.system_tools.subprocess.Popen', boom)
    v, e, x = S._get_version_detail(PY, ['--version'])
    assert v == '' and x['version_error_kind'] == 'unexpected'
    assert 'version probe failed' in e and 'Weird' in e


def test_get_version_detail_timeout_grace_fallback(monkeypatch):
    """超时后宽限内管道仍未关闭 → 直接关管道返回（不陪孙进程等）。"""
    import subprocess as sp

    class StubProc:
        def __init__(self):
            self.stdout = object()
            self.stderr = object()
            self.returncode = None
            self.killed = False

        def communicate(self, timeout=None):
            if timeout == 1:
                raise sp.TimeoutExpired(cmd='x', timeout=1)
            raise RuntimeError('grandchild holds pipe')   # 宽限也失败

        def kill(self):
            self.killed = True

    stub = StubProc()

    def fake_popen(*args, **kwargs):
        return stub

    def fake_kill_tree(proc):
        pass                      # 树杀"成功"但管道仍被孙进程握着

    monkeypatch.setattr('vools.actus.probe.system_tools.subprocess.Popen', fake_popen)
    monkeypatch.setattr('vools.actus.probe.system_tools._kill_tree', fake_kill_tree)
    v, e, x = S._get_version_detail('tool', ['--version'], timeout=1)
    assert v == '' and x['version_error_kind'] == 'timeout'
    assert stub.killed and stub.returncode is None
    # 宽限失败路径收口后不能拖过宽限太多
    assert 'timeout after 1s' in e


# ---------------------------------------------------------------- 公开面

def test_all_and_module_surface():
    assert S.__all__ == ['SystemToolsProber']
    p = S.SystemToolsProber()
    assert p.max_workers == S._DEFAULT_MAX_WORKERS      # 主线程默认 16
    assert p.total_budget == S._DEFAULT_TOTAL_BUDGET    # 默认预算 15s
    assert p.wrapper_timeout_cap == S._DEFAULT_WRAPPER_TIMEOUT_CAP
    assert p.last_stats == {}
    assert p.timeout == 5
