# -*- coding: utf-8 -*-
"""actus/tests/test_registry_omega_contracts.py — registry / omega 第 18 轮新契约回归。

背景：cmd-polish 这一轮在 `registry.py` / `omega_strong.py` 上做了一批**契约级修复**，
每一条都改变了对调用方的承诺，但都没有回归测试：
  * `write_index` 改 tmp + `os.replace` —— 写失败不破坏旧索引；
  * `load_from_file` 损坏不抛 —— 返回 `{"actions": [], "corrupt": True, "problems": {...}}`；
  * `load_from_repo` 损坏/陈旧 → 内存重建、不落盘、带 `rebuilt_from_memory` / `stale_index`；
  * `registry validate` 改走 `validate_entry()` —— 逐项收集**全部**问题、rc=1；
  * `_verify_signature_fallback` fail-closed（无 cryptography 时签名条目一律 False）；
  * `_resolve_entry_path` 拒绝对路径/`..` —— 越界条目进 `problems`、不进内存；
  * `record_installation` 原子写 + `manifest_dir`/`ACTUS_INSTALLED_DIR` 可配；
  * `omega_strong._validate_task_id` / `_ledger_path` —— 4 种逃逸全拒；
  * 账本损坏 → `.corrupt-<ts>` 备份 + **粘性拒写**；
  * `check_record` 必须 `cmd` + `exit_code`（`{'ok': True}` 不再放行）；
  * `_ledger_lock` 并发读改写不丢记录；
  * `filter_by_quality(repo_dir)` 必填（缺 → ValueError，不返回 `[]`）；
  * `check_gate` datetime 新鲜度（跨时区正确）。

本文件用 `tmp_path` + 隔离 HOME/ACTUS_META_DIR/ACTUS_INSTALLED_DIR 覆盖这些契约；
每条 docstring 写「退步了会怎样」。
"""

import json
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import cli  # noqa: E402
from vools.actus import omega_strong as omega  # noqa: E402
from vools.actus import registry as registry_mod  # noqa: E402
from vools.actus.errors import ActionError  # noqa: E402
from vools.actus.registry import ActionRegistry, RegistryEntry  # noqa: E402

_ACTION_TEXT = """# Demo

```json #!cfg
{"id": "myapp.demo", "name": "Demo", "version": "1.0.0",
 "description": "demo", "trust": "sandbox"}
```

```python #!run tag=main
print("hi")
```
"""


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    cache = tmp_path / "cache"
    repo = tmp_path / "repo"
    for directory in (home, meta, cache, repo / "actions"):
        directory.mkdir(parents=True)
    (repo / "actions" / "demo.actus.md").write_text(_ACTION_TEXT, encoding="utf-8")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.delenv("ACTUS_INSTALLED_DIR", raising=False)

    w = _World()
    w.root = tmp_path
    w.home = home
    w.meta = meta
    w.cache = cache
    w.repo = repo
    w.action_file = repo / "actions" / "demo.actus.md"
    w.index_path = repo / ".actus.registry.json"
    w.registry = ActionRegistry(cache_dir=str(cache))
    return w


def _read(path):
    with open(str(path), "rb") as handle:
        return handle.read()


def _make_entry(**overrides):
    fields = dict(id="myapp.demo", name="Demo", version="1.0.0", description="d",
                  category="c", path="actions/demo.actus.md", author="a", tags=[],
                  checksum="")
    fields.update(overrides)
    return RegistryEntry(**fields)


# ===========================================================================
# 1) write_index 原子性（含 replace 失败时清理 tmp）
# ===========================================================================

