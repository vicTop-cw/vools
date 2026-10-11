# Clipboard Monitor Dispatcher (Hook-Based + Self-Filter) - 验收检查清单

## 数据类型 & 序列化
- [ ] `ChangeType` 包含 TEXT/FILES/IMAGE/HTML/RTF/CLEAR/OTHER 共 7 个成员，int 值 0~6。
- [ ] `ClipData` 字段齐全：`content`、`files`、`change_type`、`tags`、`metadata`、`timestamp`、`sequence`；`sequence` 是全局单调递增。
- [ ] `ClipData.now(**kwargs)` 工厂能自动填充 `timestamp` 与 `sequence`。
- [ ] `to_dict / from_dict / to_json / from_json / to_pickle / from_pickle` 共 6 个方法均实现。
- [ ] JSON 序列化 bytes 时自动使用 base64，并在 dict 中带 `_encoding: "base64"` 标记；反序列化能正确还原为 bytes。
- [ ] `from_dict / from_json` 对缺失字段使用默认值（空 list、空 dict、当前时间、新 sequence），对未知字段忽略。
- [ ] `from_dict` 的 `change_type` 同时支持 int（0）和 str（"TEXT"）两种形式。

## 剪贴板读写 Adapter
- [ ] Windows ctypes 路径正确读取 `CF_UNICODETEXT` 返回 str；`CF_HDROP` 返回 files 列表；`CF_DIB` 返回 bytes。
- [ ] 非 Windows / 无 GUI 框架时，tkinter 回退路径可读取文本。
- [ ] 读取失败 → `ChangeType.OTHER` + metadata 含 `error` 字段。
- [ ] 空剪贴板 → `ChangeType.CLEAR`。
- [ ] 写回文本成功，内容可被 read() 重新读到。
- [ ] 写回 FILES 成功（Windows）且 read() 返回 FILES + 正确文件路径。
- [ ] 所有可选依赖 try/except ImportError 隔离；缺失时仍可 `import vools.reactive`。

## Hook 后端（Windows）
- [ ] 启动时在后台线程内注册窗口类 + 创建隐藏窗口 + 调用 `AddClipboardFormatListener`。
- [ ] 消息循环正确接收 `WM_CLIPBOARDUPDATE` 并触发上层 on_change。
- [ ] `PostMessageW(hwnd, WM_CLOSE, 0, 0)` 能正确唤醒消息循环并退出。
- [ ] stop() 时 `RemoveClipboardFormatListener / DestroyWindow / UnregisterClass` 全部执行；线程干净退出。
- [ ] 反复 start/stop ≥ 5 次不抛异常、不挂住、不泄漏 HWND。
- [ ] 无 pywin32 时 ctypes 路径仍然可 hook 成功。

## Polling 后端（保底）
- [ ] 使用 `threading.Event.wait(interval)` 而非 `time.sleep`；stop 可立即唤醒。
- [ ] 接口与 `_Win32HookBackend` 完全一致：`start() / stop() / is_running`。
- [ ] stop 后在 `2*interval` 内线程实际退出。

## Dispatcher 主体 & self-filter（核心）
- [ ] 构造参数齐全：`backend / interval / change_types / tags / filter_self / self_filter / self_source / self_signature_capacity / on_change_data`。
- [ ] `backend_name` 只读属性返回实际启用的后端名称。
- [ ] `filter_self: bool` 默认 True；`self_filter: Callable[[ClipData], bool] | None` 默认 None；运行时均可重新赋值。
- [ ] `self_source` 默认自动生成 `f"vools:{pid}:{id(self)}"`；可在构造或运行时赋值。
- [ ] `_self_signatures: deque[tuple]` 的 maxlen == `self_signature_capacity`（默认 32）；超过容量最旧条目被丢弃。
- [ ] `_dispatch_once()` 流程正确：读取 → signature 计算 → 先 self-filter 命中检查 → 再 content signature 去重 → 构造 ClipData（优先 on_change_data）→ subject.on_next。
- [ ] self-filter 命中时 `self_filtered_count += 1`；content 去重命中时 `duplicate_count += 1`。
- [ ] `on_change_data` 回调抛异常或返回非 ClipData 时，回退到默认 ClipData + `error_count += 1`，不中断消息循环。
- [ ] `dispatch_count / error_count / duplicate_count / self_filtered_count` 都有只读 `@property`。
- [ ] `start() / stop() / is_running` 内部 `RLock` 保护，线程安全；重复调用 start 不抛异常。
- [ ] `with ClipboardDispatcher(...) as d:` 块结束后 `d.is_running == False`。
- [ ] `subject: Subject[ClipData]` 可直接 `pipe(ops.filter, ops.map, ...)` 并订阅。

