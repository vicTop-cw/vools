# API 参考索引 (API Reference)

> **模块路径**：-
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#A06
> **最后更新**：2026-06-30

---

## 概述

本文档提供 vools 所有公共 API 的索引和链接。

## 核心模块 (vools)

### 主入口

```python
import vools
vools.__version__  # 当前版本
```

### 异常类

| 类名 | 说明 | 模块 |
|------|------|------|
| `VoolsError` | 基础异常 | vools |
| `SafeEvalError` | 安全求值异常 | vools |
| `ConfigurationError` | 配置异常 | vools |
| `CacheError` | 缓存异常 | vools |
| `ValidationError` | 验证异常 | vools |

### 装饰器

| 装饰器 | 说明 | 模块 |
|--------|------|------|
| `@curry` | 柯里化函数 | vools.decorators |
| `@overload` | 函数重载 | vools.decorators |
| `@overcurry` | 柯里化重载 | vools.decorators |
| `@overloads` | 多重重载 | vools.decorators |
| `@memorize` | 记忆化缓存 | vools.decorators |
| `@once` | 单次执行 | vools.decorators |
| `@persist` | 持久化缓存 | vools.decorators |
| `@lazy` | 延迟计算 | vools.decorators |
| `@retry` | 重试机制 | vools.decorators |
| `@rself` | 自我调用 | vools.decorators |
| `@stuff` | 依赖注入 | vools.utils |

### 函数式工具

| 函数/类 | 说明 | 模块 |
|----------|------|------|
| `_` | 占位符（单参数） | vools.functional |
| `_1`, `_2`, `_3` | 占位符（多参数） | vools.functional |
| `g` | 表达式函数 | vools.functional |
| `iif` | 立即 if | vools.functional |
| `Box` | 引用容器 | vools.functional |
| `Pipe` | 管道操作 | vools.functional |
| `Ops` | 管道操作工具 | vools.functional |

### 数据结构

| 类名 | 说明 | 模块 |
|------|------|------|
| `Seq` | 序列操作 | vools.data |
| `Table` | 表格数据 | vools.data |
| `Qax` | QAX 数据集 | vools.data |
| `Row` | 表格行 | vools.data |
| `Column` | 表格列 | vools.data |

### 日期时间

| 函数/类 | 说明 | 模块 |
|----------|------|------|
| `vDate` | 日期类 | vools.datetime |
| `get_week` | 获取周信息 | vools.datetime |
| `get_month` | 获取月信息 | vools.datetime |
| `days_gap` | 日期差 | vools.datetime |
| `parse_date_string` | 解析日期字符串 | vools.datetime |

### 响应式编程

| 类名 | 说明 | 模块 |
|------|------|------|
| `Observable` | 可观察对象 | vools.reactive |
| `Subject` | 主题 | vools.reactive |
| `BehaviorSubject` | 行为主题 | vools.reactive |
| `ReplaySubject` | 重放主题 | vools.reactive |
| `ops` | 操作符模块 | vools.reactive |

### 编码/加密

| 函数 | 说明 | 模块 |
|------|------|------|
| `b64encode` | Base64 编码 | vools.encoding |
| `b64decode` | Base64 解码 | vools.encoding |
| `gzip_compress` | Gzip 压缩 | vools.encoding |
| `gzip_decompress` | Gzip 解压 | vools.encoding |
| `md5` | MD5 哈希 | vools.crypto |
| `sha256` | SHA256 哈希 | vools.crypto |

### 序列化

| 函数 | 说明 | 模块 |
|------|------|------|
| `pickle_dumps` | pickle 序列化 | vools.serialize |
| `pickle_loads` | pickle 反序列化 | vools.serialize |
| `json_dumps` | JSON 序列化 | vools.serialize |
| `json_loads` | JSON 反序列化 | vools.serialize |

### 任务调度

| 类名 | 说明 | 模块 |
|------|------|------|
| `TaskQueue` | 任务队列 | vools.task |
| `ThreadPool` | 线程池 | vools.task |
| `DagScheduler` | DAG 调度器 | vools.task |
| `RuleEngine` | 规则引擎 | vools.task |

## 子模块

### vools.decorators

详细文档：[decorators.md](../core/decorators.md)

```python
from vools import memorize, once, persist, lazy, retry
from vools import curry, overload, overcurry, rself
```

### vools.functional

详细文档：[functional.md](../functional/index.md)

```python
from vools import _, _1, _2, _3, g, iif
from vools import Box, Pipe, Ops
```

### vools.data

详细文档：[data/index.md](../data/index.md)

```python
from vools import Seq
from vools.data import Table, Qax, Row, Column
```

### vools.reactive

详细文档：[reactive/index.md](../reactive/index.md)

```python
from vools import Observable, Subject
from vools.reactive import ops
```

### vools.bridge

详细文档：[bridge/index.md](../bridge/index.md)

```python
from vools.bridge import discover_all, BridgeManager
from vools.bridge import probe_environment
```

### vools.curried

详细文档：[curried 模块](../core/curry.md)

```python
from vools.curried import map, filter, compose, pipe
```

### vools.cache

```python
from vools.cache import memorize, once, persist
from vools.cache.sigcache import get_signature
```

## 版本历史

- **v0.4.x** - Table/QAX 重写，FreeBASIC 支持
- **v0.3.x** - 性能跃迁，Nim 桥接
- **v0.2.x** - 跨语言桥接框架
- **v0.1.x** - 装饰器和函数式工具

## 索引

### 按字母排序

- `Box` - 引用容器
- `Column` - 表格列
- `curry` - 柯里化装饰器
- `g` - 表达式函数
- `iif` - 立即 if
- `memorize` - 记忆化
- `Observable` - 可观察对象
- `Ops` - 管道工具
- `overload` - 函数重载
- `persist` - 持久化缓存
- `Pipe` - 管道操作
- `Qax` - QAX 数据集
- `retry` - 重试机制
- `Row` - 表格行
- `rself` - 自我调用
- `Seq` - 序列操作
- `stuff` - 依赖注入
- `Subject` - 主题
- `Table` - 表格数据
- `_` - 占位符

## 导出列表

完整导出列表请参考：[vools/__init__.py](../../vools/__init__.py)
