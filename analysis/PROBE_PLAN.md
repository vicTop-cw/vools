# vools-actus 探针计划 — 环境探测器 (Environment Prober)

> **设计规划文档** (2026-10-16)
> 目标：一装上就知道机器上有哪些可用的工具拿来用
> 状态：调研完成，待评审
> 前置阅读：本仓库 `vools-actus/runtimes.py`、`vools/sys/compile_cmd.py`、`vools/task/core/cli_exec.py`、`vools-actus/ACTUS_SCHEMA_SPEC.md`

---

## 一、调研结论（先回答你的问题）

### 1.1 Python 有没有现成的库？

**没有单一库覆盖全部需求**，但 stdlib + 几个轻量第三方库可以拼出完整探针。

#### stdlib（零依赖，必用）

| 能力 | 库 | 关键 API |
|---|---|---|
| PATH 查找可执行文件 | `shutil` | `shutil.which(name)` |
| OS 平台检测 | `platform` | `platform.system()`, `platform.release()`, `platform.machine()` |
| 子进程版本探测 | `subprocess` | `subprocess.run([cmd, '--version'], capture_output=True)` |
| Python 包已装检测 | `importlib` / `importlib.metadata` | `importlib.metadata.version(pkg)` |
| 文件权限 / 模式 | `os` / `stat` | `os.access()`, `os.stat()`, `stat.S_IMODE()`, `stat.S_IRWXU` |
| 环境变量 | `os` | `os.environ`, `os.getenv(name)` |
| 标准目录路径 | `os.path` | `os.path.expanduser()`, `os.path.expandvars()` |
| 文件类型判断 | `os.path` | `os.path.isfile()`, `os.path.islink()`, `os.path.isdir()` |
| 进程用户 ID | `os` | `os.geteuid()`, `os.getegid()`, `os.getuid()`, `os.getgroups()` |
| 调用原生 API | `ctypes` | `ctypes.windll.shell32.IsUserAnAdmin()` (Windows) |
| 注册表访问 | `winreg` | `winreg.OpenKey()`, `winreg.EnumValue()` (Windows only) |
| Linux 发行版 | `platform` (3.10+) | `platform.freedesktop_os_release()` |

#### 轻量第三方（推荐引入）

| 库 | 用途 | 大小 | 理由 |
|---|---|---|---|
| `psutil` | 系统信息（CPU/内存/磁盘/网络/进程/传感器） | ~250KB | 唯一成熟的跨平台系统信息库；探针用它获取 CPU 核心数、内存总量、磁盘空间、网络接口——这些是动作选择的重要依据 |
| `distro` | Linux 发行版检测 | ~50KB | 替代 Python 3.8 移除的 `platform.linux_distribution()`；返回 `{id, name, version, codename}` |
| `platformdirs` | 跨平台标准目录 | ~30KB | 自动处理 macOS/Windows/Linux 的 data/config/cache/log 目录差异；探针用它确定"该往哪写缓存" |
| `pywin32` | Windows API（管理员检测、注册表、服务） | ~5MB | `win32api.IsUserAdmin()`, `win32security` 组检测；ctypes 可以替代但 pywin32 更完整 |

#### 不需要（过度设计）

| 库 | 为什么不要 |
|---|---|
| `platformdirs` 的替代 `appdirs` | 已停止维护，被 `platformdirs` 取代 |
| `pkg_resources` | 已废弃，用 `importlib.metadata` 替代 |
| `os-release` / `linux_distribution` | Python 3.8 移除 |
| `wmi` | 功能重叠 pywin32，且仅 Windows |
| `setuptools` 的 `entry_points` | 太重，用 `importlib.metadata` 替代 |

**结论**：stdlib 覆盖 70%（工具探测 + 平台 + 权限），加 `psutil`（系统资源）+ `distro`（发行版）+ `platformdirs`（目录）+ `pywin32`（Windows API）覆盖 100%。用户说"加入依赖也没事"，那就引入。

### 1.2 大模型有没有内置能力？

**没有**。现代 LLM（Claude、GPT-4、DeepSeek 等）：
- 有"常识"——知道常见工具名和用途
- 但**无法在运行时探测具体机器上装了什么**
- MCP（Model Context Protocol）能把工具暴露给 LLM，但不负责检测
- 没有标准 API 可以问 LLM "这台机器上有什么"

**结论**：探测必须是本地代码执行，不能用 LLM API 替代。LLM 的角色是**消费探测结果**（"这台机器上有什么，我该推荐什么动作"），不是执行探测。

### 1.3 vools 里已经有什么

| 已有模块 | 位置 | 做了什么 | 缺什么 |
|---|---|---|---|
| `runtimes.py` | `vools-actus/` | 检测 Python/Shell/Node/Go/Rust/Ruby/PHP 运行时 | 没有 CLI 工具、没有编译器、没有系统工具 |
| `compile_cmd.py` | `vools/sys/` | 检测 nim/gcc/cl/g++ 编译器 | 散落在 sys 包，没有统一入口 |
| `cli_exec.py` | `vools/task/core/` | LANGUAGE_DEFAULT_CMD 映射 + find_executable | 只做语言→命令映射，不做系统工具探测 |
| `indexer.py` | `vools-actus/` | 扫描 actions/ 找 .actus.md | 只做动作发现，不检查动作依赖是否满足 |
| `adapter.py` | `vools-actus/` | 有 `discover()` 方法 | 未完全阅读，但应该是动作适配层 |
| `gaps.py` | `vools-actus/AI/` | 能力锚点 + 缺口分析 | 只做语义去重，不做环境探测 |

**缺口汇总**：没有一个统一的"探针"模块把上述散落能力汇总成一个结构化报告。

---

## 二、探针目标

### 2.1 核心问题：装上 vools-actus 后，用户问"这台机器能干什么？"

探针需要回答 **9 类问题**：

1. **平台信息**：OS、版本、架构、位宽、主机名
2. **语言运行时**：有哪些语言解释器？版本？路径？
3. **编译器**：有哪些编译器？版本？路径？
4. **系统 CLI 工具**：有哪些命令行工具可用？路径？
5. **Python 包**：装了哪些与 actus 相关的包？版本？
6. **动作可用性**：`.actus.md` 动作哪些能直接执行？哪些缺依赖？
7. **动作组合**：哪些动作可以串起来做组合工作流？
8. **环境变量**：PATH 有哪些？有无 API key？有无代理配置？有无代理拦截？
9. **权限与身份**：当前用户是谁？是不是管理员/root？能写哪些目录？关键目录的权限如何？

### 2.2 输出：一份结构化 ProbeReport

```python
ProbeReport = {
    # ── 平台 ──
    "platform": {
        "os": "Windows",
        "os_version": "11 Pro",
        "arch": "x64",
        "is_64bit": true,
        "hostname": "DESKTOP-ABC",
        "python_version": "3.13.5",
        "python_executable": "C:\\Python313\\python.exe",
        "python_base": "C:\\Python313",
        "sys_platform": "win32",
        "is_windows": true,
        "is_linux": false,
        "is_macos": false,
        # Windows 特有
        "program_files": "C:\\Program Files",
        "program_files_x86": "C:\\Program Files (x86)",
        "local_app_data": "C:\\Users\\<user>\\AppData\\Local",
        "app_data": "C:\\Users\\<user>\\AppData\\Roaming",
        "program_data": "C:\\ProgramData",
        # Linux 特有
        "linux_distro": {"id": "ubuntu", "name": "Ubuntu", "version": "22.04"},
        # macOS 特有
        "macos_sip_enabled": null,
        # 标准目录（platformdirs）
        "user_data_dir": "...",
        "user_config_dir": "...",
        "user_cache_dir": "...",
    },

    # ── 权限与身份 ──
    "permissions": {
        "user": {
            "name": "<user>",              # 当前用户名
            "uid": 1001,                  # Unix UID（Windows 为 None）
            "gid": 545,                   # Unix GID（Windows 为 None）
            "groups": ["users", "developers"],  # 补充组
        },
        "is_admin": true,                 # 是否管理员/root（核心判断）
        "is_elevated": true,              # 是否已提权（UAC 已同意）
        "elevation_possible": true,       # 能否提权（管理员账号 + UAC 开启）
        "effective_permissions": {        # 关键目录的读写权限
            "home": {"path": "C:\\Users\\<user>", "read": true, "write": true, "exec": true},
            "temp": {"path": "C:\\Users\\<user>\\AppData\\Local\\Temp", "read": true, "write": true, "exec": true},
            "system": {"path": "C:\\Windows\\System32", "read": true, "write": false, "exec": true},
            "program_files": {"path": "C:\\Program Files", "read": true, "write": false, "exec": true},
        },
        "file_acl": {                     # 关键文件的 ACL 摘要（Windows）
            "has_acl": true,
            "inheritance_enabled": true,
        },
        "can_install_system_wide": true,   # 能否系统级安装（管理员或 sudo）
        "can_create_startups": true,       # 能否创建开机自启
        "can_modify_registry": true,       # 能否写注册表（Windows）
    },

    # ── 环境变量 ──
    "environment": {
        "path_dirs": ["C:\\Python313", "C:\\Program Files\\nodejs", ...],
        "path_count": 42,
        "path_resolved": {                # PATH 中找到的可执行文件
            "C:\\Python313\\python.exe": true,
            "C:\\Program Files\\nodejs\\node.exe": true,
        },
        "env_vars": {                     # 关键环境变量（脱敏后）
            "HOME": "C:\\Users\\<user>",
            "USERPROFILE": "C:\\Users\\<user>",
            "APPDATA": "C:\\Users\\<user>\\AppData\\Roaming",
            "TEMP": "C:\\Users\\<user>\\AppData\\Local\\Temp",
            "SYSTEMROOT": "C:\\Windows",
            "PATH": "[REDACTED:42 items]",   # PATH 太长，只记数量
            "HTTPS_PROXY": "http://proxy:8080",  # 如有代理
            "HTTP_PROXY": null,
            "NO_PROXY": null,
        },
        "secret_keys_found": {            # 扫描到的 API key（只记 key 名，不记值）
            "OPENAI_API_KEY": true,
            "ANTHROPIC_API_KEY": false,
            "AWS_ACCESS_KEY_ID": false,
            "GITHUB_TOKEN": true,
        },
        "virtual_env": {                  # 虚拟环境信息
            "active": true,
            "name": "venv",
            "python_path": "C:\\Users\\<user>\\project\\venv\\Scripts\\python.exe",
            "base_python": "C:\\Python313\\python.exe",
        },
        "conda_env": {                    # conda 环境（如有）
            "active": false,
            "name": null,
        },
    },

    # ── 资源（psutil） ──
    "resources": {
        "cpu": {
            "count": 8,
            "physical_count": 8,
            "logical_count": 16,
            "brand": "Intel Core i7-12700",
        },
        "memory": {
            "total_mb": 16384,
            "available_mb": 8192,
            "used_percent": 50.0,
        },
        "disk": {
            "total_gb": 512,
            "free_gb": 256,
            "free_percent": 50.0,
            "mount_points": ["<mount_point>", "<mount_point>"],
        },
        "network": {
            "interfaces": ["WLAN", "Ethernet"],
            "has_network": true,
        },
    },

    # ── 运行时 ──
    "runtimes": [
        {"name": "python", "path": "C:\\Python313\\python.exe", "version": "3.13.5", "available": true},
        {"name": "node", "path": "C:\\Program Files\\nodejs\\node.exe", "version": "20.11.0", "available": true},
        {"name": "go", "path": "C:\\Program Files\\Go\\bin\\go.exe", "version": "1.22.5", "available": true},
        {"name": "rustc", "path": None, "version": None, "available": false},
        ...
    ],

    # ── 编译器 ──
    "compilers": [
        {"name": "gcc", "path": None, "version": None, "available": false},
        {"name": "cl", "path": "C:\\Program Files\\Microsoft Visual Studio\\...\\cl.exe", "version": "19.41", "available": true},
        ...
    ],

    # ── 系统工具 ──
    "system_tools": [
        {"name": "git", "path": "C:\\Program Files\\Git\\cmd\\git.exe", "version": "2.43.0", "available": true},
        {"name": "ffmpeg", "path": "C:\\ffmpeg\\bin\\ffmpeg.exe", "version": "6.0", "available": true},
        {"name": "docker", "path": None, "version": None, "available": false},
        ...
    ],

    # ── Python 包 ──
    "python_packages": [
        {"name": "markitdown", "version": "0.1.0", "installed": true},
        {"name": "openai", "version": None, "installed": false},
        ...
    ],

    # ── 动作 ──
    "actions": {
        "total": 109,
        "ready": 45,
        "blocked": 30,
        "missing_deps": {
            "actus.generate.screen-record": ["ffmpeg"],
            "actus.ocr.text-extract": ["pytesseract", "tesseract"],
        }
    },

    # ── 组合 ──
    "combinations": [
        {"workflow": "文档转换+截图", "actions": ["convert-to-markdown", "screenshot"], "all_ready": true},
        ...
    ],

    "probed_at": "2026-10-16T15:18:00+08:00",
}
```