def test_write_index_atomic_on_replace_failure(world, monkeypatch):
    """退步了会怎样（P1 非原子）：`write_index` 改回 `open(repo_dir, 'w')` 先截断原文件
    再 dump —— 写入中途失败/进程被杀会把**原本有效的索引**清成空/半截，search/install
    永久坏掉（只能手删）。这里让 **os.replace 失败**（tmp 写成功、替换失败）：旧索引
    必须逐字节保留，且临时文件必须清理干净（不能留 .tmp 残渣）。
    """
    world.registry.build_from_directory(str(world.repo), write=True)
    original = _read(world.index_path)

    def boom(*args, **kwargs):
        raise OSError("模拟 os.replace 失败（磁盘/权限）")

    monkeypatch.setattr(registry_mod.os, "replace", boom)
    with pytest.raises(OSError):
        world.registry.write_index({"name": "new", "actions": []}, str(world.repo))

    assert _read(world.index_path) == original, "失败的写入破坏了旧索引（非原子）"
    leftovers = [name for name in os.listdir(str(world.repo)) if ".tmp" in name]
    assert leftovers == [], "写入失败后留下临时文件: %r" % (leftovers,)
    # 旧索引仍然可读（不是半截 JSON）
    loaded = world.registry.load_from_file(str(world.index_path))
    assert loaded.get("corrupt") is None
    assert [e["id"] for e in loaded["actions"]] == ["myapp.demo"]


# ===========================================================================
# 2) 损坏索引：不抛 + 明确信号；load_from_repo 内存重建且不落盘
# ===========================================================================

def test_load_from_file_corrupt_returns_signal_not_raises(world):
    """退步了会怎样（P1 损坏不设防）：损坏索引让 `load_from_file` 直接抛
    JSONDecodeError 穿透到 CLI（`search`/`validate`/`install` 崩栈），调用方无从
    得知"索引坏了"。

    断言：返回 `actions=[]`、`corrupt=True`、`problems` 里带损坏原因；顶层非对象
    （如 `[]`）同样按 corrupt 处理。
    """
    world.index_path.write_text("{ this is not json", encoding="utf-8")
    broken = world.registry.load_from_file(str(world.index_path))
    assert broken["actions"] == []
    assert broken["corrupt"] is True
    assert broken["problems"], "损坏索引必须带明确信号（problems）"
    reason = list(broken["problems"].values())[0]
    assert "index corrupt" in reason and "JSONDecodeError" in reason

    world.index_path.write_text("[1, 2, 3]", encoding="utf-8")
    not_object = world.registry.load_from_file(str(world.index_path))
    assert not_object["corrupt"] is True
    assert not_object["problems"], not_object


def test_load_from_repo_corrupt_rebuilds_in_memory_without_touching_file(world):
    """退步了会怎样（P1）：损坏索引只报错不重建 → search/install 在索引坏掉后
    永久不可用；或重建时顺手写盘 → 只读查询悄悄改了用户仓库状态。

    断言：损坏索引下 `load_from_repo` 返回 `rebuilt_from_memory=True` + 能从磁盘
    重建出真实动作；仓库里的索引文件**逐字节不变**（读语义不落盘）。
    """
    world.index_path.write_text("{ broken", encoding="utf-8")
    before = _read(world.index_path)

    rebuilt = world.registry.load_from_repo(str(world.repo))

    assert rebuilt.get("rebuilt_from_memory") is True, rebuilt
    assert [e["id"] for e in rebuilt["actions"]] == ["myapp.demo"]
    assert rebuilt.get("problems"), "重建结果应保留原索引的 problems 诊断"
    assert _read(world.index_path) == before, "load_from_repo 是读语义，不得改写索引"


