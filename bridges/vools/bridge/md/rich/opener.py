"""
vools.bridge.md.rich.opener — 文件打开器（平台分派 + 错误分类，计划 P4 §4.3）

职责（计划 §4.3 / §7.1 opener 用例）：
- 平台分派：Windows 用 os.startfile；macOS `open` / Linux `xdg-open` 预留分支
  （RichOpener 接口按平台选择，渲染/协议层不感知平台差异）；
- 错误分类：路径不存在 / 无权限 / 无关联程序 / 其它打开失败 / 安全策略拒绝，
  统一映射为 status 模块的错误码与用户可读文案（徽标数据源）；
- 目录打开：os.path.isdir 时打开资源管理器（Windows），无需关联程序检查；
- 白名单 / 越权防护：复用 RichPathResolver 作为唯一门禁（.. 越权、绝对路径
  未 opt-in、扩展名不在白名单、符号链接逃逸一律拒绝并回传对应错误码）；
- 超时语义：宿主在 open_file 请求发出后 5s 内必须回传 open_result；超时使用
  build_pending_status() 的「已请求打开」状态（不阻塞界面，记审计日志）。

安全模型：本模块只负责“打开”与错误分类，不自行拼路径、不静默执行任意命令；
解析一律交给 RichPathResolver（与 linker 同源）。
"""

import os
import platform
import subprocess
from typing import Callable, Optional

from ...core.compat.dataclass_compat import dataclass
from ..errors import MDRichAccessDeniedError, MDRichPathError
from .resolver import RichPathResolver, DEFAULT_ALLOWED_EXTENSIONS
from .scanner import FileLink
from .status import STATUS_MESSAGES, RichStatus, error_status, ok_status

__all__ = [
    "RichOpener",
    "default_opener",
    "build_pending_status",
]

#: Windows 无关联程序错误码（ERROR_NO_ASSOCIATION）
_WINERROR_NO_ASSOC = 1155

#: Windows 拒绝访问 / 需要提升权限错误码
_WINERROR_ACCESS_DENIED = 5
_WINERROR_ELEVATION_REQUIRED = 740


def default_opener(path: str) -> bool:
    """平台默认打开器：用系统关联程序打开文件/目录。

    Windows：os.startfile；macOS：open；Linux：xdg-open（子进程）。
    成功返回 True；失败返回 False（不抛异常，错误分类由 RichOpener 负责）。
    """
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        if system == "Darwin":
            subprocess.Popen(["open", path])
            return True
        subprocess.Popen(["xdg-open", path])
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def build_pending_status() -> RichStatus:
    """「已请求打开」状态（宿主 5s 超时回传用）。

    同步调用无法完全确认异步启动结果，超时视为「已请求打开」而非失败。
    """
    return ok_status("已请求打开")


