# -*- coding: utf-8 -*-
"""actus/tests/test_loophelpers_contracts.py — loophelpers（公开 API，0% 覆盖）。

`loophelpers.py` 是 `__init__` 的 **4 个惰性导出**（fingerprint / clipboard_write /
clipboard_clear / focus_window）的实现，属公开 API，不能删；但此前 0% 覆盖。
本文件只测**纯逻辑、无外部依赖**部分；真实回放（run_playback）/ Windows GUI
（剪贴板、窗口聚焦）不真跑，只测退化契约与解包逻辑（monkeypatch 子进程）。

当前语义钉点（重要）：
  * `fingerprint()` 的 `cache` 参数**目前完全没有被读取**（`_file_hash` 是死代码），
    cache 传入后仍为空、结果与不传一致 —— 本文件钉住现状并注明"若要接线需同时
    更新产品与测试"；
  * `fingerprint()` 对**纯 mtime 变化**（内容不变）也会变（parts 含 size+mtime_ns），
    这是 docstring 声明的增量检测语义，不是内容哈希；
  * `clipboard_write` 在非 Windows + pyperclip 缺失时返回 False（不抛）；
  * `focus_window` 在非 Windows 返回 True（v0.1 附着语义，假定终端在前台）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import loophelpers  # noqa: E402


@pytest.fixture
def project(tmp_path, monkeypatch):
    """tmp 项目根 + 把 HOME/ACTUS_META_DIR 隔离（无外部副作用）。"""
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    home.mkdir()
    meta.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.txt").write_text("alpha", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_text("beta", encoding="utf-8")
    return root


# ===========================================================================
# fingerprint
# ===========================================================================

def test_fingerprint_same_directory_is_stable(project):
    """退步了会怎样：同一目录连续两次指纹不同（遍历顺序/临时文件混入）——
    增量检测永远认为"有变化"，每次 tick 都触发全量重跑。

    断言：同一内容、无改动 → 两次 fingerprint 完全相等；非空十六进制。
    """
    first = loophelpers.fingerprint(str(project))
    second = loophelpers.fingerprint(str(project))

    assert first == second
    assert isinstance(first, str) and len(first) >= 32


def test_fingerprint_changes_when_content_changes(project):
    """退步了会怎样：改了文件指纹不变 —— 增量循环漏掉真实改动（最核心的契约）。

    断言：改 `a.txt` 内容（并确保 size 变化）→ 指纹与改动前不同。
    """
    before = loophelpers.fingerprint(str(project))
    (project / "a.txt").write_text("alpha-changed-longer", encoding="utf-8")

    assert loophelpers.fingerprint(str(project)) != before


def test_fingerprint_mtime_only_change_changes_fingerprint(project):
    """退步了会怎样：有人把 fingerprint 改成"只哈希内容"却忘了改契约文档 ——
    纯 touch（mtime 变、内容不变）的改动会被静默忽略/或反过来破坏现有语义。

    当前语义（docstring：逐文件 (relpath, size, mtime_ns) 排序后总哈希）：
    **mtime 变 → 指纹变**，即使内容完全一样。本用例钉住现状，避免两套语义漂移。
    """
    before = loophelpers.fingerprint(str(project))
    target = project / "a.txt"
    stat = os.stat(str(target))
    os.utime(str(target), (stat.st_atime, stat.st_mtime + 10))

    assert loophelpers.fingerprint(str(project)) != before


def test_fingerprint_ignore_extra_excludes_patterns(project):
    """退步了会怎样（变异重点）：`ignore_extra` 不生效 —— 日志/缓存/产物变动被当成
    项目改动，增量循环被无关文件反复唤醒。

    断言：先记录基线；新建 `x.log` 后，带 `ignore_extra=['*.log']` 的指纹
    **等于**基线；不带 ignore 的指纹**不等于**基线。
    """
    baseline = loophelpers.fingerprint(str(project))
    (project / "x.log").write_text("noise", encoding="utf-8")

    ignored = loophelpers.fingerprint(str(project), ignore_extra=["*.log"])
    unignored = loophelpers.fingerprint(str(project))

    assert ignored == baseline, "ignore_extra 没有排除 *.log"
    assert unignored != baseline, "对照组失败：不带 ignore 时应能看到 x.log"


def test_fingerprint_cache_parameter_is_currently_unused(project):
    """退步了会怎样：`cache` 参数悄悄改了结果（命中旧哈希导致漏掉真实改动），
    或产品接线后没同步测试。

    当前实现：`fingerprint(..., cache=...)` 接受但**从不读取 cache**（`_file_hash`
    为死代码）。断言：结果与不传 cache 完全一致、且调用后 cache 仍为空；
    若将来真正启用增量缓存，本用例会红 —— 届时需同步更新产品契约与测试。
    """
    cache = {}
    with_cache = loophelpers.fingerprint(str(project), cache=cache)
    without = loophelpers.fingerprint(str(project))

    assert with_cache == without
    assert cache == {}, "cache 参数当前应为未使用（实测被填充说明实现已变更）"


def test_fingerprint_samples_git_metadata_mtime(project):
    """退步了会怎样：纯提交（工作区无改动、只动 .git/HEAD）被漏掉 —— 增量循环
    永远不知道仓库前进了。

    断言：创建 `.git/HEAD` 后记录指纹；把它 mtime 拨后 → 指纹改变。
    """
    git = project / ".git"
    git.mkdir()
    head = git / "HEAD"
    head.write_text("ref: refs/heads/main\n", encoding="utf-8")
    before = loophelpers.fingerprint(str(project))

    stat = os.stat(str(head))
    os.utime(str(head), (stat.st_atime, stat.st_mtime + 10))

    assert loophelpers.fingerprint(str(project)) != before


def test_default_ignore_is_nonempty_and_sane():
    """退步了会怎样：DEFAULT_IGNORE 被清空/写坏 —— `.git`、`__pycache__`、产物目录
    全部进入指纹，任何运行都会改变指纹（自激循环）。

    断言：非空列表；包含 `.git/`、`__pycache__/` 与 `*.pyc`（只钉关键项，避免脆）。
    """
    patterns = loophelpers.DEFAULT_IGNORE

    assert isinstance(patterns, list) and patterns
    assert ".git/" in patterns
    assert "__pycache__/" in patterns
    assert "*.pyc" in patterns


# ===========================================================================
# clipboard / focus：外部依赖缺失时的退化契约
# ===========================================================================

def test_clipboard_write_degrades_without_pyperclip(monkeypatch):
    """退步了会怎样（docstring 承诺"缺失时按注释语义退化"）：环境中没有 pyperclip
    且非 Windows 时，`clipboard_write` 抛 ImportError/AttributeError 而不是返回 False ——
    调用方（paste 通道）整条挂掉。

    断言：monkeypatch 造 pyperclip 缺席 + sys.platform='linux' → 返回 False、不抛。
    """
    monkeypatch.setitem(sys.modules, "pyperclip", None)   # import 时必 ImportError
    monkeypatch.setattr(sys, "platform", "linux")

    assert loophelpers.clipboard_write("hello") is False


def test_clipboard_clear_is_noop_off_windows(monkeypatch):
    """退步了会怎样：非 Windows 上 clipboard_clear 仍去 import ctypes.windll ——
    直接把"清理剪贴板"变成崩溃点。

    断言：sys.platform='linux' → 返回 None（no-op），不触碰任何平台 API。
    """
    monkeypatch.setattr(sys, "platform", "linux")

    assert loophelpers.clipboard_clear() is None


def test_focus_window_degrades_off_windows(monkeypatch):
    """退步了会怎样：非 Windows 上 focus_window 返回 False/抛异常 —— v0.1 的"附着
    语义"（假定终端已在前台）被破坏，调用方误以为无法聚焦而中止。

    断言：sys.platform='linux' → 返回 True（docstring 明确契约）。
    """
    monkeypatch.setattr(sys, "platform", "linux")

    assert loophelpers.focus_window(".*") is True


# ===========================================================================
# run_playback：只测常量与"不真跑"的解包逻辑（monkeypatch 子进程）
# ===========================================================================

class _FakeProc(object):
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_run_playback_alias_exists():
    """退步了会怎样：动作用的大写别名 `RUN_PLAYBACK` 丢掉 —— loop_prompt 动作导入即崩。

    断言：`RUN_PLAYBACK is run_playback`，且都可调用（**不真正执行回放**）。
    """
    assert loophelpers.RUN_PLAYBACK is loophelpers.run_playback
    assert callable(loophelpers.run_playback)


def test_run_playback_unpacks_engine_output(monkeypatch, project):
    """退步了会怎样：回放子进程出参解包错（把引擎外层 {status,data,error} 当成
    动作载荷返回）—— 调用方拿不到动作自身字段，误报成功/失败。

    断言（monkeypatch 子进程，不真跑）：
      * 外层 ok + data={status:ok,foo:1} → 返回 data 内容；
      * 非 JSON 输出 → 返回 status='failed' 且 message 含原始输出片段；
      * 外层 failed + error.message → 载荷 status 非 ok 且 message 透传。
    """
    calls = []

    def fake_cmd(cmd, cwd=None, env=None, timeout=None):
        calls.append({"cmd": cmd, "cwd": cwd, "timeout": timeout})
        return fake_cmd.proc

    monkeypatch.setattr(loophelpers, "run_cmd_safe", fake_cmd)

    fake_cmd.proc = _FakeProc(stdout='{"status":"ok","data":{"status":"ok","foo":1}}')
    ok = loophelpers.run_playback(str(project), {"x": 1}, str(project / "meta"))
    assert ok.get("foo") == 1 and ok.get("status") == "ok", ok
    assert calls and "--confirm" in calls[0]["cmd"]

    fake_cmd.proc = _FakeProc(stdout="not-json-output", returncode=1)
    bad = loophelpers.run_playback(str(project), {}, str(project / "meta"))
    assert bad.get("status") == "failed", bad
    assert "not-json-output" in (bad.get("message") or ""), bad

    fake_cmd.proc = _FakeProc(
        stdout='{"status":"failed","data":null,"error":{"message":"boom"}}')
    failed = loophelpers.run_playback(str(project), {}, str(project / "meta"))
    assert failed.get("status") != "ok"
    assert failed.get("message") == "boom", failed
