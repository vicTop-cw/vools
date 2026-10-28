# -*- coding: utf-8 -*-
"""actus/tests/test_probe_actions.py — 动作分析探测器（`probe/actions.py`）验收测试。

测什么 / 为什么
---------------
`ActionsProber` 对应 PROBE_PLAN.md Phase 1 的 `probe/actions.py`。计划里的专项测试
文件名 `tests/test_probe_actions.py` 一直缺位，此前 `ActionsProber` 只被
`test_probe.py` 的「完整报告包含 actions 分类」间接覆盖 —— 扫描逻辑本身没有任何
单测，扫错/漏扫/坏文件炸整批都不会被发现。

它负责两件事：
1. **扫描动作目录**：找出所有 `.actus.md` / `.actus.schema.md`，解析出动作 id；
   解析失败的动作退化为相对路径 id（一个坏文件不许打断整次扫描）；
2. **给出依赖信息**：报告 `ACTION_DEPENDENCY_MAP`（动作种类 → 依赖工具/包 的静态表）。

下游 ready / blocked 判定（PROBE_PLAN.md §9 Phase 3、`intent.IntentRouter`）也一并测：
报告里列出的动作 = ready（可推荐），其余 = blocked。

⚠️ **计划与实现的一处差异（按实现写，已在汇报里点名）**：计划 §4.7 设计的
`analyze_actions(actions_dir, probe_report)` —— 逐个动作比对 `deps` 字段、产出
`ready/blocked/missing_deps` —— **产品里并不存在**。现产品的语义是：
`ActionsProber` 只做扫描 + 静态依赖表；「ready」的判据是「动作出现在探测报告里」，
「blocked」= 没出现（解析失败、目录不可读、被探测过滤掉的动作都属于这一档）。
所以本文件按这套**真实语义**测 ready/blocked，而不是按计划里未实现的 deps 比对。

怎么测（不依赖仓库里的真实动作）
--------------------------------
* 动作全部用 `tmp_path` 现造：JSON `#!cfg` 形态、`.actus.schema.md` 的 YAML
  front-matter 形态、以及故意写坏的文件；
* 扫描根用产品自带的覆盖点 `ACTUS_REPO_ROOT`（`indexer._repo_root()` 显式支持，
  docstring 写明「测试/多仓库场景」）切到 tmp，不碰仓库 `actions/`；
* 唯一一条真跑 `probe()` 的冒烟用例把缓存目录也重定向到 tmp（不写工作区
  `_meta/probe_cache.json`）；当前整条 probe 实测约 2s。

py3.6 兼容：只用标准库，% 格式化，不用 f-string。
"""

import json
import os
import sys

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.intent import IntentRouter  # noqa: E402
from vools.actus.probe import cache as cache_mod  # noqa: E402
from vools.actus.probe import probe  # noqa: E402
from vools.actus.probe.actions import (  # noqa: E402
    ACTION_DEPENDENCY_MAP,
    ActionsProber,
    _scan_actions_dir,
)
from vools.actus.probe.report import ProbeReport  # noqa: E402


# ---------------------------------------------------------------------------
# 造假动作文件（两种真实格式，最小可解析形态）
# ---------------------------------------------------------------------------

def _json_action_text(action_id, name="Alpha"):
    """传统格式：AIGC front-matter + ```json #!cfg 元数据块 + 运行块。"""
    return (
        "---\n"
        "AIGC:\n"
        '    Label: "1"\n'
        "---\n"
        "\n"
        "# %(name)s\n"
        "\n"
        "```json #!cfg\n"
        '{"id": "%(id)s", "name": "%(name)s", "version": "1.0.0", "entry": "main", '
        '"description": "%(lower)s action", "usage": "调用示例"}\n'
        "```\n"
        "\n"
        "```python #!run tag=main\n"
        "def main():\n"
        '    return {"status": "ok"}\n'
        "```\n"
    ) % {"id": action_id, "name": name, "lower": name.lower()}


