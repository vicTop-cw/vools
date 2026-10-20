"""回归：三处「调用了不存在的函数、被 except 吞成静默失败」的修复。

- evolution._phase_validate 曾 import 不存在的 validate.validate_action_file
  -> Validate 阶段对任何动作都恒报 Schema invalid（2026-10-13 修）。
- webhook._dispatch_action 曾 import 不存在的 executor.execute_action
  -> webhook 从未真正触发过动作（2026-10-13 修）。
- records.list_run_records 无过滤分页应提前截断且不串味（性能修复 + 正确性）。
"""

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_VOOLS_ROOT = os.path.dirname(os.path.dirname(_HERE))          # .../vools
_BRIDGES = os.path.join(_VOOLS_ROOT, "bridges")

# 必须在 import vools.actus 【之前】定位并设置 ACTUS_REPO_ROOT —— validate 在
# import 期就缓存 contracts/action.schema.json 路径。contracts 保留在独立
# Actus 仓库（validate._resolve_schema_path 的 docs/32 迁移约定）。
def _locate_actus_repo():
    env = os.environ.get("ACTUS_REPO_ROOT")
    if env and os.path.isfile(os.path.join(env, "contracts", "action.schema.json")):
        return env
    sibling = os.path.abspath(os.path.join(_VOOLS_ROOT, "..", "Actus"))
    if os.path.isfile(os.path.join(sibling, "contracts", "action.schema.json")):
        return sibling
    return ""

_ACTUS_REPO = _locate_actus_repo()

_HAVE_CONTRACTS = bool(_ACTUS_REPO)
_requires_contracts = pytest.mark.skipif(
    not _HAVE_CONTRACTS,
    reason="需要独立 Actus 仓库的 contracts/action.schema.json",
)

# 注意：【不要】在模块顶层设置 ACTUS_REPO_ROOT 全局环境变量——它会泄漏到同一
# pytest 进程里的其它模块（test_ai_gaps 等），改变其索引/schema 路径行为。
# validate 在 import 期缓存模块级 _SCHEMA_PATH，这里用 fixture 精确 patch，
# 用后即还原，零全局副作用。
@pytest.fixture
def _contracts_schema():
    from vools.actus import validate as vmod
    schema = os.path.join(_ACTUS_REPO, "contracts", "action.schema.json")
    saved = vmod._SCHEMA_PATH
    vmod._SCHEMA_PATH = schema
    vmod._schema_cache = None
    try:
        yield schema
    finally:
        vmod._SCHEMA_PATH = saved
        vmod._schema_cache = None

# 命名空间引导：actuss 本地源码 + 核心 + bridges（parse_cfg 用 vools.bridge.md）
sys.path.insert(0, _HERE)
if os.path.isdir(_BRIDGES):
    sys.path.insert(0, _BRIDGES)
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

import vools  # noqa: E402
_BRIDGE_NS = os.path.join(_BRIDGES, "vools")
if os.path.isdir(_BRIDGE_NS) and _BRIDGE_NS not in list(getattr(vools, "__path__", [])):
    vools.__path__.append(_BRIDGE_NS)


MIN_VALID_ACTION = '''# demo

```json #!cfg
{
  "id": "actus.test.demo",
  "name": "demo",
  "version": "1.0.0",
  "trust": "sandbox",
  "entry": "main",
  "platform": ["desktop"],
  "description": "demo action",
  "args": {"type": "object", "properties": {}}
}
```

```python #!run tag=main
print("ok")
```
'''


# ---------- evolution._phase_validate ----------

@_requires_contracts
def test_evolution_validate_accepts_well_formed_action(tmp_path, _contracts_schema):
    from vools.actus.evolution import EvolutionEngine

    action_file = tmp_path / "demo.actus.md"
    action_file.write_text(MIN_VALID_ACTION, encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()

    eng = EvolutionEngine(repo_root=str(repo))
    res = eng._phase_validate(str(action_file))
    assert res["valid"] is True, res
    # 关键：错误信息绝不能再是“cannot import name 'validate_action_file'”
    assert all("validate_action_file" not in e for e in res.get("errors", []))


@_requires_contracts
def test_evolution_validate_reports_real_parse_error_not_import_error(tmp_path, _contracts_schema):
    from vools.actus.evolution import EvolutionEngine

    bad = tmp_path / "bad.actus.md"
    bad.write_text("# no cfg at all\n", encoding="utf-8")
    eng = EvolutionEngine(repo_root=str(tmp_path / "repo2"))
    # 不存在/非法文件：返回 invalid 且错误来自解析，不是缺失导入
    (tmp_path / "repo2").mkdir(exist_ok=True)
    res = eng._phase_validate(str(bad))
    assert res["valid"] is False
    assert all("validate_action_file" not in str(e) for e in res.get("errors", []))


# ---------- records.list_run_records ----------

def _write_run(meta_dir, idx, action="actus.x.run"):
    runs = os.path.join(meta_dir, "runs")
    os.makedirs(runs, exist_ok=True)
    # 文件名可排序：用零填充 idx 保证倒序确定
    with open(os.path.join(runs, "run_%05d.json" % idx), "w", encoding="utf-8") as f:
        json.dump({"action": action, "seq": idx}, f)


def test_list_run_records_limit_offset_without_filter(tmp_path):
    from vools.actus import records

    for i in range(10):
        _write_run(str(tmp_path), i)
    page = records.list_run_records(meta_dir=str(tmp_path), limit=3, offset=0)
    assert len(page) == 3
    # 倒序：最新的 seq=9 在前
    assert [r["seq"] for r in page] == [9, 8, 7]
    page2 = records.list_run_records(meta_dir=str(tmp_path), limit=3, offset=3)
    assert [r["seq"] for r in page2] == [6, 5, 4]


def test_list_run_records_filter_scans_all(tmp_path):
    from vools.actus import records

    for i in range(10):
        _write_run(str(tmp_path), i, action="actus.keep" if i % 2 == 0 else "actus.skip")
    kept = records.list_run_records(meta_dir=str(tmp_path),
                                    action_id="actus.keep", limit=100)
    assert {r["seq"] for r in kept} == {0, 2, 4, 6, 8}


# ---------- webhook dispatch 真正调用 executor.execute ----------

def test_webhook_dispatch_calls_real_execute(monkeypatch):
    import vools.actus.webhook as wh
    import vools.actus.executor as executor

    captured = {}

    def fake_execute(action_id, params=None, confirmed=False, meta_dir=None):
        captured["action_id"] = action_id
        captured["params"] = params
        captured["confirmed"] = confirmed
        return {"exec_id": "E1", "status": "queued"}

    monkeypatch.setattr(executor, "execute", fake_execute)

    receiver = wh.WebhookReceiver.__new__(wh.WebhookReceiver)  # 不起服务
    out = receiver._dispatch_action("actus.test.foo", "push", {"a": 1})

    assert captured["action_id"] == "actus.test.foo"
    assert captured["params"]["event_type"] == "push"
    assert captured["params"]["triggered_by"] == "webhook"
    # webhook 自动触发不得自动放行 audit 动作
    assert captured["confirmed"] is False
    assert out == {"exec_id": "E1", "status": "queued"}


def test_webhook_dispatch_swallows_failure_as_none(monkeypatch):
    import vools.actus.webhook as wh
    import vools.actus.executor as executor

    def boom(*a, **k):
        raise RuntimeError("executor down")

    monkeypatch.setattr(executor, "execute", boom)
    receiver = wh.WebhookReceiver.__new__(wh.WebhookReceiver)
    # 异步上下文中失败应被吞成 None，不外抛
    assert receiver._dispatch_action("a", "e", {}) is None
