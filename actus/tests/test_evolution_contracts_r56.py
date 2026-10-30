"""evolution.py 契约测试（Round 51）。

契约:
- EvolutionEngine 构造：显式 root / 默认（indexer._repo_root + paths.meta_dir）、构造不建目录
- evolve 循环：generate fail / validate fail→repair / test pass→promote / max rounds
- repair：action 不存在 / validate 失败修复循环 / max rounds
- _phase_generate：scaffold 成功/非文件/异常
- _phase_validate：真实入口（parse_cfg_from_file + validate_action + split_validation）/异常
- _phase_test：awaiting_confirmation=pass / failed=fail / preview 异常 / 期望校验
- _phase_repair：round>=max → None / 写回修复结果 / 无变化 → None / 文件缺失 → None
- _repair_simple/context/restructure/degrade：逐策略替换
- _check_expectations：恒 (True, ...)（preview 不执行，契约即退化）
- _save_version_snapshot：keep_history=False 跳过；建目录+拷贝+info.json
- get_history：无目录/无文件 → []；读 jsonl
- rollback：版本不存在/无快照/当前动作缺失/成功（BUG 佐证：返回 action_id 字面量）
- compare_versions：版本缺失/快照缺失/行级 diff
- _find_action_path：installer 命中 / installer 异常→resolver / 双双失败 → None
- list_evolved_actions / get_status
- 便捷函数 + __all__

BUG 发现（未修，佐证于断言）:
- rollback (evolution.py:516) 返回 {"action_id": "action_id"} —— 字面量而非变量，
  任何成功回滚都汇报错误的 id。
"""

import json
import os
from pathlib import Path

import pytest

import vools.actus.evolution as evo_mod
from vools.actus.evolution import (
    EvolutionConfig,
    EvolutionEngine,
    EvolutionRecord,
    compare_action_versions,
    evolve_action,
    get_evolution_status,
    repair_action,
    rollback_action,
)


ACTION_MD = """# demo

```json #!cfg
{"id": "evo.t", "title": "T", "version": "0.1.0", "trust": "trusted", "kind": "exec", "entry": "main"}
```

## 执行

```python
print("ok")
```
"""


class TestConfigAndRecord:
    """EvolutionConfig / EvolutionRecord。"""

    def test_config_defaults(self):
        c = EvolutionConfig()
        assert c.max_rounds == 5
        assert c.test_timeout == 30
        assert c.auto_promote is False
        assert c.rollback_on_failure is True
        assert c.keep_history is True
        assert c.diversity == 0.3

    def test_record_to_dict(self):
        r = EvolutionRecord(round_num=1, phase="test", status="pass",
                            action_id="a", message="m", details={"x": 1})
        d = r.to_dict()
        assert d["round_num"] == 1
        assert d["phase"] == "test"
        assert d["status"] == "pass"
        assert d["details"] == {"x": 1}
        assert isinstance(d["timestamp"], float)