def _schema_action_text(action_id, name="Gamma"):
    """新规范格式：`.actus.schema.md` 的 YAML front-matter 元数据。"""
    return (
        "---\n"
        "id: %(id)s\n"
        "name: %(name)s\n"
        "version: 1.0.0\n"
        "trust: sandbox\n"
        "kind: exec\n"
        "purpose: [compute]\n"
        "industry: [general]\n"
        "trigger: [manual]\n"
        "entry: main\n"
        "description: %(lower)s action\n"
        "author: vools\n"
        "platform: desktop\n"
        "---\n"
        "\n"
        "# %(name)s\n"
        "\n"
        "```python\n"
        'print("hi")\n'
        "```\n"
    ) % {"id": action_id, "name": name, "lower": name.lower()}


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _actions_dir(repo_root):
    return repo_root / "actions"


def _items_by_name(items):
    return {item.name: item for item in items}


def _item(items, name):
    by_name = _items_by_name(items)
    assert name in by_name, "探测器没有产出 %r 条目（实得 %s）" % (
        name, sorted(by_name))
    return by_name[name]


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """造一个只含假动作的仓库根，并通过产品自带的 ACTUS_REPO_ROOT 覆盖点接上。"""
    root = tmp_path / "repo"
    _actions_dir(root).mkdir(parents=True)
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(root))
    return root


@pytest.fixture
def isolated_probe_cache(tmp_path, monkeypatch):
    """探测缓存重定向到 tmp（冒烟用例不许写工作区 `_meta/probe_cache.json`）。"""
    cache_file = tmp_path / "probe_cache.json"
    monkeypatch.setattr(cache_mod, "_CACHE_FILE", str(cache_file))
    monkeypatch.setattr(cache_mod, "_CACHE_DIR", str(tmp_path))
    return cache_file


# ---------------------------------------------------------------------------
# 1) 目录不存在 / 空目录
# ---------------------------------------------------------------------------

def test_scan_nonexistent_actions_dir(tmp_path):
    """目录不存在：exists=False、0 个动作，且**不抛异常**（路径写错不能整份探测崩）。"""
    missing = tmp_path / "no_such_actions"
    info = _scan_actions_dir(str(missing))
    assert info["exists"] is False
    assert info["actions"] == []
    assert info["actions_dir"] == str(missing)


def test_prober_reports_unavailable_when_actions_dir_missing(tmp_path, monkeypatch):
    """扫描根下没有 actions/ 时，条目必须如实标不可用、计数为 0。"""
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))   # 故意不建 actions/
    items = ActionsProber().run()
    item = _item(items, "actions")
    assert item.available is False
    assert item.extra["action_count"] == 0
    assert item.extra["actions"] == []
    # 依赖表条目与目录可读性无关：始终可用
    assert _item(items, "action_dependencies").available is True


def test_scan_empty_actions_dir(fake_repo):
    """空目录：exists=True、0 个动作（「目录在但没动作」不能被误报成不可用）。"""
    info = _scan_actions_dir()
    assert info["exists"] is True
    assert info["actions"] == []

    item = _item(ActionsProber().run(), "actions")
    assert item.available is True
    assert item.extra["action_count"] == 0


# ---------------------------------------------------------------------------
# 2) 正常扫描：两种格式都能解析出动作 id
# ---------------------------------------------------------------------------

def test_scan_collects_ids_from_both_formats(fake_repo):
    """`.actus.md`（JSON cfg）与 `.actus.schema.md`（YAML front-matter）都要能扫到。"""
    actions = _actions_dir(fake_repo)
    _write(actions / "alpha.actus.md", _json_action_text("test.alpha"))
    _write(actions / "nested" / "deeper" / "beta.actus.md",
           _json_action_text("test.beta", "Beta"))
    _write(actions / "gamma.actus.schema.md", _schema_action_text("test.gamma"))

    info = _scan_actions_dir()
    assert info["exists"] is True
    assert {entry["id"] for entry in info["actions"]} == {
        "test.alpha", "test.beta", "test.gamma"}

    item = _item(ActionsProber().run(), "actions")
    assert item.extra["action_count"] == 3
    assert {entry["id"] for entry in item.extra["actions"]} == {
        "test.alpha", "test.beta", "test.gamma"}
    # 条目必须能 JSON 序列化（落缓存 / 给 LLM 消费两条下游都依赖）
    json.dumps(item.to_dict(), ensure_ascii=False)


