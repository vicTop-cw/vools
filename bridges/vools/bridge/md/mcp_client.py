"""
vools.bridge.md.mcp_client — 极简 MCP stdio 客户端（零第三方依赖）

在 MD 代码块中通过 stdio 协议调用外部 MCP 服务器。
支持 JSON-RPC 2.0 / initialize / tools/list / tools/call 三个方法。

用法（在 .md 文件中）：

    ```mcp #!server=filesystem #!tool=read_file
    {"path": "README.md"}
    ```

    ```mcp #!server=http://localhost:8080/mcp #!tool=search
    {"query": "actus"}
    ```

配置（mcp.json，与 MCP SDK 同格式）：

    {
      "mcpServers": {
        "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]}
      }
    }
"""


__all__ = [
    "MCPClient",
    "MCPClientError",
    "execute_mcp_block",
    "load_mcp_config",
    "find_mcp_server",
]


import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════

MCP_PROTOCOL_VERSION = "2024-11-05"

#: mcp.json 配置文件查找顺序（相对工作目录）
_MCP_CONFIG_NAMES = ("mcp.json", ".mcp.json", "mcp/mcp.json")


# ═══════════════════════════════════════════════════════
# 异常
# ═══════════════════════════════════════════════════════


class MCPClientError(Exception):
    """MCP 客户端错误。"""

    def __init__(self, message: str, code: str = "E_MCP_ERROR"):
        super().__init__(message)
        self.code = code


# ═══════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════


def load_mcp_config(workdir: Optional[str] = None) -> Dict[str, Dict]:
    """
    加载 mcp.json 配置。

    Args:
        workdir: 搜索起始目录（默认 os.getcwd()）

    Returns:
        {"server_name": {"command": ..., "args": [...], ...}, ...}

    Raises:
        MCPClientError: 找不到配置文件或格式错误
    """
    base = workdir or os.getcwd()
    config_path = None
    for name in _MCP_CONFIG_NAMES:
        cand = os.path.join(base, name)
        if os.path.isfile(cand):
            config_path = cand
            break

    if config_path is None:
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise MCPClientError(f"mcp.json 读取失败: {e}", code="E_MCP_CONFIG_READ")

    servers = raw.get("mcpServers", raw)
    if not isinstance(servers, dict):
        raise MCPClientError("mcp.json 格式错误: 缺少 mcpServers 对象", code="E_MCP_CONFIG_SCHEMA")

    return servers


def find_mcp_server(name: str, workdir: Optional[str] = None) -> Optional[Dict]:
    """
    按名字查找 MCP 服务器配置。

    Args:
        name: 服务器名（如 "filesystem"）
        workdir: 工作目录

    Returns:
        配置字典，未找到返回 None
    """
    config = load_mcp_config(workdir)
    return config.get(name)


# ═══════════════════════════════════════════════════════
# MCPClient（stdio 传输）
# ═══════════════════════════════════════════════════════


