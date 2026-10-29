"""`publisher.py` 契约测试（第 29 轮，T0r4 覆盖率补齐 + 审计钉桩）。

覆盖三件事：
  1. **dry_run 真不写盘**（审计判据"dry-run 真不写"）
  2. **真发布流程**：复制 → registry 刷新 → 幂等/冲突语义
  3. **门禁 fail-closed**：缺 Omega 语料必须拒绝发布，不能"当没门禁"

另把审计发现的 3 个问题（P1 静默吞生成器异常 / P2 dry_run 报告未标注计划值 /
P3 sigma 门异常逃逸）用"当前行为"钉住 —— 将来修好后这些用例会红，提醒同步更新。

隔离：所有用例把 `ACTUS_REPO_ROOT` / `ACTUS_META_DIR` / `HOME` 指到 tmp，
**不碰真实用户目录**；不发任何网络请求（GitHub 客户端全部用假 opener）。
"""
import json
import os
import shutil

import pytest

from vools.actus import publisher as P


# ═══════════════════════════════════════════════════════════════════
# 夹具：临时 dev 仓 + 合法动作（全部隔离）
# ═══════════════════════════════════════════════════════════════════


def _write_action(path, action_id="actus.pub.demo", extra_cfg="", body=None):
    cfg = {
        "id": action_id, "name": action_id.rsplit(".", 1)[-1], "version": "1.0.0",
        "trust": "sandbox", "entry": "main", "description": "d", "author": "t",
        "kind": "exec", "platform": ["desktop"],
    }
    if extra_cfg:
        cfg.update(extra_cfg)
    text = ("```json #!cfg\n" + json.dumps(cfg, ensure_ascii=False) + "\n```\n\n"
            + (body or "```python #!run tag=main\nimport json\nprint(json.dumps({'ok': 1}))\n```\n"))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """把仓库/元数据/HOME 全部指到 tmp —— 用例绝不触碰真实用户目录。"""
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    repo = tmp_path / "repo"
    for d in (home, meta, repo):
        d.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    return {"home": home, "meta": meta, "repo": repo, "tmp": tmp_path}


@pytest.fixture
def dev_repo(isolated_env):
    """一个合法的 actus 开发仓：`<name>.actus/` + registry 文件。"""
    root = isolated_env["tmp"] / "myrepo.actus"
    (root / "actions").mkdir(parents=True)
    (root / "actus.registry.json").write_text(
        json.dumps({"actions": [], "owner": "tester"}), encoding="utf-8")
    return root


@pytest.fixture
def action_file(isolated_env):
    src = isolated_env["tmp"] / "src"
    src.mkdir()
    return _write_action(str(src / "demo.actus.md"))


def _snapshot(root):
    out = set()
    for dp, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            out.add(os.path.relpath(os.path.join(dp, name), root).replace(os.sep, "/"))
    return out


# ═══════════════════════════════════════════════════════════════════
# ① dry_run 真不写盘
# ═══════════════════════════════════════════════════════════════════


def test_dry_run_writes_nothing_to_repo(dev_repo, action_file):
    """退步了会怎样：`dry_run=True` 却把动作拷进仓里（或刷新了 registry）——
    "预览发布"变成真实副作用，用户在没确认前就改了目标仓（假 dry-run）。
    """
    before = _snapshot(dev_repo)
    result = P.publish_local_only([action_file], str(dev_repo), dry_run=True, gate=False)
    after = _snapshot(dev_repo)

    assert result["status"] == "ok"
    assert result["dry_run"] is True
    assert after == before, "dry_run 不得改动目标仓，新增: %s" % sorted(after - before)


def test_dry_run_reports_planned_dest_not_existing_file(dev_repo, action_file):
    """退步了会怎样：审计 P2 —— dry_run 的 `published[].dest` 是**计划值**却与真发布
    同名字段，调用方拿它当"已存在的产物"就会报假成功。本用例钉住该语义：
    dest 有值、文件不存在。将来产品把它改名为 `planned_dest`（或加 dry_run 标注）时，
    本用例会红，提醒同步更新调用方。
    """
    result = P.publish_local_only([action_file], str(dev_repo), dry_run=True, gate=False)
    dest = result["published"][0]["planned_dest"]      # P2 修复后：dry_run 用 planned_dest
    assert dest, "dry_run 报告应给出计划目标路径"
    assert not (dev_repo / dest).exists(), \
        "dry_run 的 planned_dest 竟然真的存在 → 预览产出了实际文件（假 dry-run）"


