# vools 用户指南

vools 是一个 Python 函数式编程工具集，提供装饰器、函数式编程工具、响应式编程、数据处理等模块。

**当前版本**: v0.1.18

---

## 快速导航

| 指南 | 内容 | 适合读者 |
|------|------|----------|
| [核心功能](core.md) | 占位符、重载、stuff、persist、Box、g、iif | 新手入门 |
| [函数式编程](functional.md) | curried 模块、管道操作、Seq 序列 | 进阶用户 |
| [vic 工具类](vic-classes.md) | vDate、VText、VList、Seq | 数据处理 |
| [响应式编程](reactive.md) | Observable、Subject、操作符、clipboard、keyboard_mouse | 事件驱动 |
| [编码加密与 Result](extras.md) | 编码模块、加密模块、Result 类型 | 工具类 |

## 项目信息

- **GitHub 仓库**: <https://github.com/vicTop-cw/vools>
- **联系邮箱**: <victortop921129@gmail.com>
- **PyPI 主页**: <https://pypi.org/project/vools/>
- **许可证**: Apache 2.0

## 安装

### 环境要求

- Python 3.9+
- 核心依赖：`wrapt`, `attrs`, `pandas`, `numpy`

### 安装方式

```bash
# 从 PyPI 安装
pip install vools

# 或从源码安装
git clone https://github.com/vicTop-cw/vools.git
cd vools
pip install -e .

# 安装开发依赖
pip install vools[dev]
```

## 快速开始

```python
from vools import _, _1, _2, overload, overcurry, stuff, persist, overloads

# 占位符
result = (_ + 1)(5)        # 6
result = (_1 + _2)(10, 20)  # 30

# 基于参数数量的重载
@overload
def process():
    return "无参数"

@process.register
def process_one(x):
    return f"一个参数: {x}"

print(process())        # 无参数
print(process(10))      # 一个参数: 10

# stuff（柯里化 + 延迟求值）
@stuff
def add(a, b, c):
    return a + b + c

result = add(1)(2)(3)()  # 6

# persist（结果持久化缓存）
@persist
def expensive(x):
    return x ** 2
print(expensive(5))  # 25
```

## 模块概览

| 模块 | 文件位置 | 主要内容 |
|------|----------|----------|
| 装饰器 | `vools/decorators/` | `overload`, `overcurry`, `stuff`, `persist`, `curry_core`, `selector`, `cache` |
| 函数式 | `vools/functional/` | `_, _1, _2`, `Box`, `g`, `iif`, `Result`, `Success`, `Failure`, `safe`, `pipe`, `compose` |
| 响应式 | `vools/reactive/` | `Observable`, `Subject`, `BehaviorSubject`, `ReplaySubject`, `ops.*`, 键鼠/剪贴板/文件监控 |
| 数据 | `vools/data/` | `Seq`, `VList`, `VText`, `NONE`, `collect` |
| 日期 | `vools/datetime/` | `vDate`, `DateProcessor`, `EnhancedDateFormatter`, `get_week`, `get_month`, `days_gap` |
| 序列化 | `vools/serialize/` | `Serializer`, `dumps`, `loads`, `dumps_hex`, `loads_hex`, callable handler |
| 编码 | `vools/encoding/` | `Encoder`, `Decoder`, `CodecRegistry`, `b64encode`, `urlencode`, `json_dumps`, `gzip_compress` |
| 加密 | `vools/crypto/` | `Encryptor`, `md5`, `sha1`, `sha256`, `sha512`, `hmac_md5`, `hmac_sha256`, `generate_key`, `generate_token` |
| OOP 工具 | `vools/oop/` | `Mixer`, `Mixer_`, `mixer`, `extend`, `clone`, `selector`, `Selector`, `calltype`, `attr_Enum`, `g` |
| 任务 | `vools/task/` | 任务调度与规则引擎 |
| 安全 | `vools/security/` | `safe_eval`, `safe_exec` |
| 通用工具 | `vools/utils/` | `Stuff`, `Hoder` |
| 响应式监控 | `vools/reactive/monitoring/` | `KeySubject`, `MouseSubject`, `ClipSubject`, `FileSubject`, `FolderSubject` |

## 许可证

Apache 2.0 © Victor