class MCPClient:
    """MCP stdio 客户端。

    通过子进程 stdio 与 MCP 服务器通信，使用 JSON-RPC 2.0。

    生命周期：
        client = MCPClient({"command": "npx", "args": [...]})
        try:
            client.connect()
            tools = client.list_tools()
            result = client.call_tool("read_file", {"path": "a.txt"})
        finally:
            client.close()
    """

    def __init__(
        self,
        server_config: Dict,
        *,
        timeout: int = 30,
        cwd: Optional[str] = None,
        env: Optional[Dict] = None,
    ):
        """
        Args:
            server_config: MCP 服务器配置（command / args / env）
            timeout: 单次调用超时（秒），默认 30
            cwd: 子进程工作目录
            env: 附加环境变量
        """
        self._config = server_config
        self._timeout = timeout
        self._cwd = cwd
        self._env = env
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._req_id = 0
        self._connected = False

    # ── 连接 / 断开 ──

    def connect(self) -> None:
        """启动 MCP 服务器子进程并完成 initialize 握手。"""
        if self._connected:
            return

        cmd = self._config.get("command", "")
        if not cmd:
            raise MCPClientError("MCP 配置缺少 command", code="E_MCP_NO_COMMAND")

        # 检查命令是否在 PATH 中（相对路径允许，如 ./server.py）
        if os.path.sep not in cmd and not cmd.startswith("."):
            if shutil.which(cmd) is None:
                raise MCPClientError(
                    f"MCP 服务器命令不存在: {cmd}",
                    code="E_MCP_CMD_NOT_FOUND",
                )

        args = list(self._config.get("args", []) or [])
        env = dict(os.environ)
        env.update(self._config.get("env", {}) or {})
        if self._env:
            env.update(self._env)
        # 强制子进程 stdout 使用 UTF-8（Windows 默认 cp936 会导致 JSON 乱码）
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")

        # 如果是 .py 文件且没指定解释器，用当前 python
        if args and args[0].endswith(".py") and not shutil.which(cmd):
            env["PYTHONPATH"] = env.get("PYTHONPATH", "") + os.pathsep + os.getcwd()

        try:
            self._proc = subprocess.Popen(
                [cmd] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._cwd,
                env=env,
                bufsize=0,  # unbuffered: avoid pipe deadlock
            )
        except Exception as e:
            raise MCPClientError(f"MCP 服务器启动失败: {e}", code="E_MCP_SPAWN")

        # initialize 握手
        self._rpc("initialize", {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"roots": {"listChanged": False}},
            "clientInfo": {"name": "vools-bridge-md", "version": "0.1.0"},
        })

        # notifications/initialized（不期待回执）
        self._send_notification("notifications/initialized")

        self._connected = True

    def close(self) -> None:
        """关闭子进程。"""
        if self._proc:
            try:
                self._send_notification("notifications/cancelled", {
                    "requestId": self._req_id,
                    "reason": "client closed",
                })
            except Exception:
                pass
            try:
                if self._proc.poll() is None:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
            except Exception:
                pass
            self._proc = None
        self._connected = False

    # ── 工具 ──

    def list_tools(self) -> List[Dict]:
        """列出服务器可用工具。"""
        result = self._rpc("tools/list", {})
        return result.get("tools", [])

    def call_tool(self, name: str, args: Dict) -> Any:
        """调用 MCP 工具。"""
        result = self._rpc("tools/call", {"name": name, "arguments": args or {}})
        return result

    # ── 内部 ──

    def _rpc(self, method: str, params: Dict) -> Dict:
        """发送 JSON-RPC 请求并等待响应。"""
        if not self._proc or self._proc.poll() is not None:
            raise MCPClientError("MCP 服务器未连接或已退出", code="E_MCP_DISCONNECTED")

        with self._lock:
            self._req_id += 1
            req_id = self._req_id
            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params,
            }

            line = json.dumps(payload, ensure_ascii=False) + "\n"
            try:
                self._proc.stdin.write(line.encode("utf-8"))
                self._proc.stdin.flush()
            except Exception as e:
                raise MCPClientError(f"写入 MCP 请求失败: {e}", code="E_MCP_WRITE")

            # 读取响应（按行；匹配 id）
            deadline = time.time() + self._timeout
            while time.time() < deadline:
                try:
                    raw_line = self._proc.stdout.readline()
                except Exception as e:
                    raise MCPClientError(f"读取 MCP 响应失败: {e}", code="E_MCP_READ")

                if not raw_line:
                    # stdout 关闭，检查子进程状态
                    if self._proc.poll() is not None:
                        stderr_tail = b""
                        if self._proc.stderr:
                            try:
                                stderr_tail = self._proc.stderr.read()
                            except Exception:
                                pass
                        raise MCPClientError(
                            f"MCP 服务器退出(code={self._proc.returncode}): {stderr_tail.decode('utf-8', errors='replace')}",
                            code="E_MCP_EXIT",
                        )
                    continue  # 可能非 JSON 行

                resp_line = raw_line.decode("utf-8", errors="replace").strip()
                if not resp_line:
                    continue
                try:
                    resp = json.loads(resp_line)
                except json.JSONDecodeError:
                    continue  # 可能是日志，跳过

                if resp.get("id") != req_id:
                    # 非匹配响应（如 notification），跳过
                    continue

                if "error" in resp:
                    err = resp["error"]
                    raise MCPClientError(
                        f"MCP 错误 {err.get('code')}: {err.get('message')}",
                        code="E_MCP_RPC_ERROR",
                    )
                return resp.get("result", {})

            raise MCPClientError(
                f"MCP 请求超时 ({self._timeout}s): {method}",
                code="E_MCP_TIMEOUT",
            )

    def _send_notification(self, method: str, params: Optional[Dict] = None) -> None:
        """发送 JSON-RPC notification（无 id，不期待回执）。"""
        if not self._proc:
            return
        payload = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        try:
            self._proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            self._proc.stdin.flush()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════