class TestEngineInit:
    """构造契约。"""

    def test_explicit_root(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        assert e._repo_root == str(tmp_path)
        assert e._evolution_dir == os.path.join(str(tmp_path), "_meta", "evolution")

    def test_default_root_follows_paths(self, tmp_path, monkeypatch):
        """无显式 root：indexer._repo_root() + paths.meta_dir()。"""
        import vools.actus.indexer as indexer_mod
        import vools.actus.paths as paths_mod
        monkeypatch.setattr(indexer_mod, "_repo_root", lambda: str(tmp_path))
        meta = tmp_path / "m"
        monkeypatch.setattr(paths_mod, "meta_dir", lambda: str(meta))
        e = EvolutionEngine()
        assert e._repo_root == str(tmp_path)
        assert e._evolution_dir == str(meta / "evolution")

    def test_construct_creates_no_dirs(self, tmp_path):
        """纯读（--list）也构造本类 → 构造不得建目录。"""
        EvolutionEngine(repo_root=str(tmp_path))
        assert not (tmp_path / "_meta").exists()

    def test_history_property_returns_copy(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        h1 = e.history
        h2 = e.history
        assert h1 is not h2
        assert h1 == h2


class TestEvolveLoop:
    """evolve 主循环。"""

    def _engine(self, tmp_path):
        return EvolutionEngine(repo_root=str(tmp_path))

    def test_generate_fail(self, tmp_path, monkeypatch):
        e = self._engine(tmp_path)
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action",
                            lambda **kw: {"path": "", "id": "evo.t"})
        r = e.evolve("desc", action_id="evo.t")
        assert r["status"] == "failed"
        assert r["reason"] == "Generate failed"
        assert r["rounds"] == 1

    def test_generate_exception(self, tmp_path, monkeypatch):
        e = self._engine(tmp_path)
        def boom(**kw):
            raise RuntimeError("scaffold down")
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action", boom)
        r = e.evolve("desc", action_id="evo.t")
        assert r["status"] == "failed"
        # 异常被 _record 记录（round 0, generate, fail）
        assert any(rec["phase"] == "generate" and rec["status"] == "fail"
                   and "scaffold down" in rec["message"]
                   for rec in r["history"])

    def test_success_first_round(self, tmp_path, monkeypatch):
        action_file = tmp_path / "actions" / "evo.t.actus.md"
        action_file.parent.mkdir()
        action_file.write_text(ACTION_MD, encoding="utf-8")
        e = self._engine(tmp_path)
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action",
                            lambda **kw: {"path": str(action_file), "id": "evo.t"})
        monkeypatch.setattr(e, "_phase_validate",
                            lambda p: {"valid": True, "message": "ok", "errors": []})
        monkeypatch.setattr(e, "_phase_test",
                            lambda p, exp: {"pass": True, "message": "ok"})
        r = e.evolve("desc")
        assert r["status"] == "ok"
        assert r["rounds"] == 1
        assert r["path"] == str(action_file)
        phases = [rec["phase"] for rec in r["history"]]
        assert "promote" in phases

    def test_validate_fail_then_repair_fails(self, tmp_path, monkeypatch):
        action_file = tmp_path / "actions" / "evo.t.actus.md"
        action_file.parent.mkdir()
        action_file.write_text(ACTION_MD, encoding="utf-8")
        e = self._engine(tmp_path)
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action",
                            lambda **kw: {"path": str(action_file), "id": "evo.t"})
        monkeypatch.setattr(e, "_phase_validate",
                            lambda p: {"valid": False, "message": "bad", "errors": ["e"]})
        # 修复无变化 → None → Repair failed (validate)
        monkeypatch.setattr(e, "_phase_repair", lambda p, fi, rn: None)
        r = e.evolve("desc")
        assert r["status"] == "failed"
        assert r["reason"] == "Repair failed (validate)"

    def test_validate_fail_then_repair_recovers(self, tmp_path, monkeypatch):
        action_file = tmp_path / "actions" / "evo.t.actus.md"
        action_file.parent.mkdir()
        action_file.write_text(ACTION_MD, encoding="utf-8")
        e = self._engine(tmp_path)
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action",
                            lambda **kw: {"path": str(action_file), "id": "evo.t"})
        # round1 invalid → repair 成功改文件；round2 valid + test pass
        monkeypatch.setattr(e, "_phase_validate",
                            lambda p: ({"valid": False, "message": "bad", "errors": ["e"]}
                                       if len(e.history) < 2 else
                                       {"valid": True, "message": "ok", "errors": []}))
        def repair(p, fi, rn):
            with open(p, "w", encoding="utf-8") as f:
                f.write(ACTION_MD + "\n# fixed\n")
            return p
        monkeypatch.setattr(e, "_phase_repair", repair)
        monkeypatch.setattr(e, "_phase_test",
                            lambda p, exp: {"pass": True, "message": "ok"})
        r = e.evolve("desc")
        assert r["status"] == "ok"
        assert r["rounds"] == 2

    def test_max_rounds_reached(self, tmp_path, monkeypatch):
        action_file = tmp_path / "actions" / "evo.t.actus.md"
        action_file.parent.mkdir()
        action_file.write_text(ACTION_MD, encoding="utf-8")
        e = self._engine(tmp_path)
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action",
                            lambda **kw: {"path": str(action_file), "id": "evo.t"})
        monkeypatch.setattr(e, "_phase_validate",
                            lambda p: {"valid": True, "message": "ok", "errors": []})
        monkeypatch.setattr(e, "_phase_test",
                            lambda p, exp: {"pass": False, "message": "still bad"})
        monkeypatch.setattr(e, "_phase_repair",
                            lambda p, fi, rn: p)  # 修复但不变好
        r = e.evolve("desc")
        assert r["status"] == "failed"
        assert "Max rounds (5) reached" in r["reason"]
        assert r["rounds"] == 5

    def test_history_reset_between_runs(self, tmp_path, monkeypatch):
        """每次 evolve 清空 _history。"""
        action_file = tmp_path / "actions" / "evo.t.actus.md"
        action_file.parent.mkdir()
        action_file.write_text(ACTION_MD, encoding="utf-8")
        e = self._engine(tmp_path)
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action",
                            lambda **kw: {"path": "", "id": "evo.t"})
        r1 = e.evolve("desc")
        n1 = len(r1["history"])
        r2 = e.evolve("desc")
        assert len(r2["history"]) == n1  # 不叠加


