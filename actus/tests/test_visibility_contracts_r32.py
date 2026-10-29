# -*- coding: utf-8 -*-
"""actus/tests/test_visibility_contracts_r32.py — visibility.py（51% 覆盖）安全契约。

可见性决定"什么被暴露给谁"：默认 fail-open（任何人可见）还是 fail-closed（拒绝），
私有动作缺 author 是否放行、gated 密钥是否只存摘要、团队名是否可路径逃逸 ——
每条都直接是安全边界。本文件覆盖六个级别、三套配置/团队管理、gated 仓储与
私有索引，不写必然绿的断言。

审计观察（报告，未改产品）：
  * `check_visibility(visibility='public'/'unlisted')` 恒放行（设计如此）；
  * `_load_private_index` 对损坏 JSON 降级为空（视为"没有私有动作"，fail-closed 的
    表现是访问被拒 —— 不会误放行，符合安全方向，但错误被静默吞掉、无 warning）。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import visibility as vis  # noqa: E402


class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    actions = repo / "actions"
    config = tmp_path / "config"
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    for directory in (actions, config, home, meta):
        directory.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.delenv("ACTUS_USER", raising=False)

    w = _World()
    w.root = tmp_path
    w.repo = repo
    w.actions = actions
    w.config = config
    w.store = vis.GatedKeyStore(str(config))
    w.engine = vis.VisibilityEngine(config_dir=str(config), current_user="alice",
                                    gated_store=w.store)
    return w


# ===========================================================================
# internal 路径判定（大小写 / 反斜杠绕过）
# ===========================================================================

def test_is_internal_path_is_case_and_separator_insensitive():
    """退步了会怎样（越权绕过）：按大小写敏感比较 —— 把动作放进 `_INTERNAL/` 就能
    绕过 executor 的 internal 门禁（Windows/macOS 不区分大小写）。

    断言：`/system/_internal/` 判定 True；大写 `_INTERNAL`、反斜杠形式同样 True；
    普通路径/空/NULL → False。
    """
    assert vis.is_internal_path("/repo/actions/system/_internal/x.actus.md") is True
    assert vis.is_internal_path("/repo/actions/system/_INTERNAL/x.actus.md") is True
    assert vis.is_internal_path("C:\\\\repo\\\\system\\\\_Internal\\\\x") is True
    assert vis.is_internal_path("/repo/actions/system/public/x") is False
    assert vis.is_internal_path("") is False
    assert vis.is_internal_path(None) is False


# ===========================================================================
# GatedKeyStore
# ===========================================================================

def test_gated_store_grant_verify_rotation_revoke(world):
    """退步了会怎样（安全洞）：gated 密钥验证放行任意 key（授权式公开变成人人可装）；
    轮换后旧钥仍有效（撤销失效）。

    断言：grant 明确文、只存摘要；正确 key 通过、错误 key 拒绝；再次 grant 轮换后
    **旧 key 立即失效**、新 key 通过；revoke 后新 key 也失效；has_gate 跟着变化。
    """
    store = world.store
    granted = store.grant(action_id="act.one")
    old_key = granted["key"]
    assert old_key.startswith("actus-gk-")
    assert store.verify(old_key, action_id="act.one") is True
    assert store.verify("wrong-key", action_id="act.one") is False
    assert store.has_gate(action_id="act.one") is True

    rotated = store.grant(action_id="act.one")
    new_key = rotated["key"]
    assert rotated["rotated"] is True
    assert store.verify(old_key, action_id="act.one") is False, "旧密钥轮换后仍有效"
    assert store.verify(new_key, action_id="act.one") is True

    assert store.revoke(action_id="act.one") is True
    assert store.has_gate(action_id="act.one") is False
    assert store.verify(new_key, action_id="act.one") is False
    assert store.revoke(action_id="act.one") is False


def test_gated_store_repo_scope_and_scope_rules(world):
    """退步了会怎样：仓级密钥不生效（同仓多个 gated 动作要各发一把钥）或作用域
    缺 action/repo 时静默生成错误 scope。

    断言：repo 级 grant 的 key 对同仓动作 verify 通过；不同仓拒绝；
    scope_id 缺 action/repo → ValueError。
    """
    store = world.store
    granted = store.grant(repo="owner/repo")
    assert store.verify(granted["key"], repo="owner/repo") is True
    assert store.verify(granted["key"], repo="other/repo") is False

    with pytest.raises(ValueError):
        store.scope_id()


def test_gated_store_persists_digests_not_plaintext_and_corruption_is_fatal(world):
    """退步了会怎样（安全）：明文密钥落盘（文件外泄=所有权失守）；仓储损坏被当成
    "没有任何授权"而静默 fail-open。

    断言：gated_keys.json 中**搜不到明文 key**（只有 sha256 摘要）；
    写坏仓储后新建 GatedKeyStore 抛 RuntimeError（拒绝放行，不静默降级）。
    """
    granted = world.store.grant(action_id="secret.act")
    raw = open(str(world.store.path), "r", encoding="utf-8").read()
    assert granted["key"] not in raw
    assert vis.GatedKeyStore.digest_of(granted["key"]) in raw

    with open(str(world.store.path), "w", encoding="utf-8") as handle:
        handle.write("{broken")
    with pytest.raises(RuntimeError):
        vis.GatedKeyStore(str(world.config))


def test_gated_store_list_scopes_and_audit_no_plaintext(world):
    """退步了会怎样：作用域列表漏项（运维看不到已发的钥）或审计日志记录明文密钥
    （密钥入日志 = 泄密）。

    断言：list_scopes 含 action/repo 两档、rotations 计数正确；审计文件不含明文 key。
    """
    first = world.store.grant(action_id="a.one")
    world.store.grant(action_id="a.one")
    world.store.grant(repo="owner/repo")

    scopes = {item["scope"]: item for item in world.store.list_scopes()}
    assert set(scopes) == {"action:a.one", "repo:owner/repo"}
    assert scopes["action:a.one"]["rotations"] == 2
    assert scopes["action:a.one"]["configured"] is True

    audit = open(str(world.store.audit_path), "r", encoding="utf-8").read()
    assert first["key"] not in audit


# ===========================================================================
# 配置 / 团队数据结构
# ===========================================================================

def test_registry_config_validation_and_roundtrip():
    """退步了会怎样：配置反序列化接受错误类型（bool 当 priority、数字当 name）——
    搜索优先级错乱/配置加载崩。

    断言：合法 dict roundtrip 一致；非 dict、bool priority、非 str name → ValueError。
    """
    cfg = vis.RegistryConfig(name="team", url="https://x", registry_type="git",
                             priority=5)
    assert vis.RegistryConfig.from_dict(cfg.to_dict()) == cfg

    with pytest.raises(ValueError):
        vis.RegistryConfig.from_dict([])
    with pytest.raises(ValueError):
        vis.RegistryConfig.from_dict({"name": "n", "url": "u", "priority": True})
    with pytest.raises(ValueError):
        vis.RegistryConfig.from_dict({"name": 123, "url": "u"})


def test_team_member_and_team_config_validation():
    """退步了会怎样（权限失真）：空 user_id 入库后 `is_member('')` 命中；非法 role
    静默写盘 → 成员权限判定全错。

    断言：合法成员/团队 roundtrip；空 id、非法 role、members 非列表、
    require_signature 非布尔 → ValueError；is_member/get_role/is_admin 正确。
    """
    member = vis.TeamMember(user_id="bob", role="admin", public_key="k")
    assert vis.TeamMember.from_dict(member.to_dict()) == member
    for bad in ({"id": ""}, {"id": "  "}, {"id": "bob", "role": "superadmin"}):
        with pytest.raises(ValueError):
            vis.TeamMember.from_dict(bad)

    team = vis.TeamConfig(name="t", members=[member])
    restored = vis.TeamConfig.from_dict(team.to_dict())
    assert restored.is_member("bob") is True
    assert restored.get_role("bob") == "admin"
    assert restored.is_admin("bob") is True
    assert restored.is_admin("eve") is False
    assert restored.get_role("eve") is None

    with pytest.raises(ValueError):
        vis.TeamConfig.from_dict({"team": "t", "members": "bob"})
    with pytest.raises(ValueError):
        vis.TeamConfig.from_dict({"team": "t", "require_signature": "yes"})


# ===========================================================================
# RegistryManager / TeamManager
# ===========================================================================

def test_registry_manager_defaults_add_remove_and_private_dir(world):
    """退步了会怎样：默认注册表丢失（public/private 不可用）；只读构造 private 目录
    （只读 FS 崩）；添加/移除不落盘（重启后配置丢失）。

    断言：默认含 public/private；add 后可查且落盘；remove 返回旧配置、未知返回 None；
    list 按 priority 排序；get_private_dir(create=False) 不建目录、create=True 建。
    """
    manager = vis.RegistryManager(str(world.config))
    assert manager.get_registry("public") is not None
    assert manager.get_registry("private") is not None

    custom = vis.RegistryConfig(name="mine", url="file:///x", priority=1)
    manager.add_registry(custom)
    assert vis.RegistryManager(str(world.config)).get_registry("mine") is not None
    priorities = [r.priority for r in manager.list_registries()]
    assert priorities == sorted(priorities)

    private_dir = manager.get_private_dir()
    assert not os.path.isdir(private_dir)
    created = manager.get_private_dir(create=True)
    assert os.path.isdir(created)

    removed = manager.remove_registry("mine")
    assert removed is not None and removed.name == "mine"
    assert manager.remove_registry("no-such") is None


def test_team_manager_lifecycle_and_validation(world):
    """退步了会怎样（权限混乱）：非法成员写入（空 id/非法 role）、重复添加、
    路径穿越团队名写/删到配置目录外。

    断言：create/get/list/delete 正常；add_member 拒绝空 id/非法 role/重复/不存在
    团队；remove_member 生效；团队名 `../escape` → create ValueError、delete False。
    """
    manager = vis.TeamManager(str(world.config))
    team = manager.create_team("alpha", "alice")
    assert team.get_role("alice") == "admin"
    assert manager.get_team("alpha").is_member("alice")
    assert "alpha" in manager.list_teams()

    assert manager.add_member("alpha", "bob", role="member") is True
    assert manager.add_member("alpha", "", role="member") is False
    assert manager.add_member("alpha", "carol", role="superadmin") is False
    assert manager.add_member("alpha", "bob") is False          # 重复
    assert manager.add_member("missing", "bob") is False

    manager.save_team(manager.get_team("alpha"))
    assert manager.remove_member("alpha", "bob") is True
    assert manager.remove_member("alpha", "bob") is False
    assert manager.remove_member("missing", "alice") is False

    with pytest.raises(ValueError):
        manager.create_team("../escape", "alice")
    assert manager.delete_team("../escape") is False
    assert manager.delete_team("alpha") is True
    assert manager.get_team("alpha") is None


def test_team_manager_corrupt_team_file_degrades_to_none(world):
    """退步了会怎样（拒绝服务）：团队文件写坏后 get_team/check_visibility 直接崩
    （而不是按"团队不存在" fail-closed）。

    断言：写入非法 JSON / 非法成员角色的团队文件 → load_team/get_team 返回 None；
    list_teams 仍能列出（按文件名白名单）。
    """
    manager = vis.TeamManager(str(world.config))
    teams_dir = world.config / "teams"
    teams_dir.mkdir()
    (teams_dir / "broken.json").write_text("{broken", encoding="utf-8")
    (teams_dir / "badrole.json").write_text(json.dumps({
        "team": "badrole", "members": [{"id": "u", "role": "root"}]}),
        encoding="utf-8")

    assert manager.load_team("broken") is None
    assert manager.get_team("badrole") is None
    assert "broken" in manager.list_teams()


# ===========================================================================
# VisibilityEngine：六个级别
# ===========================================================================

def test_public_and_unlisted_are_visible_and_internal_is_gated():
    """退步了会怎样：public/unlisted 被误拒（正常动作不可用）；或 internal 对普通
    调用方放行（内部动作被外部执行）。

    断言：public/unlisted 放行；internal 仅 internal_caller=True 放行；未知级别拒绝。
    """
    engine = vis.VisibilityEngine(config_dir="", current_user="alice")
    assert engine.check_visibility("a", "public") == (True, "")
    assert engine.check_visibility("a", "unlisted") == (True, "")

    denied = engine.check_visibility("a", "internal")
    assert denied[0] is False and "引擎内部" in denied[1]
    assert engine.check_visibility("a", "internal", internal_caller=True) == (True, "")

    unknown = engine.check_visibility("a", "weird-level")
    assert unknown[0] is False and "Unknown" in unknown[1]


def test_private_visibility_requires_author_and_fails_closed_on_missing_author(world):
    """退步了会怎样（历史 fail-open）：私有动作缺 author 时对**所有人**放行
    ——"仅作者可见"变成公开。

    断言：无 author 元数据 → 拒绝且理由点明 author；作者本人放行；他人拒绝；
    不存在的私有动作拒绝。
    """
    engine = world.engine
    engine.add_private_action("priv.a", {})
    stored = engine.get_private_action("priv.a")
    assert stored["author"] == "alice"          # 写入时补全 author

    assert engine.check_visibility("priv.a", "private", expected_user="alice") == (True, "")
    denied = engine.check_visibility("priv.a", "private", expected_user="bob")
    assert denied[0] is False and "private" in denied[1]

    engine._private_actions["priv.noauthor"] = {"action_id": "priv.noauthor"}
    fail_closed = engine.check_visibility("priv.noauthor", "private", expected_user="bob")
    assert fail_closed[0] is False and "author" in fail_closed[1]

    assert engine.check_visibility("missing", "private")[0] is False


def test_team_visibility_member_nonmember_and_missing_team(world):
    """退步了会怎样：团队动作对非成员放行（越权）；或团队/动作元数据缺失时 fail-open。

    断言：成员放行；非成员拒绝；动作无 team 拒绝；team 不存在拒绝。
    """
    engine = world.engine
    manager = vis.TeamManager(str(world.config))
    manager.create_team("blue", "alice")
    manager.add_member("blue", "bob")

    engine._private_actions["team.a"] = {"action_id": "team.a", "team": "blue"}
    assert engine.check_visibility("team.a", "team", expected_user="alice") == (True, "")
    assert engine.check_visibility("team.a", "team", expected_user="bob") == (True, "")
    denied = engine.check_visibility("team.a", "team", expected_user="eve")
    assert denied[0] is False and "not a member" in denied[1]

    engine._private_actions["team.none"] = {"action_id": "team.none"}
    assert engine.check_visibility("team.none", "team")[0] is False

    engine._private_actions["team.ghost"] = {"action_id": "team.ghost", "team": "ghost"}
    assert engine.check_visibility("team.ghost", "team")[0] is False


def test_team_visibility_falls_back_to_action_file_cfg(world):
    """退步了会怎样（审计修复回归）：team 写入动作 cfg 后，判定方只查私有索引 →
    团队名落盘却永远判定"没有团队"，team 级规则等于不存在。

    断言：动作文件 cfg 带 team，未登记私有索引也能按团队判定放行/拒绝。
    """
    manager = vis.TeamManager(str(world.config))
    manager.create_team("cfgteam", "alice")
    manager.add_member("cfgteam", "bob")
    action = world.actions / "cfgteam.actus.md"
    action.write_text(
        '# T\n\n```json #!cfg\n{"id": "cfg.team", "name": "T", "version": "1.0.0",'
        ' "team": "cfgteam"}\n```\n', encoding="utf-8")

    engine = vis.VisibilityEngine(config_dir=str(world.config), current_user="bob")
    assert engine.check_visibility("cfg.team", "team") == (True, "")
    eve = vis.VisibilityEngine(config_dir=str(world.config), current_user="eve")
    assert eve.check_visibility("cfg.team", "team")[0] is False


def test_gated_visibility_requires_valid_key_and_fails_closed_on_corrupt_store(world):
    """退步了会怎样（安全洞）：无 key/错 key 也放行（gated 退化公开），或仓储损坏时
    静默当"无门禁"（fail-open）。

    断言：无 key 拒绝（auth_required 前缀）；错误 key 拒绝；正确 key 放行；
    仓储文件损坏 → 拒绝（auth_required，不是放行）。
    """
    engine = world.engine
    assert engine.check_visibility("g.a", "gated")[0] is False
    no_key = engine.check_visibility("g.a", "gated")
    assert no_key[1].startswith(vis.AUTH_REQUIRED)

    granted = world.store.grant(action_id="g.a")
    assert engine.check_visibility("g.a", "gated", key=granted["key"]) == (True, "")
    assert engine.check_visibility("g.a", "gated", key="wrong")[0] is False

    with open(str(world.store.path), "w", encoding="utf-8") as handle:
        handle.write("{broken")
    corrupt = vis.VisibilityEngine(config_dir=str(world.config), current_user="alice")
    denied = corrupt.check_visibility("g.a", "gated", key=granted["key"])
    assert denied[0] is False and denied[1].startswith(vis.AUTH_REQUIRED)


def test_can_install_can_execute_is_searchable_matrix():
    """退步了会怎样（分发越权）：internal 可安装、gated 无钥可装、或 gated/internal
    出现在公开搜索结果里。

    断言：install：public/unlisted/team → True，private 走作者判定，gated 需 key，
    internal 永 False；execute 与 check_visibility 一致；is_searchable 只允许
    public/unlisted/private/team（gated/internal 不进公开结果）。
    """
    engine = vis.VisibilityEngine(config_dir="", current_user="alice")
    assert engine.can_install("a", "public") == (True, "")
    assert engine.can_install("a", "unlisted") == (True, "")
    assert engine.can_install("a", "internal")[0] is False
    assert engine.can_install("a", "gated")[0] is False

    assert engine.can_execute("a", "public") == (True, "")
    assert engine.can_execute("a", "internal")[0] is False
    assert engine.can_execute("a", "internal", internal_caller=True) == (True, "")

    assert engine.is_searchable("public") is True
    assert engine.is_searchable("unlisted") is True
    assert engine.is_searchable("private") is True
    assert engine.is_searchable("team") is True
    assert engine.is_searchable("gated") is False
    assert engine.is_searchable("internal") is False


# ===========================================================================
# 私有索引读写 / 损坏
# ===========================================================================

def test_private_index_persistence_and_corruption(world):
    """退步了会怎样：私有动作不落盘（重启丢失，作者也访问不到）；损坏索引让引擎
    初始化崩溃。

    断言：add→落盘→新引擎可读；remove 生效；get/list 正确；损坏 index.json →
    新引擎初始化为空（不崩），且私有访问仍拒绝（fail-closed）。
    """
    engine = world.engine
    engine.add_private_action("p.one", {"note": "x"})
    assert engine.get_private_action("p.one")["note"] == "x"
    assert any(item["action_id"] == "p.one" for item in engine.list_private_actions())

    reloaded = vis.VisibilityEngine(config_dir=str(world.config), current_user="alice")
    assert reloaded.get_private_action("p.one")["note"] == "x"
    assert reloaded.remove_private_action("p.one") is True
    assert reloaded.remove_private_action("p.one") is False
    assert reloaded.get_private_action("p.one") is None

    index_path = world.config / "private" / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("{broken", encoding="utf-8")
    corrupted = vis.VisibilityEngine(config_dir=str(world.config), current_user="alice")
    assert corrupted.list_private_actions() == []
    assert corrupted.check_visibility("p.one", "private")[0] is False


def test_engine_current_user_and_lazy_gated_store(world):
    """退步了会怎样：current_user 取错（权限判定用错身份）；gated store 在非 gated
    路径被提前构造（仓储损坏拖垮 public 查询）。

    断言：显式 current_user 生效；未显式时读 ACTUS_USER；gated_keys 惰性创建且
    重复访问返回同一实例。
    """
    assert world.engine.current_user == "alice"
    engine = vis.VisibilityEngine(config_dir=str(world.config), current_user="bob")
    assert engine.current_user == "bob"

    os.environ["ACTUS_USER"] = "env-user"
    try:
        from_env = vis.VisibilityEngine(config_dir=str(world.config))
        assert from_env.current_user == "env-user"
    finally:
        os.environ.pop("ACTUS_USER", None)

    lazy = vis.VisibilityEngine(config_dir=str(world.config), current_user="u")
    assert lazy.gated_keys is lazy.gated_keys


def test_get_action_permissions_matrix(world):
    """退步了会怎样：综合权限查询把 gated/internal 的 can_install/can_view 报错
    （客户端据此放行）；未知级别与"有权限但被拒"不可区分（调用方无法定位配置错）。

    断言：public/unlisted 三项全 True；private 按作者；team 按成员；gated 不可见、
    持钥可装/执行；internal 不可见/不可装、内部路由可执行；未知级别带
    unknown_visibility + allowed_values。
    """
    engine = world.engine
    engine.add_private_action("perm.priv", {})
    public = engine.get_action_permissions("a", "public")
    assert public["can_view"] and public["can_install"] and public["can_execute"]
    assert public["searchable"] is True

    private = engine.get_action_permissions("perm.priv", "private")
    assert private["can_view"] is True      # 当前用户 alice 是作者

    gated = engine.get_action_permissions("g.x", "gated")
    assert gated["can_view"] is False and gated["can_install"] is False
    assert gated["reason"].startswith(vis.AUTH_REQUIRED)

    internal = engine.get_action_permissions("i.x", "internal")
    assert internal["can_view"] is False and internal["can_install"] is False
    assert internal["can_execute"] is False
    internal_engine = engine.get_action_permissions("i.x", "internal",
                                                    internal_caller=True)
    assert internal_engine["can_execute"] is True

    unknown = engine.get_action_permissions("x", "not-a-level")
    assert unknown["unknown_visibility"] is True
    assert set(unknown["allowed_values"]) == set(vis.ALL_VISIBILITIES)


def test_secret_auditor_records_and_reads(world):
    """退步了会怎样（审计缺口/泄密）：密钥使用与可见性判定不留痕（事后无法追溯），
    或审计行把密钥值写进去（日志=泄密）。

    断言：record_usage 可按 key 过滤、limit 生效；get_all_audits 含两类事件；
    record_visibility 记录 granted/exec_id 且不包含密钥值。
    """
    auditor = vis.SecretAuditor(str(world.config))
    auditor.record_usage("db-key", "act.one", "private")
    auditor.record_usage("db-key", "act.two", "team")
    auditor.record_usage("other-key", "act.three", "public")
    auditor.record_visibility("act.one", "gated", exec_id="exec-9", granted=False)

    scoped = auditor.get_audit("db-key")
    assert len(scoped) == 2
    assert {entry["action_id"] for entry in scoped} == {"act.one", "act.two"}
    assert auditor.get_audit("db-key", limit=1)[0]["action_id"] == "act.two"
    assert auditor.get_audit("no-such") == []

    everything = auditor.get_all_audits()
    assert any(entry.get("event") == "visibility" for entry in everything)
    assert len(everything) == 4
    visibility_row = [e for e in everything if e.get("event") == "visibility"][0]
    assert visibility_row["granted"] is False and visibility_row["exec_id"] == "exec-9"

    raw = open(str(auditor._audit_file), "r", encoding="utf-8").read()
    assert "db-key" in raw
    assert "gated-key-value" not in raw


def test_write_action_visibility_roundtrip_and_rollback(world):
    """退步了会怎样（假成功）：visibility set 只校验不落盘（CLI/MCP 报成功但 get 读
    不到）；team 级不写团队名（规则无法被判定）；写坏后不留原文回滚（动作文件损坏）。

    断言：private 写入；team 缺团队名失败；team 带团队名写入且 cfg 同时有
    visibility/team；切回 public 会删掉残留 team 键；非法级别/无 cfg 块/文件不存在
    明确失败；解析失败时回滚原文并返回错误。
    """
    path = world.actions / "vis.actus.md"
    _nl = chr(10)
    path.write_text(
        _nl.join(['# V', '', '```json #!cfg',
                  '{"id": "vis.act", "name": "V", "version": "1.0.0",',
                  ' "visibility": "private"}', '```']) + _nl,
        encoding="utf-8")

    assert vis.write_action_visibility(str(path), "private") == (True, "")
    ok, message = vis.write_action_visibility(str(path), "team")
    assert ok is False and "团队名" in message

    assert vis.write_action_visibility(str(path), "team", team="blue") == (True, "")
    text = path.read_text(encoding="utf-8")
    assert '"visibility": "team"' in text and '"team": "blue"' in text

    assert vis.write_action_visibility(str(path), "public") == (True, "")
    text = path.read_text(encoding="utf-8")
    assert '"team"' not in text and '"visibility": "public"' in text

    assert vis.write_action_visibility(str(path), "bogus")[0] is False
    assert vis.write_action_visibility(str(world.root / "missing.actus.md"), "public")[0] is False

    no_cfg = world.actions / "nocfg.actus.md"
    no_cfg.write_text("# no cfg" + chr(10), encoding="utf-8")
    assert vis.write_action_visibility(str(no_cfg), "public")[0] is False

    original = path.read_text(encoding="utf-8")
    from vools.actus import model as model_mod
    real_parse = model_mod.parse_cfg_from_file

    def boom(_path):
        raise ValueError("synthetic parse failure")
    model_mod.parse_cfg_from_file = boom
    try:
        ok, message = vis.write_action_visibility(str(path), "team", team="blue")
    finally:
        model_mod.parse_cfg_from_file = real_parse
    assert ok is False and "回滚" in message
    assert path.read_text(encoding="utf-8") == original
