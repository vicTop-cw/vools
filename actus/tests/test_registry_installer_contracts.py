# -*- coding: utf-8 -*-
"""actus/tests/test_registry_installer_contracts.py — `installer.py` / `registry.py` 契约回归。

为什么要这份文件（第 9 轮补测）
------------------------------
`installer.py`（714 行）与 `registry.py`（792 行）此前**零测试覆盖**，而本轮在它们
身上抓到多条 P0/P1，且修复后没有任何回归测试兜着：
  * install() 路径越界 → 旧实现会把 Windows 本地路径当安装名，rmtree 打到**源仓**
  * uninstall 删任意子目录（只要传对名字）
  * 配置重装静默覆盖（用户手改 `.actus.scope` 被默认值覆盖）
  * 只读文件（git 对象）让 rmtree 半途 PermissionError
  * check_update 无 remote 时误报「已是最新」
  * `build_from_directory(write=False)` / `load_from_repo()` 假写（查询命令改仓库状态）
  * `write_index()` 非原子、损坏索引直接 JSONDecodeError

测试方式：全部 `tmp_path` + `HOME/USERPROFILE` 隔离；Git 操作用**假克隆**（不联网、
不依赖本机 git），把「源仓库」复制进 cache 目录，从而能真实走 install 的
rmtree/copytree/清单/配置保护全流程。

「退步了会怎样」写在每条 docstring 首段。
"""

import hashlib
import json
import os
import shutil
import stat
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import installer as installer_mod  # noqa: E402
from vools.actus import registry as registry_mod  # noqa: E402
from vools.actus.installer import ActionInstaller  # noqa: E402
from vools.actus.registry import ActionRegistry  # noqa: E402

_URL = "https://example.invalid/owner/repo.git"

#: registry._parse_action_file 只认 ```json #!cfg 块；installer 的 gate 只读 meta。
_ACTION_TEXT = """# Demo 动作

```json #!cfg
{"id": "myapp.demo", "name": "Demo", "version": "1.0.0",
 "description": "demo action", "trust": "sandbox"}
```

```python #!run tag=main
print("hi")
```
"""


# ---------------------------------------------------------------------------
# 夹具：tmp 仓库 + 隔离 HOME + 假 git
# ---------------------------------------------------------------------------

class _World(object):
    pass


def _digest_tree(root):
    """目录内容快照：{相对路径: sha256}，用于断言「源仓零改动」。"""
    out = {}
    for dirpath, _dirnames, filenames in os.walk(str(root)):
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, str(root)).replace(os.sep, "/")
            with open(full, "rb") as handle:
                out[rel] = hashlib.sha256(handle.read()).hexdigest()
    return out


@pytest.fixture
def world(tmp_path, monkeypatch):
    """tmp 世界：source 仓（含 1 个动作）/ install_dir / cache / HOME 全隔离。

    Git 操作全部换成「把 source 仓复制到 cache」的假实现：不联网，但 install()
    后续的 gate / build_from_directory / rmtree / copytree / 清单 / 配置保护
    都走真实产品代码。
    """
    home = tmp_path / "home"
    install = tmp_path / "install"
    cache = tmp_path / "cache"
    src = tmp_path / "src"
    repo_actions = src / "actions"
    repo_actions.mkdir(parents=True)
    (repo_actions / "demo.actus.md").write_text(_ACTION_TEXT, encoding="utf-8")

    for directory in (home, install, cache):
        directory.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    def fake_clone(self, url, dest, branch):
        branch_dir = os.path.join(dest, branch)
        os.makedirs(os.path.join(branch_dir, ".git"), exist_ok=True)
        shutil.copytree(str(repo_actions), os.path.join(branch_dir, "actions"))
        return (0, "", "")

    def fake_fetch(self, dest, branch):
        return (0, "", "")

    def fake_checkout(self, dest, branch):
        return None

    monkeypatch.setattr(ActionInstaller, "_git_clone", fake_clone)
    monkeypatch.setattr(ActionInstaller, "_git_fetch", fake_fetch)
    monkeypatch.setattr(ActionInstaller, "_git_checkout_branch", fake_checkout)
    monkeypatch.setattr(ActionInstaller, "_git_checkout_tag", fake_checkout)
    monkeypatch.setattr(ActionInstaller, "_git_checkout_commit", fake_checkout)

    w = _World()
    w.root = tmp_path
    w.home = home
    w.install = install
    w.cache = cache
    w.src = src
    w.installer = ActionInstaller(install_dir=str(install), cache_dir=str(cache),
                                  config_dir=str(home / ".actus"))
    return w


