# FreeBASIC 桥接 DLL 扩展集成 - 实施计划

## [x] Task 0: 内置编译器复制与 manager 配置
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 将 FreeBASIC 32/64 位编译器从 VFB 复制到 `vools/bridge/freebasic/compiler/`
  - 更新 `bridge/manager.py` 中 freebasic 配置，添加内置编译器路径
  - 设置 FBC、FBC_DIR、FBC32 环境变量
  - 验证编译器可用（`fbc_compiler_available()` 返回 True）
- **Acceptance Criteria Addressed**: AC-1, AC-7, AC-9
- **Test Requirements**:
  - `programmatic` TR-0.1: `fbc_compiler_available()` 返回 True
  - `programmatic` TR-0.2: `get_status('freebasic').compiler_path` 指向包内路径
  - `programmatic` TR-0.3: `@fbc` 装饰器能正常编译运行简单函数
  - `programmatic` TR-0.4: 环境变量 FBC、FBC_DIR 已设置
- **Notes**: 已完成。编译器已复制，manager 已更新，测试通过。

## [/] Task 1: 建立 DLL 库目录结构并复制核心 DLL
- **Priority**: high
- **Depends On**: Task 0
- **Description**: 
  - 创建 `vools/bridge/freebasic/libs/` 目录结构
  - 按平台分：`win32/`、`win64/`
  - 每个平台下按类别分：`database/`、`graphics/`、`multimedia/`、`gui/`、`web/`、`utils/`
  - 从 VFB 复制 64 位核心 DLL 到对应目录
    - database: sqlite3_x64.dll, libmysql64.dll
    - graphics: cairo64.dll
    - multimedia: SDL3.dll, SDL3_image.dll, SDL3_mixer.dll, SDL3_ttf.dll
    - gui: Scintilla64.dll, mCtrl64.dll
    - web: mb64.dll (可选，体积大)
    - utils: (待选)
  - 从 compiler/inc/ 中复制对应的 .bi 头文件到各目录的 `inc/` 子目录
  - 创建 `manifest.json` 描述每个 DLL 的元信息
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `human-judgement` TR-1.1: 目录结构符合规范（win64/ 下 6 个类别目录）
  - `human-judgement` TR-1.2: 每个 DLL 都有对应的 inc/ 子目录和 .bi 文件
  - `programmatic` TR-1.3: manifest.json 格式正确，能被 Python 正常解析
  - `programmatic` TR-1.4: 用 ctypes 能直接加载每个 DLL（不崩溃）
- **Notes**: 第一阶段只做 64 位，32 位目录预留空文件夹或 README

## [x] Task 2: 增强 loader.py 支持第三方 DLL 加载
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 重写 `freebasic/loader.py`，扩展现有 `get_fbc_lib` 和 `is_fbc_available`
  - 新增 `get_fb_lib(name, category=None, platform=None)` 函数
  - 新增 `list_fb_libs(category=None)` 函数
  - 新增 `FbLibraryLoader` 类，对齐 `core.loader.LibraryLoader` 模式
  - 支持从 manifest.json 读取元信息
  - 自动处理 DLL 依赖（按 manifest 中的 dependencies 顺序加载）
  - DLL 路径搜索优先级：libs/win64/类别/ > libs/win64/ > 系统 PATH
  - 保持向后兼容：`get_fbc_lib('vools_fbc_demo')` 仍可用
- **Acceptance Criteria Addressed**: AC-3, AC-9
- **Test Requirements**:
  - `programmatic` TR-2.1: `get_fb_lib('sqlite3', 'database')` 返回 CDLL 实例
  - `programmatic` TR-2.2: 能调用 sqlite3_libversion 函数
  - `programmatic` TR-2.3: `list_fb_libs()` 返回所有可用 DLL 列表
  - `programmatic` TR-2.4: 重复调用返回同一实例（单例）
  - `programmatic` TR-2.5: 旧 API `get_fbc_lib()` 仍然可用（向后兼容）
  - `programmatic` TR-2.6: DLL 不存在时返回 None 不抛异常
- **Notes**: 参考 nim/_loader.py 的模式，使用 setup_func 初始化函数签名

## [ ] Task 3: 更新 manager.py 集成 runtime 配置
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 更新 `bridge/manager.py` 中 freebasic 的 runtime_paths
  - 添加 libs/win64/ 及其子目录到运行时搜索路径
  - 添加 libs/win64/database、graphics 等到 DLL 搜索路径
  - 确保 `setup_runtime('freebasic')` 能正确配置所有环境
  - 验证 64 位 Python 上自动使用 fbc64，32 位 Python 上自动使用 fbc32
