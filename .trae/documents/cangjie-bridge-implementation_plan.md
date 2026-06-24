# 仓颉(Cangjie)语言桥接实现计划

## 概述

为 vools.bridge 框架添加仓颉(Cangjie)语言桥接支持,参考现有 FreeBASIC、Rust、Nim 等桥接实现,使 Python 能够通过 ctypes 调用仓颉编译的动态库函数。

## 当前状态分析

### 仓颉语言特性(基于调研)

**编译器**: `cjc` (已安装,版本 1.0.0)
- 编译命令: `cjc [option] file...`
- 编译动态库: `cjc file.cj --output-type=dylib`
- Windows 输出: `.dll` 文件
- Linux 输出: `.so` 文件

**导出函数机制**:
- 使用 `@C` 注解导出函数,使其符合 C ABI
- 示例:
```cj
package mypackage

@C
func myHello(): Unit {
    println("Hello from Cangjie!")
}

@C
func add(a: Int64, b: Int64): Int64 {
    return a + b
}
```

**类型映射**(仓颉 ↔ C ↔ ctypes):
| 仓颉类型 | C 类型 | ctypes 类型 |
|---------|--------|-------------|
| Int8/UInt8 | int8_t/uint8_t | c_int8/c_uint8 |
| Int32/UInt32 | int32_t/uint32_t | c_int32/c_uint32 |
| Int64/UInt64 | int64_t/uint64_t | c_int64/c_uint64 |
| Float32 | float | c_float |
| Float64 | double | c_double |
| Bool | bool | c_bool |
| Unit | void | None |

### vools.bridge 现有框架

