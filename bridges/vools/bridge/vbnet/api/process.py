"""
Process 模块 - 进程管理

封装 API.Process COM 对象，提供进程启动、查询、终止等功能。
"""

from typing import Optional

from ._base import APIBridgeError, _BaseModule


class ProcessModule(_BaseModule):
    """进程管理模块

    提供进程启动、查询、终止、等待等功能。
    """

    _prog_id = "API.Process"

    def Start(self, file_name: str, arguments: Optional[str] = None,
              working_dir: Optional[str] = None) -> int:
        """启动进程

        Args:
            file_name: 可执行文件路径
            arguments: 命令行参数，为 None 时无参数
            working_dir: 工作目录，为 None 时使用默认工作目录

        Returns:
            int: 新进程的 ID，失败返回 0
        """
        args = arguments or ""
        cwd = working_dir or ""
        return self._call_int("Start", file_name, args, cwd)

    def Shell(self, file_name: str, arguments: Optional[str] = None,
              working_dir: Optional[str] = None) -> int:
        """通过 Shell 启动进程

        Args:
            file_name: 可执行文件路径或文档路径
            arguments: 命令行参数，为 None 时无参数
            working_dir: 工作目录，为 None 时使用默认工作目录

        Returns:
            int: 新进程的实例 ID，失败返回 0
        """
        args = arguments or ""
        cwd = working_dir or ""
        return self._call_int("Shell", file_name, args, cwd)

    def GetProcesses(self) -> list:
        """获取所有运行中的进程列表

        Returns:
            list: 进程列表
        """
        return self._call_list("GetProcesses")

    def GetProcessesByName(self, name: str) -> list:
        """按名称获取进程列表

        Args:
            name: 进程名称（不含 .exe 扩展名）

        Returns:
            list: 匹配的进程列表
        """
        return self._call_list("GetProcessesByName", name)

    def Kill(self, process_id: int) -> bool:
        """终止指定进程

        Args:
            process_id: 进程 ID

        Returns:
            bool: 是否成功终止
        """
        return self._call_bool("Kill", process_id)

    def WaitForExit(self, process_id: int, timeout: int = -1) -> bool:
        """等待进程退出

        Args:
            process_id: 进程 ID
            timeout: 超时时间（毫秒），-1 表示无限等待

        Returns:
            bool: 进程是否已退出（超时返回 False）
        """
        return self._call_bool("WaitForExit", process_id, timeout)

    def HasExited(self, process_id: int) -> bool:
        """检查进程是否已退出

        Args:
            process_id: 进程 ID

        Returns:
            bool: 进程是否已退出
        """
        return self._call_bool("HasExited", process_id)

    def GetProcessId(self, hwnd: int) -> int:
        """根据窗口句柄获取进程 ID

        Args:
            hwnd: 窗口句柄

        Returns:
            int: 进程 ID
        """
        return self._call_int("GetProcessId", hwnd)


Process = ProcessModule()
