"""probe/actions.py — 动作扫描 + 逐动作依赖分析（ready / blocked）。

本模块两件事：
1. **ActionsProber**（既有能力，不变）：扫描动作目录产出动作清单 + 静态依赖表
   `ACTION_DEPENDENCY_MAP`；
2. **analyze_actions()**（本轮补齐，对应 PROBE_PLAN.md §4.7）：逐动作读 `deps`
   字段，与探测到的能力比对，产出 `ready` / `blocked` / `missing_deps`。

为什么补这一块（计划与实现的差距）
----------------------------------
PROBE_PLAN.md §4.7 规划了 `analyze_actions(actions_dir, probe_report)`，§9 Phase 1
还把里程碑勾成「probe() 返回动作的 ready/blocked 状态 ✅ 已实现」，但产品里
**从来没有**这段代码：改前的 ready/blocked 语义在 `intent.IntentRouter` 里，
判据是「动作出现在探测报告里 = ready」，完全不看动作声明的依赖。

改后新增的是**逐动作、按声明的依赖**判定的那一层：

    动作声明 deps → 解析 → 与探测到的能力比对 → ready / blocked(+missing_deps)

与 IntentRouter 的关系（**互补，不是替代**）
--------------------------------------------
* `IntentRouter._is_ready()`（粗粒度）：动作**出现在报告里**就算 ready ——
  只看「这次扫描有没有发现这个动作」，不看它需要什么。
* `analyze_actions()`（细粒度）：动作出现了，但声明的依赖探测不到（或者引用的
  动作不存在 / 依赖成环 / 文件解析失败），就判 blocked 并点名缺哪一项。
* 两者可以叠加：先按 IntentRouter 过滤「报告里没有的动作」，再按本模块的
  `verdicts` 过滤「有但依赖不满足的动作」。`ActionsProber` 现在把这份分析
  作为独立条目 `action_readiness` 放进探测报告，`IntentRouter` 若想用更细的
  判据，读该条目的 `extra["verdicts"]` 即可（**需要改 `intent.py`，不在本次
  作用域，需求已写进汇报**）。

三档判定：`ready` / `degraded` / `blocked`
------------------------------------------
* `ready`    —— deps 满足 **且** 入口块指令通过引擎白名单（见下「能静态判什么」）；
* `degraded` —— deps 满足，但**入口块用了引擎不认识的指令** → 执行期必失败。
  **刻意不等于 blocked**：依赖是满足的、动作本身存在，只是当前跑不起来；
  做成 blocked 会让用户以为"工具坏了/动作没装"，属于假阴性误杀。
* `blocked`  —— deps 不满足 / 文件解析失败 / 依赖成环 / 引用了不存在的动作。

实测触发 `degraded` 的真实例子：`actus.basics.calculator`（以及 image_viewer /
text_editor / todo_list 三个 webview2 种子）的入口块写了
`webview2 #!run tag=main ... devtools=false`，而桥接层白名单里没有 `devtools`
→ `actus run` 报「未知指令: devtools」。

**能静态判什么、不能判什么（本轮调研结论）**
-------------------------------------------
能（且**与运行期判定等价**，不是近似）：
* **指令**：`vools.bridge.md.directives.BLOCK_DIRECTIVE_KEYS` 是模块级**静态常量**
  白名单；`validate_directives()` 正是 `run_block()` 在语言分派**之前**调用的同一个
  函数（`bridges/vools/bridge/md/runner.py:488`）。本模块直接复用它 → 判据同源。
* **作用范围**：只校验「执行期真的会跑到的块」—— 声明了 `entry` 时是 tag 含该值的块
  （executor 传 `only=[action.entry]`）；没有 `entry` 时是**所有块**（executor 不过滤），
  且 `run_block` 的指令校验在 `skip` 判定之前，连 skip 块也会报错。

不能（**刻意不做**，避免假阴性）：
* **语言可路由性**：只能问 `known_languages()`，要 import `vools.bridge.md.runner`
  （实测冷导入 ~300-500ms），而 actus 的 `validate.py` 已经对每个块用
  `is_routable()` 校验语言 —— 在 probe 里重复一遍性价比极低；
* **编译器/运行时是否真的可用**、运行期参数是否有效：只有执行期能确定。

判错的代价不对称，所以纪律是：**取不到校验器 / 校验抛异常 → 一律不判 degraded**
（只记 `entry_block.checked=False` 与错误文本），宁可漏判也不误杀。

`ready_scope="deps_and_entry_directives"` 随结果与每个 verdict 一起下发，
让消费方知道 ready 覆盖到哪一步（仍不含语言可路由性/运行期可用性）。

依赖语法（不另立一套）
----------------------
`deps` 的写法以 `vools/actus/dependency.py` 的 `DependencyResolver.parse_deps`
为**单一真源**，本模块只负责「解析结果 → 与探测报告比对」：
    builtin:<name>   引擎内置
    system:<cmd>     系统命令（system_tools / compilers 探测）
    pip:<pkg>        Python 包（python_packages 探测）
    npm:<pkg>        npm 包（**探测报告不含**，判 unverifiable → blocked）
    mcp:<server>     MCP server（**探测报告不含**，同上）
    action:<id>      其它动作（本次扫描里存在且自身 ready 才算满足）
    runtime:<name>   语言运行时（runtimes 探测；本轮已正式进 resolver 真源）
    cs_<name>        C# 构建产物（**探测报告不含**，同上）
  裸字符串按 action 依赖处理（与 resolver 一致）。

判定纪律（不乐观）
------------------
* **探测不到 = blocked**，绝不因为"没查到问题"就默认 ready；
* 报告无法判定的依赖类型（npm / mcp / cs_build）同样判 blocked，并在
  `unverifiable` 里点名「为什么无法判定」，不做静默放行；
* `degraded` **不参与** IntentRouter 的 ready 门禁（它只挡 blocked）：动作依赖满足、
  只是静态可判地跑不起来，仍可被推荐 —— 但报告里带着可查的原因。
* `deps` 字段缺失 **或值为 null** → 不计为"依赖满足"，而是单独列进 `undeclared`
  并在每个动作的 verdict 里带 `deps_declared: false`（**明确信号，不静默当 ready**）；
  `null` 与「键缺失」语义相同、标签不同（`<deps:null>` vs `<deps>`），
  而 `deps: []` 是作者**明确声明**"我没有依赖"，属于有效信息，保持 ready 且无信号；
* `deps` 类型错误 / 动作文件解析失败 / 依赖成环 → 都有各自的 signal。

两类能力来源（都标注在 `index_source` 里，不混为一谈）
------------------------------------------------------
* `probe_report`（**优先**）：传入 `ProbeReport`（或 `to_dict()` 的 dict、条目列表、
  计划 §4.7 的 {"runtimes": [...], "system_tools": [...], "python_packages": [...]}
  形态都收）→ 与「已探测到的能力」比对，这是 §4.7 的本意；
* `self-probe`（兜底）：没给报告时用**与探测器同一批原语**本地判定
  （PATH 索引 + `importlib.metadata`），这样 `ActionsProber` 在报告尚在生成时
  也能给出真实判定，而不是写一个假的 deferred 占位。
"""


