# -*- coding: utf-8 -*-
"""actus/tests/test_desktop_exec_contracts.py — desktop Web UI / exec_iface 新契约回归。

覆盖第 14 轮修复的"整个功能不可用 / 契约谎言"（此前只有手工验收）：
  * desktop 运行动作端点：曾对任何动作都 500（传了 executor 没有的 repo_root 参数）；
    修复后成功 200、动作失败 5xx、动作不存在 404、params 非对象 400。
  * desktop 首页：曾因 Starlette 新签名 `TemplateResponse` 恒 500，Web UI 从未跑通；
    修复后 200 且页面里真的有动作 id（不是空壳页）。
  * 模板随包分发：`templates/index.html` 必须存在且被 git 跟踪（13 轮前它是空目录）。
  * `import vools.actus.desktop` 零写：只读 FS 下 `Path.mkdir` 抛 OSError 也不能崩。
  * exec_iface `timeout_ms` 真生效（曾是从未读取的死字段）、非 dict 结果 → error/invalid、
    dry_run 三路统一 skipped、error_kind 分类（业务 401 不再误判 auth）。

隔离：`tmp_path` + `ACTUS_REPO_ROOT`/`HOME`/`ACTUS_META_DIR` 全指 tmp。
"""

import importlib
import json
import os
import subprocess
import sys
import time

import pytest

_ACTUS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import exec_iface as exec_iface_mod  # noqa: E402
from vools.actus import executor as executor_mod  # noqa: E402
from vools.actus import scattered as scattered_mod  # noqa: E402
from vools.actus.model import Action  # noqa: E402

_OK_ACTION = """# Demo

```json #!cfg
{"id": "myapp.demo", "name": "Demo", "version": "1.0.0",
 "trust": "sandbox", "entry": "main", "platform": "desktop"}
```

```python #!run tag=main
print("hello-from-desktop")
```
"""

_FAIL_ACTION = """# Bad

```json #!cfg
{"id": "myapp.fail", "name": "Fail", "version": "1.0.0",
 "trust": "sandbox", "entry": "main", "platform": "desktop"}
```

```python #!run tag=main
raise SystemExit(3)
```
"""


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    repo = tmp_path / "repo"
    actions = repo / "actions"
    for directory in (home, meta, actions):
        directory.mkdir(parents=True)
    (actions / "demo.actus.md").write_text(_OK_ACTION, encoding="utf-8")
    (actions / "fail.actus.md").write_text(_FAIL_ACTION, encoding="utf-8")

    monkeypatch.chdir(repo)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))

    w = _World()
    w.root = tmp_path
    w.repo = repo
    w.meta = meta
    return w


@pytest.fixture
def client(world):
    """TestClient；fastapi/httpx 缺席时才跳过（只影响 desktop 用例，不牵连 exec 用例）。"""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from vools.actus import desktop
    return TestClient(desktop.app)


def _fake_action(aid="a.b", **meta_overrides):
    meta = {"id": aid, "name": "n", "version": "1.0.0", "trust": "sandbox",
            "entry": "main", "platform": "desktop", "path": ""}
    meta.update(meta_overrides)
    return Action(meta=meta, path="", sha256="", blocks=[])


# ===========================================================================
# desktop —— 1) 运行动作端点
# ===========================================================================

def test_run_action_ok_returns_200_and_inner_ok(world, client):
    """退步了会怎样：端点把 executor 不认识的参数传下去（曾传 repo_root）→ 任何
    动作都 500；或没执行成功也回 200/ok（假成功）。

    断言：真实执行成功 → HTTP 200、外层 status='ok'、内层 data.status='ok'、
    输出包含动作打印的文本。
    """
    response = client.post("/api/actions/myapp.demo/run", json={"params": {}})
    body = response.json()

    assert response.status_code == 200, body
    assert body["status"] == "ok"
    assert body["data"]["status"] == "ok"
    assert "hello-from-desktop" in json.dumps(body["data"], ensure_ascii=False)


def test_run_action_failure_returns_5xx_and_outer_failed(world, client):
    """退步了会怎样（假成功）：外层 status 恒 ok、HTTP 200 —— 动作 block 失败
    （非零退出）用户却在 UI 上看到"成功"。

    断言：动作失败 → HTTP 5xx、**外层 status='failed'**（透传内层）、内层错误码非空。
    """
    response = client.post("/api/actions/myapp.fail/run", json={"params": {}})
    body = response.json()

    assert response.status_code >= 500, body
    assert body["status"] == "failed", body
    inner = body["data"]
    assert inner["status"] == "failed"
    assert (inner.get("error") or {}).get("code"), inner