def test_load_from_repo_stale_index_rebuilds_in_memory(world):
    """退步了会怎样（P2 陈旧索引）：索引与磁盘不一致（动作文件比索引新/被删/索引空
    但磁盘有动作）时还"无声信索引"，向调用方返回幽灵条目或漏掉真实动作。

    断言：把动作文件 mtime 推到索引之后 → `stale_index=True`、动作仍在结果里、
    索引文件不变；删掉动作文件同样触发 stale 重建。
    """
    world.registry.build_from_directory(str(world.repo), write=True)
    before = _read(world.index_path)

    future = time.time() + 10
    os.utime(str(world.action_file), (future, future))
    stale = world.registry.load_from_repo(str(world.repo))
    assert stale.get("stale_index") is True, stale
    assert [e["id"] for e in stale["actions"]] == ["myapp.demo"]
    assert _read(world.index_path) == before, "陈旧重建不得改写索引"

    os.remove(str(world.action_file))
    rebuilt = world.registry.load_from_repo(str(world.repo))
    assert rebuilt.get("stale_index") is True, rebuilt
    assert rebuilt["actions"] == [], "动作文件已删，陈旧索引不能再返回幽灵条目"


# ===========================================================================
# 3) `registry validate` 真校验（逐项收集全部问题、rc=1）
# ===========================================================================

def test_registry_validate_cli_reports_each_problem(world, capsys):
    """退步了会怎样（P1 假校验）：CLI 改回"只数 id 个数"——实测 id 格式非法 /
    version 非 semver / 文件不存在 / checksum 不匹配的条目照样报
    "✅ 校验通过 1/1"、rc=0。

    断言：2 个条目共 5 项问题 → rc=1，输出点名**每一项**（id 格式 / version /
    checksum / 文件缺失 / 签名失败）以及 "2/2 个动作无效"。
    """
    index = {
        "name": "repo", "version": "1.0.0",
        "actions": [
            {"id": "BAD ID", "name": "x", "version": "1.0", "description": "",
             "category": "c", "path": "actions/demo.actus.md", "author": "a",
             "tags": [], "checksum": "deadbeef"},
            {"id": "myapp.ok", "name": "ok", "version": "2.0.0", "description": "",
             "category": "c", "path": "actions/missing.actus.md", "author": "a",
             "tags": [], "checksum": "", "signature": "missing.sig"},
        ],
    }
    index_path = world.repo / ".actus.registry.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")

    rc = cli.main(["registry", "validate", "--index", str(index_path)])
    out = capsys.readouterr().out

    assert rc == 1, out
    assert "注册表校验失败" in out
    for fragment in ("Invalid action ID format: BAD ID",
                     "Invalid version format: 1.0",
                     "Checksum mismatch for BAD ID",
                     "Action file not found: actions/missing.actus.md",
                     "Signature verification failed for myapp.ok"):
        assert fragment in out, "输出没有点名问题 %r:\n%s" % (fragment, out)
    assert "2/2 个动作无效" in out


def test_registry_validate_cli_rejects_corrupt_index_with_problems(world, capsys):
    """退步了会怎样：损坏索引被当成"0 个动作"静默通过（rc=0）。

    断言：损坏索引 → rc=1 且输出 "索引损坏或含非法条目"。
    """
    index_path = world.repo / ".actus.registry.json"
    index_path.write_text("{ broken", encoding="utf-8")

    rc = cli.main(["registry", "validate", "--index", str(index_path)])
    out = capsys.readouterr().out

    assert rc == 1
    assert "索引损坏或含非法条目" in out


# ===========================================================================
# 4) `_resolve_entry_path` 拒绝越界路径（绝对路径 / `..`）
# ===========================================================================

def test_resolve_entry_path_rejects_absolute_and_parent_escapes(world):
    """退步了会怎样（P1 越界读）：`os.path.join(repo_dir, entry.path)` 遇到绝对路径会
    **丢弃 repo_dir**，恶意/损坏索引能让质量分级读到 HOME 下任意文件；`..` 同理。

    断言：绝对路径 / `../outside` / 空路径 → None；正常相对路径 → 解析到仓库内真实文件。
    """
    outside = str(world.root / "outside.md")
    assert world.registry._resolve_entry_path(str(world.repo), outside) is None
    assert world.registry._resolve_entry_path(str(world.repo), "../outside.md") is None
    assert world.registry._resolve_entry_path(str(world.repo), "") is None

    ok = world.registry._resolve_entry_path(str(world.repo), "actions/demo.actus.md")
    assert ok is not None
    assert os.path.realpath(ok) == os.path.realpath(str(world.action_file))


