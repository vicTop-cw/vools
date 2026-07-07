# vools.xl - Excel 读写库

基于 LibXL v3.8.0 的 Excel 文件读写库，支持 .xls 和 .xlsx 格式。

## 功能特点

- **高性能**：使用原生 LibXL C/C++ 库，读写速度远超纯 Python 实现
- **零依赖**：不需要安装 Excel 或其他 COM 组件
- **三层 API**：对象级 API、批量矩阵 API、便捷函数三种使用方式
- **格式丰富**：支持字体、颜色、对齐、边框、填充等单元格格式
- **工作表操作**：支持添加、删除、重命名工作表，合并单元格等
- **公式支持**：支持读写 Excel 公式
- **Pandas 集成**：与 pandas DataFrame 无缝互转
- **批量操作**：支持二维矩阵批量读写，性能提升 4x+
- **表格展示**：内置文本表格展示器，支持控制台快速预览数据

## 快速开始

### 方式1：便捷函数（最简单）

```python
from vools.xl import read_excel, write_excel

# 写入 Excel
data = [
    {'name': 'Alice', 'age': 25, 'city': 'New York'},
    {'name': 'Bob', 'age': 30, 'city': 'Los Angeles'},
]
write_excel('output.xls', data, sheet_name='Users')

# 读取 Excel
data = read_excel('input.xls')
for row in data:
    print(row['name'], row['age'])
```

### 方式2：批量矩阵读写（性能最优）

```python
from vools.xl import read_excel_matrix, write_excel_matrix

# 批量写入 - 性能比逐单元格快 4x+
data = [
    ['Name', 'Age', 'City'],
    ['Alice', 25, 'New York'],
    ['Bob', 30, 'Los Angeles'],
]
write_excel_matrix('output.xlsx', data)

# 批量读取
matrix = read_excel_matrix('input.xlsx', rows=1000, cols=10)
for row in matrix:
    print(row[0], row[1])
```

### 方式3：pandas DataFrame（数据分析）

```python
from vools.xl import read_excel_df, write_excel_df
import pandas as pd

# 写入
df = pd.DataFrame({'name': ['Alice', 'Bob'], 'age': [25, 30]})
write_excel_df('output.xlsx', df)

# 读取
df = read_excel_df('input.xlsx')
print(df.describe())
```

### 方式4：控制台表格预览

```python
from vools.xl import show_table

# 预览二维列表
data = [
    ['Name', 'Age', 'City'],
    ['Alice', 25, 'New York'],
    ['Bob', 30, 'Los Angeles'],
]
show_table(data, title='用户信息表')

# 预览 Sheet
from vools.xl import Book
with Book() as book:
    sheet = book.add_sheet('Data')
    sheet.write_str(0, 0, 'Name')
    sheet.write_str(0, 1, 'Age')
    sheet.write_str(1, 0, 'Alice')
    sheet.write_num(1, 1, 25)
    sheet.show(title='Sheet 预览')
    # 或使用 show_table(sheet)
```

### 方式5：对象级 API（功能最全）

```python
from vools.xl import Book

# 创建工作簿（默认 xlsx 格式）
with Book() as book:
    # 添加工作表
    sheet = book.add_sheet('Sheet1')

    # 写入数据
    sheet.write_str(0, 0, 'Name')
    sheet.write_str(0, 1, 'Age')
    sheet.write_str(1, 0, 'Alice')
    sheet.write_num(1, 1, 25)

    # 设置格式
    fmt = book.add_format()
    fmt.bold = True
    fmt.align_h = 2  # 居中
    sheet.write_str(0, 0, 'Name', fmt)
    sheet.write_str(0, 1, 'Age', fmt)

    # 合并单元格
    sheet.set_merge(2, 2, 0, 2)
    sheet.write_str(2, 0, 'Merged Cell')

    # 保存文件（默认 xlsx）
    book.save('output.xlsx')

# 如需 xls 格式，传入 xml_format=False
with Book(xml_format=False) as book:
    sheet = book.add_sheet('Sheet1')
    book.save('output.xls')
```

## 模块架构

```
vools/xl/
├── __init__.py          # 主入口，导出所有公共 API
├── _core/               # 核心层
│   ├── __init__.py
│   ├── loader.py        # DLL 加载器（单例模式）
│   └── api.py           # 低层 C API 封装（ctypes 声明 + 枚举常量）
├── _objects/            # 对象封装层
│   ├── __init__.py
│   ├── book.py          # Book 类（工作簿）
│   ├── sheet.py         # Sheet 类（工作表）
│   ├── format.py        # Format 类（单元格格式）
│   └── font.py          # Font 类（字体）
├── _highlevel/          # 高级便捷函数
│   ├── __init__.py
│   └── utils.py         # read_excel, write_excel 等
├── _utils/              # 工具函数
│   ├── __init__.py
│   └── helpers.py       # 地址转换、颜色转换等
└── _dlls/               # 内置 DLL 文件
    └── libxl.dll
```

