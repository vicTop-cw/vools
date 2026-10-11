# Scala 桥接实现计划

## 概要

基于现有 `vools.bridge` 框架架构，实现 Python 到 Scala 的桥接。使用 **Py4J** 作为主要的通信机制（Python 调用运行在 JVM 上的 Scala 代码）。

## 现有框架分析

### 核心组件（已存在）
- `vools.bridge.core.loader` - `SharedLibrary` 类 + `LibraryLoader` + `load_library()`
- `vools.bridge.core.types` - `CTypeMapper` 类型映射
- `vools.bridge.core.decorators` - `@bridge_function` / `@bridge_module` 装饰器
- `vools.bridge.core.serialization` - `Serializer` 序列化器

### 已实现的桥接示例
- `vools.bridge.c` - 直接 ctypes DLL 加载
- `vools.bridge.nim` - 预编译 Nim DLL + 函数签名设置
- `vools.bridge.freebasic` - FreeBASIC 编译器集成

---

## 实现方案

### 方案选择：Py4J（JVM Gateway 模式）

**原因：**
1. Scala 运行在 JVM 上，无法直接编译为原生 DLL
2. Py4J 是成熟的 Python↔Java/Scala 通信库
3. 可复用 `py4j.JavaGateway` 进行对象调用
4. 支持自动类型转换（Python ↔ Java types）

### 目录结构

```
vools/bridge/
  scala/
    __init__.py          # 模块入口，延迟导入
    loader.py            # JVM Gateway 加载器
    types.py             # Python ↔ Scala/JVM 类型映射
    decorator.py         # @scala_bridge 装饰器
    compiler.py          # Scala 源码编译（subprocess 调用 scala-cli）
    utils.py             # 辅助工具
```

---

## 详细实现

### 1. `vools/bridge/scala/__init__.py`

```python
"""
vools.bridge.scala - Scala 语言桥接模块

使用 Py4J 实现 Python 到 Scala 的跨语言调用。
"""

__all__ = ['scala_bridge', ' ScalaGateway', 'is_scala_available']
```

### 2. `vools/bridge/scala/loader.py`

核心加载器，负责管理 JVM Gateway：

```python
from py4j.java_gateway import JavaGateway, GatewayParameters
import subprocess
import os

class ScalaGateway:
    """Py4J Scala Gateway 管理器"""

    def __init__(self, port=25333, app_jar=None):
        self.port = port
        self.app_jar = app_jar
        self.gateway = None

    def start(self):
        """启动 JVM Gateway"""
        # 方式1: 直接启动 Scala 应用 JAR
        # 方式2: 连接已运行的 Scala 应用
        ...

    def stop(self):
        """停止 Gateway"""
        ...

    def get_object(self, fully_qualified_name):
        """获取 Scala/Java 对象"""
        ...
```

### 3. `vools/bridge/scala/types.py`

Python ↔ JVM 类型映射：

```python
# Python ↔ JVM 类型映射
PY_TO_JVM_TYPE_MAP = {
    int: 'java.lang.Integer',
    float: 'java.lang.Double',
    bool: 'java.lang.Boolean',
    str: 'java.lang.String',
    bytes: 'byte[]',
    list: 'java.util.List',
    dict: 'java.util.Map',
}

class ScalaTypeMapper:
    """类型映射器，支持自动推断和转换"""
    ...
```

### 4. `vools/bridge/scala/decorator.py`

装饰器实现：

```python
from vools.bridge.core.decorators import bridge_function

def scala_bridge(fallback=None, class_name=None, method_name=None):
    """
    Scala 桥接装饰器

    用法:
        @scala_bridge(class_name="com.example.MyObject", method_name="process")
        def process_data(data: str) -> str:
            pass
    """
    ...
```

### 5. `vools/bridge/scala/compiler.py`

Scala 源码编译支持（可选，使用 scala-cli）：

```python
def compile_scala(source_path: str, output_dir: str = None) -> str:
    """编译 Scala 源码为 JAR"""
    cmd = ['scala-cli', 'package', source_path, '--jar', output]
    ...
```

---

## 集成到主框架

### 修改 `vools/bridge/__init__.py`

添加延迟导入：
```python
try:
    from . import scala
except ImportError:
    pass
```

添加到 `__all__` 列表。

### 修改 `vools/bridge/core/loader.py`

在 `is_available()` 函数中添加 scala 检测：
```python
def is_available(language):
    ...
    elif language == 'scala':
        return is_scala_available()
```

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `vools/bridge/scala/__init__.py` | 新建 | 模块入口 |
| `vools/bridge/scala/loader.py` | 新建 | JVM Gateway 加载器 |
| `vools/bridge/scala/types.py` | 新建 | 类型映射 |
| `vools/bridge/scala/decorator.py` | 新建 | 装饰器 |
| `vools/bridge/scala/compiler.py` | 新建 | 编译支持（可选）|
| `vools/bridge/scala/utils.py` | 新建 | 辅助工具 |
| `vools/bridge/__init__.py` | 修改 | 添加 scala 导入 |
| `vools/bridge/core/loader.py` | 修改 | 添加 is_available('scala') |

---

## 依赖

- `py4j` - Python↔JVM 通信库（通过 pip 安装）

---

## 验证步骤

1. 确保 py4j 已安装：`pip install py4j`
2. 确保 scala 已安装且 `scala` 命令可用
3. 创建测试用例验证基本调用
4. 运行 `python -c "from vools.bridge.scala import is_scala_available; print(is_scala_available())"`

---

## 参考资料

- Py4J 官方文档: https://www.py4j.org/
- scala-cli: https://scala-cli.virtuslab.org/
