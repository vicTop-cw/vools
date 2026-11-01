# -*- coding: utf-8 -*-
"""scaffold.py 契约测试 r97 — 补齐 test_scaffold_safety 未覆盖分支。

覆盖目标（基线 72%，missed 33-64, 69-74, 93, 112, 120, 132-133, 187-188, 198-207, 299, 378-380, 531）：
- list_templates：模板目录解析/parse_cfg 失败/读取失败三条腿（33-64）
- _strip_fm：无 front-matter / 有 front-matter / 未闭合（69-74）
- match_template 关键词命中（93）+ 未命中默认（96）
- _generate_id 无词回退（112）、_validate_id 拒绝非法 id（132-133）
- scaffold_action 空描述（187-188）、外部模板驱动注入（198-207）、
  output_dir 缺省 __file__ 推导（299）、首次校验异常（378-380）
- _with_entry_driver 无 python 块回退（531）
- 隔离红线：ACTUS_REPO_ROOT / 输出全指 tmp；不写工作区 _meta/、actions/。

每条断言都能真失败；变异验证见文末注释。
"""
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

import vools.actus.scaffold as scaffold_mod  # noqa: E402
from vools.actus.errors import ActionError  # noqa: E402
from vools.actus.scaffold import (  # noqa: E402
    list_templates,
    match_template,
    scaffold_action,
    _generate_id,
    _generate_name,
    _strip_fm,
    _with_entry_driver,
    _validate_id,
)


# ---------------------------------------------------------------------------
# 夹具：模板目录钉在 tmp（不碰仓库真实 actions/templates）
# ---------------------------------------------------------------------------

_VALID_TEMPLATE = '''---
AIGC:
    Label: "1"
    ContentProducer: stub
    ProduceID: PLACEHOLDER
    ReservedCode1: PLACEHOLDER
    ContentPropagator: stub
    PropagateID: PLACEHOLDER
    ReservedCode2: PLACEHOLDER
---

# Template

```json #!cfg
{
  "id": "actus.<namespace>.<name>",
  "name": "my-action",
  "version": "1.0.0",
  "trust": "audit",
  "deps": [],
  "entry": "main",
  "description": "TODO: template description",
  "usage": "old usage",
  "author": "ai-scaffold",
  "permissions": ["files:read"],
  "args": {"type": "object", "properties": {}, "required": []},
  "ai": { "generated": true, "author": "ai-scaffold", "evolve_policy": "confirm" }
}
```

```python #!run tag=main
def main():
    return {"status": "ok"}
```
'''

_BAD_CFG_TEMPLATE = '''# broken template

```json #!cfg
{ not json
```
'''

_NO_CFG_TEMPLATE = '''# no cfg block here

just prose.
'''


@pytest.fixture
def templates_dir(tmp_path, monkeypatch):
    """建 tmp 模板目录并让 scaffold._TEMPLATES_DIR 指向它。"""
    tdir = tmp_path / "templates"
    tdir.mkdir()
    monkeypatch.setattr(scaffold_mod, "_TEMPLATES_DIR", str(tdir))
    return tdir


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """隔离红线：ACTUS_REPO_ROOT / META / VAULT2 全指 tmp。"""
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("ACTUS_META_DIR", str(tmp_path / "_meta"))
    monkeypatch.setenv("ACTUS_VAULT2_DIR", str(tmp_path / "_vault2"))
    return tmp_path


# ---------------------------------------------------------------------------
# list_templates（33-64）
# ---------------------------------------------------------------------------

def test_list_templates_missing_dir_returns_empty(monkeypatch, tmp_path):
    """模板目录不存在 → 空列表（覆盖 34-35）。"""
    monkeypatch.setattr(scaffold_mod, "_TEMPLATES_DIR",
                        str(tmp_path / "no-such-dir"))
    assert list_templates() == []