## API 参考

### Book 类

| 方法 | 说明 |
|------|------|
| `Book(xml_format=False)` | 创建工作簿，xml_format=True 时为 xlsx 格式 |
| `load(filename)` | 加载 Excel 文件 |
| `save(filename)` | 保存 Excel 文件 |
| `release()` | 释放资源（推荐使用 with 语句自动管理） |
| `add_sheet(name, init_sheet=None)` | 添加工作表 |
| `insert_sheet(index, name, init_sheet=None)` | 插入工作表 |
| `get_sheet(index)` | 获取工作表 |
| `del_sheet(index)` | 删除工作表 |
| `move_sheet(src, dst)` | 移动工作表 |
| `add_format(init_format=None)` | 添加单元格格式 |
| `add_font(init_font=None)` | 添加字体 |
| `add_custom_num_format(fmt)` | 添加自定义数字格式 |
| `date_pack(year, month, day, ...)` | 日期打包为 Excel 日期值 |
| `date_unpack(value)` | Excel 日期值解包 |
| `color_pack(r, g, b)` | RGB 颜色打包 |
| `color_unpack(color)` | 颜色值解包为 RGB |

### Sheet 类

**数据读写：**

| 方法 | 说明 |
|------|------|
| `cell_type(row, col)` | 获取单元格类型 |
| `read_str(row, col)` | 读取字符串 |
| `write_str(row, col, value, fmt=None)` | 写入字符串 |
| `read_num(row, col)` | 读取数字 |
| `write_num(row, col, value, fmt=None)` | 写入数字 |
| `read_bool(row, col)` | 读取布尔值 |
| `write_bool(row, col, value, fmt=None)` | 写入布尔值 |
| `read_formula(row, col)` | 读取公式 |
| `write_formula(row, col, expr, fmt=None)` | 写入公式 |
| `read_blank(row, col)` | 读取空白单元格 |
| `write_blank(row, col, fmt=None)` | 写入空白单元格 |
| `read_error(row, col)` | 读取错误类型 |
| `write_error(row, col, error, fmt=None)` | 写入错误 |
| `read_comment(row, col)` | 读取批注 |
| `write_comment(row, col, value, ...)` | 写入批注 |
| `remove_comment(row, col)` | 删除批注 |

**行列操作：**

| 方法 | 说明 |
|------|------|
| `col_width(col)` | 获取列宽 |
| `row_height(row)` | 获取行高 |
| `set_col(first, last, width, fmt=None, hidden=False)` | 设置列属性 |
| `set_row(row, height, fmt=None, hidden=False)` | 设置行属性 |
| `row_hidden(row)` | 检查行是否隐藏 |
| `set_row_hidden(row, hidden)` | 设置行隐藏 |
| `col_hidden(col)` | 检查列是否隐藏 |
| `set_col_hidden(col, hidden)` | 设置列隐藏 |
| `insert_row(first, last)` | 插入行 |
| `insert_col(first, last)` | 插入列 |
| `remove_row(first, last)` | 删除行 |
| `remove_col(first, last)` | 删除列 |
| `clear(row_first, row_last, col_first, col_last)` | 清除区域 |
| `copy_cell(row_src, col_src, row_dst, col_dst)` | 复制单元格 |

**合并单元格：**

| 方法 | 说明 |
|------|------|
| `set_merge(row_first, row_last, col_first, col_last)` | 合并单元格 |
| `get_merge(row, col)` | 获取合并区域 |
| `merge_size()` | 合并单元格数量 |
| `merge_by_index(index)` | 按索引获取合并区域 |
| `del_merge(row, col)` | 删除合并 |
| `del_merge_by_index(index)` | 按索引删除合并 |

**属性：**

| 属性 | 说明 |
|------|------|
| `name` | 工作表名称（可读写） |
| `first_row` | 首行索引（只读） |
| `last_row` | 末行索引（只读） |
| `first_col` | 首列索引（只读） |
| `last_col` | 末列索引（只读） |
| `hidden` | 隐藏状态（可读写） |
| `display_gridlines` | 显示网格线（可读写） |
| `print_gridlines` | 打印网格线（可读写） |
| `zoom` | 缩放比例（可读写） |
| `landscape` | 横向打印（可读写） |
| `paper` | 纸张大小（可读写） |
| `header` | 页眉（可读写） |
| `footer` | 页脚（可读写） |