def test_run_unknown_action_returns_404(world, client):
    """退步了会怎样：动作不存在也 500（客户端错误/服务端错误不分），调用方无法据此
    提示"id 写错了"。

    断言：HTTP 404、外层 failed、错误码 action_not_found。
    """
    response = client.post("/api/actions/no.such.action/run", json={"params": {}})
    body = response.json()

    assert response.status_code == 404, body
    assert body["status"] == "failed"
    assert (body["data"].get("error") or {}).get("code") == "action_not_found"


def test_run_non_object_params_returns_400(world, client):
    """退步了会怎样：params 是数组/字符串时直接 `.get` 崩 500，或静默忽略类型错误。

    断言：HTTP 400、外层 error 明说 params 必须是 JSON 对象。
    """
    response = client.post("/api/actions/myapp.demo/run", json={"params": [1, 2]})
    body = response.json()

    assert response.status_code == 400, body
    assert body["status"] == "error"
    assert "params" in body["error"] and "对象" in body["error"]


# ===========================================================================
# desktop —— 2) 首页渲染
# ===========================================================================

def test_index_page_renders_action_ids(world, client):
    """退步了会怎样：`TemplateResponse` 签名用错 → 首页恒 500（Web UI 全不可用）；
    或页面是空壳，看不到任何动作。

    断言：GET / → 200，HTML 里能 grep 到仓库里两个动作的 id（证明确实渲染了列表）。
    """
    response = client.get("/")

    assert response.status_code == 200, response.text[:500]
    text = response.text
    assert "myapp.demo" in text, "首页没有渲染动作 id（空壳页）"
    assert "myapp.fail" in text


# ===========================================================================
# desktop —— 3) 模板随包分发且被 git 跟踪
# ===========================================================================

