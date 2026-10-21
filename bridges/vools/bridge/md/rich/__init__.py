"""
vools.bridge.md.rich — 富内容展示与文件链接能力（P0/P1 骨架 + P2~P4 补全）

子模块：
- resolver:  RichPathResolver 路径解析器（.. 越权拒绝 + @artifacts 产物引用）
- status:    错误/状态模型与文案映射
- protocol:  宿主消息格式 open_file/open_result/render 与 request_id 匹配
- sanitize:  HTML L1 基础过滤 + CSP 策略表 + SVG 净化（sanitize_svg）
- renderer:  内嵌卡片渲染抽象（L1 静态卡片 / L4 源码展示卡片）+ RichDoc 渲染
- scanner:   正文扫描（scan_rich / RichDoc / #!rich 文件级指令）
- linker:    文件链接路由（FileLinkRouter：相对路径/@artifacts/realpath 校验）
- opener:    文件打开器（RichOpener：平台分派 + 错误分类 + 白名单校验，P4）
- hotreload: 热更新 L1（全文替换）/ L2（受控区域更新）补丁生成

P0 出口：resolver 单测全绿（含 .. 越权样本）、status 文案映射全绿、
protocol 序列化往返通过。
P1 出口：恶意 HTML 样本（script/onerror/javascript:/iframe）全部被 L1 剥离；
#!html level=4 源码展示含复制/折叠；CLI rich 命令可渲染最小样例。
P2~P4 出口：scan_rich/#!rich 解析/SVG 净化/文件链接路由/L1/L2 热更新单测全绿。
"""

from .resolver import RichPathResolver, ARTIFACTS_REF_PREFIX
from .status import (
    OK_CODE,
    STATUS_MESSAGES,
    RichStatus,
    error_status,
    message_for,
    ok_status,
)
from .protocol import (
    OPEN_FILE,
    OPEN_RESULT,
    RENDER,
    build_open_file,
    build_open_result,
    build_render,
    deserialize,
    matches_request,
    serialize,
    validate_message,
)
from .scanner import (
    RichConfig,
    RichDoc,
    SVGFragment,
    HTMLFragment,
    FileLink,
    ArtifactRef,
    extract_rich_directive,
    parse_rich_config,
    scan_rich,
)
from .linker import FileLinkRouter, detect_link_kind
from .opener import RichOpener, build_pending_status, default_opener
from .hotreload import (
    HotReloadManager,
    HotReloadRegion,
    build_hot_reload_client,
    build_l1_patch,
    build_l2_patch,
    extract_l2_regions,
    hot_reload_patch,
    parse_hot_reload_mode,
)
from .renderer import RenderResult, build_preview_page, render
from .sanitize import sanitize_html_fragment, sanitize_svg
from .host import PreviewSession, RichPreviewHost

__all__ = [
    # resolver
    "RichPathResolver",
    "ARTIFACTS_REF_PREFIX",
    # status
    "OK_CODE",
    "STATUS_MESSAGES",
    "RichStatus",
    "message_for",
    "ok_status",
    "error_status",
    # protocol
    "OPEN_FILE",
    "OPEN_RESULT",
    "RENDER",
    "build_open_file",
    "build_open_result",
    "build_render",
    "serialize",
    "deserialize",
    "validate_message",
    "matches_request",
    # scanner
    "RichConfig",
    "RichDoc",
    "SVGFragment",
    "HTMLFragment",
    "FileLink",
    "ArtifactRef",
    "extract_rich_directive",
    "parse_rich_config",
    "scan_rich",
    # linker
    "FileLinkRouter",
    "detect_link_kind",
    # opener
    "RichOpener",
    "build_pending_status",
    "default_opener",
    # hotreload
    "HotReloadManager",
    "HotReloadRegion",
    "build_hot_reload_client",
    "build_l1_patch",
    "build_l2_patch",
    "extract_l2_regions",
    "hot_reload_patch",
    "parse_hot_reload_mode",
    # renderer
    "RenderResult",
    "build_preview_page",
    "render",
    # sanitize
    "sanitize_html_fragment",
    "sanitize_svg",
    # host (P6 宿主集成)
    "PreviewSession",
    "RichPreviewHost",
]
