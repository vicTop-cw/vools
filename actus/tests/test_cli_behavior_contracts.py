# -*- coding: utf-8 -*-
"""actus/tests/test_cli_behavior_contracts.py — CLI 命令的**行为契约**测试。

为什么要这份测试（上一份冒烟的盲区）
------------------------------------
`tests/test_cli_all_subcommands.py` 只保证「不崩 / 不静默」：exit ∈ {0,1,2} 且输出
无崩溃特征。它抓不到**假成功** —— 因为假实现往往 rc=0 且输出正常。

上一轮修好的一批「假功能」正是这种形态，若无本文件，它们全部复活也不会有测试变红：

| 命令 | 修前「假」的形态 |
|---|---|
| `export` | 无历史 + `--output` 时打印「✅ 已导出到 X」+ exit 0，**文件根本不存在** |
| `viz` | 找不到工作流定义时把**硬编码示例**（trigger/action1/action2/end）当结果输出 + exit 0 |
| `replay` | 非 dry-run 分支固定打印「(重放执行待实现)」，**从不执行** |
| `publish --sign` | 只打印「签名动作（待实现）...」，紧接着照样「✅ 索引已生成」+ exit 0 |
| `reg`/`team`/`private`/`visibility` | dispatch 无分支 → rc=2 + **0 字节** 静默失联 |
| `history.json` 损坏 | 与「没历史」一样返回 `[]` → 打印「📭 暂无」+ exit 0 |

本文件的每条用例都按「**假实现复活 → 这里必须红**」来写：断言的是**可观察行为**
（rc + 文件是否真的存在 + 内容 + 是否真的执行 + 是否真的报错），而不是只断言「不崩」。
每条用例的 docstring 都写明了它防的具体假形态。

隔离（零仓库污染）
------------------
每个用例：`monkeypatch.chdir(tmp_path/repo)`，并把 `ACTUS_REPO_ROOT` / `ACTUS_META_DIR` /
`ACTUS_CONFIG_DIR` / `HOME` / `USERPROFILE` 全部指向 tmp。动作文件、执行记录、历史文件
都在 tmp 里造；`replay` 真执行产生的 `runs/<exec_id>.json` 也落在 tmp。

做不到 / 故意不做的条目（如实说明，不写永远绿的假测试）
------------------------------------------------------
* `publish --sign` 的**成功路径**需要真实私钥（本机没有、也不该在测试里生成），
  所以只测「密钥不存在 → 必须失败且不得声称成功」这条负路径；成功路径由
  `sign` / `trust_model` 自己的测试覆盖。
* `viz` 的 `dot/html` 渲染细节、`export` 的 csv/markdown 排版不在本文件范围
  （它们不是「假功能」的载体），只断言 json 导出内容真的可解析。

py3.6 兼容：只用标准库，% 格式化，不用 f-string。
"""

import io
import json
import os
import sys
import contextlib

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

import vools.actus.cli as cli  # noqa: E402


# 一个**结构合法且能真执行**的内联动作（id/name/version/trust 是必填四件套）。
# run 块按引擎契约从 ACTUS_PARAMS 读参数、向 stdout 打印 JSON 回执。
_VALID_ACTION_META = {
    "id": "test.hello",
    "name": "Hello",
    "version": "1.0.0",
    "trust": "sandbox",
    "entry": "main",
    "description": "behavior-contract fixture",
    "author": "test",
    "platform": ["desktop"],
    "permissions": ["files:read"],
    "args": {"type": "object", "properties": {}},
}

_ACTION_BODY = (
    "```python #!run tag=main\n"
    "import json, os\n"
    'params = json.loads(os.environ.get("ACTUS_PARAMS") or "{}")\n'
    'print(json.dumps({"status": "ok", "result": params}))\n'
    "```\n"
)


def _action_text(action_id=None):
    """动作文件正文：JSON `#!cfg` + 可执行 run 块。"""
    meta = dict(_VALID_ACTION_META)
    if action_id:
        meta["id"] = action_id
    return (
        "---\n"
        "AIGC:\n"
        '    Label: "1"\n'
        "---\n"
        "\n"
        "# %s\n"
        "\n"
        "```json #!cfg\n"
        "%s\n"
        "```\n"
        "\n"
        "%s"
    ) % (meta["name"], json.dumps(meta, ensure_ascii=False), _ACTION_BODY)


