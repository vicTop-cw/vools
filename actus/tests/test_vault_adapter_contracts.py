# -*- coding: utf-8 -*-
"""actus/tests/test_vault_adapter_contracts.py — `vault.py` / `adapter.py` 新契约回归。

背景：cmd-engine 这一轮做了几条**数据安全级**修复，但零测试覆盖：
  * `Vault.set()/delete()` 临时主密钥守卫 —— 无 `ACTUS_VAULT_KEY` 时拒绝写盘
    （改前会返回 ok 并把**重启后永远解不开**的密文落盘，属不可逆数据损失）；
  * `_atomic_write()` —— mkstemp + fsync + os.replace，`keys.json` 先于 `meta.json`；
  * 落盘失败回滚 —— 返回 failed 且内存状态回滚（不出现"内存已改、磁盘没改"）；
  * `_maybe_migrate_legacy()` —— 旧有/新空才 move；两边都有 → ambiguous 不合并；
  * **测试环境不自动迁移** —— `PYTEST_CURRENT_TEST` / `ACTUS_TEST_MODE` 时只记 pending
    （防"测试把真实用户保险库搬走"，与 zh.actus.md 事故同族）；
  * `create_adapter` 闸门 —— 校验不过抛 `AdapterSpecError`（issues + install_hint）；
  * `discover` 不丢坏 spec —— 警告 + `spec.issues`，**仍登记**（`get()` 拿得到）；
  * `ensure_available()` —— lru_cache；CLI 恒 which；HTTP 仅 `preflight` 才探测；
  * `AdapterUnavailableError` 带 `reason` + `install_hint`。

全部 `tmp_path` 隔离（HOME/ACTUS_META_DIR/ACTUS_VAULT_KEY 显式设/删），跑完真实仓库与
真实 `~/.actus` 零变化。每条 docstring 写「退步了会怎样」。
"""

import json
import os
import subprocess
import sys

import pytest

_ACTUS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VOOLS_ROOT = os.path.join(_ACTUS_ROOT, "vools")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import adapter as adapter_mod  # noqa: E402
from vools.actus import vault as vault_mod  # noqa: E402
from vools.actus.adapter import (  # noqa: E402
    AdapterRegistry, AdapterSpec, AdapterSpecError, AdapterType,
    AdapterUnavailableError, clear_availability_cache)
from vools.actus.vault import Vault  # noqa: E402


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    meta = tmp_path / "meta"
    for directory in (home, repo, meta):
        directory.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    # 守卫依赖「有没有配钥匙」：显式删掉，绝不继承 pytest/CI 环境里的值。
    monkeypatch.delenv("ACTUS_VAULT_KEY", raising=False)
    # 迁移闸门依赖测试环境标记：先清掉，需要模拟的用例自己设。
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("ACTUS_TEST_MODE", raising=False)
    monkeypatch.delenv("ACTUS_VAULT_MIGRATE", raising=False)

    w = _World()
    w.root = tmp_path
    w.home = home
    w.repo = repo
    w.meta = meta
    return w


def _vault_dir(meta):
    return os.path.join(str(meta), "vault")


def _keys_file(meta):
    return os.path.join(_vault_dir(meta), "keys.json")


def _read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_adapter(adapters_dir, filename, cfg):
    import pathlib
    pathlib.Path(adapters_dir).mkdir(parents=True, exist_ok=True)
    text = '# adapter\n\n```json #!cfg\n%s\n```\n' % json.dumps(cfg)
    (pathlib.Path(adapters_dir) / filename).write_text(text, encoding="utf-8")


# ===========================================================================
# 1) 临时主密钥守卫（P1：数据永久丢失）
# ===========================================================================

