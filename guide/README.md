# vools 用户指南

vools 是一个 Python 函数式编程工具集，提供装饰器、函数式编程工具、响应式编程、数据处理等模块。

**当前版本**: v0.1.15

---

## 快速导航

| 指南 | 内容 | 适合读者 |
|------|------|----------|
| [核心功能](core.md) | 占位符、重载、stuff、persist、Box、g、iif | 新手入门 |
| [函数式编程](functional.md) | curried 模块、管道操作、Seq 序列 | 进阶用户 |
| [vic 工具类](vic-classes.md) | vicDate、vicTools、vicText、vicList | 数据处理 |
| [响应式编程](reactive.md) | Observable、Subject、操作符、clipboard、keyboard_mouse | 事件驱动 |
| [编码加密与 Result](extras.md) | 编码模块、加密模块、Result 类型 | 工具类 |

## 项目信息

- **GitHub 仓库**: <https://github.com/vicTop-cw/vools>
- **联系邮箱**: <victortop921129@gmail.com>
- **PyPI 主页**: <https://pypi.org/project/vools/>
- **许可证**: Apache 2.0

## 安装

### 环境要求

- Python 3.6+
- 核心依赖：`wrapt`, `attrs`（Python 3.6 使用 attrs 替代 dataclass）, `pandas`, `numpy`

### 安装方式

```bash
# 从 PyPI 安装
pip install vools==0.1.8

# 或从源码安装
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install -e .

# 安装开发依赖
pip install vools[dev]
```

## 快速开始

```python
from vools import _, _1, _2, overload, overcurry, stuff, persist, memoize

# 使用占位符
result = (_ + 1)(5)                 # 6
result = (_1 + _2)(10, 20)          # 30

# 使用重载
@overload
def process():
    return "无参数"

@process.register
def process(x):
    return f"一个参数: {x}"

print(process())      # 无参数
print(process(10))    # 一个参数: 10

# 使用 stuff
@stuff
def add(a, b, c):
    return a + b + c

result = add(1, 2, 3)  # 6
result = add(1)(2)(3)  # 6（柯里化调用）

# 使用 persist
@persist(duration=5)
def expensive_calc(x):
    return x * x
```

## 测试验证

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定测试
python tests/test_placeholder.py
python tests/test_stuff.py
python tests/test_curry_overload.py
```

### 测试文件列表

| 测试文件 | 测试内容 |
|----------|----------|
| `tests/test_placeholder.py` | 占位符测试 |
| `tests/test_stuff.py` | stuff 函数测试 |
| `tests/test_decorators.py` | 装饰器测试 |
| `tests/test_overcurry_vic.py` | overcurry 和 vic 类测试 |
| `tests/test_curry_overload.py` | curry 和 overload 测试 |
| `tests/test_box.py` | box 装饰器和 Box 类测试 |
| `tests/test_g_function.py` | g 函数测试 |
| `tests/test_iif.py` | iif 函数测试 |
| `tests/test_vicdate.py` | vicDate 工具类测试 |
| `tests/test_multiline.py` | 多行表达式测试 |
| `tests/test_rself.py` | rself 装饰器测试 |
| `tests/test_pipe_ops.py` | 管道操作测试 |
| `tests/test_viclist_pipe.py` | vicList 管道测试 |
| `tests/test_curry_decorator.py` | curry_decorator 测试 |
| `tests/test_placeholder_impl.py` | placeholder_impl 测试 |
| `tests/test_box_vic.py` | box 装饰器与 vic 类集成测试 |
| `tests/test_reactive.py` | 响应式编程测试 |
| `tests/test_reactive_clipboard.py` | 剪贴板监控测试 |
| `tests/test_reactive_file_watcher.py` | 文件监控测试 |
| `tests/test_reactive_folder_watcher.py` | 文件夹监控测试 |
| `tests/test_reactive_keyboard_mouse.py` | 键鼠监控测试 |
| `tests/test_sig_cache.py` | 签名缓存测试 |

## 贡献指南

### 代码规范

- 遵循 PEP 8 编码规范
- 所有公共 API 必须有类型注解
- 添加新功能需包含对应的测试用例
- 保持向后兼容性

### 提交 PR

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 许可证

Apache 2.0 © Victor
