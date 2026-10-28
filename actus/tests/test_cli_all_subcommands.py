# -*- coding: utf-8 -*-
"""actus/tests/test_cli_all_subcommands.py — 全部 CLI 子命令端到端冒烟。

为什么要这份测试（本轮最重要的缺口）
------------------------------------
`cli.py` 用 `add_parser(...)` 声明了大量子命令，但 `tests/` 里真正被执行过的只有
`run` / `validate`（外加 `--help` / `--version`）—— **绝大多数子命令零端到端覆盖**。
后果是审计司令抓到的两个 P0 存在了很久而 `pytest tests` 一直全绿：

    [P0-1] cli.py 缺 `import os` → publish / search / registry info / registry validate /
           workflow / webhook / omega 共 6+ 命令一进入 handler 就 NameError（exit 1）
    [P0-2] cli.py 引用不存在的 API `from vools.actus.records import load_records`
           （真实导出名是 list_run_records）→ omega verify / learn 恒崩

关键点：`main()` 会把 handler 里的异常吞成 ``{"status": "failed", "error": {...}}``
并返回 1，所以**只断言 exit code 根本抓不到这两个 P0**（它们和正常业务失败一样都是 1）。
必须同时检查输出里的崩溃特征串。

本文件做什么
------------
1. **动态枚举**（不手写清单）：从 `cli._build_parser()` 递归遍历 argparse 的
   `_SubParsersAction`，得到全部「命令路径」（含嵌套，如 ``registry info`` /
   ``omega verify``）。手写列表会随时间漂移 —— 那正是这个缺口产生的原因；
   枚举失效时 `test_enumeration_self_check` 会亮。（当前实测 95 条路径。）
2. 每个路径跑 ``<path> --help``：断言 exit 0 且输出含 usage（parse 级、零副作用）。
3. 安全路径跑最小必需参数（占位值 ``zzz-smoke-nonexistent``）：断言
   exit ∈ {0,1,2}、输出**不含**崩溃特征串、且不是「静默无输出」。
4. 危险路径只跑 --help（`SKIP_EXECUTE` 逐条写了理由）；`publish --dry-run` 与
   `webhook --status` 是危险命令的安全形态，单独执行，用来覆盖这两条 handler。
5. **反向自检**：**合成注入** NameError / ImportError（让 dispatch 直接抛），断言崩溃
   探测器确实报红（证明这套断言不是空转）。不再用 `del cli.os` 之类「删真实模块属性」
   的办法 —— 那会把测试绑死到某个 handler 恰好用了哪个符号（实现细节，非契约）。

隔离（绝不污染仓库）
--------------------
每个用例 ``monkeypatch.chdir(tmp_path)``，并把 ``ACTUS_REPO_ROOT`` / ``ACTUS_META_DIR`` /
``HOME`` / ``USERPROFILE`` 全部指向 tmp —— 命令的读写都被圈在 tmp 里。原型阶段实测：
跑完全表后仓库 ``_meta/`` 与 ``actions/`` 零变更。

静默失联护栏（曾经救过一次，现在是「零容忍」）
----------------------------------------------
``reg`` / ``team`` / ``private`` / ``visibility`` 四族曾在 parser 里声明、``_dispatch``
里却没有分支 → 静默 ``return 2``、零输出。本文件没有把它们塞进 SKIP_EXECUTE（那是掩盖），
而是执行并断言「静默失联的顶层命令 ⊆ KNOWN_UNWIRED」。cmd-engine 已把这四条真正接线，
因此 ``KNOWN_UNWIRED`` 现在**清空为空集** —— 该断言等价于「不允许任何命令静默失联」，
将来任一条（含这四条）退回静默都会立刻变红（名单保留但为空，见常量处注释）。

py3.6 兼容：只用标准库，% 格式化，不用 f-string。
"""

import argparse
import contextlib
import io
import json
import os
import sys

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

import vools.actus.cli as cli  # noqa: E402


