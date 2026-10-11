# vools API 文档与类型注解补充计划

> 日期：2026-06-22
> 范围：`vools/` 下所有 `.py` 文件
> 目标：为缺失 docstring 和类型注解的公开 API 补充完善

---

## 一、现状分析

基于自动化扫描结果（`docstring_analysis_result.txt`）：

| 类别 | 数量 |
|------|------|
| 总 API 数 | 1452 |
| 完整文档（docstring + 类型注解） | 467 (32.2%) |
| 只有 docstring | ~500 |
| 只有类型注解 | ~100 |
| **两者都缺失（需补充）** | **~400** |

### 缺失严重的核心模块（优先处理）

| 文件 | 缺失数 | 优先级 |
|------|--------|--------|
| `reactive/core/observable.py` | 117 | 🔴 高 |
| `functional/pipe_ops.py` | 56 | 🔴 高 |
| `data/seq.py` | 47 | 🔴 高 |
| `data/vlist.py` | 21 | 🔴 高 |
| `datetime/vdate_class.py` | 16 | 🔴 高 |
| `reactive/monitoring/keyboard.py` | 18 | 🟡 中 |
| `reactive/monitoring/mouse.py` | 16 | 🟡 中 |
| `reactive/monitoring/clipboard.py` | 17 | 🟡 中 |
| `reactive/monitoring/file_watcher.py` | 14 | 🟡 中 |
| `reactive/monitoring/folder_watcher.py` | 14 | 🟡 中 |
| `reactive/core/subject.py` | 5 | 🟡 中 |
| `functional/box.py` | 5 | 🟡 中 |
| `decorators/curry_delay.py` | 10 | 🟡 中 |
| `decorators/selector.py` | 8 | 🟡 中 |
| `functional/placeholder_impl.py` | 10 | 🟢 低（分析工具误报，部分是私有方法）|
| `data/vtext.py` | 5 | 🟢 低 |
| `oop/mixer.py` | 2 | 🟢 低 |
| `utils/stuff.py` | 3 | 🟢 低 |

---

## 二、补充策略

### 文档规范

每个公开 API 需补充：
1. **docstring**：简短描述功能（Google style 或 NumPy style）
2. **类型注解**：参数类型 `->` 返回值类型

示例格式：
```python
def func_name(arg1: Type1, arg2: Type2 = default) -> ReturnType:
    """简要描述功能。

    Args:
        arg1: 参数1的描述
        arg2: 参数2的描述（可选）

    Returns:
        返回值的描述

    Raises:
        ValueError: 何时抛出
    """
```

### 不需要补充的情况
- `__pycache__` 目录下文件
- 以下划线 `_` 开头的私有方法（除非确实需要公开）
- `__all__` 之外的非公开符号

---

## 三、具体实施步骤

> 按优先级分批执行

### 第一批：最高优先级核心模块（~150 个 API）

#### 1. `vools/data/seq.py` — 补充 47 个 API
**范围**：SeqBase 和 Seq 类的所有公开方法

需补充 docstring + 类型注解的方法：
- `SeqBase`：`_SeqIterator.__next__`、`SeqBase.cursor`、`_fill_to`、`__lshift__`、`of`、`range`、`cycle`、`from_callable`
- `Seq`：`distinct`、`group_by`、`grouper`、`prepend`、`extend`、`add`、`add_reversed`、`sort_by`、`reverse`、`sorted`、`count_by`、`reduce_by`、`any`、`all`、`find`、`find_index`、`accum`、`run`、`__iadd__`、`__rshift__`、`__or__`、`__add__`、`__radd__`、`__len__`、`__bool__`、`__repr__`、`__str__`、`_evaluate`、`filterfalse`、`filter_not`、`filternot`、`filter_false`、`_starmap`、`_mapmap`、`where`、`wherenot`、`select`、`starmap`、`mapmap`、`collect`、`take_while`、`drop_while`、`take`、`tee`、`skip`、`enumerate`、`zip`、`zip_longest`、`flatten`、`as_list`、`flatmap`、`flatmap_ex1`、`flatmap_ex`、`ensure_seq`、`register`

