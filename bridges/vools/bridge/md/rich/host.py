"""
vools.bridge.md.rich.host — P6 富内容宿主集成（内置查看器 + L1/L2 热更新挂钩）

将 scanner / renderer / hotreload / webview2 组合为宿主闭环：

    RichPreviewHost.open(md_path)
        → scan_rich(doc)
        → render(interactive=True, hot_reload=mode)
        → WebView2Manager.open_preview(html, config)
        → PreviewSession（持有 block_id，供后续热更新推送）

    PreviewSession.refresh()
        → re-scan + render
        → hot_reload_patch（L1 全文 / L2 区域 diff）
        → WebView2Manager.refresh_preview(block_id, patch)

安全模型（P6 分层）：
- 容器层由 WebView2Config 隔离（独立 user_data_dir / open_file 白名单 /
  导航兜底），用户内容只进 renderer 产出的内层文档（自带 L1 CSP）；
- 热更新补丁由 hotreload 模块生成，宿主经 ExecuteScript 推送，
  绝不把用户 HTML 内联进宿主脚本；
- mock 测试只验证 patch 选择与 execute_script 调用，不真实开窗。
"""

from typing import Dict, Optional

from ...core.compat.dataclass_compat import dataclass, field
from ..webview2 import WebView2Config, WebView2Manager, WebView2Result
from .hotreload import (
    HotReloadManager,
    build_l1_patch,
    build_l2_patch,
    extract_l2_regions,
    parse_hot_reload_mode,
)
from .renderer import render
from .scanner import RichConfig, scan_rich


@dataclass
class PreviewSession:
    """一次内置查看器会话：md 源 + WebView2 block_id + 热更新状态。"""

    md_path: str
    manager: "WebView2Manager"
    block_id: str
    build_dir: Optional[str] = None
    config: Optional[RichConfig] = None
    mode: str = "l1"
    hr: Optional[HotReloadManager] = None

    def refresh(self) -> str:
        """重新扫描渲染并按档位生成补丁，推送到预览窗口。

        Returns:
            已推送的补丁 JS（空串表示无变化或推送失败）。
        """
        doc = scan_rich(
            self.md_path,
            build_dir=self.build_dir,
            config=self.config,
        )
        if self.mode == "l2":
            inner = render(doc, interactive=False, hot_reload="l2").html
            updates = extract_l2_regions(inner)
            patch = (self.hr or HotReloadManager(mode="l2")).patch(
                new_contents=updates
            )
        else:
            inner = render(doc, interactive=False, hot_reload="l1").html
            patch = (self.hr or HotReloadManager(mode="l1")).patch(
                full_html=inner
            )
        if not patch:
            return ""
        pushed = self.manager.refresh_preview(self.block_id, patch)
        return patch if pushed else ""

    def close(self) -> bool:
        """关闭预览窗口（block_id 生命周期管理，避免幽灵窗口累积）。"""
        try:
            self.manager.close_window(self.block_id)
            return True
        except Exception:  # noqa: BLE001 窗口可能已被用户手动关闭
            return False


class RichPreviewHost:
    """富内容内置查看器宿主：open → PreviewSession（P6 主入口）。"""

    def __init__(self, manager: Optional[WebView2Manager] = None):
        self.manager = manager or WebView2Manager()
        self._sessions: Dict[str, PreviewSession] = {}

    def open(
        self,
        md_path: str,
        *,
        build_dir: Optional[str] = None,
        config: Optional[RichConfig] = None,
        hot_reload: str = "l1",
        rich_open_root: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        width: int = 960,
        height: int = 720,
        title: str = "vools rich preview",
    ) -> PreviewSession:
        """扫描渲染 md 并在内置 WebView2 查看器中打开（P6 三件套起点）。

        Args:
            md_path: 源 .md 文件
            build_dir: 产物根目录（scan_rich 产物引用）
            config: RichConfig（None 时自动解析 #!rich 指令）
            hot_reload: l1 / l2
            rich_open_root: open_file 协议白名单根目录（None 不启用）
            user_data_dir: WebView2 独立数据目录（None 自动分配临时隔离）
            width/height/title: 查看器窗口尺寸与标题
        """
        mode = parse_hot_reload_mode(hot_reload)
        if config is None:
            config = RichConfig(hot_reload=mode)

        doc = scan_rich(md_path, build_dir=build_dir, config=config)
        # L2 时交互态外层页无 iframe 差异，这里统一产出内层文档，
        # 由宿主预览页承载；L1 时产出 iframe 预览外层页。
        if mode == "l2":
            result = render(doc, interactive=False, hot_reload="l2")
        else:
            result = render(doc, interactive=True, hot_reload="l1")

        wv_config = WebView2Config(
            title=title,
            width=width,
            height=height,
        )
        if rich_open_root is not None:
            wv_config.rich_open_root = rich_open_root

        import time as _time
        import uuid as _uuid

        block_id = f"rich_preview_{int(_time.time())}_{_uuid.uuid4().hex[:6]}"

        r: WebView2Result = self.manager.open_preview(
            result.html,
            config=wv_config,
            block_id=block_id,
            rich_open_root=rich_open_root,
            user_data_dir=user_data_dir,
        )
        if r.status != "ok":
            raise RuntimeError(f"open_preview 失败: {r.error or r.status}")

        session = PreviewSession(
            md_path=md_path,
            manager=self.manager,
            block_id=block_id,
            build_dir=build_dir,
            config=config,
            mode=mode,
            hr=HotReloadManager(mode=mode),
        )
        self._sessions[block_id] = session
        return session

    def sessions(self) -> Dict[str, PreviewSession]:
        """当前存活的预览会话（block_id → session）。"""
        return dict(self._sessions)

    def close_all(self) -> int:
        """关闭全部预览会话，返回成功关闭数。"""
        closed = 0
        for bid, s in list(self._sessions.items()):
            if s.close():
                closed += 1
            self._sessions.pop(bid, None)
        return closed


__all__ = [
    "PreviewSession",
    "RichPreviewHost",
]
