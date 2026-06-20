# Checklist

## 包结构
- [ ] `vools/serialize/` 目录结构完整
- [ ] `vools/serialize/backends/` 子包结构正确
- [ ] `vools/serialize/callable/` 子包结构正确

## 后端实现
- [ ] `PickleBackend` 正确实现
- [ ] `JsonBackend` 正确实现，支持 orjson 回退到 json
- [ ] `MsgpackBackend` 正确实现（可选后端）
- [ ] 后端基类 `BaseBackend` 接口定义正确

## Serializer 核心类
- [ ] `Serializer.dumps(obj)` 正确序列化对象
- [ ] `Serializer.loads(data)` 正确反序列化数据
- [ ] `Serializer.dumps_hex(obj)` 生成十六进制字符串
- [ ] `Serializer.loads_hex(hex_str)` 从十六进制字符串反序列化
- [ ] `Serializer` 支持切换后端

## 配置管理
- [ ] `set_default_backend()` 正确设置全局默认后端
- [ ] `get_default_backend()` 正确获取全局默认后端
- [ ] 默认后端可被各组件正确使用

## Callable 特殊处理
- [ ] `CurryHandler` 正确处理 curry 化的函数
- [ ] `DecoratorHandler` 正确处理被装饰器包装的函数
- [ ] `FunctionalHandler` 正确处理 Pipe, Ops, Box 等函数式对象
- [ ] `ReactiveHandler` 正确处理 Observable, Subject 等响应式对象
- [ ] Callable 处理器注册机制正常工作

## 函数装饰器
- [ ] `@serialize` 装饰器正确序列化函数返回值
- [ ] `@deserialize` 装饰器正确反序列化函数参数
- [ ] 装饰器支持 `backend` 参数指定后端
- [ ] 装饰器保留原函数签名（使用 functools.wraps）

## 类装饰器
- [ ] `@serializable` 类装饰器正确为类添加 serialize/deserialize 类方法
- [ ] `MyClass.serialize(instance)` 正确序列化类实例
- [ ] `MyClass.deserialize(data)` 正确反序列化为类实例
- [ ] 实例的 callable 属性被正确序列化

## 实例方法装饰器
- [ ] `@serialize_method` 实例方法装饰器正确序列化方法返回值
- [ ] `@deserialize_method` 实例方法装饰器正确反序列化方法参数
- [ ] 类装饰器与实例方法装饰器可组合使用

## API 导出
- [ ] `Serializer` 类正确导出
- [ ] `dumps`, `loads`, `dumps_hex`, `loads_hex` 函数正确导出
- [ ] 函数装饰器 `serialize`, `deserialize` 正确导出
- [ ] 类装饰器 `serializable` 正确导出
- [ ] 实例方法装饰器 `serialize_method`, `deserialize_method` 正确导出
- [ ] `set_default_backend`, `get_default_backend` 正确导出
- [ ] 可选后端（msgpack、orjson）未安装时不影响基本功能

## 集成到主包
- [ ] `vools/__init__.py` 正确导入 serialize 模块
- [ ] `serialize`, `deserialize` 可通过 `vools.serialize` 访问
- [ ] 延迟导入机制正常工作

## 测试覆盖
- [ ] 各后端序列化/反序列化测试通过
- [ ] `@serialize` 装饰器测试通过
- [ ] `@deserialize` 装饰器测试通过
- [ ] `@serializable` 类装饰器测试通过
- [ ] `@serialize_method` 装饰器测试通过
- [ ] `@deserialize_method` 装饰器测试通过
- [ ] Curry 函数序列化测试通过
- [ ] 函数式对象序列化测试通过
- [ ] 全局配置测试通过
