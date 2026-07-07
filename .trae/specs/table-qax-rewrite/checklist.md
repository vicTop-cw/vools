# Table/QAX 重写工程 - Verification Checklist

## Row 类验证
- [ ] Row 类继承自 Seq
- [ ] Row 类使用 @rself 装饰器
- [ ] Row 实现了 __from_parent__ 方法
- [ ] Row 支持按索引迭代（每行的单元格值序列）
- [ ] Row['列名'] 可以访问单元格
- [ ] Row['列名'] = value 可以修改单元格
- [ ] Row.to_dict() 正常工作
- [ ] Row.map() 返回 Row 类型（@rself 保证）
- [ ] Row.filter() 返回 Row 类型
- [ ] Row.where() 可用
- [ ] Row.select() 可用
- [ ] Row.reduce() 可用
- [ ] Row.distinct() 可用
- [ ] Row.size / len(Row) 正确
- [ ] Row 持有对 Table 的引用和行索引

## Column 类验证
- [ ] Column 类继承自 Seq
- [ ] Column 类使用 @rself 装饰器
- [ ] Column 实现了 __from_parent__ 方法
- [ ] Column 支持按行索引迭代（每列的单元格值序列）
- [ ] Column[i] 可以访问单元格
- [ ] Column[i] = value 可以修改单元格
- [ ] Column.name() 返回列名
- [ ] Column.index() 返回列索引
- [ ] Column.to_list() 正常工作
- [ ] Column.sum() 正常（数字列）
- [ ] Column.avg() 正常（数字列）
- [ ] Column.min() 正常
- [ ] Column.max() 正常
- [ ] Column.count() 正常
- [ ] Column.distinct() 正常
- [ ] Column.map() 返回 Column 类型
- [ ] Column.filter() 返回 Column 类型

## Table 类验证
- [ ] Table 类继承自 Seq
- [ ] Table 类使用 @rself 装饰器
- [ ] Table 实现了 __from_parent__ 方法
- [ ] Table 默认迭代按行返回 list（向后兼容）
- [ ] Table.iter_rows() 返回 Row 对象迭代器
- [ ] Table.iter_cols() 返回 Column 对象迭代器
- [ ] Table.iter_cells_row_major() 先行后列遍历单元格
- [ ] Table.iter_cells_col_major() 先列后行遍历单元格
- [ ] Table.at() 正常工作
- [ ] Table.row() 返回字典
- [ ] Table.get_row() 返回 Row 对象
- [ ] Table.column() 返回列表
- [ ] Table.get_col() 返回 Column 对象
- [ ] Table.rows() 返回行数
- [ ] Table.cols() 返回列数
- [ ] Table.columns() 返回列名列表
- [ ] Table.name() 返回表名
- [ ] Table.set_name() 设置表名
- [ ] Table.where() 正常工作
- [ ] Table.select() 正常工作
- [ ] Table.order_by() / sort() 正常
- [ ] Table.group_by() 正常
- [ ] Table.agg() / aggregate() 正常
- [ ] Table.join() 正常
- [ ] Table.merge() 正常
- [ ] Table.set_cell() 正常
- [ ] Table.del_row() 正常
- [ ] Table.del_col() 正常
- [ ] Table.add_col() 正常
- [ ] Table.new_row() 正常
- [ ] Table.to_dicts() 正常
- [ ] Table.to_list() 正常
- [ ] Table.to_array() 正常
- [ ] Table.to_file() 正常
- [ ] Table.to_dataframe() 正常
- [ ] Table.show() 正常
- [ ] Table 继承的 Seq 方法（map/filter/reduce 等）正常
- [ ] Table 的链式调用返回 Table 类型

## Qax 类验证
- [ ] Qax 类存在且可导入
- [ ] Qax 类继承自 Table
- [ ] Qax 类使用 @rself 装饰器
- [ ] Qax 实现了 __from_parent__ 方法
- [ ] QAX 创建方法可用: QAX(), ArrayToQax(), FileToQax()
- [ ] QAX 信息方法可用: QAXRows(), QAXCols(), QAXColNames(), QAXName(), SetQaxName()
- [ ] QAX 访问方法可用: GetCell(), GetCell2(), GetRow(), GetCol(), GetCols()
- [ ] QAX 修改方法可用: SetCell(), SetCell2(), DelRow(), DelCol(), NewRow()
- [ ] QAX 数据操作: QAXSelect(), QAXSort(), QAXDistinct()
- [ ] QAX 聚合方法: QAXSum(), QAXAvg(), QAXCount(), QAXMax(), QAXMin(), QaxGroup(), QAXCompute()
- [ ] QAX 连接合并: QaxJoin(), QAXMerge()
- [ ] QAX 更新方法: QAXUpdate(), QAXReplace(), QAXClear()
- [ ] QAX 字符串方法: QAXSubstr(), QAXSplit(), QAXConcat()
- [ ] QAX 转换方法: QAXToArray(), QAXToFile(), showQax()
- [ ] QAX 列操作: QAXColToDate(), QAXColToNum(), QAXColToStr(), SetColName(), SetOrdinal()
- [ ] QAX 方法命名与 SqlCel 风格一致（PascalCase）
- [ ] Qax 的链式调用返回 Qax 类型
- [ ] 所有 Table 的方法 Qax 也能使用（继承）

## 向后兼容性验证
- [ ] tests/data/test_table_sql.py 全部通过
- [ ] tests/data/test_table_qax.py 全部通过
- [ ] tests/xl/ 目录下所有测试通过
- [ ] Table 公开 API 签名无破坏性变更
- [ ] read_excel / write_excel 便捷函数正常
- [ ] Table.read_excel / Table.write_excel 类方法正常

## Python 3.6 兼容性验证
- [ ] 无 Python 3.7+ 独占语法（如 dataclass、位置专用参数等）
- [ ] 类型注解兼容 3.6（字符串注解或 from __future__ import annotations）
- [ ] f-string 使用符合 3.6 规范（无 = 调试语法）
- [ ] 无 3.7+ 才有的标准库函数/类的使用
- [ ] 所有 import 在 3.6 下不报错

## 性能验证
- [ ] 迭代性能开销 < 10%（与纯列表操作对比）
- [ ] 常用操作（where/select/order_by）无明显性能下降
- [ ] 内存使用无显著增加
