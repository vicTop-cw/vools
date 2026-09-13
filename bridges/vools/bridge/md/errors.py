"""
vools.bridge.md errors — 自定义异常类

提供清晰的错误类型，便于调试和错误处理。
"""
from typing import Optional, Dict, List


class MDBridgeError(Exception):
    """vools.bridge.md 基础异常"""
    def __init__(self, message: str, md_path: Optional[str] = None,
                 block_index: Optional[int] = None):
        self.md_path = md_path
        self.block_index = block_index
        self.message = message
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = [self.message]
        if self.md_path:
            parts.append(f" (file: {self.md_path})")
        if self.block_index is not None:
            parts.append(f" (block: {self.block_index})")
        return "".join(parts)


class MDParseError(MDBridgeError):
    """Markdown 解析错误"""
    pass


class MDDirectiveError(MDBridgeError):
    """指令错误（无效指令、互斥冲突等）"""
    pass


class MDConfigError(MDBridgeError):
    """配置错误（lua 配置加载失败等）"""
    pass


class MDDepsError(MDBridgeError):
    """依赖错误（TOML 解析失败、依赖缺失等）"""
    pass


class MDManifestError(MDBridgeError):
    """清单错误（YAML 读写失败等）"""
    pass


class MDExecutionError(MDBridgeError):
    """执行错误（代码块执行失败、超时等）"""
    pass


class MDImportError(MDBridgeError):
    """导入错误（目标文件不存在、循环导入等）"""
    pass


class MDArtifactError(MDBridgeError):
    """产物错误（哈希计算失败、产物清理失败等）"""
    pass


class MDLibraryError(MDBridgeError):
    """库级错误（扫描失败、manifest 构建失败等）"""
    pass


class MDSandboxError(MDBridgeError):
    """沙箱错误（安全限制、路径越界等）"""
    pass
