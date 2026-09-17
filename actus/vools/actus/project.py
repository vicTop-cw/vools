"""project.py —— 多语言项目编排引擎（docs/23 §E1-1）。

支持：
- 自动语言检测（Cargo.toml / go.mod / package.json / pyproject.toml 等）
- 项目定义加载与校验
- DAG 构建流水线（复用 workflow.py 的 DAGScheduler）
- 模块级构建/测试/部署
- 依赖解析与拓扑排序
- 并行执行与错误传播
"""

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import records as _records
from .workflow import DAGScheduler, WorkflowExecutor


# ── 数据结构 ──

@dataclass
class ModuleConfig:
    """模块配置。"""
    id: str
    language: str
    path: str
    build_cmd: str = ""
    test_cmd: str = ""
    deploy_cmd: str = ""
    lint_cmd: str = ""
    outputs: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=list) if False else field(default_factory=dict)
    deps: List[str] = field(default_factory=list)
    timeout: int = 300
    retries: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "language": self.language,
            "path": self.path,
            "build_cmd": self.build_cmd,
            "test_cmd": self.test_cmd,
            "deploy_cmd": self.deploy_cmd,
            "lint_cmd": self.lint_cmd,
            "outputs": self.outputs,
            "env": self.env,
            "deps": self.deps,
            "timeout": self.timeout,
            "retries": self.retries,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ModuleConfig":
        return cls(
            id=d.get("id", ""),
            language=d.get("language", ""),
            path=d.get("path", ""),
            build_cmd=d.get("build_cmd", ""),
            test_cmd=d.get("test_cmd", ""),
            deploy_cmd=d.get("deploy_cmd", ""),
            lint_cmd=d.get("lint_cmd", ""),
            outputs=d.get("outputs", []),
            env=d.get("env", {}),
            deps=d.get("deps", []),
            timeout=d.get("timeout", 300),
            retries=d.get("retries", 0),
        )


@dataclass
class PipelineStep:
    """流水线步骤。"""
    id: str
    module: str  # "*" 表示所有模块
    phase: str   # build / test / deploy / lint
    depends_on: List[str] = field(default_factory=list)
    condition: str = ""
    retries: int = 0
    timeout: int = 300

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "module": self.module,
            "phase": self.phase,
            "depends_on": self.depends_on,
            "condition": self.condition,
            "retries": self.retries,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineStep":
        return cls(
            id=d.get("id", ""),
            module=d.get("module", "*"),
            phase=d.get("phase", "build"),
            depends_on=d.get("depends_on", []),
            condition=d.get("condition", ""),
            retries=d.get("retries", 0),
            timeout=d.get("timeout", 300),
        )


@dataclass
class ProjectConfig:
    """项目配置。"""
    name: str
    version: str = "1.0.0"
    languages: List[str] = field(default_factory=list)
    modules: Dict[str, ModuleConfig] = field(default_factory=dict)
    pipeline: List[PipelineStep] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    work_dir: str = "."

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "languages": self.languages,
            "modules": {k: v.to_dict() for k, v in self.modules.items()},
            "pipeline": [s.to_dict() for s in self.pipeline],
            "env": self.env,
            "work_dir": self.work_dir,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectConfig":
        modules = {}
        for k, v in d.get("modules", {}).items():
            modules[k] = ModuleConfig.from_dict(v)
        pipeline = [PipelineStep.from_dict(s) for s in d.get("pipeline", [])]
        return cls(
            name=d.get("name", "unnamed"),
            version=d.get("version", "1.0.0"),
            languages=d.get("languages", []),
            modules=modules,
            pipeline=pipeline,
            env=d.get("env", {}),
            work_dir=d.get("work_dir", "."),
        )


# ── 语言检测 ──

def _has_ts_config() -> bool:
    """检查当前目录是否存在 tsconfig.json。"""
    return os.path.isfile("tsconfig.json")


