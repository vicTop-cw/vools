# xl 模块性能优化 + 二维数据结构规划

## 一、问题分析

### 1.1 当前性能瓶颈

**批量写入 (10000行 x 10列)**:
- vools.xl: **0.42s** (LibXL C库)
- openpyxl: 0.96s
- vools.xl 快 **2.3x** ✅

**批量读取 (10000行 x 10列)**:
- vools.xl: **2.46s** (Python循环调用DLL)
- openpyxl: 0.78s
- openpyxl 快 **3.2x** ❌

**瓶颈原因**:
1. **LibXL API 限制**: 无批量写入API，只能逐单元格调用 `xlSheetWriteStrA/NumA`
2. **Python循环开销**: 读取时每格调用一次DLL，跨语言调用开销大
3. **类型判断开销**: `_read_cell` 每格判断类型

### 1.2 现有数据结构

`vools/data/` 模块已有:
- `Seq` - 序列抽象
- `VList` - 链式列表 (继承Seq)
- `VText` - 文本处理

**无二维表格数据结构**

---

## 二、方案选型分析

### 2.1 性能优化方案

| 方案 | 写入提升 | 读取提升 | 复杂度 | 推荐 |
|------|----------|----------|--------|------|
| A. 批量写入API封装 | ~2x | - | 低 | ✅ |
| B. 批量读取(一次取多格) | - | ~3-5x | 中 | ✅ |
| C. NumPy ndarray支持 | ~1.5x | ~2-3x | 中 | 可选 |
| D. 多线程并行写入 | ~1.5x | ~1.5x | 高 | ❌ |

**推荐方案 A+B**: 封装批量读写API，利用LibXL内部优化

### 2.2 二维数据结构选型

| 方案 | 特点 | 适用场景 | 推荐指数 |
|------|------|----------|----------|
| A. Table (基于VList) | 轻量、链式操作 | 小型数据(<100万) | ⭐⭐⭐⭐ |
| B. DataFrame兼容 | pandas兼容 | 数据分析 | ⭐⭐⭐⭐⭐ |
| C. NumPy ndarray | 高性能数值计算 | 科学计算 | ⭐⭐⭐ |
| D. 自定义Matrix | 极简、纯Python | 无外部依赖 | ⭐⭐ |

**推荐方案 B**: 与 `read_excel_df/write_excel_df` 共用底层，pandas生态兼容

---

## 三、实施方案

### 3.1 Phase 1: 批量读写API (高优先级)

#### 3.1.1 Sheet 批量写入方法

**文件**: `vools/xl/_objects/sheet.py`

新增方法:
```python
def write_matrix(self, data: List[List[Any]], start_row: int = 1, start_col: int = 0,
                  fmt: Format = None) -> bool:
    """批量写入二维数据矩阵

    Args:
        data: 二维数据列表
        start_row: 起始行 (默认1避开trial)
        start_col: 起始列
        fmt: 默认格式
    Returns:
        True-成功
    """
    # 优化: 减少Python层开销
    # 1. 类型预判断 2. 批量encode 3. 减少DLL调用参数检查
```

**性能目标**: 写入提升 30-50%

#### 3.1.2 Sheet 批量读取方法

**文件**: `vools/xl/_objects/sheet.py`

新增方法:
```python
def read_matrix(self, rows: int, cols: int,
                start_row: int = 1, start_col: int = 0) -> List[List[Any]]:
    """批量读取矩阵数据

    Args:
        rows: 行数
        cols: 列数
        start_row: 起始行
        start_col: 起始列

    Returns:
        二维数据列表
    """

def read_range(self, row_first: int, row_last: int,
               col_first: int, col_last: int) -> List[List[Any]]:
    """按范围批量读取

    Args:
        row_first, row_last, col_first, col_last: 行列范围

    Returns:
        二维数据列表
    """
```

**性能目标**: 读取提升 2-3x

### 3.2 Phase 2: NumPy 集成 (可选)

**文件**: `vools/xl/_highlevel/numpy_io.py`

```python
def read_excel_array(filename, sheet=0) -> np.ndarray:
    """读取为NumPy数组"""

def write_excel_array(filename, arr: np.ndarray, sheet_name='Sheet1'):
    """NumPy数组写入Excel"""
```