def test_scan_ignores_non_action_files(fake_repo):
    """非动作文件（notes.md / readme.txt / data.json）一律不进动作列表。"""
    actions = _actions_dir(fake_repo)
    _write(actions / "notes.md", "# 只是文档\n")
    _write(actions / "readme.txt", "x\n")
    _write(actions / "data.json", "{}\n")
    _write(actions / "ok.actus.md", _json_action_text("test.ok"))

    info = _scan_actions_dir()
    assert [entry["id"] for entry in info["actions"]] == ["test.ok"]


def test_scan_accepts_explicit_dir_argument(tmp_path):
    """`_scan_actions_dir(dir)` 显式传目录时不该依赖 ACTUS_REPO_ROOT。"""
    custom = tmp_path / "custom_actions"
    _write(custom / "x.actus.md", _json_action_text("test.x"))

    info = _scan_actions_dir(str(custom))
    assert info["exists"] is True
    assert info["actions_dir"] == str(custom)
    assert [entry["id"] for entry in info["actions"]] == ["test.x"]


# ---------------------------------------------------------------------------
# 3) 解析失败容错：坏文件不能打断整批扫描
# ---------------------------------------------------------------------------

def test_broken_action_files_fall_back_to_relative_path(fake_repo):
    """坏动作文件 → id 退化为相对路径，其余动作照常解析，扫描不抛异常。

    这也是 PROBE_PLAN.md 风险表「动作依赖格式不统一 → 容错解析」那一行的
    可执行判据：坏文件既不许炸掉扫描，也不许被静默丢弃（它仍会计数，
    只是 id 退化），否则用户看不到「这个动作没解析成功」。
    """
    actions = _actions_dir(fake_repo)
    _write(actions / "good.actus.md", _json_action_text("test.good"))
    _write(actions / "broken.actus.md", "这不是任何合法配置\n")
    # 坏 YAML：front-matter 里留一个未闭合的列表
    _write(actions / "bad.actus.schema.md",
           "---\nid: [unclosed\nname: broken\n---\n\n# broken\n")

    info = _scan_actions_dir()          # 不抛异常
    ids = {entry["id"] for entry in info["actions"]}
    assert "test.good" in ids
    # 解析失败 → 相对路径作 id（而不是静默丢弃）
    assert "broken.actus.md" in ids
    assert "bad.actus.schema.md" in ids
    assert len(info["actions"]) == 3

    item = _item(ActionsProber().run(), "actions")
    assert item.available is True
    assert item.extra["action_count"] == 3


# ---------------------------------------------------------------------------
# 4) 依赖信息：静态映射表
# ---------------------------------------------------------------------------

def test_dependency_map_item_reports_static_table(fake_repo):
    """`action_dependencies` 条目就是 `ACTION_DEPENDENCY_MAP` 这张静态表。

    注意：它是「动作种类 → 依赖工具/包」的**静态**映射，不随本机是否装了
    git/curl 变化 —— probe 层不做逐动作 deps 解析（见模块 docstring 的说明）。
    """
    item = _item(ActionsProber().run(), "action_dependencies")
    assert item.category == "actions"
    assert item.available is True
    assert item.extra == ACTION_DEPENDENCY_MAP

    for kind in ("git", "http", "screenshot", "clipboard", "json"):
        assert kind in item.extra, "依赖表缺 %r 这一类动作" % kind
        assert isinstance(item.extra[kind].get("tools"), list)
        assert isinstance(item.extra[kind].get("packages"), list)
    # 抽查语义：git 动作依赖 git 命令与 GitPython
    assert item.extra["git"]["tools"] == ["git"]
    assert "GitPython" in item.extra["git"]["packages"]


# ---------------------------------------------------------------------------
# 5) ready / blocked（PROBE_PLAN.md §9 Phase 3 的真实语义）
# ---------------------------------------------------------------------------

def test_ready_when_action_is_listed_in_probe_report(fake_repo):
    """动作出现在探测报告里 → ready（可被 route 推荐）。"""
    _write(_actions_dir(fake_repo) / "alpha.actus.md",
           _json_action_text("test.alpha"))
    report = ProbeReport(items=ActionsProber().run())

    router = IntentRouter()
    router.register_action("test.alpha", "alpha action", tags=["alpha"])
    router.register_action("test.not_probed", "not probed action", tags=["notprobed"])
    router.set_probe_report(report)

    ready_ids = {action["id"] for action in router.list_actions()}
    assert "test.alpha" in ready_ids
    hit = router.route("alpha")
    assert hit["action_id"] == "test.alpha", "ready 动作必须能被推荐: %r" % (hit,)