# 语言检测规则：文件模式 → (语言, 包管理器, 构建命令, 测试命令)
LANGUAGE_RULES = [
    {
        "files": ["Cargo.toml"],
        "language": "rust",
        "package_manager": "cargo",
        "build_cmd": "cargo build --release",
        "test_cmd": "cargo test",
        "lint_cmd": "cargo clippy -- -D warnings",
    },
    {
        "files": ["go.mod"],
        "language": "go",
        "package_manager": "go modules",
        "build_cmd": "go build ./...",
        "test_cmd": "go test ./...",
        "lint_cmd": "golangci-lint run",
    },
    {
        "files": ["package.json"],
        "language": "javascript",  # 默认 javascript，detect_language 中动态判断 tsconfig
        "package_manager": "npm",
        "build_cmd": "npm ci && npm run build",
        "test_cmd": "npm test",
        "lint_cmd": "npm run lint",
        "_has_ts": True,  # 标记需要检查 tsconfig
    },
    {
        "files": ["pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"],
        "language": "python",
        "package_manager": "pip",
        "build_cmd": "pip install -r requirements.txt",
        "test_cmd": "pytest",
        "lint_cmd": "ruff check .",
    },
    {
        "files": ["pom.xml"],
        "language": "java",
        "package_manager": "maven",
        "build_cmd": "mvn compile",
        "test_cmd": "mvn test",
        "lint_cmd": "mvn checkstyle:check",
    },
    {
        "files": ["build.gradle", "build.gradle.kts"],
        "language": "java",
        "package_manager": "gradle",
        "build_cmd": "./gradlew build",
        "test_cmd": "./gradlew test",
        "lint_cmd": "./gradlew checkstyleMain",
    },
    {
        "files": ["*.csproj"],
        "language": "csharp",
        "package_manager": "dotnet",
        "build_cmd": "dotnet build",
        "test_cmd": "dotnet test",
        "lint_cmd": "dotnet format --verify-no-changes",
    },
]


def _has_ts_config_in_dir(dir_path: str) -> bool:
    """检查指定目录是否存在 tsconfig.json。"""
    return os.path.isfile(os.path.join(dir_path, "tsconfig.json"))


def detect_language(dir_path: str) -> Optional[str]:
    """检测目录的编程语言。"""
    for rule in LANGUAGE_RULES:
        for pattern in rule["files"]:
            if "*" in pattern:
                import glob
                if glob.glob(os.path.join(dir_path, pattern)):
                    # 特殊处理 package.json：检查是否有 tsconfig
                    if pattern == "package.json":
                        return "typescript" if _has_ts_config_in_dir(dir_path) else "javascript"
                    return rule["language"]
            else:
                if os.path.isfile(os.path.join(dir_path, pattern)):
                    # 特殊处理 package.json
                    if pattern == "package.json":
                        return "typescript" if _has_ts_config_in_dir(dir_path) else "javascript"
                    return rule["language"]
    return None


def detect_languages(root: str) -> List[str]:
    """递归检测项目根目录下所有模块的语言。"""
    languages = set()
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过常见非项目目录
        dirnames[:] = [d for d in dirnames if d not in (
            "node_modules", ".git", "__pycache__", "target", "dist", "build",
            ".venv", "venv", ".tox", ".eggs", "*.egg-info"
        )]
        lang = detect_language(dirpath)
        if lang:
            languages.add(lang)
    return sorted(languages)


def detect_modules(root: str) -> Dict[str, ModuleConfig]:
    """自动检测项目中的所有模块。"""
    modules = {}
    for entry in os.listdir(root):
        entry_path = os.path.join(root, entry)
        if not os.path.isdir(entry_path):
            continue
        if entry.startswith(".") or entry in ("node_modules", "__pycache__", "target"):
            continue
        lang = detect_language(entry_path)
        if lang:
            rule = next((r for r in LANGUAGE_RULES if r["language"] == lang), None)
            module_id = entry.replace("-", "_").replace(" ", "_")
            modules[module_id] = ModuleConfig(
                id=module_id,
                language=lang,
                path=entry,
                build_cmd=rule.get("build_cmd", "") if rule else "",
                test_cmd=rule.get("test_cmd", "") if rule else "",
                lint_cmd=rule.get("lint_cmd", "") if rule else "",
            )
    return modules


# ── 项目编排引擎 ──

