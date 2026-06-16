# vools 功能扩展与优化计划

## 文档概述

本计划旨在系统性分析 vools 与 funcy、toolz、returns 三个相关库之间的功能差异，识别缺失功能，并制定分阶段实施计划。

---

## 1. 功能对比分析

### 1.1 库定位与设计哲学

| 维度 | vools | funcy | toolz | returns |
|------|-------|-------|-------|---------|
| **定位** | 全功能函数式工具集 + 响应式编程 | 实用函数式工具库 | 纯函数式编程核心工具 | 函数式错误处理与类型安全 |
| **设计哲学** | 多范式融合，兼顾实用与创新 | 简洁实用，专注集合操作 | 纯函数式，组合优先 | 类型安全，Result模式 |
| **核心优势** | 响应式编程 + 装饰器生态 | 集合操作丰富 | 函数组合强大 | 类型安全错误处理 |
| **适用场景** | 全栈开发，需要响应式能力 | 数据处理管道 | 纯函数式编程 | 需要类型安全的项目 |

### 1.2 核心功能模块对比

#### 1.2.1 装饰器模块

| 功能 | vools | funcy | toolz | returns |
|------|-------|-------|-------|---------|
| `curry` | ✅ | ✅ (`autocurry`) | ✅ | ❌ |
| `memorize/cache` | ✅ | ✅ | ❌ | ❌ |
| `once` | ✅ | ✅ | ❌ | ❌ |
| `retry` | ✅ | ✅ | ❌ | ❌ |
| `throttle` | ✅ | ❌ | ❌ | ❌ |
| `debounce` | ✅ | ❌ | ❌ | ❌ |
| `lazy` | ✅ | ✅ | ❌ | ❌ |
| `singleton` | ✅ | ❌ | ❌ | ❌ |
| `deprecated` | ✅ | ❌ | ❌ | ❌ |

#### 1.2.2 集合操作模块

| 功能 | vools | funcy | toolz | returns |
|------|-------|-------|-------|---------|
| `walk` | ❌ | ✅ | ❌ | ❌ |
| `mapcat` | ❌ | ✅ | ❌ | ❌ |
| `pluck` | ❌ | ✅ | ✅ | ❌ |
| `pluck_attr` | ❌ | ✅ | ❌ | ❌ |
| `compact` | ❌ | ✅ | ❌ | ❌ |
| `flatten` | ❌ | ✅ | ✅ | ❌ |
| `distinct` | ✅ (reactive) | ✅ | ❌ | ❌ |
| `group_by` | ✅ (reactive) | ✅ | ✅ | ❌ |
| `count_by` | ❌ | ✅ | ✅ | ❌ |

#### 1.2.3 序列操作模块

| 功能 | vools | funcy | toolz | returns |
|------|-------|-------|-------|---------|
| `take` | ✅ (reactive) | ✅ | ✅ | ❌ |
| `drop` | ✅ (reactive) | ✅ | ✅ | ❌ |
| `split_at` | ❌ | ✅ | ❌ | ❌ |
| `butlast` | ❌ | ✅ | ❌ | ❌ |
| `cons` | ❌ | ✅ | ✅ | ❌ |
| `conj` | ❌ | ✅ | ❌ | ❌ |
| `interleave` | ❌ | ✅ | ✅ | ❌ |
| `interpose` | ❌ | ❌ | ✅ | ❌ |

#### 1.2.4 字典操作模块

| 功能 | vools | funcy | toolz | returns |
|------|-------|-------|-------|---------|
| `merge` | ❌ | ✅ | ✅ | ❌ |
| `merge_with` | ❌ | ✅ | ❌ | ❌ |
| `update_in` | ❌ | ✅ | ✅ | ❌ |
| `get_in` | ❌ | ✅ | ✅ | ❌ |
| `set_in` | ❌ | ✅ | ❌ | ❌ |
| `dissoc` | ❌ | ❌ | ✅ | ❌ |
| `assoc` | ❌ | ❌ | ✅ | ❌ |
| `assoc_in` | ❌ | ❌ | ✅ | ❌ |

#### 1.2.5 函数组合模块