def test_blocked_when_action_absent_from_probe_report(fake_repo):
    """动作没出现在探测报告里（缺依赖 / 解析失败 / 不在扫描根）→ blocked，不得被推荐。

    现产品有两道门：① `IntentRouter._ready_ids` —— 报告里没有它 → 不可推荐；
    ② 报告里 `action_readiness` 条目的逐动作 verdict（`analyze_actions` 明确判
    blocked 的动作同样不可推荐）。本用例走的是第一道门：`_scan_actions_dir` 解析
    失败的动作会退化成相对路径 id、根本不在报告里，于是与「依赖不满足」同样落到
    blocked 一档。
    """
    _write(_actions_dir(fake_repo) / "alpha.actus.md",
           _json_action_text("test.alpha"))
    report = ProbeReport(items=ActionsProber().run())

    router = IntentRouter()
    router.register_action("test.alpha", "alpha action", tags=["alpha"])
    router.register_action("test.blocked", "blocked action", tags=["blocked"])
    router.set_probe_report(report)

    ready_ids = {action["id"] for action in router.list_actions()}
    assert ready_ids == {"test.alpha"}, \
        "报告里没有的动作必须被判 blocked，实得 ready=%r" % (ready_ids,)

    # blocked 动作即使标签/描述能匹配查询，也不许出现在推荐结果里
    assert router.route("blocked")["action_id"] != "test.blocked"


def test_unavailable_actions_report_does_not_block_everything(tmp_path, monkeypatch):
    """探测报告里 actions 不可用（目录缺失）时，ready 过滤必须关闭（不误杀全部动作）。

    否则「探测不到动作目录」会被下游解读成「所有动作都 blocked」，
    用户一个动作都推荐不出来 —— 这是 ready 过滤最危险的失败形态。
    """
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))   # 无 actions/
    report = ProbeReport(items=ActionsProber().run())
    assert _item(report.items, "actions").available is False

    router = IntentRouter()
    router.register_action("test.any", "any action", tags=["any"])
    router.set_probe_report(report)

    ready_ids = {action["id"] for action in router.list_actions()}
    assert ready_ids == {"test.any"}, \
        "探测不可用时不应把所有动作误判 blocked，实得 ready=%r" % (ready_ids,)


# ---------------------------------------------------------------------------
# 6) 端到端冒烟：真跑 probe()（约 2s），确认 actions 段进了报告且能被下游消费
# ---------------------------------------------------------------------------

@pytest.mark.timeout(180)
def test_probe_report_integrates_actions_section(fake_repo, isolated_probe_cache):
    """真跑一次 probe()：actions 段出现在报告里，且 report → ready 过滤链路通。

    这是本文件唯一不靠打桩的用例：其余用例都只跑探测器本体，所以需要一条
    「探测 → 报告 → intent」的端到端证据（打桩测不出来接线断掉）。
    缓存目录已重定向到 tmp，且扫描根是假仓库 —— 不依赖仓库里的真实动作。
    """
    _write(_actions_dir(fake_repo) / "alpha.actus.md",
           _json_action_text("test.probe.alpha"))

    report = probe(force_refresh=True)
    assert isinstance(report, ProbeReport)

    actions_items = [item for item in report.items if item.category == "actions"]
    assert actions_items, "报告里没有 actions 分类的条目"
    listed = _item(actions_items, "actions")
    assert listed.available is True
    assert "test.probe.alpha" in {entry["id"] for entry in listed.extra["actions"]}
    assert report.summary["by_category"]["actions"]["total"] == len(actions_items)

    router = IntentRouter()
    router.register_action("test.probe.alpha", "alpha", tags=["alpha"])
    router.register_action("test.other", "other", tags=["other"])
    router.set_probe_report(report)
    assert {action["id"] for action in router.list_actions()} == {"test.probe.alpha"}
