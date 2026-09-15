"""adapter.py — 适配器引擎 (Phase P1-P5)。

将外部工具（CLI/Quicker/MCP/HTTP）包装为 Actus 动作：
- 协议验证（adapter.schema.json）
- CLI 适配器：包装任意命令行工具
- Quicker 适配器：双向调用 Quicker 动作
- MCP 适配器：桥接 MCP 服务器
- HTTP 适配器：云 API 调用
- 跨适配器工作流编排（flows/）
- 适配器 CLI 集成
"""

import os
import re
import json
import time
import shlex
import shutil
import logging
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

try:
    import jsonschema
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


class AdapterType(Enum):
    CLI = "cli"
    QUICKER = "quicker"
    MCP = "mcp"
    HTTP = "http"


@dataclass
class AdapterResult:
    """适配器执行结果。"""
    success: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    data: Any = None          # JSON 解析后的数据
    duration: float = 0.0
    artifact_path: str = ""   # 输出文件路径

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "data": self.data,
            "duration": self.duration,
            "artifact_path": self.artifact_path,
        }


@dataclass
class AdapterSpec:
    """适配器规范（从 .actus.md 的 #!cfg 解析）。"""
    id: str
    type: AdapterType
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    command: str = ""
    args: List[str] = field(default_factory=list)
    check: str = ""
    install: str = ""
    url: str = ""
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    body: Dict = field(default_factory=dict)
    timeout: int = 30
    starter: str = ""
    action: str = ""
    mcp_server: str = ""
    mcp_tool: str = ""
    params: List[Dict] = field(default_factory=list)
    output_type: str = "text"
    output_path: str = ""
    output_encoding: str = "utf-8"
    trust: str = "community"

    @classmethod
    def from_dict(cls, data: Dict) -> "AdapterSpec":
        """从字典创建。"""
        adapter = data.get("adapter", {})
        return cls(
            id=data["id"],
            type=AdapterType(adapter.get("type", "cli")),
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            tags=data.get("tags", []),
            command=adapter.get("command", ""),
            args=adapter.get("args", []),
            check=adapter.get("check", ""),
            install=adapter.get("install", ""),
            url=adapter.get("url", ""),
            method=adapter.get("method", "GET"),
            headers=adapter.get("headers", {}),
            body=adapter.get("body", {}),
            timeout=adapter.get("timeout", 30),
            starter=adapter.get("starter", ""),
            action=adapter.get("action", ""),
            mcp_server=adapter.get("mcp_server", ""),
            mcp_tool=adapter.get("mcp_tool", ""),
            params=data.get("params", []),
            output_type=data.get("output", {}).get("type", "text"),
            output_path=data.get("output", {}).get("path", ""),
            output_encoding=data.get("output", {}).get("encoding", "utf-8"),
            trust=data.get("trust", "community"),
        )


# ── 参数替换 ──────────────────────────────────────────────────────────────

def _substitute_params(template: str, params: Dict) -> str:
    """替换 ${param} 占位符。"""
    def replacer(match):
        key = match.group(1)
        value = params.get(key, "")
        return str(value)
    return re.sub(r"\$\{([^}]+)\}", replacer, template)


def _substitute_in_args(args: List[str], params: Dict) -> List[str]:
    """在参数列表中替换占位符。"""
    return [_substitute_params(a, params) for a in args]


# ── CLI 适配器 ────────────────────────────────────────────────────────────