**核心模块** ([vools/bridge/core](file:///e:/IDEProjects/AI/vools/vools/bridge/core)):
- [decorators.py](file:///e:/IDEProjects/AI/vools/vools/bridge/core/decorators.py): `@bridge_function`, `@bridge_module` 装饰器
- [loader.py](file:///e:/IDEProjects/AI/vools/vools/bridge/core/loader.py): `LibraryLoader`, `load_library`, `is_available`
- [types.py](file:///e:/IDEProjects/AI/vools/vools/bridge/core/types.py): `CTypeMapper` 类型映射系统
- [serialization.py](file:///e:/IDEProjects/AI/vools/vools/bridge/core/serialization.py): 序列化支持

**现有桥接实现参考**:
- [freebasic](file:///e:/IDEProjects/AI/vools/vools/bridge/freebasic): 动态编译装饰器模式
  - [compiler.py](file:///e:/IDEProjects/AI/vools/vools/bridge/freebasic/compiler.py): `@fbc` 装饰器,动态编译
  - [types.py](file:///e:/IDEProjects/AI/vools/vools/bridge/freebasic/types.py): Python ↔ FreeBASIC 类型映射
  - [loader.py](file:///e:/IDEProjects/AI/vools/vools/bridge/freebasic/loader.py): DLL 加载器
- [rust](file:///e:/IDEProjects/AI/vools/vools/bridge/rust): 类似架构
- [nim](file:///e:/IDEProjects/AI/vools/vools/bridge/nim): 预编译库加载模式

**关键设计模式**:
1. **装饰器模式**: `@lang` 装饰器,函数体返回目标语言代码
2. **类型映射**: Python 类型 ↔ 目标语言类型 ↔ ctypes 类型
3. **动态编译**: 运行时编译源码到 DLL,缓存管理
4. **免序列化**: 直接通过 ctypes 调用,不走 JSON/CSV

## 提议变更

### 1. 创建仓颉桥接模块结构

**目录**: `vools/bridge/cangjie/`

**文件列表**:
```
vools/bridge/cangjie/
├── __init__.py          # 模块入口,导出主要 API
├── compiler.py          # 编译器封装,动态编译装饰器
├── types.py             # Python ↔ 仓颉类型映射
├── loader.py            # DLL 加载器
├── templates.py         # 仓颉代码生成模板
└── README.md            # 使用说明
```

### 2. 实现类型映射 (types.py)

**功能**:
- Python 类型 → 仓颉类型映射表
- 仓颉类型 → ctypes 类型映射表
- 类型推断函数

**映射表设计**:
```python
PY_TO_CJ_TYPE = {
    int: 'Int64',
    float: 'Float64',
    bool: 'Bool',
    str: 'String',  # 需特殊处理
    bytes: 'Array<Byte>',
    list: 'Array<T>',
    type(None): 'Unit',
}

CJ_TO_CTYPES = {
    'Int8': ctypes.c_int8,
    'Int32': ctypes.c_int32,
    'Int64': ctypes.c_int64,
    'Float32': ctypes.c_float,
    'Float64': ctypes.c_double,
    'Bool': ctypes.c_bool,
    'Unit': None,
}
```

### 3. 实现编译器封装 (compiler.py)

**核心装饰器**: `@cangjie`

**功能**:
- 检测仓颉编译器可用性 (`cjc_compiler_available()`)
- 动态编译仓颉代码到 DLL
- 缓存管理(基于代码 hash)
- 多种模式支持(DEBUG/NORMAL/FORCE/ONLY_RUN/ONLY_CODE)

**装饰器设计**(参考 fbc 装饰器):
```python
def cangjie(func=None, *, mode='NORMAL', cache_dir=None, ret_type=None, auto_signature=True):
    """
    仓颉动态编译装饰器

    使用方式:
        @cangjie
        def fib(n: int) -> int:
            return '''
            if n <= 1 {
                return 1
            } else {
                return fib(n - 1) + fib(n - 2)
            }
            '''

        @cangjie(mode='DEBUG')
        def add(a: int, b: int) -> int:
            return 'return a + b'
    """
```

**编译流程**:
1. 调用原函数获取仓颉代码体
2. 自动生成函数签名(基于 Python 类型注解)
3. 生成完整仓颉代码(包含 `@C` 注解和 `package` 声明)
4. 使用 `cjc --output-type=dylib` 编译
5. 缓存 DLL 路径(避免重复编译)
6. 通过 ctypes 调用 DLL 函数

### 4. 实现代码生成模板 (templates.py)

**功能**:
- 生成仓颉函数签名
- 生成 package 声明
- 处理 `@C` 注解

**模板示例**:
```cj
package {package_name}

@C
func {func_name}({params}) -> {return_type} {
    {body}
}
```

### 5. 实现加载器 (loader.py)

**功能**:
- 加载仓颉编译的 DLL
- 函数签名设置(argtypes, restype)
- 参数转换(str → bytes 等)

### 6. 更新桥接框架入口

**文件**: [vools/bridge/__init__.py](file:///e:/IDEProjects/AI/vools/vools/bridge/__init__.py)

**变更**:
- 添加 `cangjie` 子模块导入
- 导出 `cangjie` 相关 API

### 7. 创建测试文件

**文件**: `tests/test_cangjie_bridge.py`

**测试内容**:
- 编译器可用性检测
- 简单函数调用(整数运算)
- 字符串处理
- 数组处理
- 多种模式测试

### 8. 创建使用示例

**文件**: `examples/cangjie_bridge_example.py`

**示例内容**:
- Fibonacci 数列
- 字符串处理
- 数值计算

## 假设与决策

### 关键假设

1. **仓颉编译器已安装**: 用户已安装 `cjc` 并添加到 PATH
2. **C ABI 兼容**: `@C` 注解导出的函数符合 C ABI,可通过 ctypes 调用
3. **类型映射准确**: 仓颉基本类型与 C/ctypes 类型映射正确
4. **运行时依赖**: 仓颉 DLL 可能依赖仓颉运行时库(需处理)

### 设计决策

1. **装饰器模式**: 采用与 FreeBASIC 相同的装饰器模式,函数体返回仓颉代码
2. **动态编译**: 运行时编译,缓存 DLL,避免重复编译开销
3. **免序列化**: 直接 ctypes 调用,不走 JSON/CSV 中转
4. **自动签名**: 从 Python 类型注解自动生成仓颉函数签名
5. **package 命名**: 使用函数名作为 package 名(简化管理)

### 已知限制

1. **字符串处理**: 仓颉 String 类型可能需要特殊处理(UTF-8 编码)
2. **数组处理**: 仓颉 Array 类型需要指针+长度传递
3. **运行时依赖**: 仓颉 DLL 可能需要仓颉运行时 DLL(需测试验证)
4. **复杂类型**: struct、class 等复杂类型暂不支持

## 实现步骤

### Phase 1: 核心模块实现

1. 创建 `vools/bridge/cangjie/` 目录结构
2. 实现 `types.py` - 类型映射系统
3. 实现 `templates.py` - 代码生成模板
4. 实现 `compiler.py` - 编译器封装和装饰器
5. 实现 `loader.py` - DLL 加载器
6. 实现 `__init__.py` - 模块入口

### Phase 2: 框架集成

7. 更新 `vools/bridge/__init__.py` 导入 cangjie 模块
8. 添加 cangjie 到 `__all__` 导出列表

### Phase 3: 测试与验证

9. 创建 `tests/test_cangjie_bridge.py` 测试文件
10. 运行测试验证基本功能
11. 测试不同模式(NORMAL/DEBUG/FORCE 等)

### Phase 4: 文档与示例

12. 创建 `vools/bridge/cangjie/README.md` 使用文档
13. 创建 `examples/cangjie_bridge_example.py` 示例代码

## 验证步骤

### 编译器验证
```bash
cjc --version  # 应输出 "Cangjie Compiler: 1.0.0 (cjnative)"
```

### 基本功能测试
```python
from vools.bridge.cangjie import cangjie, cjc_compiler_available

# 检查编译器可用
assert cjc_compiler_available()

# 测试简单函数
@cangjie
def add(a: int, b: int) -> int:
    return 'return a + b'

result = add(10, 20)
assert result == 30
```

### DLL 导出验证
```bash
# 编译测试 DLL
cjc test.cj --output-type=dylib -o test.dll

# Python 调用
python -c "import ctypes; lib = ctypes.CDLL('test.dll'); print(lib.add(10, 20))"
```

## 风险与应对

### 风险1: 仓颉运行时依赖
- **风险**: 仓颉 DLL 可能依赖仓颉运行时库
- **应对**: 测试验证,必要时添加运行时 DLL 到 PATH

### 风险2: 字符串类型不兼容
- **风险**: 仓颉 String 可能不是 C ABI 兼容类型
- **应对**: 使用 CPointer<Byte> 或 CString 替代

### 风险3: 符号导出问题
- **风险**: 函数名可能被 mangle 或无法找到
- **应对**: 使用 `@C` 注解确保 C ABI 导出

## 参考资料

- [仓颉编译器手册](http://iwenwiki.com/cangjie/docs/user_manual/source_zh_cn/Chapter_18_cjc-Compiler-Manual_Community.html)
- [仓颉 FFI 实战](https://blog.csdn.net/2501_92277340/article/details/154076033)
- [仓颉与 .NET 互操作](https://blog.csdn.net/sd7o95o/article/details/149163810)
- [vools/bridge/freebasic](file:///e:/IDEProjects/AI/vools/vools/bridge/freebasic) - FreeBASIC 桥接实现
- [E:\IDEProjects\py\study\Pys\cross_lang\fbc.py](file:///E:/IDEProjects/py/study/Pys/cross_lang/fbc.py) - 参考实现