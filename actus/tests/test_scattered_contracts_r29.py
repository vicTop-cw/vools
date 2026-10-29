# -*- coding: utf-8 -*-
"""actus/tests/test_scattered_contracts_r29.py — scattered（零散动作，773 行）契约。

`scattered.py` 是 docs/41 主题 C 的落地：任意路径 `.actus.md` / `<id>.actus/` 即插即用。
此前仅 ~18% 覆盖，是本批最大的风险面。本文件覆盖：

  1. 形态判定/解析（单文件、目录入口、非法路径、路径逃逸）；
  2. `check_scattered` 的校验三态（合法 / 规范错误 / 声明式依赖/环路）；
  3. `run_scattered` 的执行前拦截、**env 注入与还原**（S4：注入/还原在
     `PROCESS_STATE_LOCK` 临界区内）、目录形态的 actions_dir；
  4. 并发：持锁时 run 必须等待（不越过锁改 os.environ）。

语义钉点（实测当前行为，非直觉）：
  * 目录形态只认 `<id>.actus/main.actus.md` —— **不会**把普通目录里所有
    `*.actus.md` 展开成多个动作（"展开"由 executor 以 actions_dir 扫描完成）；
  * 未声明 trust 的零散动作按 `audit` 处理；`audit` 级别还要求 tests 绑定，
    所以"默认 trust 的动作"在本 fixture 里 valid 可能为 False —— 缺省值本身
    仍然会写进 `defaults_applied`（本文件钉住的是**缺省值应用**而非 valid）；
  * 声明式依赖（`pip:`/`npm:`/`system:`/`env:`）未在 `project.actus.toml`
    声明 → `dependency_missing`；路径依赖逃逸授权根 → `path_escaped`；
    路径依赖成环 → `dependency_cycle`。

S4 竞态：cmd-hardening 已把 `run_scattered` 的 env 注入/还原移进
`PROCESS_STATE_LOCK`（本文件按修复后行为断言；不修改产品）。
"""

import json
import os
import shutil
import sys
import threading

import pytest

_ACTUS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import scattered  # noqa: E402
from vools.actus.process_state import PROCESS_STATE_LOCK  # noqa: E402


# ---------------------------------------------------------------------------
# 夹具 / 辅助
# ---------------------------------------------------------------------------

class _World(object):
    pass


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    actions = repo / "actions"
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    for directory in (actions, home, meta):
        directory.mkdir(parents=True)
    shutil.copytree(os.path.join(_ACTUS_ROOT, "contracts"), str(repo / "contracts"))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_VAULT2_DIR", str(tmp_path / "vault2"))
    monkeypatch.setenv("ACTUS_VAULT2_KEY_PROTECTION", "file-key")

    w = _World()
    w.root = tmp_path
    w.repo = repo
    w.meta = meta
    w.__class__.write_action = staticmethod(_write_action)
    return w


def _write_action(path, aid, deps=None, trust="sandbox", extra=None):
    """在 path 写一个最小合法零散动作；deps 用 JSON（不能用 Python repr，会变非法 JSON）。"""
    cfg = {"id": aid, "name": "A", "version": "1.0.0", "description": "d",
           "entry": "main", "platform": "desktop"}
    if trust is not None:
        cfg["trust"] = trust
    if deps is not None:
        cfg["deps"] = deps
    if extra:
        cfg.update(extra)
    text = ('# A\n\n```json #!cfg\n%s\n```\n\n'
            '```python #!run tag=main\nprint("hi")\n```\n' % json.dumps(cfg, ensure_ascii=False))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _err_codes(report):
    return [item.get("code") for item in (report.get("errors") or [])]


class _FakeExecutor(object):
    def __init__(self):
        self.calls = []
        self.env_during = None

    def __call__(self, action_id, params, **kwargs):
        self.calls.append({"action_id": action_id, "params": params, "kwargs": kwargs})
        self.env_during = {k: os.environ.get(k) for k in
                           ("PYTHONPATH", "ACTUS_SCATTERED", "ACTUS_INJECTED_CORE")}
        return {"status": "ok", "data": {"ran": action_id}}


# ===========================================================================
# 1) 形态判定与解析
# ===========================================================================