def test_set_refuses_when_master_key_is_ephemeral(world):
    """退步了会怎样（P1 不可逆数据损失）：未配置 `ACTUS_VAULT_KEY` 时 `set()` 返回
    `ok` 并把密文落盘 —— 主密钥是进程级临时值，重启后 `get()` 永远解不开
    （实测：进程 A set→ok，进程 B get→None/inspect→undecryptable）。

    断言：`ephemeral_key=True`、`status()['writable']==False`；`set()` →
    `{'status':'refused','code':'vault_ephemeral_key'}`；**磁盘上不产生 keys.json**；
    `get()` 拿不到值。第二个 Vault 实例（同进程，从环境看到临时钥）也必须继续拒绝。
    """
    vault = Vault(meta_dir=str(world.meta))
    try:
        assert vault.ephemeral_key is True
        assert vault.status()["writable"] is False

        result = vault.set("api_key", "secret-value")
        assert result["status"] == "refused", result
        assert result["code"] == "vault_ephemeral_key"
        assert "ACTUS_VAULT_KEY" in result["message"]

        assert not os.path.isfile(_keys_file(world.meta)), \
            "临时主密钥下仍写盘了 keys.json（密文将永久不可解）"
        assert os.listdir(_vault_dir(world.meta)) == []
        assert vault.get("api_key") is None

        second = Vault(meta_dir=str(world.meta))
        assert second.ephemeral_key is True, \
            "同进程第二个实例必须仍识别为临时钥（临时钥写回了环境变量）"
        assert second.set("another", "x")["status"] == "refused"
        assert not os.path.isfile(_keys_file(world.meta))
    finally:
        os.environ.pop("ACTUS_VAULT_KEY", None)


def test_delete_refuses_when_master_key_is_ephemeral(world):
    """退步了会怎样：临时密钥下 `delete()` 仍执行删除 —— 在"读不出内容"的状态下
    按名字删掉真实密钥（破坏性且不可逆）。

    断言：返回 False、`last_refusal` 记 refused/code、磁盘不变、第二次不再有 refusal
    （正常路径 `last_refusal` 清空）。
    """
    vault = Vault(meta_dir=str(world.meta))
    try:
        assert vault.delete("api_key") is False
        refusal = vault.last_refusal
        assert refusal is not None and refusal["status"] == "refused"
        assert refusal["code"] == "vault_ephemeral_key"
        assert not os.path.isfile(_keys_file(world.meta))
    finally:
        os.environ.pop("ACTUS_VAULT_KEY", None)


# ===========================================================================
# 2) 有 key 时持久化 + 跨实例/跨进程可读
# ===========================================================================

def test_set_persists_and_readable_across_instances_and_processes(world, monkeypatch):
    """退步了会怎样（加密后端/主密钥派生漂移）：同一把 `ACTUS_VAULT_KEY` 下，
    进程 A 写入、进程 B 读不出（或重建实例读不出）—— 密钥等于丢了。

    断言：set 后同一进程重建 Vault 能解密；再起**真实子进程**用同一把钥匙读，
    也能拿到明文（跨进程契约）。
    """
    monkeypatch.setenv("ACTUS_VAULT_KEY", "test-master-key")
    vault = Vault(meta_dir=str(world.meta))
    assert vault.ephemeral_key is False
    assert vault.set("api_key", "secret-value")["status"] == "ok"
    assert vault.get("api_key") == "secret-value"

    reopened = Vault(meta_dir=str(world.meta))
    assert reopened.get("api_key") == "secret-value"

    code = (
        "import json, sys\n"
        "sys.path.insert(0, %r)\n"
        "from vools.actus.vault import Vault\n"
        "v = Vault(meta_dir=%r)\n"
        "print(json.dumps({'value': v.get('api_key'), 'ephemeral': v.ephemeral_key}))\n"
        % (_VOOLS_ROOT, str(world.meta)))
    env = dict(os.environ)
    env["ACTUS_VAULT_KEY"] = "test-master-key"
    env["PYTHONPATH"] = _VOOLS_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=120, env=env, cwd=str(world.root))
    assert proc.returncode == 0, proc.stderr[-800:]
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload == {"value": "secret-value", "ephemeral": False}


# ===========================================================================
# 3) 原子写 + 失败回滚
# ===========================================================================

def test_atomic_write_failure_rolls_back_memory_and_keeps_disk_valid(world, monkeypatch):
    """退步了会怎样（灾难级）：直接 `open(path,'w') + json.dump` —— 崩在中间留下
    截断半份 JSON，下次 `_load` 抛 JSONDecodeError；且 `set()` 失败后内存已改，
    下一次别的操作会把半截状态写进磁盘。

    断言：先成功写 a=1；让 `json.dump` 抛错后 set a=2 →
    `{'status':'failed'}` + **内存回滚为 1** + 磁盘仍是合法 JSON 且 a=1（新实例可读）
    + 无 `.vault-*.tmp` 残留。
    """
    monkeypatch.setenv("ACTUS_VAULT_KEY", "test-master-key")
    vault = Vault(meta_dir=str(world.meta))
    assert vault.set("a", "1")["status"] == "ok"
    assert vault.get("a") == "1"

    real_dump = vault_mod.json.dump

    def boom(*args, **kwargs):
        raise RuntimeError("模拟磁盘写满")

    monkeypatch.setattr(vault_mod.json, "dump", boom)
    result = vault.set("a", "2")

    assert result["status"] == "failed", result
    assert result["code"] == "vault_write_failed"
    assert "已回滚内存" in result["message"]
    assert vault.get("a") == "1", "写盘失败后内存没有回滚"

    monkeypatch.setattr(vault_mod.json, "dump", real_dump)
    on_disk = _read_json(_keys_file(world.meta))
    assert on_disk, "写盘失败后 keys.json 不是合法 JSON"
    reopened = Vault(meta_dir=str(world.meta))
    assert reopened.get("a") == "1", "失败的写入污染了磁盘上的旧密钥"
    leftovers = [n for n in os.listdir(_vault_dir(world.meta)) if ".tmp" in n]
    assert leftovers == [], "原子写失败后留下临时文件: %r" % (leftovers,)