# ---------------------------------------------------------------------------
# 枚举：从真实 parser 递归拿「命令路径 + 必需参数」
# ---------------------------------------------------------------------------

# 占位值：不存在的动作 id / 文件 / 目录名。让 handler 尽快失败，避免真副作用。
_DUMMY = "zzz-smoke-nonexistent"

# 崩溃特征串。前 6 条是 P0-1/P0-2 在输出里的真实形态（main() 把异常吞成 JSON 错误）；
# "Traceback" 兜住漏出 main() 的极端情况。
_CRASH_MARKERS = (
    "Traceback",
    "is not defined",
    "NameError",
    "ImportError",
    "cannot import name",
    "ModuleNotFoundError",
)

# parser 里声明了、但 _dispatch 没接线的命令（静默 rc=2、零输出）——**当前为空集**。
#
# 历史：`reg` / `team` / `private` / `visibility` 四族（14 条路径）曾长期静默失联，
# 当时这份名单是 {reg, team, private, visibility}。某轮 cmd-engine 把它们真正接线
# （cli.py 里已有 `args.command == 'reg'` 等分支）后，名单必须清空 —— 否则
# 「静默集合 ⊆ 名单」在名单过期后恒真，将来这几条命令再退回静默也不会红，
# 护栏就退化成「免罪名单」。
# 现在它是空集，下面「静默失联集合 ⊆ KNOWN_UNWIRED」的断言等价于
# **不允许任何命令静默失联**；将来若再有命令（包括这四条）漏接线，测试立刻失败。
KNOWN_UNWIRED = frozenset()

# 危险路径：只跑 --help。键是命令路径前缀（tuple），值是「为什么不执行」的理由。
# 前缀匹配：("omega", "batch") 只挡该子命令；("mcp",) 挡整条命令。
SKIP_EXECUTE = {
    ("mcp",): "启动 MCP server（stdio/sse 前台阻塞，等客户端）",
    ("desktop",): "启动 Desktop Web UI server（前台阻塞）",
    ("dialog",): "弹系统对话框（GUI，可能阻塞 / 需要桌面）",
    ("install",): "从 Git 拉取仓库并写安装目录",
    ("uninstall",): "删除已安装目录",
    ("rollback",): "修改安装目录（git 回滚）",
    ("sync",): "网络拉取并覆盖安装目录",
    ("check-update",): "访问网络检查远程更新",
    ("scan",): "重写 _meta/actions.index.json（仓库内文件）",
    ("scaffold",): "生成动作骨架文件（可能覆盖既有动作）",
    ("author",): "修改已有动作文件",
    ("project",): "导入/导出项目文件（会覆盖仓库文件）",
    ("project-mgmt",): "生成/修改项目文件",
    ("evolve",): "写进化候选与动作文件",
    ("selfheal",): "修改动作文件做自愈",
    ("viz",): "写可视化输出文件",
    ("keygen",): "写签名密钥对（落盘到用户密钥目录）",
    ("sign",): "在目标文件旁写 .sig 签名",
    ("notify",): "发送系统通知（外部副作用）",
    ("execute",): "执行任意代码片段",
    ("probe",): "写 _meta/probe_cache.json（仓库内文件；已由 test_probe*.py 覆盖）",
    ("config",): "生成并写 MCP 接入配置文件",
    ("template",): "生成动作模板文件",
    ("publish",): "发布流程（写 .actus.registry.json）——安全形态 publish --dry-run 单独跑",
    ("webhook",): "默认启动 webhook server——安全形态 webhook --status 单独跑",
    # 有副作用的嵌套子命令（同命令的只读子命令照常执行）
    ("omega", "batch"): "批量执行 omega，会写输出文件",
    ("omega", "format"): "格式化并写报告文件",
    ("omega", "learn"): "写学习/进化结果",
    ("omega", "template"): "生成模板文件",
    ("artifacts", "cleanup"): "删除产物文件",
    ("concurrency", "set"): "写并发上限配置",
    ("concurrency", "reset"): "重置并发配置",
    ("triggers", "add"): "写触发器配置",
    ("triggers", "remove"): "删除触发器配置",
    ("vault", "set"): "写密钥库",
    ("vault", "delete"): "删除密钥库条目",
    ("loop", "stop"): "向会话项目目录写 .loop_prompt.stop 信号文件",
    ("private", "add"): "写可见性配置",
    ("private", "remove"): "写可见性配置",
    ("visibility", "set"): "写动作可见性",
    ("reg", "add"): "写多注册表配置",
    ("reg", "remove"): "写多注册表配置",
    ("team", "create"): "写团队配置",
    ("team", "add-member"): "写团队成员配置",
    ("team", "remove-member"): "写团队成员配置",
    ("registry", "build"): "写 .actus.registry.json 索引文件",
}

