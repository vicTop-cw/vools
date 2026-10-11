"""dependency.py —— 动作依赖解析与自动安装引擎。

职责：
- 解析动作的 deps 字段
- 检查依赖是否满足（编译产物存在、版本匹配）
- 懒加载策略：hint（提示）→ ephemeral（临时执行）→ download（下载安装）
- 依赖图拓扑排序
- 循环依赖检测
- MCP 工具 + CLI 集成
- 启动自检：actus doctor
"""

import json
import os
import subprocess
import sys
import shutil
from typing import Dict, List, Optional, Tuple, Set
from vools.core.dataclass_compat import dataclass, field
from enum import Enum
from collections import deque


class DepStrategy(Enum):
    """依赖懒加载策略。"""
    HINT = "hint"           # 提示安装命令，不硬失败
    EPHEMERAL = "ephemeral"  # pipx/npx 临时执行
    DOWNLOAD = "download"   # 下载单文件到 _meta/tools/
    FAIL = "fail"           # 硬失败（默认）


class DepType(Enum):
    """依赖类型。"""
    BUILTIN = "builtin"     # 引擎内
    SYSTEM = "system"       # 系统命令
    LANG = "lang"           # pip/npm 包（统一为 lang:pkg）
    MCP = "mcp"             # MCP server
    ACTION = "action"       # 其他动作
    CS_BUILD = "cs_build"   # C# 构建产物


@dataclass
class Dependency:
    """单个依赖定义。"""
    name: str                    # 依赖名称（如 "cs_forms", "pandoc", "requests"）
    type: DepType = DepType.ACTION  # 类型
    required: bool = True        # 是否必需
    min_version: str = ""        # 最低版本
    strategy: DepStrategy = DepStrategy.HINT  # 懒加载策略
    build_command: str = ""      # 构建命令（cs_build 类型）
    build_check: str = ""        # 构建产物检查路径
    lang_manager: str = ""       # 包管理器：pip / npm（lang 类型）
    @property
    def fix_command(self) -> str:
        """自动修复命令（兼容属性访问）。"""
        if self.type == DepType.CS_BUILD:
            return self.build_command
        elif self.type == DepType.LANG:
            if self.lang_manager == "npm":
                return f"npm install {self.name}"
            return f"pip install {self.name}"
        elif self.type == DepType.SYSTEM:
            return f"安装系统工具: {self.name}"
        return ""

    @property
    def ephemeral_command(self) -> Optional[str]:
        """临时执行命令（ephemeral 策略）。"""
        if self.type == DepType.LANG:
            if self.lang_manager == "npm":
                return f"npx {self.name}"
            return f"pipx run {self.name}"
        return None


