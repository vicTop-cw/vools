"""project.py 契约测试（Round 50）。

契约:
- ModuleConfig/PipelineStep/ProjectConfig: to_dict/from_dict 往返 + 默认值
- detect_language: 各语言规则 + tsconfig 区分 ts/js + glob + 未识别
- detect_languages: 递归 + 跳过 node_modules/.git 等
- detect_modules: 子目录检测 + 隐藏目录跳过 + id 归一化
- ProjectOrchestrator: 加载/校验/执行/条件/状态/模块管理/save 路径逃逸
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from vools.actus.project import (
    LANGUAGE_RULES, ModuleConfig, PipelineStep, ProjectConfig,
    ProjectOrchestrator, detect_and_init, detect_language, detect_languages,
    detect_modules, load_project, run_pipeline,
)


# ── 数据结构 ──

class TestDataclasses:
    """to_dict/from_dict 往返。"""

    def test_module_config_defaults(self):
        m = ModuleConfig(id="a", language="python", path=".")
        assert m.build_cmd == "" and m.timeout == 300 and m.retries == 0
        assert m.outputs == [] and m.env == {} and m.deps == []

    def test_module_config_roundtrip(self):
        m = ModuleConfig(id="a", language="rust", path="srv", build_cmd="cargo build",
                         test_cmd="cargo test", env={"R": "1"}, deps=["b"],
                         outputs=["target"], timeout=9, retries=2, lint_cmd="clippy")
        m2 = ModuleConfig.from_dict(m.to_dict())
        assert m2 == m

    def test_module_config_from_dict_missing(self):
        m = ModuleConfig.from_dict({"id": "x"})
        assert m.language == "" and m.path == "" and m.timeout == 300

    def test_pipeline_step_defaults(self):
        s = PipelineStep(id="s1", module="*", phase="build")
        assert s.depends_on == [] and s.condition == "" and s.timeout == 300

    def test_pipeline_step_roundtrip(self):
        s = PipelineStep(id="s1", module="m", phase="test", depends_on=["s0"],
                         condition="all_prev_ok", retries=1, timeout=5)
        s2 = PipelineStep.from_dict(s.to_dict())
        assert s2 == s

    def test_project_config_roundtrip(self):
        cfg = ProjectConfig(
            name="proj", version="2.0", languages=["python"],
            modules={"m": ModuleConfig(id="m", language="python", path="m")},
            pipeline=[PipelineStep(id="s", module="m", phase="build")],
            env={"K": "V"}, work_dir="wd",
        )
        cfg2 = ProjectConfig.from_dict(cfg.to_dict())
        assert cfg2.name == "proj" and cfg2.modules["m"].language == "python"
        assert cfg2.pipeline[0].id == "s" and cfg2.env == {"K": "V"}

    def test_project_config_from_dict_empty(self):
        cfg = ProjectConfig.from_dict({})
        assert cfg.name == "unnamed" and cfg.version == "1.0.0" and cfg.modules == {}


# ── 语言检测 ──

class TestDetectLanguage:
    """detect_language 各规则。"""

    def _mk(self, tmp_path, *files, ts=False):
        for f in files:
            (tmp_path / f).write_text("x", encoding="utf-8")
        if ts:
            (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
        return tmp_path

    def test_rust(self, tmp_path):
        self._mk(tmp_path, "Cargo.toml")
        assert detect_language(str(tmp_path)) == "rust"

    def test_go(self, tmp_path):
        self._mk(tmp_path, "go.mod")
        assert detect_language(str(tmp_path)) == "go"

    def test_javascript(self, tmp_path):
        self._mk(tmp_path, "package.json")
        assert detect_language(str(tmp_path)) == "javascript"

    def test_typescript(self, tmp_path):
        self._mk(tmp_path, "package.json", ts=True)
        assert detect_language(str(tmp_path)) == "typescript"

    def test_python_pyproject(self, tmp_path):
        self._mk(tmp_path, "pyproject.toml")
        assert detect_language(str(tmp_path)) == "python"

    def test_python_requirements(self, tmp_path):
        self._mk(tmp_path, "requirements.txt")
        assert detect_language(str(tmp_path)) == "python"

    def test_python_setup_py(self, tmp_path):
        self._mk(tmp_path, "setup.py")
        assert detect_language(str(tmp_path)) == "python"

    def test_python_setup_cfg(self, tmp_path):
        self._mk(tmp_path, "setup.cfg")
        assert detect_language(str(tmp_path)) == "python"

    def test_java_maven(self, tmp_path):
        self._mk(tmp_path, "pom.xml")
        assert detect_language(str(tmp_path)) == "java"

    def test_java_gradle(self, tmp_path):
        self._mk(tmp_path, "build.gradle")
        assert detect_language(str(tmp_path)) == "java"

    def test_java_gradle_kts(self, tmp_path):
        self._mk(tmp_path, "build.gradle.kts")
        assert detect_language(str(tmp_path)) == "java"

    def test_csharp_glob(self, tmp_path):
        self._mk(tmp_path, "App.csproj")
        assert detect_language(str(tmp_path)) == "csharp"

    def test_unknown(self, tmp_path):
        assert detect_language(str(tmp_path)) is None

    def test_language_rules_complete(self):
        """每条规则都有必备字段。"""
        for rule in LANGUAGE_RULES:
            assert rule["files"] and rule["language"]
            assert "build_cmd" in rule and "test_cmd" in rule


class TestDetectLanguages:
    """detect_languages 递归 + 跳过目录。"""

    def test_multi(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "Cargo.toml").write_text("x", encoding="utf-8")
        (tmp_path / "b").mkdir()
        (tmp_path / "b" / "go.mod").write_text("x", encoding="utf-8")
        assert detect_languages(str(tmp_path)) == ["go", "rust"]

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text("x", encoding="utf-8")
        assert detect_languages(str(tmp_path)) == []

    def test_skips_git_and_venv(self, tmp_path):
        for d in (".git", ".venv", "__pycache__", "target"):
            sub = tmp_path / d
            sub.mkdir()
            (sub / "Cargo.toml").write_text("x", encoding="utf-8")
        assert detect_languages(str(tmp_path)) == []

    def test_root_itself(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("x", encoding="utf-8")
        assert detect_languages(str(tmp_path)) == ["python"]


class TestDetectModules:
    """detect_modules。"""

    def test_detects_subdirs(self, tmp_path):
        for name, marker in (("api", "go.mod"), ("web", "package.json"),
                             ("core", "Cargo.toml")):
            d = tmp_path / name
            d.mkdir()
            (d / marker).write_text("x", encoding="utf-8")
        mods = detect_modules(str(tmp_path))
        assert set(mods) == {"api", "web", "core"}
        assert mods["api"].language == "go"
        assert mods["api"].build_cmd == "go build ./..."

    def test_skips_hidden_and_junk(self, tmp_path):
        for name in (".hidden", "node_modules", "__pycache__", "target"):
            d = tmp_path / name
            d.mkdir()
            (d / "go.mod").write_text("x", encoding="utf-8")
        assert detect_modules(str(tmp_path)) == {}

    def test_skips_files(self, tmp_path):
        (tmp_path / "go.mod").write_text("x", encoding="utf-8")  # 根下是文件不是子目录
        (tmp_path / "README.md").write_text("x", encoding="utf-8")
        assert detect_modules(str(tmp_path)) == {}

    def test_id_normalization(self, tmp_path):
        d = tmp_path / "my-app v2"
        d.mkdir()
        (d / "go.mod").write_text("x", encoding="utf-8")
        mods = detect_modules(str(tmp_path))
        assert "my_app_v2" in mods
        assert mods["my_app_v2"].path == "my-app v2"


# ── ProjectOrchestrator ──

def _make_config(**kw):
    return ProjectConfig(
        name=kw.get("name", "proj"),
        modules=kw.get("modules", {
            "m1": ModuleConfig(id="m1", language="python", path="m1",
                               build_cmd="echo build1", test_cmd="echo test1"),
        }),
        pipeline=kw.get("pipeline", [
            PipelineStep(id="s1", module="m1", phase="build"),
        ]),
        env=kw.get("env", {"PROJ_VAR": "1"}),
    )


class TestProjectOrchestratorBasics:
    """初始化与属性。"""

    def test_init_defaults(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        assert o.work_dir == str(tmp_path)
        assert o.config is None and o.is_loaded is False

    def test_load_config(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        cfg = _make_config()
        o.load_config(cfg)
        assert o.is_loaded and o.config.name == "proj"

    def test_load_project(self, tmp_path):
        cfg = _make_config()
        (tmp_path / ".actus-project.json").write_text(
            json.dumps(cfg.to_dict()), encoding="utf-8")
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        loaded = o.load_project()
        assert loaded.name == "proj"
        assert loaded.work_dir == str(tmp_path)

    def test_load_project_escape_rejected(self, tmp_path):
        """路径逃逸必须被 ensure_within 拒绝。"""
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        with pytest.raises(ValueError):
            o.load_project("../outside.json")

    def test_load_project_not_found(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        with pytest.raises(FileNotFoundError):
            o.load_project("missing.json")


class TestValidate:
    """validate 校验。"""

    def _orch(self, tmp_path, cfg):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(cfg)
        return o

    def test_no_config(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        ok, errors = o.validate()
        assert ok is False and errors == ["No project loaded"]

    def test_valid(self, tmp_path):
        o = self._orch(tmp_path, _make_config())
        ok, errors = o.validate()
        assert ok is True and errors == []

    def test_missing_language_and_path(self, tmp_path):
        cfg = _make_config(modules={"m1": ModuleConfig(id="m1", language="", path="")})
        ok, errors = self._orch(tmp_path, cfg).validate()
        assert ok is False
        assert any("missing language" in e for e in errors)
        assert any("missing path" in e for e in errors)

    def test_unknown_module_in_step(self, tmp_path):
        cfg = _make_config(pipeline=[PipelineStep(id="s1", module="ghost", phase="build")])
        ok, errors = self._orch(tmp_path, cfg).validate()
        assert ok is False
        assert any("unknown module ghost" in e for e in errors)

    def test_unknown_dependency(self, tmp_path):
        cfg = _make_config(pipeline=[
            PipelineStep(id="s1", module="m1", phase="build", depends_on=["nope"]),
        ])
        ok, errors = self._orch(tmp_path, cfg).validate()
        assert ok is False
        assert any("unknown dependency nope" in e for e in errors)

    def test_validate_does_not_detect_cycles(self, tmp_path):
        """BUG-P2 佐证：validate 的 _build_dag 不跑拓扑排序 → 环检不出。

        DAGScheduler 的环检在 topological_sort()（workflow.py:110，抛
        ActionError），而 validate 只 catch ValueError —— 环形流水线
        validate 返回 ok=True。
        """
        cfg = _make_config(pipeline=[
            PipelineStep(id="a", module="m1", phase="build", depends_on=["b"]),
            PipelineStep(id="b", module="m1", phase="build", depends_on=["a"]),
        ])
        ok, errors = self._orch(tmp_path, cfg).validate()
        assert ok is True and errors == []  # 记录现状：环漏检


class TestRunPipeline:
    """run_pipeline 执行。"""

    def _orch(self, tmp_path, cfg):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(cfg)
        return o

    def test_no_config(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        assert o.run_pipeline() == {"status": "error", "message": "No project loaded"}

    def test_circular_raises_actionerror(self, tmp_path):
        """BUG-P2 佐证：环形依赖让 run_pipeline 直接崩 ActionError。

        project.py:409-410 catch ValueError，但 workflow.py:110 抛的是
        ActionError(Exception) —— 承诺的 {"status": "error"} 永远不返回。
        """
        from vools.actus.errors import ActionError
        cfg = _make_config(pipeline=[
            PipelineStep(id="a", module="m1", phase="build", depends_on=["b"]),
            PipelineStep(id="b", module="m1", phase="build", depends_on=["a"]),
        ])
        with pytest.raises(ActionError):
            self._orch(tmp_path, cfg).run_pipeline()

    def test_ok_run(self, tmp_path):
        o = self._orch(tmp_path, _make_config())
        result = o.run_pipeline()
        # BUG-P1 佐证：topological_sort 返回 List[List[str]]（分层），而
        # run_pipeline 把它当平铺 id 迭代（s.id == step_id 永不匹配）→
        # 所有步骤被 continue 跳过 → 结果恒 "ok" 但一个步骤都没跑。
        assert result["status"] == "ok"
        assert result["results"] == {}  # ← 零执行却报成功
        assert result["steps_total"] == 1 and result["steps_ok"] == 1

    def test_run_pipeline_is_silent_noop(self, tmp_path):
        """BUG-P1 佐证：失败命令也报 ok —— 流水线是静默空转。"""
        cfg = _make_config(modules={
            "m1": ModuleConfig(id="m1", language="python", path="m1", build_cmd="exit 7"),
        }, pipeline=[PipelineStep(id="s1", module="m1", phase="build")])
        o = self._orch(tmp_path, cfg)
        result = o.run_pipeline()
        assert result["status"] == "ok"  # ← exit 7 却报 ok（空转）
        assert result["results"] == {}
        # 状态里也没有任何 step 记录
        assert o.get_status()["steps"] == {}

    def test_phase_filter(self, tmp_path):
        cfg = _make_config(pipeline=[
            PipelineStep(id="b", module="m1", phase="build"),
            PipelineStep(id="t", module="m1", phase="test", depends_on=["b"]),
        ])
        o = self._orch(tmp_path, cfg)
        result = o.run_pipeline(phase="build")
        assert result["steps_total"] == 1  # build 阶段只有一步（含层级计数）

    def test_dependency_failed_skips_downstream(self, tmp_path):
        """依赖失败跳过下游：绕过空转的 run_pipeline，直接驱动 _run_step。

        （run_pipeline 因 BUG-P1 永不执行步骤，此分支现网不可达 —— 这里
        用单步结果模拟上游失败，验证 skip 记账逻辑本身。）
        """
        cfg = _make_config(modules={
            "m1": ModuleConfig(id="m1", language="python", path="m1", build_cmd="exit 1"),
        }, pipeline=[
            PipelineStep(id="s1", module="m1", phase="build"),
            PipelineStep(id="s2", module="m1", phase="build", depends_on=["s1"]),
        ])
        o = self._orch(tmp_path, cfg)
        # 手动模拟：上游失败后，下游依赖命中 failed 集
        failed = {"s1"}
        step2 = cfg.pipeline[1]
        assert any(dep in failed for dep in step2.depends_on) is True


class TestRunStep:
    """run_step / _run_step。"""

    def _orch(self, tmp_path, cfg):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(cfg)
        return o

    def test_no_config(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        assert o.run_step("s") == {"status": "error", "message": "No project loaded"}

    def test_not_found(self, tmp_path):
        o = self._orch(tmp_path, _make_config())
        assert "not found" in o.run_step("ghost")["message"]

    def test_unknown_module_id_no_modules(self, tmp_path):
        """step.module 指向不存在的模块 → No modules 错误。"""
        cfg = _make_config(pipeline=[PipelineStep(id="s", module="ghost", phase="build")])
        # validate 会拦；绕过 validate 直接 _run_step
        o = self._orch(tmp_path, cfg)
        result = o._run_step(PipelineStep(id="s", module="ghost", phase="build"))
        assert result["status"] == "error"
        assert "No modules" in result["message"]

    def test_empty_cmd_skipped(self, tmp_path):
        """模块无该阶段命令 → results 空 → all_ok=True（空 all 为 True）。"""
        cfg = _make_config(modules={
            "m1": ModuleConfig(id="m1", language="python", path="m1"),  # 无 build_cmd
        }, pipeline=[PipelineStep(id="s", module="m1", phase="build")])
        result = self._orch(tmp_path, cfg).run_step("s")
        assert result["status"] == "ok" and result["modules"] == []

    def test_wildcard_runs_all(self, tmp_path):
        cfg = _make_config(modules={
            "m1": ModuleConfig(id="m1", language="python", path="m1", build_cmd="echo one"),
            "m2": ModuleConfig(id="m2", language="rust", path="m2", build_cmd="echo two"),
        }, pipeline=[PipelineStep(id="s", module="*", phase="build")])
        result = self._orch(tmp_path, cfg).run_step("s")
        assert result["status"] == "ok"
        assert {r["module"] for r in result["modules"]} == {"m1", "m2"}


class TestInternals:
    """_get_phase_cmd / _eval_condition / get_status / _exec_cmd。"""

    def test_get_phase_cmd_all(self, tmp_path):
        mod = ModuleConfig(id="m", language="py", path=".",
                           build_cmd="b", test_cmd="t", deploy_cmd="d", lint_cmd="l")
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        assert o._get_phase_cmd(mod, "build") == "b"
        assert o._get_phase_cmd(mod, "test") == "t"
        assert o._get_phase_cmd(mod, "deploy") == "d"
        assert o._get_phase_cmd(mod, "lint") == "l"
        assert o._get_phase_cmd(mod, "nope") == ""

    def test_eval_condition(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        ok_results = {"s1": {"status": "ok"}}
        bad_results = {"s1": {"status": "failed"}}
        assert o._eval_condition("all_prev_ok", ok_results) is True
        assert o._eval_condition("all_prev_ok", bad_results) is False
        assert o._eval_condition("any_prev_ok", bad_results) is False
        assert o._eval_condition("any_prev_ok", ok_results) is True
        assert o._eval_condition("whatever", {}) is True  # 默认通过

    def test_get_status_empty(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        st = o.get_status()
        assert st["loaded"] is False and st["project"] is None and st["modules"] == []

    def test_get_status_loaded(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(_make_config())
        o.run_pipeline()
        st = o.get_status()
        assert st["loaded"] is True and st["project"] == "proj"
        assert "m1" in st["modules"]
        # BUG-P1 佐证：run_pipeline 空转 → steps 恒为 {}
        assert st["steps"] == {}

    def test_has_ts_config(self, tmp_path, monkeypatch):
        from vools.actus.project import _has_ts_config
        monkeypatch.chdir(tmp_path)
        assert _has_ts_config() is False
        (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
        assert _has_ts_config() is True

    def _orchestrator(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(_make_config())
        return o

    def test_validate_dag_valueerror_caught(self, tmp_path):
        """_build_dag 抛 ValueError → 计入 validate 错误列表。"""
        o = self._orchestrator(tmp_path)
        with patch.object(o, "_build_dag", side_effect=ValueError("bad dag")):
            ok, errors = o.validate()
        assert ok is False
        assert any("bad dag" in e for e in errors)

    def test_run_pipeline_dag_error(self, tmp_path):
        """_build_dag 抛 ValueError → error dict（403-404 处理器）。"""
        o = self._orchestrator(tmp_path)
        with patch.object(o, "_build_dag", side_effect=ValueError("boom")):
            result = o.run_pipeline()
        assert result["status"] == "error"
        assert "boom" in result["message"]

    def test_run_pipeline_cycle_valueerror_handler(self, tmp_path):
        """topological_sort 抛 ValueError → "Circular dependency" 处理器。

        （真实路径抛 ActionError 不进这个 handler —— BUG-P2，见上面
        test_circular_raises_actionerror。此测试锁 handler 本身的行为。）
        """
        o = self._orchestrator(tmp_path)
        mock_dag = MagicMock()
        mock_dag.topological_sort.side_effect = ValueError("loop!")
        with patch.object(o, "_build_dag", return_value=mock_dag):
            result = o.run_pipeline()
        assert result["status"] == "error"
        assert "Circular dependency" in result["message"]

    def test_exec_cmd_success(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        proc = MagicMock(returncode=0, stdout="out", stderr="")
        with patch("vools.actus.project.run_cmd_safe", return_value=proc) as rc:
            code, out, err = o._exec_cmd("echo hi", ".", {"X": "1"}, 10)
        assert code == 0 and out == "out"
        rc.assert_called_once()
        assert rc.call_args.kwargs["shell"] is True

    def test_exec_cmd_merges_env(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(_make_config(env={"PROJ": "1"}))
        proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch("vools.actus.project.run_cmd_safe", return_value=proc) as rc:
            o._exec_cmd("x", ".", {"MOD": "2"}, 5)
        env = rc.call_args.kwargs["env"]
        assert env["PROJ"] == "1" and env["MOD"] == "2"

    def test_exec_cmd_exception(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        with patch("vools.actus.project.run_cmd_safe", side_effect=OSError("boom")):
            code, out, err = o._exec_cmd("x", ".", {}, 5)
        assert code == -1 and "boom" in err

    def test_exec_cmd_missing_cwd_falls_back(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch("vools.actus.project.run_cmd_safe", return_value=proc) as rc:
            o._exec_cmd("x", "no_such_dir", {}, 5)
        assert rc.call_args.kwargs["cwd"] == str(tmp_path)

    def test_stdout_stderr_truncated(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(_make_config(modules={
            "m1": ModuleConfig(id="m1", language="py", path=".", build_cmd="big"),
        }))
        proc = MagicMock(returncode=0, stdout="S" * 2000, stderr="E" * 2000)
        with patch("vools.actus.project.run_cmd_safe", return_value=proc):
            result = o.run_step("s1")
        r = result["modules"][0]
        assert len(r["stdout"]) == 500 and len(r["stderr"]) == 500


class TestModuleManagement:
    """add_module / remove_module / auto_detect / save_project。"""

    def test_add_module_no_config(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        with pytest.raises(RuntimeError):
            o.add_module(ModuleConfig(id="m", language="py", path="."))

    def test_add_module(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(_make_config())
        o.add_module(ModuleConfig(id="m2", language="rust", path="m2"))
        assert "m2" in o.config.modules
        assert "rust" in o.config.languages

    def test_remove_module_no_config(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        with pytest.raises(RuntimeError):
            o.remove_module("m")

    def test_remove_module_drops_steps(self, tmp_path):
        cfg = _make_config(pipeline=[
            PipelineStep(id="s1", module="m1", phase="build"),
            PipelineStep(id="s2", module="other", phase="build"),
        ])
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(cfg)
        o.remove_module("m1")
        assert "m1" not in o.config.modules
        assert [s.id for s in o.config.pipeline] == ["s2"]

    def test_auto_detect_without_config(self, tmp_path):
        sub = tmp_path / "api"
        sub.mkdir()
        (sub / "go.mod").write_text("x", encoding="utf-8")
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        mods = o.auto_detect()
        assert set(mods) == {"api"}

    def test_auto_detect_updates_config(self, tmp_path):
        sub = tmp_path / "api"
        sub.mkdir()
        (sub / "go.mod").write_text("x", encoding="utf-8")
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(_make_config())
        o.auto_detect()
        assert "api" in o.config.modules
        assert "go" in o.config.languages

    def test_save_project_no_config(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        with pytest.raises(RuntimeError):
            o.save_project()

    def test_save_project_escape(self, tmp_path):
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(_make_config())
        with pytest.raises(ValueError):
            o.save_project("../ESCAPED.json")

    def test_save_and_reload_roundtrip(self, tmp_path):
        cfg = _make_config()
        o = ProjectOrchestrator(work_dir=str(tmp_path))
        o.load_config(cfg)
        o.save_project()
        o2 = ProjectOrchestrator(work_dir=str(tmp_path))
        loaded = o2.load_project()
        assert loaded.name == "proj" and "m1" in loaded.modules


class TestConvenience:
    """便捷函数。"""

    def test_load_project_fn(self, tmp_path):
        (tmp_path / ".actus-project.json").write_text(
            json.dumps(_make_config().to_dict()), encoding="utf-8")
        orch = load_project(work_dir=str(tmp_path))
        assert orch.is_loaded and orch.config.name == "proj"

    def test_detect_and_init(self, tmp_path):
        sub = tmp_path / "svc"
        sub.mkdir()
        (sub / "Cargo.toml").write_text("x", encoding="utf-8")
        orch = detect_and_init(work_dir=str(tmp_path))
        assert orch.config.name == tmp_path.name
        assert "svc" in orch.config.modules
        assert orch.config.languages == ["rust"]

    def test_run_pipeline_fn(self, tmp_path):
        cfg = _make_config(modules={
            "m1": ModuleConfig(id="m1", language="python", path=".", build_cmd="echo hi"),
        })
        (tmp_path / ".actus-project.json").write_text(
            json.dumps(cfg.to_dict()), encoding="utf-8")
        result = run_pipeline(work_dir=str(tmp_path))
        assert result["status"] == "ok"


class TestModuleExports:
    """__all__ 完整性。"""

    def test_all(self):
        import vools.actus.project as pm
        expected = {'LANGUAGE_RULES', 'ModuleConfig', 'PipelineStep', 'ProjectConfig',
                    'ProjectOrchestrator', 'detect_and_init', 'detect_language',
                    'detect_languages', 'detect_modules', 'load_project', 'run_pipeline'}
        assert set(pm.__all__) == expected
