# xl/data Engine Adapter + SqlCel Integration Spec

## Why
当前 `vools.xl` 的 pandas 接口 (`read_excel_df` / `write_excel_df`) 只内置 vools.xl 自身引擎，不支持 pandas 的 `engine` 参数生态，限制了与 pandas 生态的互通。同时 `D:\SqlCel` 提供了 SQL 风格 Excel 自定义函数库 (`D_FIND/D_VLOOKUP/D_SUMIF/D_COUNTIF/D_SELECT`)，与 `vools.xl` + `vools.data` 在数据处理场景上有强协同价值，需要规划引擎适配层和 SqlCel 集成点。

## What Changes
- **xl**: 新增 `engine` 适配层，让 `read_excel_df/write_excel_df` 支持 `engine='vools'` / `'openpyxl'` / `'xlrd'` / `'odf'` 等，与 pandas 生态一致
- **xl**: 新增底层 `register_engine()` 接口，允许第三方引擎注册
- **data/Table**: 新增 `Table.to_pandas(engine='vools')` / `Table.from_pandas(engine='vools')` 与 `Table.exec()` 风格的方法签名占位
- **data**: 评估并引入 SqlCel 风格的 SQL 风格数据集方法 `select/where/group_by/having/order_by/limit/agg` 扩展
- **docs**: 文档化 engine 适配机制和 SqlCel 函数映射
- 标记为 **BREAKING**: `read_excel_df/write_excel_df` 默认参数从 `header=1` 调整为 `header=0`，由 `engine` 层显式控制，避免 trial 限制耦合

## Impact
- Affected specs: 暂无直接相关 spec (新增 change-id)
- Affected code:
  - `vools/xl/_highlevel/pandas_io.py` (新增 engine 参数)
  - `vools/xl/_highlevel/__init__.py` (导出新 API)
  - `vools/xl/__init__.py` (导出 `register_engine` / `get_engine`)
  - `vools/data/table.py` (新增 SQL 风格方法)
  - `vools/data/__init__.py` (导出)
  - `vools/xl/README.md` (文档)
  - `vools/data/README.md` (新建)

## ADDED Requirements

### Requirement: xl pandas engine adapter
系统 SHALL 在 `vools.xl` 提供 `engine` 参数和 `register_engine()` 注册机制，使 `read_excel_df/write_excel_df` 与 `pd.read_excel/to_excel` 行为一致。

#### Scenario: Default engine unchanged
- **WHEN** 调用 `read_excel_df('x.xlsx')` 不传 `engine`
- **THEN** 使用 vools.xl 内置引擎，与当前行为一致

#### Scenario: Switch engine to openpyxl
- **WHEN** 调用 `read_excel_df('x.xlsx', engine='openpyxl')`
- **THEN** 通过 pandas + openpyxl 引擎读取，返回 DataFrame

#### Scenario: Custom engine registration
- **WHEN** 调用 `register_engine('myengine', my_reader, my_writer)`
- **THEN** `read_excel_df(..., engine='myengine')` 调用 `my_reader(filename, **kwargs)`

#### Scenario: Write engine selection
- **WHEN** 调用 `write_excel_df('x.xlsx', df, engine='openpyxl')`
- **THEN** 通过 pandas + openpyxl 引擎写入

### Requirement: data Table SQL-style query API
系统 SHALL 在 `vools.data.Table` 引入 SQL 风格查询方法，便于用户使用熟悉的 SQL 语法操作数据。

#### Scenario: select + where
- **WHEN** `table.select('name', 'age').where('age > 25')`
- **THEN** 返回符合条件行的子集 (Table)

#### Scenario: group_by + agg
- **WHEN** `table.group_by('city').agg({'age': 'mean', 'salary': 'sum'})`
- **THEN** 返回按 city 分组的聚合 Table

#### Scenario: order_by + limit
- **WHEN** `table.order_by('age', desc=True).limit(5)`
- **THEN** 返回按 age 降序的前 5 行

### Requirement: SqlCel function reference
系统 SHALL 在 `vools.xl` 文档中映射 SqlCel Excel UDF 与 vools.xl/data Table 方法对应关系，便于用户迁移。

#### Scenario: Lookup SqlCel equivalent
- **WHEN** 用户查询 D_VLOOKUP 的 Python 等价
- **THEN** 文档显示对应 `Table.where()` + `select()` 链式调用

## MODIFIED Requirements

### Requirement: pandas header default
原 `read_excel_df(header=1)` 默认值 改为 `header=0`，由 vools engine 内部处理 trial 限制 (写入时自动从第 1 行开始)。

#### Scenario: 兼容用户调用
- **WHEN** 用户调用 `read_excel_df('x.xlsx')` 不传 header
- **THEN** 默认从第 0 行读取表头，vools engine 自动处理 trial 限制

## REMOVED Requirements
无
