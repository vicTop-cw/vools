"""`scattered.py` 契约测试（第 31 轮，T0r4 + S4 竞态回归）。

覆盖：
  1. **形态判定与授权根**：单文件 / `.actus/` 目录 / 非法后缀 / URL / 越界路径
  2. **C2.2 校验**：缺省值补齐、校验失败结构化、未声明依赖拒绝、坏 TOML 显式报错
  3. **C2.4 执行**：校验不过不进入执行；执行前后 env 零残留
  4. **S4 竞态回归（本轮修复）**：env 注入必须持 `PROCESS_STATE_LOCK`；
     并发执行不得串环境/留残留

隔离：`HOME` / `ACTUS_META_DIR` / `ACTUS_REPO_ROOT` 全部指到 tmp；
执行器一律用假实现（`_pick_executor`），**不真跑用户代码**。
"""
import json
import os
import threading
import time

import pytest

from vools.actus import scattered as S
from vools.actus.process_state import PROCESS_STATE_LOCK


# ═══════════════════════════════════════════════════════════════════
# 夹具
# ═══════════════════════════════════════════════════════════════════


def _action_text(action_id="actus.scat.demo", deps=None, trust="sandbox"):
    cfg = {"id": action_id, "name": action_id.rsplit(".", 1)[-1], "version": "1.0.0",
           "trust": trust, "entry": "main", "description": "d", "author": "t",
           "kind": "exec", "platform": ["desktop"]}
    if deps is not None:
        cfg["deps"] = deps
    return ("```json #!cfg\n" + json.dumps(cfg, ensure_ascii=False) + "\n```\n\n"
            "```python #!run tag=main\nimport json\nprint(json.dumps({'ok': 1}))\n```\n")


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    repo = tmp_path / "repo"
    for d in (home, meta, repo):
        d.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    return {"home": home, "meta": meta, "repo": repo, "tmp": tmp_path}


@pytest.fixture
def action_file(isolated_env):
    root = isolated_env["tmp"] / "proj"
    root.mkdir()
    path = root / "demo.actus.md"
    path.write_text(_action_text(), encoding="utf-8")
    return path


@pytest.fixture
def spy_executor(monkeypatch):
    """假执行器：记录调用并返回固定结果，绝不真跑动作代码。"""
    calls = []

    def executor(action_id, params, **kw):
        calls.append({"action_id": action_id, "params": dict(params or {}),
                      "env_scattered": os.environ.get("ACTUS_SCATTERED"),
                      "lock_free": PROCESS_STATE_LOCK.acquire(blocking=False)})
        if calls[-1]["lock_free"]:
            PROCESS_STATE_LOCK.release()
        return {"status": "ok", "data": {"spy": True}}

    monkeypatch.setattr(S, "_pick_executor", lambda: executor)
    return calls


# ═══════════════════════════════════════════════════════════════════
# ① 形态判定 / 授权根
# ═══════════════════════════════════════════════════════════════════


def test_single_file_resolves_with_parent_as_root(action_file):
    """退步了会怎样：单文件形态的授权根被取成动作文件本身或仓根 → 同级相对依赖
    （`./lib.actus/`）全被判越界，合法的复杂动作没法跑。
    """
    sc = S.resolve_scattered(str(action_file))
    assert sc.kind == "file"
    assert sc.path == os.path.abspath(str(action_file))
    assert sc.root == os.path.dirname(os.path.abspath(str(action_file)))


def test_directory_form_requires_entry_file(isolated_env):
    """退步了会怎样：`<x>.actus/` 目录缺 `main.actus.md` 时被当成"没有动作"静默跳过，
    而不是明确告知缺入口 → 用户以为路径写错。
    """
    d = isolated_env["tmp"] / "multi.actus"
    d.mkdir()
    with pytest.raises(S.ScatteredError) as exc:
        S.resolve_scattered(str(d))
    assert exc.value.code == "action_not_found"
    assert exc.value.details.get("expected_entry") == S.ENTRY_FILENAME


def test_directory_form_resolves_entry(isolated_env):
    """退步了会怎样：目录形态解析不到入口（或 kind 记成 file）→ 后续执行拿错路径。
    """
    d = isolated_env["tmp"] / "multi2.actus"
    d.mkdir()
    entry = d / S.ENTRY_FILENAME
    entry.write_text(_action_text("actus.scat.dir"), encoding="utf-8")
    sc = S.resolve_scattered(str(d))
    assert sc.kind == "dir"
    assert sc.path == os.path.abspath(str(entry))


def test_non_action_suffix_rejected(isolated_env):
    """退步了会怎样：任意 `.md`/`.txt` 被当成零散动作 → 解析器会在非动作文件上炸，
    或被误当动作执行。
    """
    junk = isolated_env["tmp"] / "notes.md"
    junk.write_text("x", encoding="utf-8")
    with pytest.raises(S.ScatteredError) as exc:
        S.resolve_scattered(str(junk))
    assert exc.value.code == "action_not_found"


