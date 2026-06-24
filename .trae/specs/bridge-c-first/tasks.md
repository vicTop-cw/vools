# vools.bridge C 优先架构 - 实现计划

## [x] Task 1: 重构核心层 - 提取 ctypes 通用能力到 core
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 创建 `bridge/core/loader.py` - 通用共享库加载器（从现有 Nim loader 抽象）
  - 创建 `bridge/core/types.py` - Python ↔ ctypes 类型映射
  - 支持 Windows .dll 和 Linux .so
  - 支持库缓存、线程安全
- **Acceptance Criteria Addressed**: AC-1, AC-7
- **Test Requirements**:
  - `programmatic` TR-1.1: 在 Windows 上能正确加载 .dll
  - `programmatic` TR-1.2: 在 Linux 上能正确加载 .so
  - `programmatic` TR-1.3: 重复加载同一库走缓存
- **Notes**: 现有的 `bridge/core/loader.py` 已存在，需要重构使其更通用

## [x] Task 2: 实现 C 桥接模块
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 
  - 创建 `bridge/c/__init__.py`
  - 提供 `load_dll()` 函数（复用 core.loader）
  - 提供 `call_func()` 便捷函数
  - 提供 `@c_dll` 装饰器
  - 支持自动类型推断
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: load_dll 能加载 C DLL
  - `programmatic` TR-2.2: call_func 能调用 DLL 函数并返回正确结果
  - `programmatic` TR-2.3: @c_dll 装饰器工作正常
  - `programmatic` TR-2.4: 自动类型推断正确（int/float/str 等）

## [x] Task 3: 重构 Nim 桥接模块 - 复用 core + 增加编译器
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 
  - 重构 `bridge/nim/_loader.py` 复用 core.loader
  - 完善 `bridge/nim/compiler.py` - Nim 动态编译
  - 修复现有 bug（UnboundLocalError 等）
  - 完善 `@nim` 装饰器
  - 支持编译缓存
- **Acceptance Criteria Addressed**: AC-3, AC-4
- **Test Requirements**:
  - `programmatic` TR-3.1: @nim 装饰器能正确编译并运行 Nim 代码
  - `programmatic` TR-3.2: 相同代码第二次调用走缓存
  - `programmatic` TR-3.3: 支持基本类型（int/float/str）
  - `programmatic` TR-3.4: 递归函数能正常工作

## [x] Task 4: 实现通用装饰器 - @bridge_function 和 @bridge_module
- **Priority**: P1
- **Depends On**: Task 1
- **Description**: 
  - 完善 `bridge/core/decorators.py`
  - `@bridge_function` - 单函数桥接
  - `@bridge_module` - 模块/类级桥接
  - 支持指定语言、库名、函数名
  - 支持 fallback 回退
- **Acceptance Criteria Addressed**: AC-2, AC-6
- **Test Requirements**:
  - `programmatic` TR-4.1: @bridge_function 能正确映射到库函数
  - `programmatic` TR-4.2: @bridge_module 能批量映射
  - `programmatic` TR-4.3: 库不存在时回退到 fallback

## [x] Task 5: 实现异步编译和调用支持
- **Priority**: P1
- **Depends On**: Task 3
- **Description**: 
  - `@nim(async_mode=True)` 异步模式
  - 使用 ThreadPoolExecutor 后台编译
  - 返回 awaitable 对象
  - 支持 async/await 语法
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-5.1: 异步模式下 await 能获取结果
  - `programmatic` TR-5.2: 异步编译不阻塞主线程

## [x] Task 6: 完善回退机制
- **Priority**: P1
- **Depends On**: Task 2, Task 3
- **Description**: 
  - 编译器不存在时回退
  - 编译失败时回退
  - 运行时错误时回退
  - 清晰的错误信息
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-6.1: 没有编译器时不崩溃，使用 fallback
  - `programmatic` TR-6.2: 编译错误时抛出清晰的异常

## [x] Task 7: 整合到 vools 主包
- **Priority**: P1
- **Depends On**: Task 2, Task 3
- **Description**: 
  - 更新 `vools/__init__.py` 中的导出
  - 确保向后兼容
  - 旧的 _nim_*.py 文件继续工作
- **Acceptance Criteria Addressed**: NFR-3
- **Test Requirements**:
  - `programmatic` TR-7.1: `import vools.bridge` 成功
  - `programmatic` TR-7.2: `import vools.bridge.c` 成功
  - `programmatic` TR-7.3: `import vools.bridge.nim` 成功
  - `programmatic` TR-7.4: 旧的 vools.md5 等 API 仍然可用

## [x] Task 8: 预留其他语言目录
- **Priority**: P2
- **Depends On**: Task 1
- **Description**: 
  - 创建 bridge/rust/__init__.py（占位）
  - 创建 bridge/cpp/__init__.py（占位）
  - 创建 bridge/csharp/__init__.py（占位）
  - 每个都有基础架构说明
- **Acceptance Criteria Addressed**: NFR-2
- **Test Requirements**:
  - `programmatic` TR-8.1: 所有占位模块能正常 import

## [x] Task 9: 测试和验证
- **Priority**: P1
- **Depends On**: Task 7
- **Description**: 
  - Windows 端完整测试
  - WSL/Linux 端完整测试
  - 性能基准测试
- **Acceptance Criteria Addressed**: 所有 AC
- **Test Requirements**:
  - `programmatic` TR-9.1: Windows 上所有测试通过
  - `programmatic` TR-9.2: Linux 上所有测试通过
