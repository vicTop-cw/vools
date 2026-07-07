# Table/QAX 重写工程 - Product Requirement Document

## Overview
- **Summary**: 将 vools.data.Table 类及其相关的 Row/Column 类重写为继承 Seq + @rself 装饰器的架构，并新增 Qax 类提供 SqlCel Qax 风格的 60+ API，同时支持四种迭代方式（按行、按列、按 cell 先行后列、按 cell 先列后行）。
- **Purpose**: 统一数据结构 API 风格，复用 Seq 丰富的链式操作能力，简化代码维护，提供 SqlCel 用户熟悉的 Qax 数据集操作体验。
- **Target Users**: vools 库用户，SqlCel 迁移用户，数据处理开发者。

## Goals
- Row 类继承 Seq 并使用 @rself，支持行级链式操作
- Column 类继承 Seq 并使用 @rself，支持列级链式操作
- Table 类继承 Seq 并使用 @rself，支持表级链式操作
- Table 支持四种迭代方式：按行、按列、按 cell 先行后列、按 cell 先列后行
- Qax 类继承 Table 并使用 @rself，提供 SqlCel Qax 风格的 60+ API
- 保持向后兼容，现有 Table API 不破坏
- 复用 Seq 的 map/filter/where/select/reduce 等能力

## Non-Goals (Out of Scope)
- 不集成 SqlCel 原生 DLL（纯 Python 实现）
- 不引入新的外部依赖
- 不修改 xl 子包的现有 API
- 不实现 Qax 的 Excel COM 相关功能（如 RngToQAX、QAXToRng 等需要 Excel 环境的方法）
- 不修改 dll32/bridge 等其他子包

## Background & Context
- 现有的 VList/VText 已经采用了「继承 Seq + @rself」的模式，效果良好
- Table/Row/Column 当前是独立实现，没有复用 Seq 的能力，代码重复多
- SqlCel 的 QAX 数据集有 60+ 便捷方法，用户熟悉该 API 风格
- 用户希望 xl 子包能够返回 Qax 数据集对象，提供类似 SqlCel 的体验
- @rself 装饰器限制为单继承，因此 Table 只能继承 Seq（不能同时继承其他类）

## Functional Requirements
- **FR-1**: Row 类继承 Seq，每行元素是单元格值，支持 Seq 的所有链式方法（map/filter/where/select/reduce 等）
- **FR-2**: Column 类继承 Seq，每列元素是单元格值，支持 Seq 的所有链式方法
- **FR-3**: Table 类继承 Seq，默认迭代方式为按行迭代（每行是一个列表或 Row 对象）
- **FR-4**: Table 提供四种迭代器生成方法：iter_rows()、iter_cols()、iter_cells_row_major()、iter_cells_col_major()
- **FR-5**: Table 继承后仍然保持现有的所有 API（at/row/column/where/select/order_by 等）
- **FR-6**: Qax 类继承 Table，提供 SqlCel QAX 风格的方法命名（如 QAXRows/QAXCols/GetCell/SetCell 等）
- **FR-7**: Qax 类提供 60+ API，覆盖创建、访问、修改、转换、聚合、字符串操作等类别
- **FR-8**: 所有类使用 @rself 装饰器，确保链式调用返回正确的子类类型
- **FR-9**: 提供 __from_parent__ 方法，支持 Seq 操作结果正确转回 Table/Row/Column/Qax 类型

## Non-Functional Requirements
- **NFR-1**: 性能：迭代和链式操作的性能开销不超过 10%（与纯列表操作相比）
- **NFR-2**: 兼容性：Python 3.6 和 Python 3.13 均支持
- **NFR-3**: 向后兼容：现有 Table 的所有公开 API 保持不变
- **NFR-4**: 可维护性：通过继承减少重复代码，代码行数减少 20% 以上