class CLIAdapter:
    """CLI 适配器 — 包装任意命令行工具。"""

    def __init__(self, spec: AdapterSpec):
        self.spec = spec

    def check_available(self) -> Tuple[bool, str]:
        """检查工具是否可用。"""
        if self.spec.check:
            try:
                result = subprocess.run(self.spec.check, shell=True, capture_output=True, timeout=10)
                return result.returncode == 0, ""
            except Exception as e:
                return False, str(e)

        # 默认检查：which 命令
        cmd = self.spec.command.split()[0] if self.spec.command else ""
        if not cmd:
            return False, "未指定命令"
        if shutil.which(cmd):
            return True, ""
        return False, f"命令不可用: {cmd}"

    def install_hint(self) -> str:
        """返回安装提示。"""
        if self.spec.install:
            return self.spec.install
        cmd = self.spec.command.split()[0] if self.spec.command else self.spec.id
        return f"请安装 {cmd} 后重试"

    def run(self, params: Dict = None, cwd: str = None) -> AdapterResult:
        """执行 CLI 命令。"""
        start = time.time()
        params = params or {}

        if not self.spec.command:
            return AdapterResult(False, stderr="未指定 command", returncode=-1)

        # 构建命令
        cmd = _substitute_params(self.spec.command, params)
        args = _substitute_in_args(self.spec.args, params)

        # 安全：移除 shell=True，除非命令包含 shell 特殊字符
        use_shell = any(c in cmd for c in "|&;<>$`\\")

        # 构建完整命令
        if use_shell:
            full_cmd = cmd
            if args:
                full_cmd += " " + " ".join(shlex.quote(a) for a in args)
        else:
            full_cmd = [cmd] + args

        logger.info(f"CLI 适配器执行: {full_cmd}")

        try:
            result = subprocess.run(
                full_cmd,
                shell=use_shell,
                capture_output=True,
                text=True,
                cwd=cwd or os.getcwd(),
                timeout=self.spec.timeout,
            )

            # 处理输出
            output_path = ""
            if self.spec.output_path:
                output_path = _substitute_params(self.spec.output_path, params)
                # 如果输出是文件，读取它
                if self.spec.output_type in ("file", "binary"):
                    try:
                        with open(output_path, "r", encoding=self.spec.output_encoding, errors="ignore") as f:
                            file_content = f.read()
                        return AdapterResult(
                            success=result.returncode == 0,
                            stdout=file_content,
                            stderr=result.stderr,
                            returncode=result.returncode,
                            data={"path": output_path, "content": file_content},
                            duration=time.time() - start,
                            artifact_path=output_path,
                        )
                    except Exception:
                        pass  # 文件不存在，返回 stdout

            # JSON 输出
            data = None
            if self.spec.output_type == "json" and result.stdout:
                try:
                    data = json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass

            return AdapterResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
                data=data,
                duration=time.time() - start,
                artifact_path=output_path,
            )

        except subprocess.TimeoutExpired:
            return AdapterResult(False, stderr=f"执行超时 ({self.spec.timeout}s)", returncode=-1)
        except Exception as e:
            return AdapterResult(False, stderr=str(e), returncode=-1)


# ── Quicker 适配器 ────────────────────────────────────────────────────────

class QuickerAdapter:
    """Quicker 适配器 — 双向调用 Quicker 动作。"""

    def __init__(self, spec: AdapterSpec):
        self.spec = spec

    def check_available(self) -> Tuple[bool, str]:
        """检查 Quicker 是否可用。"""
        if self.spec.starter and Path(self.spec.starter).exists():
            return True, ""
        if shutil.which("QuickerStarter.exe"):
            return True, ""
        return False, "Quicker 不可用，请安装 Quicker 并配置 starter 路径"

    def install_hint(self) -> str:
        return "请从 https://getquicker.net 安装 Quicker"

    def run(self, params: Dict = None, cwd: str = None) -> AdapterResult:
        """执行 Quicker 动作。"""
        start = time.time()
        params = params or {}

        if not self.spec.action:
            return AdapterResult(False, stderr="未指定 Quicker 动作 ID", returncode=-1)

        # 构建 Quicker 调用命令
        action_id = self.spec.action
        param_str = json.dumps(params, ensure_ascii=False) if params else "{}"

        # Quicker 命令行调用格式
        if self.spec.starter and Path(self.spec.starter).exists():
            cmd = [self.spec.starter, "runaction", action_id, param_str]
        else:
            cmd = ["QuickerStarter.exe", "runaction", action_id, param_str]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd or os.getcwd(),
                timeout=self.spec.timeout,
            )

            # 解析输出
            data = None
            if result.stdout:
                try:
                    data = json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass

            return AdapterResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
                data=data,
                duration=time.time() - start,
            )

        except subprocess.TimeoutExpired:
            return AdapterResult(False, stderr=f"执行超时 ({self.spec.timeout}s)", returncode=-1)
        except Exception as e:
            return AdapterResult(False, stderr=str(e), returncode=-1)


# ── HTTP 适配器 ───────────────────────────────────────────────────────────