def _invoke(argv):
    """同进程执行 cli.main(argv)，返回 (rc, stdout, stderr)。

    argparse 的 --help / 用法错误抛 SystemExit（不是 Exception），统一折算成退出码。
    """
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(list(argv))
    except SystemExit as exc:
        rc = exc.code if exc.code is not None else 0
    return rc, out.getvalue(), err.getvalue()


def _write_action(actions_dir, action_id="test.hello"):
    path = actions_dir / (action_id.rsplit(".", 1)[-1] + ".actus.md")
    path.write_text(_action_text(action_id), encoding="utf-8")
    return path


def _write_history(meta_dir, records):
    """写 `_meta/runs/history.json`（replay/export 的首选数据源）。"""
    runs_dir = meta_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / "history.json"
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return path


def _corrupt_history(meta_dir):
    runs_dir = meta_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / "history.json"
    path.write_text("{ this is definitely not json", encoding="utf-8")
    return path


def _run_record_files(meta_dir):
    runs_dir = meta_dir / "runs"
    if not runs_dir.is_dir():
        return set()
    return set(name for name in os.listdir(str(runs_dir))
               if name.endswith(".json") and name != "history.json")


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    """tmp 版「世界」：repo/actions、repo/_meta、独立 config 与 home，全部隔离。"""
    repo = tmp_path / "repo"
    actions = repo / "actions"
    meta = repo / "_meta"
    home = tmp_path / "home"
    config = tmp_path / "config"
    for directory in (actions, meta, home, config):
        directory.mkdir(parents=True)

    monkeypatch.chdir(repo)
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_CONFIG_DIR", str(config))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    class World(object):
        pass

    w = World()
    w.root = tmp_path
    w.repo = repo
    w.actions = actions
    w.meta = meta
    w.home = home
    w.config = config
    return w


# ---------------------------------------------------------------------------
# 1) export：不许「报成功但没写文件」
# ---------------------------------------------------------------------------

def test_export_empty_history_must_not_fake_success(world):
    """假实现复活会怎样：无历史 + --output 时打印「✅ 已导出到 X」并 exit 0，而文件不存在。

    断言 rc==1、输出文件**不存在**、stdout 不含「✅ 已导出」，stderr 明确说没生成。
    """
    out_file = world.root / "export-empty.json"
    rc, out, err = _invoke(["export", "--output", str(out_file)])

    assert rc == 1, "没有历史时 export --output 必须失败（改前假成功是 rc=0）"
    assert not out_file.exists(), "rc 非 0 却写出了文件 —— 返回值与副作用自相矛盾"
    assert "✅ 已导出" not in out, "假成功文案复活了"
    assert ("未生成文件" in err) or ("没有可导出的" in err), \
        "stderr 必须说明为什么没生成文件，实得 %r" % (err[:300],)


def test_export_with_history_writes_real_parseable_file(world):
    """假实现复活会怎样：即便有历史也只打印成功、不落盘（或落盘内容不是记录）。

    断言 rc==0、文件真实存在且非空、`json.loads` 得到记录列表且内容与历史一致。
    """
    _write_history(world.meta, [{
        "run_id": "run-A1",
        "action_id": "test.hello",
        "status": "ok",
        "timestamp": "2026-01-01T00:00:00",
        "params": {"x": 1},
    }])
    out_file = world.root / "export-history.json"
    rc, out, err = _invoke(["export", "--output", str(out_file)])

    assert rc == 0, "有历史时 export 应成功，实得 rc=%r err=%r" % (rc, err[:300])
    assert out_file.exists(), "export 报成功但文件不存在（改前的假成功形态）"
    text = out_file.read_text(encoding="utf-8")
    assert text.strip(), "导出文件是空的"

    data = json.loads(text)
    assert isinstance(data, list) and len(data) == 1, \
        "json 导出应是记录列表，实得 %r" % (type(data),)
    assert data[0]["action_id"] == "test.hello", "导出的内容不是那条历史记录"
    assert "✅ 已导出" in out


# ---------------------------------------------------------------------------
# 2) viz：不许把硬编码示例当真实工作流
# ---------------------------------------------------------------------------

