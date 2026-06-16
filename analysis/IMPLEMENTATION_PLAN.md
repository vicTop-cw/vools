# vools 项目实现计划

## 1. 项目分析

通过分析 `D:\work_for_ai\dataquest\source\pys` 目录下的文件，发现以下需要实现的组件：

### 1.1 缺失的日期相关组件
- **myDate.py**: 包含 vDate 函数和各种日期相关的 Spark UDF
- **myDates.py**: 包含日期范围函数（get_recently_months, get_recently_weeks, get_recently_days, get_dates）
- **daterange.py**: 包含 get_date_range 函数
- **vicDate**: 需要实现的日期类

### 1.2 缺失的 Spark UDF 函数
- 各种日期处理 UDF
- JSON 处理 UDF (extract_json_keys_udf)
- 数组处理 UDF (array_sum)

### 1.3 配置系统需求
- 处理 look_upon.py 中的硬编码文件名路径
- 处理数据库连接凭证的安全存储

### 1.4 PostgreSQL 和 Spark 交互组件
- look_upon.py 中的数据库连接需要使用配置文件
- 硬编码的数据库凭证需要移至配置文件

### 1.5 函数重载实现
- 需要确保所有重载机制都已正确实现

## 2. 实现计划

### 2.1 日期相关组件整合

**目标**: 将所有日期相关组件组织到 `datetime` 模块中

**实施步骤**:
1. **更新 `vools/datetime/__init__.py`**:
   - 导入所有日期相关模块
   - 导出所有公开接口

2. **创建 `vools/datetime/mydate.py`**:
   - 实现 vDate 函数
   - 实现日期处理相关的 Spark UDF

3. **创建 `vools/datetime/mydates.py`**:
   - 实现 get_recently_months 函数
   - 实现 get_recently_weeks 函数
   - 实现 get_recently_days 函数
   - 实现 get_dates 函数

4. **更新 `vools/datetime/range.py`**:
   - 整合 daterange.py 中的功能
   - 实现 vicDate 类

5. **更新 `vools/datetime/dates_format.py`**:
   - 确保日期格式化功能完整

### 2.2 Spark UDF 函数整合

**目标**: 将所有 Spark UDF 函数组织到 `spark/udf.py` 模块中

**实施步骤**:
1. **创建 `vools/spark/udf.py`**:
   - 分类组织 UDF 函数（日期 UDF、JSON UDF、数组 UDF 等）
   - 提供注册 UDF 的功能

### 2.3 配置系统实现

**目标**: 实现完整的配置系统，处理文件名和数据库凭证

**实施步骤**:
1. **更新 `vools/config.py`**:
   - 添加文件名配置项
   - 添加数据库连接配置项

2. **更新 `vools/spark/config.py`**:
   - 使用配置系统替代硬编码路径

3. **创建 `vools/config.template.py`**:
   - 提供配置模板

### 2.4 PostgreSQL 和 Spark 交互组件

**目标**: 实现安全的数据库交互组件

**实施步骤**:
1. **创建 `vools/db/postgresql.py`**:
   - 实现 PostgreSQL 连接管理
   - 使用配置系统获取连接参数

2. **更新 `vools/spark/init.py`**:
   - 确保 Spark 会话正确初始化
   - 支持 PostgreSQL 连接

3. **更新 `vools/look_upon.py`**:
   - 使用配置系统获取数据库凭证
   - 使用配置系统获取文件路径

### 2.5 函数重载实现

**目标**: 确保所有重载机制正确实现

**实施步骤**:
1. **检查 `vools/decorators/overload.py`**:
   - 确保基础 overload 实现完整
   - 确保 overloads 实现完整

2. **检查 `vools/decorators/overcurry.py`**:
   - 确保 overcurry 实现完整

### 2.6 项目结构优化

**目标**: 优化项目结构，确保组件组织合理

**实施步骤**:
1. **重新组织文件结构**:
   - 确保模块划分清晰
   - 确保功能组织合理

2. **更新 `vools/__init__.py`**:
   - 确保所有组件正确导出

3. **更新文档**:
   - 更新 README.md
   - 更新 USER_GUIDE.md

## 3. 技术实现细节

### 3.1 日期模块实现

**vools/datetime/mydate.py**:
- 实现 vDate 函数，支持多种日期格式
- 实现日期相关的 Spark UDF
- 提供日期计算函数（days_gap, weeks_gap, months_gap 等）

**vools/datetime/mydates.py**:
- 实现 get_recently_months 函数
- 实现 get_recently_weeks 函数
- 实现 get_recently_days 函数
- 实现 get_dates 函数

**vools/datetime/range.py**:
- 整合 get_date_range 函数
- 实现 vicDate 类，提供丰富的日期操作功能

### 3.2 Spark UDF 实现

**vools/spark/udf.py**:
- 分类组织 UDF 函数
- 提供 UDF 注册功能
- 支持自动注册到 Spark 会话

### 3.3 配置系统实现

**vools/config.py**:
- 支持从配置文件加载配置
- 支持从环境变量加载配置
- 提供默认配置值
- 支持配置验证

### 3.4 数据库交互实现

**vools/db/postgresql.py**:
- 实现数据库连接池
- 支持事务管理
- 提供查询执行功能

**vools/look_upon.py**:
- 使用配置系统获取数据库凭证
- 使用配置系统获取文件路径
- 确保安全的数据库交互

## 4. 测试计划

### 4.1 单元测试
- 测试日期相关函数
- 测试 Spark UDF 函数
- 测试配置系统
- 测试数据库交互

### 4.2 集成测试
- 测试完整的工作流程
- 测试配置系统与其他组件的集成
- 测试数据库交互与 Spark 的集成

## 5. 部署计划

### 5.1 打包准备
- 更新 setup.py
- 更新 pyproject.toml
- 更新 requirements.txt

### 5.2 文档准备
- 更新 README.md
- 更新 USER_GUIDE.md
- 创建 API 文档

### 5.3 发布流程
- 构建包
- 上传到 PyPI
- 推送到 GitHub

## 6. 时间估算

| 任务 | 时间估算（小时） |
|------|-----------------|
| 日期模块实现 | 8 |
| Spark UDF 实现 | 4 |
| 配置系统实现 | 6 |
| 数据库交互实现 | 6 |
| 函数重载检查 | 2 |
| 项目结构优化 | 4 |
| 测试 | 6 |
| 文档更新 | 4 |
| 部署准备 | 4 |
| **总计** | **44** |

## 7. 依赖项

### 7.1 核心依赖
- Python 3.6+
- wrapt

### 7.2 数据处理依赖
- pandas
- numpy
- openpyxl
- xlrd
- xlwt

### 7.3 Spark 依赖
- pyspark 2.4.3+

### 7.4 数据库依赖
- psycopg2-binary (PostgreSQL)

### 7.5 测试依赖
- pytest
- pytest-cov
- black
- isort
- flake8
- mypy

## 8. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 日期格式处理复杂性 | 中 | 充分测试各种日期格式 |
| Spark UDF 注册失败 | 高 | 提供详细的错误处理和日志 |
| 数据库连接配置错误 | 高 | 提供配置验证和错误处理 |
| 配置文件权限问题 | 中 | 提供安全的配置文件存储建议 |
| 依赖版本不兼容 | 中 | 明确依赖版本要求 |

## 9. 结论

本实现计划涵盖了所有缺失的组件和功能，确保项目结构合理、功能完整、配置安全。通过系统的实施步骤，可以确保项目的高质量和可维护性。
