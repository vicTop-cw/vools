# -*- coding: utf-8 -*-
"""actus/tests/test_cli_no_side_effects.py — 「只读命令不得写仓库」契约测试。

为什么要这份测试
----------------
上一轮挖出两个「读了却写」的缺陷，它们的共同点是**命令看起来只读，但改了仓库状态**：

1. `publish --dry-run` **真写** `.actus.registry.json`（假干跑）：
   `build_from_directory()` 内部顺手落盘，而 dry-run 分支也调了它；
2. `actus search`（纯查询命令）也写 `.actus.registry.json`：
   `load_from_repo()` 缺索引时调了会落盘的 `build_from_directory()`。

此前的测试抓不到这类缺陷 —— 因为它们断言的是「输出的内容对不对」，而不是
「文件系统有没有被改」。本文件的每条用例都断言**磁盘状态**：跑命令前后对整个
tmp 仓库做递归快照（路径 + size + **mtime_ns** + **sha256**，覆盖 `actions/`、
`contracts/`、根目录（含隐藏文件）以及被 gitignore 的 `_meta/`），有任何
预期外的增/删/改都算红。

判定语义（两类，逐条在用例里写明）
----------------------------------
* **严格只读**：跑完仓库**零变化**（包括 `_meta/` 里的运行期文件）。适用于
  `publish --dry-run`、`search`、`list`、`status`、`events`、`records list`、
  `health`、`viz`、`export`、`deps`、`runtimes`、`replay --dry-run`、失败路径，
  以及 **`info` / 单目标 `validate`**（第 18 轮审计修复：它们曾被错误地放进
  `_META_CASES`，等于把旧的"读时写 mtime 缓存"行为合法化了）。
* **只允许写 `_meta/` 运行期产物**：**仅限"产物本身就是文件"的命令** ——
  全仓 `validate` / `scan`（重建索引是它们的目的）、`probe`（写自己的缓存）。
  每条必须带**理由**（`_META_CASES` 第三项）且由自检用例强制非空；对这类命令
  断言**变化集合 ⊆ 明确白名单**（源码树 `actions/`/`contracts/`/根目录一律不许动）。

⚠️ 护栏反向的历史教训（第 18 轮审计 #1）：如果一条命令"现在会写"就把它挪进
白名单，护栏会**把写行为合法化**。判定标准是"这个写是不是命令的**目的**"，
不是"它现在写不写" —— 自检用例会拒绝 `_META_CASES` 里出现空理由/敷衍理由。

变异验证（写测试时实际执行过）
------------------------------
把 `build_from_directory(write=False)` 强制改成 `write=True`（等价于 bug 复活）：
`test_publish_dry_run_writes_nothing` / `test_search_writes_nothing` 立刻变红。

隔离
----
全部在 `tmp_path` 造的最小仓库里跑（复制真实 `actions/`、`contracts/` 的必要文件），
`ACTUS_REPO_ROOT` / `ACTUS_META_DIR` / `ACTUS_CONFIG_DIR` / `HOME` 全部指到 tmp；
真实仓库本身不被写入（跑完整套件后 `git status` 为空，见汇报证据）。

py3.6 兼容：只用标准库，% 格式化，不用 f-string。
"""

import hashlib
import io
import json
import os
import shutil
import sys
import contextlib

import pytest

# 第 22 轮：真实 IO / 真实执行型测试 —— 用 `pytest -m "not slow"` 跳过
pytestmark = pytest.mark.slow

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

import vools.actus.cli as cli  # noqa: E402


# 只读命令的「跑一次」参数；note 说明这条防什么。
_STRICT_CASES = [
    (["list"], "只读：读索引列出动作"),
    (["status"], "只读：读执行状态/记录"),
    (["events"], "只读：读事件流"),
    (["records", "list"], "只读：读执行记录列表"),
    (["health"], "只读：系统健康检查"),
    (["viz"], "只读：渲染 .actus.workflow.json（不带 --output）"),
    (["export"], "只读：打印历史（不带 --output）"),
    (["deps", "actus.generated.probe"], "只读：读动作依赖"),
    (["runtimes"], "只读：探测运行时（只在内存里）"),
]

# 第 18 轮审计修复（#1 护栏反向）：`info` 与**单目标** `validate` 是纯查询，
# 曾经因为"实现会刷新 mtime 缓存"被放进 _META_CASES —— 那是把缺陷合法化。
# 现在它们在这里接受**严格零变化**断言；变异验证见汇报（把 info 改回写 mtimes 即红）。
_STRICT_CASES += [
    (["info", "actus.generated.probe"], "只读：解析单个动作（不许刷新 mtime 缓存）"),
    (["validate", "actus.generated.probe"],
     "只读：单目标校验（不重建索引、不写 audit；全仓 validate 才建索引）"),
]

