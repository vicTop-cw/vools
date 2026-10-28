# -*- coding: utf-8 -*-
"""actus/tests/test_scaffold_safety.py — `scaffold` 覆盖保护（数据丢失防线）验收测试。

为什么要这份测试（真实事故）
----------------------------
`scaffold.py` 改前对**主要产物**（动作文件）直接 `open(file_path, 'w')`，没有存在性
检查；而同一函数里次要的配套测试骨架反倒有 `if not os.path.exists(...)` 保护 ——
保护了次要的、破坏了主要的。结果：

    actus/actions/zh.actus.md 被 `actus scaffold` 静默覆盖了两次（每次 -156 行，
    内容变成 PLACEHOLDER 模板），每次都要手工 git checkout 恢复。

它能长期存在的原因之一就是**没有测试**：`tests/test_scaffold*.py` 从未存在，
`scaffold_action` 的覆盖行为没有任何回归保护。cmd-engine 修好后（`force: bool = False`
+ `ActionError('action_exists')`），本文件把这条数据丢失防线钉死。

每条用例的 docstring 都写明「假实现/退步会怎样」；核心断言是**磁盘上的字节**，
不是返回值 —— 只要有人把存在性检查去掉，用例 1 立刻红。

隔离
----
全部写入 `tmp_path` 的假仓库（`repo/actions`、`repo/tests`），并通过 `ACTUS_REPO_ROOT`
把 CLI 的写入也钉在 tmp。**绝不拿仓库真实的 `actions/zh.actus.md` 做实验**：真实文件
只被**只读**读取（复制内容做幸存的 tmp 副本）+ 读前读后 sha256 对照（一旦有代码真去
写它，hash 断言会亮，等于给事故文件装了行程开关）。

py3.6 兼容：只用标准库，% 格式化，不用 f-string。
"""

import hashlib
import inspect
import io
import os
import contextlib
import pathlib

import pytest

# 与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树
# 而不是 site-packages 的发布 wheel（否则测的是旧包，结论是假的）。
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus.errors import ActionError  # noqa: E402
from vools.actus.scaffold import scaffold_action  # noqa: E402
import vools.actus.cli as cli  # noqa: E402


# 「用户手写内容」标记串：只要被覆盖，断言就会看到它消失/被模板替换。
_MARKER = (
    "# 用户手写的 zh 动作 —— 这是数据，不是模板\n"
    "MARKER-LINE-42: DO NOT OVERWRITE\n"
    "MARKER-LINE-43: 覆盖即数据丢失\n"
)

_DESC = "把中文文档生成摘要并输出"        # 触发模板匹配，同时刷新 id/name/description

_ZH_ACTION_ID = "actus.generated.zh"      # → 文件名 zh.actus.md（与事故同一个目标）