@dataclass
class DepCheckResult:
    """依赖检查结果。"""
    name: str
    satisfied: bool
    message: str
    strategy: DepStrategy = DepStrategy.FAIL
    auto_fixable: bool = False
    fix_command: str = ""           # 自动修复命令（pip install / npm install / 构建命令）
    ephemeral_cmd: str = ""         # 临时执行命令（pipx run / npx）
    download_url: str = ""          # 下载 URL（download 策略）


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
                dep_type = d.get("type", "action")
                if isinstance(dep_type, str):
                    try:
                        dep_type = DepType(dep_type)
                    except ValueError:
                        dep_type = DepType.ACTION
                strategy = d.get("strategy", "hint")
                if isinstance(strategy, str):
                    try:
                        strategy = DepStrategy(strategy)
                    except ValueError:
                        strategy = DepStrategy.HINT
                deps.append(Dependency(
                    name=d.get("name", ""),
                    type=dep_type,
                    required=d.get("required", True),
                    min_version=d.get("min_version", ""),
                    strategy=strategy,
                    build_command=d.get("build_command", ""),
                    build_check=d.get("build_check", ""),
                    lang_manager=d.get("lang_manager", "pip")
                ))
        return deps

    def _parse_dep_string(self, dep_str: str) -> Dependency:
        """解析依赖字符串。

        格式：
        - "builtin:xxx" → 引擎内依赖
        - "system:pandoc" → 系统命令
        - "pip:requests" → Python 包（lang 类型）
        - "npm:shiki" → npm 包（lang 类型）
        - "mcp:server" → MCP server
        - "action:actus.system.dialog_alert" → 其他动作
        - "cs_forms" / "cs_tools" → C# 构建依赖
        """
        if dep_str.startswith("builtin:"):
            return Dependency(name=dep_str[8:], type=DepType.BUILTIN)
        elif dep_str.startswith("system:"):
            return Dependency(name=dep_str[7:], type=DepType.SYSTEM, strategy=DepStrategy.HINT)
        elif dep_str.startswith("pip:"):
            return Dependency(name=dep_str[4:], type=DepType.LANG, lang_manager="pip", strategy=DepStrategy.EPHEMERAL)
        elif dep_str.startswith("npm:"):
            return Dependency(name=dep_str[4:], type=DepType.LANG, lang_manager="npm", strategy=DepStrategy.EPHEMERAL)
        elif dep_str.startswith("mcp:"):
            return Dependency(name=dep_str[4:], type=DepType.MCP, strategy=DepStrategy.HINT)
        elif dep_str.startswith("action:"):
            return Dependency(name=dep_str[7:], type=DepType.ACTION)
        elif dep_str.startswith("cs_") or dep_str in ("cs_forms", "cs_tools"):
            return self._build_cs_dep(dep_str)
        else:
            # 默认作为 action 依赖
            return Dependency(name=dep_str, type=DepType.ACTION)

    def _build_cs_dep(self, name: str) -> Dependency:
        """构建 C# 依赖定义。"""
        build_dir = os.path.join(self._build_root, name, "build")
        if name == "cs_forms":
            exe_path = os.path.join(build_dir, "Dialogs", "net8.0-windows", "actus-dialogs.exe")
            return Dependency(
                name=name, type=DepType.CS_BUILD,
                build_command=f"cd {self._actions_root}/system/{name} && scripts/hot_reload.bat build",
                build_check=exe_path
            )
        elif name == "cs_tools":
            exe_path = os.path.join(build_dir, "DesktopTools", "net8.0-windows", "actus-tools.exe")
            return Dependency(
                name=name, type=DepType.CS_BUILD,
                build_command=f"cd {self._actions_root}/system/{name} && scripts/hot_reload.bat build",
                build_check=exe_path
            )
        else:
            return Dependency(name=name, type=DepType.CS_BUILD, build_check=build_dir)

    def check_dep(self, dep: Dependency) -> DepCheckResult:
        """检查单个依赖是否满足。"""
        if dep.name in self._cache:
            return self._cache[dep.name]

        result = self._do_check(dep)
        self._cache[dep.name] = result
        return result

    def _do_check(self, dep: Dependency) -> DepCheckResult:
        """实际检查逻辑。"""
        if dep.type == DepType.CS_BUILD:
            return self._check_cs_build(dep)
        elif dep.type == DepType.LANG:
            return self._check_lang_pkg(dep)
        elif dep.type == DepType.SYSTEM:
            return self._check_system_cmd(dep)
        elif dep.type == DepType.ACTION:
            return self._check_action(dep)
        elif dep.type == DepType.BUILTIN:
            return self._check_builtin(dep)
        elif dep.type == DepType.MCP:
            return self._check_mcp(dep)
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

    def _check_lang_pkg(self, dep: Dependency) -> DepCheckResult:
        """检查语言包（pip/npm）。"""
        if dep.lang_manager == "npm":
            return self._check_npm_pkg(dep)
        return self._check_pip_pkg(dep)

    def _check_pip_pkg(self, dep: Dependency) -> DepCheckResult:
        """检查 Python 包。"""
        try:
            __import__(dep.name)
            return DepCheckResult(
                dep.name, True,
                f"Python 包 {dep.name} 已安装",
                strategy=dep.strategy,
                ephemeral_cmd=f"pipx run {dep.name}"
            )
        except ImportError:
            return DepCheckResult(
                dep.name, False,
                f"Python 包 {dep.name} 未安装",
                strategy=dep.strategy,
                auto_fixable=True,
                fix_command=f"pip install {dep.name}",
                ephemeral_cmd=f"pipx run {dep.name}"
            )

    def _check_npm_pkg(self, dep: Dependency) -> DepCheckResult:
        """检查 npm 包。"""
        pkg_json = os.path.join(self._actions_root, "..", "engine", "actuscore", "_shiki", "package.json")
        if os.path.exists(pkg_json):
            with open(pkg_json) as f:
                pkg = json.load(f)
            deps = pkg.get("dependencies", {})
            if dep.name in deps:
                return DepCheckResult(
                    dep.name, True,
                    f"npm 包 {dep.name} 已声明",
                    strategy=dep.strategy,
                    ephemeral_cmd=f"npx {dep.name}"
                )
        node_modules = os.path.join(os.path.dirname(pkg_json), "node_modules", dep.name)
        if os.path.isdir(node_modules):
            return DepCheckResult(
                dep.name, True,
                f"npm 包 {dep.name} 已安装",
                strategy=dep.strategy,
                ephemeral_cmd=f"npx {dep.name}"
            )
        return DepCheckResult(
            dep.name, False,
            f"npm 包 {dep.name} 未安装",
            strategy=dep.strategy,
            auto_fixable=True,
            fix_command=f"cd engine/actuscore/_shiki && npm install {dep.name}",
            ephemeral_cmd=f"npx {dep.name}"
        )

    def _check_system_cmd(self, dep: Dependency) -> DepCheckResult:
        """检查系统命令。"""
        try:
            r = subprocess.run(
                ["where", dep.name],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                return DepCheckResult(
                    dep.name, True,
                    f"系统命令 {dep.name} 可用: {r.stdout.strip()}",
                    strategy=dep.strategy
                )
        except Exception:
            pass

        # 检查是否在 _meta/tools/ 中
        tools_dir = os.path.join(self._actions_root, "..", "_meta", "tools")
        tool_path = os.path.join(tools_dir, dep.name)
        if os.path.exists(tool_path) or os.path.exists(tool_path + ".exe"):
            return DepCheckResult(
                dep.name, True,
                f"系统命令 {dep.name} 在 _meta/tools/ 中可用",
                strategy=dep.strategy
            )

        # 根据策略处理
        if dep.strategy == DepStrategy.HINT:
            return DepCheckResult(
                dep.name, False,
                f"系统命令 {dep.name} 未找到",
                strategy=dep.strategy,
                auto_fixable=True,
                fix_command=f"安装 {dep.name} 或添加到 PATH"
            )
        elif dep.strategy == DepStrategy.DOWNLOAD:
            return DepCheckResult(
                dep.name, False,
                f"系统命令 {dep.name} 未找到，需下载到 _meta/tools/",
                strategy=dep.strategy,
                auto_fixable=True
            )
        return DepCheckResult(dep.name, False, f"系统命令 {dep.name} 未找到")

    def _check_builtin(self, dep: Dependency) -> DepCheckResult:
        """检查引擎内依赖。"""
        # 检查 engine/actuscore/ 中是否存在对应模块
        core_dir = os.path.join(os.path.dirname(__file__))
        module_path = os.path.join(core_dir, f"{dep.name}.py")
        if os.path.exists(module_path):
            return DepCheckResult(dep.name, True, f"引擎内依赖 {dep.name} 存在")
        return DepCheckResult(dep.name, False, f"引擎内依赖 {dep.name} 不存在")

    def _check_mcp(self, dep: Dependency) -> DepCheckResult:
        """检查 MCP server。"""
        # MCP server 需要在配置中声明，这里仅做存在性检查
        # 实际调用时通过 stdio 或 SSE 连接
        return DepCheckResult(
            dep.name, True,
            f"MCP server {dep.name} 需运行时连接",
            strategy=dep.strategy
        )

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
        """解析依赖，返回 (是否全部满足, 消息列表)。

        三策略流程：
        1. 检查依赖是否已满足
        2. 不满足时按策略走：
           - HINT: 仅提示安装命令（不硬失败）
           - EPHEMERAL: 尝试 pipx/npx 临时运行
           - DOWNLOAD: 下载单文件到 _meta/tools/
        3. 全部满足 → True；任一必需依赖不满足 → False
        """
        messages = []
        all_ok = True

        for dep in deps:
            result = self.check_dep(dep)
            if result.satisfied:
                messages.append(f"✅ {result.name}: {result.message}")
                continue

            # 依赖未满足，按策略处理
            all_ok = False
            strategy_label = {
                DepStrategy.HINT: "💡 提示",
                DepStrategy.EPHEMERAL: "⚡ 临时执行",
                DepStrategy.DOWNLOAD: "📥 下载",
                DepStrategy.FAIL: "❌ 缺失",
            }.get(dep.strategy, "❌ 缺失")

            messages.append(f"{strategy_label} {dep.name}: {result.message}")

            # HINT 策略：输出安装命令
            if dep.strategy == DepStrategy.HINT:
                if result.fix_command:
                    messages.append(f"   安装命令: {result.fix_command}")
                if result.ephemeral_cmd:
                    messages.append(f"   临时执行: {result.ephemeral_cmd}")

            # EPHEMERAL 策略：尝试 pipx/npx 临时运行
            elif dep.strategy == DepStrategy.EPHEMERAL:
                if result.ephemeral_cmd:
                    messages.append(f"   尝试临时执行: {result.ephemeral_cmd}")
                    ok, output = self.try_ephemeral(dep)
                    if ok:
                        messages.append(f"   ✅ 临时执行成功（{output[:100]}）")
                        all_ok = True  # 临时执行成功视为满足
                        continue
                    else:
                        messages.append(f"   ⚠️ 临时执行失败: {output[:100]}")
                # 降级到 hint
                if result.fix_command:
                    messages.append(f"   安装命令: {result.fix_command}")

            # DOWNLOAD 策略：下载单文件到 _meta/tools/
            elif dep.strategy == DepStrategy.DOWNLOAD:
                ok, output = self.try_download(dep)
                if ok:
                    messages.append(f"   ✅ {output}")
                    all_ok = True
                else:
                    messages.append(f"   ❌ 下载失败: {output}")
                    if result.fix_command:
                        messages.append(f"   备选安装: {result.fix_command}")

            # FAIL 策略（默认）：硬失败
            else:
                if auto_install and result.auto_fixable and result.fix_command:
                    messages.append(f"   🔧 自动修复: {result.fix_command}")
                    if self._try_fix(result):
                        messages.append(f"   ✅ 修复成功")
                        all_ok = True
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

    def try_ephemeral(self, dep: Dependency) -> Tuple[bool, str]:
        """尝试 ephemeral 策略执行。

        返回: (是否成功, 输出)
        """
        if dep.type == DepType.LANG:
            if dep.lang_manager == "npm":
                cmd = f"npx {dep.name}"
            else:
                cmd = f"pipx run {dep.name}"
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                return r.returncode == 0, r.stdout + r.stderr
            except FileNotFoundError:
                return False, f"ephemeral 工具不可用: {cmd}"
            except Exception as e:
                return False, str(e)
        return False, f"类型 {dep.type} 不支持 ephemeral 策略"

    def try_download(self, dep: Dependency) -> Tuple[bool, str]:
        """尝试 download 策略下载工具到 _meta/tools/。

        返回: (是否成功, 输出)
        """
        if dep.type != DepType.SYSTEM:
            return False, f"类型 {dep.type} 不支持 download 策略"

        tools_dir = os.path.join(self._actions_root, "..", "_meta", "tools")
        os.makedirs(tools_dir, exist_ok=True)

        # 预定义下载映射（可扩展）
        download_map = {
            "pandoc": "https://github.com/jgm/pandoc/releases/download/3.1.11/pandoc-3.1.11-windows-x86_64.zip",
            "jq": "https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-windows-amd64.exe",
        }

        if dep.name not in download_map:
            return False, f"无预定义下载地址: {dep.name}"

        url = download_map[dep.name]
        dest = os.path.join(tools_dir, dep.name + ".exe")

        try:
            import urllib.request
            urllib.request.urlretrieve(url, dest)
            os.chmod(dest, 0o755)
            return True, f"已下载到 {dest}"
        except Exception as e:
            return False, f"下载失败: {e}"

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


def doctor() -> dict:
    """启动自检：输出各依赖状态与建议安装清单。"""
    resolver = get_resolver()
    results = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "checks": [],
        "recommendations": [],
        "summary": {"total": 0, "ok": 0, "warning": 0, "error": 0}
    }

    # 高频工具检查清单
    recommended_tools = [
        ("python", DepType.SYSTEM, "Python 解释器"),
        ("git", DepType.SYSTEM, "Git 版本控制"),
        ("jq", DepType.SYSTEM, "JSON 处理工具"),
        ("pandoc", DepType.SYSTEM, "文档转换工具"),
        ("node", DepType.SYSTEM, "Node.js 运行时"),
        ("npm", DepType.SYSTEM, "npm 包管理器"),
        ("pipx", DepType.SYSTEM, "Python 应用隔离运行"),
    ]

    for name, dep_type, desc in recommended_tools:
        dep = Dependency(name=name, type=dep_type, strategy=DepStrategy.HINT)
        result = resolver.check_dep(dep)
        check_result = {
            "name": name,
            "type": dep_type.value,
            "description": desc,
            "satisfied": result.satisfied,
            "message": result.message,
            "strategy": result.strategy.value,
            "fix_command": result.fix_command if result.auto_fixable else None,
        }
        results["checks"].append(check_result)
        results["summary"]["total"] += 1
        if result.satisfied:
            results["summary"]["ok"] += 1
        else:
            if dep_type == DepType.SYSTEM:
                results["summary"]["warning"] += 1
                results["recommendations"].append(f"建议安装: {name} - {desc}")
            else:
                results["summary"]["error"] += 1

    # 检查动作依赖
    actions_index_path = os.path.join(resolver._actions_root, "..", "_meta", "actions.index.json")
    if os.path.exists(actions_index_path):
        try:
            with open(actions_index_path) as f:
                index = json.load(f)
            for action_id, action_meta in index.get("actions", {}).items():
                raw_deps = action_meta.get("deps", [])
                deps = resolver.parse_deps(raw_deps)
                for dep in deps:
                    result = resolver.check_dep(dep)
                    if not result.satisfied:
                        results["recommendations"].append(
                            f"动作 {action_id} 缺少依赖: {dep.name} ({dep.type.value})"
                        )
        except Exception:
            pass

    return results