| 功能 | vools | funcy | toolz | returns |
|------|-------|-------|-------|---------|
| `compose` | ✅ | ✅ | ✅ | ❌ |
| `pipe` | ✅ | ✅ | ✅ | ❌ |
| `compose_left` | ❌ | ❌ | ✅ | ❌ |
| `flip` | ❌ | ❌ | ✅ | ❌ |
| `identity` | ✅ | ✅ | ✅ | ❌ |
| `constantly` | ❌ | ✅ | ❌ | ❌ |

#### 1.2.6 错误处理模块

| 功能 | vools | funcy | toolz | returns |
|------|-------|-------|-------|---------|
| `Result` 类型 | ❌ | ❌ | ❌ | ✅ |
| `Maybe` 类型 | ❌ | ❌ | ❌ | ✅ |
| `silent` | ❌ | ✅ | ❌ | ❌ |
| `suppress` | ❌ | ✅ | ❌ | ❌ |
| `ignore` | ❌ | ✅ | ❌ | ❌ |
| `excepts` | ❌ | ❌ | ✅ | ❌ |

#### 1.2.7 响应式编程模块

| 功能 | vools | funcy | toolz | returns |
|------|-------|-------|-------|---------|
| `Observable` | ✅ | ❌ | ❌ | ❌ |
| `Subject` | ✅ | ❌ | ❌ | ❌ |
| 操作符链 | ✅ | ❌ | ❌ | ❌ |
| 背压处理 | ✅ | ❌ | ❌ | ❌ |
| 调度器 | ✅ | ❌ | ❌ | ❌ |

---

## 2. 缺失功能清单

### 2.1 高优先级缺失功能（P0）

| 功能 | 来源库 | 描述 | 优先级 |
|------|--------|------|--------|
| `Result` 类型 | returns | 函数式错误处理的核心类型 | **P0** |
| `pluck` / `pluck_attr` | funcy/toolz | 从集合中提取属性 | **P0** |
| `merge` / `merge_with` | funcy/toolz | 字典合并操作 | **P0** |
| `get_in` / `set_in` / `update_in` | funcy/toolz | 嵌套字典操作 | **P0** |
| `walk` / `mapcat` | funcy | 集合遍历与展平操作 | **P0** |

### 2.2 中优先级缺失功能（P1）

| 功能 | 来源库 | 描述 | 优先级 |
|------|--------|------|--------|
| `compact` | funcy | 移除 falsy 值 | P1 |
| `flatten` | funcy/toolz | 展平嵌套序列 | P1 |
| `split_at` | funcy | 在指定位置分割序列 | P1 |
| `butlast` | funcy | 返回除最后一个元素外的所有元素 | P1 |
| `compose_left` | toolz | 从左到右函数组合 | P1 |
| `flip` | toolz | 翻转函数参数顺序 | P1 |
| `excepts` | toolz | 异常处理装饰器 | P1 |

### 2.3 低优先级缺失功能（P2）

| 功能 | 来源库 | 描述 | 优先级 |
|------|--------|------|--------|
| `Maybe` 类型 | returns | 可选值处理 | P2 |
| `silent` | funcy | 静默异常 | P2 |
| `suppress` | funcy | 抑制异常 | P2 |
| `ignore` | funcy | 忽略返回值 | P2 |
| `constantly` | funcy | 返回常量的函数 | P2 |
| `interleave` | funcy/toolz | 交错序列 | P2 |
| `interpose` | toolz | 在元素间插入值 | P2 |
| `dissoc` / `assoc` / `assoc_in` | toolz | 字典操作 | P2 |

---

## 3. 实现方案详述

### 3.1 `Result` 类型实现

**技术路径**：
- 创建 `vools/functional/result.py`
- 实现 `Result`、`Success`、`Failure` 三个类
- 支持 `bind`、`map`、`unwrap`、`unwrap_or` 等方法

**设计要点**：
```python
class Result(Generic[T, E]):
    """函数式错误处理的核心类型"""
    
    @classmethod
    def success(cls, value: T) -> 'Result[T, E]':
        return Success(value)
    
    @classmethod
    def failure(cls, error: E) -> 'Result[T, E]':
        return Failure(error)
    
    def bind(self, fn: Callable[[T], 'Result[R, E]']) -> 'Result[R, E]':
        """链式调用"""
    
    def map(self, fn: Callable[[T], R]) -> 'Result[R, E]':
        """映射成功值"""
    
    def unwrap(self) -> T:
        """获取成功值，失败时抛出异常"""
    
    def unwrap_or(self, default: T) -> T:
        """获取成功值或默认值"""
```

