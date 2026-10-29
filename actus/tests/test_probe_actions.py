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

⚠️ **计划与实现的差异（按实现写）**：`analyze_actions()` 后来已按 §4.7 落地（逐动作
`deps` → ready/blocked），但它是 `action_readiness` 条目、由 `tests/test_analyze_actions.py`
专项覆盖；**本文件负责的是 `ActionsProber` 的两条既有条目（`actions` 清单 +
`action_dependencies` 静态表）以及「报告里出现 = ready」这道粗粒度门**。

怎么测（不依赖仓库里的真实动作）
--------------------------------
* 动作全部用 `tmp_path` 现造：JSON `#!cfg` 形态、`.actus.schema.md` 的 YAML
  front-matter 形态、以及故意写坏的文件；
* 扫描根用产品自带的覆盖点 `ACTUS_REPO_ROOT`（`indexer._repo_root()` 显式支持，
  docstring 写明「测试/多仓库场景」）切到 tmp，不碰仓库 `actions/`；
* **多根语义（本轮更新）**：`actions` 条目缺省扫**全部动作根** —— 用户项目 `actions/`
  + 包内种子（`indexer._action_roots()`，与 `action_readiness`、docs/actus/03:32 对齐）。
  因此本文件分两档断言，避免「为了绿而放宽」：
    - **扫描层**用显式目录 `_scan_actions_dir(str(dir))` → 精确断言「只扫该目录」；
    - **条目层**用「本地动作 + 包内种子」的**精确并集**计数（种子集合动态取自产品
      真源 `_seed_actions_dir()`，不写死 8/14 这些会漂移的数字）。
* 唯一一条真跑 `probe()` 的冒烟用例把缓存目录也重定向到 tmp（不写工作区
  `_meta/probe_cache.json`）；当前整条 probe 实测约 2s。