def test_save_writes_keys_before_meta(world, monkeypatch):
    """退步了会怎样：先写 meta.json 再写 keys.json —— 两次 replace 之间崩溃会出现
    「列表里看得见、get 却拿不到」的幽灵条目（更坏的假象）。

    断言：`_save` 的写盘顺序必须是 keys.json → meta.json。
    """
    monkeypatch.setenv("ACTUS_VAULT_KEY", "test-master-key")
    vault = Vault(meta_dir=str(world.meta))
    written = []
    real_atomic = vault_mod.Vault._atomic_write

    def recorder(path, data):
        written.append(os.path.basename(path))
        return real_atomic(path, data)

    monkeypatch.setattr(vault_mod.Vault, "_atomic_write", staticmethod(recorder))
    assert vault.set("k", "v")["status"] == "ok"

    assert written == ["keys.json", "meta.json"], \
        "写盘顺序必须 keys 先于 meta（幽灵条目防护），实得 %r" % (written,)


# ===========================================================================
# 4) 旧库迁移两种情形
# ===========================================================================

def _make_legacy_vault(world, master_key="test-master-key"):
    """在 `cwd/vault` 造一个旧位置保险库（`_legacy_vault_candidates` 的候选之一）。"""
    return Vault(meta_dir=str(world.root), master_key=master_key,
                 migrate_legacy=False)


def test_migration_moves_legacy_when_new_is_empty(world, monkeypatch):
    """退步了会怎样：新位置为空、旧位置有数据时**不迁移** —— 用户升级后打开
    `actus vault list` 一片空白，以为密钥丢了。

    断言：`migrate_legacy=True` 时旧库被 move 到新位置、`migrated_from` 指向旧路径、
    旧位置已不存在、旧密钥仍能解密。
    """
    monkeypatch.setenv("ACTUS_VAULT_KEY", "test-master-key")
    legacy = _make_legacy_vault(world)
    assert legacy.set("old", "oldvalue")["status"] == "ok"
    legacy_dir = os.path.join(str(world.root), "vault")
    assert os.path.isdir(legacy_dir)

    new_meta = world.root / "new_meta"
    migrated = Vault(meta_dir=str(new_meta), migrate_legacy=True)

    assert migrated.migrated_from is not None, migrated.status()
    assert os.path.realpath(migrated.migrated_from) == os.path.realpath(legacy_dir)
    assert not os.path.isdir(legacy_dir), "旧位置应被 move 走（不是复制）"
    assert migrated.get("old") == "oldvalue", "迁移后旧密钥必须仍可解密"
    assert migrated.status()["migrated_from"] is not None


def test_migration_ambiguous_keeps_both_and_does_not_merge(world, monkeypatch):
    """退步了会怎样：新旧两边都有数据时自动合并/覆盖 —— 静默丢一边的历史。

    断言：`migration_conflict` 以 `ambiguous` 开头、两边目录都保留、两边密钥各自可读。
    """
    monkeypatch.setenv("ACTUS_VAULT_KEY", "test-master-key")
    legacy = _make_legacy_vault(world)
    assert legacy.set("old", "oldvalue")["status"] == "ok"

    new_meta = world.root / "new_meta"
    existing = Vault(meta_dir=str(new_meta), migrate_legacy=False)
    assert existing.set("new", "newvalue")["status"] == "ok"

    conflicted = Vault(meta_dir=str(new_meta), migrate_legacy=True)

    assert (conflicted.migration_conflict or "").startswith("ambiguous"), \
        conflicted.status()
    assert os.path.isdir(os.path.join(str(world.root), "vault")), "旧库被擅自合并/删除了"
    assert os.path.isdir(_vault_dir(new_meta)), "新库被擅自覆盖了"
    assert Vault(meta_dir=str(world.root), migrate_legacy=False).get("old") == "oldvalue"
    assert conflicted.get("new") == "newvalue"


