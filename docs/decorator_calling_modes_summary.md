# 装饰器调用方式统一修改总结

## 修改概述

统一了 vools 装饰器模块的调用方式，确保所有装饰器都支持两种调用方式：
1. `@decorator` 直接调用
2. `@decorator(params)` 带参数调用

## 修改的文件

### 1. cache.py

#### memorize
- **修改内容**：修复实现，正确支持两种调用方式
- **添加功能**：
  - 参数验证（duration > 0）
  - 使用关键字参数 `*` 强制 duration 为关键字参数
- **调用方式**：
  - `@memorize` - 直接调用
  - `@memorize(duration=5)` - 带参数调用

#### once
- **修改内容**：添加可选参数支持
- **添加功能**：
  - 新增 `force_default` 参数，用于设置默认的 force 参数值
  - 修改 `_OnceWrapper` 类，添加 `force_default` 属性
- **调用方式**：
  - `@once` - 直接调用
  - `@once(force_default=True)` - 带参数调用

#### persist
- **修改内容**：添加可选参数支持
- **添加功能**：
  - 新增可选参数：`file_key`, `force`, `force_when`, `target_folder`
  - 调用时可以覆盖装饰器参数
- **调用方式**：
  - `@persist` - 直接调用
  - `@persist(file_key="cache", target_folder="/tmp")` - 带参数调用

### 2. control.py

#### retry
- **修改内容**：添加无参数调用支持
- **添加功能**：
  - 参数验证（tries > 0, delay >= 0, backoff > 0）
  - 使用关键字参数强制所有参数为关键字参数
- **调用方式**：
  - `@retry` - 直接调用（使用默认参数）
  - `@retry(tries=3, delay=0.5)` - 带参数调用

#### rerun
- **修改内容**：添加无参数调用支持
- **添加功能**：
  - 提供默认 `until` 函数（lambda x: True）
  - 参数验证（interval > 0, time_out > 0）
  - 移除 wrapt 依赖，直接实现装饰器
- **调用方式**：
  - `@rerun` - 直接调用（使用默认参数）
  - `@rerun(until=lambda x: x == "success")` - 带参数调用

#### excepts
- **修改内容**：添加无参数调用支持
- **添加功能**：
  - 提供默认值（exc_type=Exception, handler=lambda e: None）
- **调用方式**：
  - `@excepts` - 直接调用（捕获所有异常，返回 None）
  - `@excepts(exc_type=ValueError, handler=lambda e: f"错误: {e}")` - 带参数调用

#### suppress
- **修改内容**：添加无参数调用支持
- **添加功能**：
  - 提供默认异常类型（Exception）
- **调用方式**：
  - `@suppress` - 直接调用（抑制所有异常）
  - `@suppress(ValueError, TypeError)` - 带参数调用

#### ignore
- **修改内容**：添加可选参数支持
- **添加功能**：
  - 新增 `return_value` 参数，指定返回的值
- **调用方式**：
  - `@ignore` - 直接调用（返回 None）
  - `@ignore(return_value="已执行")` - 带参数调用

### 3. overload.py

#### strict
- **修改内容**：添加可选参数支持
- **添加功能**：
  - 新增 `enabled` 参数，控制是否启用类型检查
  - 当 `enabled=False` 时，直接返回原函数
- **调用方式**：
  - `@strict` - 直接调用（启用类型检查）
  - `@strict(enabled=False)` - 带参数调用（不检查类型）

### 4. curry_core.py

#### curry
- **状态**：已经正确支持两种调用方式，无需修改
- **调用方式**：
  - `@curry` - 直接调用
  - `@curry(is_strict=True)` - 带参数调用

## 实现模式

所有装饰器都采用统一的实现模式：

```python
def decorator(func: Optional[Callable] = None, *, param1=default1, param2=default2) -> Callable:
    """装饰器文档"""
    
    # 参数验证
    if param1 <= 0:
        raise ValueError(f"param1 必须为正数，当前值: {param1}")
    
    def decorator_impl(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 装饰器逻辑
            return f(*args, **kwargs)
        return wrapper
    
    # 支持两种调用方式
    if func is None:
        # @decorator(param1=value) 带参数调用
        return decorator_impl
    else:
        # @decorator 直接调用
        return decorator_impl(func)
```

## 关键特性

1. **统一调用方式**：所有装饰器都支持 `@decorator` 和 `@decorator(params)` 两种调用方式
2. **参数验证**：添加了参数验证逻辑，确保参数值有效
3. **类型注解**：使用类型注解提高代码可读性
4. **functools.wraps**：使用 `@wraps` 保持函数签名和文档
5. **关键字参数**：使用 `*` 强制可选参数为关键字参数，避免混淆
6. **默认值**：提供合理的默认值，使无参数调用有意义

## 测试验证

创建了专门的测试文件 `tests/test_decorator_calling_modes.py`，验证所有装饰器的两种调用方式。所有测试都通过。

原有测试 `tests/test_decorators.py` 也全部通过，确保没有破坏现有功能。

## 注意事项

1. **参数命名**：所有可选参数使用 snake_case 命名
2. **参数顺序**：func 参数始终是第一个参数，且为可选参数
3. **关键字参数**：使用 `*` 分隔符强制可选参数为关键字参数
4. **默认值**：所有可选参数都有默认值
5. **参数验证**：添加了必要的参数验证逻辑

## 兼容性

所有修改都保持了向后兼容性：
- 原有的调用方式仍然有效
- 新增的可选参数不影响现有代码
- 所有测试都通过，确保没有破坏现有功能