### 3.2 集合操作函数实现

**技术路径**：
- 在 `vools/curried/collection.py` 中添加缺失函数
- 支持 curry 化调用

**函数清单**：
```python
def pluck(key, seq):
    """从序列中提取指定键的值"""

def pluck_attr(attr, seq):
    """从序列中提取指定属性"""

def walk(fn, seq):
    """对序列中每个元素应用函数"""

def mapcat(fn, seq):
    """map 后展平结果"""

def compact(seq):
    """移除 falsy 值"""

def flatten(seq, depth=None):
    """展平嵌套序列"""
```

### 3.3 字典操作函数实现

**技术路径**：
- 在 `vools/curried/collection.py` 中添加字典操作函数

**函数清单**：
```python
def merge(*dicts):
    """合并多个字典"""

def merge_with(fn, *dicts):
    """使用函数合并字典值"""

def get_in(keys, d, default=None):
    """获取嵌套字典的值"""

def set_in(keys, value, d):
    """设置嵌套字典的值"""

def update_in(keys, fn, d):
    """更新嵌套字典的值"""
```

### 3.4 序列操作函数实现

**技术路径**：
- 在 `vools/curried/iteration.py` 中添加序列操作函数

**函数清单**：
```python
def split_at(n, seq):
    """在位置 n 分割序列"""

def butlast(seq):
    """返回除最后一个元素外的所有元素"""

def cons(x, seq):
    """在序列开头添加元素"""

def conj(seq, x):
    """在序列末尾添加元素"""
```

### 3.5 函数组合增强

**技术路径**：
- 在 `vools/curried/composition.py` 中添加函数

**函数清单**：
```python
def compose_left(*funcs):
    """从左到右函数组合"""

def flip(fn):
    """翻转函数参数顺序"""

def constantly(value):
    """返回常量的函数"""
```

### 3.6 错误处理工具

**技术路径**：
- 在 `vools/decorators/control.py` 中添加装饰器

**函数清单**：
```python
def excepts(exc_type, handler):
    """异常处理装饰器"""

def silent(fn=None, default=None):
    """静默异常，返回默认值"""

def suppress(exc_type):
    """抑制指定类型的异常"""

def ignore(fn):
    """忽略函数返回值"""
```

---

## 4. 实施计划时间表

### 4.1 第一阶段：核心功能实现（2周）

| 任务 | 预估工时 | 责任人 | 依赖 |
|------|----------|--------|------|
| `Result` 类型 | 2天 | 开发A | 无 |
| `pluck` / `pluck_attr` | 1天 | 开发B | 无 |
| `merge` / `merge_with` | 1天 | 开发B | 无 |
| `get_in` / `set_in` / `update_in` | 2天 | 开发A | 无 |
| 单元测试 | 2天 | 测试 | 上述功能 |
| **合计** | **8天** | | |

### 4.2 第二阶段：集合与序列操作（2周）

| 任务 | 预估工时 | 责任人 | 依赖 |
|------|----------|--------|------|
| `walk` / `mapcat` | 1天 | 开发B | 无 |
| `compact` / `flatten` | 1天 | 开发B | 无 |
| `split_at` / `butlast` / `cons` | 1天 | 开发A | 无 |
| `compose_left` / `flip` | 1天 | 开发A | 无 |
| 单元测试 | 2天 | 测试 | 上述功能 |
| **合计** | **6天** | | |

### 4.3 第三阶段：错误处理与增强（1周）

| 任务 | 预估工时 | 责任人 | 依赖 |
|------|----------|--------|------|
| `excepts` / `silent` / `suppress` | 2天 | 开发A | 无 |
| `Maybe` 类型（可选） | 2天 | 开发B | Result |
| 文档更新 | 1天 | 文档 | 所有功能 |
| **合计** | **5天** | | |

### 4.4 项目甘特图

