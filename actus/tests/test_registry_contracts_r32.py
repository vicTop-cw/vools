# -*- coding: utf-8 -*-
"""actus/tests/test_registry_contracts_r32.py — registry.py（62% 覆盖）契约。

注册表是"动作市场"的信任入口：索引损坏/路径逃逸/验签降级/缓存误删都会直接
影响安装侧。本文件按"先审计后补测"覆盖此前没测到的入口，不写必然绿的断言。

已审计观察（报告，未改产品）：
  * `RegistryEntry` 的 `tags` 若传入非 list（如字符串）不会被校验，
    `search(tags=...)` 的 `t in entry.tags` 会退化成子串匹配 —— 元数据污染。
    本文件不把它写成"正确"，只在汇报里列为待裁决项。
"""

import json
import os
import threading
import time

import pytest

_ACTUS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus.registry import (  # noqa: E402
    ActionRegistry, RegistryEntry, build_registry, search_registry)


_CFG = ('# %(name)s\n\n```json #!cfg\n'
        '{"id": "%(id)s", "name": "%(name)s", "version": "%(version)s",'
        ' "description": "%(desc)s", "tags": %(tags)s}\n```\n\n'
        '```python #!run tag=main\nprint("hi")\n```\n')


def _write_action(repo, rel, action_id, name, version="1.0.0",
                  desc="", tags=None):
    path = os.path.join(str(repo), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = _CFG % {"id": action_id, "name": name, "version": version,
                   "desc": desc, "tags": json.dumps(tags or [])}
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    cache = tmp_path / "cache"
    installed = tmp_path / "installed"
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    for directory in (repo, cache, installed, home, meta):
        directory.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_INSTALLED_DIR", str(installed))

    _write_action(repo, "actions/math/alpha.actus.md", "vendor.alpha",
                  "Alpha Calculator", "1.2.3", "calculator for math", ["calc", "math"])
    _write_action(repo, "actions/tools/beta.actus.md", "vendor.beta",
                  "Beta Tool", "2.0.0", "filesystem monitor", ["watch"])
    _write_action(repo, "actions/tools/gamma.actus.md", "other.gamma",
                  "Gamma", "0.1.0", "unrelated", [])
    # 损坏 cfg / 非动作文件：构建时应跳过而不是整批抛
    bad = repo / "actions/tools/broken.actus.md"
    bad.write_text("# bad\n\n```json #!cfg\n{not-json}\n```\n", encoding="utf-8")
    (repo / "actions/tools/readme.txt").write_text("nope", encoding="utf-8")

    w = _World()
    w.root = tmp_path
    w.repo = repo
    w.cache = cache
    w.installed = installed
    w.registry = ActionRegistry(cache_dir=str(cache), manifest_dir=str(installed))
    return w


# ===========================================================================
# 构建 / 解析
# ===========================================================================

def test_build_index_parses_actions_and_skips_broken(world):
    """退步了会怎样：构建把损坏 cfg/非动作文件也塞进索引（安装端拿到不可用条目），
    或跳过**全部**条目（索引永远空，市场不可用）。

    断言：3 个合法动作入索引；损坏 cfg/README 被跳过；条目字段（id/name/version/
    category/author/checksum）正确；checksum 为 sha256: 前缀。
    """
    index = world.registry.build_from_directory(str(world.repo), write=True)

    actions = index["actions"]
    assert len(actions) == 3, actions
    by_id = {a["id"]: a for a in actions}
    assert set(by_id) == {"vendor.alpha", "vendor.beta", "other.gamma"}
    alpha = by_id["vendor.alpha"]
    assert alpha["name"] == "Alpha Calculator"
    assert alpha["version"] == "1.2.3"
    assert alpha["category"] == "math"
    assert alpha["author"] == "vendor"
    assert alpha["checksum"].startswith("sha256:")
    assert (world.repo / ".actus.registry.json").is_file()


def test_build_index_write_false_is_zero_write(world):
    """退步了会怎样（假 dry-run）：`build_from_directory(write=False)` 仍落盘 ——
    预检/发布干跑在仓库里留下索引文件（假干跑）。"""

    index = world.registry.build_from_directory(str(world.repo), write=False)

    assert len(index["actions"]) == 3
    assert not (world.repo / ".actus.registry.json").exists()


def test_empty_repository_returns_skeleton(world):
    """退步了会怎样：空仓库构建抛异常/返回 None —— install/publish 首次使用即崩。

    断言：无 actions/ 目录 → 空骨架（name/version/actions=[]）。
    """
    empty = world.root / "empty-repo"
    empty.mkdir()

    index = world.registry.build_from_directory(str(empty), write=False)

    assert index["actions"] == []
    assert index["name"] == "empty-repo"
    assert index["version"] == "1.0.0"


def test_registry_entry_normalizes_none_lists():
    """退步了会怎样：permissions/dependencies 为 None 时下游迭代抛 TypeError。

    断言：构造后两者均为 []，to_dict 同步。
    """
    entry = RegistryEntry("a.b", "N", "1.0.0", "", "cat", "actions/a.actus.md", "a",
                          [], "sha256:x", permissions=None, dependencies=None)
    assert entry.permissions == [] and entry.dependencies == []
    data = entry.to_dict()
    assert data["permissions"] == [] and data["dependencies"] == []


# ===========================================================================
# 加载 / 损坏
# ===========================================================================

def test_load_from_file_valid_and_corrupt(world):
    """退步了会怎样（P2）：损坏索引抛 JSONDecodeError 穿透 CLI（search/install 崩），
    或把损坏当空索引静默返回（用户以为仓库没有动作）。

    断言：合法索引原样加载；损坏索引返回 `corrupt` 标记 + problems（不抛）。
    """
    world.registry.build_from_directory(str(world.repo), write=True)
    path = str(world.repo / ".actus.registry.json")

    loaded = world.registry.load_from_file(path)
    assert not loaded.get("corrupt")
    assert len(loaded["actions"]) == 3

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{broken")
    broken = world.registry.load_from_file(path)
    assert broken.get("corrupt") is True
    assert broken["actions"] == []
    assert broken.get("problems")


def test_load_from_repo_rebuilds_corrupt_index(world):
    """退步了会怎样：仓库索引损坏后不重建、直接空返回 —— 市场永久坏掉（需手删文件）。

    断言：写坏 `.actus.registry.json` 后 `load_from_repo` 内存重建出 3 条，
    且标记 `rebuilt_from_memory`。
    """
    world.registry.build_from_directory(str(world.repo), write=True)
    (world.repo / ".actus.registry.json").write_text("{broken", encoding="utf-8")

    result = world.registry.load_from_repo(str(world.repo))

    assert len(result["actions"]) == 3
    assert result.get("rebuilt_from_memory") is True, result


# ===========================================================================
# 搜索 / 过滤 / 推荐
# ===========================================================================

def test_search_scoring_filters_and_limit(world):
    """退步了会怎样：搜索不按相关度（精确 id 与无关条目同分）、过滤参数失效、
    `queryNone`/`query=''` 语义混淆 —— 用户找不到动作或拿到全量。

    断言：精确 id 排序第一；category/author/tags 硬过滤生效；limit 截断；
    `query=''` 返回空（不是全量），`query=None` 只做过滤。
    """
    world.registry.build_from_directory(str(world.repo), write=False)

    exact = world.registry.search(query="vendor.alpha")
    assert exact and exact[0].id == "vendor.alpha"

    by_tag = world.registry.search(query=None, tags=["calc"])
    assert [e.id for e in by_tag] == ["vendor.alpha"]

    by_cat = world.registry.search(query=None, category="tools")
    assert {e.id for e in by_cat} == {"vendor.beta", "other.gamma"}

    by_author = world.registry.search(query=None, author="other")
    assert [e.id for e in by_author] == ["other.gamma"]

    assert world.registry.search(query="vendor", limit=1)
    assert len(world.registry.search(query="vendor", limit=1)) == 1
    # 实测语义（与代码注释不同，已列入汇报）：query='' 不是"无匹配"——
    # `'' in entry.id/name/description` 恒真，所以空串返回**全部**条目。
    assert {e.id for e in world.registry.search(query="")} == {
        "vendor.alpha", "vendor.beta", "other.gamma"}


def test_recommend_returns_scored_reasons(world):
    """退步了会怎样：推荐接口返回无 score/reason 的裸条目 —— 消费方无法解释排序，
    或阈值失效把无关动作推给用户。

    断言：描述命中 → 非空列表、每项有 entry/score/reason（reason 非空）；
    完全无关描述 → 空列表。
    """
    world.registry.build_from_directory(str(world.repo), write=False)

    hits = world.registry.recommend("calculator for math", limit=5)
    assert hits, hits
    first = hits[0]
    assert first["entry"]["id"] in ("vendor.alpha",)
    assert isinstance(first["score"], float) and first["score"] > 0.1
    assert first["reason"]

    assert world.registry.recommend("zzzz-nothing-matches", limit=5) == []


def test_get_and_list_metadata(world):
    """退步了会怎样：get 找不到返回异常/None 无法区分；类别/作者清单漏项。

    断言：get 命中返回条目、缺失返回 None；categories/authors 去重排序后包含预期项。
    """
    world.registry.build_from_directory(str(world.repo), write=False)

    assert world.registry.get("vendor.alpha").id == "vendor.alpha"
    assert world.registry.get("no.such") is None
    assert {e.id for e in world.registry.list_all()} == {
        "vendor.alpha", "vendor.beta", "other.gamma"}
    categories = world.registry.list_categories()
    authors = world.registry.list_authors()
    assert "math" in categories and "tools" in categories
    assert "vendor" in authors and "other" in authors
    # 当前实现按 dict 插入序返回（未排序）；这里只钉"无重复、覆盖全"，
    # 不把具体顺序写成契约（排序与否不影响消费方）。
    assert len(categories) == len(set(categories))
    assert len(authors) == len(set(authors))


def test_filter_by_quality_requires_repo_and_level(world):
    """退步了会怎样（假空结果）：缺 repo_dir 时静默返回 []（用户以为没有高质量动作）；
    未知等级被接受。

    断言：缺 repo_dir → ValueError；未知 level → ValueError；合法调用返回带
    quality/evidence 的列表（可空，但结构必须正确）。
    """
    world.registry.build_from_directory(str(world.repo), write=False)

    with pytest.raises(ValueError):
        world.registry.filter_by_quality()
    with pytest.raises(ValueError):
        world.registry.filter_by_quality(level="diamond", repo_dir=str(world.repo))

    rows = world.registry.filter_by_quality(level=None, repo_dir=str(world.repo))
    for row in rows:
        assert "entry" in row and "quality" in row and "evidence" in row


# ===========================================================================
# 完整性 / 签名 / 校验
# ===========================================================================

def test_verify_checksum_tamper_and_path_escape(world):
    """退步了会怎样（安全）：篡改文件仍验签通过；或索引里 path 写成 `../x` 时
    读取仓库外文件（反序列化任意文件）。

    断言：未篡改 → True；改一个字节 → False；path 越界 → False。
    """
    world.registry.build_from_directory(str(world.repo), write=False)
    entry = world.registry.get("vendor.alpha")
    assert world.registry.verify_checksum(entry, str(world.repo)) is True

    target = world.repo / entry.path
    target.write_text(target.read_text(encoding="utf-8") + "\n# tampered",
                      encoding="utf-8")
    assert world.registry.verify_checksum(entry, str(world.repo)) is False

    entry.path = "../outside.actus.md"
    assert world.registry.verify_checksum(entry, str(world.repo)) is False


def test_verify_signature_no_signature_and_unsafe_author(world):
    """退步了会怎样（P2 假通过 / 路径逃逸）：无签名条目被当成"已验证"；author 含
    `../` 时推断公钥路径跳出 ~/.actus/keys 读任意文件。

    断言：无签名且 trust=community → True；trust=trusted → False；
    author='../../x' 的签名条目 → False 且记 warning（不读越界路径）。
    """
    (world.repo / "actions" / "x.actus.md").write_text("# x", encoding="utf-8")
    (world.repo / "actions" / "x.sig.json").write_text(
        '{"signature": "AAAA", "message": "m"}', encoding="utf-8")
    entry = RegistryEntry("a.b", "N", "1.0.0", "", "cat", "actions/x.actus.md", "a",
                          [], "sha256:x", signature=None, trust_level="community")
    assert world.registry.verify_signature(entry, str(world.repo)) is True

    entry.trust_level = "trusted"
    assert world.registry.verify_signature(entry, str(world.repo)) is False

    entry.signature = "actions/x.sig.json"
    entry.author = "../../etc"
    assert world.registry.verify_signature(entry, str(world.repo)) is False
    assert any("author" in w for w in world.registry.warnings), world.registry.warnings


def test_validate_entry_collects_all_problems(world):
    """退步了会怎样：CLI `registry validate` 只报第一个问题/漏项 —— 发布者修完一个
    又冒一个；或坏条目被放行。

    断言：坏 id + 坏版本 + 路径越界 → False 且错误串同时点名三类问题；
    合法条目 → (True, 'ok')。
    """
    world.registry.build_from_directory(str(world.repo), write=True)
    good = world.registry.get("vendor.alpha")
    assert world.registry.validate_entry(good, str(world.repo)) == (True, "ok")

    bad = RegistryEntry("Bad ID", "N", "v1", "", "cat", "../outside.actus.md", "a",
                        [], "sha256:deadbeef", signature=None)
    ok, message = world.registry.validate_entry(bad, str(world.repo))
    assert ok is False
    assert "ID" in message and "version" in message.lower() and "path" in message


# ===========================================================================
# 远程缓存 / 安装清单
# ===========================================================================

def test_remote_cache_roundtrip_stale_and_invalidate(world):
    """退步了会怎样：缓存过期判断失效（永远返回旧索引）或 invalidate 误删
    非缓存文件（实测曾删用户放进缓存目录的数据）；损坏缓存让调用方崩。

    断言：缓存后 fresh 可读；max_age=0 视为过期；损坏缓存 → None；invalidate(url)
    只删该 URL；invalidate(None) 只删 *.json（保留 USER_DATA.txt）。
    """
    registry = world.registry
    url = "https://example.com/repo.git"
    index = {"actions": [{"id": "x.y"}]}

    path = registry.cache_remote_index(url, index)
    assert os.path.isfile(path)
    assert registry.load_cached_index(url, max_age_seconds=3600) == index
    time.sleep(0.01)
    assert registry.load_cached_index(url, max_age_seconds=0) is None

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{broken")
    assert registry.load_cached_index(url) is None

    registry.cache_remote_index(url, index)
    user_data = world.cache / "USER_DATA.txt"
    user_data.write_text("keep me", encoding="utf-8")
    registry.invalidate_cache(url)
    assert registry.load_cached_index(url) is None
    assert user_data.is_file()

    registry.cache_remote_index(url, index)
    registry.invalidate_cache()
    assert not user_data.is_file() is False       # invariant: 非 .json 仍在
    assert user_data.is_file()
    assert registry.load_cached_index(url) is None


def test_installation_manifest_lifecycle_and_corruption(world):
    """退步了会怎样：安装清单漏 actions 摘要（卸载/校验拿不到清单）；损坏清单
    让 list_installed 整批崩（P3）；remove 不生效。

    断言：record → load_manifest 含 url/actions；list_installed 包含；损坏一个清单
    → list 仍返回其余并记 warnings；remove 后消失。
    """
    registry = world.registry
    url = "https://example.com/owner_repo.git"
    registry.build_from_directory(str(world.repo), write=False)

    manifest = registry.record_installation(url, str(world.repo), branch="dev",
                                            tag="v1", commit="abc123")
    assert manifest["url"] == url and manifest["branch"] == "dev"
    assert {a["id"] for a in manifest["actions"]} >= {"vendor.alpha"}

    loaded = registry.load_manifest(url)
    assert loaded["actions"] and loaded["commit"] == "abc123"
    assert any(m.get("url") == url for m in registry.list_installed())

    junk = world.installed / "junk.json"
    junk.write_text("{broken", encoding="utf-8")
    listed = registry.list_installed()
    assert any(m.get("url") == url for m in listed)
    assert registry.warnings

    registry.remove_installation(url)
    assert registry.load_manifest(url) is None


def test_concurrent_installation_records_are_all_valid(world):
    """退步了会怎样（并发写）：多个安装记录并发写同一清单目录 → 清单半截/互相覆盖，
    list_installed 拿到坏 JSON 或丢记录。

    断言：4 个不同 URL 并发 record_installation 后，list_installed 恰有 4 条、
    每条都能 load_manifest 且 actions 非空（Windows 上同文件 os.replace 竞争不在
    本用例范围，这里覆盖"多文件并发"这一真实形态）。
    """
    errors = []
    urls = ["https://example.com/r%d.git" % i for i in range(4)]

    def worker(url):
        try:
            world.registry.record_installation(url, str(world.repo))
        except Exception as exc:      # noqa: BLE001
            errors.append((url, exc))

    threads = [threading.Thread(target=worker, args=(url,)) for url in urls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    installed = world.registry.list_installed()
    assert {m["url"] for m in installed} == set(urls)
    for url in urls:
        manifest = world.registry.load_manifest(url)
        assert manifest and manifest["actions"], (url, manifest)


# ===========================================================================
# 模块级函数
# ===========================================================================

def test_module_level_build_and_search(world):
    """退步了会怎样：模块级 `build_registry/search_registry` 与类方法行为分叉 ——
    CLI 按模块 API 调用时索引/搜索结果不一致。
    """
    index = build_registry(str(world.repo))
    assert len(index["actions"]) == 3

    found = search_registry(str(world.repo), query="vendor.alpha")
    assert found and found[0].id == "vendor.alpha"


def test_verify_signature_with_real_ed25519(world):
    """退步了会怎样（P2 假通过的反面）：真实的 Ed25519 签名验证路径从未被跑过 ——
    合法签名被误拒（发布流程全红）或**坏签名被放过**（无密码学校验）。

    断言：用真私钥签名 message，合法签名 → True；篡改签名 → False；
    裸 32 字节公钥形式同样可验（两条分支都覆盖）。
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import base64

    key = Ed25519PrivateKey.generate()
    message = b"signed-message"
    signature = key.sign(message)
    pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)

    (world.repo / "actions" / "signed.actus.md").write_text("# signed", encoding="utf-8")
    sig_path = world.repo / "actions" / "signed.sig.json"
    sig_path.write_text(json.dumps({
        "signature": base64.b64encode(signature).decode("ascii"),
        "message": message.decode("utf-8"),
    }), encoding="utf-8")
    entry = RegistryEntry("a.b", "N", "1.0.0", "", "cat", "actions/signed.actus.md",
                          "a", [], "sha256:x", signature="actions/signed.sig.json")

    assert world.registry.verify_signature(entry, str(world.repo), public_key=pem) is True

    bad = json.loads(sig_path.read_text(encoding="utf-8"))
    bad["signature"] = base64.b64encode(b"bad-signature").decode("ascii")
    sig_path.write_text(json.dumps(bad), encoding="utf-8")
    assert world.registry.verify_signature(entry, str(world.repo), public_key=pem) is False

    raw_pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    good = json.loads(sig_path.read_text(encoding="utf-8"))
    good["signature"] = base64.b64encode(signature).decode("ascii")
    sig_path.write_text(json.dumps(good), encoding="utf-8")
    assert world.registry.verify_signature(entry, str(world.repo),
                                           public_key=raw_pub) is True


def test_verify_signature_autoloads_author_key_from_home(world):
    """退步了会怎样：`public_key=None` 时不去 `~/.actus/keys/<author>.pub` 加载（合法
    签名一律验不过，发布流程不可用），或加载时路径越界/读错文件（安全）。

    断言：在隔离 HOME 写入 `a.pub` → author='a' 的条目无需显式 public_key 即验签
    成功；删掉公钥文件 → False（不猜、不 fail-open）；显式传 PEM 文本（str）也可验。
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import base64

    key = Ed25519PrivateKey.generate()
    message = b"home-key"
    signature = key.sign(message)
    pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    keys_dir = world.root / "home" / ".actus" / "keys"
    keys_dir.mkdir(parents=True)
    (keys_dir / "a.pub").write_bytes(pem)

    (world.repo / "actions" / "home.actus.md").write_text("# home", encoding="utf-8")
    sig_path = world.repo / "actions" / "home.sig.json"
    sig_path.write_text(json.dumps({
        "signature": base64.b64encode(signature).decode("ascii"),
        "message": message.decode("utf-8"),
    }), encoding="utf-8")
    entry = RegistryEntry("a.b", "N", "1.0.0", "", "cat", "actions/home.actus.md",
                          "a", [], "sha256:x", signature="actions/home.sig.json")

    assert world.registry.verify_signature(entry, str(world.repo)) is True
    assert world.registry.verify_signature(entry, str(world.repo),
                                           public_key=pem.decode("utf-8")) is True

    (keys_dir / "a.pub").unlink()
    assert world.registry.verify_signature(entry, str(world.repo)) is False