def _install(world, url=_URL, **kwargs):
    kwargs.setdefault("branch", "main")
    return world.installer.install(url, **kwargs)


def _inside(root, path):
    root_real = os.path.realpath(str(root))
    return os.path.realpath(str(path)).startswith(root_real + os.sep)


# ===========================================================================
# installer —— 1) install() 路径越界防护（P0）
# ===========================================================================

@pytest.mark.parametrize("name", ["..", ".", "../outside", "sub/../../outside"])
def test_inside_install_dir_rejects_escapes(world, name):
    """退步了会怎样（P0 的尺子）：`_inside_install_dir` 恒 True 时，`..` / `.` /
    `sub/../..` 这类安装名会让 `os.path.join(install_dir, name)` 跳出安装根，
    紧接着的 `shutil.rmtree(target_dir)` 就删到仓外（旧事故：rmtree 打到源仓 .git）。

    断言：越界名一律 False；正常名 True。
    """
    assert world.installer._inside_install_dir(name) is False, name
    assert world.installer._inside_install_dir("owner_repo") is True
    assert world.installer._inside_install_dir("nested" + os.sep) is True


def test_install_windows_local_path_stays_inside_and_keeps_source(world):
    """退步了会怎样（P0 回归）：用 Windows 本地路径当 repo_url 安装时，安装名里带
    反斜杠/盘符 → target_dir 跳到 install_dir 之外，重装路径上的 rmtree 删源仓。

    断言：安装成功且 target **严格位于 install_dir 内**；源仓内容前后逐字节一致。
    """
    source_before = _digest_tree(world.src)
    result = _install(world, url=str(world.src))

    assert result["status"] == "ok", result
    assert _inside(world.install, result["path"]), \
        "安装目录越出 install_dir: %r" % (result["path"],)
    assert os.path.realpath(result["path"]) != os.path.realpath(str(world.install))
    assert _digest_tree(world.src) == source_before, \
        "install() 改动了源仓库（P0：rmtree 打到仓外）"


def test_install_normal_path_records_manifest_and_actions(world):
    """退步了会怎样：正常安装不落清单/不报动作数（用户看不到装了什么）。

    断言：path 在 install_dir 内、actions 含 myapp.demo、action_count==1、
    安装清单可由 registry.list_installed() 读到同一 local_path。
    """
    result = _install(world)

    assert result["status"] == "ok", result
    assert result["name"] == "owner_repo"
    assert result["actions"] == ["myapp.demo"]
    assert result["action_count"] == 1
    assert _inside(world.install, result["path"])

    manifests = ActionRegistry(cache_dir=str(world.cache)).list_installed()
    local_paths = [os.path.realpath(m["local_path"]) for m in manifests]
    assert os.path.realpath(result["path"]) in local_paths
    assert (world.home / ".actus" / "installed").is_dir(), \
        "安装清单没有落到隔离 HOME 的 ~/.actus/installed"


# ===========================================================================
# installer —— 2) uninstall 只删清单内目录（P1）
# ===========================================================================

def test_uninstall_refuses_directory_not_in_manifest(world):
    """退步了会怎样（P1）：只要传对名字就 rmtree install_dir 下任意子目录 ——
    实测「从未由 actus 安装、内含用户文件」的目录被删掉还报 status=ok。

    断言：非清单目录 → status=error、消息点名「安装清单」与 force；目录与文件还在。
    """
    victim = world.install / "victim"
    victim.mkdir()
    user_file = victim / "user.txt"
    user_file.write_text("user data", encoding="utf-8")

    result = world.installer.uninstall(name="victim")

    assert result["status"] == "error", result
    assert "安装清单" in result["message"], result["message"]
    assert "force" in result["message"], result["message"]
    assert victim.is_dir() and user_file.read_text(encoding="utf-8") == "user data"