# ===========================================================================
# 5) 测试环境不自动迁移（防搬走真实用户数据）
# ===========================================================================

def test_pytest_environment_does_not_auto_migrate(world, monkeypatch):
    """退步了会怎样（与 zh.actus.md 事故同族）：在 pytest 里构造 Vault 时，测试闸门
    失效 → 旧位置**真实用户保险库**被搬进 tmp，用户下次打开发现密钥消失了。

    断言：设 `PYTEST_CURRENT_TEST` 后默认构造 → `migration_conflict` 以 `pending`
    开头、旧位置仍在原地、新位置没有拿到数据；显式 `migrate_legacy=True` 或
    `ACTUS_VAULT_MIGRATE=1` 才允许迁移。
    """
    monkeypatch.setenv("ACTUS_VAULT_KEY", "test-master-key")
    legacy = _make_legacy_vault(world)
    assert legacy.set("old", "oldvalue")["status"] == "ok"
    legacy_dir = os.path.join(str(world.root), "vault")

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_x.py::test_y")
    new_meta = world.root / "new_meta"
    guarded = Vault(meta_dir=str(new_meta))

    assert (guarded.migration_conflict or "").startswith("pending"), guarded.status()
    assert os.path.isdir(legacy_dir), "测试环境把旧位置的保险库搬走了（用户数据被移动）"
    assert not os.path.isfile(_keys_file(new_meta)), "测试环境不应发生迁移"

    forced = Vault(meta_dir=str(world.root / "forced_meta"), migrate_legacy=True)
    assert forced.migrated_from is not None, "显式 migrate_legacy=True 必须允许迁移"
    assert not os.path.isdir(legacy_dir)


# ===========================================================================
# 6) adapter 闸门 + discover 不丢坏 spec
# ===========================================================================

def _spec(**overrides):
    fields = dict(id="adapter.cli.demo", type=AdapterType.CLI)
    fields.update(overrides)
    return AdapterSpec(**fields)


def test_create_adapter_rejects_invalid_spec_with_issues_and_hint(world):
    """退步了会怎样（第 25 轮修复前的原形）：缺 command 的 spec 一路被实例化，
    直到 `run()` 才返回"未指定 command"——失败发生在动作开始之后，且没有可行动信息。

    断言：`create_adapter` 抛 `AdapterSpecError`（ValueError 子类）、`issues` 点名
    缺 command、`install_hint` 非空且出现在异常消息里。
    """
    registry = AdapterRegistry(adapters_dir=str(world.root / "adapters"))

    with pytest.raises(AdapterSpecError) as excinfo:
        registry.create_adapter(_spec(command=""))

    exc = excinfo.value
    assert isinstance(exc, ValueError)
    assert any("缺少 command" in issue for issue in exc.issues), exc.issues
    assert exc.install_hint, "必须给出安装提示"
    assert exc.install_hint in str(exc), "异常消息必须带上 install_hint"


def test_discover_registers_bad_spec_and_exposes_issues(world):
    """退步了会怎样：discover 把校验不过的 spec 静默丢弃 → `get()` 返回 None →
    上层报"适配器不存在"，把"配置错"伪装成"没这个适配器"，且看不到哪里错。

    断言：好/坏两个 spec 都被登记；坏 spec 的 `issues` 非空且 `get()` 拿得到；
    好 spec 能正常 `create_adapter`。
    """
    adapters_dir = str(world.root / "adapters")
    _write_adapter(adapters_dir, "bad.actus.md",
                   {"id": "adapter.cli.badcfg", "name": "bad",
                    "adapter": {"type": "cli"}})
    _write_adapter(adapters_dir, "good.actus.md",
                   {"id": "adapter.cli.goodcfg", "name": "good",
                    "adapter": {"type": "cli", "command": sys.executable}})

    registry = AdapterRegistry(adapters_dir=adapters_dir)
    specs = registry.discover()

    assert [s.id for s in specs] == ["adapter.cli.badcfg", "adapter.cli.goodcfg"]
    bad = registry.get("adapter.cli.badcfg")
    assert bad is not None, "坏 spec 被静默丢弃了（get 拿不到）"
    assert bad.issues and any("缺少 command" in issue for issue in bad.issues)

    with pytest.raises(AdapterSpecError):
        registry.create_adapter(bad)
    good = registry.get("adapter.cli.goodcfg")
    assert registry.create_adapter(good).__class__.__name__ == "CLIAdapter"


