# -*- coding: utf-8 -*-
"""vools.actus.clipboard - Actus 剪贴板能力（vools.reactive 落地）。

把 rx 子项目的剪贴板能力（ClipData / ClipboardDispatcher / from_clipboard /
write_to_clipboard）接入 actus，收敛为「配置 + 动作」式交互：调用方只需提供
配置信息并指定动作方式即可完成剪贴板读写与监控，无需编写链路控制代码。

    动作（读 / 写 / 清空 / 监控）：
        clip_read()                      -> ClipData     读当前剪贴板
        clip_write(text, *, tags, source) -> ClipData    写文本到剪贴板
        clip_clear()                     -> None         清空剪贴板
        clip_watch(**config)             -> ClipWatcher  监控剪贴板变更（可 stop）

    配置（clip_watch 参数，透传底层 Dispatcher）：
        interval       轮询间隔（秒，默认 0.2）
        backend        "auto" | "win32" | "polling"（默认 auto）
        change_types   白名单；None 表示全部分发
        tags           默认附加标签
        filter_self    是否过滤「自己写回」分发（默认 True）
        on_text / on_change / on_error   事件回调

依赖：vools.reactive（rx 子项目提供 vools.reactive 命名空间，需在 sys.path 上）。
不可用时本模块各入口抛 ImportError 并附原因。

典型用法：
    >>> from vools.actus import clip_read, clip_write, clip_watch
    >>> cd = clip_read()                       # 动作：读
    >>> clip_write("老板，这是要写入的文本", tags=["actus"])   # 动作：写
    >>> w = clip_watch(interval=0.1, on_text=lambda cd: print(cd.content))
    >>> w.stop()                               # 动作：停
"""

import math
from typing import Any, Callable, Iterable, Optional

try:  # rx 命名空间可能不可用（monitoring 子模块整体受条件导入保护）
    from vools.reactive.monitoring.clipboard import (
        ClipChangeType,
        ClipData,
        from_clipboard,
    )
except Exception as _clip_import_err:  # pragma: no cover - 依赖缺失路径
    _CLIP_IMPORT_ERROR = _clip_import_err

    ClipChangeType = None  # type: ignore[assignment]
    ClipData = None  # type: ignore[assignment]
    from_clipboard = None  # type: ignore[assignment]

    def _raise_missing() -> None:
        raise ImportError(
            "vools.reactive 剪贴板能力不可用"
            "（需 rx 子项目在 sys.path 上提供 vools.reactive 命名空间）: "
            + repr(_CLIP_IMPORT_ERROR)
        )

else:
    _CLIP_IMPORT_ERROR = None

    def _raise_missing() -> None:  # pragma: no cover - 正常路径不可达
        raise AssertionError("unreachable")


__all__ = [
    "ClipData",
    "ClipChangeType",
    "ClipWatcher",
    "clip_read",
    "clip_write",
    "clip_clear",
    "clip_watch",
]


def _shared_reader() -> Any:
    """复用 rx 模块内共享的 _ClipboardReader（Win32 进程级剪贴板单例）。

    说明：_ClipboardReader 是 rx 内部私有符号；actus 封装层与 rx 同仓库，
    直接引用以复用其类级剪贴板锁与 tk 缓存，避免创建额外实例竞争剪贴板。
    """
    from vools.reactive.monitoring.clipboard import _ClipboardReader

    return _ClipboardReader.shared()


# ====================================================================
# 动作：读 / 写 / 清空
# ====================================================================


def clip_read() -> "ClipData":
    """动作：读当前剪贴板，返回 ClipData。

    空剪贴板返回 change_type=CLEAR 的 ClipData；读失败时 content=None 且
    metadata["error"] 携带原因。
    """
    if ClipData is None:
        _raise_missing()
    change_type, content, files, meta = _shared_reader().read()
    return ClipData.now(
        content=content,
        files=files,
        change_type=change_type,
        metadata=meta,
    )


def clip_write(
    text: str,
    *,
    tags: Optional[Iterable[str]] = None,
    source: Optional[str] = None,
) -> "ClipData":
    """动作：把文本写入系统剪贴板，返回表示已写入内容的 ClipData。

    参数：
        text:    要写入的文本（None 视为空串；bytes/bytearray/memoryview
                 一律拒绝——历史上 bytes 会被 str() 静默变形为 "b'...'" 写入
                 剪贴板，调用者毫无察觉，属静默数据污染，T0r4.5 收口改为硬报错）
        tags:    附加标签
        source:  来源标识（写入 metadata._source）
    """
    if ClipData is None:
        _raise_missing()
    if text is None:
        text = ""
    elif isinstance(text, (bytes, bytearray, memoryview)):
        raise TypeError(
            "clip_write 拒绝 bytes-like 输入（%s）：二进制内容静默 str() 会变形为 "
            "\"b'...'\" 写入剪贴板；请先显式 decode('utf-8', errors=...) 或改为写入文本"
            % type(text).__name__
        )
    else:
        text = str(text)
    _shared_reader().write(text, [], ClipChangeType.TEXT)
    meta: dict = {}
    if source:
        meta["_source"] = source
    return ClipData.now(
        content=text,
        change_type=ClipChangeType.TEXT,
        tags=tags or (),
        metadata=meta,
    )