### Format 类

| 属性/方法 | 说明 |
|-----------|------|
| `font` | 字体对象（可读写） |
| `num_format` | 数字格式（可读写） |
| `align_h` | 水平对齐（可读写） |
| `align_v` | 垂直对齐（可读写） |
| `wrap` | 自动换行（可读写） |
| `rotation` | 文字旋转角度（可读写） |
| `indent` | 缩进（可读写） |
| `shrink_to_fit` | 缩小字体填充（可读写） |
| `set_border(style)` | 设置所有边框样式 |
| `set_border_color(color)` | 设置所有边框颜色 |
| `border_left/right/top/bottom` | 各边边框样式（可读写） |
| `border_left/right/top/bottom_color` | 各边边框颜色（可读写） |
| `fill_pattern` | 填充模式（可读写） |
| `pattern_foreground_color` | 图案前景色（可读写） |
| `pattern_background_color` | 图案背景色（可读写） |
| `locked` | 锁定单元格（可读写） |
| `hidden` | 隐藏公式（可读写） |

### Font 类

| 属性 | 说明 |
|------|------|
| `size` | 字号（可读写） |
| `bold` | 粗体（可读写） |
| `italic` | 斜体（可读写） |
| `strike_out` | 删除线（可读写） |
| `color` | 字体颜色（可读写） |
| `name` | 字体名称（可读写） |
| `script` | 上下标（可读写）：0=正常, 1=上标, 2=下标 |
| `underline` | 下划线类型（可读写） |

### 便捷函数

| 函数 | 说明 |
|------|------|
| `read_excel(filename, sheet_index=0, header=True, ...)` | 读取 Excel 为字典列表 |
| `write_excel(filename, data, sheet_name='Sheet1', ...)` | 字典列表写入 Excel |
| `read_excel_rows(filename, ...)` | 读取 Excel 为二维列表 |
| `write_excel_rows(filename, data, ...)` | 二维列表写入 Excel |
| `read_excel_matrix(filename, rows=None, cols=None, ...)` | 批量读取二维矩阵 |
| `write_excel_matrix(filename, data, ...)` | 批量写入二维矩阵 |
| `read_excel_df(filename, sheet_name=0, header=1, ...)` | 读取为 pandas DataFrame |
| `write_excel_df(filename, df, sheet_name='Sheet1', ...)` | DataFrame 写入 Excel |

### Sheet 批量方法

| 方法 | 说明 |
|------|------|
| `sheet.write_matrix(data, start_row=1, start_col=0)` | 批量写入二维矩阵 |
| `sheet.read_matrix(rows, cols, start_row=1, start_col=0)` | 批量读取矩阵 |
| `sheet.read_range(row_first, row_last, col_first, col_last)` | 按范围批量读取 |

### 工具函数

| 函数 | 说明 |
|------|------|
| `rowcol_to_addr(row, col, absolute=False)` | 行列索引转 Excel 地址 |
| `addr_to_rowcol(addr)` | Excel 地址转行列索引 |
| `rgb_to_color(red, green, blue)` | RGB 转 LibXL 颜色值 |
| `color_to_rgb(color)` | LibXL 颜色值转 RGB |

### 表格展示器

| 函数/方法 | 说明 |
|-----------|------|
| `show_table(data, title=None, has_header=True, ...)` | 在控制台打印二维表格数据（支持 list/Sheet/Book/DataFrame） |
| `sheet.show(title=None, has_header=True, ...)` | Sheet 对象方法，在控制台显示当前工作表 |
| `book.show(title=None, has_header=True, ...)` | Book 对象方法，在控制台显示所有工作表 |
| `sheet_to_2d_list(sheet, has_header=True)` | 将 Sheet 转换为二维列表 |
| `book_to_sheets_data(book, sheet_names=None)` | 将 Book 转换为多个二维列表 |
| `dataframe_to_2d_list(df, show_index=False)` | 将 DataFrame 转换为二维列表 |

## 枚举常量

**单元格类型 (CellType)：**
- `CELLTYPE_EMPTY` - 空
- `CELLTYPE_NUMBER` - 数字
- `CELLTYPE_STRING` - 字符串
- `CELLTYPE_BOOLEAN` - 布尔
- `CELLTYPE_BLANK` - 空白
- `CELLTYPE_ERROR` - 错误