class ProjectOrchestrator:
    """多语言项目编排器。

    使用方式:
        orch = ProjectOrchestrator()
        orch.load_project(".actus-project.json")
        result = orch.run_pipeline()
    """

    def __init__(self, work_dir: str = "."):
        self._work_dir = work_dir
        self._config: Optional[ProjectConfig] = None
        self._status: Dict[str, dict] = {}
        self._logs: List[dict] = []
        self._start_time: float = 0

    @property
    def work_dir(self) -> str:
        return self._work_dir

    @property
    def config(self) -> Optional[ProjectConfig]:
        return self._config

    @property
    def is_loaded(self) -> bool:
        return self._config is not None

    # ── 加载与校验 ──

    def load_project(self, project_file: str = ".actus-project.json") -> ProjectConfig:
        """加载项目定义文件。"""
        path = os.path.join(self._work_dir, project_file)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Project file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._config = ProjectConfig.from_dict(data)
        self._config.work_dir = self._work_dir
        self._log("project_loaded", f"Loaded project: {self._config.name}")
        return self._config

    def load_config(self, config: ProjectConfig):
        """直接加载配置对象。"""
        self._config = config
        self._log("config_loaded", f"Loaded config: {config.name}")

    def validate(self) -> Tuple[bool, List[str]]:
        """验证项目定义。"""
        errors = []
        if not self._config:
            return False, ["No project loaded"]

        # 检查模块 id 唯一性
        module_ids = set()
        for mid, mod in self._config.modules.items():
            if mid in module_ids:
                errors.append(f"Duplicate module id: {mid}")
            module_ids.add(mid)
            if not mod.language:
                errors.append(f"Module {mid}: missing language")
            if not mod.path:
                errors.append(f"Module {mid}: missing path")

        # 检查流水线步骤引用
        for step in self._config.pipeline:
            if step.module != "*" and step.module not in self._config.modules:
                errors.append(f"Step {step.id}: unknown module {step.module}")
            for dep in step.depends_on:
                if dep not in [s.id for s in self._config.pipeline]:
                    errors.append(f"Step {step.id}: unknown dependency {dep}")

        # 检查循环依赖
        try:
            self._build_dag()
        except ValueError as e:
            errors.append(str(e))

        return len(errors) == 0, errors

    # ── 语言检测 ──

    def auto_detect(self) -> Dict[str, ModuleConfig]:
        """自动检测项目模块。"""
        modules = detect_modules(self._work_dir)
        if self._config:
            self._config.modules.update(modules)
            self._config.languages = list(set(
                self._config.languages + [m.language for m in modules.values()]
            ))
        self._log("auto_detect", f"Detected {len(modules)} modules")
        return modules

    # ── 流水线执行 ──

    def run_pipeline(self, pipeline_id: str = "default",
                     phase: str = None) -> dict:
        """执行构建流水线。"""
        if not self._config:
            return {"status": "error", "message": "No project loaded"}

        self._start_time = time.time()
        self._status = {}
        self._logs = []

        # 构建 DAG
        try:
            dag = self._build_dag(phase)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        # 拓扑排序
        try:
            order = dag.topological_sort()
        except ValueError as e:
            return {"status": "error", "message": f"Circular dependency: {e}"}

        # 执行
        results = {}
        failed = set()

        for step_id in order:
            step = next((s for s in self._config.pipeline if s.id == step_id), None)
            if not step:
                continue

            # 检查依赖是否成功
            if any(dep in failed for dep in step.depends_on):
                self._status[step_id] = {"status": "skipped", "reason": "dependency_failed"}
                failed.add(step_id)
                continue

            # 条件判断
            if step.condition and not self._eval_condition(step.condition, results):
                self._status[step_id] = {"status": "skipped", "reason": "condition_not_met"}
                continue

            # 执行步骤
            result = self._run_step(step)
            results[step_id] = result
            self._status[step_id] = result

            if result.get("status") != "ok":
                failed.add(step_id)

        duration = time.time() - self._start_time
        status = "ok" if not failed else "partial" if len(failed) < len(order) else "failed"

        return {
            "status": status,
            "duration": duration,
            "steps_total": len(order),
            "steps_ok": len(order) - len(failed),
            "steps_failed": len(failed),
            "results": results,
        }

    def run_step(self, step_id: str) -> dict:
        """执行单个步骤。"""
        if not self._config:
            return {"status": "error", "message": "No project loaded"}

        step = next((s for s in self._config.pipeline if s.id == step_id), None)
        if not step:
            return {"status": "error", "message": f"Step not found: {step_id}"}

        return self._run_step(step)

    def _run_step(self, step: PipelineStep) -> dict:
        """执行单个步骤。"""
        self._log("step_start", f"Running step: {step.id}")

        modules = []
        if step.module == "*":
            modules = list(self._config.modules.values())
        else:
            mod = self._config.modules.get(step.module)
            if mod:
                modules = [mod]

        if not modules:
            return {"status": "error", "message": f"No modules for step {step.id}"}

        results = []
        for mod in modules:
            cmd = self._get_phase_cmd(mod, step.phase)
            if not cmd:
                continue

            # 执行命令
            exit_code, stdout, stderr = self._exec_cmd(
                cmd, mod.path, mod.env, step.timeout
            )
            results.append({
                "module": mod.id,
                "phase": step.phase,
                "exit_code": exit_code,
                "stdout": stdout[-500:] if stdout else "",
                "stderr": stderr[-500:] if stderr else "",
            })

        # 汇总
        all_ok = all(r["exit_code"] == 0 for r in results)
        return {
            "status": "ok" if all_ok else "failed",
            "modules": results,
        }

    def _get_phase_cmd(self, mod: ModuleConfig, phase: str) -> str:
        """获取阶段的命令。"""
        cmd_map = {
            "build": mod.build_cmd,
            "test": mod.test_cmd,
            "deploy": mod.deploy_cmd,
            "lint": mod.lint_cmd,
        }
        return cmd_map.get(phase, "")

    def _exec_cmd(self, cmd: str, cwd: str, env: dict,
                  timeout: int) -> Tuple[int, str, str]:
        """执行 shell 命令。"""
        work_path = os.path.join(self._work_dir, cwd)
        if not os.path.isdir(work_path):
            work_path = self._work_dir

        merged_env = os.environ.copy()
        merged_env.update(self._config.env if self._config else {})
        merged_env.update(env)

        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=work_path,
                env=merged_env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Command timed out after {timeout}s"
        except Exception as e:
            return -1, "", str(e)

    # ── DAG 构建 ──

    def _build_dag(self, phase: str = None) -> DAGScheduler:
        """从流水线步骤构建 DAG。

        DAGScheduler 通过 nodes 列表中的 'depends' 字段自动建图。
        """
        step_ids = set()
        nodes = []
        for step in self._config.pipeline:
            if phase and step.phase != phase:
                continue
            step_ids.add(step.id)
            node = step.to_dict()
            # DAGScheduler 使用 'depends' 字段（不是 'depends_on'）
            node["depends"] = list(step.depends_on)
            nodes.append(node)

        # 添加被依赖但不在当前阶段筛选范围内的虚拟节点
        for step in self._config.pipeline:
            if phase and step.phase != phase:
                continue
            for dep in step.depends_on:
                if dep not in step_ids:
                    nodes.append({
                        "id": dep,
                        "module": "_dependency",
                        "phase": "_external",
                        "depends": []
                    })

        return DAGScheduler(nodes)

    # ── 条件判断 ──

    def _eval_condition(self, condition: str, results: dict) -> bool:
        """评估条件表达式。"""
        # 简单条件：检查前置步骤是否成功
        if condition == "all_prev_ok":
            return all(
                r.get("status") == "ok"
                for r in results.values()
            )
        if condition == "any_prev_ok":
            return any(
                r.get("status") == "ok"
                for r in results.values()
            )
        # 默认通过
        return True

    # ── 状态与日志 ──

    def get_status(self) -> dict:
        """获取流水线状态。"""
        return {
            "loaded": self.is_loaded,
            "project": self._config.name if self._config else None,
            "modules": list(self._config.modules.keys()) if self._config else [],
            "steps": self._status,
            "logs": self._logs[-50:],
        }

    def _log(self, event: str, message: str):
        """记录日志。"""
        self._logs.append({
            "timestamp": time.time(),
            "event": event,
            "message": message,
        })

    # ── 模块管理 ──

    def add_module(self, module: ModuleConfig):
        """添加模块。"""
        if not self._config:
            raise RuntimeError("No project loaded")
        self._config.modules[module.id] = module
        if module.language not in self._config.languages:
            self._config.languages.append(module.language)

    def remove_module(self, module_id: str):
        """移除模块。"""
        if not self._config:
            raise RuntimeError("No project loaded")
        self._config.modules.pop(module_id, None)
        # 移除相关流水线步骤
        self._config.pipeline = [
            s for s in self._config.pipeline
            if s.module != module_id
        ]

    def save_project(self, project_file: str = ".actus-project.json"):
        """保存项目定义到文件。"""
        if not self._config:
            raise RuntimeError("No project loaded")
        path = os.path.join(self._work_dir, project_file)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._config.to_dict(), f, ensure_ascii=False, indent=2)