def test_is_scattered_path_recognizes_forms_and_rejects_others(world):
    """退步了会怎样：`.actus.schema.md`（新格式）或 `.actus/` 目录不被认成零散动作
    —— 用户把动作放在任意路径下，CLI/MCP 却当普通文件处理；URL 被误判成本地路径
    （抢在 resolver 的 URL 分支前）。

    断言：`.actus.md` / `.actus.schema.md` / 已存在的 `<id>.actus/` → True；
    URL、普通 .txt、**不存在的** `.actus` 目录 → False。
    """
    single = world.write_action(world.root / "single.actus.md", "single.a")
    schema = world.root / "schema.actus.schema.md"
    schema.write_text(single.read_text(encoding="utf-8"), encoding="utf-8")
    bundle = world.root / "bundle.actus"
    world.write_action(bundle / "main.actus.md", "bundle.a")

    assert scattered.is_scattered_path(str(single)) is True
    assert scattered.is_scattered_path(str(schema)) is True
    assert scattered.is_scattered_path(str(bundle)) is True
    assert scattered.is_scattered_path("https://example.com/x.actus.schema.md") is False
    assert scattered.is_scattered_path(str(world.root / "x.txt")) is False
    assert scattered.is_scattered_path(str(world.root / "missing.actus")) is False


def test_resolve_single_file_and_dir_entry(world):
    """退步了会怎样：解析结果把 root/entry_path 弄错（目录形态拿目录当动作文件）——
    后续校验/执行读错文件，路径边界也失效。

    断言：单文件 → kind='file'、path=文件、root=所在目录、entry_path=None；
    目录 → kind='dir'、path=main.actus.md、root=目录、entry_path=入口。
    """
    single = world.write_action(world.root / "one.actus.md", "one.a")
    sc_file = scattered.resolve_scattered(str(single))
    assert sc_file.kind == "file"
    assert os.path.samefile(sc_file.path, str(single))
    assert sc_file.root == os.path.dirname(str(single))
    assert sc_file.entry_path is None

    bundle = world.root / "b2.actus"
    entry = world.write_action(bundle / "main.actus.md", "b2.a")
    sc_dir = scattered.resolve_scattered(str(bundle))
    assert sc_dir.kind == "dir"
    assert os.path.samefile(sc_dir.path, str(entry))
    assert os.path.samefile(sc_dir.entry_path, str(entry))
    assert os.path.samefile(sc_dir.root, str(bundle))


def test_resolve_dir_without_entry_is_explicit_error(world):
    """退步了会怎样：`<id>.actus/` 缺少 main.actus.md 时静默当成"没有动作"/空动作 ——
    用户得到一条看不出原因的失败。显式报 action_not_found 并点名缺什么。

    断言：ScatteredError.code='action_not_found'，消息含入口文件名。
    """
    bundle = world.root / "empty.actus"
    bundle.mkdir()

    with pytest.raises(scattered.ScatteredError) as excinfo:
        scattered.resolve_scattered(str(bundle))
    assert excinfo.value.code == "action_not_found"
    assert scattered.ENTRY_FILENAME in excinfo.value.message


def test_resolve_rejects_non_action_suffix_and_missing_path(world):
    """退步了会怎样：普通 .txt / 不存在的路径被当成零散动作（后续 parse 抛
    FileNotFoundError 之类不可诊断错误）。

    断言：两者都抛 ScatteredError(action_not_found)，消息可读。
    """
    txt = world.root / "plain.txt"
    txt.write_text("nope", encoding="utf-8")
    with pytest.raises(scattered.ScatteredError) as excinfo:
        scattered.resolve_scattered(str(txt))
    assert excinfo.value.code == "action_not_found"

    with pytest.raises(scattered.ScatteredError) as excinfo:
        scattered.resolve_scattered(str(world.root / "no.such.actus.md"))
    assert excinfo.value.code == "action_not_found"


def test_resolve_rejects_path_outside_authorized_root(world):
    """退步了会怎样（路径逃逸）：显式 authorized_root 只包含 inner/，用户传
    `../outside.actus.md` 仍被解析/执行 —— 授权根形同虚设。

    断言：文件在授权根外 → ScatteredError(path_escaped)，details 带 root/resolved。
    """
    inner = world.root / "inner"
    inner.mkdir()
    outside = world.write_action(world.root / "outside.actus.md", "out.a")

    with pytest.raises(scattered.ScatteredError) as excinfo:
        scattered.resolve_scattered(str(outside), authorized_root=str(inner))
    assert excinfo.value.code == "path_escaped"
    assert "root" in excinfo.value.details and "resolved" in excinfo.value.details


