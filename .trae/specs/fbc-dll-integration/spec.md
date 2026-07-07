# FreeBASIC 桥接 DLL 扩展集成 - 产品需求文档

## Overview
- **Summary**: 在现有 vools.bridge.freebasic 桥接子包基础上，集成 VisualFreeBasic 中的第三方 DLL 库，扩展 FreeBASIC 桥接的功能边界。将 VFB 中可用的 20+ 个第三方 C 库（SQLite、Cairo、SDL、Scintilla、Miniblink 等）按类别组织到 freebasic 子包中，配套提供 FB 封装模块和 Python shim 层，让用户可以通过 `@fbc` 装饰器或直接 Python API 调用这些库的功能。
- **Purpose**: 解决当前 freebasic 桥接只有编译器、没有现成可用扩展库的问题。利用 VFB 生态中已有的丰富 DLL 资源，为 vools 用户提供开箱即用的数据库、图形、多媒体、浏览器等能力，同时保持与现有桥接框架的一致性。
- **Target Users**: 使用 vools.bridge.freebasic 的开发者，需要在 Python 中调用高性能原生库的用户，以及从 VisualFreeBasic 迁移到 Python 的开发者。

## Goals
- 将 FreeBASIC 32/64 位编译器内置到桥接子包中，实现零依赖开箱即用
- 建立规范化的第三方 DLL 库目录结构，按类别（database/graphics/multimedia/gui/web/utils）组织
- 对齐现有 nim 桥接的 shim 模式，为核心 DLL 提供 Python 封装层
- 提供 FreeBASIC 侧的 .bas 封装模块，简化用户在 `@fbc` 装饰器中的调用
- 更新 manager 配置，支持自动发现和加载内置 DLL 库
- 更新 README 文档，说明新增功能和使用方式
- 保持与现有桥接框架（core.loader、bridge_function 装饰器、LangBridge 抽象）的完全兼容

## Non-Goals (Out of Scope)
- 不重写或修改现有 core 模块的 API
- 不为所有 200+ 个 VFB DLL 提供封装，只选取高价值的核心库（约 7 大类，15-20 个 DLL）
- 不实现 32 位 DLL 的 Python 侧直接调用（32 位 DLL 仅通过 `@dll32` 装饰器或在 32 位 FB 编译时使用）
- 不修改 `@fbc` 装饰器的核心编译逻辑
- 不实现 GUI 相关的 Python 侧封装（只提供底层 DLL 访问能力）
- 不做性能优化（第一阶段只做功能集成）

## Background & Context

### 现有框架结构
vools.bridge 框架采用分层设计：
1. **core 层**：`vools.bridge.core` 提供共享库加载器（loader.py）、类型映射（types.py）、桥接装饰器（decorators.py）等通用基础设施
2. **LangBridge 抽象**：`vools.bridge._base` 定义统一的语言桥接接口规范
3. **语言桥接层**：各语言（nim、c、cangjie、freebasic 等）继承 LangBridge，实现各自的编译和调用逻辑
4. **shim 层**：nim 桥接采用 `xxx_shim.py` + Python fallback 的模式，提供优雅的降级体验

### FreeBASIC 桥接现状
- 已有 `@fbc` 装饰器，支持动态编译 FB 代码为 DLL
- 已有类型映射和 Transport 抽象（免序列化数组传递）
- 已有 loader.py 框架，但没有实际的预编译库
- 编译器刚刚从 VFB 复制到 `compiler/` 子目录，已更新 manager.py 配置

### VFB DLL 资源
从 `E:\VFB599\VisualFreeBasic599` 中可提取的高价值 DLL：
- 数据库：SQLite3（32/64）、MySQL（32/64）
- 图形：Cairo（32/64）
- 多媒体：SDL3 + SDL3_image + SDL3_mixer + SDL3_ttf（32/64）
- 代码编辑器：Scintilla（32/64）
- 浏览器：Miniblink（32/64）
- UI 控件：mCtrl（32/64）
- 工具：7-zip（32位）

### 技术约束
- 项目必须支持 Python 3.6 到 3.13
- 所有子包导入必须使用相对导入
- DLL/SO 文件必须放在 `vools/lib/windows/` 或对应语言子目录下
- 桥接库命名遵循 `vools_<name>.dll` 约定（nim 桥接模式）

## Functional Requirements

### FR-1: 内置编译器集成
- 将 FreeBASIC 32位和64位编译器完整复制到 `vools/bridge/freebasic/compiler/`
- 编译器路径自动注册到 bridge.manager，优先使用内置编译器
- 自动设置 FBC、FBC_DIR 等环境变量
- 64位 Python 默认使用 fbc64.exe，32位 Python 默认使用 fbc32.exe

