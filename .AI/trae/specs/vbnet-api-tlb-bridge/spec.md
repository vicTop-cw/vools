# VB.NET API TLB 桥接模块 - 产品需求文档

## Overview
- **Summary**: 在 vools.bridge.vbnet 子包中新增 API TLB 桥接模块，通过 VB.NET 包装 `E:\dlls\API-Setup\API\API.tlb` 中的 COM 组件，为 Python 提供 Windows 自动化能力（窗口操作、键鼠模拟、图像处理、文件系统、网络、JSON 等 70+ 接口）。
- **Purpose**: 利用已有的 API.tlb COM 组件，通过 VB.NET 互操作层封装为 Python 可直接调用的 API，扩展 vools 的 Windows 自动化能力。
- **Target Users**: 需要在 Python 中进行 Windows UI 自动化、系统操作、图像处理的开发者。

## Goals
- 创建 `vools.bridge.vbnet.api` 子模块，封装 API.tlb 中的核心 COM 接口
- 提供与现有 vools.bridge 框架一致的使用体验（装饰器/函数调用）
- 支持 Window、Mouse、Keyboard、Image、FileSystem、Process、Network 等核心模块
- 提供 Pythonic 的 API 设计（属性、方法、异常处理）
- 支持延迟加载，未安装 API.dll 时不影响其他功能

## Non-Goals (Out of Scope)
- 不重写 API.dll 的功能，仅做 VB.NET 互操作封装
- 不支持非 Windows 平台（API.dll 是 Windows 专用 COM 组件）
- 不实现所有 70+ 接口的 100% 覆盖，优先实现常用核心模块
- 不修改 API.dll 或 API.tlb 本身

## Background & Context
- `E:\dlls\API-Setup\API\API.tlb` 是一个 VB6/.NET 编写的 COM 组件，提供丰富的 Windows 自动化 API
- 现有 vools.bridge.vbnet 模块支持 VB.NET 动态编译和 DLL 调用，但没有专门的 TLB/COM 互操作封装
- 该组件已有 VBA 示例（API函数用法示例.xlsm），说明 COM 接口成熟稳定
- 项目需要支持 Python 3.6 - 3.13，桥接模块需遵循现有架构模式

## Functional Requirements
- **FR-1**: 提供 API 组件可用性检测（检查是否注册了 API.tlb 对应的 COM 组件）
- **FR-2**: 实现 Window 模块封装（查找窗口、窗口操作、获取窗口信息等）
- **FR-3**: 实现 Mouse 模块封装（鼠标移动、点击、滚轮等）
- **FR-4**: 实现 Keyboard 模块封装（按键模拟、热键等）
- **FR-5**: 实现 Image 模块封装（截图、图像处理、像素操作等）
- **FR-6**: 实现 FileSystem 模块封装（文件/目录操作）
- **FR-7**: 实现 Process 模块封装（进程管理、启动进程等）
- **FR-8**: 实现 Network 模块封装（网络检测、下载、HTTP 请求等）
- **FR-9**: 提供统一的 API 入口类和模块组织方式
- **FR-10**: 支持异常处理和错误码转换

## Non-Functional Requirements
- **NFR-1**: 性能：单次 COM 调用开销应 < 1ms（不含实际操作时间）
- **NFR-2**: 可用性：在 API.dll 未安装/未注册时，导入不报错，调用时给出清晰提示
- **NFR-3**: 兼容性：支持 Python 3.6 - 3.13，仅 Windows 平台可用
- **NFR-4**: 可维护性：代码结构清晰，易于新增对其他 TLB 接口的封装

## Constraints
- **Technical**: 
  - 仅 Windows 平台可用
  - 依赖 API.dll/API.tlb 正确注册
  - 需使用 VB.NET 或 C# 通过 COM Interop 包装
  - Python 端通过 pythonnet (clr) 或 win32com.client 调用
  - 遵循 vools 现有桥接模块架构
