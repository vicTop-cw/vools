"""vools.bridge.md — Markdown 即代码桥接子包"""

from .parser import (
    parse_md,
    ParsedMD,
    FileDirectives,
    CodeBlock,
)
from .directives import (
    FILE_DIRECTIVE_KEYS,
    BLOCK_DIRECTIVE_KEYS,
    parse_block_directives,
    validate_directives,
)
from .config import load_config, load_config_from_block
from .deps import parse_toml, check_deps, DepsReport
from .manifest import (
    write_manifest,
    read_manifest,
    minimal_yaml_parse,
    minimal_yaml_dump,
)
from .artifacts import (
    ensure_build_dir,
    compute_artifact_hash,
    is_artifact_stale,
    clean_build,
    register_artifact,
)
from .runner import (
    run_md,
    run_block,
    run_multiple_md,
    run_library,
    resolve_imports,
    scan_library,
    build_library_manifest,
    load_library_manifest,
)
from .errors import (
    MDBridgeError,
    MDParseError,
    MDDirectiveError,
    MDConfigError,
    MDDepsError,
    MDManifestError,
    MDExecutionError,
    MDImportError,
    MDArtifactError,
    MDLibraryError,
    MDSandboxError,
)
from .logger import get_logger, set_level, add_file_handler, remove_file_handler

__version__ = "0.5.0"

# ── webview2 惰性导出（PEP 562）────────────────────────────
# webview2 模块导入 pythonnet/pywebview，开销 ~900ms；解析/执行/校验
# 场景用不到 GUI 渲染。把重导出改为 __getattr__ 延迟加载，使
# `import vools.bridge.md` / `from vools.bridge.md import parse_md` 等
# 冷启动省掉这 ~0.9s。对外 API 不变：`from vools.bridge.md import
# render_webview2` / `from vools.bridge.md import WebView2Manager` 仍可用。
_WEBVIEW2_EXPORTS = (
    "render_webview2",
    "generate_html_file",
    "send_to_webview",
    "execute_script_in_webview",
    "close_webview_window",
    "get_active_webview_windows",
    "get_webview2_mode",
    "WebView2Config",
    "WebView2Event",
    "WebView2Result",
    "WebView2Manager",
    "WebView2Mode",
    "WebView2Theme",
    "WebView2EventType",
)


def __getattr__(name: str):
    """PEP 562：首次访问 webview2 导出时惰性导入对应子模块。"""
    if name in _WEBVIEW2_EXPORTS:
        import importlib
        mod = importlib.import_module(f"{__name__}.webview2")
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """在既有模块属性基础上追加惰性 webview2 导出名（保持 dir() 完整）。"""
    return sorted(set(globals().keys()) | set(_WEBVIEW2_EXPORTS))

__all__ = [
    # parser
    "parse_md",
    "ParsedMD",
    "FileDirectives",
    "CodeBlock",
    # directives
    "FILE_DIRECTIVE_KEYS",
    "BLOCK_DIRECTIVE_KEYS",
    "parse_block_directives",
    "validate_directives",
    # config
    "load_config",
    "load_config_from_block",
    # deps
    "parse_toml",
    "check_deps",
    "DepsReport",
    # manifest
    "write_manifest",
    "read_manifest",
    "minimal_yaml_parse",
    "minimal_yaml_dump",
    # artifacts
    "ensure_build_dir",
    "compute_artifact_hash",
    "is_artifact_stale",
    "clean_build",
    "register_artifact",
    # runner
    "run_md",
    "run_block",
    "run_multiple_md",
    "run_library",
    "resolve_imports",
    "scan_library",
    "build_library_manifest",
    "load_library_manifest",
    # webview2 (WebView2 GUI 渲染)
    "render_webview2",
    "generate_html_file",
    "send_to_webview",
    "execute_script_in_webview",
    "close_webview_window",
    "get_active_webview_windows",
    "get_webview2_mode",
    "WebView2Config",
    "WebView2Event",
    "WebView2Result",
    "WebView2Manager",
    "WebView2Mode",
    "WebView2Theme",
    "WebView2EventType",
    # errors
    "MDBridgeError",
    "MDParseError",
    "MDDirectiveError",
    "MDConfigError",
    "MDDepsError",
    "MDManifestError",
    "MDExecutionError",
    "MDImportError",
    "MDArtifactError",
    "MDLibraryError",
    "MDSandboxError",
    # logger
    "get_logger",
    "set_level",
    "add_file_handler",
    "remove_file_handler",
]
