# vools Bridge - 实现计划

## [ ] Task 1: 创建 bridge 子包目录结构
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 创建 `vools/bridge/__init__.py`
  - 创建 `vools/bridge/core/` 目录（核心基础设施）
  - 创建 `vools/bridge/nim/` 目录（Nim 桥接实现）
  - 创建其他语言的占位目录（mojo/, rust/, c/, cpp/, csharp/）
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-1.1: 目录结构正确创建
  - `programmatic` TR-1.2: `import vools.bridge` 成功
- **Notes**: 其他语言目录仅创建占位 `__init__.py`

## [ ] Task 2: 实现统一共享库加载器
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 
  - 在 `bridge/core/loader.py` 中实现 `LibraryLoader` 类
  - 支持跨平台（Windows .dll, Linux .so）
  - 支持自动查找库路径
  - 支持缓存已加载的库
  - 提供 `is_library_available(name)` 方法
- **Acceptance Criteria Addressed**: AC-3, AC-6
- **Test Requirements**:
  - `programmatic` TR-2.1: 在 Windows 上正确加载 .dll
  - `programmatic` TR-2.2: 在 Linux 上正确加载 .so
  - `programmatic` TR-2.3: 库不存在时返回 None 且不抛出异常
- **Notes**: 基于现有 `_nim_loader.py` 重构

## [ ] Task 3: 实现统一数据序列化层
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 
  - 在 `bridge/core/serialization.py` 中实现序列化器
  - 支持 CSV、JSON 格式
  - 提供 `serialize` 和 `deserialize` 方法
  - 支持 int、float、string、list 类型
- **Acceptance Criteria Addressed**: FR-4
- **Test Requirements**:
  - `programmatic` TR-3.1: int 列表 CSV 序列化/反序列化正确
  - `programmatic` TR-3.2: float 列表 CSV 序列化/反序列化正确
  - `programmatic` TR-3.3: string 列表 CSV 序列化/反序列化正确
- **Notes**: 基于现有 `_nim_seq.py` 中的 CSV 辅助函数重构

## [ ] Task 4: 实现 @bridge_function 装饰器
- **Priority**: P0
- **Depends On**: Task 2, Task 3
- **Description**: 
  - 在 `bridge/core/decorators.py` 中实现 `bridge_function` 装饰器
  - 支持指定语言（如 "nim"）和 fallback 函数
  - 自动处理数据序列化和反序列化
  - 自动检测语言可用性并选择实现
- **Acceptance Criteria Addressed**: AC-1, AC-5
- **Test Requirements**:
  - `programmatic` TR-4.1: Nim 可用时调用 Nim 实现
  - `programmatic` TR-4.2: Nim 不可用时调用 Python fallback
  - `programmatic` TR-4.3: 装饰器不影响函数签名
- **Notes**: 装饰器应尽量减少运行时开销

## [ ] Task 5: 实现 @bridge_module 装饰器
- **Priority**: P1
- **Depends On**: Task 4
- **Description**: 
  - 在 `bridge/core/decorators.py` 中实现 `bridge_module` 装饰器
  - 支持批量定义一组桥接函数
  - 自动为模块中的所有函数应用桥接逻辑
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-5.1: 类的所有方法自动使用桥接实现
  - `programmatic` TR-5.2: 模块级别的回退机制正常工作
- **Notes**: 可以基于 `@bridge_function` 实现

## [ ] Task 6: 实现 Nim 桥接模块
- **Priority**: P0
- **Depends On**: Task 2, Task 3, Task 4
- **Description**: 
  - 创建 `bridge/nim/__init__.py` 导出 API
  - 创建 `bridge/nim/crypto.py` 桥接加密函数
  - 创建 `bridge/nim/seq.py` 桥接序列操作函数
  - 创建 `bridge/nim/datetime.py` 桥接日期时间函数
  - 创建 `bridge/nim/curried.py` 桥接函数式函数
  - 创建 `bridge/nim/encoding.py` 桥接编码函数
- **Acceptance Criteria Addressed**: AC-4, FR-5
- **Test Requirements**:
  - `programmatic` TR-6.1: md5/sha1/sha256 函数正确
  - `programmatic` TR-6.2: seq 操作函数正确（map、filter、sum 等）
  - `programmatic` TR-6.3: datetime 函数正确（is_leap_year、days_between 等）
  - `programmatic` TR-6.4: encoding 函数正确（base64）
- **Notes**: 重用现有 `_nim_*.py` 文件的逻辑

## [ ] Task 7: 整合到 vools 主包
- **Priority**: P1
- **Depends On**: Task 6
- **Description**: 
  - 在 `vools/__init__.py` 中导出 `bridge` 子包
  - 更新 `vools/__init__.py` 中的 NIM_*_AVAILABLE 标志
  - 确保向后兼容性（现有 API 保持不变）
- **Acceptance Criteria Addressed**: NFR-4
- **Test Requirements**:
  - `programmatic` TR-7.1: `import vools.bridge` 成功
  - `programmatic` TR-7.2: 现有 API（如 `vools.md5`）仍然可用
  - `programmatic` TR-7.3: `vools.bridge.nim.is_available()` 返回正确值
- **Notes**: 不破坏现有用户代码

## [ ] Task 8: 清理旧的桥接文件
- **Priority**: P2
- **Depends On**: Task 7
- **Description**: 
  - 删除或标记为 deprecated 的 `_nim_loader.py`、`_nim_crypto.py`、`_nim_seq.py` 等文件
  - 确保所有功能已迁移到新的 bridge 包
- **Acceptance Criteria Addressed**: -
- **Test Requirements**:
  - `programmatic` TR-8.1: 所有测试通过（无功能丢失）
  - `human-judgment` TR-8.2: 代码结构清晰，无重复逻辑
- **Notes**: 可以先标记为 deprecated，后续版本再删除
