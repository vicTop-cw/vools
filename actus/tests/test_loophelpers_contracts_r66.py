# -*- coding: utf-8 -*-
"""loophelpers.py 契约测试 (Round 60)。

覆盖：_ignored（目录前缀/文件 glob/os.sep 归一）、fingerprint（确定性/
变更敏感性/ignore 生效/.git 元数据采样/stat 异常跳过）、clipboard_write
（pyperclip 路径/缺失退化/非 win32 False）、clipboard_clear 非 win32 no-op、
focus_window 非 win32 True/真实枚举找不到 False、run_playback（解包/坏
JSON/空输出/inner 非 dict/error 注入/env 对齐）、send_to_pipe（成功/失败/
FileNotFoundError/其他异常/input 透传）、RUN_PLAYBACK 别名。
"""

import json
import os
import sys
import types

import pytest

from vools.actus import loophelpers as lmod


# ---------------------------------------------------------------- _ignored

class TestIgnored:
    def test_dir_pattern_prefix(self):
        assert lmod._ignored('.git/config', ['.git/']) is True
        assert lmod._ignored('node_modules/x/y.js', ['node_modules/']) is True

    def test_dir_pattern_no_match(self):
        assert lmod._ignored('src/gitlike', ['.git/']) is False

    def test_file_glob(self):
        assert lmod._ignored('src/mod.pyc', ['*.pyc']) is True
        assert lmod._ignored('src/mod.py', ['*.pyc']) is False

    def test_windows_sep_normalized(self):
        assert lmod._ignored('a\\b.pyc', ['*.pyc']) is True

    def test_empty_patterns(self):
        assert lmod._ignored('anything', []) is False


# ---------------------------------------------------------------- fingerprint