```
阶段一          阶段二          阶段三
┌──────────┐    ┌──────────┐    ┌───────┐
│ Result   │    │ walk     │    │ excepts│
│ pluck    │    │ compact  │    │ silent │
│ merge    │    │ split_at │    │ Maybe  │
│ get_in   │    │ compose  │    │ 文档   │
│ 测试     │    │ 测试     │    │        │
└──────────┘    └──────────┘    └───────┘
第1-2周     第3-4周     第5周
```

---

## 5. 资源需求评估

### 5.1 人力需求

| 角色 | 人数 | 职责 |
|------|------|------|
| 后端开发 | 2人 | 功能实现 |
| 测试工程师 | 1人 | 测试用例编写与执行 |
| 技术文档 | 1人 | 文档编写与维护 |
| **合计** | **4人** | |

### 5.2 工具需求

| 工具 | 用途 | 版本要求 |
|------|------|----------|
| Python | 开发 | >= 3.10 |
| pytest | 测试 | >= 7.0 |
| mypy | 类型检查 | >= 1.0 |
| sphinx | 文档 | >= 5.0 |

### 5.3 潜在风险评估

| 风险 | 描述 | 概率 | 影响 | 缓解措施 |
|------|------|------|------|----------|
| API 设计冲突 | 新增函数与现有 API 冲突 | 中 | 中 | 代码审查时检查命名 |
| 性能影响 | 新增功能影响现有性能 | 低 | 中 | 性能测试 |
| 类型安全 | Result 类型的类型推断问题 | 中 | 高 | 使用 mypy 严格检查 |
| 文档滞后 | 功能实现后文档未及时更新 | 高 | 低 | 文档与代码同步 |

---

## 6. 质量验收标准

### 6.1 功能验收标准

| 指标 | 标准 |
|------|------|
| **代码覆盖率** | >= 90% |
| **类型检查** | mypy 无错误 |
| **文档覆盖率** | 所有新增功能有文档 |
| **API 一致性** | 与现有 API 风格保持一致 |

### 6.2 性能验收标准

| 指标 | 标准 |
|------|------|
| 集合操作性能 | 不低于 funcy 的 80% |
| Result 类型开销 | 相对于直接异常处理 < 10% |
| 内存使用 | 无明显内存泄漏 |

### 6.3 兼容性验收标准

| 指标 | 标准 |
|------|------|
| Python 版本 | 支持 3.10+ |
| 无破坏性变更 | 不影响现有 API |
| 向后兼容 | 现有代码无需修改 |

---

## 7. 输出物清单

| 输出物 | 状态 | 交付时间 |
|--------|------|----------|
| `vools/functional/result.py` | 待开发 | 第1周 |
| `vools/curried/collection.py`（增强） | 待开发 | 第2周 |
| `vools/curried/iteration.py`（增强） | 待开发 | 第3周 |
| `vools/curried/composition.py`（增强） | 待开发 | 第3周 |
| `vools/decorators/control.py`（增强） | 待开发 | 第5周 |
| 单元测试套件 | 待开发 | 同步 |
| API 文档 | 待编写 | 第5周 |
| 功能对比矩阵更新 | 待更新 | 第5周 |

---

## 附录：funcy/toolz/returns 功能速查

### funcy 核心功能
- **集合操作**: walk, mapcat, pluck, pluck_attr, compact, flatten
- **序列操作**: take, drop, split_at, butlast, cons, conj
- **字典操作**: merge, merge_with, update_in, get_in, set_in
- **装饰器**: autocurry, cache, cached_property, once, retry, lazy
- **工具函数**: silent, suppress, ignore, constantly

### toolz 核心功能
- **函数组合**: compose, compose_left, pipe, flip
- **集合操作**: pluck, flatten, interleave, interpose
- **字典操作**: merge, get_in, assoc, assoc_in, dissoc, update_in
- **工具函数**: excepts, identity, countby, groupby

### returns 核心功能
- **Result 类型**: Success, Failure, bind, map, unwrap
- **Maybe 类型**: Some, Nothing
- **装饰器**: safe, returns_result, returns_future
- **类型安全**: 完整的类型注解支持

---

**文档版本**: v1.0  
**创建日期**: 2026-06-13  
**最后更新**: 2026-06-13  
**作者**: vools 开发团队