**水平对齐 (AlignH)：**
- `ALIGNH_GENERAL` - 常规
- `ALIGNH_LEFT` - 左对齐
- `ALIGNH_CENTER` - 居中
- `ALIGNH_RIGHT` - 右对齐
- `ALIGNH_FILL` - 填充
- `ALIGNH_JUSTIFY` - 两端对齐
- `ALIGNH_MERGE` - 合并
- `ALIGNH_DISTRIBUTED` - 分散对齐

**垂直对齐 (AlignV)：**
- `ALIGNV_TOP` - 顶端
- `ALIGNV_CENTER` - 居中
- `ALIGNV_BOTTOM` - 底端
- `ALIGNV_JUSTIFY` - 两端对齐
- `ALIGNV_DISTRIBUTED` - 分散对齐

**边框样式 (BorderStyle)：**
- `BORDERSTYLE_NONE` - 无边框
- `BORDERSTYLE_THIN` - 细
- `BORDERSTYLE_MEDIUM` - 中
- `BORDERSTYLE_DASHED` - 虚线
- `BORDERSTYLE_DOTTED` - 点线
- `BORDERSTYLE_THICK` - 粗
- `BORDERSTYLE_DOUBLE` - 双线
- `BORDERSTYLE_HAIR` - hair

**填充模式 (FillPattern)：**
- `FILLPATTERN_NONE` - 无
- `FILLPATTERN_SOLID` - 实心
- `FILLPATTERN_GRAY50` - 50% 灰
- `FILLPATTERN_GRAY75` - 75% 灰
- `FILLPATTERN_GRAY25` - 25% 灰

**常用颜色 (Color)：**
- `COLOR_BLACK` - 黑色
- `COLOR_WHITE` - 白色
- `COLOR_RED` - 红色
- `COLOR_GREEN` - 绿色
- `COLOR_BLUE` - 蓝色
- `COLOR_YELLOW` - 黄色
- `COLOR_AUTO` - 自动

## 使用示例

### 1. 基本读写

```python
from vools.xl import Book

with Book() as book:
    sheet = book.add_sheet('Data')

    # 写入表头
    headers = ['Name', 'Age', 'City']
    for i, h in enumerate(headers):
        sheet.write_str(0, i, h)

    # 写入数据
    data = [
        ('Alice', 25, 'New York'),
        ('Bob', 30, 'Los Angeles'),
    ]
    for row_idx, row_data in enumerate(data, start=1):
        sheet.write_str(row_idx, 0, row_data[0])
        sheet.write_num(row_idx, 1, row_data[1])
        sheet.write_str(row_idx, 2, row_data[2])

    book.save('data.xls')
```

### 2. 带格式的表格

```python
from vools.xl import Book
from vools.xl._core.api import ALIGNH_CENTER, FILLPATTERN_SOLID, COLOR_YELLOW

with Book() as book:
    sheet = book.add_sheet('Report')

    # 表头格式
    header_fmt = book.add_format()
    header_fmt.bold = True
    header_fmt.align_h = ALIGNH_CENTER
    header_fmt.fill_pattern = FILLPATTERN_SOLID
    header_fmt.pattern_foreground_color = COLOR_YELLOW

    # 写入表头
    headers = ['ID', 'Product', 'Price', 'Qty']
    for i, h in enumerate(headers):
        sheet.write_str(0, i, h, header_fmt)

    # 设置列宽
    sheet.set_col(0, 0, 8)
    sheet.set_col(1, 1, 30)
    sheet.set_col(2, 3, 12)

    book.save('report.xls')
```

### 3. 公式与合并单元格

```python
from vools.xl import Book

with Book() as book:
    sheet = book.add_sheet('Calc')

    # 标题（合并单元格）
    sheet.set_merge(0, 0, 0, 3)
    title_fmt = book.add_format()
    title_fmt.bold = True
    title_fmt.align_h = 2  # 居中
    title_fmt.size = 14
    sheet.write_str(0, 0, 'Sales Report', title_fmt)

    # 数据
    sheet.write_str(2, 0, 'Product A')
    sheet.write_num(2, 1, 100)
    sheet.write_num(2, 2, 10)

    sheet.write_str(3, 0, 'Product B')
    sheet.write_num(3, 1, 200)
    sheet.write_num(3, 2, 5)

    # 合计公式
    sheet.write_str(5, 0, 'Total:')
    sheet.write_formula(5, 1, 'SUMPRODUCT(B3:B4,C3:C4)')

    book.save('calc.xls')
```

### 4. 使用便捷函数