### FR-2: 第三方 DLL 库目录结构
- 在 `vools/bridge/freebasic/libs/` 下建立规范化的库目录结构
- 按平台分目录：`win32/`（32位）、`win64/`（64位）
- 每个平台下按类别分目录：`database/`、`graphics/`、`multimedia/`、`gui/`、`web/`、`utils/`
- 每个类别目录下放对应的 DLL 文件
- 对应 FB 头文件（.bi）放在各 DLL 所在目录的 `inc/` 子目录
- 提供 `manifest.json` 描述每个 DLL 的元信息（名称、版本、函数数量、依赖等）

### FR-3: FB 封装模块（.bas wrapper）
- 为核心 DLL 提供 FreeBASIC 侧的简化封装模块
- 封装模块放在 `vools/bridge/freebasic/modules/` 目录
- 每个 DLL 对应一个 `xxx_wrapper.bas` 文件
- 封装常用功能，屏蔽底层复杂的 C API 调用
- 用户可在 `@fbc` 装饰器中通过 `#Include Once` 引入这些模块

### FR-4: Python shim 层
- 对齐 nim 桥接的 shim 模式，为核心 DLL 提供 Python 侧封装
- shim 文件命名：`xxx_shim.py`，放在 `vools/bridge/freebasic/` 目录
- 每个 shim 模块包含：DLL 加载、函数签名设置、Python 友好 API、Python fallback 实现
- 优先用 `@bridge_function` 装饰器（core.decorators）实现，保持框架一致性
- DLL 不可用时自动回退到纯 Python 实现

### FR-5: 扩展 loader 模块
- 增强 `freebasic/loader.py`，支持加载第三方 DLL
- 提供 `get_fb_lib(name, category=None)` 函数，按名称和类别查找 DLL
- 提供 `list_fb_libs()` 函数，列出所有可用的扩展 DLL
- 自动处理 DLL 依赖（如 SDL3_image 依赖 SDL3）
- 与 `core.loader.LibraryLoader` 模式保持一致

### FR-6: 管理器集成
- 在 bridge.manager 中注册 freebasic 的 runtime_paths，包含 libs 目录
- 设置 DLL 搜索路径，确保运行时能正确加载依赖
- 支持 `setup_runtime('freebasic')` 自动配置所有环境

### FR-7: 文档更新
- 更新 `vools/bridge/freebasic/README.md`
- 新增章节：内置编译器、扩展 DLL 库、FB 封装模块、Python shim 层
- 每个类别 DLL 提供使用示例
- 补充完整的 API 文档

## Non-Functional Requirements

### NFR-1: 向后兼容
- 所有现有 API 保持不变，不破坏现有用户代码
- 新增功能均为增量添加
- `@fbc` 装饰器行为完全不变

### NFR-2: 框架一致性
- 目录结构、命名约定、API 风格与现有 nim 桥接保持一致
- 使用 core 模块提供的基础设施（loader、types、decorators）
- 遵循 LangBridge 抽象接口规范

### NFR-3: Python 版本兼容
- 支持 Python 3.6 到 3.13
- 不使用 3.6 不支持的语法（如 walrus operator、generic subscripting 等）
- 使用相对导入，不使用绝对导入

### NFR-4: 跨平台兼容
- 目录结构设计考虑 Linux 支持（预留 linux/ 目录位置）
- 平台判断使用 `platform.system()` 而非硬编码
- DLL 加载使用 `os.name == 'nt'` 判断

### NFR-5: 性能无退化
- 新增的 loader 逻辑不影响现有 `@fbc` 装饰器的编译速度
- shim 层的 overhead 可忽略（< 5%）
- DLL 加载使用单例模式，避免重复加载

### NFR-6: 可维护性
- 代码结构清晰，模块化设计
- 每个 DLL 的封装独立，易于新增和移除
- manifest.json 驱动的库注册机制

## Constraints

### 技术约束
- 必须使用 Python 3.6+ 兼容语法
- 必须使用相对导入
- DLL 文件必须放在 vools 包内（随包分发）
- 必须与现有 bridge.core 和 bridge.manager 集成

### 业务约束
- 第一阶段只集成 64 位 DLL（当前主要使用场景）
- 32 位 DLL 只做目录预留，不提供 Python 侧封装
- 优先选择有对应 .bi 头文件的 DLL

### 依赖约束
- 第三方 DLL 来自 VisualFreeBasic 599 版本
- 不修改第三方 DLL 的源代码
- DLL 之间的依赖关系需要正确处理（如 SDL 系列）