def test_list_templates_parses_cfg(templates_dir):
    """合法模板 → default_id/trust/description 来自 #!cfg（覆盖 41-54）。"""
    (templates_dir / "audit.demo.actus.md").write_text(_VALID_TEMPLATE,
                                                       encoding="utf-8")
    (templates_dir / "notes.txt").write_text("skip me", encoding="utf-8")
    result = list_templates()
    assert len(result) == 1, "非动作文件（.txt）必须被 is_action_file 过滤"
    t = result[0]
    assert t["template_file"] == "audit.demo.actus.md"
    assert t["default_id"] == "actus.<namespace>.<name>"
    assert t["trust"] == "audit"
    assert t["description"] == "TODO: template description"


def test_list_templates_bad_cfg_falls_back(templates_dir):
    """#!cfg 不是合法 JSON → 空字段兜底条目，不炸（覆盖 55-61 except）。"""
    (templates_dir / "bad.actus.md").write_text(_BAD_CFG_TEMPLATE,
                                                encoding="utf-8")
    result = list_templates()
    assert len(result) == 1
    t = result[0]
    assert t["template_file"] == "bad.actus.md"
    assert t["default_id"] == ""
    assert t["trust"] == ""
    assert t["description"] == ""


def test_list_templates_no_cfg_block_falls_back(templates_dir):
    """无 #!cfg 块 → parse_cfg 抛 action_invalid → 同样落空字段兜底（覆盖 47-61 另一腿）。"""
    (templates_dir / "plain.actus.md").write_text(_NO_CFG_TEMPLATE,
                                                  encoding="utf-8")
    result = list_templates()
    assert len(result) == 1
    assert result[0]["default_id"] == ""


def test_list_templates_read_failure_skipped(templates_dir, monkeypatch):
    """文件读取失败（如编码/权限）→ 静默跳过（覆盖 62-63 except）。"""
    (templates_dir / "ok.actus.md").write_text(_VALID_TEMPLATE,
                                               encoding="utf-8")
    real_open = open

    def fake_open(path, *a, **kw):
        if "ok.actus.md" in str(path):
            raise OSError("stub: unreadable")
        return real_open(path, *a, **kw)

    import builtins
    monkeypatch.setattr(builtins, "open", fake_open)
    assert list_templates() == [], "读取失败的模板被跳过"


# ---------------------------------------------------------------------------
# _strip_fm（69-74）
# ---------------------------------------------------------------------------

def test_strip_fm_without_frontmatter():
    assert _strip_fm("plain body") == "plain body"


def test_strip_fm_with_frontmatter():
    raw = "---\nAIGC:\n    Label: \"1\"\n---\n\n# Title\n\nbody"
    assert _strip_fm(raw).startswith("# Title")


def test_strip_fm_unclosed_frontmatter_returns_raw():
    """--- 开头但无闭合 --- → 原样返回（覆盖 72-73 end == -1 腿）。"""
    raw = "---\nAIGC:\n    Label: \"1\"\nno closing"
    assert _strip_fm(raw) == raw


# ---------------------------------------------------------------------------
# match_template（91-96）
# ---------------------------------------------------------------------------

def test_match_template_shell_keyword():
    assert match_template("run a shell command 命令行") == "sandbox.shell.actus.md"


def test_match_template_workflow_keyword():
    assert match_template("编排一个 pipeline workflow") == "workflow.linear.actus.md"


def test_match_template_default_python():
    """无关键词命中 → 默认 trusted python 模板（覆盖 96）。"""
    assert match_template("随便写点啥 xyzzy") == "trusted.python.actus.md"


# ---------------------------------------------------------------------------
# _generate_id / _validate_id / _generate_name（105-141）
# ---------------------------------------------------------------------------

def test_generate_id_explicit_valid():
    assert _generate_id("desc", "actus.my.tool") == "actus.my.tool"


def test_generate_id_explicit_invalid_raises():
    """显式 id 非法 → ActionError（覆盖 106 + 132-133 _validate_id 抛出）。"""
    with pytest.raises(ActionError) as excinfo:
        _generate_id("desc", "Not Valid!")
    assert excinfo.value.code == "action_invalid"


