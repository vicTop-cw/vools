"""installer.py 契约测试（Round 70）——与 test_registry_installer_contracts.py 互补。

已有文件覆盖 install() 全流程（假 git + 真实 registry/copytree/清单）。
本文件聚焦未覆盖的单元分支：
- _snapshot_user_configs / _restore_user_configs（含 OSError 跳过）
- _rmtree_force（只读文件兜底）
- enforce_visibility_gate 各分支（internal/gated 无键/验签/Store 故障/解析失败跳过）
- install 名字清洗（Windows 路径 / 穿越 name）
- uninstall 各拒绝分支 / force / 清单移除
- update / sync_all / rollback / check_update（假 run_cmd_safe）
- get/set_scope、get_install_path、discover_actions_dirs、resolve_action_path
- _run_git 的 -9/-1/异常 分支
- _write_scope_config / _write_visibility_config 保护语义
- install_with_visibility 私有动作分支
- _load_manifest、_url_to_*、便捷函数

全部隔离：目录进 tmp_path，HOME/USERPROFILE 指 tmp；不联网、不跑真 git。
"""

import json
import os
import stat
import sys

import pytest

import _ai_local_bootstrap  # noqa: E402,F401  — 必须先于 vools.actus 导入（本地源码优先 + 身份一致）

import vools.actus.installer as inst_mod
from vools.actus.installer import (  # noqa: E402
    ActionInstaller,
    _restore_user_configs,
    _rmtree_force,
    _snapshot_user_configs,
)
from vools.actus.visibility import AUTH_REQUIRED  # noqa: E402


# ---------------------------------------------------------------------------
# 基础世界：全部目录进 tmp，HOME 指 tmp
# ---------------------------------------------------------------------------

@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    install = tmp_path / "install"
    cache = tmp_path / "cache"
    for d in (home, install, cache):
        d.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    inst = ActionInstaller(install_dir=str(install),
                           cache_dir=str(cache),
                           config_dir=str(home / ".actus"))
    w = type("W", (), {})()
    w.tmp = tmp_path
    w.home = home
    w.install = install
    w.cache = cache
    w.inst = inst
    return w


_CFG = '{"id": "myapp.demo", "name": "Demo", "version": "1.0.0", "description": "d", "trust": "sandbox"}'
_ACT = ("# t\n\n```json #!cfg\n" + _CFG + "\n```\n\n"
        "```python #!run tag=main\nprint(1)\n```\n")

#: gate 用 parse_cfg_from_file 读 meta —— 动作必须有 entry 才是合法 Action
_CFG_ENTRY = ('{"id": "myapp.demo", "name": "Demo", "version": "1.0.0", '
              '"description": "d", "trust": "sandbox", "entry": "main"}')
_ACT_FULL = ("# t\n\n```json #!cfg\n" + _CFG_ENTRY + "\n```\n\n"
             "```python #!run tag=main\nprint(1)\n```\n")


def _with_vis(vis):
    return _ACT_FULL.replace('"entry": "main"',
                             '"entry": "main", "visibility": "%s"' % vis)


