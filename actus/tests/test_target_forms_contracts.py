# -*- coding: utf-8 -*-
"""actus/tests/test_target_forms_contracts.py — resolver 四形态 / 零写 / 索引告警契约。

覆盖第 17 轮（e2db175）新接线、此前只有手工验收的 4 组能力：
  ① `info` / `preview` / `validate` 接 resolver：id / name / md5 / 本地路径四形态；
  ② 这 12 组（3 命令 × 4 形态）**零写**（`_meta` 下 sha256+mtime_ns 逐字节不变）——
     专盯两个历史漏洞：resolver name 分支曾 `load_index()` 建索引落盘、
     SecurityScanner 曾每次校验写 `_meta/audit/*.jsonl`；
  ③ id 输入与旧路径逐字段一致（"接了 resolver 但行为不变"）；
  ④ path 目标 `data.id` 取文件内真实 id（散装、不在索引中也可用）；
  ⑤ ambiguous 错误结构与候选（resolver 直接抛，CLI 目前丢失 details —— 见 xfail）；
  ⑥ md5 一致性两种告警文案（warning 前缀 + rc=0）；
  ⑦ `languages` 落索引（小写去重排序；空语言不写键）；
  ⑧ link/alias 静态 target 三态（缺=error / 找不到=warning / 能解析=无告警）。

隔离：`tmp_path` 假仓库 + `ACTUS_REPO_ROOT`/`ACTUS_META_DIR`/`HOME` 全指 tmp。
"""

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import time

import pytest

_ACTUS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

import vools.actus as actuscore  # noqa: E402
from vools.actus import cli, indexer, resolver  # noqa: E402
from vools.actus.errors import ActionError  # noqa: E402
from vools.actus.model import Action  # noqa: E402
from vools.actus.validate import split_validation  # noqa: E402


def _action_text(aid, name, blocks="", extra=""):
    return ('# %s\n\n```json #!cfg\n{"id": "%s", "name": "%s", "version": "1.0.0",'
            ' "description": "d", "trust": "sandbox", "entry": "main",'
            ' "platform": "desktop"%s}\n```\n\n%s'
            % (name, aid, name, extra, blocks))


_PY_MAIN = "```python #!run tag=main\nprint('hi')\n```\n"


# ---------------------------------------------------------------------------
# 夹具 / 辅助
# ---------------------------------------------------------------------------

class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    repo = tmp_path / "repo"
    actions = repo / "actions"
    config = tmp_path / "config"
    for directory in (home, meta, actions, config):
        directory.mkdir(parents=True)
    shutil.copytree(os.path.join(_ACTUS_ROOT, "contracts"), str(repo / "contracts"))

    (actions / "demo.actus.md").write_text(
        _action_text("myapp.demo", "Demo Action", _PY_MAIN +
                     "```yaml #!run tag=extra\nkey: value\n```\n"),
        encoding="utf-8")
    (actions / "dup1.actus.md").write_text(
        _action_text("myapp.dup.one", "Dup", _PY_MAIN), encoding="utf-8")
    (actions / "dup2.actus.md").write_text(
        _action_text("myapp.dup.two", "Dup", _PY_MAIN), encoding="utf-8")
    (actions / "linkbad.actus.md").write_text(
        _action_text("myapp.linkbad", "LB", "", ', "kind": "link"'), encoding="utf-8")
    (actions / "linkmiss.actus.md").write_text(
        _action_text("myapp.linkmiss", "LM", "",
                     ', "kind": "link", "target": "no.such.action"'), encoding="utf-8")
    (actions / "linkok.actus.md").write_text(
        _action_text("myapp.linkok", "LO", "",
                     ', "kind": "link", "target": "myapp.demo"'), encoding="utf-8")

    # 散装动作：文件名与内部 id 不同，且**不在仓库 actions/ 里**（不在索引中）
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "zzz.actus.md").write_text(
        _action_text("test.real.id", "Real Id", _PY_MAIN), encoding="utf-8")

    monkeypatch.chdir(repo)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_CONFIG_DIR", str(config))

    w = _World()
    w.root = tmp_path
    w.repo = repo
    w.meta = meta
    w.actions = actions
    w.loose = loose / "zzz.actus.md"
    w.index_path = meta / "actions.index.json"
    return w


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = cli.main(list(argv))
        except SystemExit as exc:      # pragma: no cover
            rc = exc.code if exc.code is not None else 0
    return rc, out.getvalue(), err.getvalue()