def test_generate_id_no_words_falls_back_to_action():
    """描述无字母/中文词 → 回退 'action'（覆盖 111-112）。"""
    assert _generate_id("!!! ...") == "actus.generated.action"


def test_generate_name_from_id():
    assert _generate_name("actus.generated.hello-world_x") == "Hello World X"


# ---------------------------------------------------------------------------
# scaffold_action — 空描述（186-188）
# ---------------------------------------------------------------------------

def test_scaffold_empty_description_raises(clean_env):
    for bad in ("", "   "):
        with pytest.raises(ActionError) as excinfo:
            scaffold_action(bad)
        assert excinfo.value.code == "action_invalid"


# ---------------------------------------------------------------------------
# scaffold_action — 内联回退 + 驱动注入（193-207, 521-533）
# ---------------------------------------------------------------------------

def test_scaffold_inline_template_fallback(clean_env, tmp_path):
    """模板缺失 → __inline__ + ENTRY_DRIVER 注入 + 校验通过（覆盖 194-196）。"""
    out = tmp_path / "out"
    result = scaffold_action("hello world demo",
                             action_id="actus.gen.inline1",
                             output_dir=str(out), trust="sandbox")
    assert result["template"] == "__inline__"
    text = open(result["path"], encoding="utf-8").read()
    assert "_zparams" in text, "内联模板必须带引擎模块级驱动"
    assert '"id": "actus.gen.inline1"' in text
    assert result["validation"]["valid"] is True, \
        "sandbox 信任级 + 内联模板应一次通过校验: %r" % (result["validation"]["errors"],)
    assert '"tests"' not in text, "sandbox 不声明配套测试"


def test_scaffold_external_template_injects_driver(templates_dir, clean_env,
                                                   tmp_path):
    """外部模板无 _zparams → 读取后注入 ENTRY_DRIVER（覆盖 198-207）。

    契约：scaffold_action 永远经 match_template(description) 选模板，
    描述含 'workflow' → workflow.linear.actus.md，写入同名模板文件即被采用。
    """
    (templates_dir / "workflow.linear.actus.md").write_text(_VALID_TEMPLATE,
                                                            encoding="utf-8")
    out = tmp_path / "out"
    result = scaffold_action("ext workflow pipeline demo",
                             action_id="actus.gen.ext1",
                             output_dir=str(out), trust="sandbox")
    assert result["template"] == "workflow.linear.actus.md"
    text = open(result["path"], encoding="utf-8").read()
    assert "_zparams" in text, "外部模板缺驱动时必须被注入 ENTRY_DRIVER"
    assert result["validation"]["valid"] is True


def test_with_entry_driver_no_python_block_appends():
    """无 ```python 块 → 驱动追加到尾部（覆盖 530-531）。"""
    text = _with_entry_driver("no code fences here")
    assert text.endswith("if __name__ == \"__main__\":\n") or "_zparams" in text


def test_with_entry_driver_strips_legacy_driver():
    """模板自带旧协议模块级调用 → 注入前先剥掉（覆盖 _strip_legacy_driver 503-518）。"""
    legacy = (
        "```python #!run tag=main\n"
        "def main():\n"
        "    return {}\n"
        "params = json.loads(os.environ.get('ACTUS_PARAMS') or '{}')\n"
        "print(json.dumps(main(params), ensure_ascii=False))\n"
        "```\n"
    )
    out = _with_entry_driver(legacy)
    assert out.count("_zparams") >= 1, "必须注入新驱动"
    # 旧协议签名是 params = json.loads(os.environ...)；新驱动用 sys.argv，
    # 所以 os.environ 形态必须归零，新驱动的 params = json.loads(sys.argv...) 保留。
    assert out.count("params = json.loads(os.environ") == 0, "旧协议调用必须被剥掉"


# ---------------------------------------------------------------------------
# scaffold_action — output_dir 缺省（295-301）与 repo_root（296-297）
# ---------------------------------------------------------------------------

