# -*- coding: utf-8 -*-
"""actus/tests/test_vault_readonly_contracts.py — secret resolver **读路径零写**契约。

背景（第 12 轮残留修复）：`vault2.auth()` 会 UPDATE `last_auth_at` /
`failed_attempts` / `used_codes`；而 `_v2_read_secret()` 此前用 `_v2_session()`
（即 auth）—— `resolve_secret()` 是最热读路径（CLI/MCP `vault get`、`vault list`
逐 key、executor `vault://` 批量解析），**每次读都在偷偷写 db**。
修法：新增 `_v2_readonly_session()`，读路径（resolve / list / resolver_status /
executor 注入）全部切只读；PIN/锁定/机器指纹检查照做，但不做登录副作用。

本文件用 **sha256 + mtime_ns + size 三件套** 快照 `vault2.db`，钉住：
  ① resolve_secret 读成功/读失败都不改 db；
  ② CLI `vault get`（真实子进程）不改 db；
  ③ executor 的 `vault://` 注入不改 db；
  ④ resolver_status 诊断不改 db；
  ⑤ 对照组：write/delete/懒迁移**可以写**（证明流程真的跑起来了，不是"什么都没发生"）；
  ⑥ 锁定身份：只读会话仍检查锁定（读也被拒绝），且检查本身不写 db；
  ⑦ 公开 API：`list_secret_names` 四情形、`delete_secret` 的 v1/v2 语义。

隔离：`tmp_path` + `HOME`/`ACTUS_META_DIR`/`ACTUS_VAULT2_DIR` 全指 tmp；
`ACTUS_VAULT_KEY` 显式设/删；每例重置 vault2 单例与 resolver 缓存。
"""

import hashlib
import json
import os
import subprocess
import sys
import time

import pytest

_ACTUS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VOOLS_ROOT = os.path.join(_ACTUS_ROOT, "vools")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import executor as executor_mod  # noqa: E402
from vools.actus import vault as vault_resolver  # noqa: E402
from vools.actus import vault2 as vault2_mod  # noqa: E402
from vools.actus.model import Action  # noqa: E402
from vools.actus.vault import Vault  # noqa: E402
from vools.actus.vault2 import Vault2  # noqa: E402

_PIN = "123456"


# ---------------------------------------------------------------------------
# 夹具 / 辅助
# ---------------------------------------------------------------------------

class _World(object):
    pass


def _reset_resolver_state():
    """清掉进程内的 resolver 会话/错误/只读缓存与 vault2 单例。"""
    vault_resolver._V2_READONLY_CACHE.clear()
    vault_resolver._V2_SESSION_CACHE.update(
        {'creds': None, 'token': None, 'module': None, 'ts': 0.0})
    vault_resolver._V2_ERROR_CACHE.update(
        {'creds': None, 'ts': 0.0, 'reason': None})
    vault2_mod._vault2_singleton = None


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    v2dir = tmp_path / "vault2"
    for directory in (home, meta, v2dir):
        directory.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_VAULT2_DIR", str(v2dir))
    # file-key 保护：避开 OS keyring 交互，确定性
    monkeypatch.setenv("ACTUS_VAULT2_KEY_PROTECTION", "file-key")
    monkeypatch.setenv("ACTUS_VAULT2_NO_PROMPT", "1")
    # 显式清掉可能继承的密钥/凭据（别依赖环境里有没有）
    for name in ("ACTUS_VAULT_KEY", "ACTUS_VAULT_LAZY_MIGRATE",
                 vault_resolver.V2_IDENTITY_ENV, vault_resolver.V2_MACHINE_ENV,
                 vault_resolver.V2_PIN_ENV):
        monkeypatch.delenv(name, raising=False)

    _reset_resolver_state()

    w = _World()
    w.root = tmp_path
    w.home = home
    w.meta = meta
    w.v2dir = v2dir
    w.db_path = v2dir / "vault2.db"
    return w


def _setup_v2(world, identity="alice", pin=_PIN):
    """在 world 的 v2 库注册身份/机器、写入 db_pw，并把凭据放进环境变量。"""
    vault = Vault2(vault_dir=str(world.v2dir))
    registered = vault.register(identity, pin, security_level="L1")
    assert registered["status"] == "ok", registered
    identity_id = registered["identity_id"]
    machine_id = registered["machine_id"]
    auth = vault.auth(identity_id, machine_id, pin)
    assert auth["status"] == "ok", auth
    assert vault.set_secret(auth["session_token"], "db_pw", "s3cr3t!")["status"] == "ok"

    os.environ[vault_resolver.V2_IDENTITY_ENV] = identity_id
    os.environ[vault_resolver.V2_MACHINE_ENV] = machine_id
    os.environ[vault_resolver.V2_PIN_ENV] = pin
    _reset_resolver_state()
    return {
        "vault": vault,
        "identity_id": identity_id,
        "machine_id": machine_id,
        "pin": pin,
    }