### 3.3 Phase 3: Table 数据结构 (推荐)

**文件**: `vools/data/table.py` (新建)

```python
class Table:
    """二维表格数据结构

    设计目标:
    1. 与 pandas DataFrame 互转便捷
    2. 链式操作 (继承Seq设计理念)
    3. Excel直接读写
    4. 轻量无外部依赖

    使用场景:
    - 小型数据分析
    - Excel数据处理
    - 与xl模块深度集成
    """

    def __init__(self, data: List[List[Any]] = None,
                 columns: List[str] = None):
        self._data = data or []
        self._columns = columns or []

    # ========== 数据访问 ==========
    def rows(self) -> int: ...
    def cols(self) -> int: ...
    def at(self, row: int, col: int) -> Any: ...
    def row(self, i: int) -> List[Any]: ...
    def column(self, name: str) -> List[Any]: ...

    # ========== Excel IO ==========
    def read_excel(filename: str, sheet=0) -> 'Table': ...
    def write_excel(filename: str) -> bool: ...

    # ========== 链式操作 ==========
    def select(self, *cols: str) -> 'Table': ...
    def filter(self, predicate: Callable) -> 'Table': ...
    def map(self, func: Callable) -> 'Table': ...
    def sort(self, by: str, reverse=False) -> 'Table': ...
    def group_by(self, col: str) -> Dict[Any, 'Table']: ...

    # ========== 转换 ==========
    def to_dicts(self) -> List[Dict]: ...
    def to_dataframe(self) -> 'DataFrame': ...
    @classmethod
    def from_dataframe(cls, df: 'DataFrame') -> 'Table': ...
    def to_numpy(self) -> np.ndarray: ...
```

---

## 四、实现计划

### 步骤 1: Sheet 批量读写优化
- [ ] 新增 `Sheet.write_matrix()` 方法
- [ ] 新增 `Sheet.read_matrix()` 方法
- [ ] 新增 `Sheet.read_range()` 方法
- [ ] 性能测试验证

### 步骤 2: 高层便捷函数
- [ ] 新增 `write_excel_matrix()` 函数
- [ ] 新增 `read_excel_matrix()` 函数
- [ ] 更新 `__init__.py` 导出

### 步骤 3: NumPy 集成 (可选)
- [ ] 新增 `numpy_io.py`
- [ ] `read_excel_array()` / `write_excel_array()`

### 步骤 4: Table 数据结构
- [ ] 创建 `vools/data/table.py`
- [ ] 实现核心功能: 数据存储、行列访问
- [ ] 实现Excel IO
- [ ] 实现链式操作
- [ ] 实现与pandas互转

### 步骤 5: 测试与文档
- [ ] 性能基准测试
- [ ] 更新 README.md
- [ ] 单元测试

---

## 五、验证步骤

### 5.1 性能测试脚本
```python
# tests/xl/perf_batch.py
ROWS, COLS = 10000, 10

# 旧方法
t1 = timeit(lambda: old_write(...), number=1)

# 新方法
t2 = timeit(lambda: write_matrix(...), number=1)

print(f"写入提升: {t1/t2:.1f}x")
```

### 5.2 预期性能

| 操作 | 当前 | 优化后 | 提升 |
|------|------|--------|------|
| 批量写入 | 0.42s | ~0.25s | **1.7x** |
| 批量读取 | 2.46s | ~0.8s | **3x** |

---

## 六、决策要点

### 6.1 是否建立自己的二维数据结构？

**建议: 是**，理由:
1. pandas 依赖较重，不适合轻量场景
2. 可与 xl 模块深度集成
3. vools/data/ 已有 Seq/VList 设计理念
4. Table 可作为 Seq 的二维扩展

### 6.2 Table vs DataFrame?

**建议: Table 作为 DataFrame 的轻量替代**
- Table -> DataFrame: 一行代码
- DataFrame -> Table: 一行代码
- 用户按需选择

### 6.3 实现优先级?

1. **P0**: Sheet 批量读写 (性能收益最高)
2. **P1**: Table 数据结构 (架构完善)
3. **P2**: NumPy 集成 (可选，按需)