# ═══════════════════════════════════════════════════════════════════
# ② 真实发布流程
# ═══════════════════════════════════════════════════════════════════


def test_real_publish_copies_file_and_refreshes_registry(dev_repo, action_file):
    """退步了会怎样：真发布只拷文件却不刷新 registry（仓清单里查不到新动作），
    或只写 registry 却没拷文件（清单指向不存在的动作）—— 两者都会让 `repo.status()`
    与真实内容脱节。
    """
    result = P.publish_local_only([action_file], str(dev_repo), dry_run=False, gate=False)

    assert result["status"] == "ok", result
    dest = dev_repo / result["published"][0]["dest"]
    assert dest.is_file(), "真发布必须把动作文件落进仓"
    assert dest.read_bytes() == open(action_file, "rb").read()

    registry = json.loads((dev_repo / "actus.registry.json").read_text(encoding="utf-8"))
    ids = {a.get("id") for a in registry.get("actions") or []}
    assert "actus.pub.demo" in ids, "registry 未收录刚发布的动作: %s" % sorted(ids)
    assert registry.get("owner") == "tester"


def test_identical_republish_is_idempotent_noop(dev_repo, action_file):
    """退步了会怎样：重复发布同一版本被判冲突（或反过来重复写盘把 mtime 改掉）——
    前者让正常重跑失败，后者让"没变化"也产生 diff。
    """
    first = P.publish_local_only([action_file], str(dev_repo), dry_run=False, gate=False)
    dest = dev_repo / first["published"][0]["dest"]
    mtime_before = dest.stat().st_mtime_ns
    content_before = dest.read_bytes()

    second = P.publish_local_only([action_file], str(dev_repo), dry_run=False, gate=False)

    assert second["status"] == "ok", "内容相同的重复发布必须幂等成功: %r" % (second.get("error"),)
    assert dest.read_bytes() == content_before
    assert dest.stat().st_mtime_ns == mtime_before, "幂等 no-op 不应重写文件（mtime 变了）"


def test_conflicting_republish_refused_unless_force(dev_repo, action_file):
    """退步了会怎样：同名不同内容被静默覆盖 —— 仓里既有动作被替换，作者毫不知情
    （这正是 `_copy_into_repo` 审计修掉的旧行为）。必须先拒绝、force 才允许。
    """
    P.publish_local_only([action_file], str(dev_repo), dry_run=False, gate=False)
    with open(action_file, "a", encoding="utf-8") as fh:
        fh.write("\n<!-- changed -->\n")

    with pytest.raises(P.PublishError) as exc:
        P.publish_local_only([action_file], str(dev_repo), dry_run=False, gate=False)
    assert exc.value.code == "action_exists"

    forced = P.publish_local_only([action_file], str(dev_repo), dry_run=False,
                                  gate=False, force=True)
    assert forced["status"] == "ok"
    dest = dev_repo / forced["published"][0]["dest"]
    assert b"<!-- changed -->" in dest.read_bytes(), "force=True 应真的覆盖"


def test_directory_input_expands_to_all_action_files(dev_repo, isolated_env):
    """退步了会怎样：目录入参只发布一个文件（或把非动作文件也当动作）——
    批量发布漏项/多项，作者无法预期。
    """
    src = isolated_env["tmp"] / "multi"
    src.mkdir()
    _write_action(str(src / "a.actus.md"), action_id="actus.pub.a")
    _write_action(str(src / "b.actus.md"), action_id="actus.pub.b")
    (src / "notes.txt").write_text("not an action", encoding="utf-8")

    result = P.publish_local_only([str(src)], str(dev_repo), dry_run=True, gate=False)

    # 本用例只验"目录展开"（Red 2 诊断：展开本身正确）。action_id 需要过三重门才解析，
    # gate=False 时由 P4 的 cfg 解析兜底；id 断言放到专门的 P4 用例里。
    dests = sorted(p["planned_dest"] for p in result["published"])   # dry_run 用 planned_dest
    assert dests == ["actions/a.actus.md", "actions/b.actus.md"], dests


