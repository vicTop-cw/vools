# -*- coding: utf-8 -*-
"""actus 测试套件全局夹具：**运行时数据目录默认隔离**（测试卫生）。

测试分档（第 22 轮起）：
  * `pytest -m "not slow"` —— 日常快速子集（跳过真实 probe / 真实动作执行 /
    真实 TLS / 真实 crypto IO / 71 个 CLI 子命令全跑等慢测试）；
  * `pytest` —— 全量（CI 的 test-actus 作业必须跑这条）。
 慢测试清单：grep -rn "pytest.mark.slow" tests/。

背景（第 15 轮，真实事故）：测试套件跑完会把真实仓库 `_meta/` 写脏
（`events.jsonl` / `probe_cache.json` / `actions.index.json` / `call_log.db` /
`runs/*.json` / `status.json` / `logs/*`）。它们是 gitignore 的运行时状态，但同属
「测试写真实仓库文件」——与 `calculator.actus.schema.md` 被中断污染同族：
并发跑、CI 次跑之间会互相影响，也让「零副作用」类断言失真。

做法：autouse 把 `ACTUS_META_DIR` 默认指到 per-test tmp 目录。各用例自己
`monkeypatch.setenv("ACTUS_META_DIR", ...)` 时（更具体）仍以用例为准。
本夹具**不碰** `actions/`、`contracts/` 等真实产物目录（那是产物，不是运行时状态）。
"""

# ---------------------------------------------------------------------------
# 模块导入路径修复（第 31 轮 / 统帅轮-08时）：修复 5 个测试文件收集失败
#
# 问题：在 `actus/` 目录跑 pytest 时，`vools` 解析到 `actus/vools/`（仅含 actus
# 子模块），导致 `import vools.core` / `import vools.bridge` 失败，5 个测试文件
# （test_action_lookup / test_desktop_contracts_r65 / test_directives /
# test_mdtest_contracts_r55 / test_mdtest_validation）收集报错。
#
# 根因：actus/vools/ 是 actus 子项目的本地 vools 包副本（只含 actus 子模块），
# 缺 core / bridge 子模块。vools.core 在仓库根 `vools/core/`，vools.bridge 在
# `bridges/vools/bridge/`。
#
# 修复：把仓库根 `vools/` 与 `bridges/` 加入 sys.path，让 `vools` 优先解析到
# 仓库根的完整包（含 core/bridge），而不是 actus/vools/ 的子集。
# 注意：此修复只在测试收集期生效（conftest 顶部），不影响运行时安装态。
# ---------------------------------------------------------------------------
import sys
import os

# 仓库根 = actus/ 的上两级目录（actus/tests/conftest.py → actus/ → vools/）
_VOOLS_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 把仓库根加入 sys.path（让 `import vools` 解析到完整包，而非 actus/vools/ 子集）
if _VOOLS_REPO_ROOT not in sys.path:
    sys.path.insert(0, _VOOLS_REPO_ROOT)

# 把 bridges/ 加入 sys.path（让 `import vools.bridge` 解析到 bridges/vools/bridge/）
_VOOLS_BRIDGES_DIR = os.path.join(_VOOLS_REPO_ROOT, "bridges")
if _VOOLS_BRIDGES_DIR not in sys.path:
    sys.path.insert(0, _VOOLS_BRIDGES_DIR)

# 把 rx/ 加入 sys.path（让 `import vools.reactive` 解析到 rx/vools/reactive/，
# 供 vools.actus.clipboard 使用；vools/__init__ 用 extend_path 合并命名空间，
# 不加 rx 根则 vools.reactive 整体不可见）
_VOOLS_RX_DIR = os.path.join(_VOOLS_REPO_ROOT, "rx")
if _VOOLS_RX_DIR not in sys.path:
    sys.path.insert(0, _VOOLS_RX_DIR)

# 把 actus/vools/ 加入 vools.__path__（让 `import vools.actus` 解析到
# actus/vools/actus/，因为 actus 源码在 actus/vools/actus/ 而非 vools/actus/）
_ACTUS_VOOLS_DIR = os.path.join(_VOOLS_REPO_ROOT, "actus", "vools")
try:
    import vools as _vools_pkg
    if _ACTUS_VOOLS_DIR not in _vools_pkg.__path__:
        _vools_pkg.__path__.append(_ACTUS_VOOLS_DIR)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# pytest tmpdir 清理对损坏 reparse point 的容忍补丁（统帅轮-02时 / T0r4.1）