## Constraints
- **Technical**: 必须使用现有的 Seq 类和 @rself 装饰器，不修改 seq.py 和 rself.py 的核心逻辑
- **Technical**: @rself 只支持单继承，因此 Row/Column/Table/Qax 只能继承 Seq
- **Technical**: 必须支持 Python 3.6（不能使用 dataclasses、f-string 等 3.6 不支持的特性... f-string 3.6 支持）
- **Business**: 保持现有 API 兼容性，不引入破坏性变更
- **Dependencies**: 仅依赖 vools 内部已有的模块（seq、decorators.rself 等）

## Assumptions
- 用户可以接受 Table 继承 Seq 后，`for row in table:` 默认返回列表而不是 Row 对象（可以通过 iter_rows() 获取 Row 对象）
- Qax 的 60+ API 是方法名对齐，底层实现复用 Table 的现有逻辑
- 不需要实现 Qax 的所有 60+ 方法的每一个细节，主要是提供 API 命名和基本功能
- 四种迭代方式中，默认迭代是按行（与现有行为一致）

## Acceptance Criteria

### AC-1: Row 继承 Seq 并使用 @rself
- **Given**: 一个 Table 实例
- **When**: 调用 `table.get_row(i)` 获取 Row 对象
- **Then**: Row 对象支持所有 Seq 方法（map/filter/where/select/reduce/size/distinct 等），且链式调用返回 Row 类型
- **Verification**: `programmatic`

### AC-2: Column 继承 Seq 并使用 @rself
- **Given**: 一个 Table 实例
- **When**: 调用 `table.get_col(name)` 获取 Column 对象
- **Then**: Column 对象支持所有 Seq 方法，且链式调用返回 Column 类型
- **Verification**: `programmatic`

### AC-3: Table 继承 Seq 并使用 @rself
- **Given**: 一个 Table 实例
- **When**: 调用 `table.map(...)` 或 `table.filter(...)` 等 Seq 方法
- **Then**: 返回值类型正确（返回 Table 或对应类型），且链式调用可用
- **Verification**: `programmatic`

### AC-4: 四种迭代方式
- **Given**: 一个 Table 实例
- **When**: 分别调用 iter_rows()/iter_cols()/iter_cells_row_major()/iter_cells_col_major()
- **Then**: 四种迭代器按正确顺序产生元素
- **Verification**: `programmatic`

### AC-5: 向后兼容
- **Given**: 现有的 Table 测试文件
- **When**: 运行所有现有测试
- **Then**: 所有测试通过，无破坏性变更
- **Verification**: `programmatic`

### AC-6: Qax 类存在并继承 Table
- **Given**: 导入 vools.data.Qax
- **When**: 创建 Qax 实例并调用 SqlCel 风格方法
- **Then**: Qax 继承自 Table，支持 60+ API 方法名
- **Verification**: `programmatic`

### AC-7: QAX 核心 API 可用
- **Given**: Qax 实例
- **When**: 调用常用方法（QAXRows/QAXCols/GetCell/SetCell/QAXSelect/QAXSort/QAXSum/QAXAvg 等）
- **Then**: 方法正常工作，返回正确结果
- **Verification**: `programmatic`

### AC-8: Python 3.6 兼容性
- **Given**: Python 3.6 环境
- **When**: 导入 vools.data 并使用 Table/Row/Column/Qax
- **Then**: 无语法错误，功能正常
- **Verification**: `programmatic`

### AC-9: 单元测试覆盖
- **Given**: 测试文件
- **When**: 运行测试
- **Then**: 新增功能的测试覆盖率 >= 80%
- **Verification**: `programmatic`

## Open Questions
- [ ] Table 默认迭代的元素是 list 还是 Row 对象？（当前假设是 list，因为 Row 对象有额外开销）
- [ ] Qax 类放在哪个模块？vools.data.qax 还是直接 vools.data？
- [ ] Qax 的方法命名是完全复刻 SqlCel（如 `QAXRows`）还是 Python 化（如 `qax_rows`）？