def test_url_is_not_a_scattered_path():
    """退步了会怎样：URL 被 `is_action_file` 判成本地散落路径（后缀恰好是 .actus.md），
    在目标解析优先级链里抢先命中，把 URL 分支整个吞掉。
    """
    assert S.is_scattered_path("https://example.com/a.actus.schema.md") is False
    assert S.is_scattered_path("./a.actus.md") is True


def test_path_escape_rejected_by_realpath(isolated_env, action_file):
    """退步了会怎样：授权根外的文件被接受（只判 startswith 而不 realpath，或干脆不判）
    → 零散动作可以读取/执行授权根之外任意文件（路径穿越）。
    """
    outside = isolated_env["tmp"] / "outside.actus.md"
    outside.write_text(_action_text("actus.scat.out"), encoding="utf-8")
    with pytest.raises(S.ScatteredError) as exc:
        S.resolve_scattered(str(outside), authorized_root=str(action_file.parent))
    assert exc.value.code == "path_escaped"


# ═══════════════════════════════════════════════════════════════════
# ② C2.2 校验
# ═══════════════════════════════════════════════════════════════════


def test_check_scattered_valid_action_applies_defaults(isolated_env):
    """退步了会怎样：缺省值（trust=audit / visibility=private）没补上 → 执行前
    校验报 "trust 缺失"，零散动作根本跑不起来；或补了但不记录（调用方无从知情）。
    """
    root = isolated_env["tmp"] / "p2"
    root.mkdir()
    act = root / "d.actus.md"
    cfg = {"id": "actus.scat.d", "name": "d", "version": "1.0.0", "entry": "main",
           "description": "d", "author": "t", "kind": "exec", "platform": ["desktop"]}
    act.write_text("```json #!cfg\n" + json.dumps(cfg) + "\n```\n\n"
                   "```python #!run tag=main\nprint('{}')\n```\n", encoding="utf-8")

    chk = S.check_scattered(str(act))
    # 注意：trust 缺省补成 audit 后，docs/47 §4 的「audit 必须带测试绑定」会判 valid=False
    # —— 那是**另一条正确的校验规则**。本用例只钉"缺省值补齐并被记录"。
    assert chk["defaults_applied"]["trust"] == "audit", chk["defaults_applied"]
    assert chk["defaults_applied"]["visibility"] == "private"
    assert chk["action"]["trust"] == "audit"
    assert chk["action"]["visibility"] == "private"


def test_check_scattered_reports_errors_for_invalid_action(isolated_env):
    """退步了会怎样：校验失败只返回 `valid=False` 不给明细 → 用户不知道该改哪。
    """
    root = isolated_env["tmp"] / "p3"
    root.mkdir()
    bad = root / "bad.actus.md"
    bad.write_text("```json #!cfg\n{\"name\": \"no-id\"}\n```\n", encoding="utf-8")
    chk = S.check_scattered(str(bad))
    assert chk["valid"] is False
    assert chk["errors"], "校验失败必须逐项列出错误"
    assert any(e.get("code") for e in chk["errors"])


def test_undeclared_dependency_rejected(isolated_env):
    """退步了会怎样：动作声明 `pip:xxx` 但 project.actus.toml 没声明时被放行 →
    隐形安装/隐式依赖（docs/35 明确"未声明即拒"）。
    """
    root = isolated_env["tmp"] / "p4"
    root.mkdir()
    act = root / "deps.actus.md"
    act.write_text(_action_text("actus.scat.deps", deps=["pip:somepkg"]), encoding="utf-8")
    chk = S.check_scattered(str(act))
    assert chk["valid"] is False
    codes = [e["code"] for e in chk["errors"]]
    assert "dependency_missing" in codes, codes


def test_declared_dependency_accepted(isolated_env):
    """退步了会怎样：声明了依赖却被拒（或都没声明就放行）—— 声明式依赖形同虚设。
    """
    root = isolated_env["tmp"] / "p5"
    root.mkdir()
    act = root / "deps.actus.md"
    act.write_text(_action_text("actus.scat.deps2", deps=["pip:somepkg"]), encoding="utf-8")
    (root / S.PROJECT_DEPS_FILENAME).write_text('pip = ["somepkg"]\n', encoding="utf-8")
    chk = S.check_scattered(str(act))
    codes = [e["code"] for e in chk["errors"]]
    assert "dependency_missing" not in codes, chk["errors"]
    assert chk["deps"]["declared"] == ["pip:somepkg"]


def test_toml_parse_error_is_explicit(isolated_env):
    """退步了会怎样：坏 TOML 被读成"没有依赖" → 未声明依赖静默放行（fail-open）。
    """
    root = isolated_env["tmp"] / "p6"
    root.mkdir()
    (root / S.PROJECT_DEPS_FILENAME).write_text("this is not toml\n", encoding="utf-8")
    with pytest.raises(S.ScatteredError) as exc:
        S.load_project_deps(str(root))
    assert exc.value.code == "action_invalid"


