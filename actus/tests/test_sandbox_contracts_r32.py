# -*- coding: utf-8 -*-
"""actus/tests/test_sandbox_contracts_r32.py — sandbox（64 stmts，28% 覆盖）安全契约。

`sandbox.py` 是执行层的"尽力而为"隔离：jail 根、路径越界校验、环境注入、资源限额、
回收。安全模块的低覆盖比普通模块危险 —— 本文件专门钉住**越界必须被拦**、
**未启用沙箱时语义不变**、**限额失败不抛**、**回收不留残留**。

诚实边界（与模块 docstring 一致）：
  * 这不是 OS 级强制沙箱；裸 `os` 调用不受强制（本文件只测 guard_write 工具本身）；
  * 符号链接逃逸依赖运行环境允许创建 symlink；不允许时**窄跳过并说明**，不硬跑。
"""

import os
import sys

import pytest

_ACTUS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import sandbox  # noqa: E402


@pytest.fixture
def jail(tmp_path, monkeypatch):
    """tmp artifacts 根 + 清掉可能继承的 ACTUS_SANDBOX_ROOT。"""
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("ACTUS_META_DIR", str(tmp_path / "meta"))
    monkeypatch.delenv("ACTUS_SANDBOX_ROOT", raising=False)
    root = sandbox.prepare(str(artifacts), "exec-1")
    return artifacts, root


# ===========================================================================
# prepare / env
# ===========================================================================

def test_prepare_creates_jail_root_and_is_idempotent(jail):
    """退步了会怎样：jail 根没建/建在错误层级 —— 动作在无沙箱根下运行
    （TMP 指向宿主临时目录），隔离形同虚设；重复调用抛 FileExistsError。

    断言：root == artifacts/_sandbox/<exec_id>；目录存在；重复 prepare 不抛且路径相同。
    """
    artifacts, root = jail
    expected = os.path.join(str(artifacts), "_sandbox", "exec-1")
    assert os.path.realpath(root) == os.path.realpath(expected)
    assert os.path.isdir(root)

    again = sandbox.prepare(str(artifacts), "exec-1")
    assert again == root


def test_sandbox_env_injects_all_temp_variables(jail):
    """退步了会怎样：漏注入 TMPDIR/TEMP/TMP 或 ACTUS_SANDBOX_ROOT —— 子进程把临时
    文件写到真实宿主临时目录，越出 jail；guard 函数也失去根。

    断言：ACTUS_SANDBOX='1'、ROOT=root、TMPDIR/TEMP/TMP 全部=root（POSIX+Windows 都覆盖）。
    """
    _artifacts, root = jail
    env = sandbox.sandbox_env(root)

    assert env["ACTUS_SANDBOX"] == "1"
    assert env["ACTUS_SANDBOX_ROOT"] == root
    for name in ("TMPDIR", "TEMP", "TMP"):
        assert env[name] == root, (name, env)


# ===========================================================================
# guard_write：越界拦截（安全关键）
# ===========================================================================

def test_guard_write_allows_targets_inside_jail(jail):
    """退步了会怎样：jail 内合法写入被误拦 —— 沙箱下动作无法产出任何 artifact。

    断言：jail 内嵌套路径返回 realpath 且可实际写入；根目录自身也允许。
    """
    _artifacts, root = jail
    target = os.path.join(root, "out", "deep", "file.txt")

    got = sandbox.guard_write(target, root)

    assert os.path.realpath(got) == os.path.realpath(target)
    os.makedirs(os.path.dirname(got), exist_ok=True)
    with open(got, "w", encoding="utf-8") as handle:
        handle.write("ok")
    assert open(got, encoding="utf-8").read() == "ok"


def test_guard_write_blocks_parent_traversal(jail):
    """退步了会怎样（安全洞）：`jail/../host.txt` 被放行 —— 动作写到 jail 外的
    宿主目录（本模块的核心承诺"越界写拦截"失效）。

    断言：抛 PermissionError，消息点名"越界"。
    """
    _artifacts, root = jail
    escape = os.path.join(root, "..", "host.txt")

    with pytest.raises(PermissionError) as excinfo:
        sandbox.guard_write(escape, root)
    assert "越界" in str(excinfo.value)


def test_guard_write_blocks_absolute_path_outside_jail(jail):
    """退步了会怎样：绝对路径（宿主任意位置）绕过校验 —— 等价于没有沙箱。

    断言：绝对路径 jail 外 → PermissionError；绝对路径 jail 内 → 放行。
    """
    artifacts, root = jail
    outside = str(artifacts / "outside.txt")

    with pytest.raises(PermissionError):
        sandbox.guard_write(outside, root)

    inside = os.path.join(root, "inside.txt")
    assert sandbox.guard_write(inside, root) == os.path.realpath(inside)