# ── 便捷函数 ──

def load_project(project_file: str = ".actus-project.json",
                 work_dir: str = ".") -> ProjectOrchestrator:
    """便捷函数：加载项目。"""
    orch = ProjectOrchestrator(work_dir=work_dir)
    orch.load_project(project_file)
    return orch


def detect_and_init(work_dir: str = ".") -> ProjectOrchestrator:
    """便捷函数：检测项目并初始化。"""
    orch = ProjectOrchestrator(work_dir=work_dir)
    modules = orch.auto_detect()
    config = ProjectConfig(
        name=os.path.basename(os.path.abspath(work_dir)),
        modules=modules,
        languages=sorted(set(m.language for m in modules.values())),
    )
    orch.load_config(config)
    return orch


def run_pipeline(project_file: str = ".actus-project.json",
                 work_dir: str = ".",
                 phase: str = None) -> dict:
    """便捷函数：加载并执行流水线。"""
    orch = load_project(project_file, work_dir)
    return orch.run_pipeline(phase=phase)


__all__ = [
    'LANGUAGE_RULES',
    'ModuleConfig',
    'PipelineStep',
    'ProjectConfig',
    'ProjectOrchestrator',
    'detect_and_init',
    'detect_language',
    'detect_languages',
    'detect_modules',
    'load_project',
    'run_pipeline'
]