def test_toml_unknown_keys_are_reported_not_dropped(isolated_env):
    """退步了会怎样：写错的键（如 `pips`）被静默丢弃 → 作者以为声明生效了，
    实际依赖未声明却被"看起来配了"蒙混过去。
    """
    root = isolated_env["tmp"] / "p7"
    root.mkdir()
    (root / S.PROJECT_DEPS_FILENAME).write_text(
        'pip = ["a"]\npips = ["b"]\n', encoding="utf-8")
    doc = S.load_project_deps(str(root))
    assert doc["_unknown_keys"] == ["pips"], doc


# ═══════════════════════════════════════════════════════════════════
# ③ C2.4 执行
# ═══════════════════════════════════════════════════════════════════


def test_run_scattered_refuses_invalid_before_execution(isolated_env, spy_executor, monkeypatch):
    """退步了会怎样：校验不过仍然进入执行（check_first 失效）→ 未校验的动作被执行，
    门禁/沙箱策略全部跳过。
    """
    root = isolated_env["tmp"] / "p8"
    root.mkdir()
    bad = root / "bad.actus.md"
    bad.write_text("```json #!cfg\n{\"name\": \"x\"}\n```\n", encoding="utf-8")

    result = S.run_scattered(str(bad))
    assert result["status"] == "failed"
    assert result["error"]["code"] == "action_invalid"
    assert spy_executor == [], "校验不过时执行器绝不能被调用"


def test_run_scattered_executes_and_restores_host_env(action_file, spy_executor):
    """退步了会怎样：执行后 `PYTHONPATH`/`ACTUS_SCATTERED` 没还原 → 宿主（CLI/MCP
    的后续命令）会带着零散模式的注入环境继续跑，import 拓扑被静默改掉。
    """
    before = {k: os.environ.get(k) for k in
              ("PYTHONPATH", "ACTUS_SCATTERED", "ACTUS_INJECTED_CORE")}
    result = S.run_scattered(str(action_file), {}, confirmed=False)

    assert result["status"] == "ok"
    assert len(spy_executor) == 1, "合法动作应真的进入执行器一次"
    assert spy_executor[0]["env_scattered"] == "1", "执行器内必须看到注入标记"
    after = {k: os.environ.get(k) for k in
             ("PYTHONPATH", "ACTUS_SCATTERED", "ACTUS_INJECTED_CORE")}
    assert after == before, "执行后宿主环境必须逐键还原: %r -> %r" % (before, after)


# ═══════════════════════════════════════════════════════════════════
# ④ S4 竞态回归（本轮修复：env 注入必须持 PROCESS_STATE_LOCK）
# ═══════════════════════════════════════════════════════════════════


def test_s4_env_injection_waits_for_process_state_lock(action_file, spy_executor):
    """退步了会怎样（S4）：env 注入在锁外进行 —— 别的线程持锁（正在注入/还原它自己的
    环境）时，本次执行照样改 `os.environ`，两个执行互相看见对方的 PYTHONPATH/
    ACTUS_SCATTERED。表现为偶发、难复现的串环境。

    本用例让另一个线程持锁 0.5s：修复后 run_scattered 必须等它释放（>=0.45s）；
    修复前会立刻返回（~0.0s）。
    """
    held = threading.Event()

    def holder():
        PROCESS_STATE_LOCK.acquire()
        held.set()
        time.sleep(0.5)
        PROCESS_STATE_LOCK.release()

    thread = threading.Thread(target=holder, daemon=True)
    thread.start()
    assert held.wait(5)

    start = time.perf_counter()
    result = S.run_scattered(str(action_file), {}, confirmed=False)
    elapsed = time.perf_counter() - start
    thread.join(5)

    assert result["status"] == "ok"
    assert elapsed >= 0.45, \
        "run_scattered 未等待 PROCESS_STATE_LOCK（竞态窗口仍在）: %.3fs" % elapsed


def test_s4_concurrent_runs_leave_no_env_residue(action_file, monkeypatch):
    """退步了会怎样（S4 的第二半）：快照在锁外取 → 可能把别人注入后的值当"原始值"
    写回宿主，跑完残留 ACTUS_SCATTERED（实测并发 8×3 轮后残留 True）。
    本用例并发 6 线程 × 2 轮，跑完必须零残留。
    """
    def executor(action_id, params, **kw):
        time.sleep(0.005)
        return {"status": "ok", "data": {"spy": True}}

    monkeypatch.setattr(S, "_pick_executor", lambda: executor)
    before = {k: os.environ.get(k) for k in
              ("PYTHONPATH", "ACTUS_SCATTERED", "ACTUS_INJECTED_CORE")}

    for _ in range(2):
        threads = [threading.Thread(target=S.run_scattered,
                                    args=(str(action_file), {}, False))
                   for _ in range(6)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(20)

    after = {k: os.environ.get(k) for k in
             ("PYTHONPATH", "ACTUS_SCATTERED", "ACTUS_INJECTED_CORE")}
    assert after == before, "并发执行后宿主环境残留: %r -> %r" % (before, after)