class TestRepairEntry:
    """repair() 修复已有动作。"""

    def _mk_action(self, tmp_path):
        f = tmp_path / "actions" / "rep.t.actus.md"
        f.parent.mkdir()
        f.write_text(ACTION_MD, encoding="utf-8")
        return f

    def test_action_not_found(self, tmp_path, monkeypatch):
        e = EvolutionEngine(repo_root=str(tmp_path))
        monkeypatch.setattr(e, "_find_action_path", lambda aid: None)
        r = e.repair("nope")
        assert r == {"status": "error", "message": "Action not found: nope"}

    def test_repair_success(self, tmp_path, monkeypatch):
        f = self._mk_action(tmp_path)
        e = EvolutionEngine(repo_root=str(tmp_path))
        monkeypatch.setattr(e, "_find_action_path", lambda aid: str(f))
        monkeypatch.setattr(e, "_phase_validate",
                            lambda p: {"valid": True, "message": "ok", "errors": []})
        monkeypatch.setattr(e, "_phase_test",
                            lambda p, exp: {"pass": True, "message": "ok"})
        r = e.repair("rep.t")
        assert r["status"] == "ok"
        assert r["rounds"] == 1

    def test_repair_validate_fail_no_fix(self, tmp_path, monkeypatch):
        f = self._mk_action(tmp_path)
        e = EvolutionEngine(repo_root=str(tmp_path))
        monkeypatch.setattr(e, "_find_action_path", lambda aid: str(f))
        monkeypatch.setattr(e, "_phase_validate",
                            lambda p: {"valid": False, "message": "bad", "errors": ["e"]})
        monkeypatch.setattr(e, "_phase_repair", lambda p, fi, rn: None)
        r = e.repair("rep.t")
        assert r["status"] == "failed"
        assert r["reason"] == "Repair failed"

    def test_repair_max_rounds(self, tmp_path, monkeypatch):
        f = self._mk_action(tmp_path)
        e = EvolutionEngine(repo_root=str(tmp_path))
        monkeypatch.setattr(e, "_find_action_path", lambda aid: str(f))
        monkeypatch.setattr(e, "_phase_validate",
                            lambda p: {"valid": True, "message": "ok", "errors": []})
        monkeypatch.setattr(e, "_phase_test",
                            lambda p, exp: {"pass": False, "message": "bad"})
        monkeypatch.setattr(e, "_phase_repair", lambda p, fi, rn: p)
        r = e.repair("rep.t")
        assert r["status"] == "failed"
        assert r["reason"] == "Max rounds reached"