def _snapshot(path):
    """sha256 + mtime_ns + size 三件套（只比 mtime 或只比 size 都不可靠）。"""
    stat = os.stat(str(path))
    with open(str(path), "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size, "sha256": digest}


def _assert_unchanged(world, before, label):
    after = _snapshot(world.db_path)
    assert after == before, "%s 改动了 vault2.db: before=%r after=%r" % (
        label, before, after)


# ===========================================================================
# ① resolve_secret 无写副作用（最重要）
# ===========================================================================

def test_resolve_secret_reads_are_byte_identical(world):
    """退步了会怎样（本轮核心 P1）：读路径改回 `_v2_session()`/`vault2.auth()` ——
    每次 `vault get` / `vault://` 引用都会 UPDATE `last_auth_at`/`failed_attempts`/
    `used_codes`，把最热的**读**变成偷偷的**写**（并发/审计/备份全被污染）。

    断言：读成功、读不存在、重复读多次之后，vault2.db 的
    sha256 + mtime_ns + size **逐字节不变**。

    注意：先等过一秒再读 —— `auth` 的 `last_auth_at` 是**秒级**整数，若读发生在
    与 setup 同一个秒内，即使回归成 auth 也可能写入同值而不改文件（变异检测会漏）。
    """
    _setup_v2(world)
    time.sleep(1.05)          # 让「如果回归成 auth」的 last_auth_at 一定跨秒
    before = _snapshot(world.db_path)

    result = vault_resolver.resolve_secret("db_pw", meta_dir=str(world.meta))
    assert result["status"] == "ok", result
    assert result["value"] == "s3cr3t!"
    assert result["source"] == "v2"

    missing = vault_resolver.resolve_secret("no_such_key", meta_dir=str(world.meta))
    assert missing["status"] == "not_found"
    # 热路径重复读（模拟 CLI list 逐 key / executor 多个 vault://）
    for _ in range(3):
        vault_resolver.resolve_secret("db_pw", meta_dir=str(world.meta))

    _assert_unchanged(world, before, "resolve_secret")


# ===========================================================================
# ② CLI `vault get` 无写副作用（真实子进程）
# ===========================================================================

def test_cli_vault_get_is_read_only(world):
    """退步了会怎样：CLI `vault get` 走 auth 会话 —— 用户每查一次密钥，db 的
    `last_auth_at`/`used_codes` 就被改一次（读操作写盘，无法做只读副本/备份校验）。

    断言：真实子进程 `python -m vools.actus.cli vault get db_pw` → rc=0、
    输出 source='v2'、value 正确；成功读与不存在读之后 db 快照都不变。
    """
    _setup_v2(world)
    before = _snapshot(world.db_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = _VOOLS_ROOT + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.run(
        [sys.executable, "-m", "vools.actus.cli", "vault", "get", "db_pw"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180, env=env, cwd=str(world.root))
    assert proc.returncode == 0, (proc.stdout, proc.stderr[-800:])
    payload = json.loads(proc.stdout)
    assert payload["status"] == "ok"
    assert payload["source"] == "v2"
    assert payload["value"] == "s3cr3t!"

    missing = subprocess.run(
        [sys.executable, "-m", "vools.actus.cli", "vault", "get", "no_such_key"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180, env=env, cwd=str(world.root))
    assert missing.returncode == 1, (missing.stdout, missing.stderr[-800:])

    _assert_unchanged(world, before, "CLI vault get")


# ===========================================================================
# ③ executor 的 `vault://` 注入无写副作用
# ===========================================================================

def test_executor_vault_ref_injection_is_read_only(world):
    """退步了会怎样：动作里写 `vault://KEY` 时，executor 的 secrets 注入走 auth
    会话 —— **每执行一次动作**就写一次 vault db（高频路径，且执行失败也可能已经写脏）。

    断言：直接调用 executor 的注入函数（同一真源），env 里拿到正确明文；
    vault2.db 快照不变；结束后注入的 env 被还原。
    """
    _setup_v2(world)
    action = Action(meta={
        "id": "test.vaultref", "name": "v", "version": "1.0.0",
        "trust": "sandbox", "entry": "main", "platform": "desktop",
        "secrets": [{"env": "DB_PW", "key": "vault://db_pw"}],
    }, path="", sha256="", blocks=[])
    before = _snapshot(world.db_path)
    before_env = executor_mod._env_snapshot()

    try:
        executor_mod._apply_env_injections(
            action, {}, "E1", str(world.root / "artifacts"), False, str(world.meta))
        assert os.environ.get("DB_PW") == "s3cr3t!", "executor 没有注入 vault:// 明文"
    finally:
        executor_mod._env_restore(before_env)

    assert os.environ.get("DB_PW") is None, "注入的 secrets 没有还原到父进程环境外"
    _assert_unchanged(world, before, "executor vault:// 注入")


# ===========================================================================
# ④ resolver_status 无写副作用（诊断更不该写）
# ===========================================================================

def test_resolver_status_is_read_only(world):
    """退步了会怎样：`resolver_status()` 走 auth —— 排障脚本每跑一次诊断就改一次 db，
    而且"诊断会在错误 PIN 时累加 failed_attempts"，可能把用户锁死。

    断言：status 返回 v2_available=True；连调两次 db 快照不变。
    """
    _setup_v2(world)
    before = _snapshot(world.db_path)

    first = vault_resolver.resolver_status()
    second = vault_resolver.resolver_status()

    assert first["v2_available"] is True, first
    assert first["v2_reason"] is None, first
    assert second["v2_available"] is True
    _assert_unchanged(world, before, "resolver_status")


# ===========================================================================
# ⑤ 对照组：写路径确实写（证明流程真的跑起来了）
# ===========================================================================

def test_write_and_delete_paths_really_write(world):
    """退步了会怎样（反向验证）：如果测试环境根本没连上 v2（例如凭据/库没生效），
    "读路径零写"会**因为什么都没发生而假绿**。

    断言：write_secret → ok/source v2 且 db 快照**发生变化**；read 能读到新值；
    delete_secret → ok/deleted_v2=True 且 db 再次变化。
    """
    _setup_v2(world)
    before = _snapshot(world.db_path)

    written = vault_resolver.write_secret("newkey", "newvalue", meta_dir=str(world.meta))
    assert written["status"] == "ok", written
    assert written["source"] == "v2"
    after_write = _snapshot(world.db_path)
    assert after_write != before, "写路径没有真正写 vault2.db（对照组失效）"

    read_back = vault_resolver.resolve_secret("newkey", meta_dir=str(world.meta))
    assert read_back["status"] == "ok" and read_back["value"] == "newvalue"

    deleted = vault_resolver.delete_secret("newkey", meta_dir=str(world.meta))
    assert deleted["status"] == "ok", deleted
    assert deleted["deleted_v2"] is True
    after_delete = _snapshot(world.db_path)
    assert after_delete != after_write, "delete 没有真正写 vault2.db"


# ===========================================================================
# ⑥ 锁定身份：读也拒绝，且检查本身不写 db
# ===========================================================================

def test_locked_identity_rejected_on_read_without_writing(world):
    """退步了会怎样：只读会话为了"不写"跳过锁定检查 → 被锁定的身份仍能读密钥；
    或检查失败时顺手 UPDATE failed_attempts（读也会写）。

    断言：连续错 PIN 锁死身份后，用正确 PIN 读 → 拒绝且原因含「锁定」；
    db 快照（锁定后）在读取前后不变。
    """
    setup = _setup_v2(world)
    vault = setup["vault"]
    second = vault.register("bob", "654321", security_level="L1")
    identity_id, machine_id = second["identity_id"], second["machine_id"]
    for _ in range(vault2_mod.MAX_FAILED_ATTEMPTS):
        vault.auth(identity_id, machine_id, "000000")   # 错 PIN，累加失败次数

    os.environ[vault_resolver.V2_IDENTITY_ENV] = identity_id
    os.environ[vault_resolver.V2_MACHINE_ENV] = machine_id
    os.environ[vault_resolver.V2_PIN_ENV] = "654321"
    _reset_resolver_state()
    before = _snapshot(world.db_path)

    result = vault_resolver.resolve_secret("db_pw", meta_dir=str(world.meta))

    assert result["status"] in ("not_found", "error"), result
    message = str(result.get("message") or "")
    assert "锁定" in message, message
    _assert_unchanged(world, before, "锁定身份读取")


# ===========================================================================
# ⑦ list_secret_names：四种 source/conflict 情形
# ===========================================================================

def test_list_secret_names_sources_and_conflicts(world, monkeypatch):
    """退步了会怎样：v1/v2 合并清单的 source/conflict 口径漂移 —— CLI `vault list`
    会把冲突密钥静默算成一边（用户看到"只有一个值"，实际两库不一致）。

    断言四种情形：
      * 仅 v1 → source='v1'、in_v1=True/in_v2=False；
      * 仅 v2 → source='v2'；
      * 两边同值 → source='v2+v1'、conflict=False；
      * 两边不同 → source='v1+v2'、conflict=True（不静默挑一个）。
    另断言：list 本身不修改 vault2.db。
    """
    _setup_v2(world)
    monkeypatch.setenv("ACTUS_VAULT_KEY", "v1-master-key")
    v1 = Vault(meta_dir=str(world.meta))
    assert v1.set("v1only", "one")["status"] == "ok"
    assert v1.set("both_equal", "same")["status"] == "ok"
    assert v1.set("both_conflict", "aaa")["status"] == "ok"
    assert vault_resolver.write_secret("v2only", "two", meta_dir=str(world.meta))["status"] == "ok"
    assert vault_resolver.write_secret("both_equal", "same", meta_dir=str(world.meta))["status"] == "ok"
    assert vault_resolver.write_secret("both_conflict", "bbb", meta_dir=str(world.meta))["status"] == "ok"

    before = _snapshot(world.db_path)
    listed = vault_resolver.list_secret_names("global", str(world.meta))
    _assert_unchanged(world, before, "list_secret_names")

    assert listed["status"] == "ok"
    assert listed["v2_available"] is True
    rows = {row["key"]: row for row in listed["keys"]}

    assert rows["v1only"]["source"] == "v1"
    assert rows["v1only"]["in_v1"] is True and rows["v1only"]["in_v2"] is False
    assert rows["v2only"]["source"] == "v2"
    assert rows["both_equal"]["source"] == "v2+v1"
    assert rows["both_equal"]["conflict"] is False
    assert rows["both_equal"]["in_v1"] is True and rows["both_equal"]["in_v2"] is True
    assert rows["both_conflict"]["source"] == "v1+v2"
    assert rows["both_conflict"]["conflict"] is True, rows["both_conflict"]


# ===========================================================================
# ⑧ delete_secret：默认只删 v2 / include_v1 才删 v1 / v2 不可用 → failed+hint
# ===========================================================================

def test_delete_secret_v2_only_by_default_then_include_v1(world, monkeypatch):
    """退步了会怎样：默认 delete 顺手删掉 v1 旧库副本（破坏性且不可逆）；
    或 include_v1=True 也不删 v1（迁移收尾做不干净）。

    断言：两边都有同名密钥时，默认 delete → deleted_v2=True、deleted_v1=False、
    v1 仍能读到；重建 v2 后 include_v1=True → 两边都删掉。
    """
    _setup_v2(world)
    monkeypatch.setenv("ACTUS_VAULT_KEY", "v1-master-key")
    v1 = Vault(meta_dir=str(world.meta))
    assert v1.set("shared", "same")["status"] == "ok"
    assert vault_resolver.write_secret("shared", "same", meta_dir=str(world.meta))["status"] == "ok"

    default_delete = vault_resolver.delete_secret("shared", meta_dir=str(world.meta))
    assert default_delete["status"] == "ok", default_delete
    assert default_delete["deleted_v2"] is True
    assert default_delete["deleted_v1"] is False
    assert "include_v1" in default_delete.get("hint", "")
    assert Vault(meta_dir=str(world.meta)).get("shared") == "same", "默认 delete 误删了 v1"

    assert vault_resolver.write_secret("shared", "same", meta_dir=str(world.meta))["status"] == "ok"
    both = vault_resolver.delete_secret("shared", meta_dir=str(world.meta), include_v1=True)
    assert both["status"] == "ok", both
    assert both["deleted_v2"] is True and both["deleted_v1"] is True
    assert Vault(meta_dir=str(world.meta)).get("shared") is None


def test_delete_secret_v2_unavailable_is_failed_with_hint(world):
    """退步了会怎样：v2 不可用时 delete 静默返回 not_found —— 用户以为"本来就没有"，
    实际是 v2 连不上、密钥还在。

    断言：清掉 v2 凭据后 delete → status='failed'、errors 明说 v2 不可用、
    带 hint（默认只删 v2 的说明）。
    """
    _setup_v2(world)
    for name in (vault_resolver.V2_IDENTITY_ENV, vault_resolver.V2_MACHINE_ENV,
                 vault_resolver.V2_PIN_ENV):
        os.environ.pop(name, None)
    _reset_resolver_state()

    result = vault_resolver.delete_secret("db_pw", meta_dir=str(world.meta))

    assert result["status"] == "failed", result
    assert result["errors"], result
    assert "v2 不可用" in result["errors"][0]
    assert result.get("hint")