# ===========================================================================
# 2) check_scattered：三态与依赖
# ===========================================================================

def test_check_valid_action_reports_form_action_and_defaults(world):
    """退步了会怎样：合法零散动作被判 invalid（默认值/注入报告没接上）——
    "任意路径即插即用"直接不可用。

    断言：valid=True、errors=[]、form.kind='file'、action.id 正确、
    defaults_applied 含 visibility=private（trust 显式 sandbox 不覆盖）、
    injection 报告存在。
    """
    path = world.write_action(world.root / "ok.actus.md", "ok.a")

    report = scattered.check_scattered(str(path))

    assert report["valid"] is True, report["errors"]
    assert report["errors"] == []
    assert report["form"]["kind"] == "file"
    assert report["action"]["id"] == "ok.a"
    assert report["defaults_applied"].get("visibility") == "private"
    assert isinstance(report.get("injection"), dict) and report["injection"]


def test_check_applies_default_trust_audit_and_visibility_private(world):
    """退步了会怎样（C1 默认私有）：未声明 trust/visibility 的零散动作被当成
    trusted/public —— 首次执行不要求确认，安全默认失效。

    断言：defaults_applied 明确记录 trust=audit、visibility=private，且 action 字段
    透出这两个值（valid 可能因 audit 需 tests 绑定而 False —— 缺省值仍已应用）。
    """
    path = world.write_action(world.root / "defaults.actus.md", "def.a", trust=None)

    report = scattered.check_scattered(str(path))

    assert report["defaults_applied"].get("trust") == "audit"
    assert report["defaults_applied"].get("visibility") == "private"
    assert report["action"]["trust"] == "audit"
    assert report["action"]["visibility"] == "private"


def test_check_broken_cfg_reports_action_invalid(world):
    """退步了会怎样（失败路径）：#!cfg 元数据损坏被静默当成"没有动作"/空报告 ——
    用户拿不到可修复的原因。

    断言：不抛异常；valid=False；errors 中 code=action_invalid 且消息含 JSON 解析信息。
    """
    bad = world.root / "broken.actus.md"
    bad.write_text('# bad\n\n```json #!cfg\n{not-json}\n```\n', encoding="utf-8")

    report = scattered.check_scattered(str(bad))

    assert report["valid"] is False
    assert "action_invalid" in _err_codes(report), report["errors"]
    assert any("JSON" in (e.get("message") or "") for e in report["errors"]), report["errors"]


def test_check_declared_dependency_requires_project_toml(world):
    """退步了会怎样（docs/41 §C3）：动作声明 `pip:requests` 但没在 project.actus.toml
    背书就放行 —— 执行时才隐式安装/失败，供应链风险。

    断言：未声明 → dependency_missing；补上 `pip = ["requests"]` 后 → valid=True，
    deps.declared 恰为 ['pip:requests']。
    """
    path = world.write_action(world.root / "dep.actus.md", "dep.a",
                              deps=["pip:requests"])

    undeclared = scattered.check_scattered(str(path))
    assert undeclared["valid"] is False
    assert "dependency_missing" in _err_codes(undeclared), undeclared["errors"]

    (world.root / "project.actus.toml").write_text('pip = ["requests"]\n',
                                                   encoding="utf-8")
    declared = scattered.check_scattered(str(path))
    assert declared["valid"] is True, declared["errors"]
    assert declared["deps"]["declared"] == ["pip:requests"], declared["deps"]


def test_check_malformed_project_toml_is_explicit_error(world):
    """退步了会怎样：project.actus.toml 写坏时被当成"没有依赖声明"—— 未声明依赖
    静默放行（正是 docs/35 要挡的降级）。

    断言：valid=False，errors 含 action_invalid，消息点名 project.actus.toml。
    """
    path = world.write_action(world.root / "dep2.actus.md", "dep2.a",
                              deps=["pip:requests"])
    (world.root / "project.actus.toml").write_text("pip = [unclosed\n", encoding="utf-8")

    report = scattered.check_scattered(str(path))

    assert report["valid"] is False
    assert "action_invalid" in _err_codes(report), report["errors"]
    assert any(scattered.PROJECT_DEPS_FILENAME in (e.get("message") or "")
               for e in report["errors"]), report["errors"]