---

## 三、架构设计

### 3.1 分层

```
┌──────────────────────────────────────────────────────────────────┐
│  vools.actus.probe.report            — ProbeReport 组装          │
├──────────────────────────────────────────────────────────────────┤
│  vools.actus.probe.permissions       — 权限与身份探测 ★新增       │
│  vools.actus.probe.environment       — 环境变量探测 ★新增         │
│  vools.actus.probe.resources         — 系统资源探测（psutil） ★新增│
│  vools.actus.probe.runtimes          — 语言运行时探测             │
│  vools.actus.probe.compilers         — 编译器探测                 │
│  vools.actus.probe.system_tools      — 系统 CLI 工具探测          │
│  vools.actus.probe.python_pkgs       — Python 包探测              │
│  vools.actus.probe.actions           — 动作依赖分析               │
│  vools.actus.probe.platform          — 平台信息采集               │
├──────────────────────────────────────────────────────────────────┤
│  vools.actus.probe.cache             — 探测结果缓存               │
├──────────────────────────────────────────────────────────────────┤
│  vools.actus.probe.base              — 探测基类 + 注册表          │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 目录结构

```
vools-actus/
└── vools/
    └── actus/
        └── probe/
            ├── __init__.py           # probe() 入口函数
            ├── base.py               # ProbeResult 基类 + 注册表
            ├── platform.py           # 平台信息采集
            ├── permissions.py        # 权限与身份探测 ★新增
            ├── environment.py        # 环境变量探测 ★新增
            ├── resources.py          # 系统资源探测（psutil） ★新增
            ├── runtimes.py           # 语言运行时探测（复用 runtimes.py 的 is_available）
            ├── compilers.py          # 编译器探测（复用 compile_cmd.py 的逻辑）
            ├── system_tools.py       # 系统 CLI 工具探测
            ├── python_pkgs.py        # Python 包探测
            ├── actions.py            # 动作依赖分析
            ├── report.py             # ProbeReport 组装
            ├── cache.py              # 探测结果缓存（24h TTL）
            └── TOOL_TABLE.py         # 已知工具表（数据资产）
```

### 3.3 探测基类

```python
# vools/actus/probe/base.py

class ProbeItem(object):
    """探测项基类。"""
    
    def __init__(self, name, aliases=None, version_cmd=None, well_known_paths=None):
        self.name = name
        self.aliases = aliases or []
        self.version_cmd = version_cmd or [self.name, '--version']
        self.well_known_paths = well_known_paths or []
    
    def probe(self):
        """执行探测，返回 dict。"""
        # 1. shutil.which(name) 搜索 PATH
        # 2. 如果没找到，搜索 well_known_paths
        # 3. 找到后，用 version_cmd 探测版本号
        # 4. 返回 {name, path, version, available}
        ...

class Prober(object):
    """探测器基类。"""
    
    def __init__(self, timeout=5):
        self.timeout = timeout
        self._items = []
    
    def add_item(self, item):
        self._items.append(item)
    
    def run(self):
        """执行所有探测项，返回结果列表。"""
        results = []
        for item in self._items:
            try:
                result = item.probe()
                results.append(result)
            except Exception as e:
                results.append({
                    "name": item.name,
                    "path": None,
                    "version": None,
                    "available": False,
                    "error": str(e)
                })
        return results
```

### 3.4 已知工具表（TOOL_TABLE.py）

```python
# vools/actus/probe/TOOL_TABLE.py

"""已知工具表：可探测的系统工具清单。

这是探针的**数据资产**——不是探测逻辑，而是"我们要探测哪些东西"。
新增工具只需往这个表里加一行。
"""

# (name, aliases, version_cmd, well_known_paths_by_platform)
KNOWN_TOOLS = [
    # ── 语言运行时 ──
    ("python", ["py", "python3"], ["--version"], {}),
    ("node", ["nodejs"], ["--version"], {}),
    ("go", [], ["version"], {}),
    ("rustc", ["cargo"], ["--version"], {}),
    ("ruby", [], ["--version"], {}),
    ("php", [], ["--version"], {}),
    ("perl", [], ["--version"], {}),
    ("swift", [], ["--version"], {}),
    
    # ── 编译器 ──
    ("gcc", ["cc"], ["--version"], {}),
    ("g++", ["c++"], ["--version"], {}),
    ("cl", ["msvc"], ["??"], {
        "Windows": [r"C:\Program Files\Microsoft Visual Studio\*\*\*\*\*\*",
                     r"C:\Program Files (x86)\Microsoft Visual Studio\*\*\*\*\*\*"]
    }),
    ("clang", [], ["--version"], {}),
    ("nim", [], ["--version"], {}),
    ("zig", [], ["version"], {}),
    ("rustc", ["cargo"], ["--version"], {}),
    
    # ── 版本控制 ──
    ("git", [], ["--version"], {}),
    ("svn", [], ["--version"], {}),
    
    # ── 容器/虚拟化 ──
    ("docker", ["docker-compose"], ["--version"], {}),
    ("podman", [], ["--version"], {}),
    ("kubectl", ["k", "helm"], ["version"], {}),
    
    # ── 文件传输 ──
    ("sftp", ["scp", "rsync", "rsync"], ["--version"], {}),
    ("ssh", ["ssh-keygen", "ssh-copy-id"], ["-V"], {}),
    ("curl", ["wget", "aria2c", "aria2"], ["--version"], {}),
    
    # ── 文本处理 ──
    ("jq", [], ["--version"], {}),
    ("yq", [], ["--version"], {}),
    ("pandoc", [], ["--version"], {}),
    ("sed", [], ["--version"], {}),
    ("grep", [], ["--version"], {}),
    
    # ── 图像/多媒体 ──
    ("ffmpeg", ["ffprobe"], ["-version"], {}),
    ("convert", ["magick", "identify"], ["--version"], {}),  # ImageMagick
    ("tesseract", [], ["--version"], {}),
    ("inkscape", [], ["--version"], {}),
    
    # ── 数据库 ──
    ("psql", [], ["--version"], {}),
    ("mysql", [], ["--version"], {}),
    ("sqlite3", [], ["--version"], {}),
    ("mongosh", [], ["--version"], {}),
    ("redis-cli", [], ["--version"], {}),
    
    # ── 脚本/工具 ──
    ("bash", ["sh", "zsh", "fish"], ["--version"], {}),
    ("powershell", ["pwsh", "powershell.exe"], ["-Version"], {}),
    ("make", ["ninja", "cmake"], ["--version"], {}),
    ("go", [], ["version"], {}),
    ("cargo", [], ["--version"], {}),
    ("npm", ["npx", "yarn", "pnpm"], ["--version"], {}),
    ("pip", ["pip3", "pipenv", "poetry"], ["--version"], {}),
    
    # ── AI/ML ──
    ("ollama", [], ["--version"], {}),
    ("whisper", [], ["--help"], {}),  # openai-whisper CLI
    ("claude", [], [], {}),            # Claude Code CLI
    ("codex", [], [], {}),             # OpenAI Codex CLI
]
```

---

## 四、探测逻辑细节

### 4.1 探测一个工具的流程

```python
def probe_tool(name, aliases, version_cmd, well_known_paths, timeout=5):
    """探测一个工具，返回 {name, path, version, available}。"""
    
    # Step 1: shutil.which — PATH 搜索
    for cmd in [name] + aliases:
        found = shutil.which(cmd)
        if found:
            return _get_version(found, version_cmd, timeout)
    
    # Step 2: 平台特定路径搜索（well-known paths）
    platform = sys.platform  # win32 / linux / darwin
    for pattern in well_known_paths.get(platform, []):
        for path in glob.glob(pattern):
            exe = os.path.join(path, name + (".exe" if platform == "win32" else ""))
            if os.path.isfile(exe) and os.access(exe, os.X_OK):
                return _get_version(exe, version_cmd, timeout)
    
    # Step 3: 没找到
    return {"name": name, "path": None, "version": None, "available": False}