```python
from vools.xl import read_excel, write_excel

# 简单写入
data = [
    {'name': '张三', 'age': 28, 'department': '研发部'},
    {'name': '李四', 'age': 32, 'department': '市场部'},
    {'name': '王五', 'age': 25, 'department': '财务部'},
]
write_excel('employees.xls', data, sheet_name='员工信息')

# 简单读取
employees = read_excel('employees.xls')
for emp in employees:
    print(f"{emp['name']} - {emp['department']}")
```

## 注意事项

1. **Trial 版本限制**：未注册的 LibXL 会在 A1 单元格自动写入 trial 提示，且首个工作表写入 A1 会返回失败。注册后可正常使用。

2. **资源管理**：Book 对象使用完需要调用 `release()` 释放资源。推荐使用 `with` 语句自动管理。

3. **行号列号**：所有行号列号均从 0 开始计数，与 Excel 界面中的 A1（第1行第1列）对应关系为：row=0, col=0。

4. **xlsx 格式**：创建 Book 时传入 `xml_format=True` 可创建 xlsx 格式文件。

5. **注册码**：使用 `book.set_key(name, key)` 设置注册码去除 trial 版本限制。

## SqlCel 函数映射 (vools.xl + vools.data Table)

[SqlCel](D:\SqlCel) 提供了丰富的 Excel 自定义函数库 (D_FIND/D_VLOOKUP/D_SUMIF 等)。本节给出 SqlCel UDF 与 vools.xl + vools.data Table 方法的映射，便于从 Excel 公式迁移到 Python。

| SqlCel UDF | 描述 | Python 等价 |
|------------|------|-------------|
| `D_FIND(range, value)` | 查找值所在行 | `Table.where(f"{col} == '{value}'")` |
| `D_VLOOKUP(value, range, col, exact)` | 垂直查找 | `Table.where(f"{key} == '{value}'").select(col)` |
| `D_SUMIF(range, criteria, sum_range)` | 条件求和 | `Table.where(criteria).sum(sum_col)` |
| `D_COUNTIF(range, criteria)` | 条件计数 | `Table.where(criteria).rows()` |
| `D_AVERAGEIF(range, criteria, avg_range)` | 条件平均值 | `Table.where(criteria).avg(avg_col)` |
| `D_SELECT(range, conditions)` | 条件查询 | `Table.where(conditions)` |
| `D_GROUPBY(range, group_col, agg_col, func)` | 分组聚合 | `Table.group_by(group_col).agg({agg_col: func})` |
| `D_SORT(range, sort_col, desc)` | 排序 | `Table.order_by(sort_col, desc=desc)` |
| `D_DISTINCT(range)` | 去重 | `Table.distinct()` |
| `D_LIMIT(range, n)` | 限制行数 | `Table.limit(n)` |
| `D_FILTER(range, conditions)` | 多条件过滤 | `Table.where(conditions).filter(predicate)` |

**示例对比**:

```excel
=SUMIF(D2:D100, ">30", E2:E100)
```
```python
table.where('age > 30').sum('salary')
```

```excel
=VLOOKUP("Alice", A2:D100, 4, FALSE)
```
```python
table.where('name == "Alice"').select('salary').column('salary')[0]
```

```excel
=COUNTIF(B2:B100, "NYC")
```
```python
table.where('city == "NYC"').rows()
```

## 引擎适配 (Engine Adapter)

vools.xl 支持 pandas 风格的 `engine` 参数，可在不同 Excel 引擎间切换：

```python
from vools.xl import read_excel_df, write_excel_df, get_engine, list_engines

# 查看已注册引擎
print(list_engines())  # ['odf', 'openpyxl', 'vools', 'xlrd']

# 默认使用 vools 引擎 (基于 LibXL)
df = read_excel_df('input.xlsx')

# 切换到 openpyxl
df = read_excel_df('input.xlsx', engine='openpyxl')

# 自定义引擎
from vools.xl import register_engine, BaseEngine

class MyEngine(BaseEngine):
    name = 'myengine'
    def read_df(self, filename, **kwargs): ...
    def write_df(self, filename, df, **kwargs): ...

register_engine('myengine', MyEngine())
```

## 常见问题

**Q: 为什么写入 A1 单元格返回 False？**
A: 未注册的 LibXL trial 版本会在 A1 写入 trial 提示，导致用户无法写入 A1。注册后即可正常使用。

**Q: 支持哪些 Excel 格式？**
A: 支持 .xls (BIFF8) 和 .xlsx (Office Open XML) 格式。

**Q: 需要安装 Excel 吗？**
A: 不需要。LibXL 是独立的库，不依赖 Excel 或任何 COM 组件。

**Q: 支持大文件吗？**
A: 支持。LibXL 性能优秀，可高效处理大型 Excel 文件。