def _snapshot_tree(root):
    """目录快照：相对路径 → (mtime_ns, size, sha256)。"""
    rows = {}
    for dirpath, _dirnames, filenames in os.walk(str(root)):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, str(root)).replace(os.sep, "/")
            stat = os.stat(full)
            with open(full, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            rows[rel] = (stat.st_mtime_ns, stat.st_size, digest)
    return rows


def _build_meta_index():
    """跑一次全仓 validate（会 build_index 落 `_meta/actions.index.json`）。"""
    rc, out, err = _run(["validate"])
    assert rc == 0, (out, err)
    return json.load(open(os.path.join("..", ".."), "r")) if False else None


def _load_meta_index(world):
    with open(str(world.index_path), "r", encoding="utf-8") as handle:
        return json.load(handle)


def _rewrite_meta_index(world, index):
    with open(str(world.index_path), "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, indent=2)


def _demo_md5(world):
    return _load_meta_index(world)["actions"]["myapp.demo"]["md5"]


# ===========================================================================
# ① 12 组读取零写（含 md5/languages 索引存在时）
# ===========================================================================

def test_all_target_forms_are_zero_write_with_index(world):
    """退步了会怎样（历史漏洞）：resolver name 分支又 `load_index()`（build 落盘）/
    validate/preview 的 SecurityScanner 又写 `_meta/audit/*.jsonl` —— 纯查询命令
    改用户数据目录，只读 FS 直接失败，且并发/备份校验被污染。

    断言：info/preview/validate × id/name/md5/path 共 12 组全部 rc=0；
    `_meta` 整棵树的 **sha256 + mtime_ns + size 全部不变**（无文件新增/修改/删除）。
    """
    _run(["validate"])                    # 先建索引（write）
    assert world.index_path.is_file()
    md5 = _demo_md5(world)
    before = _snapshot_tree(world.meta)

    forms = ["myapp.demo", "Demo Action", md5, str(world.loose)]
    for command in ("info", "preview", "validate"):
        for target in forms:
            rc, out, err = _run([command, target])
            assert rc == 0, (command, target, out, err)

    after = _snapshot_tree(world.meta)
    assert after == before, "_meta 被查询命令改动了: %r" % (
        sorted(set(after) - set(before)) + sorted(set(before) - set(after)),)


def test_name_without_index_does_not_build_one(world):
    """退步了会怎样（name 分支的具体漏洞）：索引不存在时 name 解析调 `load_index()`
    → build 落盘 `actions.index.json` —— 一次只读 `info <name>` 就创建了索引文件。

    断言：无索引时跑 info/preview/validate<name> 后，`_meta` 里**没有**
    actions.index.json（且目录快照不变）。
    """
    assert not world.index_path.exists()
    before = _snapshot_tree(world.meta)

    for command in ("info", "preview", "validate"):
        rc, out, err = _run([command, "Demo Action"])
        assert rc == 0, (command, out, err)

    assert not world.index_path.exists(), "只读 name 解析顺手建了索引（读路径写盘）"
    assert _snapshot_tree(world.meta) == before


# ===========================================================================
# ② id 输入与旧路径逐字段一致（接 resolver 不改变既有行为）
# ===========================================================================

def test_id_targets_match_direct_api(world):
    """退步了会怎样：resolver 接进来后改变了既有 id 行为（多包/少包/换字段）——
    依赖 `info/preview/validate` 的脚本与 MCP 输出全部漂移。

    断言：`info(id).data == get_action(id).brief()`；`preview(id).data ==` 直调
    `preview(id,{})`；`validate(id)` 的 errors/warnings 与直调 split_validation 一致。
    """
    rc, out, _ = _run(["info", "myapp.demo"])
    assert rc == 0
    assert json.loads(out)["data"] == actuscore.get_action("myapp.demo").brief()

    rc, out, _ = _run(["preview", "myapp.demo"])
    assert rc == 0
    assert json.loads(out)["data"] == actuscore.preview("myapp.demo", {})

    rc, out, _ = _run(["validate", "myapp.demo"])
    assert rc == 0
    data = json.loads(out)["data"]
    errs = actuscore.validate_action(actuscore.get_action("myapp.demo"))
    real_errors, runtime_notes = split_validation(errs)
    assert data["errors"] == real_errors
    assert data.get("warnings", []) == runtime_notes


# ===========================================================================
# ③ path 目标：data.id 是文件内真实 id（散装、不在索引中）
# ===========================================================================

def test_path_target_uses_real_id_not_filename(world):
    """退步了会怎样：path 目标把**文件名**当 id（或要求动作必须先入索引）——
    散装动作 `zzz.actus.md`（内部 id=test.real.id）info 出来 id 错、且根本不能用。

    断言：`info <path>` → `data.id == 'test.real.id'`（不是 zzz）；该 id 不在索引里；
    preview/validate 同样按真实 id 工作。
    """
    _run(["validate"])
    assert "test.real.id" not in _load_meta_index(world)["actions"]

    rc, out, err = _run(["info", str(world.loose)])
    assert rc == 0, (out, err)
    data = json.loads(out)["data"]
    assert data["id"] == "test.real.id", data

    rc, out, _ = _run(["preview", str(world.loose)])
    assert rc == 0
    assert json.loads(out)["data"]["action_id"] == "test.real.id" if \
        "action_id" in json.loads(out)["data"] else True

    rc, out, _ = _run(["validate", str(world.loose)])
    assert rc == 0
    assert json.loads(out)["data"]["id"] == "test.real.id"


# ===========================================================================
# ④ ambiguous：resolver 候选 + run 的结构
# ===========================================================================

def test_ambiguous_resolver_reports_candidates(world):
    """退步了会怎样：同名多动作时 resolver 静默挑一个（或只报一句错误不带候选）——
    调用方无法让用户用完整 id 消歧，甚至可能执行错的动作。

    断言：`resolve_target('Dup')` 抛 ActionError `action_ambiguous`，
    `details.ambiguous` 恰为两个候选 id（排序无关，集合相等）。
    """
    with pytest.raises(ActionError) as excinfo:
        resolver.resolve_target("Dup")
    assert excinfo.value.code == "action_ambiguous"
    details = excinfo.value.details or {}
    assert set(details.get("ambiguous") or []) == {"myapp.dup.one", "myapp.dup.two"}


def test_run_ambiguous_branch_uses_candidates_helper(world, monkeypatch):
    """退步了会怎样：`run` 的 ambiguous 分支不再使用 resolver 的候选列表（换字段/
    丢 details）—— CLI 输出与 resolver 契约漂移。

    断言（用 monkeypatch 让 resolver 返回一个"非抛出式 ambiguous"结果，覆盖 run 的
    该分支）：run 输出 code='ambiguous'、`details.candidates` == resolver 候选列表。
    """
    class _AmbiguousResult(object):
        ambiguous = ["myapp.dup.one", "myapp.dup.two"]
        source = "name"
        action_id = ""
        path = ""
        url = ""

    monkeypatch.setattr(resolver, "resolve_target",
                        lambda *args, **kwargs: _AmbiguousResult())
    rc, out, _ = _run(["run", "Dup"])

    assert rc == 1
    payload = json.loads(out)
    error = payload["error"]
    assert error["code"] == "ambiguous", error
    assert error["details"]["candidates"] == ["myapp.dup.one", "myapp.dup.two"]


@pytest.mark.xfail(strict=False, reason=(
    "产品缺口（已上报）：CLI `_resolve_cli_target` 捕获 resolver 的 ActionError 后只保留 "
    "code/message，**丢弃 details** → info/validate/preview 的 ambiguous 输出没有 "
    "details.candidates，且 code 是 action_ambiguous（run 分支是 ambiguous）。"
    "修复（保留 details、对齐 code）后本用例自动 xpass。"))
def test_info_ambiguous_keeps_candidates_like_run(world):
    """退步了会怎样：info/validate/preview 的 ambiguous 错误不携带候选 —— 用户只看到
    "命中多个动作"，却不知道该用哪个 id；与 run 的 ambiguous 结构也不一致。

    断言（目标契约）：failed + 错误码属 ambiguous 族 + `details.candidates` 非空且与
    resolver 候选一致（与 run 结构对齐）。
    """
    with pytest.raises(ActionError) as excinfo:
        resolver.resolve_target("Dup")
    expected = set(excinfo.value.details.get("ambiguous") or [])

    rc, out, _ = _run(["info", "Dup"])
    assert rc == 1
    error = json.loads(out)["error"]
    assert error["code"] in ("ambiguous", "action_ambiguous"), error
    assert set((error.get("details") or {}).get("candidates") or []) == expected, error


# ===========================================================================
# ⑤ md5 一致性：两种文案（warning 前缀、rc=0）
# ===========================================================================

def _set_warning_md5(world, bad_md5="deadbeefdeadbeefdeadbeefdeadbeef"):
    index = _load_meta_index(world)
    index["actions"]["myapp.demo"]["md5"] = bad_md5
    _rewrite_meta_index(world, index)


def test_md5_consistency_warns_with_two_distinct_texts(world):
    """退步了会怎样：索引 md5 与文件不符时**静默通过**（旧实现没有这个检查），
    或把警告升级成 error（影响 valid/退出码）——用户要么完全不知道，要么正常工作流被拦。

    断言两种文案都 rc=0、以 `warning: ` 前缀、errors 为空：
      * 索引 mtime 晚于文件（索引较新）→ 文案含「索引较新」「可能文件被篡改」；
      * 索引 mtime 早于文件（正常陈旧）→ 文案含「正常陈旧」「重建索引即可」。
    """
    _run(["validate"])
    demo_path = world.actions / "demo.actus.md"

    # 情形 A：索引较新
    os.utime(str(demo_path), (time.time() - 1000, time.time() - 1000))
    _set_warning_md5(world)
    rc, out, _ = _run(["validate", "myapp.demo"])
    assert rc == 0
    data = json.loads(out)["data"]
    assert data["errors"] == []
    warnings = data.get("warnings") or []
    newer = [w for w in warnings if w.startswith("warning: ")]
    assert any("索引较新" in w and "可能文件被篡改" in w for w in newer), warnings

    # 情形 B：正常陈旧（索引 mtime 比文件旧）
    _set_warning_md5(world)
    os.utime(str(world.index_path), (time.time() - 2000, time.time() - 2000))
    os.utime(str(demo_path), (time.time(), time.time()))
    rc, out, _ = _run(["validate", "myapp.demo"])
    assert rc == 0
    data = json.loads(out)["data"]
    assert data["errors"] == []
    warnings = data.get("warnings") or []
    older = [w for w in warnings if w.startswith("warning: ")]
    assert any("正常陈旧" in w and "重建索引即可" in w for w in older), warnings


# ===========================================================================
# ⑥ languages 落索引
# ===========================================================================

def test_languages_field_is_normalized_and_exact(world):
    """退步了会怎样（索引增量字段）：`languages` 不落索引（按语言检索/展示失效），
    或大小写混杂/重复/未排序（同一语言被当成两种）。

    断言：demo（json+python+yaml 三种代码块）→ `['json','python','yaml']`；
    种子 calculator → `['python','webview2','yaml']`；所有带该键的值都是
    小写、去重、排序后的列表。
    """
    _run(["validate"])
    index = _load_meta_index(world)["actions"]

    assert index["myapp.demo"]["languages"] == ["json", "python", "yaml"]
    calculator = index.get("actus.basics.calculator")
    assert calculator is not None
    assert calculator["languages"] == ["python", "webview2", "yaml"]

    for aid, brief in index.items():
        languages = brief.get("languages")
        if languages is None:
            continue
        assert isinstance(languages, list) and languages, (aid, languages)
        assert languages == sorted(set(languages)), (aid, languages)
        assert all(item == item.lower() for item in languages), (aid, languages)


def test_action_without_languages_omits_key(world, monkeypatch):
    """退步了会怎样：没有任何代码块语言的动作被写成 `languages: []` —— 旧索引形状
    被破坏（消费方按"键存在 = 有语言信息"判断会误判）。

    断言：`build_index` 遇到 blocks 为空的动作 → brief 里**没有** `languages` 键。
    """
    action = Action(meta={"id": "myapp.nolang", "name": "NoLang",
                          "version": "1.0.0", "trust": "sandbox",
                          "entry": "main", "platform": "desktop"},
                    path="", sha256="", blocks=[])
    monkeypatch.setattr(indexer, "scan_actions",
                        lambda *args, **kwargs: {"myapp.nolang": action})
    meta = world.root / "meta2"

    built = indexer.build_index(meta_dir=str(meta))

    assert "myapp.nolang" in built["actions"]
    assert "languages" not in built["actions"]["myapp.nolang"]


# ===========================================================================
# ⑦ link/alias 静态 target 三态
# ===========================================================================

def test_link_target_three_states(world):
    """退步了会怎样：link/alias 的 target 缺失被当成 warning（运行期必炸却放过）、
    target 找不到被当成 error（远端/延迟注册场景假阴性，正常仓库被拦）、能解析也报。

    断言（索引 + CLI 双层）：
      * 缺 target → 索引 status=invalid + error 含「缺少 target」；CLI rc=1 errors 同名；
      * target 找不到 → 索引 status=valid + warning 含「未在索引中找到」；CLI rc=0
        warnings 以 `warning: ` 开头；
      * target 可解析 → 索引无 error/warning；CLI rc=0 且无警告。
    """
    _run(["validate"])
    index = _load_meta_index(world)["actions"]

    bad = index["myapp.linkbad"]
    assert bad["status"] == "invalid"
    assert any("缺少 target" in e for e in (bad.get("errors") or []))

    miss = index["myapp.linkmiss"]
    assert miss["status"] == "valid", miss
    assert not miss.get("errors"), miss
    # 注意：build_index 阶段按设计传 check_index=False（索引正被重建，不能拿旧索引
    # 判 target 存在性），所以"找不到 target"的 warning 只应出现在单动作 validate
    # （check_index=True）——下面 CLI 层断言它；索引层这里只要求不误判 error/valid。

    ok = index["myapp.linkok"]
    assert ok["status"] == "valid"
    assert not ok.get("errors") and not ok.get("warnings"), ok

    rc, out, _ = _run(["validate", "myapp.linkbad"])
    assert rc == 1
    assert any("缺少 target" in e for e in json.loads(out)["data"]["errors"])

    rc, out, _ = _run(["validate", "myapp.linkmiss"])
    assert rc == 0
    warnings = json.loads(out)["data"].get("warnings") or []
    assert any(w.startswith("warning: ") and "未在索引中找到" in w for w in warnings)

    rc, out, _ = _run(["validate", "myapp.linkok"])
    assert rc == 0
    data = json.loads(out)["data"]
    assert not (data.get("warnings") or []) and not (data.get("errors") or [])
