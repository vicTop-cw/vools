"""jump.py 远程 shell 命令引用（防空格断裂 / 命令注入）回归。

jump 经 ssh 在远端执行 find/mkdir/tar，路径与 --exclude 历史上被 f-string
裸拼进 shell：含空格路径会断词（文档示例 Victor/My Build/x.jar 即踩），
含 ; / $() / 反引号可注入任意远端命令。这些测试不连真实 SSH，而是
monkeypatch subprocess.run/Popen，断言【构造出的远程命令】对任意输入
都是一个被单引号安全引用的单词。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import jump  # noqa: E402


# ---------- shquote 单元 ----------

def test_shquote_plain_and_spaces():
    assert jump.shquote("abc") == "'abc'"
    assert jump.shquote("a b") == "'a b'"
    assert jump.shquote("/data/My Build/x") == "'/data/My Build/x'"


def test_shquote_neutralizes_metacharacters():
    # 注入载荷：分号 / 命令替换 / 反引号 / 引号 全部应被字面化在单引号内
    payload = "x; rm -rf /; echo $(id) `whoami` $HOME & | >"
    q = jump.shquote(payload)
    assert q.startswith("'") and q.endswith("'")
    # 唯一可能逃逸单引号的是裸的 ' 字符（已转成 '\''），载荷内不应有未转义引号
    assert "; rm -rf /" in q  # 原样保留在引号里
    # 验证它真的是一个合法的 POSIX 单 token（用本地 sh 解析，若可用）
    import shutil
    import subprocess
    if shutil.which("sh"):
        out = subprocess.run(
            ["sh", "-c", "printf %s " + q], capture_output=True, text=True)
        assert out.returncode == 0
        assert out.stdout == payload


def test_shquote_embedded_single_quote():
    # 经典 O'Brien：内部单引号转成 '\''，整体仍是一个词
    q = jump.shquote("O'Brien")
    assert q == "'O'\\''Brien'"
    import shutil
    import subprocess
    if shutil.which("sh"):
        out = subprocess.run(["sh", "-c", "printf %s " + q],
                             capture_output=True, text=True)
        assert out.stdout == "O'Brien"


# ---------- 远程命令构造：拦截 subprocess ----------

class _Rec:
    def __init__(self):
        self.calls = []
        self.returncode = 0
        self.stdout = ""
        self.stderr = ""


def _patch_run(monkeypatch, rec):
    def fake_run(cmd, **kw):
        rec.calls.append(list(cmd))
        return rec
    monkeypatch.setattr(jump.subprocess, "run", fake_run)


def test_scan_remote_quotes_path(monkeypatch):
    rec = _Rec()
    _patch_run(monkeypatch, rec)
    evil = "/data/My Build; touch /tmp/pwned"
    jump.scan_remote_files(evil, "h", "u", timeout=4)
    remote_cmd = rec.calls[0][-1]
    assert remote_cmd.startswith("find '")
    # 注入片段必须在引号内，不是未引用的 `;`
    assert "touch /tmp/pwned" in remote_cmd
    assert "; touch /tmp/pwned" in remote_cmd
    assert "find '/data/My Build; touch /tmp/pwned'" in remote_cmd


def test_push_scp_mkdir_quotes_path(monkeypatch):
    rec = _Rec()
    calls = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        return rec
    monkeypatch.setattr(jump.subprocess, "run", fake_run)

    jump._push_scp("/local/a", "/remote/My Dir", "h", "u", 22, None, None,
                   ["/local/a"], 30)
    # 第一个 run 是 ssh mkdir，其远程命令参数必须引用目录
    mkdir_cmd = calls[0][-1]
    assert mkdir_cmd == "mkdir -p '/remote/My Dir'"


def test_pull_tar_exclude_pattern_is_quoted(monkeypatch):
    captured = {}

    class FakeProc:
        returncode = 0
        def communicate(self, *a, **k):
            return ("", "")
        def wait(self, *a, **k):
            return 0

    def fake_popen(cmd, **kw):
        captured.setdefault("cmds", []).append(list(cmd))
        return FakeProc()
    monkeypatch.setattr(jump.subprocess, "Popen", fake_popen)

    jump._pull_tar_ssh("/r/d;id", "/local", "h", "u", 22, None, None,
                       ["a'b", "node_modules"], 30)
    remote = captured["cmds"][0][-1]
    # 含单引号的 exclude 被安全引用；远端 POSIX 路径按 posixpath 切成
    # dirname=/r basename=d;id，且 basename 里的 ; 被单引号字面化（不注入）
    assert "--exclude 'a'\\''b'" in remote
    assert "--exclude 'node_modules'" in remote
    assert "-C '/r'" in remote
    assert " 'd;id'" in remote          # 分号在引号内
    assert remote.count("d;id") >= 1 and "d;id " not in remote  # 未作为裸命令
