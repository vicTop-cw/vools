# vools.actus.probe — 环境探测

`vools.actus.probe` 提供跨平台环境探测能力：检测操作系统、已安装工具链、
系统资源、权限状态等，为动作执行、依赖分析、平台适配提供事实依据。

## 核心模块

| 模块 | 公开符号 | 探测目标 |
|---|---|---|
| `TOOL_TABLE` | `TOOL_TABLE` | 已知系统工具表（编译器/解释器/CLI） |
| `platform` | `PlatformProber`, `probe`, `get_platform_info` | OS/arch/内核 |
| `compilers` | `CompilersProber`, `probe` | gcc/clang/rustc/nim 等 |
| `runtimes` | `RuntimesProber`, `probe` | python/node/java/go 等 |
| `python_pkgs` | `PythonPackagesProber`, `probe` | Python 已装包 |
| `environment` | `EnvironmentProber`, `probe`, `get_environment_info` | env 变量 |
| `permissions` | `PermissionsProber`, `probe`, `get_permissions_info` | 文件权限 |
| `resources` | `ResourcesProber`, `probe`, `get_resources_info` | CPU/内存/磁盘 |
| `actions` | `ActionsProber`, `probe` | 可执行动作 |
| `system_tools` | `SystemToolsProber`, `probe` | 系统工具可用性 |
| `cache` | `load_cache`, `save_cache`, `invalidate_cache` | 探测缓存 |
| `report` | `ProbeReport`, `format_summary`, ... | 探测报告聚合 |

## 探测协议

每个 Prober 子类实现：

- `probe()` → `list[ProbeItem]`，每个 `ProbeItem` 带 `name / available / version / detail`。
- 模块级便捷函数 `probe()` 同步到该 Prober 的探测结果。

## 约定

- 探测不抛异常：单个工具失败不影响其它项。
- 每个模块显式声明 `__all__`。
