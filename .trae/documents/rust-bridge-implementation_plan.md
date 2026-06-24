# Rust 桥接实现计划 - PyO3 + 动态编译装饰器

## Overview
- **Summary**: 实现 Rust 桥接模块，采用类似 fbc.py 的动态编译装饰器模式，函数返回 Rust 代码，自动编译为 DLL 并通过 ctypes 加载执行
- **Purpose**: 为 vools 添加 Rust 高性能桥接能力，复用现有 bridge/core 基础设施
- **Target Users**: vools 库开发者、需要 Rust 性能优化的用户

## Current State Analysis

### 现有架构
- **bridge/core/**: 已有完整的 ctypes 基础设施
  - `loader.py`: 共享库加载、缓存、路径查找
  - `types.py`: Python ↔ ctypes 类型映射、自动推断
  - `decorators.py`: `@bridge_function`、`@bridge_module` 装饰器
  - `serialization.py`: CSV/JSON 序列化
- **bridge/nim/**: Nim 桥接已实现，提供加密、序列、日期时间等模块
- **bridge/rust/**: 当前为空模块，仅有预留注释

### 参考实现 (fbc.py)
- **核心模式**: 函数返回目标语言代码字符串，装饰器自动编译并执行
- **关键特性**:
  - 多种模式支持 (DEBUG/FORCE/NORMAL/ONLY_RUN/ONLY_CODE)
  - 自动签名生成（基于 Python 类型注解）
  - 类型映射系统（Python → 目标语言）
  - 编译缓存机制
  - 自动类型推断调用

### 技术栈选择
- **PyO3**: Rust 的 Python 绑定库，用于原生扩展（备选方案）
- **动态编译**: 主要方案，类似 fbc.py，使用 `cargo` 编译 Rust 为 DLL
- **ctypes**: 加载编译后的 DLL，复用现有基础设施

## Proposed Changes

### 1. Rust 桥接核心模块 (`vools/bridge/rust/`)

#### 文件结构
```
vools/bridge/rust/
├── __init__.py          # 导出 Rust 桥接 API
├── compiler.py          # Rust 编译器封装、代码生成
├── types.py             # Python ↔ Rust 类型映射
├── decorator.py         # @rust 动态编译装饰器
├── templates.py         # Rust 代码模板生成
└── _loader.py           # Rust DLL 加载器（复用 core.loader）
```

#### 核心组件

**1.1 类型映射系统 (`types.py`)**
- Python 类型 → Rust 类型映射表
- 支持基本类型：int → i64, float → f64, bool → bool, str → &str
- 支持数组类型：list → Vec<T>
- 支持指针类型：bytes → &[u8]
- 自动类型推断函数

**1.2 代码生成器 (`templates.py`)**
- 生成 Rust 函数签名
- 生成 C ABI 导出代码（`extern "C"`）
- 生成 DLL 入口点
- 支持预处理指令（use、mod 等）

**1.3 编译器封装 (`compiler.py`)**
- Cargo 项目初始化
- Cargo.toml 配置生成
- 动态编译命令执行
- 编译缓存管理（基于代码哈希）
- 错误处理和日志

**1.4 装饰器 (`decorator.py`)**
```python
@rust(mode='NORMAL', auto_signature=True)
def fib(n: int) -> int:
    return """
    if n <= 1 {
        1
    } else {
        fib(n - 1) + fib(n - 2)
    }
    """
```

**装饰器参数**:
- `mode`: 运行模式（DEBUG/FORCE/NORMAL/ONLY_RUN/ONLY_CODE）
- `auto_signature`: 是否自动生成签名（默认 True）
- `dll_name`: 自定义 DLL 名称
- `cache_dir`: 编译缓存目录
- `features`: Cargo features 列表

**装饰器流程**:
1. 获取函数签名和类型注解
2. 调用函数获取 Rust 代码字符串
3. 自动生成函数签名（如果启用）
4. 检查缓存（基于代码哈希）
5. 编译 Rust 代码为 DLL（如果需要）
6. 通过 ctypes 加载 DLL
7. 调用函数并返回结果

### 2. 实现细节

#### 2.1 Cargo 项目结构
```rust
// 生成的 Cargo.toml
[package]
name = "vools_rust_<func_name>"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]  # 动态库

[dependencies]
# 可选依赖，根据 features
serde = { version = "1.0", optional = true }
```

#### 2.2 Rust 代码模板
```rust
// 生成的 src/lib.rs
use std::os::raw::*;

#[no_mangle]
pub extern "C" fn fib(n: c_long) -> c_long {
    if n <= 1 {
        1
    } else {
        fib(n - 1) + fib(n - 2)
    }
}
```

#### 2.3 类型映射表
```python
PY_TO_RUST_TYPE_MAP = {
    int: 'c_long',          # 使用 C ABI 类型
    float: 'c_double',
    bool: 'c_int',          # C ABI 中 bool 用 int 表示
    str: '*const c_char',   # C 字符串指针
    bytes: '*const c_uchar',
    list: 'void',           # 复杂类型通过序列化传递
    None: 'void',
}
```

#### 2.4 编译缓存策略
- 缓存目录：`__rust__/cache/`
- 缓存键：代码内容哈希 + 函数签名哈希
- 缓存文件：`<hash>.dll` + `<hash>.toml`
- 清理策略：超过 100 个缓存文件时清理最旧的

### 3. 复用现有基础设施

#### 3.1 复用 core.loader
```python
from vools.bridge.core.loader import SharedLibrary, load_from_path

# Rust 加载器直接使用 SharedLibrary
def load_rust_dll(dll_path):
    return load_from_path(dll_path)
```

#### 3.2 复用 core.types
```python
from vools.bridge.core.types import CTypeMapper, infer_arg_types

# Rust 使用相同的 ctypes 类型系统
# 因为编译后的 DLL 是 C ABI
```

#### 3.3 复用 core.serialization
```python
from vools.bridge.core.serialization import Serializer

# 复杂类型通过序列化传递
# Rust 端使用 serde 反序列化
```

### 4. 高级功能

#### 4.1 异步编译支持
```python
@rust(async_mode=True)
async def heavy_compute(data: list) -> float:
    return """
    // Rust 代码
    """
```

#### 4.2 多函数模块
```python
@rust_module(name='math_ops')
class MathOps:
    def add(a: int, b: int) -> int: ...
    def mul(a: float, b: float) -> float: ...
```

#### 4.3 PyO3 原生扩展（备选）
```python
@pyo3_module
class FastCrypto:
    def md5(data: bytes) -> str:
        # 直接使用 PyO3 绑定，无需 ctypes
        pass
```

### 5. 文件修改清单

#### 新增文件
1. `vools/bridge/rust/__init__.py` - 导出 API
2. `vools/bridge/rust/compiler.py` - 编译器封装
3. `vools/bridge/rust/types.py` - 类型映射
4. `vools/bridge/rust/decorator.py` - 装饰器实现
5. `vools/bridge/rust/templates.py` - 代码模板
6. `vools/bridge/rust/_loader.py` - 加载器

#### 修改文件
1. `vools/bridge/__init__.py` - 添加 rust 模块导出
2. `pyproject.toml` - 添加 rust 编译依赖说明

#### 测试文件
1. `tests/test_rust_decorator.py` - 装饰器测试
2. `tests/test_rust_types.py` - 类型映射测试
3. `tests/test_rust_compiler.py` - 编译器测试

## Assumptions & Decisions

### 关键假设
1. 用户已安装 Rust 工具链（rustc、cargo）
2. 目标平台支持动态库加载（Windows/Linux）
3. 使用 C ABI 作为 Rust 和 Python 的接口标准
4. 复杂类型通过序列化传递（JSON/MessagePack）

### 关键决策
1. **主要方案**: 动态编译装饰器（类似 fbc.py）
2. **备选方案**: PyO3 原生扩展（未来可选）
3. **接口标准**: C ABI（extern "C"），确保 ctypes 可加载
4. **类型系统**: 复用现有 ctypes 类型映射
5. **缓存策略**: 基于代码哈希的文件缓存
6. **编译目录**: `__rust__/`（类似 `__fbc__/`）

### 设计权衡
- **性能**: 动态编译比 PyO3 原生扩展略慢，但更灵活
- **易用性**: 装饰器模式比手动编写 Cargo 项目更简单
- **兼容性**: C ABI 确保跨平台兼容性
- **可维护性**: 复用现有基础设施，减少重复代码

## Verification Steps

### 单元测试
1. 类型映射测试：验证 Python → Rust → ctypes 类型转换
2. 代码生成测试：验证 Rust 代码模板生成正确性
3. 编译器测试：验证 Cargo 编译流程
4. 装饰器测试：验证各模式下的行为

### 集成测试
1. 简单函数测试：fib、add 等基本运算
2. 字符串处理测试：验证字符串传递
3. 数组处理测试：验证序列化传递
4. 缓存测试：验证编译缓存机制
5. 回退测试：验证编译失败时的 Python 回退

### 性能测试
1. 首次编译时间：记录编译耗时
2. 缓存命中性能：对比缓存和非缓存调用
3. 与 Nim 对比：对比 Rust 和 Nim 桥接性能
4. 与 Python 对比：对比 Rust 和纯 Python 性能

### 兼容性测试
1. Windows 测试：验证 .dll 加载
2. Linux 测试：验证 .so 加载
3. Python 3.6+ 测试：验证各版本兼容性

## Implementation Phases

### Phase 1: 核心框架（1-2 天）
- 实现类型映射系统
- 实现代码模板生成
- 实现编译器封装
- 实现基础装饰器

### Phase 2: 完善功能（1-2 天）
- 实现缓存机制
- 实现多模式支持
- 实现错误处理
- 实现回退机制

### Phase 3: 高级功能（可选）
- 实现异步编译
- 实现多函数模块
- 实现 PyO3 原生扩展

### Phase 4: 测试和文档
- 编写单元测试
- 编写集成测试
- 编写使用文档
- 编写示例代码

## Risk Analysis

### 技术风险
- **编译失败**: Rust 编译器可能报错，需要良好的错误处理
- **类型不匹配**: C ABI 类型转换可能有问题，需要充分测试
- **内存安全**: 跨语言传递指针需要注意内存管理

### 缓解措施
- 提供详细的编译错误信息
- 实现自动回退到 Python 实现
- 使用序列化传递复杂类型，避免直接指针操作
- 充分的单元测试和集成测试

## Success Criteria

1. ✅ 装饰器可以成功编译 Rust 代码为 DLL
2. ✅ 编译后的 DLL 可以通过 ctypes 正确加载和调用
3. ✅ 缓存机制可以避免重复编译
4. ✅ 编译失败时可以回退到 Python 实现
5. ✅ 类型映射系统可以正确转换基本类型
6. ✅ 测试覆盖率 > 80%
7. ✅ 文档和示例完整可用

## Next Steps

执行计划后立即开始：
1. 创建 Rust 桥接模块目录结构
2. 实现类型映射系统
3. 实现代码模板生成器
4. 实现编译器封装
5. 实现装饰器核心逻辑
6. 编写测试用例
7. 编写使用文档和示例