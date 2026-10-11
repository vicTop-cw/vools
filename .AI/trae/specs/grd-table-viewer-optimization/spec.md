# GRD Table Viewer 优化 - Product Requirement Document

## Overview
- **Summary**: 完善 GRD Table Viewer 的列排序功能、性能优化、xl 模块集成、测试和文档，提供一个功能完整、性能优良的表格数据查看工具。
- **Purpose**: 解决当前表格查看器缺少列头点击排序、排序指示符显示等问题，确保大数据量加载性能，完善 xl 模块集成，提供完整的测试和文档支持。
- **Target Users**: 使用 vools.xl 模块进行数据处理和可视化的开发者和数据分析师。

## Goals
- 完善列排序功能：点击列头触发排序（升序→降序→无排序 循环切换）
- 排序时保持行数据完整性，自动识别数字列和字符串列
- 在列头上显示排序指示符（↑↓符号）
- 确保大数据量（1万行 × 10列）加载性能良好
- 完善 xl 模块集成，确保 API 正确导出
- 提供完整的单元测试覆盖
- 提供详细的使用文档

## Non-Goals (Out of Scope)
- 不实现单元格编辑功能
- 不实现数据过滤功能
- 不实现图表可视化功能
- 不实现导出到其他格式的功能
- 不实现多语言支持

## Background & Context
- GRD Table Viewer 基于 FreeBASIC GRD 网格控件实现，通过 DLL 方式供 Python 调用
- Python 端已实现 TableViewer 类和 show_table 函数，支持二维列表、Sheet、Book、DataFrame 多种数据源
- 排序逻辑函数已实现（TV_SortSheet 等），但缺少列头点击触发和排序指示符
- xl 模块已基本集成 viewer，但需要完善导出和循环导入处理

## Functional Requirements
- **FR-1**: 点击列头触发排序，支持升序→降序→无排序 循环切换
- **FR-2**: 排序时保持行数据完整性（整行跟着排序）
- **FR-3**: 自动识别数字列和字符串列，使用不同的排序算法
- **FR-4**: 在列头上显示排序指示符（↑↓符号）
- **FR-5**: 第一行（表头）不参与排序
- **FR-6**: 支持 1万行 × 10列 数据的快速加载
- **FR-7**: xl 模块正确导出所有 viewer 相关 API
- **FR-8**: Sheet.show() 和 Book.show() 方法完善可用
- **FR-9**: 提供完整的单元测试（不包含 GUI 实际显示）

## Non-Functional Requirements
- **NFR-1**: 1万行 × 10列数据加载时间 < 2秒
- **NFR-2**: 排序操作响应时间 < 500ms（1万行数据）
- **NFR-3**: 内存使用合理，无明显内存泄漏
- **NFR-4**: 代码遵循现有项目的编码规范
- **NFR-5**: 兼容 Python 3.6 到 Python 3.13

## Constraints
- **Technical**: 必须使用 FreeBASIC + GRD 控件实现 GUI 部分，Python 端使用 ctypes 调用 DLL
- **Business**: 必须保持向后兼容，不破坏现有 API
- **Dependencies**: 依赖 vools/bridge/freebasic/modules/ 下的 grd_grid.dll 和 table_viewer.dll

## Assumptions
- GRD 控件的 GRDN_COLSSELECTED 通知在列头点击时会发送
- 现有排序函数（TV_SortSheet 等）功能正确
- 用户在 Windows 平台上使用（FreeBASIC DLL 依赖 Windows API）

## Acceptance Criteria

### AC-1: 列头点击触发排序
- **Given**: 表格查看器已打开，显示有数据
- **When**: 用户点击某一列的列头
- **Then**: 该列数据按升序排列，列头显示 ↑ 符号
- **Verification**: `human-judgment`
- **Notes**: 需要手动测试 GUI 交互

### AC-2: 排序循环切换
- **Given**: 某列已按升序排列
- **When**: 用户再次点击该列列头
- **Then**: 该列数据按降序排列，列头显示 ↓ 符号
- **Verification**: `human-judgment`

### AC-3: 取消排序
- **Given**: 某列已按降序排列
- **When**: 用户第三次点击该列列头
- **Then**: 数据恢复原始顺序，列头无排序指示符
- **Verification**: `human-judgment`

### AC-4: 排序保持行完整性
- **Given**: 表格有多列数据
- **When**: 按某列排序
- **Then**: 每行的各列数据保持对应关系，不出现错位
- **Verification**: `programmatic`

### AC-5: 表头不参与排序
- **Given**: 表格有表头行
- **When**: 按任意列排序
- **Then**: 表头行始终在第一行，不参与排序
- **Verification**: `programmatic`

### AC-6: 数字列排序正确
- **Given**: 某列包含数字数据
- **When**: 按该列排序
- **Then**: 按数值大小排序，而非字符串字典序
- **Verification**: `programmatic`

### AC-7: 大数据加载性能
- **Given**: 1万行 × 10列的测试数据
- **When**: 加载到表格查看器
- **Then**: 加载时间 < 2秒
- **Verification**: `programmatic`

### AC-8: xl 模块正确导出
- **Given**: 导入 vools.xl 模块
- **When**: 检查 __all__ 和可用属性
- **Then**: TableViewer 和 show_table 可正确导入
- **Verification**: `programmatic`

### AC-9: Sheet.show() 方法可用
- **Given**: 一个 Sheet 对象
- **When**: 调用 sheet.show()
- **Then**: 不报错，能正确创建查看器（不实际显示）
- **Verification**: `programmatic`

### AC-10: 单元测试通过
- **Given**: 测试文件 tests/xl/test_viewer.py
- **When**: 运行测试
- **Then**: 所有测试通过
- **Verification**: `programmatic`

## Open Questions
- [ ] 是否需要支持多列组合排序？
- [ ] 是否需要保存原始数据顺序以便取消排序？
- [ ] 性能测试的基准数据规模是否合适？