# ═══════════════════════════════════════════════════════════════════
# ③ 入参与目标仓校验（失败路径）
# ═══════════════════════════════════════════════════════════════════


def test_non_action_file_rejected(isolated_env):
    """退步了会怎样：非动作后缀的文件被当动作发布 → 仓里多出无法解析的垃圾。
    """
    junk = isolated_env["tmp"] / "junk.txt"
    junk.write_text("x", encoding="utf-8")
    with pytest.raises(P.PublishError) as exc:
        P.validate_action_paths([str(junk)])
    assert exc.value.code == "action_invalid"


def test_empty_directory_rejected(isolated_env):
    """退步了会怎样：空目录被当成"发布成功、0 个动作" → 用户以为发完了。
    """
    empty = isolated_env["tmp"] / "empty"
    empty.mkdir()
    with pytest.raises(P.PublishError) as exc:
        P.validate_action_paths([str(empty)])
    assert exc.value.code == "action_not_found"


def test_missing_path_rejected(isolated_env):
    """退步了会怎样：路径不存在时报"没有动作"而不是"路径不存在" → 排查方向被带偏。
    """
    with pytest.raises(P.PublishError) as exc:
        P.validate_action_paths([str(isolated_env["tmp"] / "nope.actus.md")])
    assert exc.value.code == "action_not_found"


def test_publish_requires_explicit_route(isolated_env, action_file):
    """退步了会怎样：不指定 to_repo/to_pr/to_fork 就默默执行某个默认途径 ——
    发布是外向动作，途径必须显式。
    """
    with pytest.raises(P.PublishError) as exc:
        P.publish([action_file])
    assert exc.value.code == "param_invalid"


# ═══════════════════════════════════════════════════════════════════
# ④ 门禁 fail-closed（缺语料必须拒绝，不能降级成装饰）
# ═══════════════════════════════════════════════════════════════════


def test_missing_omega_corpus_blocks_publish(dev_repo, action_file):
    """退步了会怎样：缺 Omega 语料时把门禁当"通过"→ 未验证的动作被发布，
    发布门槛降级成装饰（docs/41 §A3 明确 blocked 也算不通过）。
    """
    gate = P.triple_gate(action_file)
    assert gate["gates"]["omega"]["status"] == "blocked"
    assert gate["publishable"] is False

    result = P.publish_local_only([action_file], str(dev_repo), dry_run=False, gate=True)
    assert result["status"] == "failed"
    assert result["published"] == [], "门禁未过时一个文件都不许发布（防半截发布）"
    assert not (dev_repo / "actions" / "demo.actus.md").exists()


def test_omega_corpus_present_makes_gate_passable(dev_repo, action_file):
    """退步了会怎样：有语料却仍判 blocked（门禁永远拦）→ 没人能发布；
    或反过来语料损坏也判 pass（门禁形同虚设）。
    """
    # Red 3 诊断：_find_omega_spec 只认 actions/{private,public}/omega/<name>.spec.json、
    # actions/**/omega/…、或与动作文件同目录；放仓根是找不到的。
    spec_dir = dev_repo / "actions" / "private" / "omega"
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec = spec_dir / "demo.spec.json"
    spec.write_text(json.dumps({"cases": [{"in": {}, "out": {}}]}), encoding="utf-8")
    gate = P.triple_gate(action_file, actions_dir=str(dev_repo))
    assert gate["gates"]["omega"]["status"] == "pass", gate["gates"]["omega"]
    assert gate["gates"]["omega"]["cases"] == 1