#
# 真实事故（2026-11-07 实测）：Temp\pytest-of-victo\pytest-current 变成损坏的
# reparse point（fsutil reparsepoint query → Error 5，连 rmdir/takeown 都
# Access denied，无法在用户态删除）。pytest ≥7 每次进程结束都走
# cleanup_numbered_dir → cleanup_dead_symlinks → Path.resolve()，
# resolve 到这个坏链接抛 PermissionError(WinError 5) 且未被捕获 ——
# 结果：**196/196 个测试文件 rc=1，即使用例全过**（逐文件实测留证，
# _scan_result.json）。测试退出码全局不可信，CI 退出码判定失灵。
#
# 修复：包一层 cleanup_dead_symlinks，对 PermissionError/OSError 跳过该坏项
# （只影响退出清理的 symlink 体检，不影响任何测试行为与 tmp 内容）。
# ---------------------------------------------------------------------------


def _patch_cleanup_dead_symlinks_tolerant():
    try:
        import _pytest.pathlib as _pplib
    except Exception:
        return
    _orig = getattr(_pplib, "cleanup_dead_symlinks", None)
    if _orig is None or getattr(_orig, "_actus_tolerant", False):
        return

    def tolerant(root):
        try:
            return _orig(root)
        except (PermissionError, OSError):
            # 坏 reparse point / ACL 异常项：跳过清理体检（不影响测试结果）
            return

    tolerant._actus_tolerant = True  # type: ignore[attr-defined]
    _pplib.cleanup_dead_symlinks = tolerant
    # 已绑定的引用也换掉（cleanup_numbered_dir 闭包里按名字引用模块级函数）
    for _name in ("cleanup_numbered_dir", "make_numbered_dir_with_cleanup"):
        _fn = getattr(_pplib, _name, None)
        if _fn is not None:
            try:
                _fn.__globals__["cleanup_dead_symlinks"] = tolerant
            except Exception:
                pass


_patch_cleanup_dead_symlinks_tolerant()

import shutil
import time as _real_time

import pytest

# ---------------------------------------------------------------------------
# ② WSL 防 SIGTERM 守卫（R115 / 统帅轮-21时）
#
# 问题：沙箱对 `wsl.EXE` 有黑名单——任何 pytest 会话里只要某个用例（或 state
# 泄漏）实际 spawn 了 `wsl.exe`（最典型是 `probe/platform_tools._probe_windows_wsl`
# 跑 `wsl.exe -l -v`），沙箱会直接 SIGTERM 整个 pytest 进程，导致整段门禁无法在
# 沙箱内跑通（此前只能隔离分批）。
#
# 修法：在 conftest 载入期（仅 pytest 进程，不影响 `actus` 运行时二进制）把
# `subprocess.Popen` 包一层——命令可执行文件是 `wsl`/`wsl.exe` 时**不改产品代码、
# 直接抛 FileNotFoundError**，让来源代码走其既有「命令没跑起来 → (None,b"")」的优雅
# 降级分支（platform_tools._run 已捕获 FileNotFoundError）。于是：
#   * 沙箱内绝不真正 exec wsl.exe → 不会再被 SIGTERM；
#   * 代码既有的「WSL 不可用」路径被如实覆盖（正是沙箱 / 无 WSL 机的真实语义）；
#   * 需要真跑 WSL 的集成用例，设 `ACTUS_TEST_ALLOW_WSL=1` 即解除守卫。
# 仅拦截 wsl.exe（沙箱黑名单项），bash/cmd/python 等一律放行，爆破半径最小。
# 所有源码均 `import subprocess`（模块属性访问），故补丁对全部调用方（含
# subprocess.run，其内部引用模块级 Popen）生效。
# ---------------------------------------------------------------------------
import subprocess as _subprocess

_ACTUS_ALLOW_WSL = os.environ.get("ACTUS_TEST_ALLOW_WSL") == "1"

