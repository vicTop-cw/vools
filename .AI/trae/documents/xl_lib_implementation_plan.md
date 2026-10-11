# vools.xl - LibXL Excel 读写库实现计划

## 摘要

基于 LibXL v3.8.0 (同时提供 32位/64位 DLL)，创建 `vools.xl` 子包，提供 Excel 文件的读写功能。采用 **64位 DLL + 纯 Python ctypes 高级封装** 方案，提供对象级 API（Book、Sheet、Format、Font）和便捷函数（read_excel、write_excel），符合 vools 现有框架的设计模式。

## 当前状态分析

### LibXL 库分析

**文件位置**: `E:\vb\FileRecv\[Excel读写]LibXL.for.Windows.v3.8.0.Incl.Keygen\libxl-3.8.0.0\`

**DLL 文件**:
- `bin/libxl.dll` - 32 位 DLL
- `bin64/libxl.dll` - 64 位 DLL

**API 特点**:
- C 风格扁平函数 API（非面向对象）
- 同时提供 ANSI (A 后缀) 和 Unicode (W 后缀) 版本
- 使用 Handle 模式：`BookHandle`, `SheetHandle`, `FormatHandle`, `FontHandle` 等
- 约 200+ 个函数，覆盖工作簿、工作表、单元格、格式、字体、图片、打印等

**核心 API 分类**:
| 类别 | 示例函数 |
|------|---------|
| 工作簿 | `xlCreateBookCA`, `xlBookLoadA`, `xlBookSaveA`, `xlBookReleaseA` |
| 工作表 | `xlBookAddSheetA`, `xlBookGetSheetA`, `xlBookSheetCountA` |
| 单元格读写 | `xlSheetReadStrA`, `xlSheetWriteStrA`, `xlSheetReadNumA`, `xlSheetWriteNumA` |
| 单元格格式 | `xlSheetCellFormatA`, `xlSheetSetCellFormatA` |
| 行列操作 | `xlSheetSetColA`, `xlSheetSetRowA`, `xlSheetInsertRowA` |
| 格式 | `xlBookAddFormatA`, `xlFormatSetAlignHA`, `xlFormatSetBorderA` |
| 字体 | `xlBookAddFontA`, `xlFontSetBoldA`, `xlFontSetSizeA` |
| 合并单元格 | `xlSheetSetMergeA`, `xlSheetGetMergeA` |
| 图片 | `xlBookAddPictureA`, `xlSheetSetPictureA` |

### 现有框架模式参考

| 模块 | 特点 | 适用场景 |
|------|------|---------|
| `vools.sys.dll` | `@dll` 装饰器，直接 ctypes 调用 64位 DLL | 简单 DLL 调用 |
| `vools.dll32` | 32位进程桥接 + 装饰器 + 包装类 + 签名注册表 | 32位 DLL 调用 |
| `vools.bridge.c` | C 代码编译 + DLL 加载 + `CDLLWrapper` | 动态编译 C 代码 |

## 技术选型

### 推荐方案：64位 DLL + 纯 Python ctypes 高级封装

**选择理由**:
1. **性能最优**: 直接 ctypes 调用 64位 DLL，无进程桥接开销
2. **API 丰富**: LibXL 有 200+ 函数，进程桥接模式（dll32）性能太差
3. **封装完整**: 可实现完整的对象级封装（Book、Sheet、Format、Font）
4. **符合框架**: 参考 `vools.sys.dll` 和 `vools.dll32` 的设计模式
5. **64位优先**: 当前主环境是 64位 Python，优先支持 64位

**不选其他方案的原因**:
- ❌ **dll32 模式**: 每次调用都要启动 32位进程，200+ 函数调用太慢
- ❌ **bridge.c 模式**: 主要用于动态编译 C 代码，不适合纯 DLL 封装
- ❌ **FreeBASIC 封装**: 额外编译层，增加复杂度，无必要

## 模块结构设计

```
vools/xl/
├── __init__.py              # 主入口，导出核心 API
├── README.md                # 使用文档
├── _core/                   # 核心层
│   ├── __init__.py
│   ├── loader.py            # DLL 加载器（加载 libxl.dll）
│   └── api.py               # 低层 LibXL C API 封装（ctypes 函数声明）
├── _objects/                # 对象封装层
│   ├── __init__.py
│   ├── book.py              # Book 类（工作簿）
│   ├── sheet.py             # Sheet 类（工作表）
│   ├── format.py            # Format 类（单元格格式）
│   └── font.py              # Font 类（字体）
├── _utils/                  # 工具层
│   ├── __init__.py
│   └── helpers.py           # 辅助函数（类型转换、错误处理等）
└── _dlls/                   # 内置 DLL
    ├── __init__.py
    ├── libxl.dll            # 64 位 LibXL DLL
    └── libxl32.dll          # 32 位 LibXL DLL（预留）
