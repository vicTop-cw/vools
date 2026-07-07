# GRD Table Viewer 优化 - The Implementation Plan (Decomposed and Prioritized Task List)

## [ ] Task 1: 列排序功能完善（FreeBASIC 端）
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 TV_WndProc 的 WM_NOTIFY 中处理 GRDN_COLSSELECTED 通知
  - 实现列头点击触发排序循环（升序→降序→无排序）
  - 添加排序指示符（↑↓）到列头
  - 确保表头行不参与排序
  - 添加保存原始列头文本的功能，以便取消排序时恢复
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4, AC-5, AC-6
- **Test Requirements**:
  - `human-judgement` TR-1.1: 点击列头能触发排序，列头显示排序指示符
  - `human-judgement` TR-1.2: 排序循环切换正常（升序→降序→无排序）
  - `programmatic` TR-1.3: 排序函数逻辑正确，保持行完整性
- **Notes**: 需要修改 table_viewer.bas，在 TVSheetInfo 中添加原始表头存储

## [ ] Task 2: 性能优化与测试
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 测试 1万行 × 10列 数据加载时间
  - 优化数据设置方式（如需要）
  - 确保 Python 端数据转换效率
  - 编写性能测试脚本
- **Acceptance Criteria Addressed**: AC-7
- **Test Requirements**:
  - `programmatic` TR-2.1: 1万行 × 10列数据加载时间 < 2秒
  - `programmatic` TR-2.2: 排序操作响应时间 < 500ms（1万行数据）
- **Notes**: 性能测试需要考虑 Python 到 DLL 的数据传递开销

## [ ] Task 3: xl 模块集成完善
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 检查 vools/xl/__init__.py 的导出是否完整
  - 检查 vools/xl/viewer/__init__.py 的导出
  - 确保 Sheet.show() 和 Book.show() 实现完善
  - 确保循环导入问题已正确处理
  - 更新 __all__ 列表
- **Acceptance Criteria Addressed**: AC-8, AC-9
- **Test Requirements**:
  - `programmatic` TR-3.1: from vools.xl import TableViewer, show_table 正常工作
  - `programmatic` TR-3.2: Sheet.show() 方法不报错（不实际显示窗口）
  - `programmatic` TR-3.3: Book.show() 方法不报错（不实际显示窗口）
- **Notes**: 测试时避免实际创建 GUI 窗口，防止阻塞

## [ ] Task 4: 创建测试文件 tests/xl/test_viewer.py
- **Priority**: high
- **Depends On**: Task 3
- **Description**: 
  - 模块导入测试
  - 数据转换测试（list、Sheet、Book、DataFrame）
  - TableViewer 类结构测试
  - 辅助函数测试
  - 不做 GUI 实际显示测试（避免阻塞 CI）
- **Acceptance Criteria Addressed**: AC-10
- **Test Requirements**:
  - `programmatic` TR-4.1: 所有测试用例通过
  - `programmatic` TR-4.2: 测试覆盖数据转换、类结构、辅助函数
- **Notes**: 测试需要 mock DLL 调用或仅测试纯 Python 部分

## [ ] Task 5: 创建文档 vools/xl/viewer/README.md
- **Priority**: medium
- **Depends On**: Task 1, Task 3
- **Description**: 
  - 功能介绍
  - 快速开始
  - API 文档（TableViewer 类、show_table 函数）
  - 支持的数据源类型
  - 使用示例（二维列表、Sheet、Book、DataFrame）
  - 常见问题
- **Acceptance Criteria Addressed**: （文档类，无对应 AC）
- **Test Requirements**:
  - `human-judgement` TR-5.1: 文档内容完整、清晰、准确
  - `human-judgement` TR-5.2: 示例代码可运行
- **Notes**: 文档使用中文编写
