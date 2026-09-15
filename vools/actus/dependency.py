"""dependency.py —— 动作依赖解析与自动安装引擎。

职责：
- 解析动作的 deps 字段
- 检查依赖是否满足（编译产物存在、版本匹配）
- 自动构建/安装缺失依赖
- 依赖图拓扑排序
- 循环依赖检测
- MCP 工具 + CLI 集成
"""

import json
import os
import subprocess
import sys
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import deque


@dataclass
class Dependency:
    """单个依赖定义。"""
    name: str                    # 依赖名称（如 "cs_forms", "cs_tools", "python:requests"）
    type: str                    # 类型: "action" | "python" | "npm" | "system" | "cs_build"
    required: bool = True        # 是否必需
    min_version: str = ""        # 最低版本
    build_command: str = ""      # 构建命令（cs_build 类型）
    build_check: str = ""        # 构建产物检查路径
    @property
    def fix_command(self) -> str:
        """自动修复命令（兼容属性访问）。"""
        if self.type == "cs_build":
            return self.build_command
        elif self.type == "python":
            return f"pip install {self.name}"
        elif self.type == "npm":
            return f"npm install {self.name}"
        return ""


@dataclass
class DepCheckResult:
    """依赖检查结果。"""
    name: str
    satisfied: bool
    message: str
    auto_fixable: bool = False
    fix_command: str = ""