def _get_version(path, version_cmd, timeout=5):
    """探测版本号。"""
    try:
        cmd = [path] + version_cmd
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        version = result.stdout.strip().split('\n')[0]
        return {"path": path, "version": version, "available": True}
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return {"path": path, "version": None, "available": True}  # 找到但版本探测失败
```

### 4.2 平台特定逻辑

```python
# vools/actus/probe/platform.py

def get_platform_info():
    """采集平台信息。"""
    info = {
        "os": platform.system(),          # Windows / Linux / Darwin
        "os_release": platform.release(), # 11 / 22.04 / 14.5
        "arch": platform.machine(),       # AMD64 / x86_64 / arm64
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform_tag": sys.platform,      # win32 / linux / darwin
        "is_windows": sys.platform == "win32",
        "is_linux": sys.platform == "linux",
        "is_macos": sys.platform == "darwin",
    }
    
    # Windows 特有：版本号 + 系统根路径
    if info["is_windows"]:
        info["windows_version"] = _get_windows_version()
        info["program_files"] = os.environ.get("ProgramFiles", "")
        info["program_files_x86"] = os.environ.get("ProgramFiles(x86)", "")
        info["local_app_data"] = os.environ.get("LOCALAPPDATA", "")
        info["app_data"] = os.environ.get("APPDATA", "")
        info["program_data"] = os.environ.get("ProgramData", "")
    
    # Linux 特有：发行版
    if info["is_linux"]:
        info["linux_distro"] = _get_linux_distro()
    
    # macOS 特有：SIP 状态
    if info["is_macos"]:
        info["sip_enabled"] = _get_sip_status()
    
    # PATH 目录列表
    info["path_dirs"] = os.environ.get("PATH", "").split(os.pathsep)
    
    return info
```

### 4.3 权限与身份探测 ★新增

```python
# vools/actus/probe/permissions.py

"""权限与身份探测。

核心问题：当前用户是谁？权限有多大？能做什么？不能做什么？

跨平台 API 汇总：
  Windows:
    - ctypes.windll.shell32.IsUserAnAdmin() → 是否管理员
    - ctypes.windll.shell32.IsUserMember() → 组检测
    - win32api.IsUserAdmin() (pywin32)
    - win32security.LookupAccountName() → 用户名
    - win32security.GetTokenGroups() → 安全组
    - os.access(path, os.W_OK) → 文件级写权限
  Linux/macOS:
    - os.geteuid() / os.getegid() → 有效 UID/GID
    - os.getuid() / os.getgid() → 真实 UID/GID
    - os.getgroups() → 补充组
    - pwd.getpwuid() / grp.getgrgid() → 用户名/组名
    - os.access(path, os.R_OK/W_OK/X_OK) → 文件级权限
    - stat.S_IMODE() → 权限位
    - stat.S_ISUID / S_ISGID → setuid/setgid
    - stat.S_ISVTX → sticky bit
"""

def get_permissions_info():
    """探测当前用户的权限信息。"""
    info = {"user": {}, "is_admin": False, "is_elevated": False,
            "elevation_possible": False, "effective_permissions": {},
            "can_install_system_wide": False, "can_create_startups": False}

    # ── 用户身份 ──
    try:
        import pwd
        user_name = pwd.getpwuid(os.geteuid()).pw_name
    except (ImportError, KeyError):
        # Windows: 用环境变量
        user_name = os.environ.get("USERNAME", os.environ.get("USER", "unknown"))

    info["user"]["name"] = user_name
    info["user"]["uid"] = os.geteuid() if hasattr(os, "geteuid") else None
    info["user"]["gid"] = os.getegid() if hasattr(os, "getegid") else None

    # ── 补充组（Unix only） ──
    if hasattr(os, "getgroups"):
        group_names = []
        for gid in os.getgroups():
            try:
                import grp
                group_names.append(grp.getgrgid(gid).gr_name)
            except Exception:
                pass
        info["user"]["groups"] = group_names

    # ── 管理员/root 检测 ──
    if sys.platform == "win32":
        info["is_admin"] = _check_windows_admin()
        info["is_elevated"] = info["is_admin"]  # Windows 管理员即提权
        info["can_install_system_wide"] = info["is_admin"]
        info["can_create_startups"] = info["is_admin"] or os.access(_get_windows_startup_dir(), os.W_OK)
    else:
        # Unix: root = uid 0
        euid = os.geteuid()
        info["is_admin"] = (euid == 0)
        info["is_elevated"] = (euid == 0)
        # sudo 检测：检查 sudoers 文件是否可读
        info["elevation_possible"] = os.access("/etc/sudoers", os.R_OK) or (euid == 0)
        info["can_install_system_wide"] = (euid == 0) or info["elevation_possible"]
        info["can_create_startups"] = os.access(os.path.expanduser("~/.config/autostart"), os.W_OK) or (euid == 0)

    # ── 关键目录权限 ──
    info["effective_permissions"] = {
        "home": _check_dir_permissions(os.path.expanduser("~")),
        "temp": _check_dir_permissions(os.environ.get("TEMP", os.environ.get("TMP", "/tmp"))),
        "system": _check_dir_permissions(
            os.environ.get("SYSTEMROOT", "C:\\Windows") if sys.platform == "win32" else "/usr"
        ),
        "program_files": _check_dir_permissions(
            os.environ.get("ProgramFiles", "C:\\Program Files") if sys.platform == "win32" else "/usr/local"
        ),
    }

    return info


def _check_windows_admin():
    """Windows 管理员检测（ctypes，零依赖）。"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        # 回退：检查环境变量
        return bool(os.environ.get("USERNAME")) and "All Users" in os.environ.get("ProgramData", "")


def _check_dir_permissions(path):
    """检查目录的读写执行权限。"""
    if not os.path.exists(path):
        return {"path": path, "exists": False}
    return {
        "path": path,
        "exists": True,
        "read": os.access(path, os.R_OK),
        "write": os.access(path, os.W_OK),
        "exec": os.access(path, os.X_OK),
    }


def _get_windows_startup_dir():
    """Windows 开机自启目录。"""
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
```

### 4.4 环境变量探测 ★新增

```python
# vools/actus/probe/environment.py

"""环境变量探测。

核心问题：环境里有什么？API key 有没有？代理配置是什么？虚拟环境激活了吗？

安全考虑：
  - 不记录敏感值（API key、token、password）——只记录 key 名是否存在
  - PATH 太长时只记数量和解析后的可执行文件列表
  - 不暴露完整的注册表内容
"""

import re

# 敏感 key 模式（只记 key 名，不记值）
SENSITIVE_PATTERNS = [
    r'API_KEY', r'TOKEN', r'SECRET', r'PASSWORD', r'PASSWD',
    r'PRIVATE_KEY', r'CREDENTIAL', r'AUTH', r'BASIC_AUTH',
]

# 关键环境变量白名单（始终采集）
CRITICAL_VARS = [
    'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP',
    'SYSTEMROOT', 'SystemRoot', 'ProgramFiles', 'ProgramFiles(x86)',
    'ProgramData', 'PATH', 'PATHEXT',
    'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY',
    'http_proxy', 'https_proxy', 'no_proxy',
    'VIRTUAL_ENV', 'CONDA_PREFIX', 'CONDA_DEFAULT_ENV',
    'PYTHONPATH', 'PYTHONHOME', 'PYTHONUNBUFFERED',
    'LANG', 'LC_ALL', 'LC_CTYPE',
    'DISPLAY', 'TERM',
]

def get_environment_info():
    """探测环境变量信息。"""
    info = {}

    # ── PATH 分析 ──
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    info["path_dirs"] = path_dirs
    info["path_count"] = len(path_dirs)
    info["path_resolved"] = {}
    for d in path_dirs:
        if os.path.isdir(d):
            try:
                files = os.listdir(d)
                for f in files:
                    if os.access(os.path.join(d, f), os.X_OK):
                        info["path_resolved"][os.path.join(d, f)] = True
            except (OSError, PermissionError):
                pass

    # ── 关键环境变量 ──
    info["env_vars"] = {}
    for var in CRITICAL_VARS:
        val = os.environ.get(var)
        if val is not None:
            if var == "PATH":
                info["env_vars"][var] = "[REDACTED:%d items]" % len(path_dirs)
            else:
                info["env_vars"][var] = val

    # ── 敏感 key 扫描 ──
    info["secret_keys_found"] = {}
    for key in os.environ:
        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, key, re.IGNORECASE):
                info["secret_keys_found"][key] = True
                break

    # ── 虚拟环境检测 ──
    info["virtual_env"] = _detect_virtual_env()

    # ── conda 环境检测 ──
    info["conda_env"] = _detect_conda_env()

    return info


def _detect_virtual_env():
    """检测虚拟环境（venv/virtualenv）。"""
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        return {
            "active": True,
            "path": venv,
            "python_path": os.path.join(venv, "Scripts" if sys.platform == "win32" else "bin", "python"),
        }
    # 检查 sys.prefix != sys.base_prefix（Python 3.3+ 的 venv 检测方式）
    if hasattr(sys, "base_prefix") and sys.prefix != sys.base_prefix:
        return {
            "active": True,
            "path": sys.prefix,
            "python_path": sys.executable,
        }
    return {"active": False}


def _detect_conda_env():
    """检测 conda 环境。"""
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        return {
            "active": True,
            "name": os.environ.get("CONDA_DEFAULT_ENV", os.path.basename(conda_prefix)),
            "path": conda_prefix,
        }
    return {"active": False}
```

### 4.5 系统资源探测 ★新增（psutil）

```python
# vools/actus/probe/resources.py

"""系统资源探测（psutil）。