## set_clipboard 标准写回
- [ ] `set_clipboard(content, files, change_type, *, source, tags, metadata) -> ClipData` 的 API 签名与文档一致。
- [ ] 实际写入系统剪贴板成功（用 reader.read() 验证）。
- [ ] 写回后读取系统剪贴板得到 signature，登记进 `_self_signatures`。
- [ ] 构造的 ClipData metadata 含 `_source` 与 `_owner_seq` 字段；`_source` 优先用参数 source，否则用 `self_source`。
- [ ] 写回后直接 `subject.on_next(clip_data)` 投递一份；`dispatch_count += 1`。
- [ ] `change_type is None` 时能按 content/files 类型合理推断（files 非空 → FILES；bytes → IMAGE；其它 → TEXT）。

## 响应式操作符 write_to_clipboard
- [ ] `write_to_clipboard(dispatcher, source=None)` 可在 pipe 中作为算子使用。
- [ ] 正确处理五种上游 item 类型：ClipData / str / bytes / tuple / dict。
- [ ] 对每个上游 item，都调用 `dispatcher.set_clipboard(...)` 并把返回的 ClipData 继续向下游传递。
- [ ] 上游抛异常时正确走 `on_error`，不中断整个流。
- [ ] 与 `vools.reactive.ops.*` 其它算子风格一致、链式组合正常。

## 顶层工厂 from_clipboard
- [ ] `from_clipboard(auto_start=True, ...)` 返回 `(Observable[ClipData], ClipboardDispatcher)` 二元组。
- [ ] auto_start=True 时，返回的 dispatcher.is_running == True；auto_start=False 时为 False。
- [ ] `from vools.reactive import ChangeType, ClipData, ClipboardDispatcher, from_clipboard` 均能成功。
- [ ] `from vools.reactive.ops import write_to_clipboard` 也能成功。

## 关键行为测试（避免循环触发）
- [ ] **场景 1**：外部写 "hello" → `dispatcher.set_clipboard("HELLO")` → 等待 ≥ 200ms → `dispatch_count` 最终只能 == 2（1 原始 + 1 直接投递），不会出现 3+。
- [ ] **场景 2**：`filter_self=False` 时，上述流程的 `dispatch_count` 可能 ≥ 3（系统通知被当作外部变更）；这是预期行为。
- [ ] **场景 3**：自定义 `self_filter = lambda d: "_owner_seq" in d.metadata`；之后当一份 ClipData 命中此回调时，`self_filtered_count` 正确增长。
- [ ] **场景 4**：多线程并发 start/stop/set_clipboard 20 轮 → 无死锁、无 RuntimeError、无残留挂起线程；最终 `is_running == False`。

## 测试
- [ ] `tests/test_reactive_clipboard.py` 存在且组织为 8+ 个测试类。
- [ ] `pytest tests/test_reactive_clipboard.py -q` 全部通过。
- [ ] 非 Windows / 无 pywin32 的测试正确 skip，不影响整体结果。
- [ ] fixture `working_dispatcher()` 在 teardown 时自动 stop，避免残留线程。
- [ ] 测试覆盖枚举、序列化、读写 Adapter、Hook 后端、Polling 后端、self-filter、并发、上下文管理器、顶层工厂、pipe 接入。

## 代码风格与文档
- [ ] `clipboard.py` 使用 `from __future__ import annotations`。
- [ ] 中文模块 docstring + 公共 API 中文 docstring。
- [ ] `__all__ = ["ChangeType", "ClipData", "ClipboardDispatcher", "from_clipboard", "write_to_clipboard"]` 显式声明。
- [ ] 内部类型/类以下划线 `_` 前缀命名，不对外暴露。
- [ ] 可选依赖 try/except ImportError 隔离；不阻塞 import。
- [ ] `vools/reactive/__init__.py` 以一致的风格引入并再导出。
- [ ] 可选：调试日志（logging DEBUG 级别）可在需要时开启；默认不输出任何日志。
