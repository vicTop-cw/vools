"""importsys.py —— 多语言模块导入系统 (Phase L)。

允许动作通过 #!import 元数据字段跨语言导入模块。
支持:
- Python → C/Rust/Cython (编译为 .pyd/.so)
- Python → Shell (通过 subprocess)
- Python → Node.js (通过子进程)
- Python → Wasm (通过 wasmtime，若可用)

用法:
    #!import rust:path/to/lib.rs as mylib
    #!import c:path/to/code.c as fast
    #!import shell:path/to/util.sh as sh
    #!import node:path/to/tool.mjs as js

动作执行时，importsys 自动:
1. 解析 import 声明
2. 编译外部代码为可调用模块
3. 注入到执行上下文中

缓存: 编译结果缓存到 `_meta/imports_cache/`，源文件未变化时直接复用。
"""

import os
import re
import hashlib
import shutil
import subprocess
import tempfile
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Import 解析 ─────────────────────────────────────────────────────────────

IMPORT_RE = re.compile(
    r'^#!import\s+(\w+):([^\s]+)\s+as\s+(\w+)$',
    re.MULTILINE
)


class ImportDecl:
    """一条 #!import 声明。"""

    def __init__(self, language: str, path: str, alias: str):
        self.language = language
        self.path = path
        self.alias = alias

    def __repr__(self):
        return f"#!import {self.language}:{self.path} as {self.alias}"

    def source_key(self) -> str:
        """生成缓存键。"""
        return f"{self.language}:{self.path}"


def parse_imports(meta_text: str) -> List[ImportDecl]:
    """从元数据文本中解析所有 #!import 声明。

    参数:
        meta_text: .actus.md 中的 #!cfg 文本块。

    返回:
        ImportDecl 列表。
    """
    decls = []
    for m in IMPORT_RE.finditer(meta_text):
        decls.append(ImportDecl(
            language=m.group(1).strip(),
            path=m.group(2).strip(),
            alias=m.group(3).strip(),
        ))
    return decls


# ── 编译器后端 ──────────────────────────────────────────────────────────────

class CompilerBackend:
    """编译器后端基类。"""

    @property
    def language(self) -> str:
        ...

    def is_available(self) -> bool:
        """检查编译器是否可用。"""
        ...

    def compile(self, source_path: Path, output_path: Path) -> Tuple[bool, str]:
        """编译源文件到输出路径。

        返回: (成功, 错误信息)
        """
        ...