if not _ACTUS_ALLOW_WSL and not getattr(_subprocess.Popen, "_actus_wsl_guard", False):
    _actus_orig_popen = _subprocess.Popen

    def _actus_guarded_popen(cmd, *args, **kwargs):
        exe = ""
        if isinstance(cmd, (list, tuple)) and cmd:
            exe = cmd[0]
        elif isinstance(cmd, str) and cmd:
            exe = cmd.split(None, 1)[0]
        if os.path.basename(exe).lower() in ("wsl", "wsl.exe"):
            raise FileNotFoundError(
                "wsl.exe blocked by actus test guard "
                "(set ACTUS_TEST_ALLOW_WSL=1 to allow real WSL): %r" % (cmd,))
        return _actus_orig_popen(cmd, *args, **kwargs)

    _actus_guarded_popen._actus_wsl_guard = True  # type: ignore[attr-defined]
    _subprocess.Popen = _actus_guarded_popen


# ---------------------------------------------------------------------------
# ① session 级目录钉死 + 污染检测器（第 19 轮，终结 `~/.actus` 污染）
#
# 为什么需要（真实事故，3 次）：
#   1) 第 1 次：某个测试直接构造 Vault2()，默认目录 ~/.actus/vault2 被建库；
#      cmd-engine 删空库清现场 —— 后来又出现。
#   2) 第 2 次：修了 vault.py `_v2_session()` 守卫（库不存在就别造），
#      但**换一个入口**（别的路径仍构造 Vault2）又复现。
#   3) 第 3 次：二分定位到**跨测试环境泄漏** —— 决定性复现：
#        pytest tests/test_vault_readonly_contracts.py tests/test_vault_roundtrip.py
#      单跑每个文件都干净，合跑却创建 ~/.actus/vault2。
#
#   根因：前者用 monkeypatch.setenv('ACTUS_VAULT2_DIR', tmp) 做隔离；
#   teardown 把它**恢复成"未设置"**，紧接着的后者在"未设置"环境里构造
#   Vault2() → 走默认目录 ~/.actus/vault2 → 建库。
#   即：**一个测试的隔离手段，成了下一个测试的不隔离。**
#
# 修法：在**整个会话**期间把隔离目录钉死（不是 function scope），
# 用 os.environ 直接设值（monkeypatch 会在每个用例结束时还原，正是泄漏来源），
# 会话结束才恢复原值。这样任何测试 `delenv`/teardown 后拿到的也仍是 tmp 会话目录。
#
# 为什么不钉 ACTUS_REPO_ROOT：多个测试需要读**真实仓库**的 actions/contracts
# （如动作扫描、桌面首页、MCP 工具表）；钉到 tmp 会让它们找不到动作而失败。
# 仓库目录由各用例自己的 tmp fixture / monkeypatch 负责，不在此处钉。
# ---------------------------------------------------------------------------


#: 真实 ~/.actus 的"指纹"函数：文件相对路径 + mtime_ns + size。
def _real_actus_fingerprint():
    root = os.path.expanduser("~/.actus")
    if not os.path.isdir(root):
        return None
    rows = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            try:
                stat = os.stat(full)
                rows.append((os.path.relpath(full, root).replace(os.sep, "/"),
                             stat.st_mtime_ns, stat.st_size))
            except OSError:
                rows.append((os.path.relpath(full, root).replace(os.sep, "/"),
                             -1, -1))
    return sorted(rows)


#: 钉死的环境变量。**不钉 ACTUS_INSTALLED_DIR**：安装清单的默认位置由 HOME 推导
#: （`~/.actus/installed`），钉它反而会覆盖默认、破坏既有安装契约；HOME 已钉在 tmp，
#: 默认目录自然落在 tmp。只有外部显式设置该变量时才跟着钉到 tmp（避免写到外部路径）。
_PINNED_ENV = ("HOME", "USERPROFILE", "ACTUS_META_DIR", "ACTUS_VAULT2_DIR")