- **Acceptance Criteria Addressed**: AC-7, AC-9
- **Test Requirements**:
  - `programmatic` TR-3.1: `setup_runtime('freebasic')` 返回 True
  - `programmatic` TR-3.2: PATH 环境变量包含 libs 相关目录
  - `programmatic` TR-3.3: 64 位 Python 默认使用 fbc64.exe
  - `programmatic` TR-3.4: 现有 freebasic 相关功能不受影响

## [x] Task 4: 实现 SQLite3 shim 层（作为样板）
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 创建 `freebasic/sqlite3_shim.py`
  - 对齐 nim 桥接的 shim 模式（base64_shim.py, hash_shim.py 等）
  - 使用 `@bridge_function` 装饰器（core.decorators）或手动实现
  - 封装常用 SQLite3 功能：
    - 版本查询（sqlite3_libversion）
    - 打开/关闭数据库
    - 执行 SQL 语句
    - 查询结果获取
  - 提供 Python fallback（使用标准库 sqlite3 模块）
  - DLL 不可用时自动回退
  - 在 `__init__.py` 中导出 shim API
- **Acceptance Criteria Addressed**: AC-4, AC-5, AC-9
- **Test Requirements**:
  - `programmatic` TR-4.1: DLL 存在时调用 DLL 版本的 sqlite3_libversion
  - `programmatic` TR-4.2: DLL 不存在时 fallback 到 Python sqlite3 不报错
  - `programmatic` TR-4.3: 能打开内存数据库并执行简单 SQL
  - `programmatic` TR-4.4: API 符合 Python 习惯（类似标准库 sqlite3）
  - `programmatic` TR-4.5: `from vools.bridge.freebasic import sqlite3_version` 可用
- **Notes**: SQLite3 作为第一个 shim，建立样板模式，后续 DLL 可参照

## [ ] Task 5: 实现 Cairo shim 层
- **Priority**: medium
- **Depends On**: Task 4
- **Description**:
  - 创建 `freebasic/cairo_shim.py`
  - 封装常用 Cairo 2D 绘图功能
  - 提供 Python fallback（可选，用 Pillow 或其他库）
  - 在 `__init__.py` 中导出
- **Acceptance Criteria Addressed**: AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-5.1: 能创建 cairo surface 和 context
  - `programmatic` TR-5.2: 能绘制基本图形（矩形、圆形、线条）
  - `programmatic` TR-5.3: 能输出到 PNG 图片文件
  - `programmatic` TR-5.4: DLL 不存在时优雅降级
- **Notes**: Cairo 是图形库的核心，API 较多，第一阶段只封装常用绘图功能

## [ ] Task 6: 实现 FB 封装模块（.bas wrapper）
- **Priority**: medium
- **Depends On**: Task 1
- **Description**:
  - 创建 `vools/bridge/freebasic/modules/` 目录
  - 为 SQLite3 创建 `sqlite3_wrapper.bas`，封装常用操作
  - 为 Cairo 创建 `cairo_wrapper.bas`，简化绘图调用
  - 为 SDL3 创建 `sdl3_wrapper.bas`，简化窗口/渲染初始化
  - 封装函数使用 FB 风格命名，带 Export 关键字
  - 在 `@fbc` 装饰器的 module_code 参数中可直接引用
  - 确保头文件路径正确（能找到 inc/ 中的 .bi 文件）
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-6.1: 在 `@fbc` 中 `#Include Once "sqlite3_wrapper.bas"` 能成功编译
  - `programmatic` TR-6.2: 封装函数能正常调用并返回正确结果
  - `human-judgement` TR-6.3: .bas 代码风格一致，有清晰注释
  - `programmatic` TR-6.4: 封装模块不依赖外部路径，开箱即用
- **Notes**: FB 封装模块的目的是让用户在 @fbc 里写更少的样板代码

## [ ] Task 7: SDL3 多媒体库集成
- **Priority**: medium
- **Depends On**: Task 2
- **Description**:
  - 将 SDL3 + SDL3_image + SDL3_mixer + SDL3_ttf 放入 multimedia/ 目录
  - 处理 DLL 依赖关系（image/mixer/ttf 都依赖 SDL3 主库）
  - 在 loader 中正确设置依赖加载顺序
  - 创建基础的 `sdl3_shim.py`（可选，或只做 FB 封装模块）
  - 确保 SDL3 能正常初始化窗口和渲染器
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-7.1: SDL3.dll 能被 ctypes 正确加载
  - `programmatic` TR-7.2: SDL_Init(SDL_INIT_VIDEO) 返回 0（或模拟无窗口环境测试）
  - `programmatic` TR-7.3: loader 按正确顺序加载依赖（先 SDL3，再 image/mixer/ttf）