def test_audit_p1_registry_generator_failure_is_currently_silent(dev_repo, action_file, monkeypatch):
    """退步了会怎样：审计 P1 —— `_refresh_registry` 用 `except Exception: generated={}`
    兜底，生成器崩了发布仍报 ok 且**回执里没有任何提示**（静默降级）。
    本用例钉住"当前确实静默"。等产品补 `registry_warning` 字段后，本用例应改为
    断言该字段存在。
    """
    from vools.actus import registry as R

    def boom(self, *a, **k):
        raise RuntimeError("模拟 registry 生成器失败")

    monkeypatch.setattr(R.ActionRegistry, "build_from_directory", boom)
    result = P.publish_local_only([action_file], str(dev_repo), dry_run=False, gate=False)

    assert result["status"] == "ok", "生成器失败目前不阻断发布（这正是待裁决点）"
    assert not any(k in result for k in ("warnings", "warning", "registry_warning")), \
        "如果产品已补上 registry 告警字段，请更新本用例（P1 已修复）"


def test_sigma_gate_internal_error_becomes_structured_fail(dev_repo, isolated_env, monkeypatch):
    """退步了会怎样：sigma 引擎内部抛错时异常**穿透** `triple_gate`（P3 修复前的
    行为）→ 调用方拿不到结构化 gate 结果，只能看到一句 RuntimeError，无法判断
    "是动作不合格还是引擎坏了"。修复后必须收敛成 `sigma.status='fail'` 且带原因。
    """
    from vools.actus import sigma as SIG

    def boom(*a, **k):
        raise RuntimeError("sigma 引擎内部错")

    monkeypatch.setattr(SIG, "verify_module", boom)
    src = isolated_env["tmp"] / "src2"
    src.mkdir()
    act = src / "sig.actus.md"
    _write_action(
        str(act), action_id="actus.pub.sig",
        body=("```sigma\nmodule demo { }\n```\n\n"
              "```python #!run tag=main\nprint('{}')\n```\n"))

    gate = P.triple_gate(str(act))          # 不得抛异常
    sigma = gate["gates"]["sigma"]
    assert sigma["status"] == "fail", sigma
    assert "Sigma 校验引擎内部异常" in sigma["reason"]
    assert gate["publishable"] is False


# ═══════════════════════════════════════════════════════════════════
# ⑤ GitHub 客户端：凭据不回显 / 错误结构化（不发真实网络）
# ═══════════════════════════════════════════════════════════════════


def test_github_client_without_token_raises_auth_required(isolated_env):
    """退步了会怎样：无凭据时直接发请求（401 才报错）或静默返回空 ——
    前者把认证问题推迟到远端、后者让"没发出去"看起来像成功。
    """
    client = P.GitHubClient(token=None)
    with pytest.raises(P.PublishError) as exc:
        client.repo("o", "n")
    assert exc.value.code == "auth_required"


def test_github_http_error_is_structured_and_token_not_echoed(isolated_env, monkeypatch):
    """退步了会怎样：把 token 写进错误回执（凭据泄漏到日志/UI），
    或 HTTP 错误被当成成功（假发布）。
    """
    import urllib.error
    import urllib.request

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = P.GitHubClient(token="SECRET-TOKEN-XYZ")
    resp = client.repo("o", "n")

    assert resp["ok"] is False
    assert resp["status"] == 401
    assert "SECRET-TOKEN-XYZ" not in json.dumps(resp), "回执里泄漏了 token"


def test_github_client_injected_opener_receives_token(isolated_env):
    """退步了会怎样：注入的 opener 收不到 token（测试替身与真实路径行为分叉），
    或注入路径根本没被用上。
    """
    seen = {}

    def opener(method, url, body, token):
        seen.update({"method": method, "url": url, "token": token})
        return {"ok": True, "status": 200, "json": {}}

    P.GitHubClient(token="tk", opener=opener).repo("o", "n")
    assert seen["method"] == "GET"
    assert seen["url"].endswith("/repos/o/n")
    assert seen["token"] == "tk"


# ═══════════════════════════════════════════════════════════════════
# ⑥ P1/P2/P4 回归（第 31 轮修复后应绿）
# ═══════════════════════════════════════════════════════════════════


