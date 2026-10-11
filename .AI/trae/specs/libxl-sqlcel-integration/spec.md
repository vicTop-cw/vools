# LibXL DLL 替换与 SqlCel 集成 - 产品需求文档

## Overview
- **Summary**: 本文档描述两个任务：1) 确认并替换 vools.xl 使用的 libxl.dll 为 VFB 项目中的免注册版本；2) 设计并实现 SqlCel .NET 程序集的 Python API 封装，为 vools 提供高性能的 Excel 数据处理和数据集操作能力。
- **Purpose**: 确保 LibXL DLL 分发版本的正确性（免注册、体积优化），并将 SqlCel 丰富的 Excel 数据处理能力集成到 vools 生态中，扩展 xl 和 data 模块的功能边界。
- **Target Users**: vools 库的使用者，特别是需要高性能 Excel 数据处理、复杂数据集操作的 Python 开发者。

## Goals
- 确认现有 libxl.dll 与 VFB 项目中 libxl.dll 的差异，选择最优版本进行分发
- 验证 libxl.dll 的免注册特性（原生 C DLL，无需 COM 注册）
- 设计 SqlCel Python API 封装方案，明确子包结构
- 实现核心 SqlCel 功能的 Python 封装（数据查询、Excel操作、数据集处理）
- 与现有 vools.xl 和 vools.data 模块形成互补/集成
- 保持与现有 vools 架构风格一致

## Non-Goals (Out of Scope)
- 不重新实现 SqlCel 的内部逻辑，仅做 DLL 调用封装
- 不修改 SqlCel 源代码
- 不支持非 Windows 平台（SqlCel 依赖 .NET 和 Office 互操作）
- 不实现 Excel VBA 宏运行环境（IronPython 集成暂不做）
- 不做 GUI 界面，仅提供 Python API
- 不替换现有 vools.xl 的 LibXL 实现，SqlCel 作为补充能力

## Background & Context

### LibXL DLL 现状
- 当前 `vools/xl/_dlls/libxl.dll`: MD5=CCB7994E8AACFC188B181BDDD6ED91DD, 9,312,256 字节 (~9MB)
- VFB 项目中 `E:\vb\FileRecv\VisualFreeBasic5.6.3\Projects\Test1\release\libxl.dll`: MD5=A42555B55A5211A757F0962442FA3516, 6,517,248 字节 (~6.5MB)
- 两者均为原生 C DLL，使用 ctypes.CDLL 加载，**不需要 COM 注册**（免注册）
- 当前 DLL 体积更大，可能包含更多功能（如同时支持 xls/xlsx）或不同编译选项

### SqlCel 现状
- SqlCel 是一款 Excel 数据处理插件，核心功能包括：
  - D_ 系列函数：D_FIND、D_VLOOKUP、D_SUMIF、D_COUNTIF、D_AVERAGEIF 等（类 Excel 函数但性能更高）
  - 表堆堆：可视化数据处理流程
  - 工作表查询：SQL 查询 Excel 数据
  - 支持 Excel 和 WPS
- 核心 DLL（均为 .NET Assembly）：
  - `LittleSql.dll`: SQL 引擎核心
  - `Bridge.dll`: Excel 插件桥接层，含 `Bridge.AddInFuncs` 类（代码混淆）
  - `SqlCelAddIn.dll`: Excel COM 插件主程序
- Bridge.AddInFuncs 公开方法包括：ActiveWB、AddSheet、GetSht、ListRsltToExcel、arrToRange、Run、Run2 等

### 现有 vools 架构
- `vools.bridge.csharp/vbnet`: 支持 .NET 程序集的编译和调用
- `vools.bridge.vbnet.api`: 通过 COM 封装 API.tlb 的范例
- `vools.xl`: 基于 LibXL 的 Excel 读写库，支持 xls/xlsx
- `vools.data`: 含 Table 类的轻量级二维数据结构，支持 SQL 风格链式操作

## Functional Requirements

### FR-1: LibXL DLL 版本确认与替换
- 对比两个 libxl.dll 的功能差异（支持的格式、导出函数、版本号）
- 确认 VFB 版本的 libxl.dll 是否完全兼容现有 vools.xl API
- 如兼容，替换为 VFB 版本（体积更小，~6.5MB vs ~9MB）
- 更新 _dlls 目录和相关文档

### FR-2: SqlCel 子包结构设计
- 创建独立子包 `vools.sqlcel`（顶级子包，非 bridge 孙包）
- 理由：SqlCel 是面向用户的功能模块，不是桥接语言实现细节
- 内部通过 `vools.bridge.csharp` 或 pythonnet 调用 .NET DLL
- 子包结构：`vools/sqlcel/__init__.py`、`core.py`、`functions.py`、`dataset.py` 等

### FR-3: SqlCel 核心函数封装（D_ 系列）
- 封装 D_FIND、D_VLOOKUP、D_SUMIF、D_SUMIFS、D_COUNTIF、D_COUNTIFS
- 封装 D_AVERAGEIF、D_AVERAGEIFS、D_MAX、D_MIN、D_SUMPRODUCT
- 封装 D_LARGE、D_SMALL、D_MEDIAN、D_STDEV、D_VAR、D_CORREL
- 函数参数从 Excel 范围字符串适配为 Python 数据结构（list/Table/DataFrame）