```

### 各模块职责

| 模块 | 职责 | 对外暴露 |
|------|------|---------|
| `_core/loader.py` | 加载 LibXL DLL，管理 DLL 实例 | `get_libxl_dll()`, `LibXLLoader` |
| `_core/api.py` | 低层 C API 的 ctypes 函数声明 | 所有 `xl*` 函数的 ctypes 包装 |
| `_objects/book.py` | Book 类，封装工作簿操作 | `Book` 类 |
| `_objects/sheet.py` | Sheet 类，封装工作表操作 | `Sheet` 类 |
| `_objects/format.py` | Format 类，封装单元格格式 | `Format` 类 |
| `_objects/font.py` | Font 类，封装字体 | `Font` 类 |
| `_utils/helpers.py` | 辅助函数（错误处理、类型转换） | `check_error()`, `rowcol_to_addr()` 等 |
| `_dlls/` | 存放 LibXL DLL 文件 | `get_dll_path()`, `list_dlls()` |

## 详细实现计划

### 阶段 1: 基础架构搭建

**目标**: 建立模块结构，实现 DLL 加载和低层 API 封装

**修改文件**:
1. `vools/xl/__init__.py` - 新建，定义包入口和导出列表
2. `vools/xl/_dlls/__init__.py` - 新建，DLL 路径管理
3. `vools/xl/_core/__init__.py` - 新建，核心层导出
4. `vools/xl/_core/loader.py` - 新建，DLL 加载器
5. `vools/xl/_core/api.py` - 新建，低层 C API 声明

**实现要点**:
- 从 `bin64/libxl.dll` 复制 64位 DLL 到 `vools/xl/_dlls/libxl.dll`
- `loader.py` 实现 DLL 单例加载，使用 `ctypes.CDLL`
- `api.py` 声明所有核心函数的 `argtypes` 和 `restype`
- Handle 类型使用 `c_void_p`
- 字符串使用 `c_char_p`（ANSI 版本）
- 优先实现核心函数（约 30-40 个最常用的）

### 阶段 2: 对象级封装

**目标**: 实现 Book、Sheet、Format、Font 四个核心类

**修改文件**:
1. `vools/xl/_objects/__init__.py` - 新建，对象层导出
2. `vools/xl/_objects/book.py` - 新建，Book 类
3. `vools/xl/_objects/sheet.py` - 新建，Sheet 类
4. `vools/xl/_objects/format.py` - 新建，Format 类
5. `vools/xl/_objects/font.py` - 新建，Font 类
6. `vools/xl/_utils/__init__.py` - 新建，工具层导出
7. `vools/xl/_utils/helpers.py` - 新建，辅助函数

**Book 类核心方法**:
```python
class Book:
    def __init__(self, xml_format=False): ...        # 创建工作簿
    def load(self, filename): -> bool                 # 加载 Excel 文件
    def save(self, filename): -> bool                 # 保存 Excel 文件
    def add_sheet(self, name, init_sheet=None): -> Sheet  # 添加工作表
    def get_sheet(self, index): -> Sheet              # 获取工作表
    @property
    def sheet_count(self): -> int                     # 工作表数量
    def add_format(self, init_format=None): -> Format # 添加格式
    def add_font(self, init_font=None): -> Font       # 添加字体
    def release(self): ...                            # 释放资源
    def __enter__(self): ...                          # 上下文管理器支持
    def __exit__(self, *args): ...
