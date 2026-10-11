# vools.sys 与 LangBridge 扩展 - The Implementation Plan (Decomposed and Prioritized Task List)

## [ ] Task 1: 实现 @exe 装饰器
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 `vools/sys/exe.py` 中实现 `exe` 装饰器函数
  - 支持参数映射规则：`_f` → `-f value`，`__path` → `--path value`，`_m=None` → `-m`
  - 位置参数（无下划线前缀）按顺序追加到命令末尾
  - 支持 `async_mode=True` 异步模式
  - 支持 `fallback` 回退函数
  - 返回值为 `(returncode, stdout, stderr)` 元组
  - 函数体可以为 pass（装饰器自动构建命令执行）
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-1.1: 基本调用测试 - 使用 Python -c "print('hello')" 模拟 exe，验证返回 (0, "hello\n", "")
  - `programmatic` TR-1.2: 参数映射测试 - 验证 `_f='a'` → `-f a`，`__path='/tmp'` → `--path /tmp`，`_m=None` → `-m`
  - `programmatic` TR-1.3: 位置参数测试 - 验证无特殊前缀的参数按顺序追加
  - `programmatic` TR-1.4: 异步模式测试 - 验证 async_mode=True 时可以 await 调用
  - `programmatic` TR-1.5: fallback 测试 - 验证 exe 不存在时调用 fallback
  - `programmatic` TR-1.6: 无参函数测试 - 验证无参签名可以正常工作
- **Notes**: 使用 sys.executable + -c 来模拟外部程序进行测试

## [ ] Task 2: 实现 @dll 装饰器
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 `vools/sys/dll.py` 中实现 `dll` 装饰器函数
  - 装饰器参数格式 `"path/to/dll::{func_name}"`
  - 根据 Python 类型注解自动映射 ctypes 类型
  - 支持 `async_mode=True` 异步模式
  - 支持 `fallback` 回退函数
  - 函数体可以为 pass（装饰器自动加载调用）
- **Acceptance Criteria Addressed**: AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-2.1: 基本调用测试 - 用 C 编译一个简单的 add 函数 DLL，验证调用正确
  - `programmatic` TR-2.2: 类型映射测试 - 验证 int/float/str/bytes/bool 自动转换
  - `programmatic` TR-2.3: 返回值测试 - 验证返回类型正确映射
  - `programmatic` TR-2.4: 异步模式测试 - 验证 async_mode=True
  - `programmatic` TR-2.5: 无参函数测试 - 验证无参函数正常调用
- **Notes**: 测试用 DLL 可以用 MinGW gcc 动态编译生成，或者用 c 模块的编译能力

## [ ] Task 3: 更新 vools.sys.__init__ 导出
- **Priority**: medium
- **Depends On**: Task 1, Task 2
- **Description**: 
  - 在 `vools/sys/__init__.py` 中导出 `exe` 和 `dll` 装饰器
  - 保持现有 SysCLI 的导出不变
- **Acceptance Criteria Addressed**: FR-5
- **Test Requirements**:
  - `programmatic` TR-3.1: 导入测试 - `from vools.sys import exe, dll` 正常工作
  - `programmatic` TR-3.2: 向后兼容 - 现有 SysCLI 导入不受影响

## [ ] Task 4: 扩展 LangBridge 支持 only_code 模式
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 在 `LangBridge.decorator` 中新增 `only_code`、`output_file`、`write_mode`、`prefix`、`suffix` 参数
  - 实现仅代码生成逻辑：调用 generate_code 后不编译，直接写入文件
  - 支持多种写入模式：overwrite / append / insert:NN / replace:MM-NN
  - 支持 prefix 和 suffix 包裹生成的代码
  - 保持现有编译调用模式完全不变
- **Acceptance Criteria Addressed**: AC-6, AC-7, AC-8, AC-10
- **Test Requirements**:
  - `programmatic` TR-4.1: 覆盖写入测试 - 验证 only_code=True 时代码写入文件
  - `programmatic` TR-4.2: 追加模式测试 - 验证 write_mode='append' 时追加到末尾
  - `programmatic` TR-4.3: 插入模式测试 - 验证 write_mode='insert:5' 插入到第5行后
  - `programmatic` TR-4.4: 替换模式测试 - 验证 write_mode='replace:3-7' 替换第3到7行
  - `programmatic` TR-4.5: prefix/suffix 测试 - 验证生成代码包含前缀后缀
  - `programmatic` TR-4.6: 向后兼容测试 - 不传 only_code 时行为与之前完全一致
- **Notes**: 用 FreeBASIC 模块做测试验证即可，核心逻辑在基类

## [ ] Task 5: 扩展 LangBridge 支持 project 模式
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 在 `LangBridge.decorator` 中新增 `project_dir`、`entry` 参数
  - 增加抽象方法 `compile_project(project_dir: str, entry: str) -> str`，返回产物路径
  - 各语言子类按需实现项目编译（FreeBASIC 和 C 优先实现）
  - 支持缓存机制（基于项目文件内容哈希）
  - 支持异步模式
- **Acceptance Criteria Addressed**: AC-9, AC-10
- **Test Requirements**:
  - `programmatic` TR-5.1: FreeBASIC 项目编译测试 - 创建简单 fbp 项目，验证编译生成 exe/dll
  - `programmatic` TR-5.2: C 项目编译测试 - 创建简单 C 项目，验证编译生成产物
  - `programmatic` TR-5.3: 缓存测试 - 二次调用不重新编译
  - `programmatic` TR-5.4: 向后兼容 - 不传 project_dir 时行为不变
- **Notes**: 先实现 FreeBASIC 和 C 的 project 编译，其他语言可以后续补充

## [ ] Task 6: 集成测试与文档
- **Priority**: low
- **Depends On**: Task 1, 2, 3, 4, 5
- **Description**: 
  - 编写综合测试用例，验证各功能组合使用
  - 确保所有模块无导入错误
  - 验证完整的端到端流程
- **Acceptance Criteria Addressed**: AC-10
- **Test Requirements**:
  - `programmatic` TR-6.1: 全部导入测试 - 所有新增模块无导入错误
  - `programmatic` TR-6.2: 接口一致性测试 - @exe/@dll/@lang 装饰器风格一致
  - `programmatic` TR-6.3: 现有测试回归 - 现有功能不受影响