def test_uninstall_force_deletes_non_manifest_directory(world):
    """退步了会怎样：force=True 也删不掉非清单目录（用户明确要求却做不到）。

    断言：force=True → status=ok、forced=True、目录消失。
    """
    victim = world.install / "victim"
    victim.mkdir()
    (victim / "user.txt").write_text("user data", encoding="utf-8")

    result = world.installer.uninstall(name="victim", force=True)

    assert result["status"] == "ok", result
    assert result["forced"] is True
    assert result["removed"] == "victim"
    assert not victim.exists()


def test_uninstall_installed_repo_removes_manifest_entry(world):
    """退步了会怎样：用 name 卸载后清单里留下指向已删目录的陈旧条目（下次 list 崩）。

    断言：卸载已安装仓库 → ok、path 消失、manifest_removed=True、清单为空。
    """
    installed = _install(world)
    assert installed["status"] == "ok"

    result = world.installer.uninstall(name="owner_repo")

    assert result["status"] == "ok", result
    assert result["manifest_removed"] is True
    assert not os.path.exists(result["path"])
    assert ActionRegistry(cache_dir=str(world.cache)).list_installed() == []


# ===========================================================================
# installer —— 3) 配置重装不覆盖用户手改（P1）
# ===========================================================================

def test_reinstall_preserves_hand_edited_scope_by_default(world):
    """退步了会怎样（P1）：重装 = rmtree + copytree，用户手改的 `.actus.scope`
    随目录消失、被默认值覆盖（实测 hand-edit trusted 后重装变回 sandbox）。

    断言：装 → 手改 scope → 重装 → 文件仍是手改值、config_preserved 点名该文件、
    scope_written=False（不静默覆盖）。
    """
    first = _install(world, scope="sandbox")
    scope_file = os.path.join(first["path"], ".actus.scope")
    assert os.path.isfile(scope_file)

    with open(scope_file, "w", encoding="utf-8") as handle:
        handle.write("trusted")

    second = _install(world, scope="sandbox")

    assert second["status"] == "ok", second
    with open(scope_file, "r", encoding="utf-8") as handle:
        assert handle.read() == "trusted", "重装覆盖了用户手改的 .actus.scope"
    assert ".actus.scope" in second["config_preserved"]
    assert second["scope_written"] is False


def test_reinstall_overwrites_scope_only_when_explicitly_asked(world):
    """退步了会怎样：overwrite_config=True 时仍保留旧值（显式覆盖失效）。

    断言：手改后带 overwrite_config=True 重装 → 文件变回本次 scope、scope_written=True。
    """
    first = _install(world, scope="sandbox")
    scope_file = os.path.join(first["path"], ".actus.scope")
    with open(scope_file, "w", encoding="utf-8") as handle:
        handle.write("trusted")

    second = _install(world, scope="sandbox", overwrite_config=True)

    with open(scope_file, "r", encoding="utf-8") as handle:
        assert handle.read() == "sandbox"
    assert second["scope_written"] is True
    assert second["config_preserved"] == []


# ===========================================================================
# installer —— 4) 只读文件删除（_rmtree_force）
# ===========================================================================

def test_uninstall_removes_readonly_files_without_permission_error(world):
    """退步了会怎样：git 对象是只读的，普通 rmtree 半途 PermissionError ——
    安装目录被留成半成品，用户报「卸载失败」。

    断言：先把一个文件置只读，并让第一次 rmtree 抛 PermissionError（模拟只读位
    拦下），`_rmtree_force` 必须去只读位后重试成功：status=ok、目录消失、
    rmtree 被调用 ≥2 次（证明走了后备路径，而不是碰巧一次删掉）。
    """
    installed = _install(world)
    readonly = os.path.join(installed["path"], "actions", "demo.actus.md")
    os.chmod(readonly, stat.S_IREAD)

    real_rmtree = installer_mod.shutil.rmtree
    calls = {"count": 0}

    def flaky_rmtree(path):
        calls["count"] += 1
        if calls["count"] == 1:
            raise PermissionError("模拟只读文件：第一次 rmtree 被拦下")
        return real_rmtree(path)

    monkeypatched = False
    try:
        installer_mod.shutil.rmtree = flaky_rmtree
        monkeypatched = True
        result = world.installer.uninstall(name="owner_repo")
    finally:
        if monkeypatched:
            installer_mod.shutil.rmtree = real_rmtree

    assert result["status"] == "ok", result
    assert result["manifest_removed"] is True
    assert not os.path.exists(installed["path"]), "只读文件导致目录没删干净"
    assert calls["count"] >= 2, "没有走 _rmtree_force 的后备路径（测试未覆盖到位）"