def test_viz_without_workflow_must_fail_not_emit_sample(world):
    """假实现复活会怎样：没有 .actus.workflow.json 时输出示例节点（action1/action2）并 exit 0，
    加 --output 还会把示例落盘成「本项目工作流」。

    断言 rc==1、stdout **不含** action1/action2、stderr 说未找到；--output 不落盘。
    """
    rc, out, err = _invoke(["viz"])
    assert rc == 1, "找不到工作流定义时必须失败（改前假数据是 rc=0）"
    assert "action1" not in out and "action2" not in out, \
        "硬编码示例节点又出现在正常输出里了: %r" % (out[:300],)
    assert "未找到工作流定义" in err

    out_file = world.root / "viz-should-not-exist.txt"
    rc2, out2, err2 = _invoke(["viz", "--output", str(out_file)])
    assert rc2 == 1
    assert not out_file.exists(), "失败路径仍把示例写盘了（改前形态）"


def test_viz_sample_only_with_explicit_flag_and_marked_as_sample(world):
    """假实现复活会怎样：示例不标注来源，用户/AI 把它当项目工作流。

    断言 `--sample` 时 rc==0、stderr 明确写「示例」、示例节点确实渲染（证明走的是显式示例分支）。
    """
    rc, out, err = _invoke(["viz", "--sample"])
    assert rc == 0
    assert "示例" in err, "显式 --sample 时 stderr 必须标注这是示例，实得 %r" % (err[:300],)
    assert out.strip()
    assert "action1" in out, "示例分支没有渲染出示例节点"


# ---------------------------------------------------------------------------
# 3) replay：必须真的执行，不是打印「待实现」
# ---------------------------------------------------------------------------

def test_replay_really_executes_and_stamps_exec_id(world):
    """假实现复活会怎样：非 dry-run 只打印「(重放执行待实现)」，rc=0，什么都没执行。

    断言 rc==0、输出含「重放成功」与执行器盖章的「exec:」、且 `_meta/runs/` 下**新增**
    执行记录文件；同时输出不含「待实现」。
    """
    _write_action(world.actions, "test.hello")
    _write_history(world.meta, [{
        "run_id": "run-OK1",
        "action_id": "test.hello",
        "status": "ok",
        "timestamp": "2026-01-02T00:00:00",
        "params": {"x": 1},
    }])
    before = _run_record_files(world.meta)

    rc, out, err = _invoke(["replay", "--limit", "1"])
    after = _run_record_files(world.meta)
    new_records = sorted(after - before)

    assert "待实现" not in out
    assert rc == 0, "重放应成功（动作与参数都有效），实得 rc=%r\n%s" % (rc, out[-800:])
    assert "重放成功" in out, "没有报告执行成功: %r" % (out[-800:],)
    assert "exec:" in out, "输出里没有执行器盖章的 exec_id —— 可能只是假装执行"
    assert new_records, "_meta/runs 下没有新增执行记录 —— replay 没有真正执行"


def test_replay_dry_run_does_not_execute(world):
    """假实现/过度执行：dry-run 仍然真的跑了动作。

    断言 rc==0、输出说明跳过、且 `_meta/runs/` **没有**新增执行记录。
    """
    _write_action(world.actions, "test.hello")
    _write_history(world.meta, [{
        "run_id": "run-OK1", "action_id": "test.hello", "status": "ok",
        "timestamp": "2026-01-02T00:00:00", "params": {},
    }])
    before = _run_record_files(world.meta)

    rc, out, err = _invoke(["replay", "--dry-run", "--limit", "1"])

    assert rc == 0
    assert "dry-run" in out, "dry-run 必须明示跳过: %r" % (out[-500:],)
    assert _run_record_files(world.meta) == before, "dry-run 却产生了执行记录"


def test_replay_run_id_matches_run_id_key(world):
    """假实现复活会怎样：`r.get('run_id') == r.get('id') == args.run_id` 链式比较 bug
    （run_id 与 id 二选一出现，两者永不相等 ⇒ 任何 --run-id 都匹配不上）。

    断言命中的 run-id 能选中记录、不存在的 run-id 明确报未找到（rc=1）。
    """
    _write_action(world.actions, "test.hello")
    _write_history(world.meta, [{
        "run_id": "run-OK1", "action_id": "test.hello", "status": "ok",
        "timestamp": "2026-01-02T00:00:00", "params": {},
    }])

    rc, out, err = _invoke(["replay", "--run-id", "run-OK1", "--dry-run"])
    assert rc == 0, "存在的 run_id 应能选中记录（链式比较 bug 会匹配不上）: %r" % (out + err,)
    assert "重放 1 条" in out

    rc2, out2, err2 = _invoke(["replay", "--run-id", "no-such-run", "--dry-run"])
    assert rc2 == 1
    assert "未找到执行记录" in out2


