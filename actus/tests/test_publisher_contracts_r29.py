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
    dest = result["published"][0]["dest"]
    assert dest, "dry_run 报告应给出计划目标路径"
    assert not (dev_repo / dest).exists(), \
        "dry_run 的 dest 竟然真的存在 → 预览产出了实际文件（假 dry-run）"


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

    ids = sorted(p["action_id"] for p in result["published"])
    assert ids == ["actus.pub.a", "actus.pub.b"], ids


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
    spec = dev_repo / "demo.spec.json"
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


def test_audit_p3_sigma_gate_internal_error_escapes(dev_repo, isolated_env, monkeypatch):
    """退步了会怎样：审计 P3 —— `_gate_sigma` 只接住 ImportError/OSError，sigma 引擎
    内部抛错会**逃出三门口**（`triple_gate` 抛异常而非返回结构化 gate 结果），
    调用方拿不到 `publishable/failed` 判据。本用例钉住当前行为，修复后应改为断言
    返回 sigma=fail。
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

    with pytest.raises(RuntimeError):
        P.triple_gate(str(act))


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