#### 2. `vools/functional/pipe_ops.py` — 补充 56 个 API
**范围**：P 管道操作符类的所有方法

需补充类型注解（该文件方法已有 docstring，仅需补类型）：
- `P.map`、`P.flat_map`、`P.flatmap`、`P.filter`、`P.filterfalse`、`P.distinct`、`P.tap`、`P.tee`、`P.take`、`P.skip`、`P.take_while`、`P.drop_while`、`P.zip`、`P.zip_longest`、`P.enumerate`、`P.flatten`、`P.flat_map_*`、`P.mapcat`、`P.reduce`、`P.scan`、`P.first`、`P.last`、`P.nth`、`P.find`、`P.find_index`、`P.group_by`、`P.sort_by`、`P.reverse`、`P.sorted`、`P.count_by`、`P.count`、`P.sum`、`P.product`、`P.mean`、`P.any`、`P.all`、`P.none`、`P.some`、`P.tail`、`P.head`、`P.init`、`P.inspect`、`P.delay`、`P.timeout`

#### 3. `vools/datetime/vdate_class.py` — 补充 16 个 API
**范围**：VDate 类的方法

需补充 docstring + 类型注解：所有公开方法（`add_days`、`add_months`、`getDateRange`、`getRecentDays`、`getRecentWeeks`、`getRecentMonths` 等）

#### 4. `vools/data/vlist.py` — 补充 21 个 API
**范围**：ListLikeMeta 和 VList 类

需补充 docstring + 类型注解：`ListLikeMeta.do`（已有 docstring，缺类型）、VList 类的 `__getitem__`、`__len__`、`__iter__`、`__and__`、`__or__`、`__rand__`、`__ror__`、`where`、`wherenot`、`select`、`map`、`flat_map`、`flatmap`、`distinct`、`group_by`、`sort_by`、`reverse`、`sorted`、`count_by`、`reduce_by`、`collect`、`add`、`push`、`pop`、`shift`、`unshift`

#### 5. `vools/functional/box.py` — 补充 5 个 API
需补充 docstring + 类型注解：
- `box` 函数（第 58 行）
- `__box_wrapped_call__`
- `CallableDescriptor.__init__`、`enable`、`disable`
- `Box.copy`

### 第二批：响应式核心模块（~140 个 API）

#### 6. `vools/reactive/core/observable.py` — 补充 117 个 API
**注意**：该文件大量方法是 RxPY 风格操作符代理方法。策略是：
- 如果方法只是调用 `ops.*`，直接在方法 docstring 中引用对应操作符说明
- 补充 `on_next`/`on_error`/`on_completed` 回调签名类型注解

#### 7. `vools/reactive/core/subject.py` — 补充 5 个 API
需补充：`BehaviorSubject`/`ReplaySubject`/`AsyncSubject` 的公开方法类型注解

#### 8. `vools/reactive/monitoring/*.py` — 补充 ~90 个 API
5 个监控文件（keyboard/mouse/clipboard/file_watcher/folder_watcher）：
- 补充事件数据类（`KeyData`/`MouseData`/`ClipData`/`FileData`/`FolderData`）的 docstring + 类型注解
- 补充 `Subject` 子类公开方法类型注解
- 添加"仅 Windows"警告注释

### 第三批：装饰器与 OOP 模块（~30 个 API）

#### 9. `vools/decorators/curry_delay.py` — 补充 10 个 API
该文件是 `@stuff` 的延迟依赖注入实现。补充 `Depend` 类的 docstring + 类型注解。

#### 10. `vools/decorators/selector.py` — 补充 8 个 API
补充 `Selector` 类的 docstring + 类型注解。

#### 11. `vools/decorators/curry_core.py` — 补充 4 个 API
补充 `curry` 函数的类型注解。

#### 12. `vools/oop/mixer.py` — 补充 2 个 API
补充 `Mixer`、`Mixer_` 的 docstring + 类型注解。