# MD 块执行入口
# ═══════════════════════════════════════════════════════


def execute_mcp_block(
    content: str,
    directives: Dict[str, str],
    config: Dict,
    timeout: int = 30,
) -> Tuple[str, str, int]:
    """
    执行 mcp 代码块。

    支持的指令：
    - server: MCP 服务器名（来自 mcp.json）或完整命令（如 "npx -y xxx"）
    - tool: 工具名（必填，除非用 `list` 列出工具）
    - timeout: 调用超时（秒，覆盖默认 30）

    代码块内容是 JSON 参数（直接传给工具）。

    语法示例：
        ```mcp #!server=filesystem #!tool=read_file
        {"path": "README.md"}
        ```

        ```mcp #!server=filesystem #!tool=list
        ```
        空内容 = 调用 list_tools()

    Returns:
        (stdout, stderr, exit_code)
    """
    server = directives.get("server", "").strip()
    tool = directives.get("tool", "").strip()
    block_timeout = int(directives.get("timeout", str(timeout)) or timeout)
    workdir = config.get("workdir", os.getcwd()) if isinstance(config, dict) else None

    if not server:
        return "", "mcp 块缺少 #!server=<name> 指令", 1

    if not tool:
        return "", "mcp 块缺少 #!tool=<name> 指令", 1

    # 解析参数：块内容是 JSON
    args: Dict = {}
    content = (content or "").strip()
    if content:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                args = parsed
            else:
                args = {"value": parsed}
        except json.JSONDecodeError as e:
            return "", f"mcp 块参数必须是 JSON 对象: {e}", 1

    # 查找服务器配置
    server_cfg = find_mcp_server(server, workdir)
    if server_cfg is None:
        # 尝试作为内联命令（空格分隔）
        parts = server.split()
        if parts:
            server_cfg = {"command": parts[0], "args": parts[1:]}
        else:
            return "", f"未找到 MCP 服务器: {server}", 1

    # 建立客户端
    client = MCPClient(server_cfg, timeout=block_timeout, cwd=workdir)
    try:
        client.connect()
        if tool == "list":
            tools = client.list_tools()
            lines = []
            for t in tools:
                name = t.get("name", "")
                desc = t.get("description", "") or ""
                lines.append(f"- {name}: {desc}")
            return "\n".join(lines) or "(no tools)", "", 0

        result = client.call_tool(tool, args)
        return _format_tool_result(result), "", 0
    except MCPClientError as e:
        return "", f"[mcp] {e}", 1
    except Exception as e:
        return "", f"[mcp] 未预期错误: {e}", 1
    finally:
        client.close()


def _format_tool_result(result: Any) -> str:
    """将 tools/call 结果格式化为可读文本。"""
    if not isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, indent=2)

    # MCP 工具结果通常是 {"content": [...], "isError": false}
    content = result.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type", "text")
                if item_type == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        text = "\n".join(parts)
        if result.get("isError"):
            return text  # 错误内容保留，但 exit code 已由调用方置 1
        return text

    if "structuredContent" in result:
        return json.dumps(result["structuredContent"], ensure_ascii=False, indent=2)

    return json.dumps(result, ensure_ascii=False, indent=2)