## Assumptions

- 用户主要在 64 位 Windows 上使用 vools
- VFB 中的 DLL 可以合法地随 vools 分发（需要用户确认）
- 现有 FreeBASIC 编译器（从 VFB 复制的版本）功能完整
- ctypes 调用 C 风格 DLL 的方式适用于所有目标 DLL
- 用户对性能敏感，愿意用 FB/DLL 换取速度
- 大部分用户不需要 GUI 相关的 Python 封装（只要能在 FB 代码里调用就行）

## Acceptance Criteria

### AC-1: 内置编译器可用
- **Given**: 用户安装了 vools 包
- **When**: 调用 `from vools.bridge.freebasic import fbc_compiler_available` 并检查返回值
- **Then**: 返回 True，且编译器路径指向包内的 compiler/ 目录
- **Verification**: `programmatic`
- **Notes**: 用 `get_status('freebasic').compiler_path` 验证路径

### AC-2: DLL 目录结构正确
- **Given**: vools 包已安装
- **When**: 检查 `vools/bridge/freebasic/libs/` 目录
- **Then**: 存在 win64/ 子目录，且包含 database/、graphics/、multimedia/、gui/、web/、utils/ 六个类别目录
- **Verification**: `human-judgment`
- **Notes**: 验证目录结构和文件存在

### AC-3: loader 能正确加载 DLL
- **Given**: libs 目录下有 sqlite3_x64.dll
- **When**: 调用 `get_fb_lib('sqlite3', category='database')`
- **Then**: 返回 ctypes.CDLL 实例，且能调用 sqlite3_libversion 函数
- **Verification**: `programmatic`
- **Notes**: 用单元测试验证

### AC-4: shim 层正常工作（以 sqlite3 为例）
- **Given**: SQLite3 DLL 存在
- **When**: 导入 `vools.bridge.freebasic.sqlite3_shim` 并调用版本查询函数
- **Then**: 返回 SQLite3 版本字符串
- **Verification**: `programmatic`
- **Notes**: 验证 DLL 调用成功，且 API 符合 Python 习惯

### AC-5: shim 层 fallback 正常
- **Given**: SQLite3 DLL 不存在（或加载失败）
- **When**: 导入 sqlite3_shim 并调用版本查询
- **Then**: 使用 Python 标准库 sqlite3 作为 fallback，不报错
- **Verification**: `programmatic`
- **Notes**: 模拟 DLL 不存在的场景

### AC-6: FB 封装模块可用
- **Given**: modules/ 目录下有 sqlite3_wrapper.bas
- **When**: 在 `@fbc` 装饰器中 `#Include Once` 该模块并调用封装函数
- **Then**: 编译成功，函数正常执行
- **Verification**: `programmatic`
- **Notes**: 用实际的 @fbc 调用测试

### AC-7: 管理器集成正常
- **Given**: vools 包已安装
- **When**: 调用 `setup_runtime('freebasic')`
- **Then**: PATH 中包含 compiler 和 libs 相关目录，环境变量 FBC/FBC_DIR 已设置
- **Verification**: `programmatic`

### AC-8: 文档完整
- **Given**: README.md 文件
- **When**: 查阅文档
- **Then**: 包含内置编译器说明、扩展 DLL 列表、每个类别的使用示例、shim API 文档
- **Verification**: `human-judgment`

### AC-9: 向后兼容
- **Given**: 现有使用 `@fbc` 装饰器的代码
- **When**: 升级到新版本后运行
- **Then**: 所有现有测试通过，行为无变化
- **Verification**: `programmatic`
- **Notes**: 运行现有 freebasic 相关测试

### AC-10: Python 3.6 兼容
- **Given**: Python 3.6 环境
- **When**: 导入 vools.bridge.freebasic 模块
- **Then**: 无语法错误，所有功能正常
- **Verification**: `programmatic`

## Open Questions

- [ ] 第三方 DLL 的授权是否允许随 vools 分发？（需要用户确认 VFB 中 DLL 的授权）
- [ ] 第一阶段具体集成哪些 DLL？（建议 SQLite3 + Cairo + SDL3 核心）
- [ ] shim 层需要做到什么程度？（完整 API 封装 vs 常用功能封装）
- [ ] 32 位 DLL 是否需要在第一阶段也集成？（当前 64 位 Python 无法直接使用）
- [ ] Miniblink 这类大 DLL（~36MB）是否要集成？可能显著增加包体积
- [ ] 是否需要实现自动安装/下载 DLL 的机制（类似 nim 的编译机制）？
