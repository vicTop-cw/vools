"""probe/TOOL_TABLE.py — 已知系统工具表。

每个条目：(name, aliases, version_cmd, well_known_paths, timeout)
- name: 工具主命令名
- aliases: 别名列表
- version_cmd: 获取版本号的参数（如 ["--version"]），空列表表示仅检测存在性
- well_known_paths: 平台特定搜索路径（dict: platform → glob patterns）
- timeout: 版本探测超时秒数
"""


__all__ = [
    "TOOL_TABLE",
]

TOOL_TABLE = [
    # ── 编译器 ──
    ("gcc", ["cc"], ["--version"], {}, 5),
    ("g++", ["c++"], ["--version"], {}, 5),
    ("clang", ["clang"], ["--version"], {}, 5),
    ("cl", [], ["??"], {
        "win32": [r"C:\Program Files\Microsoft Visual Studio\**\VC\Tools\MSVC\*\bin\Hostx64\x64\cl.exe"],
    }, 5),
    ("rustc", [], ["--version"], {}, 5),
    ("nim", [], ["--version"], {}, 5),
    ("zig", [], ["version"], {}, 5),
    ("javac", [], ["-version"], {}, 5),

    # ── 语言运行时 ──
    ("python", ["python3", "py"], ["--version"], {}, 5),
    ("node", ["nodejs"], ["--version"], {}, 5),
    ("ruby", [], ["--version"], {}, 5),
    ("php", [], ["--version"], {}, 5),
    ("go", [], ["version"], {}, 5),

    # ── 包管理器 ──
    ("pip", ["pip3", "pip3.11", "pip3.12"], ["--version"], {}, 5),
    ("npm", [], ["--version"], {}, 5),
    ("yarn", [], ["--version"], {}, 5),
    ("pnpm", [], ["--version"], {}, 5),
    ("cargo", [], ["--version"], {}, 5),
    ("brew", [], ["--version"], {}, 5),
    ("apt", ["apt-get"], ["--version"], {}, 5),
    ("dnf", [], ["--version"], {}, 5),
    ("pacman", [], ["--version"], {}, 5),

    # ── 版本控制 ──
    ("git", [], ["--version"], {}, 5),
    ("svn", [], ["--version"], {}, 5),

    # ── 构建工具 ──
    ("make", [], ["--version"], {}, 5),
    ("cmake", [], ["--version"], {}, 5),
    ("ninja", [], ["--version"], {}, 5),
    ("msbuild", [], ["/version"], {}, 5),
    ("nuget", [], ["--version"], {}, 5),

    # ── 文本/数据处理 ──
    ("jq", [], ["--version"], {}, 5),
    ("yq", [], ["--version"], {}, 5),
    ("sed", [], ["--version"], {}, 5),
    ("awk", [], ["--version"], {}, 5),
    ("grep", [], ["--version"], {}, 5),
    ("ripgrep", ["rg"], ["--version"], {}, 5),

    # ── 压缩 ──
    ("zip", [], ["--version"], {}, 5),
    ("unzip", [], ["--version"], {}, 5),
    ("tar", [], ["--version"], {}, 5),
    ("7z", [], ["--version"], {}, 5),

    # ── 网络工具 ──
    ("curl", [], ["--version"], {}, 5),
    ("wget", [], ["--version"], {}, 5),
    ("ssh", [], ["-V"], {}, 5),       # -V 而非 --version
    ("scp", [], ["-V"], {}, 5),
    ("sftp", [], ["-V"], {}, 5),

    # ── 数据库 ──
    ("psql", [], ["--version"], {}, 5),
    ("sqlite3", [], ["--version"], {}, 5),
    ("mysql", [], ["--version"], {}, 5),
    ("mongo", ["mongosh"], ["--version"], {}, 5),

    # ── 容器/虚拟化 ──
    ("docker", [], ["--version"], {}, 5),
    ("podman", [], ["--version"], {}, 5),
    ("kubectl", [], ["version", "--client"], {}, 5),
    ("helm", [], ["version"], {}, 5),

    # ── AI/ML 工具 ──
    ("ollama", [], ["--version"], {}, 5),
    ("whisper", [], ["--help"], {}, 10),  # openai-whisper CLI

    # ── 平台特有工具（Phase 2 数据补充）──────────────────────────────────
    # 这里只列「可执行文件存在性 + 版本」这一档的原始数据；需要组合判据的
    # 平台能力（vswhere 查询 VS 实例、wsl 发行版列表、systemd 是否真是 PID1、
    # xcode-select 指向哪、wt 的商店包版本）在 platform_tools.py 里做，
    # 避免在两处重复判据。
    #
    # 收录纪律（本表会**真实执行** version_cmd，所以有两条硬约束）：
    #   1. 不得收录「无参数执行会产生副作用」的工具 —— 例如 wt.exe（无参数会
    #      弹出一个 Windows Terminal 窗口，实测过）和 wsl.exe（无参数会起 shell）。
    #   2. 输出不是 UTF-8 的工具不收 —— system_tools 的版本探测走 text=True
    #      （locale 解码），wsl.exe 的 UTF-16LE 输出会变成带 NUL 的乱码。
    # 这两类都交给 platform_tools.py（它自己控 argv、自己做 UTF-16 解码）。
    #
    # 注：非当前平台的条目只会 which/glob 失败 → 如实记 not found，不执行命令。

    # Windows（包管理器）
    ("winget", [], ["--version"], {}, 5),
    ("choco", [], ["--version"], {}, 5),
    ("scoop", [], ["--version"], {}, 5),

    # Linux（服务管理 + 包管理器；输出均为 UTF-8 文本）
    ("systemctl", [], ["--version"], {}, 5),
    ("dpkg", [], ["--version"], {}, 5),
    ("zypper", [], ["--version"], {}, 5),
    ("apk", [], ["--version"], {}, 5),
    ("flatpak", [], ["--version"], {}, 5),
    ("snap", [], ["--version"], {}, 5),

    # macOS
    ("xcode-select", [], ["-p"], {}, 5),  # 无 --version（-p 打印 Developer 目录）
    ("port", [], ["version"], {}, 5),     # MacPorts
]
