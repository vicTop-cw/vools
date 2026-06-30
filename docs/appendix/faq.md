# 常见问题 (FAQ)

> **模块路径**：-
> **依赖版本**：Python 3.6+
> **平台支持**：Windows/macOS/Linux
> **测试状态**：✅ 已测试
> **编号**：#A02
> **最后更新**：2026-06-30

---

## 目录

- [安装问题](#安装问题)
- [使用问题](#使用问题)
- [装饰器问题](#装饰器问题)
- [函数式编程问题](#函数式编程问题)
- [性能问题](#性能问题)

---

## 安装问题

### Q1: pip 安装失败怎么办？

**问题描述**

使用 `pip install vools` 安装失败。

**解决方案**

1. 确保 pip 是最新版本：
```bash
pip install --upgrade pip
```

2. 使用国内镜像源（如果网络较慢）：
```bash
pip install vools -i https://pypi.tuna.tsinghua.edu.cn/simple
```

3. 从源码安装：
```bash
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install -e .
```

### Q2: 提示缺少 DLL 文件？

**问题描述**

安装完成后提示 `DLL load failed` 或类似错误。

**解决方案**

1. 确保使用 64 位 Python：
```bash
python -c "import struct; print(struct.calcsize('P') * 8, 'bit')"
```

2. 重新安装 vools：
```bash
pip uninstall vools
pip install vools
```

3. 如果是 dll32 模块问题，参考 [platform.md](./platform.md) 确认系统要求。

### Q3: Python 3.6 兼容性问题？

**问题描述**

在 Python 3.6 上出现语法错误或导入错误。

**解决方案**

vools 从 v0.3.0 开始完全支持 Python 3.6+。如果遇到问题：

1. 升级到更高版本的 Python（推荐 3.8+）：
```bash
python --version
```

2. 或安装特定兼容版本：
```bash
pip install vools==0.3.0
```

---

## 使用问题

### Q4: 导入模块失败？

**问题描述**

`import vools` 报错或返回 `ImportError`。

**解决方案**

1. 确认安装成功：
```bash
pip show vools
```

2. 检查 Python 环境：
```bash
python -c "import sys; print(sys.executable)"
```

3. 尝试明确导入：
```python
from vools import curry, overload, Seq
```

### Q5: 版本如何查看？

**问题描述**

不确定当前安装的 vools 版本。

**解决方案**

```python
import vools
print(vools.__version__)
```

或命令行：
```bash
pip show vools
```

---

## 装饰器问题

### Q6: 占位符 `_` 与 Python 内置冲突？

**问题描述**

占位符 `_` 与 Python 的 `_`（上次结果）产生冲突。

**解决方案**

使用索引占位符：
```python
from vools import _1, _2, _3

# 多参数场景
f = _1 + _2
assert f(1, 2) == 3

# 或使用 g 函数
from vools import g
f = g("_1 + _2")
assert f(1, 2) == 3
```

### Q7: 重载函数不匹配？

**问题描述**

调用重载函数时没有匹配到正确的实现。

**解决方案**

检查参数类型和数量：
```python
from vools import overload

@overload
def process(x: int):
    return x + 1

@process.register
def process_str(x: str):
    return x + "1"

# 正确调用
process(1)     # int 版本
process("a")   # str 版本
```

### Q8: curry 装饰器如何使用？

**问题描述**

不清楚柯里化函数如何调用。

**解决方案**

```python
from vools import curry

@curry
def add(a, b, c):
    return a + b + c

# 逐步调用
add(1)(2)(3)  # 6

# 批量调用
add(1, 2, 3)  # 6

# 部分应用
add5 = add(5)
add5(2, 3)  # 10
```

---

## 函数式编程问题

### Q9: 管道操作报错？

**问题描述**

使用 `|` 管道操作时报错。

**解决方案**

```python
from vools import Pipe, Ops

# 使用 Pipe 包装函数
result = [1, 2, 3] | Pipe(lambda x: [i * 2 for i in x])
print(result)  # [2, 4, 6]

# 使用 Ops 工具类
result = [1, 2, 3] | Ops.map(lambda x: x * 2) | Ops.filter(lambda x: x > 2)
print(result)  # [4, 6]
```

### Q10: 惰性求值和立即求值如何选择？

**问题描述**

不确定何时使用惰性求值版本。

**解决方案**

| 场景 | 推荐版本 | 说明 |
|------|----------|------|
| 小数据集 (<1000) | 立即求值 (`map`) | 结果直接可用 |
| 大数据集 | 惰性求值 (`imap`) | 减少内存占用 |
| 流式处理 | 惰性求值 | 支持增量处理 |

```python
from vools.curried import map, filter, imap, ifilter

# 立即求值 - 返回 list
result = map(lambda x: x * 2, [1, 2, 3])

# 惰性求值 - 返回迭代器
result = imap(lambda x: x * 2, [1, 2, 3])
```

---

## 性能问题

### Q11: 如何加速函数调用？

**问题描述**

函数调用开销较大。

**解决方案**

1. 使用 `@memorize` 缓存重复调用：
```python
from vools import memorize

@memorize
def expensive_func(x):
    return x ** 2
```

2. 使用 `@curry` 减少调用层级：
```python
from vools import curry

@curry
def process(data, transform, filter_fn):
    return map(filter_fn, map(transform, data))
```

### Q12: 响应式操作性能如何优化？

**问题描述**

响应式数据流性能不佳。

**解决方案**

1. 使用合适的操作符：
```python
# 避免复杂操作链
Observable.from_iterable(data).pipe(
    ops.filter(lambda x: x > 0),  # 先过滤减少数据量
    ops.map(lambda x: x * 2)
)
```

2. 使用 `do` 操作符调试（生产环境移除）：
```python
Observable.from_iterable([1, 2, 3]).pipe(
    ops.do(lambda x: print(f"值: {x}")),  # 调试用
    ops.map(lambda x: x * 2)
)
```

---

## 获取更多帮助

- **GitHub Issues**：https://github.com/vicTop-cw/vools/issues
- **完整文档**：访问 [在线文档](https://victop-cw.github.io/vools/)
- **测试验证**：`python -m pytest tests/ -v`
