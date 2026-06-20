# vools.core

基础核心模块，提供基础类、异常和配置管理。

## 主要功能

- **基础类**: `VoolsBase` - 所有 vools 类的基类
- **异常类**: 提供统一的异常类型（`VoolsError`, `SafeEvalError`, `ConfigurationError` 等）
- **配置管理**: `ConfigManager`, `DatabaseConfig`, `CacheConfig`, `AppConfig`

## 核心类/函数

| 名称 | 类型 | 说明 |
|------|------|------|
| `VoolsBase` | 类 | 基础类，提供通用方法 |
| `VoolsError` | 异常 | 通用异常基类 |
| `SafeEvalError` | 异常 | 安全评估异常 |
| `ConfigurationError` | 异常 | 配置异常 |
| `ConfigManager` | 类 | 配置管理器 |
| `dataclass` | 函数 | dataclass 兼容层（自动降级 attrs） |
| `field` | 函数 | field 兼容层 |
| `asdict` | 函数 | dataclass 转字典 |

## 使用示例

```python
from vools.core import VoolsBase, VoolsError, dataclass

@dataclass
class MyConfig:
    host: str = "localhost"
    port: int = 8080

class MyClass(VoolsBase):
    def process(self):
        # ...
        if error:
            raise VoolsError("处理失败")
```

## 子包

| 路径 | 说明 |
|------|------|
| `vools.core.dataclass_compat` | dataclass 兼容层（Python ≥3.7 用标准库，<3.7 用 attrs） |

## 注意事项

- 通常不需要直接导入此模块，功能已在顶层 `vools` 包中导出