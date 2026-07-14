# vools 集成计划 - 实现任务列表

## [/] Task 1: 创建 FreeBASIC 哈希算法封装模块 (hash_wrapper.bas)
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 基于 E:\vb\FileRecv\hashes\ 中的汇编代码，创建 FreeBASIC 封装模块
  - 实现 fb_hash_md5(), fb_hash_sha1(), fb_hash_sha256() 等函数
  - 支持字符串输入和输出
- **Acceptance Criteria Addressed**: AC-1, AC-4
- **Test Requirements**:
  - `programmatic` TR-1.1: hash_wrapper.bas 编译成功生成 DLL
  - `programmatic` TR-1.2: Python 端调用返回正确哈希值
  - `programmatic` TR-1.3: 结果与 Python hashlib 一致
- **Notes**: 汇编代码为 32 位，需使用 fbc32.exe 编译或适配 64 位

## [ ] Task 2: 创建 vools.crypto.hash 模块 (Python 接口)
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 创建 vools/crypto/hash.py 模块
  - 提供 md5(), sha1(), sha256(), sha512() 等函数
  - 通过 @fbc 装饰器调用 FreeBASIC 封装模块
- **Acceptance Criteria Addressed**: AC-1, AC-4
- **Test Requirements**:
  - `programmatic` TR-2.1: 模块导入成功
  - `programmatic` TR-2.2: 所有哈希函数返回正确值
  - `programmatic` TR-2.3: 支持空字符串输入
- **Notes**: 需要处理字节字符串和 Unicode 字符串的转换

## [ ] Task 3: 创建 FreeBASIC JSON 解析器封装模块 (json_wrapper.bas)
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 基于 E:\vb\FileRecv\杂项\JSON.cls 的逻辑，移植到 FreeBASIC
  - 实现 fb_json_parse(), fb_json_stringify(), fb_json_get_string() 等函数
  - 使用 Dictionary 或自定义结构存储 JSON 对象
- **Acceptance Criteria Addressed**: AC-2, AC-4
- **Test Requirements**:
  - `programmatic` TR-3.1: json_wrapper.bas 编译成功
  - `programmatic` TR-3.2: 解析简单 JSON 对象返回正确结果
  - `programmatic` TR-3.3: 解析 JSON 数组返回正确结果
- **Notes**: FreeBASIC 中没有内置 Dictionary，需要使用 Object 或自定义实现

## [ ] Task 4: 创建 vools.data.json 模块 (Python 接口)
- **Priority**: high
- **Depends On**: Task 3
- **Description**: 
  - 创建 vools/data/json.py 模块
  - 提供 parse(), stringify(), get() 等函数
  - 通过 @fbc 装饰器调用 FreeBASIC JSON 封装模块
- **Acceptance Criteria Addressed**: AC-2, AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: 模块导入成功
  - `programmatic` TR-4.2: parse() 正确解析 JSON 字符串
  - `programmatic` TR-4.3: stringify() 正确序列化 Python 对象
- **Notes**: 需要处理 Python 对象与 FreeBASIC 结构的转换

## [ ] Task 5: 创建 vools.data.vvalidate 模块 (验证模式库)
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 从 E:\vb\FileRecv\杂项\Vfx.cls 提取正则验证模式
  - 创建 vools/data/vvalidate.py 模块
  - 提供 is_email(), is_mobile(), is_idcard(), is_plate() 等函数
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-5.1: 模块导入成功
  - `programmatic` TR-5.2: 所有验证函数返回正确布尔值
  - `programmatic` TR-5.3: 支持自定义正则表达式扩展
- **Notes**: 使用 Python re 模块实现，无需 FreeBASIC 桥接

## [ ] Task 6: 注册模块到 __init__.py
- **Priority**: medium
- **Depends On**: Task 1, Task 3
- **Description**: 
  - 更新 vools/bridge/freebasic/modules/__init__.py，注册 hash_wrapper 和 json_wrapper 模块
  - 更新 vools/crypto/__init__.py，导出 hash 模块
  - 更新 vools/data/__init__.py，导出 json 和 vvalidate 模块
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-6.1: from vools.crypto import hash 成功
  - `programmatic` TR-6.2: from vools.data import json, vvalidate 成功
  - `programmatic` TR-6.3: list_modules() 返回包含 hash_wrapper 和 json_wrapper
- **Notes**: 需要保持与现有模块的一致性

## [ ] Task 7: 编写单元测试
- **Priority**: high
- **Depends On**: Task 2, Task 4, Task 5
- **Description**: 
  - 创建 tests/test_crypto_hash.py 测试哈希模块
  - 创建 tests/test_data_json.py 测试 JSON 模块
  - 创建 tests/test_data_vvalidate.py 测试验证模块
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-5
- **Test Requirements**:
  - `programmatic` TR-7.1: 所有测试用例通过
  - `programmatic` TR-7.2: 哈希性能测试达到 hashlib 的 80% 以上
  - `programmatic` TR-7.3: JSON 解析测试覆盖嵌套对象和数组
- **Notes**: 需要使用 pytest 框架

## [ ] Task 8: 更新文档
- **Priority**: medium
- **Depends On**: Task 2, Task 4, Task 5
- **Description**: 
  - 更新 docs/crypto/index.md 添加哈希模块文档
  - 更新 docs/data/index.md 添加 JSON 和验证模块文档
  - 添加全局唯一性编号
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3
- **Test Requirements**:
  - `human-judgment` TR-8.1: 文档内容完整，示例代码可运行
  - `human-judgment` TR-8.2: 全局唯一性编号正确
  - `human-judgment` TR-8.3: 文档内部链接正确
- **Notes**: 遵循现有文档风格和结构