class TestPhaseGenerate:
    """_phase_generate。"""

    def test_returns_path_and_id(self, tmp_path, monkeypatch):
        f = tmp_path / "a.actus.md"
        f.write_text(ACTION_MD, encoding="utf-8")
        e = EvolutionEngine(repo_root=str(tmp_path))
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action",
                            lambda **kw: {"path": str(f), "id": "gen.t"})
        path, aid = e._phase_generate("desc")
        assert path == str(f)
        assert aid == "gen.t"

    def test_scaffold_missing_file(self, tmp_path, monkeypatch):
        e = EvolutionEngine(repo_root=str(tmp_path))
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action",
                            lambda **kw: {"path": str(tmp_path / "ghost.md"), "id": "g"})
        path, aid = e._phase_generate("desc")
        assert path is None

    def test_scaffold_no_path_key(self, tmp_path, monkeypatch):
        """无 path 键 → path None；scaffold 的 id 覆盖传入 action_id。"""
        e = EvolutionEngine(repo_root=str(tmp_path))
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action",
                            lambda **kw: {"id": "g"})
        path, aid = e._phase_generate("desc", action_id="given")
        assert path is None
        assert aid == "g"

    def test_scaffold_empty_result_falls_back_to_given_id(self, tmp_path, monkeypatch):
        """结果无 id 键 → 回退传入的 action_id。"""
        e = EvolutionEngine(repo_root=str(tmp_path))
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action",
                            lambda **kw: {})
        path, aid = e._phase_generate("desc", action_id="given")
        assert path is None
        assert aid == "given"