py3.6 兼容：只用标准库，% 格式化，不用 f-string。
"""

import json
import os
import sys

import pytest

# 第 22 轮：真实 IO / 真实执行型测试 —— 用 `pytest -m "not slow"` 跳过
pytestmark = pytest.mark.slow

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.intent import IntentRouter  # noqa: E402
from vools.actus.indexer import _action_roots, _seed_actions_dir  # noqa: E402
from vools.actus.probe import cache as cache_mod  # noqa: E402
from vools.actus.probe import probe  # noqa: E402
from vools.actus.probe.actions import (  # noqa: E402
    ACTION_DEPENDENCY_MAP,
    ActionsProber,
    _scan_actions_dir,
)
from vools.actus.probe.base import ProbeItem  # noqa: E402
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


def _seed_action_entries():
    """包内种子根的动作条目（多根扫描的第二根）。

    为什么不写死数量：种子集随产品演进（当前 8 个），断言必须用
    「本地 + 种子」的**精确并集**，种子集合从产品真源 `_seed_actions_dir()` 现算。
    """
    seed_dir = _seed_actions_dir()
    if not os.path.isdir(seed_dir):
        return []
    return _scan_actions_dir(seed_dir)["actions"]


def _seed_ids():
    """包内种子动作 id 的排序列表（当前实现缺省多根扫描会并入它们）。"""
    return sorted(entry["id"] for entry in _seed_action_entries())


def _norm_paths(paths):
    """路径归一化后比较（Windows 大小写/分隔符差异不该让断言抖动）。"""
    return [os.path.normcase(os.path.abspath(path)) for path in paths]


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


def test_prober_uses_seed_root_when_repo_actions_missing(tmp_path, monkeypatch):
    """仓库根没有 actions/ 时，多根扫描仍会扫到**包内种子** → 条目必须可用。

    为什么从「不可用 / count=0」改成「可用 / count=种子数」：
    改前 `actions` 条目只扫仓库根（单根口径），根不存在就判不可用；
    多根化后（docs/actus/03-动作规范.md:32）「用户根缺失」≠「动作探测不可用」——
    包内种子根仍在，报告要如实列出它们，否则 IntentRouter 永远看不到种子动作。
    这是**语义修正**，不是放宽：断言用精确值（种子动作集 + roots 完整列表）。
    """
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))   # 故意不建 actions/
    seed_ids = _seed_ids()
    if not seed_ids:
        pytest.skip("包内种子目录缺失/为空，无法验证多根回退语义")

    items = ActionsProber().run()
    item = _item(items, "actions")

    assert item.available is True, "种子根存在时动作探测应可用（多根语义）"
    assert item.extra["action_count"] == len(seed_ids), \
        "缺省（多根）扫描计数应精确等于种子动作数 %d" % len(seed_ids)
    assert sorted(entry["id"] for entry in item.extra["actions"]) == seed_ids
    # roots 与产品真源 _action_roots() 一致：用户项目根（即使不存在）+ 包内种子根
    assert _norm_paths(item.extra["roots"]) == _norm_paths(_action_roots()), \
        "roots 应如实报告全部动作根，实得 %r" % (item.extra["roots"],)
    assert len(item.extra["roots"]) >= 2, "多根语义下至少应有「用户根 + 种子根」两个根"
    # 用户根没有文件：列出的路径必须全部来自种子根，不能凭空产生用户动作
    seed_dir = _seed_actions_dir()
    assert all(os.path.normcase(entry["path"]).startswith(os.path.normcase(seed_dir))
               for entry in item.extra["actions"]), \
        "缺失用户根时不应出现用户根下的动作"
    # 依赖表条目与目录可读性无关：始终可用
    assert _item(items, "action_dependencies").available is True


def test_scan_empty_actions_dir(fake_repo):
    """空用户目录：显式单根扫描 0 个；缺省多根扫描 = 包内种子（精确计数）。

    为什么拆分：改前 `action_count == 0` 建立在「缺省也只看仓库根」的单根口径上；
    多根后空用户目录只代表「本仓库没有动作」，包内种子照常计入 —— 所以扫描层
    （显式目录）断言 0，条目层（缺省多根）断言精确种子数。
    """
    actions = _actions_dir(fake_repo)

    info = _scan_actions_dir(str(actions))          # 显式单根：只扫该目录
    assert info["exists"] is True
    assert info["actions"] == []
    assert _norm_paths(info["roots"]) == _norm_paths([str(actions)]), \
        "显式传目录时应只有一个扫描根，实得 %r" % (info["roots"],)

    seed_ids = _seed_ids()
    item = _item(ActionsProber().run(), "actions")
    assert item.available is True
    assert item.extra["action_count"] == len(seed_ids), \
        "空用户目录 + 包内种子 → 计数应精确等于种子数 %d，实得 %r" % (
            len(seed_ids), item.extra["action_count"])


# ---------------------------------------------------------------------------
# 2) 正常扫描：两种格式都能解析出动作 id
# ---------------------------------------------------------------------------

def test_scan_collects_ids_from_both_formats(fake_repo):
    """两种格式都能扫到（扫描层：显式单根精确 3 个；条目层：本地 + 种子精确并集）。

    为什么这样改：改前 `_scan_actions_dir()` 缺省只扫仓库根，所以能精确断言 3 个；
    多根化后缺省会并入包内种子 → 扫描层改用**显式目录**保留「只扫该目录」的语义，
    条目层则断精确并集（本地 3 + 种子 N），不是「>=3」这种弱断言。
    """
    actions = _actions_dir(fake_repo)
    _write(actions / "alpha.actus.md", _json_action_text("test.alpha"))
    _write(actions / "nested" / "deeper" / "beta.actus.md",
           _json_action_text("test.beta", "Beta"))
    _write(actions / "gamma.actus.schema.md", _schema_action_text("test.gamma"))
    local_ids = {"test.alpha", "test.beta", "test.gamma"}

    info = _scan_actions_dir(str(actions))          # 显式单根
    assert info["exists"] is True
    assert {entry["id"] for entry in info["actions"]} == local_ids
    assert _norm_paths(info["roots"]) == _norm_paths([str(actions)])

    seed_ids = set(_seed_ids())
    item = _item(ActionsProber().run(), "actions")
    assert item.extra["action_count"] == len(local_ids | seed_ids), \
        "缺省（多根）计数应为「本地 + 包内种子」精确并集大小 %d，实得 %r" % (
            len(local_ids | seed_ids), item.extra["action_count"])
    assert {entry["id"] for entry in item.extra["actions"]} == local_ids | seed_ids
    # 条目必须能 JSON 序列化（落缓存 / 给 LLM 消费两条下游都依赖）
    json.dumps(item.to_dict(), ensure_ascii=False)


def test_scan_ignores_non_action_files(fake_repo):
    """非动作文件（notes.md / readme.txt / data.json）不进动作列表。

    扫描层用显式单根精确断言「只有 test.ok」；条目层（多根）只额外并包内种子。
    """
    actions = _actions_dir(fake_repo)
    _write(actions / "notes.md", "# 只是文档\n")
    _write(actions / "readme.txt", "x\n")
    _write(actions / "data.json", "{}\n")
    _write(actions / "ok.actus.md", _json_action_text("test.ok"))

    info = _scan_actions_dir(str(actions))
    assert [entry["id"] for entry in info["actions"]] == ["test.ok"]

    item = _item(ActionsProber().run(), "actions")
    ids = {entry["id"] for entry in item.extra["actions"]}
    assert ids == {"test.ok"} | set(_seed_ids()), \
        "多根条目应恰为「本地 test.ok + 包内种子」，实得 %r" % (sorted(ids),)


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

    为什么计数从 3 改成「本地 3 + 种子 N」：多根化后缺省扫描会并入包内种子；
    本用例先用**显式单根**断言精确 3 条（含 2 个退化 id），再用条目层断精确并集。
    """
    actions = _actions_dir(fake_repo)
    _write(actions / "good.actus.md", _json_action_text("test.good"))
    _write(actions / "broken.actus.md", "这不是任何合法配置\n")
    # 坏 YAML：front-matter 里留一个未闭合的列表
    _write(actions / "bad.actus.schema.md",
           "---\nid: [unclosed\nname: broken\n---\n\n# broken\n")

    info = _scan_actions_dir(str(actions))          # 显式单根：不抛异常
    ids = {entry["id"] for entry in info["actions"]}
    assert "test.good" in ids
    # 解析失败 → 相对路径作 id（而不是静默丢弃）
    assert "broken.actus.md" in ids
    assert "bad.actus.schema.md" in ids
    assert len(info["actions"]) == 3

    seed_ids = _seed_ids()
    item = _item(ActionsProber().run(), "actions")
    assert item.available is True
    assert item.extra["action_count"] == 3 + len(seed_ids), \
        "多根条目 = 本地 3 个（含 2 个解析失败退化）+ 包内种子 %d" % len(seed_ids)


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