def test_p1_registry_generator_output_is_merged_into_canonical(dev_repo, action_file):
    """退步了会怎样（P1）：`_refresh_registry` 又按旧顺序先读 canonical（发布前的旧表）
    并 break → 生成器刚写出的 `.actus.registry.json` 被忽略、随后被规范化删除，
    registry 一条不增。表现是"发布成功但仓清单里查不到"。

    **这条不走 publish 的兼容路径**：直接调 `_refresh_registry(repo, [])`
    （action_ids 为空，只能靠生成器发现），确保测的是合并逻辑本身。
    """
    # 动作先落进仓（模拟"文件已在仓里、registry 还没有"）
    dest_dir = dev_repo / "actions"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(action_file, dest_dir / "demo.actus.md")

    repo_obj = P.ActionRepo(str(dev_repo), owner="tester")
    data = P._refresh_registry(repo_obj, [])

    ids = [a.get("id") for a in data.get("actions") or []]
    assert "actus.pub.demo" in ids, "生成器发现的动作没被并进 registry: %s" % ids
    canonical = json.loads((dev_repo / "actus.registry.json").read_text(encoding="utf-8"))
    assert "actus.pub.demo" in {a.get("id") for a in canonical.get("actions") or []}
    assert not (dev_repo / ".actus.registry.json").exists(), \
        "归一化应删掉点前缀副本（同一份清单只留一个文件）"


def test_p1_generated_and_canonical_entries_are_both_preserved(dev_repo, action_file, isolated_env):
    """退步了会怎样（P1 方案 A 的回退）：只读一份文件 → canonical 里"人工加的、
    磁盘上没有的条目"会在下次刷新时消失（被生成器结果整个替换掉）。
    """
    shutil.copyfile(action_file, dev_repo / "actions" / "demo.actus.md")
    manual = {"id": "actus.manual.keep", "source": "manual"}
    (dev_repo / "actus.registry.json").write_text(
        json.dumps({"actions": [manual], "owner": "tester"}), encoding="utf-8")
    # 生成器会写点前缀那份（含 demo），canonical 含 manual → 两份都必须保留
    repo_obj = P.ActionRepo(str(dev_repo), owner="tester")
    data = P._refresh_registry(repo_obj, [])
    ids = {a.get("id") for a in data.get("actions") or []}
    assert {"actus.pub.demo", "actus.manual.keep"} <= ids, ids


def test_p4_gate_false_resolves_action_id_from_cfg(dev_repo, action_file):
    """退步了会怎样（P4）：`gate=False` 时 published[].action_id 恒为 ''（改前取不到 id），
    registry 兜底也收不到 → "发布成功但仓清单不可见"。修复后必须从动作 cfg 解析出 id，
    并标明解析来源。
    """
    result = P.publish_local_only([action_file], str(dev_repo), dry_run=True, gate=False)
    entry = result["published"][0]
    assert entry["action_id"] == "actus.pub.demo", entry
    assert entry["id_resolution"] == "parsed", entry


def test_p4_unresolvable_id_is_explicit_not_silent(isolated_env):
    """退步了会怎样（P4b）：动作文件解析不出 id 时静默留空 → 调用方以为 registry 收了。
    必须显式标注 `id_resolution='unresolved'`。
    """
    src = isolated_env["tmp"] / "noid"
    src.mkdir()
    bad = src / "noid.actus.md"
    bad.write_text("```json #!cfg\n{\"name\": \"x\"}\n```\n\n"
                   "```python #!run tag=main\nprint('{}')\n```\n", encoding="utf-8")
    repo = isolated_env["tmp"] / "r2.actus"
    (repo / "actions").mkdir(parents=True)
    (repo / "actus.registry.json").write_text(json.dumps({"actions": []}), encoding="utf-8")

    result = P.publish_local_only([str(bad)], str(repo), dry_run=True, gate=False)
    entry = result["published"][0]
    assert entry["action_id"] == ""
    assert entry["id_resolution"] == "unresolved", entry


def test_p2_dry_run_uses_planned_dest_not_dest(dev_repo, action_file):
    """退步了会怎样（P2）：dry_run 与真发布共用 `dest` 字段名 —— 预览时它是"计划值"、
    真发布时是"实际路径"，调用方无法区分，容易把预览当产物（假成功温床）。
    """
    dry = P.publish_local_only([action_file], str(dev_repo), dry_run=True, gate=False)
    dry_entry = dry["published"][0]
    assert "planned_dest" in dry_entry and dry_entry["planned_dest"] == "actions/demo.actus.md"
    assert "dest" not in dry_entry, "dry_run 不得给出与真发布同名的 dest"

    real = P.publish_local_only([action_file], str(dev_repo), dry_run=False, gate=False)
    real_entry = real["published"][0]
    assert real_entry["dest"] == "actions/demo.actus.md"
    assert "planned_dest" not in real_entry, "真发布不应再给 planned_dest"
    assert (dev_repo / real_entry["dest"]).is_file()


