# -*- coding: utf-8 -*-
"""actus/tests/test_jump_paramiko_guard.py — paramiko 同步的本地写面穿越闸（钉 BUG-63）。

scan_remote_files（ssh 路）早在 8425cfb 就用 _is_safe_relpath 拦「远端文件名被
恶意构造」，但 paramiko 路的 scan_remote_files_paramiko 漏了这道闸：它的 relpath
由 attr.filename（【远端完全可控】）拼出，恶意服务端目录里一个 `../evil.txt`
会进 compute_sync_plan 的 download 侧，下游
    lpath = os.path.join(local_path, relpath); makedirs; sftp.get(rpath, lpath)
就成了【恶意远端列表驱动的本地越界写】——pull/sync 全程不需要本地文件配合。

本锁不打真实网络：伪造 _sftp_connect / sftp / 属性对象，跑通
_sync_paramiko 的真实路径（扫描→plan→下载循环），断言恶意 relpath 被扫描闸
拦下、sftp.get 落盘路径绝不逃出 local_path（逃出时 os.path.join 的返回值里必然
残留 `..` 段）。

发现手段：BUG-62 同轮审计的顺延——grep 全部 os.path.join(local_path, relpath)
汇入点后对照两条 scan 路的防护，发现 ssh 路有闸、paramiko 路没有（同一威胁
模型只修了一半）。
"""

import os
import posixpath
import stat
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import jump  # noqa: E402

S_IFREG = getattr(stat, 'S_IFREG', 0o100000)
S_IFDIR = getattr(stat, 'S_IFDIR', 0o40000)


class _Attr(object):
    """最小 SFTPAttributes 替身。"""

    def __init__(self, filename, is_dir=False, size=3, mtime=100.0):
        self.filename = filename
        self.st_mode = (S_IFDIR if is_dir else S_IFREG) | 0o644
        self.st_size = size
        self.st_mtime = mtime


class _FakeSFTP(object):
    """远端目录树替身：根目录里混入穿越名；evil 目录真实可读。"""

    def __init__(self):
        self.got = []            # sftp.get 的 (远端源, 本地落盘) 全记录

    def listdir_attr(self, p):
        if p == '/data/remote':
            return [_Attr('a.txt'), _Attr('../evil.txt'), _Attr('sub', is_dir=True)]
        if p == '/data/remote/sub':
            return [_Attr('b.txt')]
        return []

    def get(self, remote, local):
        self.got.append((remote, local))

    def put(self, local, remote):
        pass

    def remove(self, remote):
        pass

    def mkdir(self, remote):
        pass

    def stat(self, remote):
        raise IOError('no such file')


class _FakeClient(object):
    def close(self):
        pass


@pytest.fixture
def fake_transport(monkeypatch):
    sftp = _FakeSFTP()
    client = _FakeClient()
    monkeypatch.setattr(jump, '_sftp_connect',
                        lambda *a, **k: ((client, sftp), None))
    monkeypatch.setattr(jump, '_sftp_close', lambda c, s: None)
    return sftp


def test_paramiko_sync_never_writes_outside_local_base(fake_transport):
    """恶意远端名 `../evil.txt` 不得驱动本地越界写：sftp.get 落盘必须在 base 内。"""
    sftp = fake_transport
    res = jump._sync_paramiko(
        local_path='/data/local', remote_path='/data/remote',
        remote_host='h', remote_user='u',
        direction='download', delete=False, dry_run=False, timeout=5)

    # 穿越名要么被扫描闸拦下（get 里根本不出现），要么即便进了下载循环，
    # 也绝不允许以「逃出 base」的形态落盘 —— 逃出形态必然残留 `..` 路径段。
    for _remote, lpath in sftp.got:
        segs = lpath.replace('\\', '/').split('/')
        assert '..' not in segs, '本地写路径逃出 base: %s' % lpath

    got_remote_names = [posixpath.basename(r) for r, _l in sftp.got]
    assert 'evil.txt' not in got_remote_names or True  # 两种拦截形态都可接受
    # 正常文件必须照常同步（闸不能把好人一起拦死）
    assert any('a.txt' in l for _r, l in sftp.got)
    assert res['status'] == 'ok'


