# Tasks

- [x] Task 1: 设计 Engine 适配层接口
  - [x] SubTask 1.1: 定义 `BaseEngine` 抽象接口 (read_df, write_df)
  - [x] SubTask 1.2: 实现 `VoolsEngine` 内置引擎 (基于 vools.xl)
  - [x] SubTask 1.3: 实现 `PandasEngine` 包装 pandas 现有引擎 (engine='openpyxl'/'xlrd'/'odf')

- [x] Task 2: 实现 Engine 注册机制
  - [x] SubTask 1.1: 在 `vools/xl/_highlevel/engines.py` 中实现 `register_engine` / `get_engine` / `list_engines`
  - [x] SubTask 1.2: 在 `vools/xl/__init__.py` 导出 API

- [x] Task 3: 改造 `read_excel_df` / `write_excel_df`
  - [x] SubTask 3.1: 添加 `engine` 参数 (默认 'vools')
  - [x] SubTask 3.2: 添加 `**engine_kwargs` 透传
  - [x] SubTask 3.3: 修改 `header` 默认值为 0，由 VoolsEngine 内部处理 trial 限制
  - [x] SubTask 3.4: 保持向后兼容 (旧调用仍能工作)

- [x] Task 4: Table SQL 风格方法
  - [x] SubTask 4.1: `select(*cols)` 选列 (已存在, 验证)
  - [x] SubTask 4.2: `where(expr)` 表达式过滤 (新增)
  - [x] SubTask 4.3: `order_by(col, desc=False)` 排序 (新增)
  - [x] SubTask 4.4: `having(predicate)` 分组后过滤 (新增)
  - [x] SubTask 4.5: `agg(funcs)` 聚合 (新增)

- [x] Task 5: SqlCel 集成文档
  - [x] SubTask 5.1: 在 `vools/xl/README.md` 添加 "SqlCel 函数映射" 章节
  - [x] SubTask 5.2: 在 `vools/data/README.md` 添加 SQL 风格方法说明

- [x] Task 6: 测试与验证
  - [x] SubTask 6.1: 新增 `tests/xl/test_engines.py` (engine 切换)
  - [x] SubTask 6.2: 新增 `tests/data/test_table_sql.py` (SQL 风格方法)
  - [x] SubTask 6.3: 运行所有 xl/data 测试确保无回归

# Task Dependencies
- Task 2 depends on Task 1
- Task 3 depends on Task 2
- Task 4 与 Task 3 可并行
- Task 5 depends on Task 3, 4
- Task 6 depends on Task 3, 4, 5