# ===========================================================================
# installer —— 5) check_update 无 remote ≠ 已是最新
# ===========================================================================

def test_check_update_without_remote_reports_unknown_not_latest(world):
    """退步了会怎样（P1 假信号）：目录不是 git 仓 / 没有 origin 时 commit 拿不到，
    旧实现 `remote == ""` → has_update=False、status=ok，CLI 打印「✅ 已是最新版本」
    —— 根本没比对过。

    断言：status='unknown'、has_update is None、消息含「无法确认」。
    """
    installed = _install(world)
    assert installed["status"] == "ok"

    result = world.installer.check_update(name="owner_repo")

    assert result["status"] == "unknown", result
    assert result["has_update"] is None, result
    assert "无法确认" in result["message"], result["message"]


# ===========================================================================
# registry —— 6/7) build_from_directory(write=False) / load_from_repo 不落盘
# ===========================================================================

def _make_registry_repo(tmp_path):
    repo = tmp_path / "registry_repo"
    actions = repo / "actions"
    actions.mkdir(parents=True)
    (actions / "demo.actus.md").write_text(_ACTION_TEXT, encoding="utf-8")
    return repo


def test_build_from_directory_without_write_does_not_touch_disk(tmp_path):
    """退步了会怎样（假 dry-run 根因）：`build_from_directory(write=False)` 仍写盘 →
    `publish --dry-run` / 只读 `search` 会在用户仓库里留下 `.actus.registry.json`，
    界面说是查询/预检，实际改了仓库状态。

    断言：返回索引含 1 条动作，但仓库目录内容前后逐字节不变、索引文件不存在。
    """
    repo = _make_registry_repo(tmp_path)
    reg = ActionRegistry(cache_dir=str(tmp_path / "cache"))
    before = _digest_tree(repo)

    index = reg.build_from_directory(str(repo), write=False)

    assert [entry["id"] for entry in index["actions"]] == ["myapp.demo"]
    assert not (repo / ".actus.registry.json").exists(), "write=False 仍落盘（假干跑）"
    assert _digest_tree(repo) == before, "write=False 改动了仓库目录"


def test_build_from_directory_with_write_persists_and_reloads(tmp_path):
    """退步了会怎样：write=True 不落盘（`registry build`/publish 之后 search 看不到），
    或落盘内容与返回索引不一致。

    断言：文件存在、JSON 与返回索引全等、load_from_file 能读回同一条动作。
    """
    repo = _make_registry_repo(tmp_path)
    reg = ActionRegistry(cache_dir=str(tmp_path / "cache"))

    index = reg.build_from_directory(str(repo), write=True)
    registry_path = repo / ".actus.registry.json"

    assert registry_path.is_file()
    with open(str(registry_path), "r", encoding="utf-8") as handle:
        persisted = json.load(handle)
    assert persisted == index
    loaded = reg.load_from_file(str(registry_path))
    assert [entry["id"] for entry in loaded["actions"]] == ["myapp.demo"]


def test_load_from_repo_does_not_create_registry_file(tmp_path):
    """退步了会怎样（同族假写）：只读 `load_from_repo()` 顺手创建
    `.actus.registry.json` —— `actus search` 这种纯查询命令会改仓库状态。

    断言：仓库无索引文件时返回实时构建结果，但目录仍然没有索引文件。
    """
    repo = _make_registry_repo(tmp_path)
    reg = ActionRegistry(cache_dir=str(tmp_path / "cache"))

    index = reg.load_from_repo(str(repo))

    assert [entry["id"] for entry in index["actions"]] == ["myapp.demo"]
    assert not (repo / ".actus.registry.json").exists(), \
        "load_from_repo() 是读语义，不应顺手落盘"


# ===========================================================================
# registry —— 8) write_index 幂等（原子性是已知缺口，单列 xfail）
# ===========================================================================

