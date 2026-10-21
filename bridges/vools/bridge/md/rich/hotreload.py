"""
vools.bridge.md.rich.hotreload — 热更新 L1/L2（计划 P3）

热更新脚本由宿主（CLI --serve / webview2 宿主）执行，绝不内联到用户 HTML：
- L1：全文替换（替换预览 iframe 的 srcdoc，或直接重建 document 根内容）
- L2：仅更新受控区域（标记 `data-rich-l2` 的元素），使用 DOMParser / template
       + replaceChildren 原地替换，不重建 iframe、不重新加载页面

输出是纯字符串 JS（宿主可直接 eval / 注入），依赖零。
"""

import hashlib
import json
from typing import Dict, Optional, Tuple

from ...core.compat.dataclass_compat import dataclass, field

#: 受控区域标记（计划 P3：L2 只更新带该属性的元素）
RICH_L2_ATTR = "data-rich-l2"

HOT_RELOAD_MODES = ("l1", "l2")


@dataclass
class HotReloadRegion:
    """L2 受控区域：selector（CSS 选择器）+ 内容哈希。"""

    selector: str
    content_hash: str = ""


def parse_hot_reload_mode(value: Optional[str]) -> str:
    """解析热更新档位（l1/l2，非法值回退 l1）。"""
    if value and str(value).strip().lower() in HOT_RELOAD_MODES:
        return str(value).strip().lower()
    return "l1"