class TestPhaseValidate:
    """_phase_validate：走真实 parse + validate 入口。"""

    def test_valid_via_mocks(self, tmp_path, monkeypatch):
        import vools.actus.model as model_mod
        import vools.actus.validate as validate_mod
        e = EvolutionEngine(repo_root=str(tmp_path))
        monkeypatch.setattr(model_mod, "parse_cfg_from_file", lambda p: {"id": "x"})
        monkeypatch.setattr(validate_mod, "validate_action", lambda a: [])
        r = e._phase_validate(str(tmp_path / "a.md"))
        assert r == {"valid": True, "message": "Schema valid", "errors": []}

    def test_runtime_notes_become_warnings(self, tmp_path, monkeypatch):
        import vools.actus.model as model_mod
        import vools.actus.validate as validate_mod
        e = EvolutionEngine(repo_root=str(tmp_path))
        monkeypatch.setattr(model_mod, "parse_cfg_from_file", lambda p: {"id": "x"})
        monkeypatch.setattr(validate_mod, "validate_action", lambda a: ["runtime: no contracts"])
        monkeypatch.setattr(validate_mod, "split_validation",
                            lambda errs: ([], ["runtime: no contracts"]))
        r = e._phase_validate(str(tmp_path / "a.md"))
        assert r["valid"] is True
        assert r["warnings"] == ["runtime: no contracts"]

    def test_real_errors(self, tmp_path, monkeypatch):
        import vools.actus.model as model_mod
        import vools.actus.validate as validate_mod
        e = EvolutionEngine(repo_root=str(tmp_path))
        monkeypatch.setattr(model_mod, "parse_cfg_from_file", lambda p: {"id": "x"})
        monkeypatch.setattr(validate_mod, "validate_action", lambda a: ["E1"])
        monkeypatch.setattr(validate_mod, "split_validation", lambda errs: (["E1"], []))
        r = e._phase_validate(str(tmp_path / "a.md"))
        assert r["valid"] is False
        assert r["errors"] == ["E1"]

    def test_exception_returns_invalid(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        r = e._phase_validate(str(tmp_path / "ghost.md"))
        assert r["valid"] is False
        assert r["errors"]  # 异常文本透传


class TestPhaseTest:
    """_phase_test：preview 干跑。"""

    def _engine(self, tmp_path):
        return EvolutionEngine(repo_root=str(tmp_path))

    def test_awaiting_confirmation_passes(self, tmp_path, monkeypatch):
        import vools.actus.executor as exec_mod
        import vools.actus.model as model_mod
        e = self._engine(tmp_path)
        monkeypatch.setattr(model_mod, "parse_cfg_from_file",
                            lambda p: {"id": "x"})
        monkeypatch.setattr(exec_mod, "preview",
                            lambda aid, actions_dir: {"status": "awaiting_confirmation", "exec_id": "e"})
        r = e._phase_test(str(tmp_path / "a.md"), {})
        assert r["pass"] is True

    def test_preview_failed(self, tmp_path, monkeypatch):
        import vools.actus.executor as exec_mod
        import vools.actus.model as model_mod
        e = self._engine(tmp_path)
        monkeypatch.setattr(model_mod, "parse_cfg_from_file", lambda p: {"id": "x"})
        monkeypatch.setattr(exec_mod, "preview",
                            lambda aid, actions_dir: {"status": "failed",
                                                      "error": {"message": "boom"}})
        r = e._phase_test(str(tmp_path / "a.md"), {})
        assert r["pass"] is False
        assert "boom" in r["message"]

    def test_preview_ok(self, tmp_path, monkeypatch):
        import vools.actus.executor as exec_mod
        import vools.actus.model as model_mod
        e = self._engine(tmp_path)
        monkeypatch.setattr(model_mod, "parse_cfg_from_file", lambda p: {"id": "x"})
        monkeypatch.setattr(exec_mod, "preview",
                            lambda aid, actions_dir: {"status": "ok"})
        r = e._phase_test(str(tmp_path / "a.md"), {})
        assert r["pass"] is True
        assert r["message"] == "Preview ok"

    def test_preview_exception(self, tmp_path, monkeypatch):
        import vools.actus.executor as exec_mod
        import vools.actus.model as model_mod
        e = self._engine(tmp_path)
        monkeypatch.setattr(model_mod, "parse_cfg_from_file", lambda p: {"id": "x"})
        def boom(aid, actions_dir):
            raise ValueError("nope")
        monkeypatch.setattr(exec_mod, "preview", boom)
        r = e._phase_test(str(tmp_path / "a.md"), {})
        assert r["pass"] is False
        assert "Test error" in r["message"]


class TestPhaseRepairStrategies:
    """_phase_repair 与 4 级修复策略。"""

    def test_round_beyond_max_returns_none(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        assert e._phase_repair("whatever", {}, 5) is None

    def test_missing_file_returns_none(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        assert e._phase_repair(str(tmp_path / "ghost.md"), {}, 1) is None

    def _write(self, tmp_path, body="print('hi')"):
        f = tmp_path / "a.actus.md"
        f.write_text(ACTION_MD.replace("print(\"ok\")", body), encoding="utf-8")
        return f

    def test_round1_simple_writes_back(self, tmp_path):
        f = self._write(tmp_path)
        e = EvolutionEngine(repo_root=str(tmp_path))
        msg = "ModuleNotFoundError: No module named 'requests'"
        out = e._phase_repair(str(f), {"message": msg}, 1)
        assert out == str(f)
        content = f.read_text(encoding="utf-8")
        assert "import requests" in content
        assert "# auto-repaired" in content

    def test_round1_simple_no_change_returns_none(self, tmp_path):
        """消息不含已知错误模式 → 修复无变化 → None。"""
        f = self._write(tmp_path)
        e = EvolutionEngine(repo_root=str(tmp_path))
        assert e._phase_repair(str(f), {"message": "mystery"}, 1) is None

    def test_round1_syntax_repair(self, tmp_path):
        f = self._write(tmp_path, body="def broken(:")
        e = EvolutionEngine(repo_root=str(tmp_path))
        e._phase_repair(str(f), {"message": "SyntaxError: invalid syntax"}, 1)
        content = f.read_text(encoding="utf-8")
        assert "# syntax error auto-repaired" in content
        assert "pass" in content

    def test_round2_context_adds_imports(self, tmp_path):
        f = self._write(tmp_path, body="x = 1")
        e = EvolutionEngine(repo_root=str(tmp_path))
        out = e._phase_repair(str(f), {"message": "bad"}, 2)
        assert out == str(f)
        content = f.read_text(encoding="utf-8")
        assert "import os" in content
        assert "import sys" in content

    def test_round2_context_no_duplicates(self, tmp_path):
        f = self._write(tmp_path, body="import os\nimport sys\nx = 1")
        e = EvolutionEngine(repo_root=str(tmp_path))
        e._phase_repair(str(f), {"message": "bad"}, 2)
        content = f.read_text(encoding="utf-8")
        assert content.count("import os") == 1

    def test_round3_restructure(self, tmp_path):
        f = self._write(tmp_path, body="complex_stuff()")
        e = EvolutionEngine(repo_root=str(tmp_path))
        e._phase_repair(str(f), {"message": "bad"}, 3)
        content = f.read_text(encoding="utf-8")
        assert "simplified implementation" in content
        assert 'print("ok")' in content

    def test_round4_degrade(self, tmp_path):
        f = self._write(tmp_path, body="complex_stuff()")
        e = EvolutionEngine(repo_root=str(tmp_path))
        e._phase_repair(str(f), {"message": "bad"}, 4)
        content = f.read_text(encoding="utf-8")
        assert "degraded execution" in content
        assert "sys.exit(1)" in content

    def test_round1_syntax_takes_precedence_over_missing_module(self, tmp_path):
        """两种模式都命中时：先模块注入再语法替换（顺序行为固化）。"""
        f = self._write(tmp_path, body="def broken(:")
        e = EvolutionEngine(repo_root=str(tmp_path))
        msg = "ModuleNotFoundError: No module named 'os'\nSyntaxError: bad"
        e._phase_repair(str(f), {"message": msg}, 1)
        content = f.read_text(encoding="utf-8")
        assert "# syntax error auto-repaired" in content


class TestCheckExpectations:
    """_check_expectations：preview 不执行 → 契约退化为恒过。"""

    def test_always_passes(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        ok, msg = e._check_expectations({}, {"exit_code": 0, "stdout_contains": "x"})
        assert ok is True
        assert msg == "Expectations met"


class TestHistoryAndSnapshots:
    """_record / _save_version_snapshot / get_history。"""

    def test_record_appends(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        e._record(1, "test", "pass", "a", "m", {"k": 1})
        e._record(2, "test", "fail", "a", "m2")
        assert len(e.history) == 2
        assert e.history[0].details == {"k": 1}
        assert e.history[1].details == {}

    def test_snapshot_disabled(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path),
                            config=EvolutionConfig(keep_history=False))
        f = tmp_path / "a.actus.md"
        f.write_text("x", encoding="utf-8")
        e._save_version_snapshot("aid", str(f), 1)
        assert not os.path.isdir(e._evolution_dir)

    def test_snapshot_copies_and_info(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        f = tmp_path / "a.actus.md"
        f.write_text("content-v1", encoding="utf-8")
        e._save_version_snapshot("aid", str(f), 2)
        vdir = Path(e._evolution_dir) / "aid" / "v2"
        assert (vdir / "a.actus.md").read_text(encoding="utf-8") == "content-v1"
        info = json.loads((vdir / "info.json").read_text(encoding="utf-8"))
        assert info["round"] == 2
        assert info["action_id"] == "aid"

    def test_get_history_no_dir(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        assert e.get_history("aid") == []

    def test_get_history_no_file(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        os.makedirs(Path(e._evolution_dir) / "aid")
        assert e.get_history("aid") == []

    def test_get_history_reads_jsonl(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        d = Path(e._evolution_dir) / "aid"
        d.mkdir(parents=True)
        (d / "history.jsonl").write_text(
            '{"round": 1, "phase": "test"}\n\n{"round": 2, "phase": "promote"}\n',
            encoding="utf-8")
        h = e.get_history("aid")
        assert len(h) == 2
        assert h[1]["phase"] == "promote"


class TestRollback:
    """rollback。"""

    def _engine_with_snapshot(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        vdir = Path(e._evolution_dir) / "aid" / "v1"
        vdir.mkdir(parents=True)
        (vdir / "aid.actus.md").write_text("old-content", encoding="utf-8")
        return e

    def test_version_not_found(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        r = e.rollback("aid", 9)
        assert r["status"] == "error"
        assert "Version 9 not found" in r["message"]

    def test_no_snapshot_file(self, tmp_path):
        e = self._engine_with_snapshot(tmp_path)
        (Path(e._evolution_dir) / "aid" / "v1" / "aid.actus.md").unlink()
        r = e.rollback("aid", 1)
        assert r == {"status": "error", "message": "No snapshot found"}

    def test_current_action_missing(self, tmp_path, monkeypatch):
        e = self._engine_with_snapshot(tmp_path)
        monkeypatch.setattr(e, "_find_action_path", lambda aid: None)
        r = e.rollback("aid", 1)
        assert r["status"] == "error"
        assert "Current action not found" in r["message"]

    def test_rollback_success_but_id_literal_bug(self, tmp_path, monkeypatch):
        """契约现状：成功回滚返回 action_id 字面量（evolution.py:516 的 BUG）。

        正确行为应是 action_id 变量值；此断言固化现状，修 BUG 后改这里。
        """
        e = self._engine_with_snapshot(tmp_path)
        target = tmp_path / "actions" / "aid.actus.md"
        target.parent.mkdir()
        target.write_text("current-content", encoding="utf-8")
        monkeypatch.setattr(e, "_find_action_path", lambda aid: str(target))
        r = e.rollback("aid", 1)
        assert r["status"] == "ok"
        assert target.read_text(encoding="utf-8") == "old-content"
        # BUG 佐证：字面量 "action_id" 而非 "aid"
        assert r["action_id"] == "action_id"


class TestCompareVersions:
    """compare_versions 行级 diff。"""

    def _mk_versions(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        v1 = Path(e._evolution_dir) / "aid" / "v1"
        v2 = Path(e._evolution_dir) / "aid" / "v2"
        v1.mkdir(parents=True)
        v2.mkdir(parents=True)
        (v1 / "aid.actus.md").write_text("a\nb\nc\n", encoding="utf-8")
        (v2 / "aid.actus.md").write_text("a\nX\nc\nd\n", encoding="utf-8")
        return e

    def test_version_not_found(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        r = e.compare_versions("aid", 1, 2)
        assert r == {"status": "error", "message": "Version not found"}

    def test_snapshot_missing(self, tmp_path):
        e = self._mk_versions(tmp_path)
        (Path(e._evolution_dir) / "aid" / "v2" / "aid.actus.md").unlink()
        r = e.compare_versions("aid", 1, 2)
        assert r == {"status": "error", "message": "Snapshot not found"}

    def test_diff_lines(self, tmp_path):
        e = self._mk_versions(tmp_path)
        r = e.compare_versions("aid", 1, 2)
        assert r["status"] == "ok"
        assert r["diff_count"] == 2  # line2 b→X、line4 None→d；line3 c==c 不算
        changed = {(d["line"], d["v1"], d["v2"]) for d in r["diff"]}
        assert (2, "b", "X") in changed
        assert (4, None, "d") in changed

    def test_identical_versions(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        v1 = Path(e._evolution_dir) / "aid" / "v1"
        v2 = Path(e._evolution_dir) / "aid" / "v2"
        v1.mkdir(parents=True)
        v2.mkdir(parents=True)
        (v1 / "a.actus.md").write_text("same\n", encoding="utf-8")
        (v2 / "a.actus.md").write_text("same\n", encoding="utf-8")
        r = e.compare_versions("aid", 1, 2)
        assert r["diff_count"] == 0
        assert r["diff"] == []


class TestFindActionPath:
    """_find_action_path 三层查找。"""

    def test_installer_hit(self, tmp_path, monkeypatch):
        import vools.actus.installer as inst_mod
        class FakeInstaller:
            def resolve_action_path(self, aid):
                return "/fake/path.md"
        monkeypatch.setattr(inst_mod, "ActionInstaller", FakeInstaller)
        e = EvolutionEngine(repo_root=str(tmp_path))
        assert e._find_action_path("aid") == "/fake/path.md"

    def test_installer_raises_falls_to_resolver(self, tmp_path, monkeypatch):
        import vools.actus.installer as inst_mod
        import vools.actus.resolver as res_mod
        class BoomInstaller:
            def __init__(self):
                raise RuntimeError("no installer")
        monkeypatch.setattr(inst_mod, "ActionInstaller", BoomInstaller)
        monkeypatch.setattr(res_mod, "find_action_file",
                            lambda aid, d: str(tmp_path / "found.md"))
        e = EvolutionEngine(repo_root=str(tmp_path))
        assert e._find_action_path("aid") == str(tmp_path / "found.md")

    def test_both_fail_returns_none(self, tmp_path, monkeypatch):
        import vools.actus.installer as inst_mod
        class BoomInstaller:
            def __init__(self):
                raise RuntimeError("no installer")
        monkeypatch.setattr(inst_mod, "ActionInstaller", BoomInstaller)
        e = EvolutionEngine(repo_root=str(tmp_path))
        # actions/ 目录不存在 → resolver 抛或返回 None
        assert e._find_action_path("ghost") in (None,)


class TestListAndStatus:
    """list_evolved_actions / get_status。"""

    def test_list_no_dir(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        assert e.list_evolved_actions() == []

    def test_lists_dirs_only(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        d = Path(e._evolution_dir)
        (d / "a").mkdir(parents=True)
        (d / "b").mkdir()
        (d / "loose.txt").write_text("x", encoding="utf-8")
        assert sorted(e.list_evolved_actions()) == ["a", "b"]

    def test_status_not_found(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        assert e.get_status("ghost") == {"status": "not_found", "action_id": "ghost"}

    def test_status_ok_with_versions(self, tmp_path):
        e = EvolutionEngine(repo_root=str(tmp_path))
        d = Path(e._evolution_dir) / "aid"
        (d / "v1").mkdir(parents=True)
        (d / "v2").mkdir()
        (d / "history.jsonl").write_text(
            '{"phase": "promote", "status": "pass"}\n', encoding="utf-8")
        s = e.get_status("aid")
        assert s["status"] == "ok"
        assert s["total_rounds"] == 1
        assert s["last_phase"] == "promote"
        assert s["versions"] == ["v1", "v2"]


class TestConvenienceFunctions:
    """模块级便捷函数。"""

    def test_evolve_action(self, tmp_path, monkeypatch):
        monkeypatch.setattr("vools.actus.scaffold.scaffold_action",
                            lambda **kw: {"path": "", "id": "x"})
        r = evolve_action("desc", repo_root=str(tmp_path))
        assert r["status"] == "failed"

    def test_repair_action_not_found(self, tmp_path):
        r = repair_action("ghost", repo_root=str(tmp_path))
        assert r["status"] == "error"

    def test_get_evolution_status(self, tmp_path):
        r = get_evolution_status("ghost", repo_root=str(tmp_path))
        assert r == {"status": "not_found", "action_id": "ghost"}

    def test_rollback_action(self, tmp_path):
        r = rollback_action("ghost", 1, repo_root=str(tmp_path))
        assert r["status"] == "error"

    def test_compare_action_versions(self, tmp_path):
        r = compare_action_versions("ghost", 1, 2, repo_root=str(tmp_path))
        assert r["status"] == "error"


class TestModuleExports:
    def test_all(self):
        assert evo_mod.__all__ == [
            'EvolutionConfig', 'EvolutionEngine', 'EvolutionRecord',
            'compare_action_versions', 'evolve_action', 'get_evolution_status',
            'repair_action', 'rollback_action',
        ]