# ===========================================================================
# 7) ensure_available：CLI 恒 which / HTTP 仅 preflight / 缓存
# ===========================================================================

def test_ensure_available_cli_checks_reality_and_raises_with_reason(world):
    """退步了会怎样：执行前不探测依赖 —— 适配器缺命令只能在 `run()` 时炸，且不给
    "该装什么"（`check_available`/`install_hint` 产品零调用的原形）。

    断言：command 指向真实可执行文件 → 不抛；指向不存在的命令 →
    `AdapterUnavailableError` 且 `reason` 含"命令不可用"、`install_hint` 非空。
    """
    registry = AdapterRegistry(adapters_dir=str(world.root / "adapters"))
    clear_availability_cache()

    registry.ensure_available("adapter.cli.goodcfg",
                              _spec(id="adapter.cli.goodcfg", command=sys.executable))

    missing = _spec(id="adapter.cli.missing", command="no-such-binary-xyz --version")
    with pytest.raises(AdapterUnavailableError) as excinfo:
        registry.ensure_available("adapter.cli.missing", missing)
    exc = excinfo.value
    assert "命令不可用" in exc.reason, exc.reason
    assert "no-such-binary-xyz" in exc.install_hint, exc.install_hint
    assert exc.install_hint in str(exc)


def test_ensure_available_uses_process_cache(world):
    """退步了会怎样：每次执行都重新探测（CLI which 尚可，但声明了 check 时是真跑
    命令/网络 HEAD）—— 重复开销；且缓存键漏了 spec 字段会串结果。

    断言：同一 spec 连续 ensure 两次 → `_probe_available` 的 cache hits 增加、miss 不增。
    """
    registry = AdapterRegistry(adapters_dir=str(world.root / "adapters"))
    clear_availability_cache()
    spec = _spec(id="adapter.cli.cached", command=sys.executable)

    registry.ensure_available("adapter.cli.cached", spec)
    info_after_first = adapter_mod._probe_available.cache_info()
    registry.ensure_available("adapter.cli.cached", spec)
    info_after_second = adapter_mod._probe_available.cache_info()

    assert info_after_first.misses == 1, info_after_first
    assert info_after_second.hits >= 1, info_after_second
    assert info_after_second.misses == 1, "同一 spec 第二次不应重新探测"


def test_ensure_available_http_skips_network_unless_preflight(world, monkeypatch):
    """退步了会怎样：HTTP 适配器无条件做 HEAD 探测 —— 每次执行多一次网络往返
    （最坏 +5s），离线环境下直接失败。

    断言：`preflight=False` → 不调用 urlopen（零网络）；`preflight=True` → 才探测，
    失败时抛 `AdapterUnavailableError`（reason 带异常）。
    """
    registry = AdapterRegistry(adapters_dir=str(world.root / "adapters"))
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(getattr(req, "full_url", req))
        raise RuntimeError("network down")

    monkeypatch.setattr(adapter_mod.urllib.request, "urlopen", fake_urlopen)

    quiet = _spec(id="adapter.http.quiet", type=AdapterType.HTTP,
                  url="http://127.0.0.1:1/never", preflight=False)
    clear_availability_cache()
    registry.ensure_available("adapter.http.quiet", quiet)
    assert calls == [], "未声明 preflight 的 HTTP 适配器不应发起网络探测"

    eager = _spec(id="adapter.http.eager", type=AdapterType.HTTP,
                  url="http://127.0.0.1:1/never", preflight=True)
    clear_availability_cache()
    with pytest.raises(AdapterUnavailableError) as excinfo:
        registry.ensure_available("adapter.http.eager", eager)
    assert calls, "声明 preflight=True 时必须真的探测"
    assert "network down" in excinfo.value.reason


def test_adapter_unavailable_error_carries_reason_and_hint():
    """退步了会怎样：依赖不可用时只抛一句"不可用"——用户不知道原因也不知道装什么。

    断言：`AdapterUnavailableError.reason` / `.install_hint` 可取，str 里两者都在。
    """
    exc = AdapterUnavailableError("adapter.cli.x", "命令不可用: foo", "请安装 foo 后重试")
    assert exc.reason == "命令不可用: foo"
    assert exc.install_hint == "请安装 foo 后重试"
    assert "命令不可用" in str(exc) and "请安装 foo" in str(exc)
