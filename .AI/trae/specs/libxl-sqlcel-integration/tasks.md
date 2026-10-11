# LibXL DLL 替换与 SqlCel 集成 - 实施计划

## [ ] Task 1: LibXL DLL 版本对比与兼容性验证
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 使用 dumpbin 或 Python ctypes 枚举两个 DLL 的导出函数列表
  - 对比函数数量、函数名、版本号信息（xlBookVersion 等）
  - 用 VFB 版本 DLL 运行现有 xl 测试套件，验证 API 兼容性
  - 确认 VFB 版本是否同时支持 xls 和 xlsx 格式
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: 两个 DLL 的导出函数列表对比报告（数量、差异函数）
  - `programmatic` TR-1.2: 现有 xl 测试套件（test_xl_*.py）全部通过
  - `programmatic` TR-1.3: xls 和 xlsx 两种格式读写均正常工作
  - `programmatic` TR-1.4: DLL 文件大小对比（当前 ~9MB vs VFB ~6.5MB）
- **Notes**: 如 VFB 版本不兼容（缺函数、版本旧），则保留当前版本并在文档中说明

## [ ] Task 2: LibXL DLL 替换（如兼容）
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 如 Task 1 确认兼容，将 VFB 版本 libxl.dll 复制到 `vools/xl/_dlls/` 替换现有版本
  - 更新 `_dlls/__init__.py` 中的版本信息（如有）
  - 更新 xl README 中的 DLL 来源和版本说明
  - 再次运行完整测试套件确保替换后功能正常
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-2.1: 替换后所有 xl 测试通过
  - `programmatic` TR-2.2: DLL MD5 与 VFB 版本一致
  - `programmatic` TR-2.3: xls/xlsx 格式读写、格式设置、批量操作均正常
- **Notes**: 替换前备份当前 DLL

## [ ] Task 3: SqlCel 子包骨架与延迟导入机制
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 创建 `vools/sqlcel/` 目录及 `__init__.py`
  - 实现延迟导入机制（参考 `vools/bridge/vbnet` 的 `__getattr__` + `_load_api` 模式）
  - 提供 `sqlcel_available()` 检测函数
  - 定义子包模块结构：`core.py`（加载器/桥接核心）、`functions.py`（D_系列函数）、`dataset.py`（数据集操作）
  - 支持用户指定 SqlCel 安装路径（环境变量或参数）
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-3.1: `import vools.sqlcel` 在无 SqlCel 环境不报错
  - `programmatic` TR-3.2: `sqlcel_available()` 在无 SqlCel 时返回 False
  - `programmatic` TR-3.3: 导入不影响 vools 其他模块正常使用
  - `human-judgement` TR-3.4: 代码结构与现有 vools 风格一致
- **Notes**: 默认从 D:\SqlCel 或环境变量 SQLCEL_PATH 查找

## [ ] Task 4: SqlCel .NET 桥接层实现
- **Priority**: high
- **Depends On**: Task 3
- **Description**: 
  - 研究 pythonnet 调用 .NET Assembly 的最佳方式
  - 实现 `core.py` 中的 SqlCel 加载器，加载 Bridge.dll
  - 通过反射获取 Bridge.AddInFuncs 的方法列表（处理混淆类型名）
  - 封装方法调用逻辑，处理参数类型转换（Python <-> .NET）
  - 实现错误处理和异常转换
- **Acceptance Criteria Addressed**: AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-4.1: 成功加载 Bridge.dll 并获取 AddInFuncs 类型
  - `programmatic` TR-4.2: 能枚举所有公开方法
  - `programmatic` TR-4.3: 调用至少一个简单方法（如 AlittleTest）成功
  - `programmatic` TR-4.4: 类型转换正确（int, str, list, array）
- **Notes**: 如 pythonnet 不可用，评估使用现有 csharp 桥接架构