def test_load_from_file_skips_escaping_entries_with_problems(world):
    """退步了会怎样（P1）：越界条目被静默加载进内存（`get()` 能取到）→ 后续
    checksum/质量分级按恶意 path 读仓库外文件。

    断言：绝对路径与 `../` 条目都进 `problems`、不进内存（`get()` 返回 None），
    且不会把整个索引判 corrupt（其它合法条目仍可用）。
    """
    index = {
        "name": "repo", "version": "1.0.0",
        "actions": [
            _make_entry(id="evil.abs", path=str(world.root / "outside.md")).to_dict(),
            _make_entry(id="evil.rel", path="../outside.md").to_dict(),
        ],
    }
    index_path = world.root / "evil.registry.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")

    loaded = world.registry.load_from_file(str(index_path))

    problems = loaded.get("problems") or {}
    assert "evil.abs" in problems and "evil.rel" in problems, problems
    assert world.registry.get("evil.abs") is None
    assert world.registry.get("evil.rel") is None
    assert loaded.get("corrupt") is None, "单条目非法不应把整个索引判损坏"


# ===========================================================================
# 5) `_verify_signature_fallback` fail-closed
# ===========================================================================

def test_verify_signature_fallback_is_fail_closed(world):
    """退步了会怎样（P2 假验签）：无 cryptography 时用 `sig.message == checksum`
    冒充验签 —— 手写 `{"message": "<公开 checksum>", "signature": "ZmFrZQ=="}` 就能过。

    断言：有签名条目（哪怕 trust=trusted）→ False；无签名 community → True；
    无签名 trusted → False（与主路径一致，只有 community 放行）。
    """
    signed_trusted = _make_entry(id="a.b", signature="x.sig", trust_level="trusted")
    unsigned_community = _make_entry(id="c.d", trust_level="community")
    unsigned_trusted = _make_entry(id="e.f", trust_level="trusted")

    assert world.registry._verify_signature_fallback(
        signed_trusted, str(world.repo)) is False, "有签名但无法验签必须 fail-closed"
    assert world.registry._verify_signature_fallback(
        unsigned_community, str(world.repo)) is True
    assert world.registry._verify_signature_fallback(
        unsigned_trusted, str(world.repo)) is False
    assert any("fail-closed" in w for w in world.registry.warnings)


# ===========================================================================
# 6) record_installation：manifest_dir 可配 + 默认契约 + 原子写
# ===========================================================================

def test_record_installation_manifest_dir_env_and_default(world, monkeypatch):
    """退步了会怎样（P2 无视 cache_dir）：清单目录写死 `~/.actus/installed` ——
    嵌入式/测试传了隔离 cache_dir 仍污染真实 HOME；或反过来默认值被改掉（破坏既有契约）。

    断言：不设 env 时默认仍是 `~/.actus/installed`；`ACTUS_INSTALLED_DIR` 可覆盖；
    显式 `manifest_dir=` 优先级最高。
    """
    default_reg = ActionRegistry(cache_dir=str(world.cache))
    assert default_reg.manifest_dir == os.path.join(str(world.home), ".actus", "installed")

    env_dir = str(world.root / "env_installed")
    monkeypatch.setenv("ACTUS_INSTALLED_DIR", env_dir)
    env_reg = ActionRegistry(cache_dir=str(world.cache))
    assert env_reg.manifest_dir == env_dir

    explicit = str(world.root / "explicit_installed")
    explicit_reg = ActionRegistry(cache_dir=str(world.cache), manifest_dir=explicit)
    assert explicit_reg.manifest_dir == explicit