class DependencyResolver:
    """动作依赖解析器。"""

    def __init__(self, actions_root: str = None, build_root: str = None):
        self._actions_root = actions_root or self._find_actions_root()
        self._build_root = build_root or os.path.join(self._actions_root, "system")
        self._cache: Dict[str, DepCheckResult] = {}

    @staticmethod
    def _find_actions_root() -> str:
        """自动定位 actions 根目录。"""
        current = os.path.dirname(os.path.abspath(__file__))
        # 从 engine/actuscore/ 回到项目根
        project_root = os.path.dirname(os.path.dirname(current))
        actions = os.path.join(project_root, "actions")
        if os.path.isdir(actions):
            return actions
        # 回退到当前工作目录
        return os.path.join(os.getcwd(), "actions")

    def parse_deps(self, raw_deps: list) -> List[Dependency]:
        """解析原始 deps 列表。"""
        deps = []
        for d in raw_deps:
            if isinstance(d, str):
                deps.append(self._parse_dep_string(d))
            elif isinstance(d, dict):
                deps.append(Dependency(
                    name=d.get("name", ""),
                    type=d.get("type", "action"),
                    required=d.get("required", True),
                    min_version=d.get("min_version", ""),
                    build_command=d.get("build_command", ""),
                    build_check=d.get("build_check", "")
                ))
        return deps

    def _parse_dep_string(self, dep_str: str) -> Dependency:
        """解析依赖字符串。

        格式：
        - "cs_forms" → C# 构建依赖
        - "cs_tools" → C# 构建依赖
        - "python:requests" → Python 包
        - "npm:shiki" → npm 包
        - "system:git" → 系统命令
        - "action:actus.system.dialog_alert" → 其他动作
        """
        if dep_str.startswith("python:"):
            return Dependency(name=dep_str[7:], type="python")
        elif dep_str.startswith("npm:"):
            return Dependency(name=dep_str[4:], type="npm")
        elif dep_str.startswith("system:"):
            return Dependency(name=dep_str[7:], type="system")
        elif dep_str.startswith("action:"):
            return Dependency(name=dep_str[7:], type="action")
        elif dep_str.startswith("cs_") or dep_str in ("cs_forms", "cs_tools"):
            return self._build_cs_dep(dep_str)
        else:
            # 默认作为 action 依赖
            return Dependency(name=dep_str, type="action")

    def _build_cs_dep(self, name: str) -> Dependency:
        """构建 C# 依赖定义。"""
        build_dir = os.path.join(self._build_root, name, "build")
        if name == "cs_forms":
            exe_path = os.path.join(build_dir, "Dialogs", "net8.0-windows", "actus-dialogs.exe")
            return Dependency(
                name=name, type="cs_build",
                build_command=f"cd {self._actions_root}/system/{name} && scripts/hot_reload.bat build",
                build_check=exe_path
            )
        elif name == "cs_tools":
            exe_path = os.path.join(build_dir, "DesktopTools", "net8.0-windows", "actus-tools.exe")
            return Dependency(
                name=name, type="cs_build",
                build_command=f"cd {self._actions_root}/system/{name} && scripts/hot_reload.bat build",
                build_check=exe_path
            )
        else:
            return Dependency(name=name, type="cs_build", build_check=build_dir)

    def check_dep(self, dep: Dependency) -> DepCheckResult:
        """检查单个依赖是否满足。"""
        if dep.name in self._cache:
            return self._cache[dep.name]

        result = self._do_check(dep)
        self._cache[dep.name] = result
        return result

    def _do_check(self, dep: Dependency) -> DepCheckResult:
        """实际检查逻辑。"""
        if dep.type == "cs_build":
            return self._check_cs_build(dep)
        elif dep.type == "python":
            return self._check_python_pkg(dep)
        elif dep.type == "npm":
            return self._check_npm_pkg(dep)
        elif dep.type == "system":
            return self._check_system_cmd(dep)
        elif dep.type == "action":
            return self._check_action(dep)
        else:
            return DepCheckResult(dep.name, False, f"unknown dep type: {dep.type}")

    def _check_cs_build(self, dep: Dependency) -> DepCheckResult:
        """检查 C# 构建产物。"""
        if dep.build_check and os.path.exists(dep.build_check):
            return DepCheckResult(dep.name, True, f"构建产物存在: {dep.build_check}")
        if dep.build_check:
            return DepCheckResult(
                dep.name, False,
                f"构建产物缺失: {dep.build_check}",
                auto_fixable=True,
                fix_command=dep.build_command
            )
        return DepCheckResult(dep.name, False, "未知构建目标")

    def _check_python_pkg(self, dep: Dependency) -> DepCheckResult:
        """检查 Python 包。"""
        try:
            __import__(dep.name)
            return DepCheckResult(dep.name, True, f"Python 包 {dep.name} 已安装")
        except ImportError:
            return DepCheckResult(
                dep.name, False,
                f"Python 包 {dep.name} 未安装",
                auto_fixable=True,
                fix_command=f"pip install {dep.name}"
            )

    def _check_npm_pkg(self, dep: Dependency) -> DepCheckResult:
        """检查 npm 包。"""
        pkg_json = os.path.join(self._actions_root, "..", "engine", "actuscore", "_shiki", "package.json")
        if os.path.exists(pkg_json):
            with open(pkg_json) as f:
                pkg = json.load(f)
            deps = pkg.get("dependencies", {})
            if dep.name in deps:
                return DepCheckResult(dep.name, True, f"npm 包 {dep.name} 已声明")
        node_modules = os.path.join(os.path.dirname(pkg_json), "node_modules", dep.name)
        if os.path.isdir(node_modules):
            return DepCheckResult(dep.name, True, f"npm 包 {dep.name} 已安装")
        return DepCheckResult(
            dep.name, False,
            f"npm 包 {dep.name} 未安装",
            auto_fixable=True,
            fix_command=f"cd engine/actuscore/_shiki && npm install {dep.name}"
        )

    def _check_system_cmd(self, dep: Dependency) -> DepCheckResult:
        """检查系统命令。"""
        try:
            r = subprocess.run(["where", dep.name], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return DepCheckResult(dep.name, True, f"系统命令 {dep.name} 可用: {r.stdout.strip()}")
        except Exception:
            pass
        return DepCheckResult(dep.name, False, f"系统命令 {dep.name} 未找到")

    def _check_action(self, dep: Dependency) -> DepCheckResult:
        """检查动作依赖。"""
        # 在 actions 目录中搜索
        for root, dirs, files in os.walk(self._actions_root):
            for f in files:
                if f.endswith(".actus.md"):
                    path = os.path.join(root, f)
                    try:
                        content = open(path, encoding="utf-8").read()
                        if f'"id": "{dep.name}"' in content or f'"id":"{dep.name}"' in content:
                            return DepCheckResult(dep.name, True, f"动作 {dep.name} 存在: {path}")
                    except Exception:
                        pass
        return DepCheckResult(dep.name, False, f"动作 {dep.name} 未找到")

    def check_all(self, deps: List[Dependency]) -> List[DepCheckResult]:
        """检查所有依赖。"""
        return [self.check_dep(d) for d in deps]

    def resolve(self, deps: List[Dependency], auto_install: bool = False) -> Tuple[bool, List[str]]:
        """解析依赖，返回 (是否全部满足, 消息列表)。"""
        messages = []
        all_ok = True

        for dep in deps:
            result = self.check_dep(dep)
            if result.satisfied:
                messages.append(f"✅ {result.name}: {result.message}")
            else:
                all_ok = False
                messages.append(f"❌ {result.name}: {result.message}")
                if auto_install and result.auto_fixable and result.fix_command:
                    messages.append(f"   🔧 自动修复: {result.fix_command}")
                    if self._try_fix(result):
                        messages.append(f"   ✅ 修复成功")
                    else:
                        messages.append(f"   ❌ 修复失败")

        return all_ok, messages

    def _try_fix(self, result: DepCheckResult) -> bool:
        """尝试自动修复依赖。"""
        if not result.fix_command:
            return False
        try:
            if result.fix_command.startswith("pip install"):
                pkg = result.fix_command.replace("pip install ", "").strip()
                r = subprocess.run([sys.executable, "-m", "pip", "install", pkg],
                                   capture_output=True, text=True, timeout=120)
                return r.returncode == 0
            elif result.fix_command.startswith("cd "):
                # 提取 cd 路径和后续命令
                parts = result.fix_command.split(" && ")
                if len(parts) >= 2:
                    cwd = parts[0].replace("cd ", "").strip()
                    cmd = " && ".join(parts[1:])
                    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=120)
                    return r.returncode == 0
            else:
                r = subprocess.run(result.fix_command, shell=True, capture_output=True, text=True, timeout=120)
                return r.returncode == 0
        except Exception:
            return False

    def topological_sort(self, actions: Dict[str, List[str]]) -> Tuple[bool, List[str]]:
        """拓扑排序，检测循环依赖。

        参数:
            actions: {action_id: [dep_id, ...]}

        返回:
            (是否无环, 排序后的 action_id 列表)
        """
        in_degree = {aid: 0 for aid in actions}
        graph = {aid: [] for aid in actions}

        for aid, deps in actions.items():
            for dep in deps:
                if dep in actions:
                    graph[dep].append(aid)
                    in_degree[aid] = in_degree.get(aid, 0) + 1

        queue = deque(aid for aid, deg in in_degree.items() if deg == 0)
        sorted_list = []

        while queue:
            node = queue.popleft()
            sorted_list.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        has_cycle = len(sorted_list) != len(actions)
        return not has_cycle, sorted_list

    def get_dep_tree(self, action_id: str, depth: int = 0, visited: Set[str] = None) -> Dict:
        """获取依赖树。"""
        if visited is None:
            visited = set()
        if action_id in visited:
            return {"id": action_id, "circular": True}
        visited.add(action_id)

        # 查找动作文件
        action_path = self._find_action_file(action_id)
        if not action_path:
            return {"id": action_id, "found": False}

        raw_deps = self._extract_deps_from_file(action_path)
        deps = self.parse_deps(raw_deps)

        children = []
        for dep in deps:
            if dep.type == "action":
                children.append(self.get_dep_tree(dep.name, depth + 1, visited.copy()))
            else:
                result = self.check_dep(dep)
                children.append({
                    "id": dep.name,
                    "type": dep.type,
                    "satisfied": result.satisfied,
                    "message": result.message
                })

        return {
            "id": action_id,
            "type": "action",
            "deps": children,
            "depth": depth
        }

    def _find_action_file(self, action_id: str) -> Optional[str]:
        """查找动作文件路径。"""
        for root, dirs, files in os.walk(self._actions_root):
            for f in files:
                if f.endswith(".actus.md"):
                    path = os.path.join(root, f)
                    try:
                        content = open(path, encoding="utf-8").read()
                        if f'"id": "{action_id}"' in content or f'"id":"{action_id}"' in content:
                            return path
                    except Exception:
                        pass
        return None

    def _extract_deps_from_file(self, path: str) -> list:
        """从动作文件中提取 deps。"""
        try:
            content = open(path, encoding="utf-8").read()
            # 简单 JSON 提取
            import re
            match = re.search(r'"deps"\s*:\s*(\[[^\]]*\])', content)
            if match:
                return json.loads(match.group(1))
        except Exception:
            pass
        return []


# ── 全局单例 ──
_resolver = None


def get_resolver() -> DependencyResolver:
    global _resolver
    if _resolver is None:
        _resolver = DependencyResolver()
    return _resolver


def check_action_deps(action_id: str, auto_install: bool = False) -> dict:
    """检查指定动作的依赖（便捷函数）。"""
    resolver = get_resolver()
    action_path = resolver._find_action_file(action_id)
    if not action_path:
        return {"ok": False, "error": f"action not found: {action_id}"}

    raw_deps = resolver._extract_deps_from_file(action_path)
    deps = resolver.parse_deps(raw_deps)
    all_ok, messages = resolver.resolve(deps, auto_install=auto_install)

    return {
        "ok": all_ok,
        "action_id": action_id,
        "deps_total": len(deps),
        "deps_satisfied": sum(1 for m in messages if m.startswith("✅")),
        "messages": messages
    }


if __name__ == "__main__":
    # 测试
    resolver = DependencyResolver()
    print(f"Actions root: {resolver._actions_root}")
    print(f"Build root: {resolver._build_root}")


__all__ = [
    'DepCheckResult',
    'Dependency',
    'DependencyResolver',
    'check_action_deps',
    'get_resolver'
]