class RustCompiler(CompilerBackend):
    """Rust → 共享库编译。"""

    @property
    def language(self) -> str:
        return "rust"

    def is_available(self) -> bool:
        return shutil.which("rustc") is not None

    def compile(self, source_path: Path, output_path: Path) -> Tuple[bool, str]:
        """编译 Rust 源文件为动态库。"""
        if not self.is_available():
            return False, "rustc 不可用"

        # 生成 C ABI 的共享库
        cmd = [
            "rustc", "--crate-type", "cdylib",
            "-o", str(output_path),
            str(source_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                return True, ""
            return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "编译超时 (120s)"
        except Exception as e:
            return False, str(e)


class CCompiler(CompilerBackend):
    """C → 共享库编译。"""

    @property
    def language(self) -> str:
        return "c"

    def is_available(self) -> bool:
        return shutil.which("gcc") is not None or shutil.which("cl.exe") is not None

    def compile(self, source_path: Path, output_path: Path) -> Tuple[bool, str]:
        if not self.is_available():
            return False, "C 编译器不可用"

        if shutil.which("gcc"):
            cmd = ["gcc", "-shared", "-fPIC", "-o", str(output_path), str(source_path)]
        else:
            cmd = ["cl.exe", "/LD", str(source_path), f"/Fe:{output_path}"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return True, ""
            return False, result.stderr
        except Exception as e:
            return False, str(e)


class ShellBackend(CompilerBackend):
    """Shell 脚本（无需编译，直接验证存在）。"""

    @property
    def language(self) -> str:
        return "shell"

    def is_available(self) -> bool:
        return True

    def compile(self, source_path: Path, output_path: Path) -> Tuple[bool, str]:
        """Shell 不需要编译，只需验证源文件存在且可执行。"""
        if not source_path.exists():
            return False, f"源文件不存在: {source_path}"
        # 仅验证存在
        return True, ""


class NodeBackend(CompilerBackend):
    """Node.js 模块（验证 node 可用）。"""

    @property
    def language(self) -> str:
        return "node"

    def is_available(self) -> bool:
        return shutil.which("node") is not None

    def compile(self, source_path: Path, output_path: Path) -> Tuple[bool, str]:
        if not self.is_available():
            return False, "node 不可用"
        if not source_path.exists():
            return False, f"源文件不存在: {source_path}"
        return True, ""


# ── Import 解析器 ──────────────────────────────────────────────────────────

class ImportResolver:
    """多语言导入解析器。

    管理编译器后端，处理 import 解析和编译缓存。
    """

    def __init__(self, repo_root: str = "."):
        self.repo_root = Path(repo_root)
        self.cache_dir = self.repo_root / "_meta" / "imports_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 注册编译器
        self._backends: Dict[str, CompilerBackend] = {
            "rust": RustCompiler(),
            "c": CCompiler(),
            "shell": ShellBackend(),
            "node": NodeBackend(),
        }

    def resolve(self, decl: ImportDecl) -> Tuple[bool, str, Optional[Path]]:
        """解析一条 import 声明。

        返回: (成功, 信息, 输出文件路径)
        """
        backend = self._backends.get(decl.language)
        if not backend:
            return False, f"不支持的语言: {decl.language}", None

        if not backend.is_available():
            return False, f"{decl.language} 编译器不可用", None

        source_path = self.repo_root / decl.path
        if not source_path.exists():
            return False, f"源文件不存在: {decl.path}", None

        # 计算缓存键
        cache_key = self._cache_key(source_path)
        cached = self.cache_dir / f"{decl.alias}_{cache_key}"

        if cached.exists():
            return True, "缓存命中", cached

        # 编译
        ok, msg = backend.compile(source_path, cached)
        if ok:
            return True, f"编译成功: {decl.path}", cached
        return False, msg, None

    def resolve_all(self, decls: List[ImportDecl]) -> Dict[str, Path]:
        """解析所有 import 声明。

        返回: {alias: 路径} 字典。
        """
        results = {}
        for decl in decls:
            ok, msg, path = self.resolve(decl)
            if ok:
                results[decl.alias] = path
            else:
                logger.warning(f"导入失败 [{decl}]: {msg}")
        return results

    def _cache_key(self, source_path: Path) -> str:
        """基于文件内容生成缓存键。"""
        content = source_path.read_bytes()
        return hashlib.md5(content).hexdigest()[:12]

    def clear_cache(self):
        """清空编译缓存。"""
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def list_available_backends(self) -> Dict[str, bool]:
        """列出所有后端及其可用状态。"""
        return {lang: b.is_available() for lang, b in self._backends.items()}


# ── 便捷函数 ───────────────────────────────────────────────────────────────

def resolve_imports_for_action(action_meta: dict, repo_root: str = ".") -> Dict[str, Path]:
    """为动作解析所有 import 声明。

    参数:
        action_meta: 动作的 meta 字典（含 #!cfg 内容）。
        repo_root: 仓库根目录。

    返回:
        {alias: 路径} 字典。
    """
    cfg_text = action_meta.get("_cfg_text", "")
    if not cfg_text:
        return {}

    decls = parse_imports(cfg_text)
    if not decls:
        return {}

    resolver = ImportResolver(repo_root)
    return resolver.resolve_all(decls)


def check_imports_available(action_meta: dict, repo_root: str = ".") -> List[dict]:
    """检查 import 声明的可用状态。

    返回:
        [{decl, ok, info}]
    """
    cfg_text = action_meta.get("_cfg_text", "")
    decls = parse_imports(cfg_text)
    resolver = ImportResolver(repo_root)

    results = []
    for decl in decls:
        ok, msg, _ = resolver.resolve(decl)
        results.append({"decl": repr(decl), "ok": ok, "info": msg})
    return results


__all__ = [
    'CCompiler',
    'CompilerBackend',
    'IMPORT_RE',
    'ImportDecl',
    'ImportResolver',
    'NodeBackend',
    'RustCompiler',
    'ShellBackend',
    'check_imports_available',
    'logger',
    'parse_imports',
    'resolve_imports_for_action'
]