def test_check_dependency_cycle_is_reported(world):
    """退步了会怎样：零散动作路径依赖成环（a→b→a）不被检测 —— 执行时递归/死循环，
    或依赖注入顺序随机。

    断言：valid=False，errors 含 dependency_cycle，details.cycle 非空。
    """
    world.write_action(world.root / "a.actus.md", "cyc.a", deps=["./b.actus.md"])
    world.write_action(world.root / "b.actus.md", "cyc.b", deps=["./a.actus.md"])

    report = scattered.check_scattered(str(world.root / "a.actus.md"))

    assert report["valid"] is False
    cycle_errors = [e for e in report["errors"] if e.get("code") == "dependency_cycle"]
    assert cycle_errors, report["errors"]
    assert cycle_errors[0]["details"].get("cycle"), cycle_errors[0]


def test_check_path_dependency_escape_is_reported(world):
    """退步了会怎样：动作用 `../outside.actus.md` 引用授权根外的文件 —— 路径依赖
    变成越权读取/执行。

    断言：valid=False，errors 含 path_escaped。
    """
    world.write_action(world.root / "outside2.actus.md", "out2.a")
    inner = world.root / "pkg"
    path = world.write_action(inner / "in.actus.md", "in.a", deps=["./../outside2.actus.md"])

    report = scattered.check_scattered(str(path), authorized_root=str(inner))

    assert report["valid"] is False
    assert "path_escaped" in _err_codes(report), report["errors"]


def test_check_missing_action_id_dependency_is_reported(world):
    """退步了会怎样：依赖一个不存在的动作 id 时静默通过 —— 执行期才 action_not_found。

    断言：valid=False，errors 含 dependency_missing，details.missing 点名该 id。
    """
    path = world.write_action(world.root / "iddep.actus.md", "iddep.a",
                              deps=["no.such.action"])
    report = scattered.check_scattered(str(path))

    assert report["valid"] is False
    missing = [e for e in report["errors"] if e.get("code") == "dependency_missing"]
    assert missing, report["errors"]
    assert "no.such.action" in (missing[0]["details"].get("missing") or []), missing[0]


# ===========================================================================
# 3) run_scattered：执行前拦截 / env 注入还原 / 目录形态
# ===========================================================================

def test_run_rejects_invalid_action_before_execution(world, monkeypatch):
    """退步了会怎样：`check_first=True` 失效 —— 校验不过的动作仍进执行链
    （"不校验就执行"的安全门被绕过）。

    断言：返回 failed/code=action_invalid；假 executor **一次都没被调用**。
    """
    bad = world.root / "bad-run.actus.md"
    bad.write_text('# x\n\n```json #!cfg\n{bad}\n```\n', encoding="utf-8")
    fake = _FakeExecutor()
    monkeypatch.setattr(scattered, "_pick_executor", lambda: fake)

    result = scattered.run_scattered(str(bad), meta_dir=str(world.meta))

    assert result["status"] == "failed"
    assert result["error"]["code"] == "action_invalid"
    assert fake.calls == [], "校验失败的动作仍进入了执行链"


def test_run_injects_env_and_restores_it_exactly(world, monkeypatch):
    """退步了会怎样（C3/S4）：执行期不注入 PYTHONPATH/ACTUS_SCATTERED（动作 import
    不到核心依赖）；或**跑完不还原** —— 宿主进程被永久污染（后续动作互相串环境）。

    断言：
      * executor 执行期间：PYTHONPATH 含本包路径且保留原 sentinel；
        ACTUS_SCATTERED == '1'；ACTUS_INJECTED_CORE 含 actuscore；
      * 返回后：三个 env 逐字还原（原本不存在 → 仍不存在）；
      * kwargs：actions_dir=动作所在目录、meta_dir 透传、preparsed_action 非 None。
    """
    path = world.write_action(world.root / "run.actus.md", "run.a")
    fake = _FakeExecutor()
    monkeypatch.setattr(scattered, "_pick_executor", lambda: fake)

    monkeypatch.setenv("PYTHONPATH", "/sentinel/pre")
    monkeypatch.delenv("ACTUS_SCATTERED", raising=False)
    monkeypatch.setenv("ACTUS_INJECTED_CORE", "sentinel-core")

    result = scattered.run_scattered(str(path), meta_dir=str(world.meta))

    assert result["status"] == "ok", result
    assert fake.calls and fake.calls[0]["action_id"] == "run.a"
    during = fake.env_during
    assert "/sentinel/pre" in (during["PYTHONPATH"] or "").split(os.pathsep)
    assert during["ACTUS_SCATTERED"] == "1", during
    assert "actuscore" in (during["ACTUS_INJECTED_CORE"] or ""), during

    assert os.environ.get("PYTHONPATH") == "/sentinel/pre"
    assert os.environ.get("ACTUS_INJECTED_CORE") == "sentinel-core"
    assert os.environ.get("ACTUS_SCATTERED") is None

    kwargs = fake.calls[0]["kwargs"]
    assert os.path.samefile(kwargs["actions_dir"], str(world.root))
    assert kwargs.get("meta_dir") == str(world.meta)
    assert kwargs.get("preparsed_action") is not None