def test_unavailable_actions_report_does_not_block_everything():
    """探测报告里 actions 条目 `available=False` 时，ready 过滤必须关闭（不误杀全部动作）。

    为什么不再用「仓库根没有 actions/」来造这个场景：多根化后包内种子兜底，
    缺省扫描**不会**再因为用户根缺失而判不可用（见
    `test_prober_uses_seed_root_when_repo_actions_missing`）。但「探测失败/降级」
    这种报告形态仍然存在（扫描抛异常、旧缓存、裁剪过的报告都会），
    IntentRouter 对它的处理不该变 —— 所以这里直接构造该形态的报告来测
    下游语义，而不是依赖某个会造成失败的扫描环境。

    退步了会怎样：`set_probe_report` 对 `available=False` 也启用 ready 过滤 →
    所有动作被判 blocked，用户一个推荐都拿不到（ready 过滤最危险的失败形态）。
    """
    report = ProbeReport(items=[ProbeItem(
        name="actions",
        category="actions",
        available=False,
        error="stub: 扫描失败（降级形态）",
        extra={"actions_dir": "/stub/actions", "roots": [],
               "action_count": 0, "actions": []},
    )])
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
    缓存目录已重定向到 tmp；扫描根是假仓库 —— 注意多根语义下报告还会并入包内
    种子动作，所以这里只断言「本地动作在列」+ ready 过滤命中本地动作（种子动作
    没被 register，不会出现在 list_actions 里）。
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