#### 13. `vools/functional/iif.py` — 补充 1 个 API
补充 `ConditionBuilder` 某个方法的类型注解。

### 第四批：其余模块（~20 个 API）

#### 14. `vools/data/vtext.py` — 5 个 API
补充 VText 类的公开方法 docstring + 类型注解。

#### 15. `vools/utils/stuff.py` — 3 个 API
补充 `Stuff` 装饰器相关的公开方法类型注解。

#### 16. `vools/recorder/gui.py` — 1 个 API
补充 GUI 相关类的公开方法。

---

## 四、具体文件与行号

### seq.py 需补充的具体位置

| 方法 | 行号 | 当前状态 |
|------|------|----------|
| `SeqBase.__init__` | ~170 | 无 docstring |
| `SeqBase._SeqIterator.__next__` | ~163 | 无 docstring |
| `SeqBase.cursor` | ~196 | 无 docstring |
| `SeqBase._fill_to` | ~199 | 无 docstring |
| `SeqBase.of` | ~236 | 无 docstring |
| `SeqBase.range` | ~242 | 无 docstring |
| `SeqBase.cycle` | ~248 | 无 docstring |
| `SeqBase.from_callable` | ~268 | 无 docstring |
| `Seq.unique` | ~342 | 无 docstring |
| `Seq.distinct` | ~353 | 无 docstring |
| `Seq.group_by` | ~367 | 无 docstring |
| `Seq.filterfalse` | ~511 | 无 docstring |
| `Seq._starmap` | ~520 | 无 docstring |
| `Seq._mapmap` | ~528 | 无 docstring |
| `Seq.where` | ~546 | 无 docstring |
| `Seq.wherenot` | ~550 | 无 docstring |
| `Seq.select` | ~554 | 无 docstring |
| `Seq.starmap` | ~558 | 无 docstring |
| `Seq.mapmap` | ~562 | 无 docstring |
| `Seq.collect` | ~566 | 无 docstring |
| `Seq.reduce` | ~569 | 无 docstring |
| `Seq.take_while` | ~574 | 无 docstring |
| `Seq.drop_while` | ~577 | 无 docstring |
| `Seq.take` | ~579 | 无 docstring |
| `Seq.tee` | ~598 | 无 docstring |
| `Seq.skip` | ~612 | 无 docstring |
| `Seq.enumerate` | ~619 | 无 docstring |
| `Seq.zip` | ~625 | 无 docstring |
| `Seq.zip_longest` | ~631 | 无 docstring |
| `Seq.flatten` | ~636 | 无 docstring |
| `Seq.flatmap` | ~649 | 无 docstring |
| `Seq.flatmap_ex` | ~704 | 有 docstring，无类型注解 |
| `Seq.size` | ~725 | 无 docstring |
| `Seq.join` | ~728 | 无 docstring |
| `Seq.ensure_seq` | ~731 | 有 docstring |
| `Seq.register` | ~740 | 有 docstring |

---

## 五、风险与注意事项

1. **seq.py 中的 `__rsub__`、`__rand__` 等魔术方法**：这些方法返回 `self`（不进行实际运算），不是标准的 Python 语义，补充文档时需如实说明行为。
2. **reactive/observable.py**：大量 RxPY 代理方法，不重复 RxPY 文档，只需注明"代理到 `ops.xxx`"即可。
3. **vools/datetime/vdate_class.py**：继承自 `datetime.datetime`，部分方法来自父类，仅补充 vtools 自定义方法。
4. **box.py 中的 `CallableDescriptor`**：这是内部描述符类，补充 docstring 时需标注为"内部使用"。

---

## 六、验收标准

1. 所有 `__all__` 中列出的公开 API 均有 docstring
2. 所有公开函数/方法有类型注解（`->` 返回值 + 参数注解）
3. 运行 `mypy vools/ --ignore-missing-imports` 无新增类型错误
4. 运行 `flake8 vools/ --max-line-length=120` 无新增 lint 错误
5. 覆盖率目标：从当前 32.2% 提升至 **70%+**