class HTTPAdapter:
    """HTTP 适配器 — 调用云 API。"""

    def __init__(self, spec: AdapterSpec):
        self.spec = spec

    def check_available(self) -> Tuple[bool, str]:
        """检查网络连通性。"""
        if not self.spec.url:
            return False, "未指定 URL"
        try:
            req = urllib.request.Request(self.spec.url, method="HEAD")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return True, ""
        except Exception as e:
            return False, str(e)

    def install_hint(self) -> str:
        return "HTTP 适配器无需安装，请检查网络"

    def run(self, params: Dict = None, cwd: str = None, local_vars: Dict = None) -> AdapterResult:
        """执行 HTTP 请求。"""
        start = time.time()
        params = params or {}

        if not self.spec.url:
            return AdapterResult(False, stderr="未指定 URL", returncode=-1)

        url = _substitute_params(self.spec.url, params)
        method = self.spec.method.upper()
        timeout = self.spec.timeout

        # 构建请求
        data = None
        if method in ("POST", "PUT", "PATCH"):
            body = self.spec.body
            if local_vars:
                for k, v in local_vars.items():
                    body[k] = v
            data = json.dumps(body).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            **self.spec.headers,
        }

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                try:
                    parsed = json.loads(body)
                except json.JSONDecodeError:
                    parsed = None
                return AdapterResult(
                    success=200 <= resp.status < 300,
                    stdout=body,
                    returncode=resp.status,
                    data=parsed,
                    duration=time.time() - start,
                )
        except urllib.error.HTTPError as e:
            return AdapterResult(False, stderr=str(e), returncode=e.code, duration=time.time() - start)
        except Exception as e:
            return AdapterResult(False, stderr=str(e), returncode=-1, duration=time.time() - start)


# ── MCP 适配器 ────────────────────────────────────────────────────────────

class MCPAdapter:
    """MCP 适配器 — 桥接 MCP 服务器。"""

    def __init__(self, spec: AdapterSpec):
        self.spec = spec

    def check_available(self) -> Tuple[bool, str]:
        """检查 MCP 服务器是否可用。"""
        if not self.spec.mcp_server:
            return False, "未指定 MCP 服务器"
        # 检查 MCP 服务器是否在配置中
        mcp_config = Path.home() / ".actus" / "mcp_servers.json"
        if mcp_config.exists():
            try:
                with open(mcp_config) as f:
                    servers = json.load(f)
                if self.spec.mcp_server in servers:
                    return True, ""
            except Exception:
                pass
        return False, f"MCP 服务器 '{self.spec.mcp_server}' 未配置"

    def install_hint(self) -> str:
        return f"请在 ~/.actus/mcp_servers.json 中配置 {self.spec.mcp_server}"

    def run(self, params: Dict = None, cwd: str = None) -> AdapterResult:
        """执行 MCP 工具调用。"""
        start = time.time()
        params = params or {}

        if not self.spec.mcp_tool:
            return AdapterResult(False, stderr="未指定 MCP 工具", returncode=-1)

        # 通过 actus mcp 桥接
        # 实际实现需要与 MCP 服务器通信
        # 这里提供框架，具体实现依赖 MCP 客户端
        logger.info(f"MCP 适配器: {self.spec.mcp_server}.{self.spec.mcp_tool}")

        return AdapterResult(
            False,
            stderr="MCP 适配器需要 MCP 客户端支持，请使用 actus mcp 命令",
            returncode=-1,
            duration=time.time() - start,
        )


# ── 适配器注册表 ──────────────────────────────────────────────────────────