# 允许写 `_meta/` 运行期产物的命令：白名单是**精确路径**，多写一个都算红。
# 第三项是**强制理由**（自检用例 test_meta_allowlist_entries_have_justification
# 校验非空、且不得是"因为它现在会写"这类敷衍话）。
_META_CASES = [
    (["validate"],
     ("_meta/actions.index.json", "_meta/actions.mtimes.json"),
     "全仓校验的目的就是重建索引（索引文件是其产物），故允许写索引+其 mtime 缓存"),
    (["scan"],
     ("_meta/actions.index.json", "_meta/actions.mtimes.json"),
     "scan 的语义就是重建索引产物，故允许写索引+其 mtime 缓存"),
    (["probe", "--json", "--force-refresh"],
     ("_meta/probe_cache.json",),
     "probe 的产物是自己的探测缓存，故允许写该缓存文件"),
]

_WORKFLOW = {
    "nodes": [
        {"id": "trigger", "label": "触发器", "type": "trigger"},
        {"id": "act", "label": "动作", "type": "action"},
        {"id": "end", "label": "完成", "type": "end"},
    ],
    "edges": [["trigger", "act"], ["act", "end"]],
}

_HISTORY = [{
    "run_id": "run-sidefx-1",
    "action_id": "actus.generated.probe",
    "status": "ok",
    "timestamp": "2026-01-01T00:00:00",
    "params": {},
}]

_REGISTRY_FILE = ".actus.registry.json"


# ---------------------------------------------------------------------------
# 快照 / 差异：断言的是磁盘状态，不是输出文本
# ---------------------------------------------------------------------------

def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot(root):
    """递归快照：{文件相对路径: (size, mtime_ns, sha256)} + 目录集合。

    覆盖隐藏文件与被 gitignore 的 `_meta/`；新增空目录也会被记下来
    （`dirs` 集合），避免「建个空目录也算写」被漏掉。
    """
    files = {}
    dirs = set()
    root_str = str(root)
    for dirpath, dirnames, filenames in os.walk(root_str):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root_str).replace(os.sep, "/")
        if rel_dir != ".":
            dirs.add(rel_dir)
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, root_str).replace(os.sep, "/")
            stat = os.stat(full)
            files[rel] = (stat.st_size, stat.st_mtime_ns, _sha256(full))
    return {"files": files, "dirs": dirs}


def _diff(before, after):
    """返回可读的变更列表：'A/M/D <rel>' 与 'A(dir)/D(dir) <rel>'。"""
    changes = []
    before_files, after_files = before["files"], after["files"]
    for rel in sorted(set(after_files) - set(before_files)):
        changes.append("A " + rel)
    for rel in sorted(set(before_files) - set(after_files)):
        changes.append("D " + rel)
    for rel in sorted(set(before_files) & set(after_files)):
        if before_files[rel] != after_files[rel]:
            changes.append("M " + rel)
    for rel in sorted(set(after["dirs"]) - set(before["dirs"])):
        changes.append("A(dir) " + rel)
    for rel in sorted(set(before["dirs"]) - set(after["dirs"])):
        changes.append("D(dir) " + rel)
    return changes


def _rel_path(change):
    return change.partition(" ")[2]


def _assert_only_changes(world, before, allowed, label):
    """断言仓库变化 ⊆ allowed（精确相对路径），失败时打印全部变更。"""
    after = _snapshot(world.repo)
    changes = _diff(before, after)
    unexpected = [c for c in changes if _rel_path(c) not in allowed]
    assert not unexpected, (
        "%s 改动了仓库里不该动的文件（变化集合 %r，允许 %r）—— 只读命令不许写仓库"
        % (label, changes, sorted(allowed)))