# 危险命令的「安全形态」：dry-run / 只读状态查询。单独参数化执行，覆盖 handler。
SAFE_FORMS = (
    (("publish",), ("--dry-run",),
     "publish 的干跑形态：只读构建索引并打印，不发布、不写文件"),
    (("webhook",), ("--status",),
     "webhook 的只读形态：查询接收器状态，不起 server"),
)


def _subparser_action(parser):
    """取 parser 的子命令 action（argparse 的 _SubParsersAction）。"""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _required_argv(subparser):
    """子命令的「最小必需参数」：位置参数 + required=True 的选项，值用占位符。"""
    argv = []
    for action in subparser._actions:
        if isinstance(action, argparse._SubParsersAction):
            continue
        if action.dest == "help":
            continue
        if not action.option_strings:
            # 位置参数：nargs None / '+' / 正整数 → 必需；'?' / '*' / 0 → 可缺省
            if action.nargs in (None, "+") or (
                    isinstance(action.nargs, int) and action.nargs > 0):
                argv.append(_DUMMY)
        elif getattr(action, "required", False):
            argv.append(action.option_strings[0])
            if action.nargs != 0:        # store_true / count 之类不吃值
                argv.append(_DUMMY)
    return tuple(argv)


def _collect_command_paths(parser):
    """递归枚举全部命令路径：[(path_tuple, required_argv_tuple), ...]。"""
    collected = []

    def walk(node, prefix):
        sub_action = _subparser_action(node)
        if sub_action is None:
            return
        for name in sorted(sub_action.choices):
            child = sub_action.choices[name]
            path = prefix + (name,)
            collected.append((path, _required_argv(child)))
            walk(child, path)

    walk(parser, ())
    return collected


_COMMANDS = _collect_command_paths(cli._build_parser())


def _is_skipped(path):
    """路径是否命中 SKIP_EXECUTE（前缀匹配）。"""
    for key in SKIP_EXECUTE:
        if tuple(path[:len(key)]) == key:
            return True
    return False


_HELP_CASES = [path for path, _required in _COMMANDS]
_EXEC_CASES = [(path, required) for path, required in _COMMANDS
               if not _is_skipped(path)]

_HELP_IDS = [" ".join(path) for path in _HELP_CASES]
_EXEC_IDS = [" ".join(path) for path, _required in _EXEC_CASES]


# ---------------------------------------------------------------------------
# 调用与断言工具
# ---------------------------------------------------------------------------

def _invoke(argv):
    """在同进程里跑 cli.main(argv)，返回 (rc, stdout, stderr)。

    argparse 的 --help / 用法错误会抛 SystemExit（不是 Exception，main() 的
    ``except Exception`` 兜不住），这里统一折算成退出码。
    """
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(list(argv))
    except SystemExit as exc:
        rc = exc.code if exc.code is not None else 0
    return rc, out.getvalue(), err.getvalue()


def _crash_markers(text):
    """返回 text 里命中的崩溃特征串（空列表 = 没有崩溃特征）。"""
    return [marker for marker in _CRASH_MARKERS if marker in text]