def content_hash(content: str) -> str:
    """内容指纹（用于跳过无变化的区域）。"""
    return hashlib.md5(content.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════
# L1 / L2 补丁生成（宿主执行脚本）
# ═══════════════════════════════════════════════════════


def build_l1_patch(full_html: str, frame_id: str = "__md_rich_preview__") -> str:
    """L1：全文替换脚本。

    优先替换预览 iframe 的 srcdoc；iframe 不存在时重建 document 根内容。
    """
    html_json = json.dumps(full_html, ensure_ascii=False)
    return (
        "(function(){"
        f"var frame=document.getElementById('{frame_id}');"
        "if(frame){frame.setAttribute('srcdoc',"
        f"{html_json}"
        ");return;}"
        "var root=document.documentElement;"
        f"root.innerHTML={json.dumps('', ensure_ascii=False)};"
        "var t=document.createElement('template');"
        f"t.innerHTML={html_json};"
        "root.replaceChildren.apply(root,t.content.childNodes);"
        "})();"
    )


def build_l2_patch(updates: Dict[str, str]) -> str:
    """L2：仅更新受控区域（selector → 新 HTML）。

    使用 template + replaceChildren 原地替换，不重建 iframe。
    """
    if not updates:
        return ""
    payload = json.dumps(updates, ensure_ascii=False)
    return (
        "(function(){"
        "var updates=" + payload + ";"
        "for(var sel in updates){"
        "var node=document.querySelector(sel);"
        "if(!node)continue;"
        "var t=document.createElement('template');"
        "t.innerHTML=updates[sel];"
        "node.replaceChildren.apply(node,t.content.childNodes);"
        "}"
        "})();"
    )


def hot_reload_patch(
    mode: str,
    *,
    full_html: Optional[str] = None,
    updates: Optional[Dict[str, str]] = None,
    frame_id: str = "__md_rich_preview__",
) -> str:
    """按档位生成热更新补丁（宿主执行）。

    Args:
        mode: l1 / l2
        full_html: L1 全文替换的目标 HTML
        updates: L2 受控区域更新 {selector: new_html}
        frame_id: L1 预览 iframe 的 id

    Returns:
        宿主可执行的 JS 字符串；无有效输入返回空串
    """
    mode = parse_hot_reload_mode(mode)
    if mode == "l1" and full_html is not None:
        return build_l1_patch(full_html, frame_id=frame_id)
    if mode == "l2" and updates:
        return build_l2_patch(updates)
    return ""


# ═══════════════════════════════════════════════════════
# HotReloadManager（跨渲染会话保持区域状态，计划 P3）
# ═══════════════════════════════════════════════════════


class HotReloadManager:
    """L2 区域状态保持：注册受控区域 → 对比哈希 → 只生成有变化的补丁。"""

    def __init__(self, mode: str = "l1"):
        self.mode = parse_hot_reload_mode(mode)
        self._regions: Dict[str, HotReloadRegion] = {}

    # ── 状态保持 ────────────────────────────────────────

    def register_region(self, selector: str, content: str) -> None:
        """注册受控区域（selector → 内容哈希）。"""
        self._regions[selector] = HotReloadRegion(
            selector=selector,
            content_hash=content_hash(content),
        )

    def snapshot(self) -> Dict[str, str]:
        """当前区域快照 {selector: content_hash}。"""
        return {sel: r.content_hash for sel, r in self._regions.items()}

    def diff_updates(self, new_contents: Dict[str, str]) -> Dict[str, str]:
        """与已注册哈希对比，返回有变化的 {selector: new_html}。"""
        updates: Dict[str, str] = {}
        for selector, html in new_contents.items():
            h = content_hash(html)
            prev = self._regions.get(selector)
            if prev is None or prev.content_hash != h:
                updates[selector] = html
                self._regions[selector] = HotReloadRegion(
                    selector=selector,
                    content_hash=h,
                )
        return updates

    # ── 补丁生成 ────────────────────────────────────────

    def patch(
        self,
        *,
        full_html: Optional[str] = None,
        new_contents: Optional[Dict[str, str]] = None,
        frame_id: str = "__md_rich_preview__",
    ) -> str:
        """基于当前档位生成补丁。"""
        if self.mode == "l1":
            return build_l1_patch(full_html, frame_id=frame_id) if full_html is not None else ""
        return build_l2_patch(self.diff_updates(new_contents or {}))


# ═══════════════════════════════════════════════════════
# L2 受控区域提取 + 预览页热更新客户端（计划 P6 宿主集成）
# ═══════════════════════════════════════════════════════


def extract_l2_regions(inner_html: str) -> Dict[str, str]:
    """从 L2 渲染的内层文档提取受控区域 {selector: new_html}。

    selector 形如 `[data-rich-l2="frag-0"]`，供 HotReloadManager.diff_updates
    对比哈希后生成 build_l2_patch 的 updates 参数（宿主 serve 的 reload 使用）。
    """
    import re

    regions: Dict[str, str] = {}
    for m in re.finditer(
        r'<section\s+data-rich-l2="([^"]+)"[^>]*>.*?</section>',
        inner_html,
        re.DOTALL,
    ):
        selector = f'[data-rich-l2="{m.group(1)}"]'
        regions[selector] = m.group(0)
    return regions


def build_hot_reload_client(mode: str, poll_path: str = "/__hot_reload__/poll") -> str:
    """预览页热更新客户端脚本（宿主 serve 时注入，绝不内联到用户 HTML）。

    - 每 1s 轮询 poll_path（带当前版本号 ?v=N），响应为
      {"version": int, "mode": "l1"|"l2", "patch": str}
    - patch 非空时更新本地版本并 eval 执行（L1 替换 iframe srcdoc /
      L2 replaceChildren 受控区域）
    - 依赖零、纯字符串 JS，可在浏览器或 WebView2 容器中运行
    """
    mode = parse_hot_reload_mode(mode)
    path_json = json.dumps(poll_path, ensure_ascii=False)
    return (
        "(function(){"
        "var v=0,t=setInterval(function(){"
        "var x=new XMLHttpRequest();"
        "x.open('GET'," + path_json + "+'?v='+v,true);"
        "x.onreadystatechange=function(){"
        "if(x.readyState===4&&x.status===200){"
        "var r;try{r=JSON.parse(x.responseText);}catch(e){return;}"
        "if(r&&typeof r.patch==='string'&&r.patch){"
        "v=r.version;"
        "try{(0,eval)(r.patch);}catch(e){}"
        "}"
        "}"
        "};"
        "x.send();"
        "},1000);"
        "})();"
    )
