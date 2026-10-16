"""probe/TOOL_TABLE.py — 已知系统工具表。

每个条目：(name, aliases, version_cmd, well_known_paths, timeout)
- name: 工具主命令名
- aliases: 别名列表
- version_cmd: 获取版本号的参数（如 ["--version"]），空列表表示仅检测存在性
- well_known_paths: 平台特定搜索路径（dict: platform → glob patterns）
- timeout: 版本探测超时秒数
"""

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
]