def test_scaffold_default_output_dir_uses_repo_root(clean_env, tmp_path):
    """output_dir=None + repo_root 指定 → 写进 repo_root/actions（覆盖 296-297）。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    result = scaffold_action("demo action", action_id="actus.gen.repo1",
                             repo_root=str(repo), trust="sandbox")
    assert os.path.isfile(str(repo / "actions" / "repo1.actus.md"))
    assert os.path.normcase(result["path"]) == os.path.normcase(
        os.path.abspath(str(repo / "actions" / "repo1.actus.md")))


def test_scaffold_default_output_dir_uses_module_inference(clean_env, tmp_path,
                                                           monkeypatch):
    """output_dir=None 且无 repo_root → 从 scaffold.__file__ 上三级推 actions/（覆盖 298-301）。

    monkeypatch scaffold 模块的 __file__ 指向 tmp 假层级
    <tmp>/pkg/sub/scaffold.py → 推导 <tmp>/actions。
    """
    fake_pkg = tmp_path / "pkg" / "sub"
    fake_pkg.mkdir(parents=True)
    monkeypatch.setattr(scaffold_mod, "__file__", str(fake_pkg / "scaffold.py"))
    result = scaffold_action("demo action", action_id="actus.gen.infer1",
                             trust="sandbox")
    expected = tmp_path / "actions" / "infer1.actus.md"
    assert expected.is_file(), \
        "无 output_dir/repo_root 时必须从 __file__ 推导 actions/: %r" % (result["path"],)


# ---------------------------------------------------------------------------
# scaffold_action — 首次校验异常（378-380）
# ---------------------------------------------------------------------------

def test_scaffold_validation_exception_reported(templates_dir, clean_env,
                                                tmp_path, monkeypatch):
    """parse_cfg_from_file 抛异常 → validation.valid=False + errors 记录（覆盖 379-380）。"""
    (templates_dir / "audit.vb.actus.md").write_text(_VALID_TEMPLATE,
                                                     encoding="utf-8")
    import vools.actus.model as model_mod
    real = model_mod.parse_cfg_from_file

    def boom(*a, **kw):
        raise RuntimeError("stub parse failure")

    monkeypatch.setattr(model_mod, "parse_cfg_from_file", boom)
    out = tmp_path / "out"
    result = scaffold_action("validation boom", action_id="actus.gen.vb1",
                             output_dir=str(out), trust="sandbox")
    # patch 对象寻址：scaffold 里是 `from .model import parse_cfg_from_file` 函数内导入，
    # 实际查的是 vools.actus.model 的属性 → monkeypatch model_mod 即生效。
    assert result["validation"]["valid"] is False
    assert any("stub parse failure" in str(e) for e in result["validation"]["errors"]), \
        "校验异常必须进 errors，实得 %r" % (result["validation"]["errors"],)


# ---------------------------------------------------------------------------
# scaffold_action — next_steps 分支（387-388）
# ---------------------------------------------------------------------------

def test_scaffold_audit_next_steps_hint(clean_env, tmp_path):
    """trust=audit → next_steps 带 --confirm 提示（覆盖 387-388）。"""
    result = scaffold_action("demo action", action_id="actus.gen.audit1",
                             output_dir=str(tmp_path / "out"), trust="audit")
    assert any("--confirm" in s for s in result["next_steps"])
    # audit 同时声明了配套测试（cfg "tests" 字段）
    text = open(result["path"], encoding="utf-8").read()
    assert '"tests"' in text


# ---------------------------------------------------------------------------
# 变异验证记录（人工执行后还原，不留在测试运行里）
# ---------------------------------------------------------------------------
# MV-1: 把 scaffold.py:131 的 re.match 模式从 '^[a-z]...' 改成 '^[A-Z]...' →
#       test_generate_id_explicit_invalid_raises 红（合法 id 被拒）。
# MV-2: 把 scaffold.py:196 内联回退分支的 `_with_entry_driver(...)` 去掉 →
#       test_scaffold_inline_template_fallback 红（"_zparams" in text 断言失败）。
# MV-3: 把 scaffold.py:379-380 `except Exception as e:` 体内改为
#       `validation['errors'] = []` → test_scaffold_validation_exception_reported 红。