### FR-4: 数据集操作 API
- 提供类似 SqlCel "表堆堆" 的链式数据处理 API
- 与 vools.data.Table 集成/互补
- 支持：筛选、排序、分组聚合、连接、合并、去重、行列转换等
- 支持从 Excel 读取数据集、写回 Excel

### FR-5: Excel 操作封装
- 封装 ActiveWB、AddSheet、GetSht 等 Excel 互操作方法
- 封装 ListRsltToExcel、arrToRange 等数据写入方法
- 封装 Run/Run2 宏执行方法（可选）
- 仅支持 Windows 平台 + 已安装 Excel/WPS

### FR-6: 延迟导入与容错
- SqlCel 为可选功能，未安装时导入不报错
- 使用延迟导入机制（参考 vools.bridge.vbnet api 模块）
- 提供 `sqlcel_available()` 函数检测可用性

## Non-Functional Requirements

- **NFR-1**: 性能 - SqlCel 函数调用的 Python 包装开销应小于 1ms
- **NFR-2**: 兼容性 - 支持 Python 3.6 - 3.13，仅 Windows 平台
- **NFR-3**: 可用性 - 未安装 SqlCel 时 vools 其他模块不受影响
- **NFR-4**: 可维护性 - 代码结构与现有 vools 风格一致
- **NFR-5**: 文档 - 提供完整的 API 文档和使用示例

## Constraints

- **Technical**: 
  - SqlCel 仅支持 Windows 平台
  - 依赖 .NET Framework（SqlCel 是 .NET Assembly）
  - Excel 互操作功能需要安装 Excel 或 WPS
  - Bridge.dll 代码混淆，直接反射调用可能受限
  - 需通过 pythonnet 或现有 csharp 桥接调用 .NET
- **Business**: 
  - SqlCel 是第三方商业软件，需用户自行安装授权
  - vools 仅提供封装，不分发 SqlCel DLL
- **Dependencies**: 
  - pythonnet（用于调用 .NET Assembly）
  - pywin32（用于 Excel COM 互操作，可选）
  - vools.bridge.csharp 现有架构

## Assumptions

- VFB 版本的 libxl.dll 与当前版本 API 兼容（都是 LibXL 3.x）
- SqlCel Bridge.dll 的公开方法可以通过 .NET 反射正常调用
- 用户已自行安装 SqlCel 并拥有合法授权
- pythonnet 可在用户环境中正常工作
- 混淆后的类型名/方法名在不同 SqlCel 版本中保持稳定（或有版本兼容策略）

## Acceptance Criteria

### AC-1: LibXL DLL 替换验证
- **Given**: 两个版本的 libxl.dll 可用
- **When**: 对比 DLL 的导出函数列表和版本信息，并运行现有 xl 测试套件
- **Then**: 若 VFB 版本兼容，则替换成功，所有现有 xl 测试通过，DLL 体积减小
- **Verification**: `programmatic`
- **Notes**: 如不兼容则保留现有版本，文档说明差异

### AC-2: SqlCel 子包创建
- **Given**: vools 项目结构
- **When**: 创建 vools.sqlcel 子包并实现延迟导入
- **Then**: import vools.sqlcel 在无 SqlCel 环境不报错，sqlcel_available() 返回 False
- **Verification**: `programmatic`

### AC-3: 核心 D_ 函数封装
- **Given**: SqlCel 已安装且可用
- **When**: 调用封装后的 D_SUMIF、D_VLOOKUP、D_FIND 等函数
- **Then**: 返回正确的计算结果，参数接受 Python list/Table 格式
- **Verification**: `programmatic`
- **Notes**: 至少封装 10 个最常用的 D_ 函数

### AC-4: 数据集操作 API
- **Given**: 已加载的数据集（Table 或 list of dict）
- **When**: 执行筛选、排序、分组聚合等链式操作
- **Then**: 返回正确结果，API 风格与 vools.data.Table 一致或互补
- **Verification**: `programmatic`

### AC-5: 与 xl/data 模块集成
- **Given**: vools.xl 和 vools.data 已可用
- **When**: 使用 sqlcel 从 Excel 读取数据并进行处理
- **Then**: 数据可无缝转换为 Table 或 DataFrame，可使用 xl 写回
- **Verification**: `programmatic`

### AC-6: 文档与示例
- **Given**: 完成的 sqlcel 子包
- **When**: 用户阅读 README
- **Then**: 能了解功能、安装方法、使用示例和限制
- **Verification**: `human-judgment`

## Open Questions

- [ ] SqlCel Bridge.dll 混淆后的方法签名是否稳定？是否需要版本适配层？
- [ ] 使用 pythonnet 还是现有 vools.bridge.csharp 架构调用 .NET？
- [ ] 哪些 D_ 函数是最高优先级需要封装的？（用户可指定 Top N）
- [ ] 是否需要实现 SqlCel 的 "表堆堆" 可视化流程概念，还是仅提供函数式 API？
- [ ] Excel 互操作功能（ActiveWB 等）的优先级？需要 Excel/WPS 安装的功能是否做？
