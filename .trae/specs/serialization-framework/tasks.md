# Tasks

## Task 1: 创建序列化子包基础结构
- [x] Task 1.1: 创建 `vools/serialize/` 目录结构
- [x] Task 1.2: 创建 `vools/serialize/__init__.py` 基础结构
- [x] Task 1.3: 创建 `vools/serialize/backends/` 子包结构
- [x] Task 1.4: 创建 `vools/serialize/callable/` 子包结构

## Task 2: 实现序列化后端
- [x] Task 2.1: 创建 `backends/base.py` 后端基类 `BaseBackend`
- [x] Task 2.2: 实现 `PickleBackend` - pickle 序列化后端
- [x] Task 2.3: 实现 `JsonBackend` - json 序列化后端（支持 orjson）
- [x] Task 2.4: 实现 `MsgpackBackend` - msgpack 序列化后端（可选）

## Task 3: 实现核心 Serializer 类
- [x] Task 3.1: 创建 `Serializer` 类，支持后端切换
- [x] Task 3.2: 实现 `dumps(obj)` 和 `loads(data)` 方法
- [x] Task 3.3: 实现 `dumps_hex(obj)` 和 `loads_hex(hex_str)` 方法

## Task 4: 实现配置管理
- [x] Task 4.1: 创建 `config.py`，实现全局默认后端配置
- [x] Task 4.2: 实现 `set_default_backend()` 和 `get_default_backend()`

## Task 5: 实现 Callable 特殊处理
- [x] Task 5.1: 创建 `callable/__init__.py` 和注册机制
- [x] Task 5.2: 实现 `CurryHandler` - 处理 curry 化的函数
- [x] Task 5.3: 实现 `DecoratorHandler` - 处理被装饰器包装的函数
- [x] Task 5.4: 实现 `FunctionalHandler` - 处理 Pipe, Ops, Box 等函数式对象
- [x] Task 5.5: 实现 `ReactiveHandler` - 处理 Observable, Subject 等响应式对象

## Task 6: 实现装饰器
- [x] Task 6.1: 实现 `@serialize` 函数装饰器
- [x] Task 6.2: 实现 `@deserialize` 函数装饰器
- [x] Task 6.3: 实现 `@serializable` 类装饰器
- [x] Task 6.4: 实现 `@serialize_method` 实例方法装饰器
- [x] Task 6.5: 实现 `@deserialize_method` 实例方法装饰器

## Task 7: 完善 __init__.py 导出
- [x] Task 7.1: 导出 `Serializer` 类
- [x] Task 7.2: 导出 `dumps`, `loads`, `dumps_hex`, `loads_hex` 函数
- [x] Task 7.3: 导出 `serialize`, `deserialize` 函数装饰器
- [x] Task 7.4: 导出 `serializable` 类装饰器
- [x] Task 7.5: 导出 `serialize_method`, `deserialize_method` 实例方法装饰器
- [x] Task 7.6: 导出 `set_default_backend`, `get_default_backend`

## Task 8: 集成到 vools 主包
- [x] Task 8.1: 在 `vools/__init__.py` 中添加 serialize 模块的延迟导入
- [x] Task 8.2: 添加 `serialize`, `deserialize` 到 `__all__` 和 `_lazy_modules`

## Task 9: 编写单元测试
- [x] Task 9.1: 测试各后端的基本序列化/反序列化
- [x] Task 9.2: 测试 `@serialize` 和 `@deserialize` 装饰器
- [x] Task 9.3: 测试 `@serializable` 类装饰器
- [x] Task 9.4: 测试 Curry 函数的序列化
- [x] Task 9.5: 测试函数式对象（Pipe, Box 等）的序列化
- [x] Task 9.6: 测试全局配置功能

## Task Dependencies
- Task 1.2 依赖 Task 1.1
- Task 1.3, 1.4 依赖 Task 1.1
- Task 2 依赖 Task 1.3
- Task 3 依赖 Task 2
- Task 4 可独立进行
- Task 5 依赖 Task 1.4 和 Task 3
- Task 6 依赖 Task 3, 4, 5
- Task 7 依赖 Task 3, 4, 5, 6
- Task 8 依赖 Task 7
- Task 9 依赖 Task 8
