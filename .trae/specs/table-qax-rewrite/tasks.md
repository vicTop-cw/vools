# Table/QAX 重写工程 - The Implementation Plan (Decomposed and Prioritized Task List)

## [ ] Task 1: Row 类重写 - 继承 Seq + @rself
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 将 Row 类改为继承 Seq
  - 添加 @rself 装饰器
  - Row 的迭代元素是该行的单元格值（按列顺序）
  - 保留原有的 `__getitem__`、`__setitem__`、`to_dict()` 等方法
  - 实现 `__from_parent__` 类方法，支持 Seq 操作结果转回 Row
  - 保持与 Table 的双向引用（Row 知道自己属于哪个 Table 的哪一行）
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: Row 是 Seq 的子类
  - `programmatic` TR-1.2: Row 支持 map/filter/where/select/reduce 等 Seq 方法
  - `programmatic` TR-1.3: Row 的链式调用返回 Row 类型（由 @rself 保证）
  - `programmatic` TR-1.4: Row['列名'] 访问和修改单元格仍然正常
  - `programmatic` TR-1.5: Row.to_dict() 仍然正常工作
- **Notes**: Row 需要同时持有 Table 引用和行索引，以便支持按列名访问

## [ ] Task 2: Column 类重写 - 继承 Seq + @rself
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 将 Column 类改为继承 Seq
  - 添加 @rself 装饰器
  - Column 的迭代元素是该列的单元格值（按行顺序）
  - 保留原有的 `__getitem__`、`__setitem__`、`sum/avg/min/max/count/distinct` 等方法
  - 实现 `__from_parent__` 类方法
  - 保持与 Table 的双向引用
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: Column 是 Seq 的子类
  - `programmatic` TR-2.2: Column 支持所有 Seq 方法
  - `programmatic` TR-2.3: Column 的链式调用返回 Column 类型
  - `programmatic` TR-2.4: Column[i] 访问和修改仍然正常
  - `programmatic` TR-2.5: Column.sum()/avg()/min()/max()/count() 仍然正常
- **Notes**: 原有的 sum/avg 等方法与 Seq 的 reduce 功能有重叠，但保留它们以保持 API 兼容

## [ ] Task 3: Table 类重写 - 继承 Seq + @rself
- **Priority**: high
- **Depends On**: Task 1, Task 2
- **Description**:
  - 将 Table 类改为继承 Seq
  - 添加 @rself 装饰器
  - Table 默认迭代方式：按行迭代（每行是一个 list）
  - 保留所有现有 API（at/row/column/where/select/order_by/group_by/agg 等）
  - 实现 `__from_parent__` 类方法，支持 Seq 操作结果转回 Table
  - 确保 _data 内部数据与 Seq 的 _collection 同步
  - Table 的 Seq 操作结果需要正确处理列名
- **Acceptance Criteria Addressed**: AC-3, AC-5
- **Test Requirements**:
  - `programmatic` TR-3.1: Table 是 Seq 的子类
  - `programmatic` TR-3.2: Table 支持 map/filter/where/select/reduce 等 Seq 方法
  - `programmatic` TR-3.3: Table 的链式调用返回 Table 类型
  - `programmatic` TR-3.4: 所有现有 Table API 仍然正常（向后兼容）
  - `programmatic` TR-3.5: Table 继承的 Seq 方法与 Table 自身的同名方法不冲突（如 where/select）
- **Notes**: Table 自身已有 where/select 等方法，需要确保与 Seq 的同名方法共存且语义一致

## [ ] Task 4: 四种迭代方式实现
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 实现 `iter_rows()` - 返回 Row 对象的迭代器
  - 实现 `iter_cols()` - 返回 Column 对象的迭代器
  - 实现 `iter_cells_row_major()` - 先行后列的单元格值迭代器
  - 实现 `iter_cells_col_major()` - 先列后行的单元格值迭代器
  - 默认迭代（`__iter__`）保持按行迭代 list 的行为
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: iter_rows() 返回 Row 对象，数量正确
  - `programmatic` TR-4.2: iter_cols() 返回 Column 对象，数量正确
  - `programmatic` TR-4.3: iter_cells_row_major() 顺序正确（行优先）
  - `programmatic` TR-4.4: iter_cells_col_major() 顺序正确（列优先）
  - `programmatic` TR-4.5: 默认迭代仍然按行返回 list
- **Notes**: 四种迭代方式是不同的遍历视角，默认迭代保持按行 list 以兼容现有代码