def _make_repo(root, action_text=_ACT, name="demo.actus.md"):
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(action_text, encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# _snapshot_user_configs / _restore_user_configs
# ---------------------------------------------------------------------------

class TestConfigSnapshot:
    def test_snapshot_reads_existing(self, tmp_path):
        (tmp_path / ".actus.scope").write_text("sandbox", encoding="utf-8")
        (tmp_path / ".actus.visibility").write_text("{}", encoding="utf-8")
        saved = _snapshot_user_configs(str(tmp_path))
        assert saved == {".actus.scope": "sandbox", ".actus.visibility": "{}"}

    def test_snapshot_missing_files(self, tmp_path):
        assert _snapshot_user_configs(str(tmp_path)) == {}

    def test_snapshot_unreadable_skipped(self, tmp_path, monkeypatch):
        target = tmp_path / ".actus.scope"
        target.write_text("x", encoding="utf-8")
        real_open = open

        def fake_open(path, *a, **kw):
            if str(path).endswith(".actus.scope"):
                raise OSError("boom")
            return real_open(path, *a, **kw)

        monkeypatch.setattr("builtins.open", fake_open)
        assert _snapshot_user_configs(str(tmp_path)) == {}

    def test_restore_writes_back(self, tmp_path):
        restored = _restore_user_configs(str(tmp_path),
                                         {".actus.scope": "trusted"})
        assert restored == [".actus.scope"]
        assert (tmp_path / ".actus.scope").read_text(encoding="utf-8") == "trusted"

    def test_restore_none_or_empty(self, tmp_path):
        assert _restore_user_configs(str(tmp_path), None) == []
        assert _restore_user_configs(str(tmp_path), {}) == []

    def test_restore_unwritable_skipped(self, tmp_path):
        # 目标子目录不存在 → open 抛 OSError → 跳过
        restored = _restore_user_configs(str(tmp_path / "nope"),
                                         {".actus.scope": "x"})
        assert restored == []


# ---------------------------------------------------------------------------
# _rmtree_force
# ---------------------------------------------------------------------------

class TestRmtreeForce:
    def test_plain_dir(self, tmp_path):
        d = tmp_path / "d"
        d.mkdir()
        (d / "f.txt").write_text("x", encoding="utf-8")
        _rmtree_force(str(d))
        assert not d.exists()

    def test_readonly_files_forced(self, tmp_path):
        d = tmp_path / "ro"
        (d / ".git").mkdir(parents=True)
        f = d / ".git" / "obj"
        f.write_text("x", encoding="utf-8")
        os.chmod(str(f), stat.S_IREAD)          # 只读：普通 rmtree 会 PermissionError
        _rmtree_force(str(d))
        assert not d.exists()

    def test_missing_path_raises_through(self, tmp_path):
        with pytest.raises(OSError):
            _rmtree_force(str(tmp_path / "ghost"))

    def test_chmod_failure_surfaces_real_error(self, tmp_path, monkeypatch):
        d = tmp_path / "ro2"
        (d / ".git").mkdir(parents=True)
        f = d / ".git" / "obj"
        f.write_text("x", encoding="utf-8")
        os.chmod(str(f), stat.S_IREAD)

        def dead_chmod(path, mode):
            raise OSError("cannot chmod")

        monkeypatch.setattr(inst_mod.os, "chmod", dead_chmod)
        # chmod 兜底也失败 → 第二次 rmtree 在只读文件上抛 PermissionError
        #（契约：不静默吞掉删除失败；调用方看到真实文件系统错误）
        with pytest.raises(OSError):
            _rmtree_force(str(d))
        assert f.exists()


# ---------------------------------------------------------------------------
# 构造与默认目录
# ---------------------------------------------------------------------------

class TestInit:
    def test_explicit_dirs_created(self, tmp_path):
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        assert (tmp_path / "i").is_dir() and (tmp_path / "c").is_dir()
        assert inst.install_dir == str(tmp_path / "i")

    def test_default_dirs_under_home(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        inst = ActionInstaller()
        assert inst._install_dir == os.path.join(str(tmp_path), ".actus", "actions")
        assert os.path.isdir(inst._install_dir)
        assert os.path.isdir(inst._cache_dir)


# ---------------------------------------------------------------------------
# enforce_visibility_gate
# ---------------------------------------------------------------------------

class TestGate:
    def _repo(self, tmp_path, action_text=_ACT_FULL):
        return _make_repo(tmp_path / "src", action_text)

    def test_no_actions_ok(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        r = inst.enforce_visibility_gate(str(empty), "https://x.dev/a/b.git")
        assert r == {"status": "ok", "gated": [], "repo": "b"}

    def test_public_action_ok(self, tmp_path):
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        repo = self._repo(tmp_path)
        r = inst.enforce_visibility_gate(str(repo), "https://x.dev/a/b.git")
        assert r["status"] == "ok" and r["gated"] == []

    def test_internal_denied(self, tmp_path):
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        repo = self._repo(tmp_path, _with_vis("internal"))
        r = inst.enforce_visibility_gate(str(repo), "https://x.dev/a/b.git")
        assert r["status"] == "error" and r["code"] == "visibility_denied"
        assert r["details"]["action_id"] == "myapp.demo"

    def test_gated_without_key(self, tmp_path):
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        repo = self._repo(tmp_path, _with_vis("gated"))
        r = inst.enforce_visibility_gate(str(repo), "https://x.dev/a/b.git")
        assert r["status"] == "error" and r["code"] == AUTH_REQUIRED
        assert r["details"]["gated"] == ["myapp.demo"]

    def test_gated_key_verified(self, tmp_path, monkeypatch):
        class FakeStore:
            def verify(self, key, action_id=None, repo=None):
                return action_id == "myapp.demo" and key == "k1"

        import vools.actus.visibility as vis
        monkeypatch.setattr(vis, "GatedKeyStore", FakeStore)
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        repo = self._repo(tmp_path, _with_vis("gated"))
        r = inst.enforce_visibility_gate(str(repo), "https://x.dev/a/b.git", key="k1")
        assert r == {"status": "ok", "gated": ["myapp.demo"], "repo": "b"}

    def test_gated_key_denied(self, tmp_path, monkeypatch):
        class FakeStore:
            def verify(self, key, action_id=None, repo=None):
                return False

        import vools.actus.visibility as vis
        monkeypatch.setattr(vis, "GatedKeyStore", FakeStore)
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        repo = self._repo(tmp_path, _with_vis("gated"))
        r = inst.enforce_visibility_gate(str(repo), "https://x.dev/a/b.git", key="bad")
        assert r["code"] == AUTH_REQUIRED and r["details"]["denied"] == ["myapp.demo"]

    def test_store_runtime_error_fail_closed(self, tmp_path, monkeypatch):
        class FakeStore:
            def __init__(self):
                raise RuntimeError("no config dir")

        import vools.actus.visibility as vis
        monkeypatch.setattr(vis, "GatedKeyStore", FakeStore)
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        repo = self._repo(tmp_path, _with_vis("gated"))
        r = inst.enforce_visibility_gate(str(repo), "https://x.dev/a/b.git", key="k")
        assert r["status"] == "error" and r["code"] == AUTH_REQUIRED
        assert "no config dir" in r["message"]

    def test_action_id_filter(self, tmp_path):
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        repo = self._repo(tmp_path, _with_vis("internal"))
        r = inst.enforce_visibility_gate(str(repo), "https://x.dev/a/b.git",
                                         action_id="other.thing")
        assert r["status"] == "ok"          # 别的动作被过滤掉，internal 不命中

    def test_parse_failure_skipped(self, tmp_path):
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        repo = tmp_path / "src"
        repo.mkdir()
        (repo / "bad.actus.md").write_text("totally not an action", encoding="utf-8")
        r = inst.enforce_visibility_gate(str(repo), "https://x.dev/a/b.git")
        assert r["status"] == "ok"

    def test_visibility_engine_unavailable(self, tmp_path, monkeypatch):
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        repo = self._repo(tmp_path)
        monkeypatch.setitem(sys.modules, "vools.actus.visibility", None)
        r = inst.enforce_visibility_gate(str(repo), "https://x.dev/a/b.git")
        assert r["status"] == "error" and r["code"] == "internal"

    def test_repo_name_fallback_on_parse_error(self, tmp_path, monkeypatch):
        import vools.actus.repo as repo_mod

        def boom(_url):
            raise ValueError("nope")

        monkeypatch.setattr(repo_mod, "parse_ref", boom)
        inst = ActionInstaller(install_dir=str(tmp_path / "i"),
                               cache_dir=str(tmp_path / "c"),
                               config_dir=str(tmp_path / "cfg"))
        repo = self._repo(tmp_path)
        r = inst.enforce_visibility_gate(str(repo),
                                         "https://x.dev/Owner/B-Repo.git")
        assert r["repo"] == "B-Repo"


# ---------------------------------------------------------------------------
# install 名字清洗 / 越界防护
# ---------------------------------------------------------------------------

class TestInstallNames:
    def test_windows_local_path_installs_by_basename(self, world, monkeypatch):
        src = world.tmp / "proj" / "myrepo"
        _make_repo(src / "actions")

        def fake_clone(self, url, dest, branch):
            bd = os.path.join(dest, branch)
            os.makedirs(os.path.join(bd, ".git"), exist_ok=True)
            act = os.path.join(bd, "actions")
            os.makedirs(act, exist_ok=True)
            with open(os.path.join(act, "demo.actus.md"), "w", encoding="utf-8") as f:
                f.write(_ACT)
            return (0, "", "")

        monkeypatch.setattr(ActionInstaller, "_git_clone", fake_clone)
        r = world.inst.install("C:\\Users\\me\\proj\\myrepo")
        assert r["status"] == "ok" and r["name"] == "myrepo"
        assert os.path.isdir(r["path"])

    def test_url_names(self, world):
        assert world.inst._url_to_install_name("https://x.dev/alice/proj.git") == "alice_proj"
        assert world.inst._url_to_install_name("git@x.dev:alice/proj.git") == "alice_proj"
        # 无 author 段 → 回退 cache key（非 [A-Za-z0-9_-] 全部转 _）
        assert world.inst._url_to_install_name("proj.git") == "proj_git"

    def test_cache_key(self, world):
        k = world.inst._url_to_cache_key("https://x.dev/a/b.git?x=1")
        assert "/" not in k and ":" not in k and len(k) <= 64
        long = "u" * 100
        assert len(world.inst._url_to_cache_key(long)) == 64


# ---------------------------------------------------------------------------
# install 完整流（假 git）
# ---------------------------------------------------------------------------

def _fake_git(world, monkeypatch, src=None):
    """把 git 三件套换成「建 cache 树 + 把 src 拷进 cache」的假实现。"""
    def fake_clone(self, url, dest, branch):
        bd = os.path.join(dest, branch)
        os.makedirs(os.path.join(bd, ".git"), exist_ok=True)
        act = os.path.join(bd, "actions")
        os.makedirs(act, exist_ok=True)
        with open(os.path.join(act, "demo.actus.md"), "w", encoding="utf-8") as f:
            f.write(_ACT)
        return (0, "", "")

    def fake_fetch(self, dest, branch):
        return (0, "", "")

    for name in ("_git_clone", "_git_fetch", "_git_checkout_branch",
                 "_git_checkout_tag", "_git_checkout_commit"):
        monkeypatch.setattr(ActionInstaller, name, fake_clone if name == "_git_clone" else fake_fetch)


class TestInstallFlow:
    def test_install_ok_and_manifest(self, world, monkeypatch):
        _fake_git(world, monkeypatch)
        r = world.inst.install("https://x.dev/alice/repo1.git", scope="sandbox")
        assert r["status"] == "ok" and r["actions"] == ["myapp.demo"]
        assert r["action_count"] == 1
        assert r["scope"] == "sandbox" and r["scope_written"] is True
        assert r["config_preserved"] == []
        # 清单已记录
        assert world.inst.is_installed(repo_url="https://x.dev/alice/repo1.git")

    def test_install_clone_fail(self, world, monkeypatch):
        def bad_clone(self, url, dest, branch):
            return (128, "", "fatal: not found")

        monkeypatch.setattr(ActionInstaller, "_git_clone", bad_clone)
        r = world.inst.install("https://x.dev/a/bad.git")
        assert r["status"] == "error" and "Git clone failed" in r["message"]

    def test_install_fetch_fail(self, world, monkeypatch):
        # 先制造已有缓存目录（cache key 与 registry 同规：非 [A-Za-z0-9_-] 全转 _），
        # 再让 fetch 失败
        cache_branch = world.cache / "https___x_dev_alice_repo2_git" / "main" / ".git"
        cache_branch.mkdir(parents=True)

        def bad_fetch(self, dest, branch):
            return (1, "", "network down")

        monkeypatch.setattr(ActionInstaller, "_git_fetch", bad_fetch)
        r = world.inst.install("https://x.dev/alice/repo2.git")
        assert r["status"] == "error" and "Git fetch failed" in r["message"]

    def test_install_gate_blocks_before_copytree(self, world, monkeypatch):
        def fake_clone(self, url, dest, branch):
            bd = os.path.join(dest, branch)
            os.makedirs(os.path.join(bd, ".git"), exist_ok=True)
            act = os.path.join(bd, "actions")
            os.makedirs(act, exist_ok=True)
            with open(os.path.join(act, "demo.actus.md"), "w", encoding="utf-8") as f:
                f.write(_with_vis("internal"))
            return (0, "", "")

        monkeypatch.setattr(ActionInstaller, "_git_clone", fake_clone)
        r = world.inst.install("https://x.dev/a/internalrepo.git")
        assert r["status"] == "error" and r["code"] == "visibility_denied"
        # gate 在 copytree 之前：安装目录里不应该有东西
        assert list(os.listdir(world.install)) == []

    def test_reinstall_preserves_user_scope(self, world, monkeypatch):
        _fake_git(world, monkeypatch)
        url = "https://x.dev/alice/repo3.git"
        r1 = world.inst.install(url, scope="sandbox")
        assert r1["scope_written"] is True
        # 用户手改
        (world.install / "alice_repo3" / ".actus.scope").write_text("trusted", encoding="utf-8")
        r2 = world.inst.install(url, scope="sandbox")
        assert r2["status"] == "ok"
        assert r2["config_preserved"] == [".actus.scope"]
        assert (world.install / "alice_repo3" / ".actus.scope").read_text() == "trusted"

    def test_reinstall_overwrite_config(self, world, monkeypatch):
        _fake_git(world, monkeypatch)
        url = "https://x.dev/alice/repo4.git"
        world.inst.install(url, scope="sandbox")
        (world.install / "alice_repo4" / ".actus.scope").write_text("trusted", encoding="utf-8")
        r2 = world.inst.install(url, scope="sandbox", overwrite_config=True)
        assert r2["config_preserved"] == []
        assert (world.install / "alice_repo4" / ".actus.scope").read_text() == "sandbox"


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------

class TestUninstall:
    def test_requires_url_or_name(self, world):
        assert world.inst.uninstall()["status"] == "error"

    def test_traversal_name_rejected(self, world):
        r = world.inst.uninstall(name="..")
        assert r["status"] == "error" and "越出安装目录" in r["message"]

    def test_not_installed(self, world):
        r = world.inst.uninstall(name="ghost")
        assert r["status"] == "error" and "Not installed" in r["message"]

    def test_not_in_manifest_refused_without_force(self, world, monkeypatch):
        d = world.install / "manual"
        d.mkdir()
        (d / "user.txt").write_text("user data", encoding="utf-8")
        r = world.inst.uninstall(name="manual")
        assert r["status"] == "error" and "拒绝删除" in r["message"]
        assert d.exists()

    def test_force_removes_unlisted(self, world):
        d = world.install / "manual"
        d.mkdir()
        (d / "user.txt").write_text("user data", encoding="utf-8")
        r = world.inst.uninstall(name="manual", force=True)
        assert r["status"] == "ok" and r["forced"] is True
        assert not d.exists()

    def test_listed_manifest_removed(self, world, monkeypatch):
        _fake_git(world, monkeypatch)
        url = "https://x.dev/alice/repo5.git"
        world.inst.install(url)
        r = world.inst.uninstall(repo_url=url)
        assert r["status"] == "ok" and r["manifest_removed"] is True
        assert world.inst.is_installed(repo_url=url) is False

    def test_uninstall_uses_basename(self, world):
        r = world.inst.uninstall(name="sub/dir/thing")
        # 名字清洗后 "thing" 不存在 → Not installed（而非越界报错）
        assert "Not installed" in r["message"]


# ---------------------------------------------------------------------------
# update / sync_all
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_not_installed(self, world):
        assert world.inst.update(name="ghost")["status"] == "error"

    def test_update_reinstalls_with_manifest(self, world, monkeypatch):
        _fake_git(world, monkeypatch)
        url = "https://x.dev/alice/repo6.git"
        world.inst.install(url, scope="sandbox")
        r = world.inst.update(repo_url=url)
        assert r["status"] == "ok" and r["branch"] == "main"

    def test_sync_all_empty(self, world):
        assert world.inst.sync_all() == []

    def test_sync_all_entries(self, world, monkeypatch):
        _fake_git(world, monkeypatch)
        url = "https://x.dev/alice/repo7.git"
        world.inst.install(url)
        results = world.inst.sync_all()
        assert len(results) == 1
        assert results[0]["url"] == url
        assert results[0]["result"]["status"] == "ok"

    def test_sync_all_skips_manifest_without_url(self, world):
        # 手写一条没有 url 的清单 → sync_all 跳过（不炸、不装）
        manifest_dir = world.cache / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "orphan.json").write_text(
            json.dumps({"cache_key": "orphan"}), encoding="utf-8")
        assert world.inst.sync_all() == []


# ---------------------------------------------------------------------------
# rollback / check_update（假 run_cmd_safe）
# ---------------------------------------------------------------------------

class _R:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestRollback:
    def test_not_installed(self, world):
        assert world.inst.rollback(name="ghost")["status"] == "error"

    def test_local_path_missing(self, world):
        from vools.actus.registry import ActionRegistry
        reg = ActionRegistry(cache_dir=str(world.cache))
        reg.record_installation("https://x.dev/a/gone.git", str(world.tmp / "deleted"),
                                branch="main")
        r = world.inst.rollback(repo_url="https://x.dev/a/gone.git", version=0)
        assert r["status"] == "error" and "Local path not found" in r["message"]

    def test_rollback_ok(self, world, monkeypatch):
        from vools.actus.registry import ActionRegistry
        d = world.install / "rb"
        d.mkdir()
        reg = ActionRegistry(cache_dir=str(world.cache))
        reg.record_installation("https://x.dev/a/rb.git", str(d), branch="main")
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            if cmd[1] == "log":
                return _R(0, "ccc333 head\nddd444 prev\neee555 old\n", "")
            return _R(0, "", "")

        monkeypatch.setattr(inst_mod, "run_cmd_safe", fake_run)
        r = world.inst.rollback(repo_url="https://x.dev/a/rb.git", version=1)
        assert r["status"] == "ok" and r["commit"] == "ddd444"
        assert ["git", "checkout", "ddd444"] in calls

    def test_git_log_fail(self, world, monkeypatch):
        from vools.actus.registry import ActionRegistry
        d = world.install / "rb2"
        d.mkdir()
        ActionRegistry(cache_dir=str(world.cache)).record_installation(
            "https://x.dev/a/rb2.git", str(d), branch="main")
        monkeypatch.setattr(inst_mod, "run_cmd_safe",
                            lambda cmd, **kw: _R(128, "", "fatal"))
        r = world.inst.rollback(repo_url="https://x.dev/a/rb2.git", version=0)
        assert r["status"] == "error" and "Git log failed" in r["message"]

    def test_version_not_found(self, world, monkeypatch):
        from vools.actus.registry import ActionRegistry
        d = world.install / "rb3"
        d.mkdir()
        ActionRegistry(cache_dir=str(world.cache)).record_installation(
            "https://x.dev/a/rb3.git", str(d), branch="main")
        monkeypatch.setattr(inst_mod, "run_cmd_safe",
                            lambda cmd, **kw: _R(0, "ccc333 head\n", ""))
        r = world.inst.rollback(repo_url="https://x.dev/a/rb3.git", version=5)
        assert r["status"] == "error" and "Version 5 not found" in r["message"]

    def test_checkout_fail(self, world, monkeypatch):
        from vools.actus.registry import ActionRegistry
        d = world.install / "rb4"
        d.mkdir()
        ActionRegistry(cache_dir=str(world.cache)).record_installation(
            "https://x.dev/a/rb4.git", str(d), branch="main")

        def fake_run(cmd, **kw):
            return _R(1, "", "conflict") if cmd[1] == "checkout" else _R(0, "a1 h\n", "")

        monkeypatch.setattr(inst_mod, "run_cmd_safe", fake_run)
        r = world.inst.rollback(repo_url="https://x.dev/a/rb4.git", version=0)
        assert r["status"] == "error" and "Checkout failed" in r["message"]

    def test_exception_caught(self, world, monkeypatch):
        from vools.actus.registry import ActionRegistry
        d = world.install / "rb5"
        d.mkdir()
        ActionRegistry(cache_dir=str(world.cache)).record_installation(
            "https://x.dev/a/rb5.git", str(d), branch="main")

        def boom(cmd, **kw):
            raise RuntimeError("git exploded")

        monkeypatch.setattr(inst_mod, "run_cmd_safe", boom)
        r = world.inst.rollback(repo_url="https://x.dev/a/rb5.git", version=0)
        assert r["status"] == "error" and "git exploded" in r["message"]


class TestCheckUpdate:
    def _setup(self, world):
        from vools.actus.registry import ActionRegistry
        d = world.install / "cu"
        d.mkdir()
        ActionRegistry(cache_dir=str(world.cache)).record_installation(
            "https://x.dev/a/cu.git", str(d), branch="main")
        return str(d)

    def test_not_installed(self, world):
        assert world.inst.check_update(name="ghost")["status"] == "error"

    def test_unknown_when_both_missing(self, world, monkeypatch):
        self._setup(world)
        monkeypatch.setattr(inst_mod, "run_cmd_safe",
                            lambda cmd, **kw: _R(1, "", "err"))
        r = world.inst.check_update(repo_url="https://x.dev/a/cu.git")
        assert r["status"] == "unknown" and r["has_update"] is None
        assert "本地" in r["message"] and "远端" in r["message"]

    def test_no_update(self, world, monkeypatch):
        self._setup(world)
        monkeypatch.setattr(inst_mod, "run_cmd_safe",
                            lambda cmd, **kw: _R(0, "abc123\n" if cmd[1] == "rev-parse" else "abc123\tHEAD\n", ""))
        r = world.inst.check_update(repo_url="https://x.dev/a/cu.git")
        assert r["status"] == "ok" and r["has_update"] is False

    def test_has_update(self, world, monkeypatch):
        self._setup(world)
        monkeypatch.setattr(inst_mod, "run_cmd_safe",
                            lambda cmd, **kw: _R(0, "old1\n" if cmd[1] == "rev-parse" else "new2\tHEAD\n", ""))
        r = world.inst.check_update(repo_url="https://x.dev/a/cu.git")
        assert r["status"] == "ok" and r["has_update"] is True

    def test_remote_missing_only(self, world, monkeypatch):
        self._setup(world)
        monkeypatch.setattr(inst_mod, "run_cmd_safe",
                            lambda cmd, **kw: _R(0, "abc123\n", "") if cmd[1] == "rev-parse" else _R(0, "", ""))
        r = world.inst.check_update(repo_url="https://x.dev/a/cu.git")
        assert r["status"] == "unknown" and "远端" in r["message"]

    def test_exception(self, world, monkeypatch):
        self._setup(world)

        def boom(cmd, **kw):
            raise OSError("no git")

        monkeypatch.setattr(inst_mod, "run_cmd_safe", boom)
        r = world.inst.check_update(repo_url="https://x.dev/a/cu.git")
        assert r["status"] == "error" and "no git" in r["message"]

    def test_local_path_not_found(self, world):
        from vools.actus.registry import ActionRegistry
        gone = world.tmp / "gone_dir"
        gone.mkdir()
        ActionRegistry(cache_dir=str(world.cache)).record_installation(
            "https://x.dev/a/cu2.git", str(gone), branch="main")
        import shutil as _sh
        _sh.rmtree(str(gone))
        r = world.inst.check_update(repo_url="https://x.dev/a/cu2.git")
        assert r["status"] == "error" and "Local path not found" in r["message"]


class TestInstallRefKinds:
    """tag/commit 路径：clone 假、checkout 走真身（_run_git 用假 run_cmd_safe）。"""

    def _patch(self, world, monkeypatch):
        def fake_clone(self, url, dest, branch):
            bd = os.path.join(dest, branch)
            os.makedirs(os.path.join(bd, ".git"), exist_ok=True)
            act = os.path.join(bd, "actions")
            os.makedirs(act, exist_ok=True)
            with open(os.path.join(act, "demo.actus.md"), "w", encoding="utf-8") as f:
                f.write(_ACT)
            return (0, "", "")

        monkeypatch.setattr(ActionInstaller, "_git_clone", fake_clone)
        monkeypatch.setattr(inst_mod, "run_cmd_safe",
                            lambda cmd, **kw: _R(0, "", ""))

    def test_install_by_tag(self, world, monkeypatch):
        self._patch(world, monkeypatch)
        r = world.inst.install("https://x.dev/alice/tagrepo.git", tag="v1.0")
        assert r["status"] == "ok" and r["tag"] == "v1.0"

    def test_install_by_commit(self, world, monkeypatch):
        self._patch(world, monkeypatch)
        r = world.inst.install("https://x.dev/alice/commitrepo.git",
                               commit="abc1234")
        assert r["status"] == "ok" and r["commit"] == "abc1234"

    def test_fetch_real_body(self, world, monkeypatch):
        self._patch(world, monkeypatch)
        # 缓存已存在 → install 走 _git_fetch 真身（.git 目录在）
        r = world.inst.install("https://x.dev/alice/fetchrepo.git")
        assert r["status"] == "ok"
        r2 = world.inst.install("https://x.dev/alice/fetchrepo.git")
        assert r2["status"] == "ok"


# ---------------------------------------------------------------------------
# 查询 / 路径发现
# ---------------------------------------------------------------------------

class TestQueries:
    def test_list_installed(self, world):
        assert world.inst.list_installed() == []

    def test_get_install_path(self, world):
        d = world.install / "alice_proj"
        d.mkdir()
        assert world.inst.get_install_path(name="alice_proj") == str(d)
        assert world.inst.get_install_path(name="ghost") is None
        assert world.inst.get_install_path(name="..") is None
        assert world.inst.get_install_path() is None
        assert world.inst.is_installed(name="alice_proj") is True

    def test_discover_actions_dirs(self, world):
        assert world.inst.discover_actions_dirs() == []
        (world.install / "a1" / "actions").mkdir(parents=True)
        (world.install / "a2").mkdir()
        dirs = world.inst.discover_actions_dirs()
        assert dirs == [os.path.join(str(world.install), "a1", "actions")]

    def test_discover_install_dir_missing(self, world):
        import shutil as _sh
        _sh.rmtree(str(world.install))
        assert world.inst.discover_actions_dirs() == []

    def test_resolve_action_path(self, world, monkeypatch):
        import vools.actus.resolver as resolver
        (world.install / "a1" / "actions").mkdir(parents=True)
        monkeypatch.setattr(resolver, "find_action_file",
                            lambda aid, d: os.path.join(d, "x.actus.md") if "a1" in d else None)
        assert world.inst.resolve_action_path("a.b") == os.path.join(
            str(world.install), "a1", "actions", "x.actus.md")
        monkeypatch.setattr(resolver, "find_action_file", lambda aid, d: None)
        assert world.inst.resolve_action_path("a.b") is None

    def test_resolve_action_path_import_error(self, world, monkeypatch):
        monkeypatch.setitem(sys.modules, "vools.actus.resolver", None)
        assert world.inst.resolve_action_path("a.b") is None


# ---------------------------------------------------------------------------
# scope 权限
# ---------------------------------------------------------------------------

class TestScope:
    def test_get_scope_missing(self, world):
        assert world.inst.get_scope(name="ghost") is None
        assert world.inst.get_scope(name="..") is None
        assert world.inst.get_scope() is None

    def test_get_scope_roundtrip(self, world):
        d = world.install / "s1"
        d.mkdir()
        (d / ".actus.scope").write_text("trusted\n", encoding="utf-8")
        assert world.inst.get_scope(name="s1") == "trusted"

    def test_set_scope(self, world):
        d = world.install / "s2"
        d.mkdir()
        assert world.inst.set_scope("sandbox", name="s2") is True
        assert world.inst.get_scope(name="s2") == "sandbox"
        assert world.inst.set_scope("x", name="ghost") is False
        assert world.inst.set_scope("x", name="..") is False
        assert world.inst.set_scope("x") is False


# ---------------------------------------------------------------------------
# _run_git
# ---------------------------------------------------------------------------

class TestRunGit:
    def test_ok(self, world, monkeypatch):
        monkeypatch.setattr(inst_mod, "run_cmd_safe", lambda c, **k: _R(0, "out", "err"))
        assert world.inst._run_git(["git", "x"]) == (0, "out", "err")

    def test_timeout(self, world, monkeypatch):
        monkeypatch.setattr(inst_mod, "run_cmd_safe", lambda c, **k: _R(-9))
        rc, _, err = world.inst._run_git(["git", "x"])
        assert rc == -1 and "timed out" in err

    def test_git_missing(self, world, monkeypatch):
        monkeypatch.setattr(inst_mod, "run_cmd_safe", lambda c, **k: _R(-1, "", "FileNotFoundError"))
        rc, _, err = world.inst._run_git(["git", "x"])
        assert rc == -1 and "Git not found" in err

    def test_exception(self, world, monkeypatch):
        def boom(c, **k):
            raise ValueError("bad")

        monkeypatch.setattr(inst_mod, "run_cmd_safe", boom)
        rc, _, err = world.inst._run_git(["git", "x"])
        assert rc == -1 and err == "bad"

    def test_git_fetch_not_a_repo(self, world, tmp_path):
        rc, _, err = world.inst._git_fetch(str(tmp_path / "no"), "main")
        assert rc == -1 and "Not a git repository" in err

    def test_checkout_branch_missing_repo_is_noop(self, world, tmp_path):
        world.inst._git_checkout_branch(str(tmp_path / "no"), "main")  # 不抛

    def test_checkout_tag_missing_repo_is_noop(self, world, tmp_path):
        world.inst._git_checkout_tag(str(tmp_path / "no"), "main", "v1")  # 不抛

    def test_checkout_commit_missing_repo_is_noop(self, world, tmp_path):
        world.inst._git_checkout_commit(str(tmp_path / "no"), "main", "abc")  # 不抛


# ---------------------------------------------------------------------------
# scope / visibility 配置保护
# ---------------------------------------------------------------------------

class TestWriteScopeConfig:
    def test_first_write(self, tmp_path, world):
        assert world.inst._write_scope_config(str(tmp_path), "sandbox") is True
        assert (tmp_path / ".actus.scope").read_text() == "sandbox"

    def test_idempotent_same(self, tmp_path, world):
        world.inst._write_scope_config(str(tmp_path), "sandbox")
        assert world.inst._write_scope_config(str(tmp_path), "sandbox") is False

    def test_preserve_user_value(self, tmp_path, world):
        (tmp_path / ".actus.scope").write_text("trusted", encoding="utf-8")
        assert world.inst._write_scope_config(str(tmp_path), "sandbox") is False
        assert (tmp_path / ".actus.scope").read_text() == "trusted"

    def test_overwrite_explicit(self, tmp_path, world):
        (tmp_path / ".actus.scope").write_text("trusted", encoding="utf-8")
        assert world.inst._write_scope_config(str(tmp_path), "sandbox",
                                              overwrite=True) is True
        assert (tmp_path / ".actus.scope").read_text() == "sandbox"

    def test_unreadable_existing_falls_through_to_write(self, tmp_path, world, monkeypatch):
        real_open = open

        def fake_open(path, mode="r", *a, **kw):
            if str(path).endswith(".actus.scope") and "r" in str(mode):
                raise OSError("locked")
            return real_open(path, mode, *a, **kw)

        monkeypatch.setattr("builtins.open", fake_open)
        assert world.inst._write_scope_config(str(tmp_path), "sandbox") is True


class TestWriteVisibilityConfig:
    def test_first_write(self, tmp_path, world):
        assert world.inst._write_visibility_config(
            str(tmp_path), "private", author="me", team="t1") is True
        data = json.loads((tmp_path / ".actus.visibility").read_text())
        assert data["visibility"] == "private" and data["author"] == "me"

    def test_idempotent(self, tmp_path, world):
        world.inst._write_visibility_config(str(tmp_path), "private", author="me")
        assert world.inst._write_visibility_config(
            str(tmp_path), "private", author="me") is False

    def test_preserve_user_value(self, tmp_path, world):
        (tmp_path / ".actus.visibility").write_text(
            json.dumps({"visibility": "private", "author": "me", "team": ""}),
            encoding="utf-8")
        assert world.inst._write_visibility_config(
            str(tmp_path), "public", author="me") is False
        assert json.loads((tmp_path / ".actus.visibility").read_text())["visibility"] == "private"

    def test_bad_json_falls_through(self, tmp_path, world):
        (tmp_path / ".actus.visibility").write_text("{bad json", encoding="utf-8")
        assert world.inst._write_visibility_config(str(tmp_path), "public") is True


# ---------------------------------------------------------------------------
# install_with_visibility
# ---------------------------------------------------------------------------

class TestInstallWithVisibility:
    def test_private_requires_author(self, world):
        r = world.inst.install_with_visibility("https://x.dev/a/p.git", visibility="private")
        assert r["status"] == "error" and "author" in r["message"]

    def test_private_author_mismatch(self, world):
        r = world.inst.install_with_visibility(
            "https://x.dev/a/p.git", visibility="private",
            author="alice", current_user="mallory")
        assert r["status"] == "error" and "denied" in r["message"]

    def test_private_empty_current_user_passes(self, world, monkeypatch):
        # 现状佐证：current_user 为空时私有检查被跳过（author != '' and ''）→ 放行
        _fake_git(world, monkeypatch)
        r = world.inst.install_with_visibility(
            "https://x.dev/a/p.git", visibility="private", author="alice",
            current_user="")
        assert r["status"] == "ok"
        assert r["visibility"] == "private" and r["author"] == "alice"

    def test_ok_writes_visibility(self, world, monkeypatch):
        _fake_git(world, monkeypatch)
        r = world.inst.install_with_visibility(
            "https://x.dev/alice/v1.git", visibility="team", author="alice",
            team="core", registry_name="team")
        assert r["status"] == "ok"
        assert r["visibility_written"] is True
        data = json.loads((world.install / "alice_v1" / ".actus.visibility").read_text())
        assert data["team"] == "core"

    def test_install_fail_passthrough(self, world, monkeypatch):
        def fail(self, *a, **kw):
            return {"status": "error", "message": "clone dead"}

        monkeypatch.setattr(ActionInstaller, "install", fail)
        r = world.inst.install_with_visibility("https://x.dev/a/v2.git")
        assert r["status"] == "error"

    def test_existing_visibility_preserved(self, world, monkeypatch):
        _fake_git(world, monkeypatch)
        d = world.install / "alice_v3"
        d.mkdir()
        (d / ".actus.visibility").write_text(
            json.dumps({"visibility": "private", "author": "me", "team": ""}),
            encoding="utf-8")
        r = world.inst.install_with_visibility(
            "https://x.dev/alice/v3.git", visibility="public", author="me")
        assert r["status"] == "ok" and r["visibility_written"] is False


# ---------------------------------------------------------------------------
# _load_manifest
# ---------------------------------------------------------------------------

class TestLoadManifest:
    def test_by_url(self, world):
        from vools.actus.registry import ActionRegistry
        d = world.install / "m1"
        d.mkdir()
        ActionRegistry(cache_dir=str(world.cache)).record_installation(
            "https://x.dev/a/m1.git", str(d), branch="main")
        m = world.inst._load_manifest(repo_url="https://x.dev/a/m1.git")
        assert m and m["url"] == "https://x.dev/a/m1.git"

    def test_by_name_cache_key(self, world):
        from vools.actus.registry import ActionRegistry
        d = world.install / "m2"
        d.mkdir()
        ActionRegistry(cache_dir=str(world.cache)).record_installation(
            "https://x.dev/a/m2.git", str(d), branch="main")
        m = world.inst._load_manifest(name="https___x_dev_a_m2_git")
        assert m and m["url"].endswith("m2.git")

    def test_by_name_local_path_suffix(self, world):
        from vools.actus.registry import ActionRegistry
        d = world.install / "m3"
        d.mkdir()
        ActionRegistry(cache_dir=str(world.cache)).record_installation(
            "https://x.dev/a/m3.git", str(d), branch="main")
        m = world.inst._load_manifest(name="m3")
        assert m is not None

    def test_no_match(self, world):
        assert world.inst._load_manifest(name="ghost") is None
        assert world.inst._load_manifest() is None


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

class _Recorder(ActionInstaller):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        type(self).calls = kw


class TestConvenience:
    """便捷函数只做一件事：构造 ActionInstaller 并转发同参方法。

    打桩策略：整体替换模块命名空间里的 ActionInstaller（patch inst_mod 的名字，
    而不是往类上挂属性）——套件里其他文件可能触发 vools.actus.installer 重载，
    类身份会换；模块命名空间替换对两个身份都生效。
    """

    def _swap_fn(self, monkeypatch, fn, **methods):
        """对便捷函数的 __globals__ 直接换 ActionInstaller。

        便捷函数读的是**它自己模块字典**里的 ActionInstaller；套件里其他
        文件可能引发 vools.actus.installer 重载，模块身份会换 —— 对
        fn.__globals__ 打桩对任何身份都命中（__globals__ 就是那个字典）。
        """
        class Fake:
            def __init__(self, *a, **kw):
                pass

        for name, impl in methods.items():
            setattr(Fake, name, impl)
        monkeypatch.setitem(fn.__globals__, "ActionInstaller", Fake)
        return Fake

    def test_install_actions(self, monkeypatch):
        calls = {}

        def fake(self, url, **kw):
            calls.update(url=url, kw=kw)
            return {"status": "ok"}

        fn0 = __import__('vools.actus.installer', fromlist=['install_actions']).install_actions
        self._swap_fn(monkeypatch, fn0, install=fake)
        r = fn0("https://x.dev/a/cf.git", scope="trusted")
        assert r["status"] == "ok"
        # 便捷函数把 branch/tag/commit 显式透传（缺省 main/None/None）
        assert calls["url"] == "https://x.dev/a/cf.git"
        assert calls["kw"] == {"branch": "main", "commit": None,
                               "scope": "trusted", "tag": None}

    def test_install_with_visibility_fn(self, monkeypatch):
        calls = {}

        def fake(self, url, **kw):
            calls.update(url=url, kw=kw)
            return {"status": "ok"}

        fn = __import__('vools.actus.installer', fromlist=['install_with_visibility']).install_with_visibility
        self._swap_fn(monkeypatch, fn, install_with_visibility=fake)
        r = fn("https://x.dev/a/cf2.git", visibility="team", current_user="u")
        assert r["status"] == "ok"
        assert calls["url"] == "https://x.dev/a/cf2.git"
        # 便捷函数把全部形参显式透传（未传的用缺省值填充）
        assert calls["kw"] == {"author": "", "branch": "main", "commit": None,
                               "current_user": "u", "registry_name": "public",
                               "scope": None, "tag": None, "team": "",
                               "visibility": "team"}

    def test_resolve_action_path_fn(self, monkeypatch):
        fn = __import__('vools.actus.installer',
                        fromlist=['resolve_action_path']).resolve_action_path
        self._swap_fn(monkeypatch, fn,
                      resolve_action_path=lambda self, aid: f"/found/{aid}")
        assert fn("a.b") == "/found/a.b"

    def test_uninstall_actions_fn(self, monkeypatch):
        seen = {}

        def fake(self, repo_url=None, name=None, force=False):
            seen.update(name=name, force=force)
            return {"status": "ok"}

        fn = __import__('vools.actus.installer', fromlist=['uninstall_actions']).uninstall_actions
        self._swap_fn(monkeypatch, fn, uninstall=fake)
        assert fn(name="x", force=True)["status"] == "ok"
        assert seen == {"name": "x", "force": True}

    def test_update_actions_fn(self, monkeypatch):
        seen = {}

        def fake(self, repo_url=None, name=None):
            seen.update(name=name)
            return {"status": "ok"}

        fn = __import__('vools.actus.installer', fromlist=['update_actions']).update_actions
        self._swap_fn(monkeypatch, fn, update=fake)
        assert fn(name="x")["status"] == "ok"
        assert seen == {"name": "x"}

    def test_list_installed_actions_fn(self, monkeypatch):
        fn = __import__('vools.actus.installer',
                        fromlist=['list_installed_actions']).list_installed_actions
        self._swap_fn(monkeypatch, fn, list_installed=lambda self: [{"x": 1}])
        assert fn() == [{"x": 1}]