```

**Sheet 类核心方法**:
```python
class Sheet:
    def __init__(self, handle, book): ...
    @property
    def name(self): -> str                           # 工作表名
    @name.setter
    def name(self, value): ...
    def read_str(self, row, col): -> str              # 读取字符串
    def write_str(self, row, col, value, fmt=None): ...  # 写入字符串
    def read_num(self, row, col): -> float            # 读取数字
    def write_num(self, row, col, value, fmt=None): ...  # 写入数字
    def read_bool(self, row, col): -> bool            # 读取布尔值
    def write_bool(self, row, col, value, fmt=None): ... # 写入布尔值
    def read_formula(self, row, col): -> str          # 读取公式
    def write_formula(self, row, col, expr, fmt=None): ... # 写入公式
    def cell_type(self, row, col): -> int             # 单元格类型
    def set_cell_format(self, row, col, fmt): ...     # 设置单元格格式
    @property
    def first_row(self): -> int                       # 首行索引
    @property
    def last_row(self): -> int                        # 末行索引
    @property
    def first_col(self): -> int                       # 首列索引
    @property
    def last_col(self): -> int                        # 末列索引
    def set_col(self, first, last, width, fmt=None, hidden=False): ...  # 设置列
    def set_row(self, row, height, fmt=None, hidden=False): ...         # 设置行
    def set_merge(self, row_first, row_last, col_first, col_last): ...  # 合并单元格
    def insert_row(self, first, last): ...            # 插入行
    def insert_col(self, first, last): ...            # 插入列
    def remove_row(self, first, last): ...            # 删除行
    def remove_col(self, first, last): ...            # 删除列
```

**Format 类核心方法**:
```python
class Format:
    def __init__(self, handle, book): ...
    @property
    def font(self): -> Font                           # 获取字体
    @font.setter
    def font(self, value): ...                        # 设置字体
    @property
    def num_format(self): -> str                      # 数字格式
    @num_format.setter
    def num_format(self, value): ...
    @property
    def align_h(self): -> int                         # 水平对齐
    @align_h.setter
    def align_h(self, value): ...
    @property
    def align_v(self): -> int                         # 垂直对齐
    @align_v.setter
    def align_v(self, value): ...
    @property
    def wrap(self): -> bool                           # 自动换行
    @wrap.setter
    def wrap(self, value): ...
    def set_border(self, style): ...                  # 设置边框
    def set_border_color(self, color): ...            # 设置边框颜色
    @property
    def fill_pattern(self): -> int                    # 填充模式
    @fill_pattern.setter
    def fill_pattern(self, value): ...
    def set_pattern_foreground_color(self, color): ... # 前景色
    def set_pattern_background_color(self, color): ... # 背景色
```

**Font 类核心方法**:
```python
class Font:
    def __init__(self, handle, book): ...
    @property
    def size(self): -> int                            # 字号
    @size.setter
    def size(self, value): ...
    @property
    def bold(self): -> bool                           # 粗体
    @bold.setter
    def bold(self, value): ...
    @property
    def italic(self): -> bool                         # 斜体
    @italic.setter
    def italic(self, value): ...
    @property
    def color(self): -> int                           # 颜色
    @color.setter
    def color(self, value): ...
    @property
    def name(self): -> str                            # 字体名
    @name.setter
    def name(self, value): ...
    @property
    def underline(self): -> int                       # 下划线
    @underline.setter
    def underline(self, value): ...
```

### 阶段 3: 便捷函数和高级功能

**目标**: 实现 read_excel、write_excel 等便捷函数，补充实用功能

**修改文件**:
1. `vools/xl/__init__.py` - 更新，导出便捷函数
2. `vools/xl/_utils/helpers.py` - 更新，添加更多辅助函数

**便捷函数**:
```python
def read_excel(filename, sheet_index=0, sheet_name=None): -> list[list]
    """读取 Excel 文件，返回二维列表"""