def test_run_dir_form_passes_action_directory(world, monkeypatch):
    """退步了会怎样：目录形态把"动作文件所在目录"（main.actus.md 的父目录）当
    actions_dir 传下去 —— 入口能跑，但同目录 lib/ 依赖解析不到。

    断言：kind='dir'、executor 收到的 actions_dir == 授权根（`.actus/` 目录本身）。
    """
    bundle = world.root / "pkg2.actus"
    world.write_action(bundle / "main.actus.md", "pkg2.a")
    fake = _FakeExecutor()
    monkeypatch.setattr(scattered, "_pick_executor", lambda: fake)

    result = scattered.run_scattered(str(bundle), meta_dir=str(world.meta))

    assert result["status"] == "ok", result
    assert os.path.samefile(fake.calls[0]["kwargs"]["actions_dir"], str(bundle))
    assert result["scattered"]["form"]["kind"] == "dir"


def test_run_waits_for_process_state_lock_before_touching_env(world, monkeypatch):
    """退步了会怎样（S4 竞态）：run_scattered 在 PROCESS_STATE_LOCK **之外**改
    os.environ —— 另一个线程持锁执行动作时，两个执行互相看见对方的
    PYTHONPATH/ACTUS_SCATTERED（偶发串环境，难复现）。

    断言：主线程先持锁；后台线程 run_scattered 必须阻塞（假 executor 未被调用）；
    释放锁后它才执行并成功。用 Event 同步，不靠固定 sleep。
    """
    path = world.write_action(world.root / "lock.actus.md", "lock.a")
    fake = _FakeExecutor()
    monkeypatch.setattr(scattered, "_pick_executor", lambda: fake)

    started = threading.Event()
    finished = threading.Event()
    result_holder = {}

    def worker():
        started.set()
        try:
            result_holder["result"] = scattered.run_scattered(
                str(path), meta_dir=str(world.meta))
        finally:
            finished.set()

    PROCESS_STATE_LOCK.acquire()
    try:
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        assert started.wait(2.0), "后台线程未启动"
        assert not finished.wait(0.2), "持锁期间 run_scattered 竟然完成了（越过了锁）"
        assert fake.calls == [], "持锁期间仍改 env 并执行了 executor"
    finally:
        PROCESS_STATE_LOCK.release()

    assert finished.wait(5.0), "释放锁后 run_scattered 仍未完成"
    assert result_holder["result"]["status"] == "ok", result_holder
    assert len(fake.calls) == 1


def test_generic_directory_is_not_expanded_to_multiple_actions(world):
    """退步了会怎样（语义漂移）：把普通目录（不以 `.actus` 结尾）里的多个
    `*.actus.md` 当成多个零散动作展开 —— 用户传错目录会被"成功执行一堆动作"，
    与 docs/41 的显式入口语义相反。

    断言：普通目录 → ScatteredError(action_not_found)；
    只有 `<id>.actus/` + main.actus.md 才是目录形态动作（见 resolve 用例）。
    """
    plain = world.root / "plain_dir"
    plain.mkdir()
    world.write_action(plain / "x.actus.md", "plain.x")
    world.write_action(plain / "y.actus.md", "plain.y")

    with pytest.raises(scattered.ScatteredError) as excinfo:
        scattered.resolve_scattered(str(plain))
    assert excinfo.value.code == "action_not_found"

    checks = scattered.check_scattered(str(plain))
    assert checks["valid"] is False
    assert checks["form"] is None
    assert "action_not_found" in _err_codes(checks)