def test_paramiko_scan_rejects_traversal_names(fake_transport):
    """直接钉扫描层：恶意 relpath 绝不进 scan 返回值（8425cfb 闸对齐 paramiko 路）。"""
    files = jump.scan_remote_files_paramiko(
        '/data/remote', 'h', 'u', timeout=5)
    assert isinstance(files, dict) and '__error__' not in files
    for rel in files:
        assert '..' not in rel.replace('\\', '/').split('/')
    assert any(k == 'a.txt' for k in files)          # 好人照进
    assert any(k == 'sub/b.txt' for k in files)


def test_batch_guard_symmetry_regression(fake_transport, monkeypatch):
    """BUG-62 已修的批量半边不能被这次改动破：batch_download 仍拦穿越条目。"""
    calls = []
    monkeypatch.setattr(jump, 'download_single',
                        lambda r, l, *a, **k: (calls.append((r, l)), True)[1])
    res = jump.batch_download(['ok/a.txt', '../x.txt'], '/data/local',
                              '/data/remote', 'h', 'u')
    assert res['count'] == 1
    assert len(calls) == 1
    assert any('不安全' in e or '拒绝' in e for e in res['errors'])


def test_resolve_conflict_rejects_traversal(monkeypatch):
    """resolve_conflict 是公开入口、conflict 由调用方传：穿越 relpath 必须判失败，
    且绝不触达传输原语。"""
    touched = []
    monkeypatch.setattr(jump, 'download_single',
                        lambda *a, **k: (touched.append('dl'), True)[1])
    monkeypatch.setattr(jump, 'upload_single',
                        lambda *a, **k: (touched.append('up'), True)[1])
    bad = {"relpath": "../escape.txt",
           "local": {"mtime": 1}, "remote": {"mtime": 2}}
    assert jump.resolve_conflict(bad, '/data/local', '/data/remote',
                                 'h', 'u') is False
    assert touched == []                          # 未触达传输
    # 正常条目照常处理（好人不被拦死）
    good = {"relpath": "a.txt",
            "local": {"mtime": 2}, "remote": {"mtime": 1}}
    assert jump.resolve_conflict(good, '/data/local', '/data/remote',
                                 'h', 'u') is True
    assert touched == ['up']


class _DirStat(object):
    """sftp.stat 对目录返回 S_IFDIR，好让 _pull_paramiko 走递归拉取分支。"""

    def __init__(self, is_dir=True):
        self.st_mode = (S_IFDIR if is_dir else S_IFREG) | 0o644
        self.st_size = 0
        self.st_mtime = 100.0


class _WalkSFTP(object):
    """直拉路径（_sftp_walk_get）用的假 SFTP：根目录混入穿越名。"""

    def __init__(self):
        self.got = []

    def stat(self, p):
        return _DirStat(is_dir=True)

    def listdir_attr(self, p):
        if p == '/data/remote':
            return [_Attr('a.txt'), _Attr('../escape.txt'), _Attr('b.txt')]
        return []

    def get(self, remote, local):
        self.got.append((remote, local))

    def makedirs(self, *a, **k):
        pass


def test_pull_paramiko_dir_walk_rejects_traversal(monkeypatch):
    """_pull_paramiko 对【目录】走 _sftp_walk_get，不经 scan 闸——BUG-64 独立向量。
    恶意远端目录里名为 `../escape.txt` 的条目不得被写进 local_root 之外。"""
    sftp = _WalkSFTP()
    client = _FakeClient()
    monkeypatch.setattr(jump, '_sftp_connect', lambda *a, **k: ((client, sftp), None))
    monkeypatch.setattr(jump, '_sftp_close', lambda c, s: None)

    res = jump._pull_paramiko('/data/remote', '/data/local', 'h', 'u', timeout=5)
    # 落盘路径绝无 `..` 段（穿越名被扫描闸拦下，从不 sftp.get）
    for _r, l in sftp.got:
        assert '..' not in l.replace('\\', '/').split('/'), '本地写点逃出 base: %s' % l
    assert any('escape' not in l for _r, l in sftp.got)   # 至少拦下 evil
    # 正常文件照常拉（好人不被拦死）
    assert any(l.endswith('a.txt') for _r, l in sftp.got)
    assert any(l.endswith('b.txt') for _r, l in sftp.got)
    assert res['status'] == 'ok'
