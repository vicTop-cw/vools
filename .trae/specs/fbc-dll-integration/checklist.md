# FreeBASIC 桥接 DLL 扩展集成 - 验证清单

## 架构与一致性

- [ ] 目录结构与现有 nim 桥接模式一致（shim、loader、modules 分层）
- [ ] 所有子包导入使用相对导入，无绝对导入
- [ ] 使用 core.loader / core.decorators 等基础设施，不重复造轮子
- [ ] 遵循 LangBridge 抽象接口规范
- [ ] 命名约定与现有桥接一致（xxx_shim.py, get_xxx_lib() 等）
- [ ] Python 3.6 语法兼容（无 walrus operator、无 f-string `=` 调试语法、无 generic subscripting 等）

## 内置编译器

- [ ] fbc64.exe 和 fbc32.exe 都在 compiler/ 目录下
- [ ] `fbc_compiler_available()` 返回 True
- [ ] `get_status('freebasic').compiler_path` 指向包内路径
- [ ] 环境变量 FBC、FBC_DIR、FBC32 已正确设置
- [ ] `@fbc` 装饰器能正常编译运行简单函数
- [ ] 64 位 Python 默认使用 fbc64，32 位 Python 默认使用 fbc32

## DLL 库目录结构

- [ ] libs/win64/ 下有 6 个类别目录：database, graphics, multimedia, gui, web, utils
- [ ] libs/win32/ 目录存在（预留）
- [ ] 每个 DLL 都在正确的类别目录下
- [ ] 每个类别目录有 inc/ 子目录，包含对应的 .bi 头文件
- [ ] manifest.json 格式正确，包含每个 DLL 的元信息
- [ ] manifest.json 中声明了 DLL 之间的依赖关系
- [ ] DLL 文件能被 ctypes.CDLL 正常加载（无崩溃）

## Loader 模块

- [ ] `get_fb_lib(name, category=None)` 能正确加载 DLL
- [ ] `list_fb_libs()` 返回所有可用 DLL 列表
- [ ] 重复调用返回同一实例（单例模式）
- [ ] DLL 不存在时返回 None，不抛异常
- [ ] 自动处理依赖（按 manifest 中的顺序加载）
- [ ] 旧 API `get_fbc_lib()` 仍然可用（向后兼容）
- [ ] `is_fbc_available()` 仍然正常工作
- [ ] loader 使用相对导入，不依赖外部模块
- [ ] 线程安全（有加载锁）

## Manager 集成

- [ ] `setup_runtime('freebasic')` 返回 True
- [ ] PATH 环境变量包含 compiler/bin/win64 目录
- [ ] PATH 环境变量包含 libs/win64 相关目录
- [ ] 64 位系统自动使用 64 位路径
- [ ] 现有 freebasic 的编译功能不受影响
- [ ] 其他语言（nim, c, cangjie 等）的配置不受影响

## SQLite3 Shim

- [ ] `sqlite3_shim.py` 文件存在
- [ ] DLL 存在时调用 DLL 版本的 sqlite3_libversion
- [ ] 返回值类型正确（字符串）
- [ ] DLL 不存在时自动 fallback 到 Python 标准库 sqlite3
- [ ] fallback 模式下功能完整（不报错）
- [ ] 能打开内存数据库（:memory:）
- [ ] 能执行简单的 CREATE TABLE / INSERT / SELECT 语句
- [ ] API 风格符合 Python 习惯（类似标准库 sqlite3）
- [ ] 错误处理正确（异常类型与标准库一致）
- [ ] 资源正确释放（关闭数据库）

## Cairo Shim（如实施）

- [ ] `cairo_shim.py` 文件存在
- [ ] 能创建 image surface
- [ ] 能创建 cairo context
- [ ] 能绘制基本图形（矩形、圆形、线条）
- [ ] 能设置颜色（RGB/RGBA）
- [ ] 能输出为 PNG 文件
- [ ] DLL 不存在时优雅降级（有 fallback 或明确报错）
- [ ] 资源正确释放（destroy surface 和 context）

## FB 封装模块

- [ ] modules/ 目录存在
- [ ] sqlite3_wrapper.bas 存在且语法正确
- [ ] cairo_wrapper.bas 存在且语法正确
- [ ] sdl3_wrapper.bas 存在且语法正确（如实施）
- [ ] 在 `@fbc` 装饰器中能通过 #Include Once 引入
- [ ] 封装函数能正常编译和调用
- [ ] 封装函数使用 Export 关键字导出
- [ ] 头文件路径正确（能找到 compiler/inc/ 中的 .bi）
- [ ] 代码风格一致，有清晰的注释

## SDL3 多媒体库（如实施）

- [ ] SDL3.dll 在 multimedia/ 目录下
- [ ] SDL3_image.dll / SDL3_mixer.dll / SDL3_ttf.dll 都在
- [ ] loader 按正确顺序加载依赖（先 SDL3，再子库）
- [ ] SDL3 能被 ctypes 正确加载
- [ ] 基本初始化函数可调用（如 SDL_Init / SDL_Quit）
- [ ] 文档中说明 SDL3 需要 GUI 环境

## __init__.py 导出

- [ ] `from vools.bridge.freebasic import get_fb_lib` 成功
- [ ] `from vools.bridge.freebasic import list_fb_libs` 成功
- [ ] `from vools.bridge.freebasic import sqlite3_version` 成功（或对应 API）
- [ ] `__all__` 列表完整，包含所有导出的名称
- [ ] 所有旧 API 仍在 `__all__` 中（向后兼容）
- [ ] 新增常量（LIBS_DIR, MODULES_DIR）已导出（如实施）

## 文档

- [ ] README.md 已更新
- [ ] 有内置编译器说明章节
- [ ] 有扩展 DLL 库列表（按类别）
- [ ] 每个类别至少有一个使用示例
- [ ] FB 封装模块有使用说明
- [ ] Python shim 层有 API 文档
- [ ] manifest.json 格式有说明
- [ ] 所有示例代码语法正确
- [ ] 文档风格与其他桥接子包一致
- [ ] 有向后兼容说明

## 向后兼容性

- [ ] 现有 `@fbc` 装饰器用法完全不变
- [ ] 现有 `compile_and_run` 函数行为不变
- [ ] 现有 `fbc_compiler_available` 返回值不变
- [ ] 现有 `get_fbc_lib` / `is_fbc_available` 仍可用
- [ ] 所有现有 freebasic 相关测试全部通过
- [ ] 其他桥接子包（nim, c, cangjie 等）不受影响

## 单元测试

- [ ] loader 模块有单元测试
- [ ] SQLite3 shim 有单元测试（含 fallback 场景）
- [ ] Cairo shim 有单元测试（如实施）
- [ ] 测试覆盖正常路径和错误路径
- [ ] 测试文件放在 tests/bridge/freebasic/ 目录
- [ ] 测试遵循项目现有的测试规范
- [ ] 所有新测试通过
- [ ] 所有现有测试仍通过（无回归）

## 代码质量

- [ ] 代码无语法错误
- [ ] 代码风格与现有代码一致
- [ ] 函数有 docstring
- [ ] 复杂逻辑有注释说明
- [ ] 无硬编码的绝对路径
- [ ] 使用平台无关的路径操作（os.path.join）
- [ ] 错误处理合理（不吞异常）
- [ ] 无内存泄漏风险（DLL 加载后正确管理）