def _invoke(argv):
    """同进程执行 cli.main(argv)，返回 (rc, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(list(argv))
    except SystemExit as exc:
        rc = exc.code if exc.code is not None else 0
    return rc, out.getvalue(), err.getvalue()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """tmp 版最小仓库：真实 actions/contracts 副本 + 预热的 _meta + 历史 + 工作流。"""
    repo = tmp_path / "repo"
    (repo / "actions").parent.mkdir(parents=True)
    shutil.copytree(os.path.join(_ROOT, "actions"), str(repo / "actions"))
    shutil.copytree(os.path.join(_ROOT, "contracts"), str(repo / "contracts"))

    meta = repo / "_meta"
    runs = meta / "runs"
    runs.mkdir(parents=True)
    (runs / "history.json").write_text(json.dumps(_HISTORY, ensure_ascii=False),
                                       encoding="utf-8")
    (repo / ".actus.workflow.json").write_text(
        json.dumps(_WORKFLOW, ensure_ascii=False), encoding="utf-8")

    home = tmp_path / "home"
    config = tmp_path / "config"
    home.mkdir()
    config.mkdir()

    monkeypatch.chdir(repo)
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_CONFIG_DIR", str(config))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    # 预热索引/mtime 缓存：否则 `list`/`info` 的「懒构建」会写出索引，
    # 让本文件测到的就不是「只读命令写不写」，而是「首次构建写不写」。
    from vools.actus.indexer import build_index
    build_index(meta_dir=str(meta))

    class World(object):
        pass

    w = World()
    w.root = tmp_path
    w.repo = repo
    w.meta = meta
    return w


# ---------------------------------------------------------------------------
# 0) 自检：快照/差异本身必须有效（否则后面全是假绿）
# ---------------------------------------------------------------------------

def test_snapshot_detects_hidden_meta_and_all_change_kinds(world):
    """快照/差异探测器自检：漏掉隐藏文件、`_meta/`、mtime 变化都会让后续断言假绿。

    构造一棵小树（含隐藏文件与 `_meta/`），分别制造「改内容 / 新增 / 删除 / 新建目录」，
    断言 `_diff` 四类都能识别，且快照确实收录了隐藏文件与 `_meta/` 下的文件。
    """
    probe = world.root / "snapcheck"
    (probe / "_meta").mkdir(parents=True)
    (probe / "actions").mkdir()
    (probe / "actions" / "a.actus.md").write_text("A", encoding="utf-8")
    (probe / ".hidden").write_text("H", encoding="utf-8")
    (probe / "_meta" / "cache.json").write_text("{}", encoding="utf-8")

    before = _snapshot(probe)
    assert ".hidden" in before["files"], "快照漏了隐藏文件"
    assert "_meta/cache.json" in before["files"], "快照漏了 _meta/ 下的文件"

    (probe / "actions" / "a.actus.md").write_text("A-CHANGED", encoding="utf-8")
    (probe / "new.actus.md").write_text("NEW", encoding="utf-8")
    (probe / "_meta" / "cache.json").unlink()
    (probe / "empty_dir").mkdir()

    changes = _diff(before, _snapshot(probe))
    assert "M actions/a.actus.md" in changes, "没识别出内容/时间戳变化: %r" % (changes,)
    assert "A new.actus.md" in changes, "没识别出新增文件: %r" % (changes,)
    assert "D _meta/cache.json" in changes, "没识别出删除文件: %r" % (changes,)
    assert "A(dir) empty_dir" in changes, "没识别出新建目录: %r" % (changes,)


# ---------------------------------------------------------------------------
# 1) 上一轮的两个 bug：假干跑 / 只读查询写注册表
# ---------------------------------------------------------------------------

def test_publish_dry_run_writes_nothing(world):
    """退步了会怎样：`build_from_directory()` 又落盘 → 干跑写出 `.actus.registry.json`。

    断言：rc==0、**仓库零变化**（含 `_meta/` 与隐藏文件）、注册表索引文件不存在。
    """
    before = _snapshot(world.repo)
    rc, out, err = _invoke(["publish", "--dry-run"])

    assert rc == 0, "publish --dry-run 应成功，实得 rc=%r err=%r" % (rc, err[:300])
    _assert_only_changes(world, before, frozenset(), "publish --dry-run")
    assert not (world.repo / _REGISTRY_FILE).exists(), \
        "假干跑复活：--dry-run 写出了 %s" % _REGISTRY_FILE


def test_search_writes_nothing(world):
    """退步了会怎样：`load_from_repo()` 缺索引时调落盘版构建 → 查询命令写注册表。

    断言：rc ∈ {0,1,2}、仓库零变化、`.actus.registry.json` 不存在。
    """
    before = _snapshot(world.repo)
    rc, out, err = _invoke(["search", "probe"])

    assert rc in (0, 1, 2), "search 退出码异常: %r" % (rc,)
    _assert_only_changes(world, before, frozenset(), "search")
    assert not (world.repo / _REGISTRY_FILE).exists(), \
        "只读查询写出了 %s（上一轮的 search 写注册表缺陷）" % _REGISTRY_FILE


def test_replay_dry_run_writes_nothing(world):
    """退步了会怎样：dry-run 仍真的执行 → 写出执行记录/产物到 `_meta/`。

    断言：rc==0、输出明示跳过、仓库零变化（含 `_meta/runs/` 不新增记录）。
    """
    before = _snapshot(world.repo)
    rc, out, err = _invoke(["replay", "--dry-run", "--limit", "1"])

    assert rc == 0, "replay --dry-run 应成功，实得 rc=%r err=%r" % (rc, err[:300])
    assert "dry-run" in out, "dry-run 没有明示跳过: %r" % (out[-400:],)
    _assert_only_changes(world, before, frozenset(), "replay --dry-run")


def test_publish_sign_failure_leaves_no_partial_state(world):
    """退步了会怎样：签名失败前先写了索引/半成品，或失败后仍留下注册表文件。

    断言：rc!=0、仓库零变化（失败路径也不许有半成品）。
    """
    before = _snapshot(world.repo)
    rc, out, err = _invoke(["publish", "--sign", "--key", "nosuchkey"])

    assert rc != 0, "签名失败必须非 0，实得 %r" % (rc,)
    _assert_only_changes(world, before, frozenset(), "publish --sign（失败路径）")


# ---------------------------------------------------------------------------
# 2) 其它只读命令：严格零变化（含 _meta/ 与隐藏文件）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv,note", _STRICT_CASES,
                         ids=[" ".join(argv) for argv, _note in _STRICT_CASES])
def test_readonly_commands_write_nothing(world, argv, note):
    """退步了会怎样：这条只读命令顺手写索引/缓存/日志/注册表 → 本用例红。

    断言：rc ∈ {0,1,2} 且整个仓库零变化（源码树 + `_meta/` + 隐藏文件）。
    """
    label = " ".join(argv)
    before = _snapshot(world.repo)
    rc, out, err = _invoke(argv)

    assert rc in (0, 1, 2), "%s 退出码异常: %r" % (label, rc)
    _assert_only_changes(world, before, frozenset(), "%s（%s）" % (label, note))


# ---------------------------------------------------------------------------
# 3) 允许写 `_meta/` 产物的命令：变化集合必须 ⊆ 精确白名单
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv,allowed,note", _META_CASES,
                         ids=[" ".join(argv) for argv, _a, _n in _META_CASES])
def test_meta_writers_only_touch_whitelisted_files(world, argv, allowed, note):
    """退步了会怎样：命令除了自己的运行期产物，还顺手改了源码树/根文件/别的 `_meta` 文件。

    断言：rc ∈ {0,1,2}；所有变化都落在 `allowed` 精确白名单里（白名单外一个都算红）。
    """
    label = " ".join(argv)
    before = _snapshot(world.repo)
    rc, out, err = _invoke(argv)

    assert rc in (0, 1, 2), "%s 退出码异常: %r" % (label, rc)
    _assert_only_changes(world, before, frozenset(allowed), "%s（%s）" % (label, note))


# ---------------------------------------------------------------------------
# 4) 自检：白名单里的每条必须给出**真实理由**（防止护栏反向再次发生）
# ---------------------------------------------------------------------------

def test_meta_allowlist_entries_have_justification():
    """退步了会怎样（第 18 轮审计 #1 的根因）：将来有人再把一条"现在会写"的命令
    加进 `_META_CASES`，只写一句"因为它现在会写"——护栏又把缺陷合法化了。

    断言：
      * 每条都有非空理由（>= 10 个字符），且不含「现在会写 / 因为它现在」等敷衍措辞；
      * 只允许写 `_meta/` 下的路径（源码树/根目录永远不许出现在白名单）；
      * 同一命令不能既在 `_STRICT_CASES`（零变化）又在 `_META_CASES`（允许写）。
    """
    strict_labels = {" ".join(argv) for argv, _note in _STRICT_CASES}
    meta_labels = set()
    forbidden_phrases = ["现在会写", "因为它现在", "它现在会", "反正会写", "实测会写"]

    for argv, allowed, reason in _META_CASES:
        label = " ".join(argv)
        assert label not in meta_labels, "重复登记: %s" % label
        assert isinstance(reason, str) and len(reason.strip()) >= 10, (
            "%s 的白名单理由太短（必须说明'为什么这个写是命令目的'）: %r"
            % (label, reason))
        for phrase in forbidden_phrases:
            assert phrase not in reason, (
                "%s 的理由在为写行为找借口（%r），应说明'这个写是不是命令的目的'"
                % (label, phrase))
        assert allowed, "%s 白名单不能为空（空白名单请放 _STRICT_CASES）" % label
        for rel in allowed:
            assert rel.startswith("_meta/"), (
                "%s 白名单只能包含 _meta/ 运行期产物，不许包含 %r" % (label, rel))
        assert label not in strict_labels, \
            "%s 同时出现在严格只读与允许写两个清单里" % label