def write_excel(filename, data, sheet_name="Sheet1"): -> bool
    """将二维列表写入 Excel 文件"""

def read_excel_dict(filename, sheet_index=0, sheet_name=None): -> list[dict]
    """读取 Excel 文件，首行为表头，返回字典列表"""

def write_excel_dict(filename, data, sheet_name="Sheet1"): -> bool
    """将字典列表写入 Excel 文件，首行为表头"""
```

### 阶段 4: 文档和测试

**目标**: 完善文档和测试，确保质量

**修改文件**:
1. `vools/xl/README.md` - 新建，使用文档
2. `tests/xl/test_xl.py` - 新建，单元测试

**测试覆盖**:
- 创建和保存 Excel 文件
- 读取现有 Excel 文件
- 写入不同类型数据（字符串、数字、布尔值、公式）
- 格式设置（字体、对齐、边框、填充）
- 行列操作
- 合并单元格
- 便捷函数测试

## API 导出示例

最终用户使用方式：

```python
from vools.xl import Book, Sheet, Format, Font
from vools.xl import read_excel, write_excel, read_excel_dict, write_excel_dict

# 方式 1: 直接使用对象
with Book() as book:
    sheet = book.add_sheet("Sheet1")
    sheet.write_str(0, 0, "Hello")
    sheet.write_num(0, 1, 123)
    book.save("output.xls")

# 方式 2: 便捷函数
data = read_excel("input.xls")
write_excel("output.xls", data)

# 方式 3: 字典方式（首行表头）
records = read_excel_dict("data.xls")
write_excel_dict("output.xls", records)
```

## 关键设计决策

### 1. 使用 ANSI (A) 版本还是 Unicode (W) 版本？
**决策**: 使用 ANSI (A) 版本
**理由**: 
- Python str 与 c_char_p 交互更简单
- 中文环境下 UTF-8/GBK 编码可手动控制
- 与现有 dll32 模块保持一致的风格

### 2. 行号列号从 0 开始还是 1 开始？
**决策**: 从 0 开始（与 LibXL C API 保持一致）
**理由**: 
- 与 LibXL 原生 API 一致，减少转换开销
- 提供 `rowcol_to_addr()` 辅助函数转换 Excel 地址格式

### 3. Handle 生命周期管理？
**决策**: Book 类管理所有 Handle，release 时统一释放
**理由**:
- Sheet/Format/Font 的 Handle 由 Book 创建，随 Book 释放
- 避免 Handle 悬空引用
- 使用上下文管理器（with 语句）确保资源释放

### 4. 错误处理方式？
**决策**: 函数返回 bool 表示成功，通过 `book.error_message` 获取错误信息
**理由**:
- 与 LibXL 原生 API 风格一致
- 避免异常开销
- 提供检查错误的辅助函数

## 实施步骤

1. **阶段 1**: 基础架构搭建（DLL 复制 + 加载器 + 低层 API）
2. **阶段 2**: 对象级封装（Book + Sheet + Format + Font）
3. **阶段 3**: 便捷函数和高级功能
4. **阶段 4**: 文档和测试

## 验证方式

1. 运行单元测试：`pytest tests/xl/test_xl.py -v`
2. 手动验证：创建 Excel 文件 → 用 Excel 打开确认正常
3. 性能测试：对比读写大文件的性能
4. 兼容性测试：测试 .xls 和 .xlsx 两种格式

## 假设与约束

### 假设
- LibXL 64位 DLL 可以在当前 64位 Python 环境正常加载
- LibXL 提供的试用版 DLL 可以正常使用（可能有水印或行数限制）
- 后续可以通过 `xlBookSetKeyA` 设置注册码去除限制

### 约束
- 仅支持 Windows 平台（LibXL 是 Windows DLL）
- 优先支持 64位 Python（32位可后续通过 dll32 模式支持）
- 第一阶段实现核心功能（约 30-40 个常用 API），后续逐步完善