def _is_silent_fall_through(rc, text):
    """静默失联的签名：rc==2 且 stdout/stderr 全空（argparse 用法错误会有 usage 文本）。"""
    return rc == 2 and not text.strip()


@pytest.fixture(autouse=True)
def _isolated_cli_world(tmp_path, monkeypatch):
    """把 cwd 与所有相关目录/家目录都圈进 tmp，命令的读写绝不落到仓库里。"""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("ACTUS_META_DIR", str(tmp_path / "_meta"))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return tmp_path


# ---------------------------------------------------------------------------
# 1) 枚举自检：宁可这里红，也不要「枚举成 0 个也全绿」
# ---------------------------------------------------------------------------

def test_enumeration_self_check():
    """枚举必须覆盖全部命令（当前 95 条路径 / 56 个顶层命令），且含嵌套命令。"""
    assert len(_COMMANDS) >= 60, (
        "只枚举到 %d 条命令路径 —— 枚举逻辑失效或 parser 结构变了（这正是本测试"
        "要防的假绿灯）" % len(_COMMANDS))
    top_level = {path[0] for path, _required in _COMMANDS}
    assert len(top_level) >= 50, "顶层命令只有 %d 个，疑似枚举失效" % len(top_level)
    assert any(len(path) > 1 for path, _required in _COMMANDS), \
        "没有枚举到任何嵌套子命令（registry info / omega verify 这类会漏掉）"

    # 审计点名「零覆盖」的命令必须在范围内
    for name in ("publish", "search", "registry", "workflow", "webhook", "omega"):
        assert name in top_level, "枚举结果漏了 %r" % name

    for path, required in _COMMANDS:
        assert path and all(part for part in path), "出现空命令路径: %r" % (path,)
        assert isinstance(required, tuple)


def test_skip_list_is_documented_and_fresh():
    """SKIP_EXECUTE 的每一条都要有理由、且命令仍在 parser 里（防止名单过期）。"""
    top_level = {path[0] for path, _required in _COMMANDS}
    for key, reason in SKIP_EXECUTE.items():
        assert key[0] in top_level, "SKIP_EXECUTE 里的 %r 已不在 parser 中（名单过期）" % (key,)
        assert reason and reason.strip(), "%r 缺少跳过理由" % (key,)

    # 明确要求「只跑 --help」的危险命令必须在名单里（安全形态除外，另有独立用例）
    for name in ("install", "uninstall", "scaffold", "author", "project",
                 "mcp", "desktop", "execute", "publish", "webhook"):
        assert any(key[0] == name for key in SKIP_EXECUTE), \
            "危险命令 %r 没进 SKIP_EXECUTE —— 它会被真实执行" % name


# ---------------------------------------------------------------------------
# 2) 所有命令：--help 必须 exit 0 且输出 usage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", _HELP_CASES, ids=_HELP_IDS)
def test_help_exits_zero(path):
    """每个命令（含嵌套）的 --help 都要 exit 0、打印 usage、且无崩溃特征。"""
    rc, out, err = _invoke(list(path) + ["--help"])
    text = out + err
    assert rc == 0, "%s --help 退出码 %r（应为 0）" % (" ".join(path), rc)
    assert "usage" in text.lower(), "%s --help 没打印 usage: %r" % (
        " ".join(path), text[:200])
    assert not _crash_markers(text), "%s --help 出现崩溃特征: %r" % (
        " ".join(path), _crash_markers(text))