# ---------------------------------------------------------------------------
# 4) publish --sign：签名失败不许被「✅」掩盖
# ---------------------------------------------------------------------------

def test_publish_sign_with_missing_key_never_claims_success(world):
    """假实现复活会怎样：--sign 只打印「签名动作（待实现）...」，随后照样输出 ✅ 并 exit 0。

    用不存在的 key 走真实失败路径（不生成密钥、不发布），断言：rc≠0、
    全输出里「✅」出现 0 次、「未实现」0 次、stderr 给出真实失败原因。
    """
    _write_action(world.actions, "test.hello")

    rc, out, err = _invoke(["publish", "--sign", "--key", "nosuchkey"])
    text = out + err

    assert rc != 0, "签名失败必须非 0（改前假成功是 0）"
    assert text.count("✅") == 0, "签名失败却输出了 ✅: %r" % (text[:500],)
    assert "未实现" not in text, "「待实现」文案复活了"
    assert "签名失败" in err, "stderr 没有说明签名失败: %r" % (err[:500],)
    assert "Private key not found" in err, \
        "失败原因不是真实的「密钥不存在」（防止用别的不相关失败假装兜底）: %r" % (err[:500],)


# ---------------------------------------------------------------------------
# 5) 原静默失联的 4 条命令：裸跑必须给用法，真子命令必须能跑
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", ["reg", "team", "private", "visibility"])
def test_formerly_silent_commands_bare_prints_usage(world, command):
    """假实现复活会怎样：dispatch 里没有分支 → 静默 `return 2`、**0 字节输出**。

    断言 rc==1（不是静默失联的 2）、输出非空、且是用法提示。
    """
    rc, out, err = _invoke([command])
    text = out + err

    assert rc == 1, "%s 裸跑应给用法并 rc=1（静默失联时是 rc=2）" % command
    assert text.strip(), "%s 输出为空 —— 静默失联回归" % command
    assert "用法" in text and command in text, \
        "%s 输出不是用法提示: %r" % (command, text[:200])


@pytest.mark.parametrize("argv,needle", [
    (["reg", "list"], "注册表"),
    (["team", "list"], "团队"),
    (["private", "list"], "私有动作"),
    (["visibility", "get", "test.hello"], "test.hello"),
])
def test_formerly_silent_commands_real_subcommands(world, argv, needle):
    """假实现复活会怎样：子命令虽然「不崩」但从不真正读写状态（或仍静默 rc=2）。

    断言 rc==0 且输出里有该子命令的真实语义内容（注册表/团队/私有动作/可见性）。
    """
    _write_action(world.actions, "test.hello")      # visibility get 需要真实动作
    rc, out, err = _invoke(argv)
    text = out + err

    assert rc == 0, "%s rc=%r（应 0）：%r" % (" ".join(argv), rc, text[:300])
    assert needle in text, "%s 输出里看不到 %r: %r" % (" ".join(argv), needle, text[:300])


# ---------------------------------------------------------------------------
# 6) history.json 损坏：必须报错，不许当「没历史」
# ---------------------------------------------------------------------------

def test_corrupt_history_is_reported_by_export_and_replay(world):
    """假实现复活会怎样：损坏的 JSON 被静默当成 `[]` → 打印「📭 暂无执行历史」+ exit 0，
    用户永远不知道自己的历史文件坏了，replay/export 永远空转。

    断言 export 与 replay 都 rc==1、stderr 都提到「损坏」、且都没有输出「暂无」。
    """
    _corrupt_history(world.meta)
    out_file = world.root / "corrupt-export.json"

    rc_e, out_e, err_e = _invoke(["export", "--output", str(out_file)])
    assert rc_e == 1, "历史损坏时 export 必须失败（改前当空历史 rc=0）"
    assert "损坏" in err_e, "export 没报告历史损坏: %r" % (err_e[:300],)
    assert "暂无" not in out_e
    assert not out_file.exists()

    rc_r, out_r, err_r = _invoke(["replay"])
    assert rc_r == 1, "历史损坏时 replay 必须失败（改前当空历史 rc=0）"
    assert "损坏" in err_r, "replay 没报告历史损坏: %r" % (err_r[:300],)
    assert "暂无" not in out_r
