# -*- coding: utf-8 -*-
"""actus/tests/test_validate_contracts_r32.py — validate.py（70% 覆盖）契约。

validate 是动作进入执行/索引前的最后一道静态校验。低覆盖意味着大量规则
"写了但没人证明它真的会红"。本文件逐组覆盖合法/非法/边界、多错误汇总，以及
**内部异常不静默**（schema 不可用 → runtime 提示，不误判 invalid）。

隔离：tmp 仓库 + `ACTUS_REPO_ROOT`/`ACTUS_META_DIR`/`HOME` 全指 tmp。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import validate as V  # noqa: E402
from vools.actus.errors import ActionError  # noqa: E402
from vools.actus.model import Action  # noqa: E402


def _action(meta=None, blocks=None, path=None, body=""):
    return Action(meta=dict(meta or {}), path=path or "/tmp/x.actus.md",
                  sha256="", blocks=list(blocks or []), body=body)


def _block(language="python", tag=("main",), code="print(1)"):
    return {"index": 0, "language": language, "tag": list(tag),
            "directives": {"tag": ",".join(tag)}, "code": code}


def _body(code="print(1)", language="python", tag="main"):
    return ("```%s #!run tag=%s\n%s\n```\n" % (language, tag, code))


def _valid_meta():
    return {"id": "demo.valid", "name": "Demo", "version": "1.0.0",
            "trust": "sandbox", "entry": "main", "platform": "desktop",
            "kind": "exec"}


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    actions = repo / "actions"
    meta = tmp_path / "meta"
    home = tmp_path / "home"
    for directory in (actions, meta, home):
        directory.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    return repo


# ===========================================================================
# 分档 / 多值规范化 / 分类
# ===========================================================================

def test_split_validation_and_is_valid():
    """退步了会怎样：`runtime:`/`warning:` 被当成真实错误 —— 裸仓库缺 contracts/
    安全扫描提示会让所有合法动作判 invalid（假红）。

    断言：真实错误留第一档；runtime/warning 进第二档；is_valid 只看真实错误。
    """
    real, notes = V.split_validation(["a", "runtime: x", "warning: w", "b"])
    assert real == ["a", "b"]
    assert notes == ["runtime: x", "warning: w"]
    assert V.is_valid(["runtime: x", "warning: w"]) is True
    assert V.is_valid(["schema: bad"]) is False
    assert V.split_validation([]) == ([], [])


def test_normalize_multi_field_lower_dedup_truncate_and_unknown():
    """退步了会怎样：多值字段大小写/重复未归一（同一分类互不命中）、超长不截断、
    未知值被**丢弃**（前向兼容丢失）。

    断言：小写去重、截到 max_n；未知值进 warnings 且不丢。
    """
    valid, warnings = V.normalize_multi_field(
        ["Dev", "dev", "ops", "weird"], ("dev", "ops"), max_n=5)
    assert valid == ["dev", "ops"]
    assert warnings and "weird" in warnings[0]

    valid, warnings = V.normalize_multi_field(
        ["a", "b", "c", "d"], ("a", "b", "c", "d"), max_n=2)
    assert valid == ["a", "b"]
    assert warnings


def test_check_classification_and_notices():
    """退步了会怎样：未知 kind 被放行（执行逻辑按错误类型分派）；purpose/industry
    的未知值静默丢失。

    断言：已知 kind 无错误；未知 kind → 错误点名合法值；notices 对未知/空 purpose
    给出提示（不静默）。
    """
    assert V.check_classification({"kind": "exec"}) == []
    bad = V.check_classification({"kind": "tool"})
    assert bad and "kind" in bad[0]

    notices = V.classification_notices({"purpose": "zzz"})
    assert notices and any("purpose" in n for n in notices), notices
    assert V.classification_notices({}) == []


def test_action_path_of():
    """退步了会怎样：动作路径解析成错误位置 —— trust/tests/安全扫描读错文件。"""
    assert V.action_path_of({"path": "actions/a.actus.md"}) == "actions/a.actus.md"
    assert V.action_path_of({}) == ""


# ===========================================================================
# 代码块 / entry / 语言
# ===========================================================================

def test_check_entry_block_valid_missing_and_directive_mismatch():
    """退步了会怎样：entry 指向不存在的 tag 仍通过（执行时找不到入口块）；
    文件级 #!entry 与 cfg.entry 漂移不被发现。

    断言：tag 命中无错误；不命中报"未找到"；file_directives 不一致报错。
    """
    assert V.check_entry_block(_action({"entry": "main"}, [_block()])) == []

    missing = V.check_entry_block(_action({"entry": "other"}, [_block()]))
    assert missing and "未找到" in missing[0]

    action = _action({"entry": "main"}, [_block()])
    action.file_directives["entry"] = "other"
    mismatch = V.check_entry_block(action)
    assert mismatch and any("不一致" in e for e in mismatch)


def test_check_block_languages_valid_invalid_and_notices():
    """退步了会怎样：未注册语言放行（执行期无法路由，动作静默失败）。

    断言：python 合法；brainfuck → language 错误；合法块 notices 为空。
    """
    assert V.check_block_languages(_action(blocks=[_block()])) == []
    bad = V.check_block_languages(_action(blocks=[_block(language="brainfuck")]))
    assert bad and bad[0].startswith("language:")
    assert V.language_notices(_action(blocks=[_block()])) == []


# ===========================================================================
# args / triggers / secrets / ai / platform / id / usage
# ===========================================================================

def test_check_args_schema_valid_and_invalid():
    """退步了会怎样：非法 args schema 被接受 —— 执行期参数校验失效（注入面）。

    断言：合法 object schema 无错误；非 object → semantic 错误。
    """
    assert V.check_args_schema({"args": {"type": "object", "properties": {}}}) == []
    bad = V.check_args_schema({"args": "nope"})
    assert bad and "args" in bad[0]


@pytest.mark.parametrize("expr,expected", [
    ("* * * * *", True),
    ("*/5 * * * *", True),
    ("0 0 * * *", True),
    ("bad", False),
    ("60 * * * *", False),
    ("* 25 * * *", False),
])
def test_cron_expr_range_checks(expr, expected):
    """退步了会怎样：越界 cron 字段被接受（触发器永不触发/运行期抛错）。"""
    assert V._cron_expr_range_ok(expr) is expected


def test_check_triggers_valid_invalid_and_bad_cron():
    """退步了会怎样：未知触发器类型/非法 cron 被接受 —— 触发器注册成功但永不工作。

    断言：合法 cron 无错误；未知 type 报错；非法 cron 报错。
    """
    assert V.check_triggers({"triggers": [{"type": "cron", "expr": "* * * * *"}]}) == []
    assert V.check_triggers({"triggers": [{"type": "nope"}]})
    assert V.check_triggers({"triggers": [{"type": "cron", "expr": "bad"}]})


def test_check_secrets_valid_and_invalid():
    """退步了会怎样：secrets 声明格式错误被放行 —— 执行期解析崩溃/凭证静默缺失。"""
    assert V.check_secrets({"secrets": [{"env": "A", "key": "vault://x",
                                         "provider": "vault"}]}) == []
    assert V.check_secrets({"secrets": [{"env": "A", "key": "vault://x"}]})
    assert V.check_secrets({"secrets": "nope"})


def test_check_ai_meta_and_platform_and_id_namespace():
    """退步了会怎样：ai 元数据非对象、未知平台、非法 id 被放行 —— 运行期路由/
    平台/命名空间错误。"""
    assert V.check_ai_meta({"ai": {"provider": "openai", "model": "m"}}) == []
    assert V.check_ai_meta({"ai": "x"})
    assert V.check_platform({"platform": "linux"}) == []
    assert V.check_platform({"platform": "amiga"})
    assert V.check_id_namespace({"id": "a.b"}) == []
    assert V.check_id_namespace({"id": "Bad ID"})


def test_check_usage_executable():
    """退步了会怎样：纯描述 usage 被放行 —— 用户照抄"文档"跑不出一行可执行命令。

    断言：含 `actus run` 的 usage 无错误；纯自然语言描述报"不可执行"。
    """
    assert V.check_usage_executable(
        {"id": "a.b", "usage": "actus run a.b --confirm"}) == []
    described = V.check_usage_executable(
        {"id": "a.b", "usage": "just do it somehow"})
    assert described and "不可执行" in described[0]


# ===========================================================================
# 自包含 / 硬编码 / omega / governance
# ===========================================================================

def test_check_self_contained_flags_same_name_import(world):
    """退步了会怎样：单文件动作 import 动作目录内同名模块（自包含被破坏）——
    分发单文件后 import 失败。

    断言：标准库 import 无错误；同目录同名模块 import → selfcontained 错误。
    """
    action_path = world / "actions" / "demo.actus.md"
    (world / "actions" / "demo.py").write_text("# local", encoding="utf-8")
    good = _action({"entry": "main", "_path": str(action_path)}, [_block()],
                   path=str(action_path), body=_body("import os\nprint(os.getcwd())"))
    assert V.check_self_contained(good) == []

    bad = _action({"entry": "main", "_path": str(action_path)}, [_block()],
                  path=str(action_path), body=_body("import demo\nprint(demo)"))
    assert V.check_self_contained(bad)


def test_check_secrets_hardcode_detects_token(world):
    """退步了会怎样（安全）：动作里硬编码 `sk-...` 凭据被放行 —— 凭据随动作
    分发/进 git，泄露。

    断言：硬编码形态命中 → secrets 错误；普通代码无命中。
    """
    clean = _action({"entry": "main"}, [_block()], body=_body("print('hello')"))
    assert V.check_secrets_hardcode(clean) == []

    hard = _action(
        {"entry": "main"}, [_block()],
        body=_body('api_key = "sk-1234567890abcdef"'))
    assert V.check_secrets_hardcode(hard)


def test_check_omega_gate_requires_declaration_for_bundle():
    """退步了会怎样（Ω 门禁）：bundle 动作未声明 omega 契约仍被放行 —— 强验收
    被静默跳过。

    断言：普通 exec 无错误；bundle 缺契约 → 错误；显式声明 contract 后无错误。
    """
    body = _body("print(demo.run())")
    assert V.check_omega_gate(_action({"kind": "exec", "entry": "main"}, body=body)) == []

    bundle = _action({"kind": "bundle", "entry": "main"}, [_block()], body=body)
    assert V.check_omega_gate(bundle), "bundle 缺 omega-gate 契约却被放行"

    declared = _action({"kind": "bundle", "entry": "main",
                        "contract": "omega-gate"}, [_block()], body=body)
    assert V.check_omega_gate(declared) == []


def test_governance_notices_report_missing_usage():
    """退步了会怎样：治理提示（缺 usage/owner 等）消失 —— 资产元数据长期缺失
    没人发现。"""
    notices = V.governance_notices({"governance": {"owner": "x"}})
    assert notices and any("usage" in n for n in notices), notices


# ===========================================================================
# 依赖图
# ===========================================================================

def test_validate_graph_missing_dep_and_cycle():
    """退步了会怎样（爆炸半径）：缺失依赖不报错（执行期才崩）；循环依赖不检测
    （递归死循环）。

    断言：缺失 → dependency_missing；环 → dependency_cycle；运行时前缀依赖跳过。
    """
    with pytest.raises(ActionError) as excinfo:
        V.validate_graph({"a.b": _action({"id": "a.b", "deps": ["missing.c"]})})
    assert excinfo.value.code == "dependency_missing"
    assert excinfo.value.details.get("missing") == "missing.c"

    one = _action({"id": "one.a", "deps": ["two.b"]})
    two = _action({"id": "two.b", "deps": ["one.a"]})
    with pytest.raises(ActionError) as excinfo:
        V.validate_graph({"one.a": one, "two.b": two})
    assert excinfo.value.code == "dependency_cycle"
    assert excinfo.value.details.get("cycle")

    runtime = _action({"id": "x.y", "deps": ["pip:requests", "system:git"]})
    assert V.validate_graph({"x.y": runtime}) is None


def test_analyze_graph_marks_only_affected_nodes():
    """退步了会怎样（连坐）：一条坏依赖把整个市场标 invalid —— 上百个无关动作下架。

    断言：缺失依赖只标声明它的动作；健康节点不受影响。
    """
    healthy = _action({"id": "ok.a"})
    broken = _action({"id": "bad.b", "deps": ["gone.c"]})
    report = V.analyze_graph({"ok.a": healthy, "bad.b": broken})
    assert "ok.a" not in report or not report["ok.a"].get("code")
    assert report["bad.b"].get("code") == "dependency_missing"


# ===========================================================================
# validate_action 汇总 / schema-md / security / load_and_validate
# ===========================================================================

def test_validate_action_collects_multiple_errors():
    """退步了会怎样：校验只报第一个错误（发布者修一个冒一个）；或必填缺失被忽略。

    断言：空 meta → 同时出现 id/name/version/trust/entry/platform 多个缺失；
    合法动作无真实错误。
    """
    errors = V.validate_action(_action({}))
    text = "\n".join(errors)
    for field in ("id", "name", "version", "trust", "entry", "platform"):
        assert field in text, (field, errors)

    valid = V.validate_action(_action(_valid_meta(), [_block()]))
    real, _notes = V.split_validation(valid)
    assert real == [], real


def test_schema_unavailable_is_runtime_note_not_invalid(monkeypatch):
    """退步了会怎样（内部异常不静默）：契约文件不可用时直接抛异常/把动作判 invalid
    —— 全仓假红；或静默吞掉（没有任何提示）。

    断言：`_load_schema` 抛 `_SchemaUnavailable` → validate_action 返回
    `runtime:` 提示（split 后不是真实错误），且提示文案点名原因。
    """
    def boom():
        raise V._SchemaUnavailable("contracts/action.schema.json 缺失")

    monkeypatch.setattr(V, "_load_schema", boom)
    errors = V.validate_action(_action(_valid_meta(), [_block()]))
    runtime = [e for e in errors if e.startswith("runtime:")]
    assert runtime and "缺失" in runtime[0], errors
    assert V.split_validation(errors)[0] == []


def test_validate_action_check_index_false_skips_index_checks():
    """退步了会怎样：build_index 阶段仍做依赖索引的 md5/link 检查 —— 新索引未写盘
    就被当成"陈旧/篡改"，全仓假红。

    断言：同一动作 check_index=True/False 的真实错误集合一致（索引类只产生
    warning，不进真实错误）。
    """
    action = _action(_valid_meta(), [_block()])
    with_index = V.validate_action(action, check_index=True)
    without = V.validate_action(action, check_index=False)
    real_with = [e for e in with_index if not e.startswith(("warning:", "runtime:"))]
    real_without = [e for e in without if not e.startswith(("warning:", "runtime:"))]
    assert real_with == real_without


def test_validate_schema_md_and_structure_checks():
    """退步了会怎样：schema-md 正文缺 ## Implementation 等结构仍通过 —— CLI validate
    对形式 B 恒绿（C14 永不执行）。

    断言：合法结构无结构问题；缺章节 → warning 点名章节；validate_schema_md
    对合法 schema-md 返回错误列表（不抛）。
    """
    assert V.check_schema_md_structure("## Implementation\n\ncode\n",
                                       {"id": "a.b"}) == []
    missing = V.check_schema_md_structure("## Other\n", {"id": "a.b"})
    assert missing and "Implementation" in missing[0]

    meta = {"id": "demo.md", "name": "D", "version": "1.0.0", "trust": "sandbox",
            "entry": "main", "kind": "exec", "platform": "desktop"}
    action = _action(meta, [_block()], path="/tmp/demo.actus.schema.md",
                     body="## Implementation" + chr(10) + chr(10) + "code" + chr(10))
    assert isinstance(V.validate_schema_md(action), list)


def test_check_security_flags_dangerous_low_trust_code():
    """退步了会怎样（安全）：低信任动作里的危险调用（os.system/rm -rf）被静默放行。

    断言：低信任 + 危险代码 → security: 错误；安全代码无命中。
    """
    dangerous = _action({"id": "d.a", "trust": "sandbox", "entry": "main"},
                        [_block()], body=_body('import os\nos.system("rm -rf /")'))
    issues = V.check_security(dangerous)
    assert issues and all(i.startswith("security:") for i in issues), issues

    safe = _action({"id": "s.a", "trust": "sandbox", "entry": "main"},
                   [_block()], body=_body("print('ok')"))
    assert V.check_security(safe) == []


def test_load_and_validate_valid_and_invalid(world):
    """退步了会怎样：load_and_validate 把 runtime/warning 当失败（合法动作被拦）
    或把真实错误当通过（坏动作进入执行）。

    断言：合法动作文件返回 Action；缺必填的文件抛 ActionError(action_invalid)
    且 details.errors 非空。
    """
    good = world / "good.actus.md"
    good.write_text(
        '# G\n\n```json #!cfg\n{"id": "demo.good", "name": "G", "version": "1.0.0",'
        ' "trust": "sandbox", "entry": "main", "platform": "desktop", "kind": "exec"}'
        '\n```\n\n```python #!run tag=main\nprint(1)\n```\n', encoding="utf-8")
    action = V.load_and_validate(str(good))
    assert action.meta.get("id") == "demo.good"

    bad = world / "bad.actus.md"
    bad.write_text('# B\n\n```json #!cfg\n{"id": "bad id"}\n```\n', encoding="utf-8")
    with pytest.raises(ActionError) as excinfo:
        V.load_and_validate(str(bad))
    assert excinfo.value.code == "action_invalid"
    assert excinfo.value.details.get("errors")


# ===========================================================================
# trust↔测试绑定 / schema-md 分支 / 校验器异常
# ===========================================================================

def test_resolve_test_binding_declared_auto_and_absent(world):
    """退步了会怎样（trust 承诺失真）：audit/trusted 动作没有可复跑的测试绑定却放行；
    或已声明的测试文件存在仍判"未绑定"。

    断言：meta.tests 显式声明且文件存在 → (True, refs)；tests/ 下引用 id 的文件
    自动命中；完全没有测试目录 → (False, [])；缺 id → (False, [])。
    """
    action_path = world / "actions" / "bound.actus.md"
    action_path.write_text("# x", encoding="utf-8")
    declared = world / "tests" / "test_bound.py"
    declared.parent.mkdir(parents=True, exist_ok=True)
    declared.write_text("# declared test" + chr(10), encoding="utf-8")

    action = _action({"id": "demo.bound", "_path": str(action_path),
                      "tests": ["tests/test_bound.py"]}, path=str(action_path))
    bound, refs = V.resolve_test_binding(action)
    assert bound is True and refs == ["tests/test_bound.py"], (bound, refs)

    declared.unlink()
    auto = world / "tests" / "test_auto.py"
    auto.write_text("def test_x():" + chr(10) + "    assert 'demo.bound' == 'demo.bound'" + chr(10),
                    encoding="utf-8")
    bound, refs = V.resolve_test_binding(
        _action({"id": "demo.bound", "_path": str(action_path)}, path=str(action_path)))
    assert bound is True and refs, (bound, refs)

    assert V.resolve_test_binding(_action({})) == (False, [])


def test_check_trust_tests_requires_binding_for_audit_and_trusted(world):
    """退步了会怎样（docs/47 §4）：audit 级动作没测试也放行（"审计"承诺落空）；
    trusted 级没有回归记录也放行（信任不可复跑）。

    断言：audit 无绑定 → trust 错误；有绑定 → []；trusted 无绑定 → 错误；
    sandbox / 非 exec kind 豁免。
    """
    action_path = world / "actions" / "t.actus.md"
    action_path.write_text("# x", encoding="utf-8")

    no_bind = _action({"id": "demo.t", "trust": "audit", "_path": str(action_path)},
                      path=str(action_path))
    error = V.check_trust_tests(no_bind)
    assert error and "无测试绑定" in error[0]

    trusted = _action({"id": "demo.t", "trust": "trusted", "_path": str(action_path)},
                      path=str(action_path))
    assert V.check_trust_tests(trusted)

    (world / "tests").mkdir(parents=True, exist_ok=True)
    (world / "tests" / "test_t.py").write_text("demo.t" + chr(10), encoding="utf-8")
    bound = _action({"id": "demo.t", "trust": "audit", "_path": str(action_path),
                     "tests": ["tests/test_t.py"]}, path=str(action_path))
    assert V.check_trust_tests(bound) == []

    sandbox = _action({"id": "demo.t", "trust": "sandbox", "_path": str(action_path)},
                      path=str(action_path))
    assert V.check_trust_tests(sandbox) == []
    demo_kind = _action({"id": "demo.t", "trust": "audit", "kind": "demo",
                         "_path": str(action_path)}, path=str(action_path))
    assert V.check_trust_tests(demo_kind) == []


def test_validate_schema_md_covers_required_field_branches():
    """退步了会怎样：形式 B 的必填/类型校验分支从不执行 —— 缺 id/kind/平台、非法
    trust/permissions/依赖类型的 schema-md 全部放行。

    断言：空 meta → 多字段缺失 + 无代码块错误；trust/kind 非法、dependencies 类型
    错、permissions 非列表/未知权限、tag 重复 → 各自出现在错误里。
    """
    empty = V.validate_schema_md(_action({}))
    text = chr(10).join(empty)
    for field in ("id", "name", "version", "trust", "entry", "kind", "platform"):
        assert field in text, (field, empty)
    assert "代码块" in text

    bad_meta = {"id": "demo.md", "name": "D", "version": "1.0.0",
                "trust": "bogus", "entry": "main", "kind": "bogus",
                "platform": "desktop", "dependencies": "not-a-map",
                "permissions": ["root"]}
    bad_blocks = [_block(), {"index": 1, "language": "python", "tag": ["main"],
                             "directives": {}, "code": "print(2)"}]
    errors = V.validate_schema_md(_action(bad_meta, bad_blocks,
                                          path="/tmp/demo.actus.schema.md",
                                          body="## Implementation" + chr(10)))
    joined = chr(10).join(errors)
    assert "trust" in joined and "kind" in joined
    assert "dependencies" in joined and "权限" in joined
    assert "tag 重复" in joined, errors

    deps_meta = dict(bad_meta)
    deps_meta["dependencies"] = {"pip": "requests", "system": "git", "env": "HOME"}
    deps_meta["permissions"] = "not-a-list"
    more = chr(10).join(
        V.validate_schema_md(_action(deps_meta, [_block()],
                                     path="/tmp/demo.actus.schema.md")))
    assert "必须" in more


def test_check_security_scanner_exception_becomes_warning(monkeypatch):
    """退步了会怎样（内部异常不静默）：安全扫描器自身故障时让所有动作判 invalid
    （全仓假红），或静默吞掉（没有任何提示）。

    断言：scanner 抛异常 → 返回 warning: 安全扫描异常（不是 security: 错误）。
    """
    from vools.actus import security as security_mod
    monkeypatch.setattr(security_mod, "get_security_scanner",
                        lambda: (_ for _ in ()).throw(RuntimeError("scanner down")))
    issues = V.check_security(_action({"id": "a.b", "trust": "sandbox"}))
    assert issues and issues[0].startswith("warning:")
    assert "异常" in issues[0]


def test_check_args_schema_metaschema_failures_are_explicit():
    """退步了会怎样：非法 JSON Schema（properties 非对象/required 非数组/未知 type）
    被静默接受 —— 执行期参数校验器直接崩或永远不校验。

    断言：三种非法 schema 均返回 semantic 错误且文案含 "不是合法 JSON Schema"。
    """
    cases = [
        {"type": "object", "properties": "nope"},
        {"type": "object", "required": "a"},
        {"type": "object", "properties": {"a": {"type": "bogus"}}},
    ]
    for schema in cases:
        errors = V.check_args_schema({"args": schema})
        assert errors and "不是合法 JSON Schema" in errors[0], (schema, errors)


def test_check_self_contained_classifies_stdlib_vools_and_unknown(world):
    """退步了会怎样：把标准库/vools 误判为非自包含（合法动作全红），或把未知包
    误判为自包含（分发后 import 失败）。

    断言：stdlib/vools 豁免；未知第三方包 → selfcontained 错误；无 entry → 跳过。
    """
    action_path = world / "actions" / "sc.actus.md"
    base = {"entry": "main", "_path": str(action_path)}

    assert V.check_self_contained(
        _action(base, [_block()], path=str(action_path), body=_body("import os"))) == []
    assert V.check_self_contained(
        _action(base, [_block()], path=str(action_path), body=_body("import vools"))) == []

    unknown = V.check_self_contained(
        _action(base, [_block()], path=str(action_path),
                body=_body("import definitely_not_a_module_xyz")))
    assert unknown and "selfcontained" in unknown[0]

    assert V.check_self_contained(
        _action({"_path": str(action_path)}, [_block()], path=str(action_path))) == []


def test_check_secrets_hardcode_sensitive_env_declaration(world):
    """退步了会怎样（安全/可用性）：读取敏感 env 但未在 meta.secrets 声明 → 运行期
    拿不到注入值静默失败；已声明却被误报。

    断言：未声明 → secrets 错误点名 env；已声明 → 无错误。
    """
    code = "import os" + chr(10) + "x = os.environ['MY_TOKEN']"
    undeclared = _action({"entry": "main"}, [_block()], body=_body(code))
    errors = V.check_secrets_hardcode(undeclared)
    assert errors and "MY_TOKEN" in errors[0], errors

    declared = _action({"entry": "main",
                        "secrets": [{"env": "MY_TOKEN", "key": "vault://x",
                                     "provider": "vault"}]},
                       [_block()], body=_body(code))
    assert V.check_secrets_hardcode(declared) == []


def test_check_schema_md_structure_conditional_sections():
    """退步了会怎样：声明了 args 却没有 ## Input Schema 章节仍通过 —— 文档与契约
    脱节；或没有依赖也强制要求 Dependencies（误伤无依赖动作）。

    断言：args 已声明但缺 Input Schema → structure 错误；无依赖缺 Dependencies →
    不报；两段齐全 → 无结构错误。
    """
    args_missing = V.check_schema_md_structure(
        "## Implementation" + chr(10), {"args": {"type": "object"}})
    assert args_missing and "Input Schema" in args_missing[0]

    no_deps = V.check_schema_md_structure(
        "## Implementation" + chr(10), {})
    assert not any("Dependencies" in e for e in no_deps), no_deps

    both = V.check_schema_md_structure(
        "## Implementation" + chr(10) + "## Input Schema" + chr(10)
        + "## Dependencies" + chr(10),
        {"args": {}, "dependencies": {}})
    assert both == [], both


def test_check_security_high_trust_is_warning_not_error():
    """退步了会怎样（分级错误）：audit/trusted 动作命中危险模式也判 security 错误
    （现有动作无故全红）；或完全不提示（假安全）。

    断言：audit 信任级 + 危险代码 → 全部 warning:（无 security:），且非空。
    """
    action = _action({"id": "a.b", "trust": "audit", "entry": "main"},
                     [_block()], body=_body('import os' + chr(10) + 'os.system("rm -rf /")'))
    issues = V.check_security(action)
    assert issues and all(i.startswith("warning:") for i in issues), issues