## [ ] Task 5: D_ 系列核心函数封装
- **Priority**: high
- **Depends On**: Task 4
- **Description**: 
  - 在 `functions.py` 中封装最常用的 10+ 个 D_ 函数
  - 优先级：D_SUMIF, D_SUMIFS, D_COUNTIF, D_COUNTIFS, D_VLOOKUP, D_FIND, D_AVERAGEIF, D_MAX, D_MIN, D_SUMPRODUCT
  - 参数适配：将 Python list/Table/DataFrame 转换为 SqlCel 需要的格式
  - 结果转换：将 .NET 返回值转换为 Python 原生类型
  - 每个函数添加文档字符串和类型注解
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-5.1: 至少 10 个 D_ 函数可调用
  - `programmatic` TR-5.2: 每个函数有对应的单元测试，验证计算正确性
  - `programmatic` TR-5.3: 支持 list of dict 和 Table 两种输入格式
  - `programmatic` TR-5.4: 错误输入有合理的异常提示
- **Notes**: D_ 函数原本操作 Excel 范围，封装后改为操作内存数据结构

## [ ] Task 6: 数据集操作 API
- **Priority**: medium
- **Depends On**: Task 5
- **Description**: 
  - 在 `dataset.py` 中实现数据集类 SqlCelDataset
  - 封装筛选、排序、分组聚合、连接、合并等操作
  - 与 vools.data.Table 双向转换
  - 提供链式调用 API（类似 Table 的风格）
  - 支持从 Excel 读取、写回 Excel
- **Acceptance Criteria Addressed**: AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-6.1: 数据集基本操作（筛选、排序、聚合）正常
  - `programmatic` TR-6.2: 与 Table 的双向转换正确
  - `programmatic` TR-6.3: 链式调用 API 流畅可用
  - `human-judgement` TR-6.4: API 设计符合 Python 习惯
- **Notes**: 优先实现 SqlCel 有而 Table 没有的功能，避免重复

## [ ] Task 7: 与 xl/data 模块集成
- **Priority**: medium
- **Depends On**: Task 6
- **Description**: 
  - 实现从 vools.xl 读取的数据直接传入 SqlCel 函数
  - 实现 SqlCel 结果用 vools.xl 写回 Excel
  - 在 data Table 中添加使用 SqlCel 函数的便捷方法（可选）
  - 在 xl README 中添加 SqlCel 集成说明
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-7.1: xl -> sqlcel -> xl 端到端流程正常
  - `programmatic` TR-7.2: Table <-> SqlCelDataset 转换无损
  - `human-judgement` TR-7.3: 集成方式自然，不违和
- **Notes**: 保持松耦合，SqlCel 可选不影响 xl/data

## [ ] Task 8: 文档与示例
- **Priority**: medium
- **Depends On**: Task 5, Task 6
- **Description**: 
  - 撰写 `vools/sqlcel/README.md`
  - 内容包括：功能介绍、安装要求、快速开始、API 参考、注意事项
  - 添加使用示例：D_ 函数使用、数据集操作、与 xl 集成
  - 更新 vools 顶层 README 的模块列表
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `human-judgement` TR-8.1: README 内容完整，结构清晰
  - `human-judgement` TR-8.2: 示例代码可运行，结果正确
  - `human-judgement` TR-8.3: 限制和依赖说明清楚
- **Notes**: 明确说明 SqlCel 需用户自行安装授权

## [ ] Task 9: 单元测试与兼容性验证
- **Priority**: high
- **Depends On**: Task 5, Task 6
- **Description**: 
  - 创建 `tests/sqlcel/` 测试目录
  - 编写核心功能单元测试（D_函数、数据集、加载器）
  - 无 SqlCel 环境下的测试（验证延迟导入不报错）
  - Python 3.6 兼容性检查（语法、类型注解等）
  - 验证测试文件归档规范
- **Acceptance Criteria Addressed**: AC-2, AC-3, AC-4
- **Test Requirements**:
  - `programmatic` TR-9.1: 无 SqlCel 环境下所有非功能测试通过
  - `programmatic` TR-9.2: 有 SqlCel 环境下功能测试全部通过
  - `programmatic` TR-9.3: Python 3.6 语法兼容（无 walrus、无 match 等）
  - `programmatic` TR-9.4: 测试文件按规范归档在 tests/sqlcel/
- **Notes**: 测试需区分「有 SqlCel」和「无 SqlCel」两种场景