def test_record_installation_is_atomic_and_lands_in_manifest_dir(world, monkeypatch):
    """退步了会怎样：清单直接 `open(...,'w')` 写 —— 写一半失败/中断留下半截 JSON，
    下次 `list_installed` 崩；或清单没落到指定 manifest_dir（污染真实 HOME）。

    断言：清单写入 manifest_dir；再次写入前把 `json.dump` 改坏 → 旧清单**逐字节保留**，
    无 `.tmp` 残留，且清单里 actions 与索引一致。
    """
    manifest_dir = world.root / "installed"
    reg = ActionRegistry(cache_dir=str(world.cache), manifest_dir=str(manifest_dir))
    manifest = reg.record_installation("https://example.invalid/owner/repo.git",
                                       str(world.repo))
    manifest_path = manifest_dir / (reg._url_to_cache_key(
        "https://example.invalid/owner/repo.git") + ".json")
    assert manifest_path.is_file(), "清单没有落到指定 manifest_dir"
    original = _read(manifest_path)
    assert manifest["actions"] and manifest["actions"][0]["id"] == "myapp.demo"

    real_dump = registry_mod.json.dump
    monkeypatch.setattr(registry_mod.json, "dump",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    try:
        with pytest.raises(RuntimeError):
            reg.record_installation("https://example.invalid/owner/repo.git",
                                    str(world.repo))
    finally:
        registry_mod.json.dump = real_dump

    assert _read(manifest_path) == original, "失败的清单写入破坏了旧清单（非原子）"
    leftovers = [name for name in os.listdir(str(manifest_dir)) if ".tmp" in name]
    assert leftovers == [], "清单写入失败后留下临时文件: %r" % (leftovers,)


# ===========================================================================
# 7) filter_by_quality(repo_dir) 必填
# ===========================================================================

def test_filter_by_quality_requires_repo_dir(world):
    """退步了会怎样（"查不到"伪装成"没有"）：repo_dir 缺省时拿 cache_dir 上一级当
    仓库根（默认 `~`，几乎永远错）→ 所有条目解析失败 → 静默返回 []，调用方以为
    "没有高质量动作"。

    断言：缺 repo_dir → ValueError 且消息点名 repo_dir；未知等级也 ValueError。
    """
    world.registry.load_from_repo(str(world.repo))

    with pytest.raises(ValueError) as excinfo:
        world.registry.filter_by_quality("gold")
    assert "repo_dir" in str(excinfo.value)

    with pytest.raises(ValueError):
        world.registry.filter_by_quality("nonsense", repo_dir=str(world.repo))


# ===========================================================================
# 8) omega_strong：task_id 逃逸全拒（_validate_task_id + _ledger_path）
# ===========================================================================

@pytest.mark.parametrize("bad_id", ["../../x", "a/b", "", "C:\\Users\\me\\x"])
def test_validate_task_id_rejects_escapes(world, bad_id):
    """退步了会怎样（P1 任意文件读写）：task_id 直接拼进账本路径 ——
    `../../escaped` 能把账本写出 `_meta/omega_strong/` 之外，绝对路径更无视
    ACTUS_META_DIR 写任意 `<abs>.json`（task_id 来自 CLI/MCP 输入，不可信）。

    断言：4 种逃逸（相对穿越 / 分隔符 / 空 / 绝对路径）都被
    `_validate_task_id` 与 `_ledger_path` 以 param_invalid 拒绝；合法 id 正常通过。
    """
    with pytest.raises(ActionError) as excinfo:
        omega._validate_task_id(bad_id)
    assert excinfo.value.code == "param_invalid"

    with pytest.raises(ActionError) as excinfo:
        omega._ledger_path(bad_id, meta_dir=str(world.meta))
    assert excinfo.value.code == "param_invalid"

    # 合法 id 仍正常工作
    assert omega._validate_task_id("task-legal_1") == "task-legal_1"
    legal_path = omega._ledger_path("task-legal_1", meta_dir=str(world.meta))
    assert legal_path.endswith("task-legal_1.json")
    assert os.path.realpath(legal_path).startswith(
        os.path.realpath(os.path.join(str(world.meta), "omega_strong")))


# ===========================================================================
# 9) check_record 必须 cmd + exit_code（{'ok': True} 不放行）
# ===========================================================================

@pytest.mark.parametrize("bad_check", [
    {"ok": True},
    {"cmd": "true"},
    {"cmd": "true", "exit_code": "0"},
    {"cmd": "", "exit_code": 0},
    {"exit_code": 0},
])
def test_check_record_rejects_incomplete_check(world, bad_check):
    """退步了会怎样（P2 假通过）：门禁状态由调用方 `check['ok']` 直接决定 ——
    实测 `check_record({'ok': True})` 就能记成 passed 并让 check_gate 放行，
    记录里连 cmd/exit_code 都没有（"不跑命令即过门禁"）。

    断言：缺 cmd / 缺整数 exit_code / 类型不对 → param_invalid，不写任何记录。
    """
    oms = omega.OmegaStrong("task-check", meta_dir=str(world.meta))
    with pytest.raises(ActionError) as excinfo:
        oms.check_record(bad_check)
    assert excinfo.value.code == "param_invalid"

    assert oms.records(omega.T_CHECK) == [], "非法 check 不应留下记录"


def test_check_record_derives_status_from_exit_code_only(world):
    """退步了会怎样：`ok` 字段能覆盖 exit_code（`{'ok': True, 'exit_code': 1}`
    仍算 passed），门禁被假数据放行。

    断言：exit_code=0 → status=passed；exit_code=1 即便 ok=True 也 → failed；
    记录内容带 cmd/exit_code 且**不含** ok/status 字段。
    """
    oms = omega.OmegaStrong("task-status", meta_dir=str(world.meta))

    passed = oms.check_record({"cmd": "true", "exit_code": 0, "ok": False})
    assert passed["status"] == "passed"
    failed = oms.check_record({"cmd": "false", "exit_code": 1, "ok": True})
    assert failed["status"] == "failed", "ok=True 不得覆盖 exit_code=1"

    recs = oms.records(omega.T_CHECK)
    assert len(recs) == 2
    payloads = [json.loads(r["content"]) for r in recs]
    assert payloads[0]["cmd"] == "true" and payloads[0]["exit_code"] == 0
    assert "ok" not in payloads[1] and "status" not in payloads[1]


# ===========================================================================
# 10) 账本损坏：备份 + 粘性拒写
# ===========================================================================

def test_corrupt_ledger_backup_and_sticky_refusal(world):
    """退步了会怎样（P2 静默清空）：损坏账本被当成"没有记录" -> 下一次 append
    落盘把原历史（approved 语料/复验记录）覆盖掉，且用户毫无感知。

    断言：损坏 → `load_ledger` 返回 corrupt=True 且原文件被改名为 `.corrupt-<ts>`；
    写路径 fail-closed（check_record 抛 internal 拒写）；备份未删除前**持续** corrupt；
    删掉备份后恢复可写（记录从空账本重新开始）。
    """
    ledger_dir = world.meta / "omega_strong"
    ledger_dir.mkdir(parents=True)
    ledger_path = ledger_dir / "task-corrupt.json"
    ledger_path.write_text("{ broken ledger", encoding="utf-8")
    original_text = ledger_path.read_text(encoding="utf-8")

    broken = omega.load_ledger("task-corrupt", meta_dir=str(world.meta))
    assert broken["corrupt"] is True
    backup = broken.get("corrupt_backup")
    assert backup and os.path.isfile(backup), broken
    with open(backup, "r", encoding="utf-8") as handle:
        assert handle.read() == original_text, "备份必须是原文件内容"

    oms = omega.OmegaStrong("task-corrupt", meta_dir=str(world.meta))
    with pytest.raises(ActionError) as excinfo:
        oms.check_record({"cmd": "true", "exit_code": 0})
    assert excinfo.value.code == "internal"

    assert omega.load_ledger("task-corrupt", meta_dir=str(world.meta))["corrupt"] is True, \
        "存在 .corrupt-* 备份时必须持续拒绝（粘性），不能悄悄重建空账本"

    os.remove(backup)
    clean = omega.load_ledger("task-corrupt", meta_dir=str(world.meta))
    assert clean.get("corrupt") is None, clean
    oms.check_record({"cmd": "true", "exit_code": 0})
    assert len(oms.records(omega.T_CHECK)) == 1, "人工清理备份后应恢复可写"


# ===========================================================================
# 11) _ledger_lock 并发：20 线程 append 全保留
# ===========================================================================

def test_concurrent_ledger_appends_keep_all_records(world):
    """退步了会怎样（P2 并发丢更新）：`_append` 是裸 read-modify-write ——
    两个线程各自 load→append→save，后写者覆盖先写者（实测记录消失）。

    断言：先写 1 条种子记录，再 20 线程各 append 唯一 id → 账本最终 21 条、
    id 集合完整（无丢失、无覆盖）。
    """
    oms = omega.OmegaStrong("task-concurrent", meta_dir=str(world.meta))
    oms._append({"id": "seed", "task_id": "task-concurrent", "spec_type": "check",
                 "content": "{}", "status": "passed", "author": "seed",
                 "created_at": "2026-01-01T00:00:00+08:00",
                 "updated_at": "2026-01-01T00:00:00+08:00"})

    errors = []

    def worker(i):
        try:
            omega.OmegaStrong("task-concurrent", meta_dir=str(world.meta))._append({
                "id": "rec-%02d" % i, "task_id": "task-concurrent",
                "spec_type": "check", "content": "{}", "status": "passed",
                "author": "worker", "created_at": "2026-01-01T00:00:00+08:00",
                "updated_at": "2026-01-01T00:00:00+08:00",
            })
        except Exception as exc:      # noqa: BLE001 —— 线程异常要带回主线程断言
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], errors
    records = oms.records()
    ids = {r.get("id") for r in records}
    assert len(records) == 21, "并发 append 丢失记录: %d != 21" % len(records)
    assert "seed" in ids
    assert {"rec-%02d" % i for i in range(20)} <= ids