class AdapterRegistry:
    """适配器注册表。"""

    def __init__(self, adapters_dir: str = None):
        if adapters_dir is None:
            adapters_dir = os.path.join(os.getcwd(), "actions", "adapters")
        self.adapters_dir = Path(adapters_dir)
        self._adapters: Dict[str, AdapterSpec] = {}

    def discover(self) -> List[AdapterSpec]:
        """发现所有适配器。"""
        specs = []
        if not self.adapters_dir.exists():
            return specs

        for md_file in self.adapters_dir.rglob("*.actus.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                # 解析 #!cfg 块 — 支持两种格式：
                # 1. ```json #!cfg\n...\n```（标准 markdown 代码块）
                # 2. #!cfg\n```json\n...\n```（#!cfg 在代码块前）
                cfg = None
                # 尝试格式 1: ```json #!cfg
                cfg_match = re.search(r"```json\s*#!cfg\s*\n(.*?)```", content, re.DOTALL)
                if cfg_match:
                    cfg = json.loads(cfg_match.group(1))
                else:
                    # 尝试格式 2: #!cfg 在代码块前
                    cfg_match = re.search(r"#!cfg\s*\n```json\s*\n(.*?)```", content, re.DOTALL)
                    if cfg_match:
                        cfg = json.loads(cfg_match.group(1))

                if cfg and "adapter" in cfg:
                    spec = AdapterSpec.from_dict(cfg)
                    specs.append(spec)
                    self._adapters[spec.id] = spec
            except Exception as e:
                logger.warning(f"解析适配器失败 {md_file}: {e}")

        return specs

    def get(self, adapter_id: str) -> Optional[AdapterSpec]:
        """获取适配器规范。"""
        if adapter_id not in self._adapters:
            self.discover()
        return self._adapters.get(adapter_id)

    def create_adapter(self, spec: AdapterSpec):
        """创建适配器实例。"""
        if spec.type == AdapterType.CLI:
            return CLIAdapter(spec)
        elif spec.type == AdapterType.QUICKER:
            return QuickerAdapter(spec)
        elif spec.type == AdapterType.HTTP:
            return HTTPAdapter(spec)
        elif spec.type == AdapterType.MCP:
            return MCPAdapter(spec)
        raise ValueError(f"未知适配器类型: {spec.type}")


# ── 便捷函数 ──────────────────────────────────────────────────────────────

def run_adapter(adapter_id: str, params: Dict = None, cwd: str = None) -> AdapterResult:
    """便捷函数：运行适配器。"""
    registry = AdapterRegistry()
    spec = registry.get(adapter_id)
    if not spec:
        return AdapterResult(False, stderr=f"适配器不存在: {adapter_id}", returncode=-1)
    adapter = registry.create_adapter(spec)
    return adapter.run(params, cwd)


def validate_adapter_spec(spec: AdapterSpec) -> Tuple[bool, List[str]]:
    """验证适配器规范。"""
    issues = []

    # 基本验证
    if not spec.id:
        issues.append("缺少 id")
    if not spec.type:
        issues.append("缺少 adapter.type")

    # 类型特定验证
    if spec.type == AdapterType.CLI:
        if not spec.command:
            issues.append("CLI 适配器缺少 command")
    elif spec.type == AdapterType.QUICKER:
        if not spec.action:
            issues.append("Quicker 适配器缺少 action")
    elif spec.type == AdapterType.HTTP:
        if not spec.url:
            issues.append("HTTP 适配器缺少 url")
    elif spec.type == AdapterType.MCP:
        if not spec.mcp_server:
            issues.append("MCP 适配器缺少 mcp_server")
        if not spec.mcp_tool:
            issues.append("MCP 适配器缺少 mcp_tool")

    # JSON Schema 验证（如果可用）
    if _HAS_JSONSCHEMA:
        try:
            schema_path = Path(__file__).parent.parent.parent / "contracts" / "adapter.schema.json"
            if schema_path.exists():
                with open(schema_path) as f:
                    schema = json.load(f)
                # 构建完整数据
                data = {
                    "id": spec.id,
                    "name": spec.name,
                    "description": spec.description,
                    "version": spec.version,
                    "author": spec.author,
                    "tags": spec.tags,
                    "adapter": {
                        "type": spec.type.value,
                        "command": spec.command,
                        "args": spec.args,
                        "check": spec.check,
                        "install": spec.install,
                        "url": spec.url,
                        "method": spec.method,
                        "headers": spec.headers,
                        "body": spec.body,
                        "timeout": spec.timeout,
                        "starter": spec.starter,
                        "action": spec.action,
                        "mcp_server": spec.mcp_server,
                        "mcp_tool": spec.mcp_tool,
                    },
                    "params": spec.params,
                    "output": {
                        "type": spec.output_type,
                        "path": spec.output_path,
                        "encoding": spec.output_encoding,
                    },
                    "trust": spec.trust,
                }
                jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            issues.append(f"Schema 验证失败: {e.message}")
        except Exception as e:
            logger.warning(f"Schema 验证异常: {e}")

    return len(issues) == 0, issues


__all__ = [
    'AdapterRegistry',
    'AdapterResult',
    'AdapterSpec',
    'AdapterType',
    'CLIAdapter',
    'HTTPAdapter',
    'MCPAdapter',
    'QuickerAdapter',
    'logger',
    'run_adapter',
    'validate_adapter_spec'
]