@dataclass
class RichOpener:
    """文件打开器：存在性检查 + 平台打开 + 错误分类。

    Args:
        root: 允许根目录（md 所在目录）。给定后内部构建 RichPathResolver
            做白名单/越权校验（.. 越界 / 绝对路径未 opt-in / 扩展名拒绝）；
            为 None 时跳过解析校验（仅用于已解析路径的直接打开）。
        build_dir: 产物目录（默认 root/.mdbuild），供 @artifacts 引用。
        opener: 自定义打开函数 fn(path) -> bool；None 使用平台默认。
            注入 fake 打开器是测试安全打开/错误分类的通道，绝不执行真实副作用。
        allow_absolute: 是否放行绝对路径引用（默认 False，与 resolver 对齐）。
    """

    root: Optional[str] = None
    build_dir: Optional[str] = None
    opener: Optional[Callable[[str], bool]] = None
    allow_absolute: bool = False

    def __post_init__(self) -> None:
        self._opener = self.opener if self.opener is not None else default_opener
        if self.root:
            self.resolver = RichPathResolver(
                os.path.abspath(self.root),
                self.build_dir,
                allow_absolute=self.allow_absolute,
                strict_dotdot=True,
                check_realpath=True,
                allowed_extensions=DEFAULT_ALLOWED_EXTENSIONS,
            )
        else:
            self.resolver = None

    # ── 公共入口 ────────────────────────────────────────────

    def open(self, target: str) -> RichStatus:
        """解析并打开目标，返回分类状态（成功/失败统一 RichStatus）。

        - 白名单/越权：resolver 拒绝时回传 E_ACCESS_DENIED / E_UNSUPPORTED_EXT
          / E_PATH_NOT_FOUND；
        - 不存在：E_PATH_NOT_FOUND；
        - 目录：直接打开资源管理器（无需关联程序检查）；
        - 文件：平台打开；PermissionError → E_ACCESS_DENIED；winerror 1155
          → E_NO_ASSOC；其它 OSError → E_OPEN_FAILED。
        """
        if not target or not str(target).strip():
            return error_status("E_PATH_NOT_FOUND", "打开目标为空")
        path = str(target).strip()

        if self.resolver is not None:
            try:
                path = self.resolver.resolve(path)
            except MDRichAccessDeniedError as e:
                return error_status("E_ACCESS_DENIED", str(e))
            except MDRichPathError as e:
                code = getattr(e, "code", "E_PATH_NOT_FOUND")
                if code in STATUS_MESSAGES:
                    return error_status(code, str(e))
                return error_status("E_OPEN_FAILED", str(e))

        if not os.path.exists(path):
            return error_status("E_PATH_NOT_FOUND", f"目标不存在: {path}")

        # 目录：os.startfile 直接打开资源管理器；无需关联程序检查
        if os.path.isdir(path):
            return self._open_with(path)

        return self._open_with(path)

    def open_link(self, link: FileLink) -> RichStatus:
        """从 FileLink 打开（open_file 协议宿主侧入口）。

        优先使用 link.resolved_path（扫描期已解析的绝对路径），否则回退
        重新解析 link.target。link.status 同步写入，供渲染层徽标刷新。
        """
        if not isinstance(link, FileLink):
            return error_status("E_OPEN_FAILED", "非法链接对象")
        target = (link.target or "").strip()
        if not target:
            return error_status("E_PATH_NOT_FOUND", "链接目标为空")

        if link.resolved_path:
            if not os.path.exists(link.resolved_path):
                status = error_status("E_PATH_NOT_FOUND", f"目标不存在: {link.resolved_path}")
            else:
                status = self._open_with(link.resolved_path)
        else:
            status = self.open(target)
        link.status = status
        return status

    # ── 内部 ────────────────────────────────────────────────

    def _open_with(self, path: str) -> RichStatus:
        """调用打开器并分类错误（path 已通过存在性/白名单校验）。"""
        try:
            ok = self._opener(path)
        except PermissionError as e:
            return error_status("E_ACCESS_DENIED", f"无权限访问: {path} ({e})")
        except OSError as e:
            return self._classify_oserror(e, path)
        except Exception as e:  # noqa: BLE001 - 打开器异常统一分类
            return error_status("E_OPEN_FAILED", f"打开异常: {path} ({e})")
        if ok:
            return ok_status(f"已打开: {path}")
        return error_status("E_OPEN_FAILED", f"打开失败: {path}")

    @staticmethod
    def _classify_oserror(exc: OSError, path: str) -> RichStatus:
        """OSError 细分类：无关联程序 / 无权限 / 其它打开失败。"""
        winerror = getattr(exc, "winerror", None)
        if winerror == _WINERROR_NO_ASSOC:
            return error_status("E_NO_ASSOC", f"无关联程序可打开: {path}")
        if winerror in (_WINERROR_ACCESS_DENIED, _WINERROR_ELEVATION_REQUIRED):
            return error_status("E_ACCESS_DENIED", f"无权限访问: {path} ({exc})")
        return error_status("E_OPEN_FAILED", f"打开失败: {path} ({exc})")