def clip_clear() -> None:
    """动作：清空系统剪贴板。"""
    if ClipData is None:
        _raise_missing()
    _shared_reader()._clear()


# ====================================================================
# 动作：监控
# ====================================================================


class ClipWatcher:
    """剪贴板监控句柄；持有底层 Dispatcher 与订阅，提供 stop()。

    事件回调（在 Dispatcher 的 worker / polling 线程触发，注意线程安全）：
        on_text(cd):   仅文本变更时调用
        on_change(cd): 任意变更时调用（含文本）
        on_error(e):   分发异常时调用

    用法：
        w = clip_watch(on_text=lambda cd: print(cd.content))
        ...
        w.stop()
    """

    def __init__(
        self,
        *,
        interval: float = 0.2,
        backend: str = "auto",
        change_types: Optional[Iterable[Any]] = None,
        tags: Iterable[str] = (),
        filter_self: bool = True,
        on_text: Optional[Callable[["ClipData"], Any]] = None,
        on_change: Optional[Callable[["ClipData"], Any]] = None,
        on_error: Optional[Callable[[Exception], Any]] = None,
    ) -> None:
        if ClipData is None:
            _raise_missing()
        # BUG-371: 原实现零校验——interval<=0 / 非数字 / NaN / inf 直接透传
        # 底层 Dispatcher。polling 后端虽有 clamp(0.02) 兜底，但 clamp 是静默
        # 行为：调用方传 0 / -1 期望"立即轮询 / 不轮询"的语义并未兑现，且
        # win32 事件后端下 interval 不参与轮询，非法值不会被任何后端报错，
        # 存在 busy-loop（interval=0/-1 落在 clamp 下限仍可接受，但语义不可见）
        # 与接口契约缺失双重风险。收口为显式 fail-fast 校验。
        if isinstance(interval, bool) or not isinstance(interval, (int, float)):
            raise TypeError(
                f"clip_watch/ClipWatcher 的 interval 需要数字，收到 "
                f"{type(interval).__name__}: {interval!r}")
        if not math.isfinite(interval):
            raise ValueError(
                f"clip_watch/ClipWatcher 的 interval 必须是有限数值，收到 {interval!r}")
        if interval <= 0:
            raise ValueError(
                f"clip_watch/ClipWatcher 的 interval 必须 > 0"
                f"（杜绝 busy-loop），收到 {interval}")
        self._on_text = on_text
        self._on_change = on_change
        self._subject, self._dispatcher = from_clipboard(
            interval=interval,
            backend=backend,
            change_types=change_types,
            tags=tags,
            filter_self=filter_self,
            auto_start=True,
        )
        self._sub = self._subject.subscribe(
            on_next=self._route,
            on_error=on_error,
        )

    # ---- 事件路由 ----------------------------------------------------
    def _route(self, cd: "ClipData") -> None:
        if self._on_text is not None and cd.change_type == ClipChangeType.TEXT:
            self._on_text(cd)
        if self._on_change is not None:
            self._on_change(cd)

    # ---- 生命周期 ----------------------------------------------------
    @property
    def is_running(self) -> bool:
        return bool(getattr(self._dispatcher, "is_running", False))

    @property
    def dispatcher(self) -> Any:
        """底层 ClipboardDispatcher（调试 / 高级用法）。"""
        return self._dispatcher

    def stop(self) -> None:
        """停止监控：退订事件并停止底层 Dispatcher。"""
        try:
            self._sub.unsubscribe()
        except Exception:
            pass
        try:
            self._dispatcher.stop()
        except Exception:
            pass

    def __enter__(self) -> "ClipWatcher":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()

    def __del__(self) -> None:  # pragma: no cover - 析构兜底
        try:
            self.stop()
        except Exception:
            pass


def clip_watch(
    *,
    interval: float = 0.2,
    backend: str = "auto",
    change_types: Optional[Iterable[Any]] = None,
    tags: Iterable[str] = (),
    filter_self: bool = True,
    on_text: Optional[Callable[["ClipData"], Any]] = None,
    on_change: Optional[Callable[["ClipData"], Any]] = None,
    on_error: Optional[Callable[[Exception], Any]] = None,
) -> ClipWatcher:
    """动作：启动剪贴板监控，返回 ClipWatcher（构造即启动，stop() 停止）。"""
    return ClipWatcher(
        interval=interval,
        backend=backend,
        change_types=change_types,
        tags=tags,
        filter_self=filter_self,
        on_text=on_text,
        on_change=on_change,
        on_error=on_error,
    )