- **Business**: 无
- **Dependencies**: 
  - API.dll + API.tlb（用户系统需安装）
  - pythonnet（可选，用于 .NET 互操作）或 pywin32（用于 COM 调用）
  - .NET Framework / .NET Runtime

## Assumptions
- 用户系统已安装 API-Setup（API.dll 已注册为 COM 组件）
- 用户使用 Windows 操作系统
- API.tlb 中的接口设计稳定，不会频繁变更
- 可以通过 win32com.client 或 pythonnet 直接调用 COM 组件，无需额外 VB.NET 包装层（可选择直接 Python 调用或加 VB.NET 层）

## Acceptance Criteria

### AC-1: 模块可用性检测
- **Given**: 用户系统可能安装或未安装 API.dll
- **When**: 导入 `vools.bridge.vbnet.api` 并调用 `is_api_available()`
- **Then**: 正确返回 True/False；未安装时导入不抛出异常
- **Verification**: `programmatic`

### AC-2: Window 模块基本功能
- **Given**: API.dll 已正确注册
- **When**: 使用 Window 模块的 FindWindow、GetWindowText、GetWindowRect 等方法
- **Then**: 能正确查找窗口并获取窗口信息，返回值类型符合 Python 习惯
- **Verification**: `programmatic`

### AC-3: Mouse 模块基本功能
- **Given**: API.dll 已正确注册
- **When**: 调用 MouseMove、LeftClick 等方法
- **Then**: 鼠标执行对应操作，无异常抛出
- **Verification**: `programmatic`

### AC-4: Keyboard 模块基本功能
- **Given**: API.dll 已正确注册
- **When**: 调用 SendKeys、KeyDown 等方法
- **Then**: 键盘输入正确模拟
- **Verification**: `programmatic`

### AC-5: Image/截图功能
- **Given**: API.dll 已正确注册
- **When**: 调用 ScreenCapture 进行全屏截图
- **Then**: 返回图像数据（PIL Image 或 bytes），图像有效
- **Verification**: `programmatic`

### AC-6: FileSystem 模块
- **Given**: API.dll 已正确注册
- **When**: 调用 FileExists、DirectoryExists、ReadAllText 等方法
- **Then**: 文件操作结果正确，与 Python 内置 os 模块行为一致
- **Verification**: `programmatic`

### AC-7: 统一 API 入口
- **Given**: API.dll 已正确注册
- **When**: 通过 `from vools.bridge.vbnet import api` 使用
- **Then**: 可以访问 api.Window、api.Mouse、api.Keyboard 等子模块
- **Verification**: `programmatic`

### AC-8: 异常处理
- **Given**: API 调用出错（如查找不存在的窗口）
- **When**: 调用对应的方法
- **Then**: 抛出有意义的 Python 异常，包含错误信息
- **Verification**: `programmatic`

### AC-9: 与现有架构一致性
- **Given**: vools.bridge 现有模块架构
- **When**: 查看 api 子模块的代码结构
- **Then**: 遵循现有模块组织模式（__init__.py 导出、README.md 文档、类型映射等）
- **Verification**: `human-judgment`

### AC-10: 文档完整性
- **Given**: 新模块已实现
- **When**: 查看 README.md 和模块 docstring
- **Then**: 包含安装说明、使用示例、支持的功能列表
- **Verification**: `human-judgment`

## Open Questions
- [ ] 实现方式选择：直接用 win32com.client 调用 vs 用 VB.NET 写一层包装再通过 DLL 调用？
  - 方案 A：直接 Python + win32com.client（简单直接，性能稍差）
  - 方案 B：VB.NET 包装层 + pythonnet/clr 调用（更符合 vbnet 子包定位，性能更好）
  - 方案 C：VB.NET 编译为 DLL + ctypes 导出 C 接口（与现有 csharp/vbnet compiler 模式一致）
- [ ] 需要覆盖多少个接口？优先实现哪些模块？
- [ ] API.dll 的分发策略？随 vools 一起分发还是用户自行安装？