def test_guard_write_blocks_symlink_escape(jail):
    """退步了会怎样（2026-10-16 实测修复回归）：用 abspath 而非 realpath —— jail 内
    建 `link -> 宿主目录`，写 `jail/link/secret` 就逃出 jail。

    断言：symlink 指向 jail 外 → PermissionError。环境不允许建 symlink 时窄跳过。
    """
    artifacts, root = jail
    outside_dir = artifacts / "host-dir"
    outside_dir.mkdir()
    link = os.path.join(root, "link")
    try:
        os.symlink(str(outside_dir), link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip("本机不允许创建目录符号链接，无法测 symlink 逃逸: %s" % exc)

    with pytest.raises(PermissionError):
        sandbox.guard_write(os.path.join(link, "secret.txt"), root)


def test_guard_write_without_root_is_passthrough(tmp_path, monkeypatch):
    """退步了会怎样：未启用沙箱（无 root/无环境变量）时反而抛错 —— 非沙箱执行路径
    全部挂掉（零回归被破坏）。

    断言：root=None 且无环境变量 → 返回 abspath（不抛）；root=None 但有
    ACTUS_SANDBOX_ROOT → 按该根校验（越界仍拦）。
    """
    monkeypatch.delenv("ACTUS_SANDBOX_ROOT", raising=False)
    target = tmp_path / "plain.txt"
    assert sandbox.guard_write(str(target)) == os.path.abspath(str(target))

    jail_dir = tmp_path / "j"
    jail_dir.mkdir()
    monkeypatch.setenv("ACTUS_SANDBOX_ROOT", str(jail_dir))
    with pytest.raises(PermissionError):
        sandbox.guard_write(str(target))


# ===========================================================================
# cleanup / apply_limits / 常量
# ===========================================================================

def test_cleanup_removes_jail_and_keep_preserves_it(jail):
    """退步了会怎样：cleanup 不删（jail 无限堆积）或 keep=True 也删（审计现场被毁）。

    断言：默认删除 jail 根；keep=True 保留；对不存在的 jail 再 cleanup 不抛。
    """
    artifacts, root = jail
    with open(os.path.join(root, "x"), "w", encoding="utf-8") as handle:
        handle.write("x")

    sandbox.cleanup(str(artifacts), "exec-1", keep=True)
    assert os.path.isdir(root)

    sandbox.cleanup(str(artifacts), "exec-1")
    assert not os.path.exists(root)
    sandbox.cleanup(str(artifacts), "exec-1")      # 幂等/不存在也不抛


def test_apply_limits_windows_without_proc_returns_false(monkeypatch):
    """退步了会怎样：没有 proc 时 apply_limits 抛异常/谎报 True —— 调用方以为限额
    已生效（实际零限额），安全属性变成假声明。

    断言：os.name='nt'、proc=None → False；
    proc 对象缺 `_handle`（Job Object 必失败）→ False 而不是抛。
    """
    monkeypatch.setattr(os, "name", "nt")
    assert sandbox.apply_limits(None) is False

    class _NoHandle(object):
        pass

    assert sandbox.apply_limits(_NoHandle()) is False


def test_apply_limits_posix_success_and_failure(monkeypatch):
    """退步了会怎样：POSIX 限额失败被当成致命错误（子进程起不来）或成功路径没真正
    setrlimit（限额形同虚设）。

    断言（monkeypatch 假 resource，不真改本进程 rlimit）：
      * setrlimit 可调用 → apply_limits() True，且 RLIMIT_AS/RLIMIT_CPU 都被设置；
      * setrlimit 抛异常 → False（不炸）。
    """
    calls = []

    class _FakeResource(object):
        RLIMIT_AS = "AS"
        RLIMIT_CPU = "CPU"
        RLIM_INFINITY = -1

        @staticmethod
        def setrlimit(kind, values):
            calls.append((kind, values))

    fake = {"resource": _FakeResource()}
    monkeypatch.setattr(sys, "modules", dict(sys.modules, **fake))
    monkeypatch.setattr(os, "name", "posix")
    assert sandbox.apply_limits() is True
    assert {kind for kind, _v in calls} == {"AS", "CPU"}

    def _boom(_kind, _values):
        raise OSError("nope")

    fake_resource = type("_R", (_FakeResource,), {"setrlimit": staticmethod(_boom)})
    monkeypatch.setitem(sys.modules, "resource", fake_resource())
    assert sandbox.apply_limits() is False


def test_job_limits_are_sane():
    """退步了会怎样：限额被改成 0/负数 —— 子进程创建即被杀或完全不受限。

    断言：memory_bytes 在 64MiB~4GiB 之间；cpu_seconds 在 1~3600 之间。
    """
    limits = sandbox.JOB_LIMITS
    assert 64 * 1024 * 1024 <= limits["memory_bytes"] <= 4 * 1024 * 1024 * 1024
    assert 1 <= limits["cpu_seconds"] <= 3600


def test_prepare_rejects_traversal_exec_id(jail):
    """退步了会怎样（安全洞，第 32 轮已修）：`prepare(artifacts, '../escape')` 在
    artifacts 之外创建目录 —— jail 根可被 exec_id 控制，后续 guard_write 的根也
    落在非法位置（沙箱边界由调用参数决定）。

    断言：父目录穿越/绝对化/非法字符/超长的 exec_id 一律 ValueError，且**不创建**
    artifacts 之外的目录（修复前该用例会红：旧实现直接 join 并 makedirs）。
    """
    artifacts, _root = jail

    for bad in ("../escape", r"..\escape", "/abs/path", "a/b", ".", "..",
                "bad name", "x" * 65):
        with pytest.raises(ValueError):
            sandbox.prepare(str(artifacts), bad)

    assert not (artifacts.parent / "escape").exists()
    # 合法名仍然工作（不能因噎废食）
    assert sandbox.prepare(str(artifacts), "exec_ok-1.2") == os.path.join(
        str(artifacts), "_sandbox", "exec_ok-1.2")