def _invoke(argv):
    """同进程执行 cli.main(argv)，返回 (rc, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(list(argv))
    except SystemExit as exc:
        rc = exc.code if exc.code is not None else 0
    return rc, out.getvalue(), err.getvalue()


def _sha256(path):
    """文件内容 sha256（接受 str 或 Path）。"""
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """tmp 版假仓库：repo/actions + repo/tests（+ 校验用 contracts），cwd/env 都指过去。

    `contracts/action.schema.json` 从仓库**只读复制**过来：scaffold 的首次校验会按
    `ACTUS_REPO_ROOT/contracts/` 找契约 schema，tmp 仓库缺它会让校验报「schema 文件
    不存在」——那是环境缺失，不是生成物有问题，不该让用例误红。
    """
    repo = tmp_path / "repo"
    actions = repo / "actions"
    tests = repo / "tests"
    actions.mkdir(parents=True)
    tests.mkdir()

    has_contracts = False
    source_schema = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "contracts", "action.schema.json")
    if os.path.isfile(source_schema):
        (repo / "contracts").mkdir()
        (repo / "contracts" / "action.schema.json").write_bytes(
            pathlib.Path(source_schema).read_bytes())
        has_contracts = True

    monkeypatch.chdir(repo)
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))

    class World(object):
        pass

    w = World()
    w.root = tmp_path
    w.repo = repo
    w.actions = actions
    w.tests = tests
    w.action_file = actions / "zh.actus.md"
    w.has_contracts = has_contracts
    return w


# ---------------------------------------------------------------------------
# 1) 撞已有动作文件 → 必须拒绝，且原文一个字都不能变
# ---------------------------------------------------------------------------

def test_existing_action_file_is_refused_not_overwritten(world):
    """假实现/退步会怎样：去掉存在性检查（即事故原形）→ 这里 `pytest.raises` 失败，
    且下面的字节断言会看到标记串被模板替换 —— 两条都会红。

    断言：抛 ActionError 且 code=='action_exists'；消息与 details 点名被占用文件；
    文件内容**逐字节**等于写入前。
    """
    world.action_file.write_text(_MARKER, encoding="utf-8")

    with pytest.raises(ActionError) as excinfo:
        scaffold_action(_DESC, action_id=_ZH_ACTION_ID,
                        repo_root=str(world.repo))

    exc = excinfo.value
    assert exc.code == "action_exists", "错误码必须是 action_exists，实得 %r" % (exc.code,)
    expected = os.path.abspath(str(world.action_file))
    assert expected in (exc.message or ""), \
        "错误消息要点名被占用的文件路径，实得 %r" % (exc.message,)
    assert (exc.details or {}).get("path") == expected, \
        "details.path 应指向被占用的文件，实得 %r" % (exc.details,)

    assert world.action_file.read_text(encoding="utf-8") == _MARKER, \
        "拒绝覆盖却改动了原文 —— 数据丢失防线失效"


def test_refusal_has_no_partial_side_effects(world):
    """假实现/退步会怎样：先写文件后发现冲突再报错，或先把测试骨架写出去。

    断言拒绝时仓库里**没有任何新增/变化**：动作文件原文不变、tests/ 下没有新骨架。
    """
    world.action_file.write_text(_MARKER, encoding="utf-8")
    before_tests = sorted(p.name for p in world.tests.iterdir())

    with pytest.raises(ActionError):
        scaffold_action(_DESC, action_id=_ZH_ACTION_ID,
                        repo_root=str(world.repo))

    assert world.action_file.read_text(encoding="utf-8") == _MARKER
    assert sorted(p.name for p in world.tests.iterdir()) == before_tests, \
        "拒绝覆盖时不该留下任何副作用（配套测试骨架被提前写出）"


def test_force_default_is_false_contract():
    """假实现/退步会怎样：有人把默认值改成 `force=True` —— 所有调用点立刻恢复静默覆盖。

    断言签名默认是 False（CLI 的 `--force` 才是显式逃生口）。
    """
    params = inspect.signature(scaffold_action).parameters
    assert "force" in params, "scaffold_action 丢了 force 参数（覆盖保护没有逃生口/开关）"
    assert params["force"].default is False, \
        "force 默认必须是 False（改前事故就是默认覆盖），实得 %r" % (
            params["force"].default,)


# ---------------------------------------------------------------------------
# 2) 只有显式 force=True 才允许覆盖
# ---------------------------------------------------------------------------

def test_force_true_overwrites_existing_action_file(world):
    """假实现/退步会怎样：force=True 也不覆盖（过度收紧）→ 下面断言文件未变会红。

    断言：不抛异常、原文标记消失、返回 overwritten=True、路径指向目标文件、内容带新 id。
    """
    world.action_file.write_text(_MARKER, encoding="utf-8")

    result = scaffold_action(_DESC, action_id=_ZH_ACTION_ID,
                             repo_root=str(world.repo), force=True)

    text = world.action_file.read_text(encoding="utf-8")
    assert "MARKER-LINE-42" not in text, "force=True 却没有覆盖"
    assert result["overwritten"] is True, \
        "返回值应如实标注 overwritten=True，实得 %r" % (result.get("overwritten"),)
    assert os.path.normcase(result["path"]) == os.path.normcase(
        os.path.abspath(str(world.action_file))), \
        "返回路径不是被覆盖的那个文件: %r" % (result.get("path"),)
    assert _ZH_ACTION_ID in text, "覆盖后的内容里没有新动作 id"


# ---------------------------------------------------------------------------
# 3) 正常新建：不许被覆盖保护误伤
# ---------------------------------------------------------------------------

def test_new_action_is_created_with_template_features(world):
    """假实现/退步会怎样：覆盖保护写得太宽（例如「actions 目录非空就拒绝」）→
    正常新建被误伤，下面断言文件不存在/结构缺失会红。

    断言：文件确实新建、内容有模板特征（#!cfg 块 / 引擎驱动 / 新 id）、
    首次校验通过、返回结构完整、配套测试骨架已生成。
    """
    action_id = "actus.generated.hello"
    result = scaffold_action(_DESC, action_id=action_id, repo_root=str(world.repo))

    target = world.actions / "hello.actus.md"
    assert target.is_file(), "目标不存在时应正常新建，实得 %r" % (result.get("path"),)
    text = target.read_text(encoding="utf-8")
    assert "```json #!cfg" in text, "生成内容缺少 #!cfg 元数据块"
    assert "_zparams" in text, "生成内容缺少引擎模块级驱动（动作每次执行 data 恒为 null）"
    assert action_id in text, "生成内容里没有新动作 id"

    assert result["id"] == action_id
    assert result["trust"] == "audit"
    assert result["overwritten"] is False
    assert result["test_file_skipped"] is False
    assert isinstance(result["validation"], dict)
    if world.has_contracts:
        # 契约 schema 在位时，生成物必须一次通过校验（scaffold 的承诺）
        assert result["validation"].get("valid") is True, \
            "首次校验应通过，实得 errors=%r" % (result["validation"].get("errors"),)
    else:
        assert isinstance(result["validation"].get("valid"), bool)
    assert isinstance(result["next_steps"], list) and result["next_steps"]
    # audit 级动作必须带配套测试骨架（docs/47 §4）
    assert (world.tests / "test_hello.py").is_file(), "audit 动作没有生成配套测试骨架"


# ---------------------------------------------------------------------------
# 4) 配套测试骨架的既有保护：已存在时跳过，且要有信号
# ---------------------------------------------------------------------------

def test_existing_test_skeleton_is_skipped_with_signal(world):
    """假实现/退步会怎样：测试骨架被无条件覆盖（改前 `open(...,'w')` 的同类风险），
    或者实现悄悄跳过却不回传信号（调用方以为生成了）。

    断言：动作文件正常新建；`test_file_skipped is True`；tests/ 下既有骨架内容一字未变。
    这个信号在本实现里**存在**（scaffold_action 返回值 `test_file_skipped`）。
    """
    skeleton = world.tests / "test_zh.py"
    skeleton.write_text("# 用户手写的测试骨架\nHANDWRITTEN-SKELETON\n", encoding="utf-8")

    result = scaffold_action(_DESC, action_id=_ZH_ACTION_ID, repo_root=str(world.repo))

    assert world.action_file.is_file(), "动作文件应正常新建（骨架存在不是冲突）"
    assert result["test_file_skipped"] is True, \
        "已有测试骨架时应回传 test_file_skipped=True，实得 %r" % (
            result.get("test_file_skipped"),)
    assert skeleton.read_text(encoding="utf-8") == \
        "# 用户手写的测试骨架\nHANDWRITTEN-SKELETON\n", "既有测试骨架被覆盖了"


# ---------------------------------------------------------------------------
# 5) CLI 层：撞已有必须失败并点名文件；--force 才覆盖
# ---------------------------------------------------------------------------

def test_cli_collision_fails_with_clear_error(world):
    """假实现/退步会怎样：CLI 吞掉 ActionError 照样打印 status=ok / rc=0（改前形态），
    用户看到「生成成功」却不知道文件被替换。

    断言：rc!=0、stdout JSON status=failed 且 code=action_exists、stderr 点名文件名
    并提示 --force、磁盘原文未变。
    """
    world.action_file.write_text(_MARKER, encoding="utf-8")

    rc, out, err = _invoke(["scaffold", _DESC, "--id", _ZH_ACTION_ID])

    assert rc != 0, "撞已有动作文件时 CLI 必须失败（改前静默覆盖后 rc=0）"
    assert '"failed"' in out and "action_exists" in out, \
        "stdout 没有结构化失败回执: %r" % (out[:600],)
    assert "zh.actus.md" in err, "stderr 没点名被占用的文件: %r" % (err[:600],)
    assert "拒绝覆盖" in err
    assert "--force" in err, "错误提示里应给出逃生口 --force"
    assert world.action_file.read_text(encoding="utf-8") == _MARKER, "CLI 路径覆盖了原文"


def test_cli_force_flag_overwrites(world):
    """假实现/退步会怎样：--force 没有真正透传到 scaffold_action（用户解不开冲突）。

    断言：rc==0、stdout JSON status=ok 且 overwritten=true、磁盘原文已被新内容替换。
    """
    world.action_file.write_text(_MARKER, encoding="utf-8")

    rc, out, err = _invoke(["scaffold", _DESC, "--id", _ZH_ACTION_ID, "--force"])

    assert rc == 0, "显式 --force 应允许覆盖，实得 rc=%r err=%r" % (rc, err[:400])
    assert '"ok"' in out
    assert '"overwritten": true' in out, "回执没有标注 overwritten=true: %r" % (out[:600],)
    assert "MARKER-LINE-42" not in world.action_file.read_text(encoding="utf-8"), \
        "--force 没有真正覆盖"


# ---------------------------------------------------------------------------
# 6) 【重点】事故文件回归钉子：绝不动仓库真实的 actions/zh.actus.md
# ---------------------------------------------------------------------------

def test_real_zh_action_file_is_never_overwritten_by_scaffold(world):
    """假实现/退步会怎样：scaffold 又去覆盖仓库真实动作（zh.actus.md 已被这样坑过两次）。

    做法（绝不拿真实文件做实验）：
      1. **只读**读取仓库真实 `actions/zh.actus.md`，把内容复制成 tmp 仓库里的同名动作；
      2. 对 tmp 副本调 scaffold（同一 action_id / 同一目标名）→ 必须拒绝，副本逐字节不变；
      3. 记录真实文件运行前后的 sha256，断言完全一致（有代码真去写它时这里会亮）。
    """
    real_action = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "actions", "zh.actus.md")
    if not os.path.isfile(real_action):
        pytest.skip("仓库里没有 actions/zh.actus.md（事故文件），无法做回归钉子")

    real_before = _sha256(real_action)
    with open(real_action, "rb") as handle:
        real_content = handle.read()
    assert real_content.strip(), "真实 zh.actus.md 是空的，回归钉子无意义"

    # 1) 内容复制到 tmp（不写真实路径）
    world.action_file.write_bytes(real_content)

    # 2) tmp 副本必须被覆盖保护挡住
    with pytest.raises(ActionError) as excinfo:
        scaffold_action(_DESC, action_id=_ZH_ACTION_ID, repo_root=str(world.repo))
    assert excinfo.value.code == "action_exists"
    assert world.action_file.read_bytes() == real_content, "tmp 副本被覆盖了（事故原形）"

    # 3) 真实文件运行前后完全一致（行程开关）
    real_after = _sha256(real_action)
    assert real_after == real_before, \
        "scaffold 相关代码改动了仓库真实动作文件 actions/zh.actus.md（数据丢失！）"