核心问题：机器性能怎么样？内存够不够？磁盘满没满？网络通不通？

为什么需要：动作选择依据——如果内存只有 2GB，就不推荐需要 4GB 的大模型推理动作；
如果磁盘只剩 10GB，就不推荐需要 50GB 的 Docker 镜像拉取动作。
"""

def get_resources_info():
    """探测系统资源（psutil 可选）。"""
    info = {}

    try:
        import psutil
        info["_psutil_available"] = True

        # ── CPU ──
        info["cpu"] = {
            "count": psutil.cpu_count(),              # 逻辑核心数
            "physical_count": psutil.cpu_count(logical=False),  # 物理核心数
            "logical_count": psutil.cpu_count(logical=True),    # 逻辑核心数
            "brand": _get_cpu_brand(),
        }

        # ── 内存 ──
        vm = psutil.virtual_memory()
        info["memory"] = {
            "total_mb": vm.total // (1024 * 1024),
            "available_mb": vm.available // (1024 * 1024),
            "used_percent": round(vm.percent, 1),
        }

        # ── 磁盘 ──
        disk = psutil.disk_usage("/")
        info["disk"] = {
            "total_gb": disk.total // (1024 ** 3),
            "free_gb": disk.free // (1024 ** 3),
            "free_percent": round(disk.percent, 1),
            "mount_points": _get_mount_points(),
        }

        # ── 网络 ──
        net_ifs = list(psutil.net_if_list())
        info["network"] = {
            "interfaces": net_ifs,
            "has_network": len(net_ifs) > 0,
        }

    except ImportError:
        info["_psutil_available"] = False
        info["_psutil_hint"] = "pip install psutil 以获取 CPU/内存/磁盘/网络信息"
        # 用 stdlib 获取基本信息
        info["cpu"] = {"count": os.cpu_count()}

    return info


def _get_cpu_brand():
    """获取 CPU 品牌（跨平台）。"""
    if sys.platform == "win32":
        try:
            import subprocess
            r = subprocess.run(["wmic", "cpu", "get", "name"], capture_output=True, text=True, timeout=5)
            lines = r.stdout.strip().split("\n")
            return lines[1].strip() if len(lines) > 1 else None
        except Exception:
            return None
    else:
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line or "Hardware" in line or "CPU implementer" in line:
                        return line.split(":", 1)[1].strip()
            return None
        except Exception:
            return None


def _get_mount_points():
    """获取磁盘挂载点。"""
    try:
        import platformdirs
        # 简单方案：列出常见挂载点
        mounts = []
        if sys.platform == "win32":
            import string
            import os
            for drive in string.ascii_uppercase:
                root = drive + ":\\"
                if os.path.exists(root):
                    mounts.append(root)
        else:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] not in mounts:
                        mounts.append(parts[1])
        return mounts
    except Exception:
        return []
```

### 4.6 Python 包探测

```python
# vools/actus/probe/python_pkgs.py

# 与 actus 动作相关的 Python 包清单
RELEVANT_PACKAGES = [
    # 文件转换
    "markitdown", "pymupdf", "pytesseract", "pillow",
    # HTTP
    "requests", "httpx", "aiohttp",
    # 数据处理
    "pandas", "numpy", "openpyxl", "xlrd",
    # 数据库
    "psycopg2", "sqlite3", "sqlalchemy",
    # SFTP
    "paramiko",
    # 加密
    "cryptography",
    # AI/ML
    "openai", "anthropic", "transformers", "torch",
    # 浏览器自动化
    "selenium", "playwright",
    # 其他
    "pyyaml", "jinja2", "rich", "typer", "click",
]

def probe_python_packages():
    """探测已安装的 Python 包。"""
    results = []
    for pkg in RELEVANT_PACKAGES:
        try:
            # 尝试导入
            __import__(pkg.replace("-", "_"))
            # 获取版本号
            version = _get_pkg_version(pkg)
            results.append({"name": pkg, "version": version, "installed": True})
        except ImportError:
            results.append({"name": pkg, "version": None, "installed": False})
    return results

def _get_pkg_version(pkg):
    """获取包版本（跨 Python 版本兼容）。"""
    # Python 3.8+ 用 importlib.metadata
    try:
        from importlib.metadata import version
        return version(pkg)
    except Exception:
        pass
    # 回退到 pkg_resources
    try:
        import pkg_resources
        return pkg_resources.get_distribution(pkg).version
    except Exception:
        return None
```

### 4.7 动作依赖分析

> **✅ 实现现状（2026-10-28 核验：本设计已真正落地，实现比下面的草图严格得多）**
>
> 下面这段是**最初的设计草图**（保留，作为「原来打算怎么做」的存档）。
> 真实实现由 `actus/vools/actus/probe/actions.py` 提供（782 行，`analyze_actions` 在 `:520`），
> 签名与返回结构如下 —— **签名有默认值，且比草图多出 9 个信号字段**：
>
> ```python
> # actus/vools/actus/probe/actions.py  ← 实际签名（与草图的差异：两个参数都可省）
> def analyze_actions(actions_dir: str = None, probe_report=None) -> dict:
>     """分析动作的依赖满足情况（PROBE_PLAN.md §4.7）。
>
>     actions_dir  : 为空时扫 indexer 的全部动作根（用户项目 + 包内种子）
>     probe_report : 收 ProbeReport / to_dict() 的 dict / 条目列表 / 计划形态
>                    {"runtimes": [...], ...}；为空时用本地原语兜底判定
>     """
> ```
>
> | 返回键 | 含义 |
> |---|---|
> | `total` / `ready` / `blocked` / `missing_deps` | **§4.7 契约四件套**（草图只定了这 4 个） |
> | `verdicts` | `{action_id: {verdict, deps, missing_deps, blocked_reasons, deps_declared, path, parse_error}}` —— 逐动作判定 + **原因链** |
> | `undeclared` | 声明里没有 `deps` 的动作（**显式信号**，不静默算 ready） |
> | `parse_failed` | 连文件都解析不了的动作 |
> | `unverifiable` | 报告无法判定的依赖（如 `npm:` / `mcp:` 类型） |
> | `duplicate_ids` | `[{id, kept, ignored}]` 同 id 多份文件 |
> | `index_source` | `probe_report` \| `self-probe` —— **如实标出这次用的是哪种能力来源** |
> | `exists` / `roots` / `actions_dir` / `elapsed_ms` | 扫描面与耗时 |
>
> **判定纪律（实现里的硬约束，草图没写）**：
> ① **探测不到 = blocked**；② 报告无法判定的依赖类型同样 blocked；
> ③ deps 缺失 / 类型错误 / 文件解析失败 / 依赖成环**各有独立信号**，绝不静默默认 ready；
> ④ **以报告为权威**：`_capabilities_from_report()` 在报告可用时**只认报告**
> （`actions.py:252-275`），**不会**因为本机装了某个工具就回退自查 ——
> 报告说 git 不可用，动作就是 blocked。
>
> **接进报告**：`ActionsProber.probe()` 在既有 `actions` / `action_dependencies`
> **之后追加第 3 个条目 `action_readiness`**（`actions.py:776`，设计注释见 `:725`），
> 于是 `probe()` 的报告里**终于有 ready/blocked 字段** —— items 从 172 增至 **173**
> （本轮实跑核验 `len(report.items)==173`）。既有两个条目的形状一个字段都没改
> （`intent.py` 与 `tests/test_probe_actions.py` 依赖它们）。
>
> **真实数据（2026-10-28 在本仓实跑，非构造数据）**：
> `analyze_actions()` → **`total=14 ready=14 blocked=0`**，`undeclared=8`、`parse_failed=0`、
> `index_source=self-probe`。→ **0 blocked 是正确结果**：真实动作里没有任何一个声明了
> 非空 deps，8 个种子动作未声明 deps 被如实计入 `undeclared`，没有凑数。
>
> ⚠️ **测试覆盖的实话**：`tests/test_probe_actions.py`（387 行 / 12 用例）覆盖的是
> `ActionsProber` 的条目形状与 `intent.py` 的 ready/blocked **粗判定**
> （该文件 `:319-321` 的注释仍写着「现产品的 blocked 判据就是**报告里没有它**」）；
> `analyze_actions` 的 `verdicts` / `blocked_reasons` / `undeclared` / `unverifiable` /
> `duplicate_ids` **细粒度分支目前没有专项单测**（`grep` 全 `actus/tests/` 零命中）。
> 这部分靠 fixture 手工验证，**建议补测**（已列入 §9 剩余工作）。
>
> **两个已知缺口（进行中 —— 代码已开始落地但本轮不判完成，见 §9）**：
> 1. **`runtime:` 依赖前缀进 resolver**：原状是 `actus/vools/actus/dependency.py` 的
>    `_parse_dep_string` **没有该分支**（docstring 只列 `builtin/system/pip/npm/mcp/action/cs_*`），
>    裸串 fallthrough 成 action 依赖 → 名为 `runtime:python` 的动作**永远 blocked**。
>    本轮核验（2026-10-28 09:0x）：**分支已在工作区落地** ——
>    `_DepKind.RUNTIME = "runtime"`（`:42`）、`elif dep_str.startswith("runtime:")`（`:189`），
>    并带一张「抽象名 → 可执行文件候选」展开表（`runtime:shell` → bash/sh…，`runtime:rust` → rustc/cargo）。
>    ⚠️ **但仍算进行中**：`grep -rn "runtime:" actus/tests/` **零命中** —— 该解析分支**尚无单测**，
>    本轮未验收。
> 2. **`intent.py` 的 ready 判据接 `verdicts`**：原状是粗粒度「动作在报告里 = ready」。
>    本轮核验：**已加第二道门** —— `_extract_blocked_ids()`（`intent.py:114-135`）从报告的
>    `action_readiness.extra.verdicts` 提取**显式 `verdict == "blocked"`** 的 id，
>    `_is_ready()`（`:137`）变成两道门：①在 `_ready_ids` 里；②不在 `_blocked_ids` 里。
>    取不到 / 结构异常 / 旧报告 → `None` → **只看第 1 道门，行为与升级前一致**（零回归）。
>    并新增专项测试 `actus/tests/test_action_readiness_intent.py`（329 行 / **9 用例，实测全过**）。
>    ⚠️ **仍算进行中**：本轮未验收，故不写「已完成」。

```python
# vools/actus/probe/actions.py —— 以下是**最初的设计草图**（实现见上方表格）

def analyze_actions(actions_dir, probe_report):
    """分析 .actus.md 动作的依赖满足情况。"""
    
    # 1. 扫描所有动作
    from vools.actus.indexer import scan_actions
    actions = scan_actions(actions_dir)
    
    # 2. 检查每个动作的依赖
    results = {"total": len(actions), "ready": 0, "blocked": 0, "missing_deps": {}}
    
    for action_id, action in actions.items():
        deps = action.meta.get("deps", [])
        missing = _check_deps(deps, probe_report)
        if missing:
            results["blocked"] += 1
            results["missing_deps"][action_id] = missing
        else:
            results["ready"] += 1
    
    return results

def _check_deps(deps, probe_report):
    """检查动作依赖是否满足。"""
    missing = []
    available_runtimes = {r["name"] for r in probe_report["runtimes"] if r["available"]}
    available_tools = {t["name"] for t in probe_report["system_tools"] if t["available"]}
    available_pkgs = {p["name"] for p in probe_report["python_packages"] if p["installed"]}
    
    for dep in deps:
        # dep 格式: "runtime:python", "system:git", "pip:markitdown"
        kind, name = dep.split(":", 1)
        if kind == "runtime" and name not in available_runtimes:
            missing.append(dep)
        elif kind == "system" and name not in available_tools:
            missing.append(dep)
        elif kind == "pip" and name not in available_pkgs:
            missing.append(dep)
    
    return missing
```

### 4.8 探测结果缓存

```python
# vools/actus/probe/cache.py

"""探测结果缓存：避免每次启动都重新探测。