- **Notes**: SDL3 需要 GUI 环境，测试可能需要特殊处理（headless 模式或跳过图形测试）

## [ ] Task 8: 更新 README 文档
- **Priority**: medium
- **Depends On**: Task 4, Task 5, Task 6
- **Description**:
  - 更新 `vools/bridge/freebasic/README.md`
  - 新增章节：
    - 内置编译器说明（不再需要单独安装）
    - 扩展 DLL 库列表（按类别）
    - FB 封装模块使用方法
    - Python shim 层 API 文档
    - manifest.json 格式说明
  - 每个类别至少一个完整使用示例
  - 更新目录结构说明图
  - 保持与其他桥接子包 README 的风格一致
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `human-judgement` TR-8.1: 文档结构清晰，章节完整
  - `human-judgement` TR-8.2: 所有示例代码语法正确
  - `human-judgement` TR-8.3: API 文档包含参数、返回值、示例
  - `programmatic` TR-8.4: README 中的示例代码能实际运行（抽样验证）
- **Notes**: 文档风格参考 nim 桥接的 README

## [ ] Task 9: 单元测试与兼容性验证
- **Priority**: high
- **Depends On**: Task 4, Task 5
- **Description**:
  - 为 loader 模块编写单元测试
  - 为 SQLite3 shim 编写单元测试（含 fallback 场景）
  - 为 Cairo shim 编写单元测试
  - 验证 Python 3.6 兼容性（语法检查）
  - 验证向后兼容性（现有测试全部通过）
  - 测试文件放在 `tests/bridge/freebasic/` 目录
- **Acceptance Criteria Addressed**: AC-3, AC-4, AC-5, AC-9, AC-10
- **Test Requirements**:
  - `programmatic` TR-9.1: 所有新写的单元测试通过
  - `programmatic` TR-9.2: 现有 freebasic 相关测试全部通过（无回归）
  - `programmatic` TR-9.3: Python 3.6 语法检查通过（无 walrus operator 等）
  - `programmatic` TR-9.4: 所有导入使用相对导入
  - `human-judgement` TR-9.5: 测试覆盖率合理（核心功能 > 80%）
- **Notes**: 遵循项目现有的测试规范和目录结构

## [ ] Task 10: 更新 __init__.py 导出
- **Priority**: medium
- **Depends On**: Task 2, Task 4, Task 5, Task 6
- **Description**:
  - 更新 `freebasic/__init__.py`
  - 导出新增的 loader API（get_fb_lib, list_fb_libs）
  - 导出 shim 层的常用函数
  - 导出 FB 封装模块路径常量（MODULES_DIR）
  - 导出 DLL 库路径常量（LIBS_DIR）
  - 保持 `__all__` 列表同步更新
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `programmatic` TR-10.1: `from vools.bridge.freebasic import get_fb_lib` 成功
  - `programmatic` TR-10.2: `from vools.bridge.freebasic import sqlite3_version` 成功
  - `programmatic` TR-10.3: `__all__` 列表中的每个名称都能正常导入
  - `programmatic` TR-10.4: 旧 API 仍然可用（向后兼容）
- **Notes**: 参考 nim/__init__.py 的导出组织方式

---

### 任务依赖图

```
Task 0 (已完成)
   │
   ▼
Task 1 (目录结构 + DLL复制)
   │
   ├───────┐
   ▼       ▼
Task 2  Task 6
(loader) (FB封装)
   │
   ▼
Task 3 (manager集成)
   │
   ▼
Task 4 (SQLite3 shim)
   │
   ▼
Task 5 (Cairo shim)     Task 7 (SDL3)
   │                      │
   ├──────────┬───────────┘
   ▼          ▼
Task 8    Task 10
(文档)   (__init__导出)
   │
   ▼
Task 9 (单元测试)
```

### 实施阶段建议

**第一阶段（核心基础）**：Task 0, 1, 2, 3, 4, 10, 9
- 建立基础设施（目录、loader、manager）
- 完成 SQLite3 作为样板
- 确保向后兼容

**第二阶段（图形增强）**：Task 5, 6, 8
- Cairo 图形库封装
- FB 封装模块
- 完善文档

**第三阶段（多媒体扩展）**：Task 7
- SDL3 多媒体库集成
- 处理 GUI 相关的测试问题