## [ ] Task 5: Qax 类实现 - 继承 Table + @rself + 60+ API
- **Priority**: high
- **Depends On**: Task 3, Task 4
- **Description**:
  - 创建 Qax 类，继承 Table
  - 添加 @rself 装饰器
  - 提供 SqlCel QAX 风格的方法命名（60+ API）
  - 方法分类：
    - 创建类: QAX(), ArrayToQax(), FileToQax(), ExcelToQAX(), QueryToQax() 等
    - 信息类: QAXRows(), QAXCols(), QAXColNames(), QAXName() 等
    - 访问类: GetCell(), GetCell2(), GetRow(), GetCol(), GetCols() 等
    - 修改类: SetCell(), SetCell2(), DelRow(), DelCol(), NewRow(), AddCol() 等
    - 数据操作: QAXSelect(), QAXSort(), QAXDistinct(), QAXFilter() 等
    - 聚合类: QAXSum(), QAXAvg(), QAXCount(), QAXMax(), QAXMin(), QaxGroup(), QAXCompute() 等
    - 连接合并: QaxJoin(), QAXMerge() 等
    - 更新类: QAXUpdate(), QAXReplace(), QAXClear() 等
    - 字符串类: QAXSubstr(), QAXSplit(), QAXConcat() 等
    - 转换类: QAXToArray(), QAXToFile(), showQax() 等
    - 列操作: QAXColToDate(), QAXColToNum(), QAXColToStr(), SetColName(), SetOrdinal() 等
  - 所有方法底层复用 Table 的现有实现
  - 实现 `__from_parent__` 支持 Seq/Table 操作转回 Qax
- **Acceptance Criteria Addressed**: AC-6, AC-7
- **Test Requirements**:
  - `programmatic` TR-5.1: Qax 是 Table 的子类
  - `programmatic` TR-5.2: QAX 核心方法（创建/访问/修改/聚合）至少 30 个可用
  - `programmatic` TR-5.3: 方法名与 SqlCel QAX 风格一致（PascalCase）
  - `programmatic` TR-5.4: Qax 的链式调用返回 Qax 类型
  - `programmatic` TR-5.5: 所有 Table 的方法 Qax 也能使用（继承）
- **Notes**: 不实现需要 Excel COM 环境的方法（如 RngToQAX、QAXToRng、MatchOutput 等），这些方法可以抛出 NotImplementedError

## [ ] Task 6: 向后兼容性验证
- **Priority**: high
- **Depends On**: Task 3, Task 5
- **Description**:
  - 运行所有现有 Table 相关测试（tests/data/ 目录下的）
  - 确保所有现有 API 行为不变
  - 修复任何破坏向后兼容的问题
  - 验证 xl 子包中使用 Table 的部分仍然正常
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-6.1: tests/data/test_table_sql.py 全部通过
  - `programmatic` TR-6.2: tests/data/test_table_qax.py 全部通过
  - `programmatic` TR-6.3: tests/xl/ 目录下涉及 Table 的测试全部通过
  - `programmatic` TR-6.4: Table 的公开 API 签名没有变化
- **Notes**: 如果发现兼容性问题，优先通过别名或适配层解决，而不是修改现有 API

## [ ] Task 7: 单元测试编写
- **Priority**: medium
- **Depends On**: Task 1 - Task 5
- **Description**:
  - 为 Row 的 Seq 能力编写测试
  - 为 Column 的 Seq 能力编写测试
  - 为 Table 的四种迭代方式编写测试
  - 为 Qax 类编写测试（覆盖主要 API）
  - 测试 @rself 装饰器的返回类型正确性
  - 测试 __from_parent__ 转换逻辑
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `programmatic` TR-7.1: Row 单元测试 >= 10 个
  - `programmatic` TR-7.2: Column 单元测试 >= 10 个
  - `programmatic` TR-7.3: Table 迭代方式测试 >= 8 个
  - `programmatic` TR-7.4: Qax 单元测试 >= 20 个
  - `programmatic` TR-7.5: 新增测试总覆盖率 >= 80%
- **Notes**: 测试文件统一放在 tests/data/ 目录下

## [ ] Task 8: Python 3.6 兼容性验证
- **Priority**: medium
- **Depends On**: Task 7
- **Description**:
  - 检查所有新代码是否有 Python 3.6 不支持的语法
  - 确保不使用 Python 3.7+ 才有的特性（如 dataclasses、f-string 的 = 调试语法等）
  - 验证类型注解在 3.6 下不报错（from __future__ import annotations 或字符串注解）
  - 如果有 WSL 中的 Python 3.6 环境，运行测试验证
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `programmatic` TR-8.1: 代码在 Python 3.6 语法下可导入
  - `programmatic` TR-8.2: 不使用 3.7+ 独占特性
  - `programmatic` TR-8.3: 类型注解兼容 3.6
- **Notes**: f-string 和 typing 模块在 3.6 都支持，主要注意不要用 3.7+ 的新特性