__all__ = [
    "ActionsProber",
    "ACTION_DEPENDENCY_MAP",
    "analyze_actions",
]

import os
import sys
import time

from .base import Prober, ProbeItem
from ..constants import is_action_file
from ..indexer import _action_roots, _repo_root

# 动作依赖映射：动作使用的工具/库 → 依赖类型（**静态**表，与「逐动作 deps」无关）
ACTION_DEPENDENCY_MAP = {
    "screenshot": {"tools": ["scrot", "import", "PowerShell"], "packages": ["Pillow", "mss"]},
    "clipboard": {"tools": ["clip", "pbcopy", "PowerShell"], "packages": ["pyperclip", "pywin32"]},
    "convert": {"tools": [], "packages": ["Pillow", "opencv-python"]},
    "json": {"tools": ["jq", "yq"], "packages": []},
    "http": {"tools": ["curl", "wget"], "packages": ["requests", "httpx"]},
    "dialog": {"tools": [], "packages": ["pywin32", "tkinter"]},
    "git": {"tools": ["git"], "packages": ["GitPython"]},
    "sftp": {"tools": ["sftp", "scp"], "packages": ["paramiko"]},
    "checksum": {"tools": ["md5sum", "sha256sum"], "packages": []},
    "mcp": {"tools": [], "packages": ["mcp"]},
    "cron": {"tools": ["crontab", "schtasks"], "packages": ["schedule"]},
    "macro": {"tools": [], "packages": ["pyautogui", "pynput"]},
    "watch": {"tools": [], "packages": ["watchdog"]},
    "encode": {"tools": [], "packages": []},
    "form": {"tools": [], "packages": []},
    "secret": {"tools": [], "packages": []},
}

# 探测报告里能回答「这类依赖满足了吗」的分类映射
_SYSTEM_CATEGORIES = ("system_tools", "compilers")
_RUNTIME_CATEGORIES = ("runtimes",)
_PYTHON_CATEGORIES = ("python_packages",)

# 报告无法判定的依赖类型 → 原因（这些一律 blocked，不静默放行）
_UNVERIFIABLE_REASONS = {
    "npm": "探测报告只覆盖 Python 包，未探测 npm 包",
    "mcp": "探测报告未覆盖 MCP server 能力",
    "cs_build": "探测报告未覆盖 C# 构建产物（cs_*）",
}

# 三档判定：
#   ready    = deps 满足 **且** 入口块指令通过引擎白名单（静态可判）
#   degraded = deps 满足，但入口块用了引擎**不认识**的指令 → 执行期必失败
#              （**不等于 blocked**：依赖是满足的，只是这个动作当前跑不起来；
#               故意不做成 blocked，避免"以为工具坏了"的假阴性）
#   blocked  = deps 不满足 / 文件解析失败 / 依赖成环 / 引用不存在的动作
VERDICT_READY = "ready"
VERDICT_DEGRADED = "degraded"
VERDICT_BLOCKED = "blocked"