def print_doctor_report():
    """打印 doctor 报告（展示三策略状态）。"""
    results = doctor()
    print("=" * 60)
    print("Actus Doctor - 启动自检报告")
    print("=" * 60)
    print(f"时间: {results['timestamp']}")
    print()

    print("【依赖检查】")
    for check in results["checks"]:
        status = "✅" if check["satisfied"] else "⚠️"
        strategy = check.get("strategy", "fail")
        strategy_label = {
            "hint": "💡 提示",
            "ephemeral": "⚡ 临时执行",
            "download": "📥 下载",
            "fail": "❌ 缺失",
        }.get(strategy, "❌ 缺失")

        print(f"  {status} {check['name']} ({check['type']}) - {check['description']} [{strategy_label}]")
        if not check["satisfied"]:
            if check.get("fix_command"):
                print(f"     安装命令: {check['fix_command']}")
            if check.get("ephemeral_cmd"):
                print(f"     临时执行: {check['ephemeral_cmd']}")
    print()

    print(f"【统计】总计: {results['summary']['total']} | 正常: {results['summary']['ok']} | 警告: {results['summary']['warning']} | 错误: {results['summary']['error']}")
    print()

    if results["recommendations"]:
        print("【建议安装】")
        for rec in results["recommendations"]:
            print(f"  • {rec}")
        print()

    # 三策略说明
    print("【三策略说明】")
    print("  💡 HINT: 缺依赖时输出安装命令，不硬失败")
    print("  ⚡ EPHEMERAL: 尝试 pipx/npx 临时运行")
    print("  📥 DOWNLOAD: 下载单文件到 _meta/tools/")
    print("  ❌ FAIL: 硬失败（默认行为）")
    print()
    print("=" * 60)


if __name__ == "__main__":
    # 测试
    resolver = DependencyResolver()
    print(f"Actions root: {resolver._actions_root}")
    print(f"Build root: {resolver._build_root}")