缓存策略：
- 文件位置：{data_dir}/_meta/probe.cache.json
- 过期时间：24 小时（可配置）
- 强制刷新：probe(force=True) 忽略缓存
- 增量探测：只重新探测标记为 changed 的项
"""

CACHE_TTL_SECONDS = 86400  # 24 小时

def should_refresh(cache_path):
    """检查缓存是否需要刷新。"""
    if not os.path.exists(cache_path):
        return True
    age = time.time() - os.path.getmtime(cache_path)
    return age > CACHE_TTL_SECONDS

def load_cache(cache_path):
    """加载缓存。"""
    if should_refresh(cache_path):
        return None
    with open(cache_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cache(cache_path, report):
    """保存缓存。"""
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
```

---

## 五、入口函数

```python
# vools/actus/probe/__init__.py

def probe(*, actions_dir=None, cache_dir=None, force=False, timeout=5):
    """一键探测当前环境，返回 ProbeReport。

    用法:
        from vools.actus.probe import probe
        report = probe()
        print(report["platform"])
        print(report["runtimes"])
        
        # 只看可用动作
        ready_actions = [a for a in report["actions"] if a["ready"]]
        
    参数:
        actions_dir: 动作目录（默认 vools-actus/actions/）
        cache_dir: 缓存目录（默认 vools-actus/_meta/）
        force: True 时忽略缓存
        timeout: 单个探测项超时秒数

    返回:
        dict: ProbeReport
    """
    # 1. 检查缓存
    cache_path = os.path.join(cache_dir or _default_cache_dir(), "probe.cache.json")
    if not force:
        cached = load_cache(cache_path)
        if cached:
            return cached
    
    # 2. 采集平台信息
    platform_info = get_platform_info()
    
    # 3. 权限与身份探测 ★新增
    permissions = get_permissions_info()
    
    # 4. 环境变量探测 ★新增
    environment = get_environment_info()
    
    # 5. 系统资源探测 ★新增（psutil）
    resources = get_resources_info()
    
    # 6. 探测运行时（复用 runtimes.py）
    runtimes = probe_runtimes(timeout)
    
    # 7. 探测编译器（复用 compile_cmd.py 逻辑）
    compilers = probe_compilers(timeout)
    
    # 8. 探测系统工具
    system_tools = probe_system_tools(timeout)
    
    # 9. 探测 Python 包
    python_pkgs = probe_python_packages()
    
    # 10. 分析动作依赖
    actions = analyze_actions(actions_dir or _default_actions_dir(), {
        "runtimes": runtimes,
        "system_tools": system_tools,
        "python_packages": python_pkgs,
    })
    
    # 11. 组装报告
    report = {
        "platform": platform_info,
        "permissions": permissions,
        "environment": environment,
        "resources": resources,
        "runtimes": runtimes,
        "compilers": compilers,
        "system_tools": system_tools,
        "python_packages": python_pkgs,
        "actions": actions,
        "probed_at": _now_iso(),
    }
    
    # 12. 保存缓存
    save_cache(cache_path, report)
    
    return report
```

---

## 六、平台特定判断

### 6.1 Windows 特有逻辑

```python
# Windows 特有探测
def probe_windows_specific():
    """Windows 特有探测项。"""
    extras = {}
    
    # Visual Studio Build Tools
    vs_paths = glob.glob(r"C:\Program Files\Microsoft Visual Studio\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*")
    extras["visual_studio"] = bool(vs_paths)
    
    # Windows Terminal
    wt = shutil.which("wt.exe")
    extras["windows_terminal"] = wt is not None
    
    # WSL
    try:
        result = subprocess.run(["wsl", "--list"], capture_output=True, text=True, timeout=5)
        extras["wsl"] = result.returncode == 0
        extras["wsl_distro"] = result.stdout.strip()
    except Exception:
        extras["wsl"] = False
    
    # Python 安装位置
    extras["python_base"] = sys.base_prefix
    
    return extras
```

### 6.2 Linux 特有逻辑

```python
# Linux 特有探测
def probe_linux_specific():
    """Linux 特有探测项。"""
    extras = {}
    
    # 发行版
    try:
        import distro
        extras["distro_name"] = distro.name()
        extras["distro_version"] = distro.version()
        extras["distro_id"] = distro.id()
    except ImportError:
        pass
    
    # 包管理器
    for pm in ["apt", "dnf", "pacman", "zypper", "emerge"]:
        extras["pkg_manager_%s" % pm] = shutil.which(pm) is not None
    
    # systemd
    extras["systemd"] = shutil.which("systemctl") is not None
    
    # Flatpak / Snap
    extras["flatpak"] = shutil.which("flatpak") is not None
    extras["snap"] = shutil.which("snap") is not None
    
    return extras
```

### 6.3 macOS 特有逻辑

```python
# macOS 特有探测
def probe_macos_specific():
    """macOS 特有探测项。"""
    extras = {}
    
    # SIP 状态
    try:
        result = subprocess.run(["csrutil", "status"], capture_output=True, text=True, timeout=5)
        extras["sip_enabled"] = "enabled" in result.stdout.lower()
    except Exception:
        pass
    
    # Homebrew
    extras["homebrew"] = shutil.which("brew") is not None
    if extras["homebrew"]:
        try:
            result = subprocess.run(["brew", "--version"], capture_output=True, text=True, timeout=5)
            extras["homebrew_version"] = result.stdout.strip().split('\n')[0]
        except Exception:
            pass
    
    # Xcode Command Line Tools
    try:
        result = subprocess.run(["xcode-select", "--version"], capture_output=True, text=True, timeout=5)
        extras["xcode_clt"] = result.returncode == 0
    except Exception:
        extras["xcode_clt"] = False
    
    return extras
```

---

## 七、复用现有模块

### 7.1 复用 `runtimes.py`

```python
# 不重新实现，直接复用
from vools.actus.runtimes import get_available_runtimes

def probe_runtimes(timeout=5):
    """探测可用运行时（复用 runtimes.py）。"""
    available = get_available_runtimes()  # ['python', 'shell', 'node', ...]
    # 补充路径和版本信息
    results = []
    for name in available:
        path = shutil.which(name)
        version = _get_version(path, [name, '--version'], timeout) if path else None
        results.append({"name": name, "path": path, "version": version, "available": True})
    
    # 补充不可用的运行时
    all_runtimes = ["python", "shell", "node", "go", "rust", "ruby", "php"]
    for name in all_runtimes:
        if name not in available:
            results.append({"name": name, "path": None, "version": None, "available": False})
    
    return results
```

### 7.2 复用 `compile_cmd.py`

```python
# 不重新实现编译器探测，复用逻辑
def probe_compilers(timeout=5):
    """探测编译器（复用 compile_cmd.py 的逻辑）。"""
    compilers = [
        ("gcc", ["--version"]),
        ("g++", ["--version"]),
        ("cl", ["??"]),
        ("clang", ["--version"]),
        ("nim", ["--version"]),
        ("zig", ["version"]),
        ("rustc", ["--version"]),
    ]
    results = []
    for name, cmd_args in compilers:
        path = shutil.which(name)
        if path:
            version = _get_version(path, cmd_args, timeout)
            results.append({"name": name, "path": path, "version": version, "available": True})
        else:
            results.append({"name": name, "path": None, "version": None, "available": False})
    return results
```

### 7.3 复用 `cli_exec.py`

```python
# 复用 LANGUAGE_DEFAULT_CMD 作为工具探测的参考
from vools.task.core.cli_exec import LANGUAGE_DEFAULT_CMD

def probe_from_language_map():
    """从 LANGUAGE_DEFAULT_CMD 提取可探测的命令列表。"""
    commands = set()
    for lang, cmd_list in LANGUAGE_DEFAULT_CMD.items():
        for cmd in cmd_list:
            commands.add(cmd[0])  # 取命令名
    return list(commands)
```

### 7.4 第三方库集成 ★新增

#### psutil — 系统资源探测

```python
# 用途：CPU/内存/磁盘/网络/进程信息
# 大小：~250KB
# 安装：pip install psutil
# 
# 关键 API：
#   psutil.cpu_count()          → 逻辑核心数
#   psutil.cpu_count(logical=False) → 物理核心数
#   psutil.cpu_percent()        → CPU 使用率
#   psutil.virtual_memory()     → {total, available, percent}
#   psutil.disk_usage("/")      → {total, free, percent}
#   psutil.net_if_list()        → 网络接口列表
#   psutil.process_iter()       → 进程迭代器
#
# 为什么需要：动作选择依据——低内存机器不推荐大模型推理，
# 低磁盘不推荐 Docker 镜像拉取。
```

#### distro — Linux 发行版检测

```python
# 用途：替代 Python 3.8 移除的 platform.linux_distribution()
# 大小：~50KB
# 安装：pip install distro
# 
# 关键 API：
#   distro.id()       → 'ubuntu', 'fedora', 'arch', ...
#   distro.name()     → 'Ubuntu', 'Fedora', ...
#   distro.version()  → '22.04', '40', ...
#   distro.like()     → 'debian'（Ubuntu 是 Debian 的派生）
#
# 为什么需要：不同发行版的包管理器不同（apt/dnf/pacman），
# 影响工具安装推荐。
```

#### platformdirs — 跨平台标准目录

```python
# 用途：确定应用数据/配置/缓存应存放在哪
# 大小：~30KB
# 安装：pip install platformdirs
# 
# 关键 API：
#   PlatformDirs("vools-actus")
#   .user_data_dir    → ~/.local/share/vools-actus (Linux)
#   .user_config_dir  → ~/.config/vools-actus (Linux)
#   .user_cache_dir   → ~/.cache/vools-actus (Linux)
#   .user_log_dir     → ~/.local/state/vools-actus/logs (Linux)
#
# Windows:
#   %LOCALAPPDATA%\vools-actus     (data)
#   %APPDATA%\vools-actus          (config)
#   %LOCALAPPDATA%\vools-actus\cache (cache)
#
# macOS:
#   ~/Library/Application Support/vools-actus (data)
#   ~/Library/Caches/vools-actus        (cache)
#
# 为什么需要：探针缓存、日志、临时文件需要放在标准位置，
# 不能硬编码路径。
```

#### pywin32 — Windows API（可选，ctypes 可替代）

```python
# 用途：Windows 管理员检测、注册表访问、服务管理
# 大小：~5MB（最大依赖，可选）
# 安装：pip install pywin32
# 
# 关键 API：
#   win32api.IsUserAdmin()              → 管理员检测
#   win32security.LookupAccountName()   → 用户名解析
#   win32security.GetTokenGroups()      → 安全组
#   win32con.STANDARD_RIGHTS_READ       → ACL 常量
#
# 替代方案（零依赖）：
#   ctypes.windll.shell32.IsUserAnAdmin()  → 管理员检测
#   winreg.OpenKey() / EnumValue()         → 注册表
#
# 决策：优先用 ctypes（零依赖），pywin32 作为可选增强。
```

---

## 八、性能考虑

### 8.1 探测速度

```
单个探测项：
  shutil.which()        ~0.1ms（纯文件系统操作）
  subprocess.run()      ~50-500ms（取决于工具启动速度）
  importlib.metadata    ~1ms（已装包查询）

全部探测（~50 个工具）：
  串行：~5-15 秒
  并行（线程池 8 线程）：~2-4 秒

优化策略：
  1. shutil.which() 先行（快），再对找到的做版本探测（慢）
  2. 版本探测用线程池并行
  3. 缓存结果，24 小时内不重复探测
  4. force=True 时强制刷新
```

> **实测现状（2026-10-27 ~ 10-28 两轮补记）**：上面「串行 ~5-15 秒 / 并行 ~2-4 秒」是**目标值**；
> 真实起点比估计的差得多（**79 秒**），优化后**确实进到了 2-4 秒区间**。
>
> **一、冷启动演进（实测序列）**
>
> | 阶段 | probe 冷启动 | 说明 |
> |---|---|---|
> | 本轮起点（并行化前，串行） | **79 052 ms** | 版本探测的 `subprocess` 开销被本文档严重低估 |
> | 仅加并行（8 线程） | **11 136 ms** | `ThreadPoolExecutor`（`probe/__init__.py`） |
> | 分探测器逐个优化后 | **1 823 / 1 897 / 2 171 ms** | 三次独立测量 |
> | 本轮（`python_pkgs` 0.88s→0.079s、WSL 尖峰收口后） | **2 000-3 700 ms** | 随机器负载波动；安静时 ~2s |
>
> 相对串行起点共 **≈41x**。文档作者于 2026-10-28 在本仓复测
> `probe(force_refresh=True)`：**2 045 / 2 189 / 2 212 ms**（与上表一致），
> 同轮 `len(report.items) == 173`。
>
> **二、单探测器现状（独立进程 / 单跑实测）**
>
> | 探测器 | 耗时 | 备注 |
> |---|---|---|
> | `system_tools` | **1.2-1.5 s** | **当前最长杆**（65 个条目，含版本探测） |
> | `compilers` | 0.3-0.75 s | |
> | `runtimes` | 0.3 s | |
> | `platform_tools` | 0.2-0.3 s | 平台细项 |
> | `python_pkgs` | 0.08-0.16 s | 本轮从 0.88 s 优化下来（importlib 快路径） |
> | `environment` | 0.04 s | |
>
> ⚠️ **尖峰提示**：`system_tools` 偶发**冷启动尖峰**（本轮一次实测到 **7 027 ms**，
> 疑似 WSL/wt 类外部命令的首调用开销；同轮后续复测回落到 1 273 / 1 519 ms）。
> 故「安静时 ~2s」是**稳态值**，首跑或冷缓存时可能显著更慢。
>
> **三、与本文档原估值的偏差**
> - 原估「串行 ~5-15 秒」→ 实际 **79 秒**（低估 5-16 倍，主因是逐个工具 `subprocess` 版本探测）。
> - 原估「并行 ~2-4 秒」→ 实测**达成**，但**并行只贡献 79s→11s**，剩下 11s→2s
>   主要靠**分探测器优化**（`python_pkgs` 的 importlib 快路径、WSL 尖峰收口），
>   不是并行单独完成的 —— 「加个线程池就快」是错的。
> - 第 3、4 条（缓存 + `force_refresh`）此前即已生效（`probe/cache.py`，注意 TTL 实为 **1 小时**非 24h）。

### 8.2 探测结果缓存

```python
# 缓存文件：vools-actus/_meta/probe.cache.json
# 格式：ProbeReport + probed_at 时间戳
# 过期：24 小时

# 增量刷新策略：
# 1. 启动时检查缓存是否过期
# 2. 过期则全量重新探测
# 3. 未过期则直接用缓存
# 4. force=True 强制全量
```

---

## 九、分阶段落地

> **进度总览（2026-10-27 按代码事实核验，文档司令补记）**
>
> | 阶段 | 状态 | 一句话 |
> |---|---|---|
> | Phase 0 — 核心探测 + 权限 + 环境 | ✅ **已完成** | Phase 0 涉及的 10 个模块全部落地（`probe/` 现共 15 个 `.py`，含后加的 `platform_tools.py`） |
> | Phase 1 — Python 包 + 动作分析 + 缓存 | ✅ **已完成** | `python_pkgs.py` / `actions.py` / `cache.py` 均在位；**`analyze_actions()` ready/blocked 契约 2026-10-28 真正落地** |
> | Phase 2 — 平台特定 + 并行化 | 🟡 **基本完成（缺 macOS 实跑）** | 并行 8 线程 + 冷启动 79s→2s；Windows 真跑 / Linux 借 WSL 真跑 / **macOS 未实跑** |
> | Phase 3 — CLI + 集成 | ✅ **已完成** | `actus probe` 含 4 个开关 + MCP `actus_probe` + `intent.py` ready 过滤 |
>
> 本节的复选框**按实际代码核对**，未完成的**不勾**。路径约定：下面的 `probe/xxx.py`
> 对应仓库内 `actus/vools/actus/probe/xxx.py`，`tests/xxx.py` 对应 `actus/tests/xxx.py`。
>
> ⚠️ **行数与实现细节为 2026-10-28 08:5x 的核验快照**：`probe/` 目录在同一段时间里有多条线
> 并行开发（`platform_tools.py` / 线程池 / `cache.py` / `report.py` / `actions.py` 都在动），
> 行数会继续变；**模块存在性、接线位置、`grep` 零命中、实跑输出这四类判据不受影响**，可随时复核。

### Phase 0 — 核心探测 + 权限 + 环境（1 周）

- [x] `probe/base.py` — ProbeItem + Prober 基类 ✅ 已实现（74 行，含 `ProbeItem` / `Prober`）
- [x] `probe/platform.py` — 平台信息采集 ✅ 已实现（`get_platform_info()` / `PlatformProber`；核验快照 145 行）
- [x] `probe/permissions.py` — 权限与身份探测（管理员/root、文件权限、目录 ACL）★新增 ✅ 已实现（124 行）
- [x] `probe/environment.py` — 环境变量探测（PATH、敏感 key、虚拟环境、代理）★新增 ✅ 已实现（128 行）
- [x] `probe/resources.py` — 系统资源探测（psutil：CPU/内存/磁盘/网络）★新增 ✅ 已实现（118 行）
- [x] `probe/TOOL_TABLE.py` — 已知工具表 ✅ 已实现（94 行）
- [x] `probe/system_tools.py` — 系统工具探测（PATH + well-known paths + version）✅ 已实现（81 行）
- [x] `probe/runtimes.py` — 语言运行时探测（复用 runtimes.py）✅ 已实现（78 行）
- [x] `probe/compilers.py` — 编译器探测（复用 compile_cmd.py）✅ 已实现（68 行）
- [x] `probe/__init__.py` — probe() 入口函数 ✅ 已实现（`__all__ = ['probe', 'ProbeReport', 'format_summary']`；核验快照 183 行）
- [x] `tests/test_probe_basic.py` — 基础探测测试 ✅ 已实现，**但实际文件名为 `tests/test_probe.py`**（294 行；
      计划里的 `test_probe_basic.py` 从未创建）。覆盖面：ProbeItem 往返/异常吞掉、platform/
      permissions/environment/resources 字段形状、敏感值不外泄、完整 ProbeReport、已知工具检出、`format_summary`
- [x] **里程碑**：`probe()` 返回完整 ProbeReport，在本机跑通 ✅ 已实现（`tests/test_probe.py::test_probe_returns_full_report`）

### Phase 1 — Python 包 + 动作分析 + 缓存（1 周）

- [x] `probe/python_pkgs.py` — Python 包探测（importlib + pkg_resources 回退）✅ 已实现
      （本轮扩到 545 行；`importlib.metadata` 快路径 + 包名规范化，单次探测 **0.88s → 0.079s**）
- [x] `probe/actions.py` — 动作依赖分析（检查 .actus.md 的 deps 字段）✅ 已实现
      （782 行：既有 `_scan_actions_dir()` + `ActionsProber`，**本轮新增 `analyze_actions()`**
      —— 见 §4.7 实现现状表；第 3 个报告条目 `action_readiness` 由它供给）
- [x] `probe/cache.py` — 探测结果缓存（TTL）✅ 已实现（同一轮已扩为 schema 版本化 + 原子写 + 优雅降级；核验快照 305 行。注意默认 TTL 实为 **1 小时**，见 `_CACHE_TTL`，非本行原写的 24h）
- [x] `tests/test_probe_packages.py` — 包探测测试 ✅ **覆盖已有，但计划文件名不存在**：用例落在
      `tests/test_probe.py`（`test_pkg_version_reads_real_metadata` /
      `test_pkg_version_missing_pkg_is_empty` / `test_python_packages_prober_reports_versions`）
- [x] `tests/test_probe_actions.py` — 动作分析测试 ✅ **已存在**（2026-10-28 核验）：
      `actus/tests/test_probe_actions.py`，**387 行 / 12 用例**。覆盖：目录缺失、空目录、
      两种动作格式都能扫到、非动作文件忽略、显式目录参数、坏文件退化为相对路径 id、
      静态依赖表条目、`ready`/`blocked` 判定、报告不可用时不误杀全部、端到端报告集成。
      ⚠️ 但见 §4.7 的实话：这 12 个用例测的是 `ActionsProber` 条目形状 + `intent.py` 的**粗判定**，
      `analyze_actions` 的 `verdicts`/`blocked_reasons`/`undeclared`/`unverifiable`/`duplicate_ids`
      **细粒度分支仍无专项单测**（`grep` 全 `actus/tests/` 零命中），故本项勾 `[x]`、
      细粒度补测另列进剩余工作
- [x] **里程碑**：probe() 返回动作的 ready/blocked 状态 ✅ 已实现（**2026-10-28 真正实现**）
      > ⚠️ **历史留档（这份计划最重要的一课，不许抹掉）**：本项在 2026-10-27 的文档同步里
      > **曾被勾成 `[x] ✅ 已实现`，但那是一次虚假勾选** —— 当时代码里
      > `analyze_actions()` **根本不存在**（`grep` 零命中），报告里也没有任何 ready/blocked 字段，
      > 实际只有 `ActionsProber` 的「动作清单」条目 + `intent.py` 的粗过滤。之所以被勾上，
      > 是因为把「`actions.py` 模块存在」误当成「ready/blocked 契约已兑现」。
      > **教训**：勾选必须对着**契约字段的真实产出**（报告里真能读到 `total/ready/blocked`），
      > 而不是对着「有个同名模块」。
      >
      > 本轮（2026-10-28）已真正兑现：`analyze_actions()` 落地（`actions.py:520`，782 行），
      > `ActionsProber` 追加第 3 条目 `action_readiness`，`probe()` 报告 items **172 → 173**，
      > 实跑 `total=14 ready=14 blocked=0`（`undeclared=8`）。证据见 §4.7 实现现状表。

### Phase 2 — 平台特定 + 并行化（1 周）

> ⚠️ **本节状态在 2026-10-27 晚 ~ 2026-10-28 早连续变化**：
> 并行化与平台细项探测由同一轮的另一路（`probe/platform_tools.py` + `probe/__init__.py` 线程池，
> 落盘 19:10-19:16）**实现并带测试**；随后 **2026-10-28** 又补齐了 Homebrew、
> `tests/test_probe_windows.py`，并在 **WSL Ubuntu 22.04 里用真实产品代码跑通了 Linux 分支**。
> 下面的勾选按**核验后的代码/实跑事实**标定，证据见每项括注。

- [x] Windows 特有探测（VS Build Tools、WSL、Windows Terminal）✅ 已实现
      （`probe/platform_tools.py`：`_probe_windows_vs_build_tools` 走 `vswhere.exe`、
      `_probe_windows_wsl` 走 `wsl.exe -l -v`（含 UTF-16LE 解码）、
      `_probe_windows_terminal` 走 `wt.exe` App Execution Alias + 商店包目录名取版本；
      早期版本只有 `platform.py` 的版本号与 Program Files 路径）
- [x] Linux 特有探测（distro、包管理器、systemd）✅ 已实现 + **已在真 Linux 实跑取证**
      （2026-10-28，借 WSL **Ubuntu 22.04.5**，kernel `6.6.87.2-microsoft-standard-WSL2`，
      在 WSL 内**加载真实产品代码**执行，非 mock）：
      - `systemd 249`、**`usable=true`**（`/proc/1/comm=systemd`，**真 PID1** 判据成立）；
      - `package_manager`：`apt 2.4.14` + `dpkg 1.21.1` + `snap 2.76.3`（判定 `family=debian`）；
      - `platform.py` 侧 `is_wsl=true`、`kernel_version` 非空、`_get_linux_distro()` 命中；
      - 该轮自检 **17/17 全过**。
      代码位置：`platform.py` 的 `_get_linux_distro()`、`platform_tools.py` 的
      `_probe_linux_systemd()` / `_probe_linux_package_manager()`
- [~] macOS 特有探测（SIP、Homebrew、Xcode CLT）⚠️ **代码三项齐了，缺 macOS 实跑证据**：
      - SIP：`platform.py` 的 `_get_sip_status()`（`csrutil status`）—— **完全未在任何 Mac 上验证**；
      - Xcode CLT：`platform_tools.py` 的 `_probe_macos_xcode_clt`（`xcode-select -p` + `clang --version`）；
      - Homebrew：**本轮已实现** `platform_tools.py:835 _probe_macos_homebrew`
        （`grep -ci brew` 由 0 → **41**；判据 = PATH + `/opt/homebrew/bin/brew` +
        `/usr/local/bin/brew` **三路查找** + `--version` + `--prefix`，
        并**拒绝非 posix 派生路径冒充 prefix**），在 `darwin` 组注册于 `:943`。
      **为何仍不勾**：整组**无 macOS 实跑证据** —— darwin 分支只用平台钩子模拟执行 +
      伪造 brew 验解析链路（11/11 过），`csrutil` 一行都没在真 Mac 上跑过。
      代码齐 ≠ 平台跑通，故保留 `[~]`
- [x] 线程池并行探测（8 线程）✅ 已实现（`probe/__init__.py` `import concurrent.futures`、
      `_MAX_PROBE_WORKERS = 8`、`ThreadPoolExecutor(max_workers=workers)`，
      并行度取 `min(8, 探测器数)`；`as_completed` 收结果后**按原始顺序合并**，不改变 items 结构；
      `verbose` 进度打印用 `threading.Lock` 串行化防交错）。
      **耗时（本轮实测，含前一轮串行基线与后续单探测器优化，见 §8.1）**：
      **79 052ms → 11 136ms（仅并行）→ 1 823-2 171ms（分探测器优化后）→ 2 000-3 700ms（本轮）**，
      相对串行起点约 **41x**。本机复测 `probe(force_refresh=True)` 实际 **2 045 / 2 189 / 2 212ms**
- [x] `tests/test_probe_windows.py` — Windows 特定测试 ✅ **已存在**（2026-10-28 核验）：
      `actus/tests/test_probe_windows.py`，**385 行 / 9 用例**；做法是**假 Windows 世界**
      （把 `sys.platform` / `os.environ` / PATH 打桩成 sterile 环境）+ 平台钩子替换，
      在**非 Windows 宿主整文件 skip**（本机 Windows 上 9 个全跑）。
      Windows 分支另有两层覆盖：`tests/test_probe_platform_tools.py`（vswhere/WSL/WT 输出形态与解析）、
      `tests/test_probe.py::test_platform_windows_specific_fields`（`platform.py` 字段）
- [~] **里程碑**：三个平台各自跑通 ⚠️ **部分** —— 三平台可证明程度不同，逐个写清：
      | 平台 | 状态 | 可证明程度 |
      |---|---|---|
      | Windows | ✅ 真机实跑 | `probe()` 完整报告（items **173**、`elapsed_ms≈2212`）+ `platform_tools` Windows 三探测 + 9 用例 |
      | Linux | ✅ 借 WSL 真跑 | WSL Ubuntu 22.04.5 内加载真实产品代码：systemd 真 PID1、apt/dpkg/snap、`is_wsl=true`，自检 17/17 |
      | macOS | ❌ **未实跑** | 无 Mac 环境；仅平台钩子模拟 + 伪造 brew 验解析链路（11/11），`csrutil` 未验证 |

### Phase 3 — CLI + 集成（1 周）

- [x] `vools actus probe` CLI 命令（人类可读输出）✅ 已实现（`actus/vools/actus/cli.py:165` 注册 `probe` 子命令，
      `:932` 分发，`:2446-2452` 人类可读走 `format_summary`）
- [x] `vools actus probe --json` — JSON 输出（机器消费）✅ 已实现（`cli.py:170` `--json` → `as_json`，输出完整结构化报告）
- [x] `vools actus probe --cache/--force` — 缓存控制 ✅ 已实现（`cli.py:166-169`：
      `--force-refresh`/`--force` 与 `--max-age N`（默认 3600），另有 `--verbose`）
- [x] 集成到 `intent.py` — 推荐动作时只推荐 ready 的 ✅ 已实现（`actus/vools/actus/intent.py:48-96`：
      `set_ready_ids()` / `set_probe_report()` / `_is_ready()`，注释直指「PROBE_PLAN.md §9 Phase 3」）
- [x] 集成到 MCP server — 暴露 probe 工具给 LLM ✅ 已实现（`actus/vools/actus/mcp_server.py:416` 注册
      `actus_probe`，`:1345` 分发）
- [x] **里程碑**：`vools actus probe` 一条命令看全貌 ✅ 已实现

### 进度小结

#### 第 1 轮（2026-10-27，文档司令 cmd-docs 补记）

- **谁补的**：文档司令（cmd-docs），按代码事实核验后回填复选框，**不含任何未核实的进度**。
  同一轮另有「平台司令」落地了 Phase 2 的并行化与平台细项探测。
- **第 1 轮结论**：Phase 0 / 1 / 3 **已完成**（原文档的 30 个复选框全是 `[ ]`，与代码严重脱节）；
  Phase 2 部分完成 —— 当时余 Homebrew、跨平台实跑、`test_probe_windows.py`。
- **第 1 轮的失误（本轮已纠正，留档）**：把 Phase 1 的「里程碑：probe() 返回 ready/blocked」
  **勾成了 `[x]`，属虚假勾选** —— 当时代码里根本没有 `analyze_actions()`（见 Phase 1 那条的历史留档）。

#### 第 2 轮（2026-10-28，同一文档司令补记）

- **5 个 `[~]` 的落地情况**：
  - `tests/test_probe_actions.py` → **`[x]`**（387 行 / 12 用例，已存在）；
  - `tests/test_probe_windows.py` → **`[x]`**（385 行 / 9 用例，假 Windows 世界 + 非 Windows 宿主整文件 skip）；
  - Linux 特有探测 → **`[x]`**（在 WSL Ubuntu 22.04.5 里用真实产品代码实跑：systemd 249 `usable=true`
    真 PID1、apt 2.4.14 / dpkg 1.21.1 / snap 2.76.3，自检 17/17）；
  - macOS 特有探测 → **仍 `[~]`**（Homebrew 已实现，SIP/Xcode CLT 在位，但**整组无 macOS 实跑证据**）；
  - 里程碑「三个平台各自跑通」 → **仍 `[~]`**（Windows ✅ 真机 / Linux ✅ 借 WSL / **macOS ❌ 未实跑**）。
- **最重要的纠正**：§4.7 的 `analyze_actions()` **从「不存在」变成「真实现」**，
  §9 Phase 1 里程碑那条 `[x]` **从「虚假」变成「名副其实」** —— `probe()` 报告 items 172 → **173**，
  实跑 `total=14 ready=14 blocked=0`（`undeclared=8`）。历史留档已写进 Phase 1 那一项里。
- **性能**：冷启动 **79 052ms → 2 000-3 700ms**（≈41x），本机复测 2 045 / 2 189 / 2 212ms，详见 §8.1。
- **两条「进行中」的产品缺口（本轮不勾、不算完成；代码已开始落地但未验收）**：
  1. **`runtime:` 依赖前缀进 resolver**：`actus/vools/actus/dependency.py` 已加
     `_DepKind.RUNTIME`（`:42`）与 `elif dep_str.startswith("runtime:")`（`:189`）+ 抽象名展开表
     （`runtime:shell`→bash/sh、`runtime:rust`→rustc/cargo）；
     **但 `grep -rn "runtime:" actus/tests/` 零命中** → 解析分支**尚无单测**，本轮不判完成；
  2. **`intent.py` 的 ready 判据接 `verdicts`**：已加第二道门
     `_extract_blocked_ids()`（`:114-135`，只认显式 `verdict == "blocked"`），
     `_is_ready()`（`:137`）改为「在 `_ready_ids` 里 **且** 不在 `_blocked_ids` 里」；
     取不到信息时回落 `None` → 与本轮之前行为一致（零回归）。
     并新增 `tests/test_action_readiness_intent.py`（329 行 / 9 用例，**实测 9 passed**）。
     **仍按「进行中」记录** —— 本轮未验收。
     注：`tests/test_probe_actions.py:319-321` 里那句「现产品的 blocked 判据就是『报告里没有它』」
     的注释**已落后于代码**（现有两道门），建议随验收一并更新。
- **剩余工作清单（按优先级）**：
  1. **macOS 实跑取证**（SIP/Homebrew/Xcode CLT 三探测在真 Mac 上验一次）—— 唯一还压着 Phase 2 里程碑的项；
  2. 给 `runtime:` 解析分支补单测，然后验收上表两条「进行中」；
  3. 补 `analyze_actions` 的**细粒度单测**（`verdicts`/`blocked_reasons`/`undeclared`/`unverifiable`/`duplicate_ids`
     目前 `grep` 全 tests/ 零命中，靠 fixture 手工验证）；
  4. 计划文档的测试文件名对齐：`test_probe_basic.py` / `test_probe_packages.py`
     实际是 `test_probe.py`（`test_probe_windows.py` 已于本轮按计划名建出）。
- **核验方式与证据（第 2 轮）**：
  - `wc -l`：`tests/test_probe_actions.py` 387 行、`tests/test_probe_windows.py` 385 行、
    `probe/actions.py` 782 行、`probe/platform_tools.py` 1110 行、`probe/python_pkgs.py` 545 行；
  - `grep -n "def analyze_actions" probe/actions.py` → `:520`；`grep -n action_readiness` → `:725/:776`；
  - **实跑** `analyze_actions()` → `total=14 ready=14 blocked=0 undeclared=8 index_source=self-probe`；
  - **实跑** `probe(force_refresh=True, max_age=0)` → `len(items)=173`、`elapsed_ms=2212`、
    报告内 `action_readiness` 条目存在；
  - `grep -ci brew probe/platform_tools.py` → **41**（第 1 轮为 0）；`_probe_macos_homebrew` 在 `:835`、
    darwin 组注册于 `:943`；
  - `grep -n "runtime:" dependency.py` → **零命中**（确认缺口 1 仍在）；
  - `grep -n "_is_ready" intent.py` → `:96`，函数体为 `action_id in self._ready_ids`（确认缺口 2 仍在）；
  - `python -m pytest tests/test_probe_actions.py tests/test_probe_windows.py` → **21 passed**；
    连同 `test_probe.py` / `test_probe_parallel.py` / `test_probe_platform_tools.py` 一起 →
    **61 passed, 3 skipped**（exit 0，2026-10-28 实测）。

---

## 十、风险与开放问题

### 10.1 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 工具版本探测超时 | 探测慢 | 5 秒超时 + 线程池并行 |
| 某些工具无 --version | 版本探测失败 | 返回 path 但不返回 version |
| Windows PATH 很长 | which() 慢 | 先 which() 再版本探测，不重复搜 PATH |
| Python 包名不统一 | 包名 hyphen vs underscore | 统一转 underscore 后 import |
| 动作依赖格式不统一 | deps 字段解析失败 | 容错解析，失败则标记为 blocked |
| 缓存过期 | 探测结果过时 | 24h TTL + force 强制刷新 |
| **敏感信息泄露** | 环境探针扫到 API key/token | **只记录 key 名存在与否，绝不记录值**；PATH 只记数量 |
| **管理员检测失败** | ctypes 在某些环境不可用 | pywin32 回退 → 环境变量启发式 |
| **psutil 未安装** | 系统资源探测失败 | 优雅降级到 stdlib 的 `os.cpu_count()` |
| **虚拟环境嵌套** | 多层 venv 混乱 | 记录完整 sys.prefix 链，不猜 |
| **sudo 检测** | `/etc/sudoers` 不可读 | 仅检查可读性，不实际执行 sudo |
| **文件 ACL 差异** | Windows ACL vs Unix 权限位 | 分别处理，结果标记平台来源 |
| **`runtime:` 依赖前缀**（进行中，代码已落地待验收） | 原状：`dependency.py` 无该分支 → 裸串当成 action 依赖 → `runtime:python` 永远 blocked | 已加 `_DepKind.RUNTIME` + `runtime:` 分支 + 抽象名展开表；**缺单测**（`grep runtime: tests/` 零命中） |
| **`intent.py` ready 判据**（进行中，代码已落地待验收） | 原状只判「动作在报告里 = ready」→ 缺依赖但出现在报告里的动作会被误推荐 | 已加第二道门读 `verdicts` 的显式 `blocked`；`test_action_readiness_intent.py` 9 用例通过；待验收 |
| **`system_tools` 偶发冷启动尖峰** | 单跑偶现 7 027ms（稳态 1.2-1.5s），拉高首跑体感 | 已定位为 WSL/wt 类外部命令首调用开销；继续收口（§8.1 尖峰提示） |

### 10.2 开放问题

1. **Q1: TOOL_TABLE 怎么维护？** 写死在代码里？还是从动作的 deps 字段动态生成？
2. **Q2: 动作的 deps 字段目前格式是什么？** `#!cfg` JSON 里的 `deps` 字段是 `[]` 还是其他格式？
3. **Q3: 探测结果要不要发给 LLM？** 如果是，LLM 怎么消费？是 MCP tool 还是直接注入 prompt？
4. **Q4: 要不要支持自定义探测项？** 用户注册自己的 probe_item？
5. **Q5: 探测速度能接受多慢？** 5 秒？15 秒？是否需要后台预热？

---

## 十一、一句话总结

> vools-actus 探针 = **stdlib（shutil.which + subprocess + importlib + os + ctypes + winreg）+ 4 个轻量第三方库（psutil + distro + platformdirs + pywin32）拼一个统一入口**。复用 `runtimes.py`（运行时）、`compile_cmd.py`（编译器）、`cli_exec.py`（语言映射）、`indexer.py`（动作发现）。新增 9 个探测维度：平台、权限、环境、资源、运行时、编译器、系统工具、Python 包、动作依赖。没有现成库能一步到位，也不需要 LLM 帮忙——探测是本地确定性操作，LLM 只负责消费结果。
