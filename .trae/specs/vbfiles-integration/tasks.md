# VB6 文件集成计划 - 实现任务列表

## [x] Task 1: 创建验证模式库模块
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 创建 vools/data/validator.py 模块，包含 Vfx.cls 中的正则验证模式
  - 实现验证函数：is_email, is_mobile, is_id_card_15, is_id_card_18, is_plate_number, is_url, is_username, is_password, is_chinese_name, is_phone_with_area, is_phone_without_area
  - 实现字符串工具函数：is_all_chinese, contains_chinese, starts_with, ends_with
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `programmatic` TR-1.1: 每个验证函数至少有 3 个测试用例（有效、无效、边界）
  - `programmatic` TR-1.2: 字符串工具函数测试覆盖所有场景
- **Notes**: 正则模式直接从 Vfx.cls 的 Vfx_RegExpPattern 方法提取

## [x] Task 2: 更新 vools/data/__init__.py 导出验证模块
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 在 vools/data/__init__.py 中导入并导出 validator 模块的所有函数
  - 更新 __all__ 列表
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: 验证模块可通过 `from vools.data import is_email` 导入
  - `programmatic` TR-2.2: 所有导出函数可正常调用
- **Notes**: 确保相对导入正确

## [x] Task 3: 为验证模块编写单元测试
- **Priority**: high
- **Depends On**: Task 2
- **Description**: 
  - 创建 tests/data/test_validator.py 测试文件
  - 测试所有验证函数和字符串工具函数
  - 测试覆盖有效、无效、边界等场景
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `programmatic` TR-3.1: 所有测试用例通过
  - `programmatic` TR-3.2: 测试覆盖率 >= 80%
- **Notes**: 使用 pytest 框架

## [x] Task 4: 将 JSON 解析器整合到 serialize 模块
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 创建 vools/serialize/backends/vb_json_backend.py 模块
  - 将 VB6 JSON.cls 的解析逻辑移植到 Python
  - 实现 parse() 和 toString() 方法
  - 将新后端集成到 serialize 模块
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-4.1: JSON 解析结果与标准库 json.loads 一致
  - `programmatic` TR-4.2: JSON 序列化结果与标准库 json.dumps 一致（顺序可能不同）
  - `programmatic` TR-4.3: 处理嵌套对象和数组
- **Notes**: VB6 JSON.cls 使用 Scripting.Dictionary 和 Collection，需要映射到 Python dict 和 list

## [x] Task 5: 更新 serialize 模块注册新后端
- **Priority**: medium
- **Depends On**: Task 4
- **Description**: 
  - 在 vools/serialize/__init__.py 中注册 vb_json 后端
  - 更新 get_backend() 函数支持 vb_json 后端
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-5.1: 可通过 get_backend('vb_json') 获取后端实例
  - `programmatic` TR-5.2: vb_json 后端的 dumps/loads 功能正常
- **Notes**: 保持向后兼容

## [x] Task 6: 为 VB JSON 后端编写单元测试
- **Priority**: medium
- **Depends On**: Task 5
- **Description**: 
  - 创建 tests/serialize/test_vb_json.py 测试文件
  - 测试 JSON 解析和序列化功能
  - 测试与标准库结果的兼容性
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-6.1: 所有测试用例通过
  - `programmatic` TR-6.2: 测试覆盖复杂 JSON 结构
- **Notes**: 使用 pytest 框架

## [ ] Task 7: 将剪贴板管理功能整合到 monitoring 模块
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 更新 vools/reactive/monitoring/clipboard.py 模块
  - 从 cClip.cls 提取剪贴板保存功能
  - 实现 save_clips_text_to_file(), save_clips_picture_to_file(), save_all_to_file() 方法
  - 添加剪贴板内容过滤功能（正则模式）
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-7.1: 剪贴板文本保存功能正常（Windows 平台）
  - `programmatic` TR-7.2: 剪贴板图片保存功能正常（Windows 平台）
  - `programmatic` TR-7.3: 正则过滤功能正常
- **Notes**: 仅支持 Windows 平台，使用 ctypes 调用 Win32 API

## [ ] Task 8: 将 Windows 消息钩子功能整合到 monitoring 模块
- **Priority**: low
- **Depends On**: None
- **Description**: 
  - 创建 vools/reactive/monitoring/window_hook.py 模块
  - 从 cSubclass.cls 提取窗口子类化逻辑
  - 实现窗口消息钩子功能
  - 支持 MSG_BEFORE、MSG_AFTER、MSG_BEFORE_AND_AFTER 三种回调模式
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-8.1: 窗口消息钩子注册和回调功能正常（Windows 平台）
  - `programmatic` TR-8.2: 三种回调模式正常工作
  - `programmatic` TR-8.3: 钩子可正常卸载
- **Notes**: 仅支持 Windows 平台，需要使用 ctypes 调用 Win32 API（SetWindowLong、CallWindowProc 等）

## [ ] Task 9: 更新 monitoring 模块 __init__.py
- **Priority**: medium
- **Depends On**: Task 7, Task 8
- **Description**: 
  - 在 vools/reactive/monitoring/__init__.py 中导入并导出新功能
  - 更新 __all__ 列表
- **Acceptance Criteria Addressed**: AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-9.1: 新功能可通过 `from vools.reactive.monitoring import ...` 导入
  - `programmatic` TR-9.2: 所有导出函数可正常调用
- **Notes**: 确保相对导入正确

## [ ] Task 10: 为 monitoring 新功能编写单元测试
- **Priority**: medium
- **Depends On**: Task 9
- **Description**: 
  - 创建 tests/reactive/test_monitoring_vb.py 测试文件
  - 测试剪贴板保存功能（Windows 平台）
  - 测试窗口消息钩子功能（Windows 平台）
- **Acceptance Criteria Addressed**: AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-10.1: 剪贴板测试用例通过（Windows 平台）
  - `programmatic` TR-10.2: 窗口钩子测试用例通过（Windows 平台）
- **Notes**: 使用 pytest 框架，非 Windows 平台跳过测试

## [ ] Task 11: 更新文档
- **Priority**: low
- **Depends On**: Task 3, Task 6, Task 10
- **Description**: 
  - 更新 docs/data/index.md 添加验证模块文档
  - 更新 docs/reactive/monitoring.md 添加剪贴板和窗口钩子文档
  - 更新 docs/serialize/index.md 添加 VB JSON 后端文档
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4, AC-5
- **Test Requirements**:
  - `human-judgement` TR-11.1: 文档完整，包含函数签名和示例
  - `human-judgement` TR-11.2: 示例代码可运行
- **Notes**: 遵循 mkdocs 文档格式