def test_template_file_ships_and_is_tracked():
    """退步了会怎样：`templates/index.html` 又丢失/未入库 —— 打包安装后首页 500
    （13 轮前它就是空目录且没被 git 跟踪，测试全绿但功能是坏的）。

    断言：文件真实存在；`git ls-files` 能看到它（已纳入版本控制）。
    """
    template = os.path.join(_ACTUS_ROOT, "vools", "actus", "templates", "index.html")
    assert os.path.isfile(template), "模板文件不存在: %s" % template
    assert os.path.getsize(template) > 0

    if not __import__("shutil").which("git"):
        pytest.skip("本机没有 git，无法验证模板是否入库")
    proc = subprocess.run(
        ["git", "-C", _ACTUS_ROOT, "ls-files", "vools/actus/templates/index.html"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert proc.stdout.strip(), "模板未被 git 跟踪（打包会丢）: %r" % (proc.stdout,)


# ===========================================================================
# desktop —— 4) import 零写（只读 FS 不崩）
# ===========================================================================

def test_desktop_import_does_not_write_on_readonly_fs(world, monkeypatch):
    """退步了会怎样：import 期裸 `Path.mkdir` —— 只读安装（site-packages 只读）下
    `import vools.actus.desktop` 直接 PermissionError（模块导入不应有写副作用）。

    断言：monkeypatch `Path.mkdir` 抛 OSError 后，重新 import 桌面模块**不抛异常**。
    """
    import pathlib

    def read_only_mkdir(self, *args, **kwargs):
        raise OSError("read-only filesystem (simulated)")

    monkeypatch.setattr(pathlib.Path, "mkdir", read_only_mkdir)
    sys.modules.pop("vools.actus.desktop", None)

    module = importlib.import_module("vools.actus.desktop")

    assert module is not None
    assert hasattr(module, "app")


# ===========================================================================
# exec_iface —— 5) timeout_ms 真生效
# ===========================================================================

def test_timeout_ms_is_enforced_and_marked_deferred(world, monkeypatch):
    """退步了会怎样（契约谎言）：`ExecutionContext.timeout_ms` 又变成从未读取的死字段
    —— 配 300ms 的慢动作照样跑满（实测 3.5s），且调用方拿不到"结果未知"的标注。

    断言：timeout_ms=300 + 慢动作（sleep 1.0s）→ 墙钟 <1s 返回；status='error'、
    error_kind='timeout'、**timeout_deferred=True**（worker 可能仍在跑）、ok=False。
    """
    def slow_execute(*args, **kwargs):
        time.sleep(1.0)
        return {"status": "ok", "data": {}, "error": None, "artifacts": []}

    monkeypatch.setattr(executor_mod, "execute", slow_execute)
    ctx = exec_iface_mod.ExecutionContext(timeout_ms=300)

    started = time.time()
    result = exec_iface_mod.executor_for("executor").execute(_fake_action(), ctx)
    elapsed = time.time() - started

    assert elapsed < 1.0, "timeout_ms 没有生效（墙钟 %.2fs）" % elapsed
    assert result.status == "error"
    assert result.error_kind == "timeout"
    assert result.timeout_deferred is True, "必须如实标注 worker 可能仍在跑"
    assert result.ok is False


# ===========================================================================
# exec_iface —— 6) 非 dict 结果不能记 ok
# ===========================================================================

def test_non_dict_executor_result_is_error_invalid(world, monkeypatch):
    """退步了会怎样：executor 返回 None/str 等非结构化结果时被当成成功（无法确认
    是否真的执行了，却回 ok）。

    断言：返回 None → status='error'、error_kind='invalid'、error 非空、ok=False。
    """
    monkeypatch.setattr(executor_mod, "execute", lambda *a, **k: None)

    result = exec_iface_mod.executor_for("executor").execute(
        _fake_action(), exec_iface_mod.ExecutionContext())

    assert result.status == "error"
    assert result.error_kind == "invalid"
    assert result.error, "非结构化结果必须有可读错误"
    assert result.ok is False


# ===========================================================================
# exec_iface —— 7) dry_run 三路统一 skipped
# ===========================================================================

def test_dry_run_executor_path_is_skipped(world, monkeypatch):
    """退步了会怎样（V-04）：executor 通道 dry_run=True 照样真跑 —— "预览"执行了
    真实动作、产生副作用。

    断言：dry_run → status='skipped'、ok=False、error 为空，且**没有调用 execute**。
    """
    calls = []
    monkeypatch.setattr(executor_mod, "preview",
                        lambda *a, **k: {"status": "ok", "blocks": []})
    monkeypatch.setattr(executor_mod, "execute",
                        lambda *a, **k: calls.append(a) or {"status": "ok"})

    result = exec_iface_mod.executor_for("executor").execute(
        _fake_action(), exec_iface_mod.ExecutionContext(dry_run=True))

    assert result.status == "skipped"
    assert result.ok is False
    assert result.error == ""
    assert calls == [], "dry_run 竟然调用了真实 execute"


def test_dry_run_adapter_path_is_skipped(world):
    """退步了会怎样（V-04）：adapter 通道无视 dry_run 真执行适配器（实测会跑命令）。

    断言：带 adapter 引用的动作 + dry_run → skipped、ok=False、data 里带 dry_run 预览。
    """
    action = _fake_action(adapter="some.adapter.id")

    result = exec_iface_mod.executor_for("adapter").execute(
        action, exec_iface_mod.ExecutionContext(dry_run=True))

    assert result.status == "skipped"
    assert result.ok is False
    assert result.data and result.data.get("dry_run") is True


def test_dry_run_scattered_path_is_skipped(world, monkeypatch):
    """退步了会怎样（V-04）：scattered 通道 dry_run 仍跑 run_scattered（trusted 动作
    会产生真实副作用）。

    断言：dry_run → skipped、ok=False、data 带 check 预览，不调用 run_scattered。
    """
    calls = []
    monkeypatch.setattr(scattered_mod, "check_scattered", lambda path: {"valid": True})
    monkeypatch.setattr(scattered_mod, "run_scattered",
                        lambda *a, **k: calls.append(a) or {"status": "ok"})
    action = Action(meta={"id": "scat.demo", "name": "s", "version": "1.0.0",
                          "trust": "sandbox", "entry": "main",
                          "platform": "desktop"},
                    path=str(world.repo / "actions" / "demo.actus.md"),
                    sha256="", blocks=[])

    result = exec_iface_mod.executor_for("scattered").execute(
        action, exec_iface_mod.ExecutionContext(dry_run=True))

    assert result.status == "skipped"
    assert result.ok is False
    assert result.data and result.data.get("dry_run") is True
    assert "check" in result.data
    assert calls == [], "dry_run 竟然调用了 run_scattered"


# ===========================================================================
# exec_iface —— 8) error_kind 分类（业务 401 不误判）
# ===========================================================================

@pytest.mark.parametrize("stderr,expected", [
    ("processed 401 records, then failed", "runtime"),
    ("connection to sqlite db closed", "runtime"),
    ("HTTP 401 Unauthorized", "auth"),
    ("connection refused", "unreachable"),
], ids=["business-401-not-auth", "sqlite-closed-not-unreachable",
        "http-401-auth", "connection-refused"])
def test_error_kind_classification_is_precise(stderr, expected):
    """退步了会怎样（P3 误分类）：裸子串匹配把业务数字 401 判成 auth、把
    "connection to sqlite db closed" 判成 unreachable —— 消费方据此重试/告警全错。

    断言：只认进程级信号（HTTP 状态行 / returncode / 明确关键字），上述 4 个样例
    分别映射到 runtime/runtime/auth/unreachable。
    """
    assert exec_iface_mod._classify_error(stderr, 1) == expected