@pytest.fixture(scope="session", autouse=True)
def _pin_isolated_dirs(tmp_path_factory):
    """**整个测试会话**钉死隔离目录；并在会话结束时检测真实 ~/.actus 是否被污染。

    存在原因见上方注释：ACTUS_VAULT2_DIR 曾被某个测试用 monkeypatch.setenv 隔离，
    teardown 恢复成"未设置"后，紧接着的其它测试文件在默认目录建库，
    导致真实 ~/.actus 被污染 3 次。function-scope fixture 无法解决
    （泄漏恰好发生在"还原成未设置"的瞬间），所以必须 session scope + os.environ。

    实现要点：
      * session scope，整个会话期间保持（含所有文件、xdist worker 各自钉死）；
      * 用 `os.environ[...]` 而非 monkeypatch（monkeypatch 会在用例结束还原）；
      * `yield` 后先恢复原值，再断言真实 `~/.actus` 指纹与会话开始时一致 ——
        不一致直接 fail（污染检测器，见 `_real_actus_fingerprint`）；
      * HOME/USERPROFILE 也钉死（`~` 展开落在 tmp，双保险）。
    """
    real_actus_before = _real_actus_fingerprint()

    base = tmp_path_factory.mktemp("session-isolation")
    dirs = {
        "home": base / "home",
        "meta": base / "meta",
        "vault2": base / "vault2",
        "installed": base / "installed",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)

    # 种子动作的 .sig 由**包内置** `vools/actus/keys/default.pub` 验签：
    # `trust_model.KeyManager.load_public_key` 是「HOME 密钥目录优先 → 包内置
    # keys/ 回退兜底」，而种子签名本就是为「干净 checkout / pip 安装（HOME 无
    # ~/.actus/keys）」设计的（统帅轮-02时 T0r4.1）。
    #
    # 若把真实 HOME 的 `default.*` 复制进会话 HOME，一旦本机轮换过默认密钥，
    # 错误公钥会**遮蔽包内置真源** → 4 个种子动作恒报
    # `Signature verification failed`（2026-11-13 实测：真实 default.pub 与包内置
    # sha256 不同，前者验签 4/4 失败、后者 4/4 通过）。
    #
    # 所以只复制非 default 的 key 文件（如 test.*）供自签用例，default 交给
    # 包内置兜底；仍不写真实 HOME。
    real_keys = os.path.expanduser("~/.actus/keys")
    if os.path.isdir(real_keys):
        target_keys = dirs["home"] / ".actus" / "keys"
        target_keys.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            real_keys, str(target_keys),
            ignore=shutil.ignore_patterns("default.key", "default.pub"),
        )

    original = {name: os.environ.get(name) for name in _PINNED_ENV}
    pinned = {
        "HOME": str(dirs["home"]),
        "USERPROFILE": str(dirs["home"]),
        "ACTUS_META_DIR": str(dirs["meta"]),
        "ACTUS_VAULT2_DIR": str(dirs["vault2"]),
    }
    # 外部显式设置了安装目录才钉它；默认（未设）让安装器用 HOME 推导
    original["ACTUS_INSTALLED_DIR"] = os.environ.get("ACTUS_INSTALLED_DIR")
    if original["ACTUS_INSTALLED_DIR"] is not None:
        pinned["ACTUS_INSTALLED_DIR"] = str(dirs["installed"])
    os.environ.update(pinned)
    try:
        yield base
    finally:
        # 先恢复原环境（无论断言是否失败都要恢复），再检查污染
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        after = _real_actus_fingerprint()
        assert after == real_actus_before, (
            "测试会话污染了真实 ~/.actus！\n  会话前: %r\n  会话后: %r\n"
            "—— 某个测试在未隔离的默认目录创建/修改了 vault2 等文件；"
            "请用 session 级 `_pin_isolated_dirs` 或显式传 vault_dir/meta_dir。"
            % (real_actus_before, after))


@pytest.fixture(autouse=True)
def _isolate_runtime_meta_dir(tmp_path, monkeypatch):
    """默认把 `_meta` 运行时目录隔离到 tmp，防止测试写真实仓库的 `_meta/`。"""
    monkeypatch.setenv("ACTUS_META_DIR", str(tmp_path / "_meta_runtime"))