# `verdict=ready` 的语义范围（随结果下发，防止消费方过度解读）。
# "deps_and_entry_directives" = deps 都满足 + 动作文件可解析 + **入口块指令**
# 通过引擎的 `BLOCK_DIRECTIVE_KEYS` 白名单。
# **仍不保证**：语言可路由性（validate.py 的 is_routable 已逐块覆盖）、
# 编译器/运行时真的装了、运行期参数是否有效 —— 那些只能执行期确定。
READY_SCOPE_DEPS_AND_ENTRY_DIRECTIVES = "deps_and_entry_directives"
# 兼容旧名（外部可能 import 过；语义已被上面的新常量取代）
READY_SCOPE_DEPS_ONLY = "deps_and_entry_directives"


# ---------------------------------------------------------------------------
# 扫描：动作 + 声明的 deps
# ---------------------------------------------------------------------------

def _scan_actions_dir(actions_dir: str = None) -> dict:
    """扫描动作，提取 id / path（动作清单条目的数据源）。

    **扫描根语义与 `indexer._action_roots()` 统一**（`docs/actus/03-动作规范.md:32`）：
    * 显式传 `actions_dir` → 只扫该目录（测试 / 单仓场景）；
    * 缺省 → 扫**全部动作根**：用户项目 `actions/` + 包内种子目录（去重保序）。

    改前缺省只扫 `_repo_root()/actions`（单根）→ 动作清单条目（6 个）与
    `action_readiness`（14 个，从一开始就用多根）覆盖范围不一致，导致 IntentRouter
    永远看不到 8 个包内种子动作（4 个 GUI + 4 个 demo），而 docs 明确宣传「pip install
    自带 4 个基线 GUI 种子动作」。这是口径漂移，不是设计（原 PROBE_PLAN 写单根、
    后续 §4.7 与 docs/03 都改成多根）。
    """
    roots = _action_roots(actions_dir)
    # 兼容字段：无显式目录时保留「仓库根 actions/」作为主根（既有消费方读它）
    primary_dir = actions_dir if actions_dir is not None else os.path.join(_repo_root(), "actions")

    actions = []
    seen_ids = set()
    exists = False
    for root in roots:
        if not os.path.isdir(root):
            continue
        exists = True
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                if not is_action_file(fn):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    rel = os.path.relpath(full, root).replace(os.sep, "/")
                except ValueError:          # 跨盘符
                    rel = full.replace(os.sep, "/")
                # 解析动作真实 id（与 indexer 的 aid 一致），失败则退化为相对路径
                aid = rel
                try:
                    from ..model import parse_cfg_from_file
                    act = parse_cfg_from_file(full)
                    aid = (act.meta or {}).get("id") or rel
                except Exception:
                    pass
                # 同 id 多份（用户项目与包内种子撞车）：先到的优先（用户优先）
                if aid in seen_ids:
                    continue
                seen_ids.add(aid)
                actions.append({"id": aid, "path": full})

    return {"actions_dir": primary_dir, "exists": exists,
            "actions": actions, "roots": list(roots)}


def _scan_actions_with_deps(actions_dir: str = None) -> dict:
    """扫描**全部动作根**并取出每个动作声明的 deps（analyze_actions 的数据源）。

    actions_dir 为空时沿用 indexer 的多根语义（用户项目 actions/ 优先于包内种子），
    这样「真实种子动作」也能被判定；显式给 actions_dir 时只扫那一个目录。

    复用 `model.parse_cfg_from_file`（与既有扫描同一个解析器，单一真源），
    并单独接住每个文件的解析异常 —— 坏文件既不能炸整批，也不能被静默当成 ready。
    """
    roots = _action_roots(actions_dir)
    entries = []
    duplicate_ids = []
    seen_ids = {}
    exists = False

    for root in roots:
        if not os.path.isdir(root):
            continue
        exists = True
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                if not is_action_file(fn):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    rel = os.path.relpath(full, root).replace(os.sep, "/")
                except ValueError:          # 跨盘符：relative 无解
                    rel = full.replace(os.sep, "/")
                entry = {
                    "id": rel,
                    "rel": rel,
                    "path": full,
                    "root": root,
                    "deps_raw": None,
                    "deps_declared": False,
                    # deps 字段的**形态**（三种必须可区分）：
                    #   missing = 键整块没有        → 未声明
                    #   null    = 键在但值是 None   → 也是未声明（作者没填）
                    #   list    = 作者明确写了列表（含 []，是有效信息：我没依赖）
                    #   invalid = 键在但类型不对    → 交给 invalid_deps_field 信号
                    "deps_field": "missing",
                    "entry": "",
                    "blocks": [],
                    "parse_error": None,
                }
                try:
                    from ..model import parse_cfg_from_file
                    action = parse_cfg_from_file(full)
                    meta = action.meta or {}
                    entry["id"] = meta.get("id") or rel
                    # 入口块信息：只读解析结果（parse_cfg_from_file 本来就要跑，
                    # 不额外 IO）。用于下一步「入口块指令是否被引擎认识」的静态判定。
                    entry["entry"] = (meta.get("entry") or "")
                    entry["blocks"] = list(getattr(action, "blocks", None) or [])
                    if "deps" in meta:
                        raw_deps = meta.get("deps")
                        if raw_deps is None:
                            # 字段存在但没填：信息量与「键缺失」完全一样（作者都没写依赖），
                            # 不能静默当成「已声明、无依赖」—— 否则 null 就绕过了 undeclared 信号。
                            entry["deps_field"] = "null"
                        elif isinstance(raw_deps, (list, tuple)):
                            entry["deps_field"] = "list"
                            entry["deps_declared"] = True
                            entry["deps_raw"] = raw_deps
                        else:
                            entry["deps_field"] = "invalid"
                            entry["deps_declared"] = True   # 作者写了东西，只是类型错
                            entry["deps_raw"] = raw_deps
                except Exception as exc:
                    entry["parse_error"] = "%s: %s" % (type(exc).__name__, exc)

                # 同 id 多份（用户项目与包内种子撞车）：先到的优先（用户优先）
                ident = entry["id"]
                if ident in seen_ids:
                    duplicate_ids.append({
                        "id": ident,
                        "kept": seen_ids[ident],
                        "ignored": full,
                    })
                    continue
                seen_ids[ident] = full
                entries.append(entry)

    return {
        "roots": roots,
        "actions_dir": actions_dir or (roots[0] if roots else None),
        "exists": exists,
        "entries": entries,
        "duplicate_ids": duplicate_ids,
    }


