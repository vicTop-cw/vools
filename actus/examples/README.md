# vools.actus 剪贴板能力示例与 API 说明

> 对齐 `docs/DEVELOPMENT_STANDARDS.md`（r1-doc-as-impl：模块 docstring 即实现，
> examples/ 即可运行文档；f2-four-forms-aligned：docstring / 文档 / 示例 / 测试四形态一致；
> cl6-doc-sync：文档与实现同步维护）。
> 本文档描述的是 `actus/vools/actus/clipboard.py` 对外公开的「配置 + 动作」式 API。

## 能力概览

剪贴板能力把 rx 子项目的响应式剪贴板（`vools.reactive.monitoring.clipboard`）
收敛为四个动作：**读 / 写 / 清空 / 监控**。调用方只提供配置信息并指定动作，
无需编写任何链路控制代码。

| 动作 | 签名 | 返回 |
|---|---|---|
| 读 | `clip_read()` | `ClipData`（当前剪贴板内容） |
| 写 | `clip_write(text, *, tags=None, source=None)` | `ClipData`（已写入内容） |
| 清空 | `clip_clear()` | `None` |
| 监控 | `clip_watch(**config)` | `ClipWatcher`（构造即启动，`stop()` 停止） |

统一导出（懒加载）：`from vools.actus import clip_read, clip_write, clip_clear, clip_watch, ClipWatcher, ClipData, ClipChangeType`

## 依赖

- 需要 `vools.reactive`（rx 子项目）在 `sys.path` 上提供
  `vools.reactive.monitoring.clipboard` 命名空间；
- 依赖缺失时各入口在调用阶段抛出 `ImportError` 并附原因（模块导入本身不炸）。

## 动作 API 说明

### clip_read()

读当前剪贴板，返回 `ClipData`。空剪贴板返回 `change_type=CLEAR` 的 `ClipData`；
读失败时 `content=None` 且 `metadata["error"]` 携带原因。

### clip_write(text, *, tags=None, source=None)

把文本写入系统剪贴板，返回表示已写入内容的 `ClipData`。

- `text`：要写入的文本（`None` 视为空串；`bytes/bytearray/memoryview`
  一律拒绝——历史上会被 `str()` 静默变形为 `"b'...'"` 写入，属静默数据污染，现为硬报错 `TypeError`）。
- `tags`：附加标签（写入返回的 `ClipData` 保留；系统剪贴板本身不携带自定义 tags）。
- `source`：来源标识（写入 `metadata._source`）。

### clip_clear()

清空系统剪贴板。

### clip_watch(**config) -> ClipWatcher

启动剪贴板监控，构造即启动。返回 `ClipWatcher` 句柄：

| ClipWatcher 成员 | 说明 |
|---|---|
| `stop()` | 停止监控（退订事件 + 停止底层 Dispatcher）；支持 `with` 上下文自动停止 |
| `is_running` | 底层 Dispatcher 是否运行中 |
| `dispatcher` | 底层 `ClipboardDispatcher`（调试 / 高级用法） |

`clip_watch` 配置参数（透传底层 Dispatcher）：

| 参数 | 默认 | 说明 |
|---|---|---|
| `interval` | `0.2` | 轮询间隔（秒）。**必须为有限正数**：`<=0` / `NaN` / `inf` / 非数字 / `bool` 均显式报错（BUG-371 收口，杜绝 busy-loop 与语义幻觉） |
| `backend` | `"auto"` | `"auto"` / `"win32"` / `"polling"` |
| `change_types` | `None` | 变更类型白名单；`None` 表示全部分发 |
| `tags` | `()` | 默认附加标签 |
| `filter_self` | `True` | 是否过滤「自己写回」分发（`False` 时 `clip_write` 的写入也会触发事件） |
| `on_text` | `None` | 仅文本变更时回调 `(cd: ClipData)` |
| `on_change` | `None` | 任意变更时回调 `(cd: ClipData)` |
| `on_error` | `None` | 分发异常回调 `(e: Exception)` |

> 事件回调在 Dispatcher 的 worker / polling 线程触发，注意线程安全。

## ClipData 数据形态

- 字段：`content`（文本或 `None`）、`change_type`（`ClipChangeType`：TEXT / CLEAR 等）、
  `files`、`tags`、`metadata`（含 `_source`、`_owner_seq` 等）、`sequence`。
- 序列化：`to_json()` / `from_json(s)`、`to_dict()` / `from_dict()`、`to_pickle(path)` / `from_pickle(path)`。

## 示例清单

| 文件 | 形态 | 运行方式 |
|---|---|---|
| `clipboard_basic.py` | 写 -> 读回验证 -> 清空，四个动作全链路 | `python clipboard_basic.py` |
| `clipboard_watch.py` | 启动监控 -> 写入 -> 收到事件 -> 停止 | `python clipboard_watch.py` |

两个示例均对系统剪贴板做**真实读写**（Windows 全局剪贴板），使用唯一前缀文本
避免与其它剪贴板活动互相干扰；脚本自带 `sys.path` 引导，无需安装包即可运行。
冒烟测试：`tests/test_examples_smoke.py` 以子进程方式真实运行两个示例并断言关键输出。

## 注意事项

- 示例与测试会短暂改写系统剪贴板内容，请勿在复制重要内容时运行。
- 监控演示使用 `backend="polling"` + `interval=0.05` 提速，便于演示与测试；
  实际场景可用默认 `auto`（Win32 事件后端优先）。
- 剪贴板监控的 `interval` 下限守卫已由 BUG-371（T0r2.1.1）修复并覆盖回归用例，
  本示例不重复演示非法参数。
