# 装饰器命名冲突分析报告

## 一、重复命名的装饰器列表

### 1. 柯里化装饰器
| 名称 | 来源文件 | 类型 | 功能 |
|------|----------|------|------|
| `curry` | `curry_core.py` | 装饰器 | 主要柯里化装饰器，功能完整 |
| `curried` | `curried.py` | 函数/方法 | 提供柯里化函数（如 `curried_map`），非装饰器 |
| `curry_class` | `curry_decorator.py` | 装饰器 | 类柯里化装饰器 |
| `overcurry` | `overcurry.py` | 装饰器 | 过载柯里化装饰器 |

### 2. 重载装饰器
| 名称 | 来源文件 | 类型 | 功能 |
|------|----------|------|------|
| `overload` | `overload.py` | 装饰器 | 主要重载装饰器，功能清晰 |
| `overloads` | `overloads.py` | 装饰器 | 重载装饰器，与 `overload` 功能重叠 |

## 二、建议保留的主要版本

| 装饰器 | 建议 | 原因 |
|--------|------|------|
| `curry` | ✅ 保留 | 主要柯里化装饰器，功能完整，广泛使用 |
| `overload` | ✅ 保留 | 主要重载装饰器，命名清晰，功能明确 |
| `curry_class` | ✅ 保留 | 特殊用途（类柯里化），与 `curry` 功能互补 |
| `overcurry` | ✅ 保留 | 特殊用途（过载柯里化），与 `curry` 功能互补 |

## 三、建议弃用的次要版本

| 装饰器 | 建议 | 原因 | 弃用方式 |
|--------|------|------|----------|
| `overloads` | ⚠️ 弃用 | 与 `overload` 功能重叠，命名不规范 | 标记为弃用，指向 `overload` |
| `curried` | ⚠️ 弃用 | 非装饰器，命名混淆 | 标记为弃用，指向 `curry` 或 `curried_map` |

## 四、命名规范建议

### 4.1 装饰器命名规范
1. **统一使用单数形式**：如 `overload`，避免 `overloads`
2. **动词形式命名**：如 `curry`, `retry`, `cache`，避免形容词形式
3. **避免功能重叠**：相同功能的装饰器只保留一个主要版本

### 4.2 参数命名规范
1. **snake_case 命名**：所有参数使用 snake_case
2. **关键字参数**：可选参数使用关键字参数
3. **类型注解**：所有参数添加类型注解

### 4.3 导出规范
1. **`__all__` 清晰**：只导出主要版本
2. **弃用警告**：弃用的装饰器添加弃用警告
3. **向后兼容**：保留弃用装饰器的导入路径

## 五、实施建议

### 5.1 立即实施
1. 标记 `overloads` 为弃用，添加弃用警告
2. 标记 `curried` 为弃用，添加弃用警告
3. 更新 `__init__.py` 导出列表

### 5.2 后续版本
1. 完善文档，说明弃用装饰器的替代方案
2. 提供迁移指南
3. 在下一个主要版本中移除弃用装饰器

## 六、相关文件

- [curry_core.py](file:///e:/IDEProjects/AI/vools/vools/decorators/curry_core.py) - 主要柯里化装饰器
- [overload.py](file:///e:/IDEProjects/AI/vools/vools/decorators/overload.py) - 主要重载装饰器
- [__init__.py](file:///e:/IDEProjects/AI/vools/vools/decorators/__init__.py) - 导出列表