# ---------------------------------------------------------------------------
# 3) 安全命令：最小参数真实执行，不许崩（P0 回归护栏）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,required", _EXEC_CASES, ids=_EXEC_IDS)
def test_minimal_invocation_does_not_crash(path, required):
    """安全子命令跑最小参数：业务失败/用法错误都算过，崩溃不算。

    判定标准（三条）：
      1. exit ∈ {0,1,2}；
      2. 输出**不含**崩溃特征串（Traceback / is not defined / ImportError /
         cannot import name …）—— 这是两个 P0 在输出里的真实形态，
         只看 exit code 抓不到（main() 把异常吞成 exit 1 的 JSON 错误）；
      3. 不许静默无输出（rc=2 + 空输出 = parser 声明了但 dispatch 没接线的签名），
         唯一豁免是 KNOWN_UNWIRED —— 而它现在是**空集**，等于零豁免。
    """
    label = " ".join(path)
    rc, out, err = _invoke(list(path) + list(required))
    text = out + err

    markers = _crash_markers(text)
    assert not markers, (
        "%s 最小参数执行后出现崩溃特征 %r（rc=%r）：\n%s"
        % (label, markers, rc, text[:1500]))
    assert rc in (0, 1, 2), "%s 退出码异常: %r" % (label, rc)

    if _is_silent_fall_through(rc, text):
        assert path[0] in KNOWN_UNWIRED, (
            "%s 静默无输出且 rc=2（parser 声明了但 _dispatch 没接线）；"
            "KNOWN_UNWIRED 当前为空集（零容忍），任何命令都不许静默失联"
            % label)


def test_no_new_silently_unwired_commands():
    """不允许任何命令静默失联（KNOWN_UNWIRED 已清空，这条断言不再有豁免）。

    cmd-engine 把历史上静默的 4 条命令真正接线后，名单清空；此后
    「静默失联集合 ⊆ KNOWN_UNWIRED(空集)」等价于「静默失联集合必须为空」。
    同时断言名单保持为空 —— 防止有人把过期名字加回去，让护栏再次退化成免罪名单。
    """
    # 名单必须为空：重新加回历史豁免项 = 把护栏变回免罪名单（断言会恒真）。
    assert KNOWN_UNWIRED == frozenset(), (
        "KNOWN_UNWIRED 必须保持空集（历史那 4 条命令已接线）；"
        "重新加回豁免项会让这条护栏恒真: %r" % (sorted(KNOWN_UNWIRED),))

    silent = set()
    for path, required in _EXEC_CASES:
        rc, out, err = _invoke(list(path) + list(required))
        if _is_silent_fall_through(rc, out + err):
            silent.add(path[0])

    unexpected = silent - set(KNOWN_UNWIRED)
    assert not unexpected, (
        "这些命令 parser 里有、实际却静默失联（rc=2 零输出）—— 不允许任何命令"
        "静默失联（KNOWN_UNWIRED 为空集）: %r" % (sorted(unexpected),))


# ---------------------------------------------------------------------------
# 4) 危险命令的安全形态：dry-run / 只读状态
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,extra,reason", SAFE_FORMS,
                         ids=[" ".join(path + extra) for path, extra, _ in SAFE_FORMS])
def test_safe_forms_of_dangerous_commands(path, extra, reason):
    """danger 命令的 dry-run / 只读形态要能真实跑通且不崩（覆盖 handler 本身）。"""
    rc, out, err = _invoke(list(path) + list(extra))
    text = out + err
    assert not _crash_markers(text), (
        "%s 出现崩溃特征 %r（rc=%r）：\n%s"
        % (" ".join(path + extra), _crash_markers(text), rc, text[:1500]))
    assert rc in (0, 1, 2), "%s 退出码异常: %r" % (" ".join(path + extra), rc)
    assert text.strip(), "%s 应有可读输出（%s）" % (" ".join(path + extra), reason)


# ---------------------------------------------------------------------------
# 5) 反向自检：证明这套断言能抓到 P0 类回归，而不是空转
# ---------------------------------------------------------------------------