# ---------------------------------------------------------------------------
# 共用时间控制夹具：`advance_totp_window(n)`
#
# 为什么要有它（这是本会话 P0 的根因）：
#   14 轮测试全绿，但 L2/L3 的 master_key 曾把**每 60 秒变一次的 TOTP 动态码**
#   掺进 PBKDF2 —— 默认级别 L2 意味着"今天存的密钥明天解不开"（P0）。
#   所有用例都在**同一个 60 秒窗口**内跑 `register → auth → set → get`，
#   于是**测试跑得太快，替 bug 做了掩护**。没有可控时间，这类缺陷永远测不出来。
# ---------------------------------------------------------------------------

class _TotpClock(object):
    """可推进的假时钟（TOTP 窗口 = int(time.time()) // 60）。"""

    def __init__(self, now):
        self.now = float(now)

    def time(self):
        return self.now

    def __getattr__(self, name):
        # vault2 只在 anomaly_check 里用 time.localtime 等；其余属性透传真实模块
        return getattr(_real_time, name)


@pytest.fixture
def advance_totp_window(monkeypatch):
    """返回 `advance(n)`：把 TOTP 时间推进 n 个 60s 窗口（不 sleep）。

    **必须同时 patch 两处 time**（实测踩过）：
      * `vault2.time` —— 会话过期/审计/`used_codes` 时间；
      * `vools.security.otp.time` —— **TOTP 算法本体**定义在 core 的
        `vools/security/otp.py`，vault2 只是 import 引用。只换 vault2.time 时
        动态码仍按真实时间生成 → 推进窗口后第二次 auth 会先撞「动态码已被使用」，
        根本走不到"跨窗口解密"那一步。

    用法：
        def test_x(advance_totp_window):
            ... 窗口 N 写 ...
            advance_totp_window(1)      # 推进 1 个窗口
            ... 窗口 N+1 读 ...
        advance_totp_window(5)          # 推进 5 个窗口

    复原：全部走 monkeypatch，用例结束自动恢复，**不要手动改全局 time**。
    """
    from vools.actus import vault2 as _vault2
    from vools.security import otp as _otp

    clock = _TotpClock(_real_time.time())
    monkeypatch.setattr(_vault2, "time", clock)
    monkeypatch.setattr(_otp, "time", clock)

    def advance(n=1):
        clock.now += float(n) * 60.0
        return clock.now

    def advance_seconds(n=1):
        """秒级推进（TTL / used_codes 清理边界用；TOTP 窗口按 60s 粒度自动跟随）。"""
        clock.now += float(n)
        return clock.now

    advance.clock = clock
    advance.seconds = advance_seconds
    return advance


# ---------------------------------------------------------------------------
# 进程级单例重置（第 18 轮审计 #2/#6：顺序依赖 / xdist 随机红）
#
# `vault2._vault2_singleton`、`security._scanner`、`eventbus._bus`、`mcp_server._TASKS`
# 都是**进程级单例**。此前没有统一重置，测试顺序一变 / xdist 并发就会随机红，
# 而且会掩盖"单例状态未清理"的真实产品缺陷。
# 只在测试侧重置，不改产品代码；每个用例前后各重置一次，保证顺序无关。
# ---------------------------------------------------------------------------

def _reset_process_globals():
    """重置进程级单例（测试卫生；任何失败都不应阻断其它清理）。"""
    try:
        from vools.actus import eventbus as _eventbus
        _eventbus._bus = _eventbus.EventBus()
    except Exception:                      # noqa: BLE001 —— 导入/构造失败不阻断
        pass
    try:
        from vools.actus import mcp_server as _mcp
        try:
            _mcp._detach_event_forwarding()
        except Exception:                  # noqa: BLE001
            pass
        lock = getattr(_mcp, "_TASKS_LOCK", None)
        if lock is not None:
            with lock:
                _mcp._TASKS.clear()
        else:                              # pragma: no cover
            _mcp._TASKS.clear()
    except Exception:                      # noqa: BLE001
        pass
    try:
        from vools.actus import vault2 as _vault2
        _vault2._vault2_singleton = None
    except Exception:                      # noqa: BLE001
        pass
    try:
        from vools.actus import security as _security
        _security._scanner = None
    except Exception:                      # noqa: BLE001
        pass


@pytest.fixture(autouse=True)
def reset_globals():
    """用例前后重置进程级单例（顺序无关；xdist 下也不会互相污染）。"""
    _reset_process_globals()
    yield
    _reset_process_globals()