class TestFingerprint:
    def _touch(self, root, rel, content=b'x'):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    def test_deterministic(self, tmp_path):
        self._touch(tmp_path, 'a.txt', b'hello')
        self._touch(tmp_path, 'sub/b.txt', b'world')
        assert lmod.fingerprint(str(tmp_path)) == lmod.fingerprint(str(tmp_path))

    def test_changes_on_file_add(self, tmp_path):
        h1 = lmod.fingerprint(str(tmp_path))
        self._touch(tmp_path, 'new.txt')
        assert lmod.fingerprint(str(tmp_path)) != h1

    def test_changes_on_size_change(self, tmp_path):
        self._touch(tmp_path, 'a.txt', b'aaa')
        h1 = lmod.fingerprint(str(tmp_path))
        self._touch(tmp_path, 'a.txt', b'aaaa')
        assert lmod.fingerprint(str(tmp_path)) != h1

    def test_default_ignore_excludes_git_and_pyc(self, tmp_path):
        self._touch(tmp_path, '.git/HEAD', b'ref: x')
        self._touch(tmp_path, '.git/config', b'[core]')
        self._touch(tmp_path, 'mod.pyc', b'junk')
        self._touch(tmp_path, 'keep.txt', b'k')
        h1 = lmod.fingerprint(str(tmp_path))
        # .git/config 与 *.pyc 既不走 walk 采样也不进 git_meta（只采 HEAD/refs）
        self._touch(tmp_path, '.git/config', b'[core2]')
        self._touch(tmp_path, 'mod.pyc', b'junk2')
        assert lmod.fingerprint(str(tmp_path)) == h1

    def test_ignore_extra(self, tmp_path):
        self._touch(tmp_path, 'logs/x.log', b'l')
        self._touch(tmp_path, 'keep.txt', b'k')
        h1 = lmod.fingerprint(str(tmp_path), ignore_extra=['logs/'])
        self._touch(tmp_path, 'logs/x.log', b'll')
        assert lmod.fingerprint(str(tmp_path), ignore_extra=['logs/']) == h1

    def test_git_meta_sampled(self, tmp_path):
        # .git 在 DEFAULT_IGNORE 里，但 HEAD/refs mtime 另行采样
        gitdir = tmp_path / '.git'
        (gitdir / 'refs').mkdir(parents=True)
        head = gitdir / 'HEAD'
        head.write_bytes(b'ref: refs/main')
        h1 = lmod.fingerprint(str(tmp_path))
        os.utime(head, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
        os.utime(gitdir / 'refs', ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
        assert lmod.fingerprint(str(tmp_path)) != h1

    def test_stat_error_file_skipped(self, tmp_path, monkeypatch):
        self._touch(tmp_path, 'gone.txt', b'x')
        real_stat = os.stat

        def flaky(path, *a, **k):
            if str(path).endswith('gone.txt'):
                raise OSError('vanished')
            return real_stat(path, *a, **k)

        monkeypatch.setattr(lmod.os, 'stat', flaky)
        h = lmod.fingerprint(str(tmp_path))  # 不抛
        assert len(h) == 32

    def test_empty_dir_is_32hex(self, tmp_path):
        h = lmod.fingerprint(str(tmp_path))
        assert len(h) == 32
        int(h, 16)

    def test_nested_relpath_forward_slash(self, tmp_path):
        # relpath 分隔符归一为 / 后参与哈希（Windows 不炸）
        self._touch(tmp_path, 'a/b/c.txt')
        assert len(lmod.fingerprint(str(tmp_path))) == 32


# ---------------------------------------------------------------- clipboard

class _Buf:
    def __init__(self, value=''):
        self.value = value


def _fake_ctypes(monkeypatch, user32, kernel32=None):
    """替换模块内 import ctypes 得到的对象（不影响真实剪贴板）。"""
    from ctypes import wintypes as real_wintypes
    fake = types.ModuleType('ctypes')
    fake.wintypes = real_wintypes
    fake.windll = types.SimpleNamespace(
        user32=user32, kernel32=kernel32 or types.SimpleNamespace())
    fake.create_unicode_buffer = _Buf
    fake.memmove = lambda *a, **k: None
    fake.sizeof = lambda x: 16
    fake.WINFUNCTYPE = lambda *t: (lambda fn: fn)
    monkeypatch.setitem(sys.modules, 'ctypes', fake)
    return fake


class TestClipboardWrite:
    def test_pyperclip_path(self, monkeypatch):
        calls = []
        fake = types.ModuleType('pyperclip')
        fake.copy = lambda t: calls.append(t)
        monkeypatch.setitem(sys.modules, 'pyperclip', fake)
        assert lmod.clipboard_write('hello') is True
        assert calls == ['hello']

    def test_pyperclip_missing_nonwin32_false(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'pyperclip', None)  # import -> ImportError
        monkeypatch.setattr(sys, 'platform', 'linux')
        assert lmod.clipboard_write('x') is False

    def test_win32_ctypes_fallback_success(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'pyperclip', None)
        calls = {'open': [], 'empty': 0, 'close': 0}

        class U:
            def OpenClipboard(self, h):
                calls['open'].append(h)
                return 1

            def EmptyClipboard(self):
                calls['empty'] += 1

            def SetClipboardData(self, fmt, handle):
                assert fmt == 13
                assert handle == 777
                return 42

            def CloseClipboard(self):
                calls['close'] += 1

        class K:
            def GlobalAlloc(self, flags, size):
                assert flags == 0x0002 and size == 16
                return 777

            def GlobalLock(self, h):
                return 888

            def GlobalUnlock(self, h):
                pass

        _fake_ctypes(monkeypatch, U(), K())
        assert lmod.clipboard_write('payload') is True
        assert calls['empty'] == 1 and calls['close'] == 1

    def test_win32_open_clipboard_fails(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'pyperclip', None)

        class U:
            def OpenClipboard(self, h):
                return 0

        _fake_ctypes(monkeypatch, U())
        assert lmod.clipboard_write('x') is False


class TestClipboardClear:
    def test_nonwin32_noop(self, monkeypatch):
        monkeypatch.setattr(sys, 'platform', 'linux')
        assert lmod.clipboard_clear() is None

    def test_win32_clears(self, monkeypatch):
        calls = {'empty': 0, 'close': 0}

        class U:
            def OpenClipboard(self, h):
                return 1

            def EmptyClipboard(self):
                calls['empty'] += 1

            def CloseClipboard(self):
                calls['close'] += 1

        _fake_ctypes(monkeypatch, U())
        lmod.clipboard_clear()
        assert calls == {'empty': 1, 'close': 1}

    def test_win32_open_fail_noop(self, monkeypatch):
        class U:
            def OpenClipboard(self, h):
                return 0

        _fake_ctypes(monkeypatch, U())
        lmod.clipboard_clear()  # 不抛不炸


# ---------------------------------------------------------------- focus_window

class TestFocusWindow:
    def test_nonwin32_true(self, monkeypatch):
        monkeypatch.setattr(sys, 'platform', 'linux')
        assert lmod.focus_window('anything') is True

    def test_no_match_false(self):
        # 真实枚举：该标题不可能存在
        assert lmod.focus_window('ZZZ_NO_SUCH_WINDOW_9857') is False

    def _fake_enum(self, monkeypatch, titles):
        """伪造 user32：EnumWindows 逐个回放标题。"""

        class U:
            def __init__(self):
                self.shown = []
                self.fg = []

            def GetWindowTextLengthW(self, hwnd):
                return len(titles.get(hwnd, ''))

            def GetWindowTextW(self, hwnd, buf, n):
                buf.value = titles.get(hwnd, '')

            def EnumWindows(self, cb, lparam):
                for hwnd in titles:
                    cb(hwnd, 0)

            def ShowWindow(self, hwnd, cmd):
                self.shown.append((hwnd, cmd))

            def SetForegroundWindow(self, hwnd):
                self.fg.append(hwnd)

        u = U()
        _fake_ctypes(monkeypatch, u)
        return u

    def test_match_pywin32_branch(self, monkeypatch):
        u = self._fake_enum(monkeypatch, {111: 'My Console', 222: 'other'})
        fake_win32 = types.ModuleType('win32gui')
        calls = []
        fake_win32.ShowWindow = lambda h, c: calls.append(('show', h, c))
        fake_win32.SetForegroundWindow = lambda h: calls.append(('fg', h))
        monkeypatch.setitem(sys.modules, 'win32gui', fake_win32)
        assert lmod.focus_window(r'Console') is True
        assert calls == [('show', 111, 9), ('fg', 111)]

    def test_match_ctypes_fallback_branch(self, monkeypatch):
        # win32gui 不可用 → 裸 ctypes 路径
        u = self._fake_enum(monkeypatch, {333: 'Agent Window'})
        monkeypatch.setitem(sys.modules, 'win32gui', None)  # import -> ImportError
        assert lmod.focus_window(r'^Agent') is True
        assert u.shown == [(333, 9)]
        assert u.fg == [333]

    def test_title_search_regex_applied(self, monkeypatch):
        # 标题存在但不匹配正则 → 找不到
        self._fake_enum(monkeypatch, {444: 'totally different'})
        assert lmod.focus_window(r'^Agent') is False


# ---------------------------------------------------------------- run_playback

class _Proc:
    def __init__(self, stdout='', stderr='', rc=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = rc


class TestRunPlayback:
    def _patch(self, monkeypatch, proc):
        calls = []
        monkeypatch.setattr(lmod, 'run_cmd_safe',
                            lambda *a, **k: (calls.append((a, k)), proc)[1])
        return calls

    def test_unwraps_engine_envelope(self, monkeypatch):
        outer = {'status': 'ok', 'data': {'status': 'ok', 'mode': 'pipe',
                                          'message': 'done'}, 'error': None}
        calls = self._patch(monkeypatch,
                            _Proc(stdout=json.dumps(outer, ensure_ascii=False)))
        payload = lmod.run_playback('repo', {'macro': 'm'}, 'META')
        assert payload == {'status': 'ok', 'mode': 'pipe', 'message': 'done'}
        args, kwargs = calls[0]
        cmd = args[0]
        assert cmd[1:4] == ['-m', 'actus', 'run']
        assert cmd[4] == 'actus.system.macro_playback'
        assert json.loads(cmd[5]) == {'macro': 'm'}
        assert '--confirm' in cmd
        assert kwargs['cwd'] == os.path.join('repo', 'engine')
        assert kwargs['env']['ACTUS_META_DIR'] == 'META'
        assert kwargs['env']['PYTHONIOENCODING'] == 'utf-8'
        assert kwargs['timeout'] == 120

    def test_custom_timeout(self, monkeypatch):
        calls = self._patch(monkeypatch, _Proc(stdout=json.dumps({'status': 'ok', 'data': {}})))
        lmod.run_playback('repo', {}, 'META', timeout=7)
        assert calls[0][1]['timeout'] == 7

    def test_bad_json_failed_tail(self, monkeypatch):
        self._patch(monkeypatch, _Proc(stdout='not json at all'))
        p = lmod.run_playback('repo', {}, 'META')
        assert p == {'status': 'failed', 'mode': None,
                     'message': 'not json at all'}

    def test_empty_output_uses_stderr(self, monkeypatch):
        self._patch(monkeypatch, _Proc(stdout='', stderr='boom happened'))
        p = lmod.run_playback('repo', {}, 'META')
        assert p['message'] == 'boom happened'

    def test_all_empty_message(self, monkeypatch):
        self._patch(monkeypatch, _Proc(stdout='', stderr=''))
        p = lmod.run_playback('repo', {}, 'META')
        assert p['message'] == '回放无输出'

    def test_inner_not_dict_falls_to_status(self, monkeypatch):
        outer = {'status': 'failed', 'data': 'oops', 'error': None}
        self._patch(monkeypatch, _Proc(stdout=json.dumps(outer)))
        p = lmod.run_playback('repo', {}, 'META')
        assert p == {'status': 'failed'}

    def test_error_message_injected(self, monkeypatch):
        outer = {'status': 'failed', 'data': {'status': 'failed'},
                 'error': {'message': '宏执行超时'}}
        self._patch(monkeypatch, _Proc(stdout=json.dumps(outer)))
        p = lmod.run_playback('repo', {}, 'META')
        assert p['message'] == '宏执行超时'

    def test_error_without_message_key(self, monkeypatch):
        outer = {'status': 'failed', 'data': {'status': 'failed'},
                 'error': {'code': 'x'}}
        self._patch(monkeypatch, _Proc(stdout=json.dumps(outer)))
        p = lmod.run_playback('repo', {}, 'META')
        assert p['message'] == '回放失败'


# ---------------------------------------------------------------- send_to_pipe

class TestSendToPipe:
    def _patch(self, monkeypatch, proc=None, exc=None):
        calls = []

        def fake(*a, **k):
            calls.append((a, k))
            if exc is not None:
                raise exc
            return proc

        monkeypatch.setattr(lmod, 'run_cmd_safe', fake)
        return calls

    def test_success(self, monkeypatch):
        calls = self._patch(monkeypatch, _Proc(stdout='out' * 1500))
        r = lmod.send_to_pipe('prompt text', ['agent', '--prompt', '-'])
        assert r == {'ok': True, 'exit_code': 0,
                     'stdout': ('out' * 1500)[-2000:]}
        assert 'message' not in r
        assert calls[0][0] == (['agent', '--prompt', '-'],)
        assert calls[0][1]['input'] == 'prompt text'

    def test_stdout_truncated_2000(self, monkeypatch):
        self._patch(monkeypatch, _Proc(stdout='a' * 5000))
        r = lmod.send_to_pipe('p', ['agent'])
        assert len(r['stdout']) == 2000

    def test_nonzero_exit(self, monkeypatch):
        self._patch(monkeypatch, _Proc(stdout='', stderr='bad stuff', rc=3))
        r = lmod.send_to_pipe('p', ['agent'])
        assert r['ok'] is False
        assert r['exit_code'] == 3
        assert r['message'] == '退出码 3: bad stuff'

    def test_file_not_found(self, monkeypatch):
        self._patch(monkeypatch, exc=FileNotFoundError())
        r = lmod.send_to_pipe('p', ['no-such-agent'])
        assert r == {'ok': False, 'message': 'agent 可执行文件不存在: no-such-agent'}

    def test_other_exception(self, monkeypatch):
        self._patch(monkeypatch, exc=RuntimeError('weird'))
        r = lmod.send_to_pipe('p', ['agent'])
        assert r['ok'] is False
        assert 'pipe 注入异常' in r['message']
        assert 'weird' in r['message']

    def test_cwd_and_timeout_passthrough(self, monkeypatch):
        calls = self._patch(monkeypatch, _Proc(stdout=''))
        lmod.send_to_pipe('p', ['agent'], cwd='C:/w', timeout=5)
        kwargs = calls[0][1]
        assert kwargs == {'input': 'p', 'timeout': 5, 'cwd': 'C:/w'}


# ---------------------------------------------------------------- aliases

def test_uppercase_aliases():
    assert lmod.RUN_PLAYBACK is lmod.run_playback
    assert lmod.SEND_TO_PIPE is lmod.send_to_pipe


def test_all_exports():
    assert set(lmod.__all__) == {'DEFAULT_IGNORE', 'fingerprint', 'clipboard_write',
                                 'clipboard_clear', 'focus_window', 'run_playback',
                                 'RUN_PLAYBACK'}