# ═══════════════════════════════════════════════════════════════════
# ⑦ 统一入口的三条途径（不触网：全部 dry_run / 缺凭据的失败路径）
# ═══════════════════════════════════════════════════════════════════


def test_publish_to_local_dev_repo_dry_run(dev_repo, action_file):
    """退步了会怎样：`publish(to_repo=<本地已存在的 dev 仓>)` 不被识别成本地仓
    （被当成 owner/name 去 clone）→ 离线/本地联调场景直接失败。
    """
    result = P.publish([action_file], to_repo=str(dev_repo), dry_run=True, gate=False)
    assert result["status"] == "ok", result
    assert result["route"] == "own_repo"
    assert result["dry_run"] is True
    assert result["published"][0]["action_id"] == "actus.pub.demo"


def test_publish_to_repo_missing_clone_reports_action_not_found(isolated_env, action_file):
    """退步了会怎样：本地没有克隆时静默"成功"或抛裸异常 → 用户不知道要先去 clone；
    或者在无网络环境里卡住等待。
    """
    result = P.publish([action_file], to_repo="someowner/somename.actus",
                       dry_run=True, gate=False)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "action_not_found"
    assert "克隆" in result["error"]["message"] or "clone" in result["error"]["message"]


def test_publish_push_without_token_fails_auth_required(dev_repo, action_file, monkeypatch):
    """退步了会怎样：push=True 但没有任何凭据时照样尝试 git push（卡在 credential
    提示上）或直接报成功（假发布）。必须先明确 `auth_required`。
    """
    monkeypatch.delenv(P.GITHUB_TOKEN_ENV, raising=False)
    result = P.publish([action_file], to_repo=str(dev_repo), dry_run=False,
                       gate=False, push=True, meta_dir=str(dev_repo.parent))
    assert result["status"] == "failed"
    assert result["error"]["code"] == "auth_required"


def test_publish_pr_dry_run_plans_without_network(action_file):
    """退步了会怎样：`to_pr` 在 dry_run 下仍然调用 GitHub API（无凭据就炸，
    有凭据就在用户没确认前建了 PR）。dry_run 必须只给计划。
    """
    result = P.publish([action_file], to_pr="owner/actus", dry_run=True, gate=False,
                       title="t", fork_owner="me", branch="b")
    assert result["status"] == "ok"
    assert result["route"] == "pr"
    planned = result["pr"]["planned"]
    assert planned["head"] == "me:b" and planned["base"] == "master"


def test_publish_fork_dry_run_reports_route(action_file, dev_repo):
    """退步了会怎样：fork 途径在 dry_run 下就去调用 fork API（副作用外溢），
    或 route 标记成 own_repo 让调用方无法区分。
    """
    result = P.publish([action_file], to_fork=str(dev_repo), dry_run=True, gate=False)
    assert result["status"] == "ok", result
    assert result["route"] == "fork"
    assert result["dry_run"] is True


def test_publish_to_repo_real_run_copies_and_updates_registry(dev_repo, action_file):
    """退步了会怎样：经统一入口真发布时，内层 `publish_local_only` 的结果没有透传
    （外层恒 ok、内层已 failed）→ 调用方以为发布成功，仓里却没有文件。
    """
    result = P.publish([action_file], to_repo=str(dev_repo), dry_run=False, gate=False)
    assert result["status"] == "ok", result
    assert (dev_repo / "actions" / "demo.actus.md").is_file()
    registry = json.loads((dev_repo / "actus.registry.json").read_text(encoding="utf-8"))
    assert "actus.pub.demo" in {a.get("id") for a in registry.get("actions") or []}
    assert "push" not in result, "未请求 push 时不应出现 push 字段（避免误以为推送过）"
