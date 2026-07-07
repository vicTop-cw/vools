# Checklist

## Engine 适配层
- [x] `BaseEngine` 抽象接口定义完整 (`read_df`, `write_df`)
- [x] `VoolsEngine` 内置引擎实现并测试通过
- [x] `PandasEngine` 包装 openpyxl/xlrd/odf 实现并测试通过
- [x] `register_engine(name, reader, writer)` 注册可用
- [x] `get_engine(name)` 返回引擎实例
- [x] `list_engines()` 列出已注册引擎

## read_excel_df / write_excel_df
- [x] `engine` 参数生效，默认 'vools'
- [x] `engine='openpyxl'` 可切换
- [x] `**engine_kwargs` 透传
- [x] `header=0` 默认值生效 (回归测试)
- [x] 旧调用 (无 engine 参数) 行为不变

## Table SQL 风格方法
- [x] `select(*cols)` 返回新 Table
- [x] `where('age > 25')` 字符串表达式过滤
- [x] `where(lambda r: r['age'] > 25)` 函数式过滤
- [x] `order_by('age', desc=True)` 排序
- [x] `having(predicate)` 分组后过滤
- [x] `agg({'age': 'mean'})` 聚合

## SqlCel 文档
- [x] `vools/xl/README.md` 增加 "SqlCel 函数映射" 章节
- [x] `vools/data/README.md` 新建并包含 SQL 风格方法说明

## 测试
- [x] `tests/xl/test_engines.py` 创建并通过
- [x] `tests/data/test_table_sql.py` 创建并通过
- [x] `tests/xl/test_pandas.py` 回归通过
- [x] `tests/xl/test_table.py` 回归通过
- [x] `tests/xl/test_xl_objects.py` 回归通过