# ---------------------------------------------------------------------------
# 能力索引：优先用探测报告，其次用与探测器同一批原语本地判定
# ---------------------------------------------------------------------------

def _report_items(probe_report):
    """把各种形态的探测报告统一成「条目序列」。取不到返回 None。"""
    if probe_report is None:
        return None
    items = getattr(probe_report, "items", None)
    if isinstance(items, list):
        return items
    if isinstance(probe_report, dict):
        if isinstance(probe_report.get("items"), list):
            return probe_report["items"]
        # 计划 §4.7 的按分类形态：{"runtimes": [...], "system_tools": [...], ...}
        collected = []
        for category in (_SYSTEM_CATEGORIES + _RUNTIME_CATEGORIES
                         + _PYTHON_CATEGORIES):
            for item in probe_report.get(category) or []:
                if isinstance(item, dict):
                    item = dict(item)
                    item.setdefault("category", category)
                collected.append(item)
        if collected:
            return collected
        return None
    if isinstance(probe_report, list):
        return probe_report
    return None


def _field(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _capabilities_from_report(probe_report):
    """探测报告 → 能力集合。报告不可用时返回 None（由调用方决定怎么处理）。"""
    items = _report_items(probe_report)
    if items is None:
        return None

    caps = _ReportCapabilities()
    for item in items:
        name = _field(item, "name")
        if not name:
            continue
        available = _field(item, "available")
        if available is None:                     # 计划形态用 installed
            available = _field(item, "installed")
        if not available:
            continue
        category = _field(item, "category") or ""
        if category in _SYSTEM_CATEGORIES:
            caps.system.add(name)
        elif category in _RUNTIME_CATEGORIES:
            caps.runtime.add(name)
        elif category in _PYTHON_CATEGORIES:
            caps.python.add(name)
    return caps


class _ReportCapabilities(object):
    """探测报告给出的能力集合（与 `_SelfCapabilities` 同一个判定接口）。"""

    source = "probe_report"

    def __init__(self):
        self.system = set()
        self.runtime = set()
        self.python = set()

    def has_system(self, name):
        return name in self.system

    def has_runtime(self, name):
        return name in self.runtime

    def has_python(self, name):
        return name in self.python


class _SelfCapabilities(object):
    """没给探测报告时的兜底：用与探测器**同一批原语**本地判定。

    * 系统命令 / 运行时：`system_tools._build_path_index` + `_lookup_in_path_index`
      （PATH 只 listdir 一遍，判据仍交回 `shutil.which`）；
    * Python 包：`importlib.metadata.version`（与 python_pkgs 探测器同源）。
    索引是**懒建**的：动作没声明 deps 时一次也不会建（不为零收益付 50ms）。
    """

    source = "self-probe"

    def __init__(self):
        self._path_index = None
        self._system_cache = {}
        self._pkg_cache = {}

    def _index(self):
        if self._path_index is None:
            from .system_tools import _build_path_index
            self._path_index = _build_path_index()
        return self._path_index

    def _command_exists(self, name):
        if not name:
            return False
        if name in self._system_cache:
            return self._system_cache[name]
        try:
            from .system_tools import _lookup_in_path_index
            found = bool(_lookup_in_path_index(name, self._index()))
        except Exception:
            found = False
        self._system_cache[name] = found
        return found

    def has_system(self, name):
        return self._command_exists(name)

    def has_runtime(self, name):
        """运行时：shell/shell 这类抽象名按 runtimes 探测器的别名表展开。"""
        if self._command_exists(name):
            return True
        try:
            from .runtimes import _CMD_MAP
        except Exception:
            return False
        for command in _CMD_MAP.get(name, []):
            if self._command_exists(command):
                return True
        return False

    def has_python(self, name):
        if not name:
            return False
        if name in self._pkg_cache:
            return self._pkg_cache[name]
        found = False
        try:
            try:
                from importlib import metadata as _metadata
            except ImportError:                     # py3.6
                import importlib_metadata as _metadata  # type: ignore
            _metadata.version(name)
            found = True
        except Exception:
            found = False
        self._pkg_cache[name] = found
        return found


def _capabilities(probe_report):
    """优先用报告；报告不可用时退回 self-probe（并如实标注来源）。"""
    caps = _capabilities_from_report(probe_report)
    if caps is not None:
        return caps
    return _SelfCapabilities()


# ---------------------------------------------------------------------------
# 依赖判定
# ---------------------------------------------------------------------------

def _dep_label(raw, dep):
    """依赖的可读标识：字符串保留原文，dict 形态归一成 type:name。"""
    if isinstance(raw, str):
        return raw
    dep_type = getattr(dep, "type", None)
    kind = getattr(dep_type, "value", None) or "action"
    name = getattr(dep, "name", "") or "?"
    if kind == "lang":
        kind = getattr(dep, "lang_manager", "pip") or "pip"
    return "%s:%s" % (kind, name)


def _parse_declared_deps(raw_deps):
    """解析动作声明的 deps，返回 (parsed, issues)。

    语法交给 `dependency.DependencyResolver.parse_deps`（单一真源；`runtime:`
    前缀本轮已正式进 resolver 真源，本模块不再自己打补丁）。
    但 resolver 对**非 str/dict 元素是静默跳过的**，这里先自己筛一遍并留痕 ——
    "deps 类型错误"必须有信号，不能被 resolver 静默吃掉。
    """
    parsed = []
    issues = []
    if raw_deps is None:
        return parsed, issues
    if not isinstance(raw_deps, (list, tuple)):
        issues.append({
            "dep": repr(raw_deps)[:80],
            "status": "invalid_deps_field",
            "reason": "deps 必须是列表，实际是 %s" % type(raw_deps).__name__,
        })
        return parsed, issues

    raw_list = list(raw_deps)
    usable = []
    for position, raw in enumerate(raw_list):
        if isinstance(raw, (str, dict)):
            usable.append((position, raw))
        else:
            issues.append({
                "dep": repr(raw)[:80],
                "status": "invalid_dep_entry",
                "reason": "deps[%d] 必须是字符串或对象，实际是 %s" % (
                    position, type(raw).__name__),
            })

    if not usable:
        return parsed, issues

    try:
        from ..dependency import get_resolver
        deps = get_resolver().parse_deps([raw for _position, raw in usable])
    except Exception as exc:
        issues.append({
            "dep": "<deps>",
            "status": "parse_error",
            "reason": "依赖解析失败（%s: %s）" % (type(exc).__name__, exc),
        })
        return parsed, issues

    # resolver 与入参一一对应；长度不符时按解析失败处理，不猜测对应关系
    if len(deps) != len(usable):
        issues.append({
            "dep": "<deps>",
            "status": "parse_error",
            "reason": "依赖解析结果条数不符（入 %d / 出 %d）" % (
                len(usable), len(deps)),
        })
        return parsed, issues

    for (_position, raw), dep in zip(usable, deps):
        parsed.append((raw, dep))
    return parsed, issues


def _dep_kind(dep):
    """Dependency → (kind, name)，kind 取值见 _UNVERIFIABLE_REASONS / 下面的分支。"""
    dep_type = getattr(dep, "type", None)
    dep_type = getattr(dep_type, "value", dep_type)
    name = getattr(dep, "name", "") or ""
    if dep_type == "lang":
        manager = (getattr(dep, "lang_manager", "") or "pip").lower()
        return ("npm" if manager == "npm" else "pip"), name
    if dep_type in ("system", "builtin", "mcp", "action", "cs_build", "runtime"):
        return dep_type, name
    return "unknown", name


def _entry_check_targets(entry):
    """选出执行期**会被跑到**的块（入口块语义，与 executor 的 only=[entry] 对齐）。

    * 动作声明了 `entry`：只跑 tag 里含该值的块（executor 传 `only=[action.entry]`）；
    * 没声明 entry：executor 不传 only → **所有块**都会跑，因此所有块都要校验
      （注意 run_block 的指令校验发生在 skip 判定**之前**，连 skip 块也会报错）。
    """
    blocks = entry.get("blocks") or []
    wanted = (entry.get("entry") or "").strip()
    if wanted:
        return [b for b in blocks if wanted in (b.get("tag") or [])]
    return list(blocks)


def _check_entry_block_directives(entry):
    """用引擎自己的指令白名单校验「会被执行到的块」，返回 (degraded_reasons, info)。

    **为什么只做指令、不做语言**（本轮调研结论）：
      * 指令白名单 `vools.bridge.md.directives.BLOCK_DIRECTIVE_KEYS` 是**模块级静态
        常量**，而 `validate_directives()` 正是 `run_block()` 在语言分派**之前**
        调用的同一个函数（bridge/md/runner.py:488）→ 静态判定与运行期判定**等价**，
        不是近似；
      * 语言可路由性只能问 `known_languages()`，它要 import
        `vools.bridge.md.runner`（实测 ~297ms），而 actus 的 `validate.py` 已经
        对每个块用 `is_routable()` 校验过语言 —— 在 probe 里重复一遍性价比极低。
    宁可漏判也不误判：取不到校验器时**不判定**（`checked=False`），绝不猜。
    """
    targets = _entry_check_targets(entry)
    info = {
        "checked": False,
        "entry": entry.get("entry") or "",
        "blocks": [],
    }
    if not targets:
        return [], info

    try:
        from vools.bridge.md.directives import validate_directives
    except Exception as exc:            # 校验器不可用 → 不判定（不猜）
        info["error"] = "%s: %s" % (type(exc).__name__, exc)
        return [], info

    reasons = []
    for block in targets:
        language = (block.get("language") or "").lower()
        directives = block.get("directives") or {}
        try:
            errors = validate_directives(directives, language)
        except Exception as exc:        # 单个块校验炸了 → 记信号但不判 degraded
            info["blocks"].append({
                "index": block.get("index"), "language": language,
                "ok": None, "error": "%s: %s" % (type(exc).__name__, exc),
            })
            continue
        info["blocks"].append({
            "index": block.get("index"), "language": language,
            "ok": not errors, "errors": errors,
        })
        for message in errors:
            reasons.append({
                "kind": "entry_block_unsupported",
                "dep": "<entry-block>",
                "status": "degraded",
                "reason": "块 index=%s（language=%s）的指令不被引擎支持：%s"
                          "（执行期会在 run_block 的指令校验处直接失败）"
                          % (block.get("index"), language or "?", message),
            })
    info["checked"] = True
    return reasons, info


def _check_simple_dep(kind, name, caps):
    """非 action 依赖：返回 (status, reason)。status ∈ ok / missing / unverifiable。"""
    if kind == "builtin":
        # 引擎内置：探测报告本身由引擎产出，"能跑 probe" 即代表内置能力在
        return "ok", "引擎内置能力"
    if kind == "system":
        if caps.has_system(name):
            return "ok", "系统工具已在探测中确认可用"
        return "missing", "系统工具未被探测到（不在 PATH / 未安装）"
    if kind == "pip":
        if caps.has_python(name):
            return "ok", "Python 包已被探测到"
        return "missing", "Python 包未被探测到（未安装）"
    if kind == "runtime":
        if caps.has_runtime(name):
            return "ok", "运行时已被探测到"
        return "missing", "运行时未被探测到（不可用或未安装）"
    if kind in _UNVERIFIABLE_REASONS:
        return "unverifiable", _UNVERIFIABLE_REASONS[kind]
    return "unverifiable", "未知依赖类型 %r，无法从探测结果判定" % (kind,)


def analyze_actions(actions_dir: str = None, probe_report=None) -> dict:
    """分析 .actus.md 动作的依赖满足情况（PROBE_PLAN.md §4.7）。

    参数:
        actions_dir:  动作目录；为空时扫 indexer 的全部动作根（用户项目 + 包内种子）
        probe_report: 探测报告，收 `ProbeReport` / `to_dict()` 的 dict / 条目列表 /
                      计划形态 {"runtimes": [...], ...}；为空时用本地原语兜底判定
                      （`index_source` 会如实标出用的是哪一种）

    返回 dict:
        total / ready / blocked / missing_deps  ← §4.7 契约字段
        **ready_scope**: `"deps_and_entry_directives"` —— `verdict=ready` 的语义限定符
        degraded:      入口块指令不被引擎支持的动作数（**不计入 blocked**）
        verdicts:      {action_id: {verdict, ready_scope, deps, missing_deps,
                                    blocked_reasons, degraded_reasons, entry_block,
                                    deps_declared, deps_field, path, parse_error}}
                       verdict ∈ {"ready", "degraded", "blocked"}
        undeclared:    [action_id ...]   没声明 deps 的动作（键缺失或值为 null；明确信号）
        parse_failed:  [action_id ...]   连文件都解析不了的动作
        unverifiable:  {action_id: [dep ...]}  报告无法判定的依赖
        duplicate_ids: [{id, kept, ignored}]   同 id 多份的动作文件
        index_source:  "probe_report" | "self-probe"
        exists:        动作根是否存在

    **`verdict=ready` 到底是什么保证**（重要，消费方必读）：
    ready = 「声明的 deps 都已满足，且动作文件可解析」，**不保证**入口块的语言/
    指令被当前引擎支持 —— 那取决于执行期才能确定的能力（例如某动作的 `webview2`
    块里用了引擎未实现的 `devtools` 指令：依赖全满足、文件也合法，但 `actus run`
    会在执行期报「未知指令」）。实测案例：`actus.basics.calculator` 在本机
    `verdict=ready`，而 `actus run actus.basics.calculator` 失败。
    需要更强保证的消费方（如 IntentRouter 门禁）应把本字段当作**必要条件而非
    充分条件**，并结合执行期结果；`ready_scope` 字段就是为了让这层限定可被机器读取。

    判定纪律：**探测不到 = blocked**；报告无法判定的依赖类型同样 blocked；
    deps 缺失/类型错误/文件解析失败/依赖成环都有各自信号，绝不静默默认 ready。
    """
    started = time.monotonic()
    scan = _scan_actions_with_deps(actions_dir)
    entries = scan["entries"]
    caps = _capabilities(probe_report)

    action_ids = set()
    for entry in entries:
        action_ids.add(entry["id"])

    verdicts = {}
    for entry in entries:
        verdicts[entry["id"]] = {
            "verdict": "pending",
            # 逐动作也带一份语义限定符：消费方只拿到 verdicts 时同样不会被
            # `ready` 误导（值同 results["ready_scope"]）。
            "ready_scope": READY_SCOPE_DEPS_AND_ENTRY_DIRECTIVES,
            "deps": [],
            "missing_deps": [],
            "blocked_reasons": [],
            "deps_declared": bool(entry["deps_declared"]),
            "deps_field": entry.get("deps_field", "missing"),
            "path": entry["path"],
            "parse_error": entry["parse_error"],
        }

    entries_by_id = {entry["id"]: entry for entry in entries}

    # ── 第一轮：文件解析失败 / 非 action 依赖 ──
    action_deps = {}
    for entry in entries:
        ident = entry["id"]
        record = verdicts[ident]

        if entry["parse_error"]:
            record["verdict"] = "blocked"
            record["blocked_reasons"].append({
                "dep": "<action file>",
                "status": "parse_error",
                "reason": "动作文件解析失败：%s" % entry["parse_error"],
            })
            continue

        parsed, issues = _parse_declared_deps(entry["deps_raw"])
        for issue in issues:
            record["blocked_reasons"].append(issue)
        record["deps"] = [_dep_label(raw, dep) for raw, dep in parsed]

        blocked = bool(issues)
        pending_action_deps = []
        for raw, dep in parsed:
            kind, name = _dep_kind(dep)
            label = _dep_label(raw, dep)
            if kind == "action":
                pending_action_deps.append((label, name))
                continue
            status, reason = _check_simple_dep(kind, name, caps)
            if status != "ok":
                blocked = True
                record["missing_deps"].append(label)
                record["blocked_reasons"].append({
                    "dep": label, "status": status, "reason": reason,
                })
        action_deps[ident] = pending_action_deps

        if blocked:
            record["verdict"] = "blocked"
        elif not entry["deps_declared"]:
            # 没声明 deps（键缺失 或 值为 null）：判 ready 但**明确标出**未做核实。
            # 两者语义相同、标签不同，保证「null 绕过 undeclared 信号」不再发生，
            # 同时 `deps: []`（作者明确声明"我没有依赖"）不受影响。
            record["verdict"] = "ready"
            if entry.get("deps_field") == "null":
                record["blocked_reasons"].append({
                    "dep": "<deps:null>",
                    "status": "undeclared",
                    "reason": "deps 字段为 null（存在但没填，语义等同未声明）："
                              "ready 仅表示「没有声明未满足的依赖」，"
                              "不代表运行所需能力已核实",
                })
            else:
                record["blocked_reasons"].append({
                    "dep": "<deps>",
                    "status": "undeclared",
                    "reason": "动作没有声明 deps：ready 仅表示「没有声明未满足的依赖」，"
                              "不代表运行所需能力已核实",
                })
        elif pending_action_deps:
            record["verdict"] = "pending"
        else:
            record["verdict"] = "ready"

    # ── 第二轮：action 依赖的不动点迭代（并检出环）──
    # 注意：**已经因其它依赖判 blocked 的动作也要跑这一轮** —— 否则它的
    # `action:` 依赖永远不会被评估，missing_deps 里就会漏掉「引用的动作不存在」。
    # 用 _action_deps_resolved 保证每个动作只结算一次（幂等，不重复追加 reason）。
    rounds = 0
    max_rounds = len(entries) + 2
    changed = True
    settled = set()          # 已结算过 action 依赖的动作 id（幂等，不重复追加 reason）
    while changed and rounds < max_rounds:
        changed = False
        rounds += 1
        for ident, pending in action_deps.items():
            record = verdicts[ident]
            if not pending or ident in settled:
                continue
            all_ready = True
            resolved = True
            new_reasons = []
            for label, target in pending:
                if target not in action_ids:
                    all_ready = False
                    new_reasons.append({
                        "dep": label, "status": "missing",
                        "reason": "引用的动作不存在（本次扫描未发现）",
                    })
                    continue
                target_verdict = verdicts[target]["verdict"]
                if target_verdict == "pending":
                    resolved = False
                    all_ready = False
                    continue
                if target_verdict != "ready":
                    all_ready = False
                    new_reasons.append({
                        "dep": label, "status": "blocked",
                        "reason": "依赖的动作未就绪（%s = %s）" % (
                            target, target_verdict),
                    })
            if not resolved:
                continue                     # 目标还没结算，等下一轮
            settled.add(ident)
            if all_ready:
                if record["verdict"] == "pending":
                    record["verdict"] = "ready"
            else:
                record["verdict"] = "blocked"
                for reason in new_reasons:
                    record["missing_deps"].append(reason["dep"])
                    record["blocked_reasons"].append(reason)
            changed = True

    # 迭代结束仍 pending = 依赖成环（环上每个动作都不可能被判定就绪）
    for ident, record in verdicts.items():
        if record["verdict"] == "pending":
            record["verdict"] = "blocked"
            record["blocked_reasons"].append({
                "dep": "<cycle>",
                "status": "cycle",
                "reason": "action 依赖成环（或环上依赖无法判定），不可能就绪",
            })
            for label, _target in action_deps.get(ident, []):
                if label not in record["missing_deps"]:
                    record["missing_deps"].append(label)

    # ── 第三轮：degraded（deps 满足，但入口块指令不被引擎支持）──
    # 只用引擎自己的白名单判定「会被执行到的块」，判错的代价是"把能跑的动作说成
    # 跑不了"，所以：取不到校验器/校验抛异常的块一律**不判** degraded，
    # 只把 checked/error 记进 verdict 供排障。degraded **不进** blocked 计数，
    # 也不参与 IntentRouter 的门禁（它只挡 blocked）。
    for ident, record in verdicts.items():
        if record["verdict"] != VERDICT_READY:
            continue
        entry = entries_by_id.get(ident)
        if entry is None:
            continue
        reasons, info = _check_entry_block_directives(entry)
        record["entry_block"] = info
        if reasons:
            record["verdict"] = VERDICT_DEGRADED
            record["degraded_reasons"] = reasons

    # ── 汇总 ──
    # ready_scope 是**语义限定符**，随结果与每个 verdict 一起下发给消费方：
    #   "deps_and_entry_directives" = verdict=ready 代表「declared deps 都满足 +
    #   动作文件可解析 + 入口块指令通过引擎白名单」。**仍不保证**语言可路由性
    #   （validate.py 的 is_routable 已逐块覆盖）、编译器真的装了、运行期有效。
    # 实测会落到 degraded 的例子：`actus.basics.calculator` 等 4 个 webview2 动作
    #   的入口块写了引擎未实现的 `devtools` 指令 → `actus run` 报「未知指令: devtools」。
    results = {
        "total": len(entries),
        "ready": 0,
        "degraded": 0,
        "blocked": 0,
        "ready_scope": READY_SCOPE_DEPS_AND_ENTRY_DIRECTIVES,
        "missing_deps": {},
        "verdicts": verdicts,
        "undeclared": [],
        "parse_failed": [],
        "unverifiable": {},
        "duplicate_ids": scan["duplicate_ids"],
        "index_source": caps.source,
        "actions_dir": scan["actions_dir"],
        "roots": scan["roots"],
        "exists": scan["exists"],
    }
    for ident, record in verdicts.items():
        verdict = record["verdict"]
        if verdict == VERDICT_READY:
            results["ready"] += 1
        elif verdict == VERDICT_DEGRADED:
            results["degraded"] += 1
        else:
            results["blocked"] += 1
        if record["missing_deps"]:
            results["missing_deps"][ident] = list(record["missing_deps"])
        if record["parse_error"]:
            results["parse_failed"].append(ident)
        # 未声明 deps 只统计「文件能解析、但没写 deps」的动作；
        # 解析失败的动作已在 parse_failed 里点名，不重复计入 undeclared。
        if not record["deps_declared"] and not record["parse_error"]:
            results["undeclared"].append(ident)
        unverifiable = [reason["dep"] for reason in record["blocked_reasons"]
                        if reason.get("status") == "unverifiable"]
        if unverifiable:
            results["unverifiable"][ident] = unverifiable

    results["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 1)
    return results


class ActionsProber(Prober):
    """动作依赖分析探测器。

    条目（顺序与名字保持既有契约）：
      1. `actions`              动作清单（扫描结果，既有）
      2. `action_dependencies`  静态依赖表 `ACTION_DEPENDENCY_MAP`（既有）
      3. `action_readiness`     **新增**：逐动作 ready/blocked（PROBE_PLAN.md §4.7）

    新增的是**追加条目**，既有两个条目一个字段都没改（`intent.py` 与
    `tests/test_probe_actions.py` 都依赖它们的形状）。
    """

    def __init__(self, timeout=5, probe_report=None):
        Prober.__init__(self, timeout=timeout)
        # 可选：显式传入探测报告时，ready/blocked 按报告里的能力判定；
        # 不传则用本地原语兜底（报告尚在生成中也能算出真实结果）
        self.probe_report = probe_report
        self.last_readiness = None

    def probe(self) -> list:
        info = _scan_actions_dir()
        results = []

        # 添加动作列表
        results.append(ProbeItem(
            name="actions",
            category="actions",
            available=info["exists"],
            extra={
                "actions_dir": info["actions_dir"],
                # 本轮起与 action_readiness 同源：缺省扫**全部动作根**（用户项目 + 包内种子），
                # 显式传目录时只扫该目录。roots 与 readiness 对称，便于排障对账。
                "roots": info.get("roots") or [],
                "action_count": len(info["actions"]),
                "actions": info["actions"][:50],  # 限制数量
            },
        ))

        # 添加依赖映射
        results.append(ProbeItem(
            name="action_dependencies",
            category="actions",
            available=True,
            extra=ACTION_DEPENDENCY_MAP,
        ))

        # 添加逐动作 ready/blocked（新增条目，PROBE_PLAN.md §4.7）
        try:
            readiness = analyze_actions(probe_report=self.probe_report)
            readiness_available = bool(readiness.get("exists"))
        except Exception as exc:      # 分析失败不许拖垮既有两个条目
            readiness = {
                "total": 0, "ready": 0, "blocked": 0, "missing_deps": {},
                "error": "%s: %s" % (type(exc).__name__, exc),
                "index_source": "failed",
                "exists": False,
            }
            readiness_available = False
        self.last_readiness = readiness
        results.append(ProbeItem(
            name="action_readiness",
            category="actions",
            available=readiness_available,
            extra=readiness,
        ))

        return results