def test_write_index_is_idempotent(tmp_path):
    """退步了会怎样：同一索引连写两次得到不同字节（非确定性/带时间戳混入），
    或留下临时文件残渣 —— 下游按内容比对/缓存会误判「变了」。

    断言：两次写入后文件字节完全一致、目录里没有 `.tmp` 残留。
    """
    repo = _make_registry_repo(tmp_path)
    reg = ActionRegistry(cache_dir=str(tmp_path / "cache"))
    index = reg.build_from_directory(str(repo), write=False)
    before = _digest_tree(repo)

    path_one = reg.write_index(index, str(repo))
    with open(path_one, "rb") as handle:
        first = handle.read()
    path_two = reg.write_index(index, str(repo))
    with open(path_two, "rb") as handle:
        second = handle.read()

    assert path_one == path_two
    assert first == second, "同一索引两次写入字节不一致（非常量输出）"
    leftovers = [name for name in os.listdir(str(repo)) if ".tmp" in name]
    assert leftovers == [], "write_index 留下了临时文件: %r" % (leftovers,)
    after = _digest_tree(repo)
    assert after[".actus.registry.json"] == hashlib.sha256(first).hexdigest()
    assert set(after) - set(before) == {".actus.registry.json"}


@pytest.mark.xfail(strict=False, reason=(
    "审计发现：write_index() 直接 open(...,'w') 截断原文件后 json.dump —— 写入中途"
    "失败/进程被杀会把**已有有效索引**清成空/半截（非原子写）。已上报，产品改为"
    "临时文件 + os.replace 后本用例自动 xpass。"))
def test_write_index_is_atomic_on_write_failure(tmp_path, monkeypatch):
    """退步了会怎样（当前就是）：索引写入不是原子的 —— 磁盘满/进程被杀时，
    原本有效的索引被截断，仓库从「索引可用」变成「索引损坏」。

    断言正确契约：一次失败的写入不得破坏旧索引内容（临时文件 + os.replace）。
    """
    repo = _make_registry_repo(tmp_path)
    reg = ActionRegistry(cache_dir=str(tmp_path / "cache"))
    good = reg.build_from_directory(str(repo), write=True)
    registry_path = str(repo / ".actus.registry.json")
    with open(registry_path, "rb") as handle:
        original = handle.read()

    def boom(*args, **kwargs):
        raise RuntimeError("模拟磁盘写满/进程中断")

    monkeypatch.setattr(registry_mod.json, "dump", boom)
    with pytest.raises(RuntimeError):
        reg.write_index(good, str(repo))

    with open(registry_path, "rb") as handle:
        assert handle.read() == original, "失败的写入破坏了已有索引（非原子）"


# ===========================================================================
# registry —— 9) 索引缺失 / 损坏时的行为
# ===========================================================================

def test_load_missing_index_returns_empty_actions(tmp_path):
    """退步了会怎样：索引文件缺失时抛异常（调用方没索引直接崩）。

    断言：load_from_file(不存在的路径) → {"actions": []}，不抛。
    """
    reg = ActionRegistry(cache_dir=str(tmp_path / "cache"))
    missing = str(tmp_path / "nope" / ".actus.registry.json")

    index = reg.load_from_file(missing)

    assert index.get("actions") == [], index


@pytest.mark.xfail(strict=False, reason=(
    "审计发现：旁边存在损坏的 .actus.registry.json 时，load_from_file 直接抛"
    "json.JSONDecodeError —— 没有「不崩溃 + 明确信号」的降级路径。已上报，产品"
    "改为返回空索引+problems/invalid 标记后本用例自动 xpass。"))
def test_corrupt_index_reports_explicit_signal_not_crash(tmp_path):
    """退步了会怎样（当前就是）：索引被写坏后 `actus search/list` 直接冒
    JSONDecodeError 堆栈，用户不知道是索引坏了、也不知道怎么修。

    断言正确契约：损坏索引 → 不抛、返回空索引 + 明确信号（problems/invalid 标记）。
    """
    repo = _make_registry_repo(tmp_path)
    (repo / ".actus.registry.json").write_text("{ this is not json", encoding="utf-8")
    reg = ActionRegistry(cache_dir=str(tmp_path / "cache"))

    index = reg.load_from_file(str(repo / ".actus.registry.json"))

    assert index.get("actions") == [], index
    assert index.get("problems") or index.get("invalid") or index.get("corrupt"), \
        "损坏索引没有任何明确信号（problems/invalid/corrupt）"