def test_crash_marker_detector_is_sensitive():
    """特征串探测本身要有效：P0 的真实文案必须命中，正常文案不许误报。"""
    for sample in (
            "Traceback (most recent call last):",
            "name 'os' is not defined",
            "NameError: name 'os' is not defined",
            "ImportError: cannot import name 'x'",
            "cannot import name 'load_records' from 'vools.actus.records'",
            "ModuleNotFoundError: No module named 'foo'",
    ):
        assert _crash_markers(sample), "没识别出崩溃文案: %r" % (sample,)
    assert _crash_markers("✅ 注册表索引已构建") == []
    assert _crash_markers("📭 暂无执行历史") == []


def test_detector_catches_nameerror_regression(monkeypatch):
    """反向自检：main() 的异常兜底 + 崩溃探测器都不是空转（合成 NameError）。

    审计修（测试耦合实现）：旧做法是 `del cli.os` 再跑 `publish --dry-run`，
    强依赖「publish handler 恰好用了模块级 os」—— 另一司令把 `os.getcwd()` 换成
    `repo_root()` 后这条就红（而修复本身是对的）。这是**实现细节**不是契约，
    下次任何重构都会再撞。

    现在改为**合成注入**：直接让 dispatch 抛一个必然的 NameError（等价于任意
    handler 里少 import 某个符号），完全不依赖哪个真实 handler 用了什么符号。
    断言：main() 兜底成 rc=1 + `{"status":"failed"}` JSON，且输出里的
    "is not defined"/"NameError" 必须被 `_crash_markers` 抓到。
    """
    def broken_dispatch(args):
        raise NameError("name 'undefined_name_xyz' is not defined")

    monkeypatch.setattr(cli, "_dispatch", broken_dispatch)

    rc, out, err = _invoke(["publish", "--dry-run"])
    markers = _crash_markers(out + err)
    assert rc == 1, "合成 NameError 应被 main() 兜成 rc=1，实得 %r" % (rc,)
    assert "is not defined" in markers, (
        "崩溃探测器没抓到 NameError（rc=%r，输出前 300 字: %r）"
        % (rc, (out + err)[:300]))
    payload = json.loads(out)
    assert payload["status"] == "failed"
    assert payload["error"]["message"] == "name 'undefined_name_xyz' is not defined"


def test_detector_catches_missing_api_regression(monkeypatch):
    """反向自检：合成 ImportError（等价于 cli.py 引用了不存在的导出名）。

    审计修（同族耦合）：旧做法是 `del records.list_run_records` 再跑
    `records list`，依赖「该命令恰好 import 这个符号」。现在直接让 dispatch 抛
    ImportError，不再依赖任何真实 handler/真实导出名的实现细节。

    断言：rc=1 + failed JSON，输出里的 "cannot import name" 必须被探测器抓到。
    """
    def broken_dispatch(args):
        raise ImportError(
            "cannot import name 'load_records' from 'vools.actus.records'")

    monkeypatch.setattr(cli, "_dispatch", broken_dispatch)

    rc, out, err = _invoke(["records", "list"])
    markers = _crash_markers(out + err)
    assert rc == 1, "合成 ImportError 应被 main() 兜成 rc=1，实得 %r" % (rc,)
    assert "cannot import name" in markers, (
        "崩溃探测器没抓到 ImportError（rc=%r，输出前 300 字: %r）"
        % (rc, (out + err)[:300]))
    payload = json.loads(out)
    assert payload["status"] == "failed"
    assert "cannot import name" in payload["error"]["message"]


def test_audit_p0_commands_are_covered():
    """审计点名「零执行」的命令必须都落在覆盖范围内（回归护栏本身不许退化）。

    覆盖方式两类：安全命令走最小参数真实执行；危险命令走 SAFE_FORMS 的
    dry-run / 只读形态，或至少保证 --help 被枚举到。
    """
    covered = {path[0] for path, _required in _EXEC_CASES}
    covered |= {path[0] for path, _extra, _reason in SAFE_FORMS}
    for name in ("publish", "search", "registry", "workflow", "webhook", "omega"):
        assert name in covered, (
            "%r 变成了「只跑 --help」—— 审计 P0 的回归覆盖消失了" % name)