# ===========================================================================
# 12) check_gate datetime 新鲜度（跨时区正确）
# ===========================================================================

def test_check_gate_compares_datetime_across_timezones(world):
    """退步了会怎样（P3 时区误判）：按字符串比较 `created_at < task_updated_at` ——
    `+08:00` 与 `Z` 混用（同一时刻）会被误判成"过期"或"新鲜"。

    断言：同一时刻的 UTC/Z 表示 → 新鲜通过；晚 1 秒（不同时区）→ 过期拒绝并给出
    可读原因；无 check 记录 / 最新记录 failed → 拒绝。
    """
    oms = omega.OmegaStrong("task-gate", meta_dir=str(world.meta))
    assert oms.check_gate("[gate:required]") == (
        False, "gate: 任务带 [gate:required]，但尚无外部检查记录，请先执行 run_check")

    oms._append({"id": "check:task-gate:r1", "task_id": "task-gate",
                 "spec_type": omega.T_CHECK, "content": "{}", "status": "passed",
                 "author": "x", "created_at": "2026-01-01T00:00:00+08:00",
                 "updated_at": "2026-01-01T00:00:00+08:00"})

    same_instant = oms.check_gate("[gate:required]", "2025-12-31T16:00:00Z")
    assert same_instant == (True, "fresh_passed"), same_instant

    later = oms.check_gate("[gate:required]", "2026-01-01T00:00:01+08:00")
    assert later[0] is False
    assert "早于任务最后更新" in later[1], later
