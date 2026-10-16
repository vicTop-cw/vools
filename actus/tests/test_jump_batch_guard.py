# -*- coding: utf-8 -*-
"""actus/tests/test_jump_batch_guard.py — 批量传输入口的路径穿越闸（钉 BUG-62）。

背景：8425cfb 给 jump 的【扫描入口】(scan_local_files / scan_remote_files*) 加了
`_is_safe_relpath` 闸，理由是「远端文件名被恶意构造时，`os.path.join(local_path,
relpath)` 若含 `..` 会逃出目标目录，绝对路径/盘符同理（join 直接丢 base）」。

但同一道闸漏覆盖了【公开批量 API】：batch_upload / batch_download 的 `files` 参数
由调用方直接传入（同步计划常被持久化后再加载，不再经 scan），旧代码对每条 relpath
直接 `os.path.join(local_path, relpath)` + `remote_join(...)` 就发起传输——
download 尤其危险：它把远端影响来的相对路径【写进本地】，`../../` 可越界落盘。

本锁不打真实网络：monkeypatch upload_single / download_single 只记录被要求传输的
路径，断言不安全条目【从不】被送去传输、且被记进 errors；安全条目照常放行。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import jump  # noqa: E402


@pytest.fixture
def spy(monkeypatch):
    """拦截传输原语，记录 (local, remote) 调用，返回不真发。"""
    calls = []

    def fake_upload(local_file, remote_file, *a, **k):
        calls.append(('up', local_file, remote_file))
        return True

    def fake_download(remote_file, local_file, *a, **k):
        calls.append(('down', remote_file, local_file))
        return True

    monkeypatch.setattr(jump, 'upload_single', fake_upload)
    monkeypatch.setattr(jump, 'download_single', fake_download)
    return calls


_LOCAL = os.path.join('C:', os.sep) if os.name == 'nt' else '/base'


def test_batch_download_rejects_traversal(spy):
    res = jump.batch_download(
        ['ok/a.txt', '../escape.txt', '/abs.txt', 'C:/x.txt'],
        local_path='/data/local', remote_path='/data/remote',
        remote_host='h', remote_user='u')
    # 只有安全条目被送去传输
    sent_local = [c[2] for c in spy]
    assert all('escape.txt' not in p for p in sent_local), '穿越条目竟被下载写盘'
    assert all(not p.startswith('/abs.txt') for p in sent_local)
    assert len(spy) == 1
    assert res['count'] == 1
    # 被拒条目明确记入 errors，且不含敏感拼接结果
    joined = '\n'.join(res['errors'])
    assert 'escape.txt' in joined
    assert '不安全' in joined or '拒绝' in joined


def test_batch_upload_rejects_traversal(spy):
    res = jump.batch_upload(
        ['safe.txt', '..\\..\\evil.txt'],
        local_path='/data/local', remote_path='/data/remote',
        remote_host='h', remote_user='u')
    assert len(spy) == 1              # evil 被拦，未拼本地路径去上传
    assert res['count'] == 1
    assert any('evil' in e for e in res['errors'])


def test_batch_accepts_normal_relpaths(spy):
    res = jump.batch_download(
        ['a.txt', 'sub/b.txt', 'x/y/z.txt'],
        local_path='/data/local', remote_path='/data/remote',
        remote_host='h', remote_user='u')
    assert res['count'] == 3
    assert res['errors'] == []
    # 远端拼接用 POSIX 分隔符（不被本地 os.path 污染）
    assert any(c[1] == '/data/remote/sub/b.txt' for c in spy)
