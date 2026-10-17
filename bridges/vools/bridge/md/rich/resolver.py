"""
vools.bridge.md.rich.resolver — 富内容路径解析器

职责（计划 §4.1 / §5.3 越权防护）：
- 解析富内容引用（相对路径 / @artifacts 产物引用 / 显式 opt-in 的绝对路径）
- 拒绝 `..` 越权（严格模式：任何 `..` 段一律拒绝；默认模式：规范化后落在根外拒绝）
- 拒绝未 opt-in 的绝对路径（allow_absolute=False 默认）
- 拒绝符号链接逃逸（check_realpath=True 时 realpath 必须落在允许根内）
- @artifacts 产物引用：优先 artifacts/rich/ 下文件，兼容旧 block_{idx}_{name}.txt 命名与
  旧 tmp/ 路径读取（决策 1：export 落盘位置修正，旧路径可继续读）

允许根集合：
- root            （md 文档所在目录）
- artifacts_dir   （build_dir/artifacts/rich，@artifacts 引用专用）
- legacy_tmp_dir  （build_dir/tmp，旧 export 落盘位置，仅读取兼容）

安全模型：resolver 是富内容访问的唯一门禁，所有 open_file 目标必须先过本解析器。
"""

import os
from typing import List, Optional

from ..errors import (
    MDRichAccessDeniedError,
    MDRichPathError,
    MDRichError,
)

#: @artifacts 引用前缀
ARTIFACTS_REF_PREFIX = "@artifacts"

#: 允许的富内容扩展名白名单（open_file / open_result 场景）
DEFAULT_ALLOWED_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".xls", ".xlsx", ".csv", ".tsv",
    ".md", ".txt", ".html", ".htm",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg",
    ".zip", ".mp4", ".mp3", ".wav",
)


class RichPathResolver:
    """富内容路径解析器（单例式，构造时固化允许根）。"""

    def __init__(
        self,
        root: str,
        build_dir: Optional[str] = None,
        *,
        allow_absolute: bool = False,
        strict_dotdot: bool = True,
        check_realpath: bool = True,
        allowed_extensions: Optional[tuple] = None,
    ):
        self.root = os.path.abspath(root)
        self.build_dir = os.path.abspath(build_dir) if build_dir else os.path.join(self.root, ".mdbuild")
        self.artifacts_dir = os.path.join(self.build_dir, "artifacts", "rich")
        self.legacy_tmp_dir = os.path.join(self.build_dir, "tmp")
        self.allow_absolute = allow_absolute
        self.strict_dotdot = strict_dotdot
        self.check_realpath = check_realpath
        self.allowed_extensions = tuple(allowed_extensions or DEFAULT_ALLOWED_EXTENSIONS)

        # 允许根集合（相对/绝对引用最终都必须落在这些根内）
        self._allowed_roots = (
            os.path.abspath(self.root),
            os.path.abspath(self.artifacts_dir),
            os.path.abspath(self.legacy_tmp_dir),
        )

    # ── 公共入口 ────────────────────────────────────────────

    def resolve(self, target: str) -> str:
        """
        解析富内容引用，返回校验后的绝对路径。

        规则（计划 §5.3）：
        - `..` 段：strict_dotdot=True 时直接拒绝；否则规范化后必须落在允许根内
        - 绝对路径：默认拒绝（allow_absolute=False），opt-in 后放行（仍校验 realpath 逃逸）
        - @artifacts 前缀：解析为 artifacts/rich/ 下产物（兼容旧命名与旧 tmp/ 读取）
        - 扩展名：不在白名单拒绝
        - 目标不存在：报 E_PATH_NOT_FOUND
        """
        if not target or not str(target).strip():
            raise MDRichPathError("引用目标为空", code="E_PATH_NOT_FOUND")

        target = str(target).strip()

        # 1. @artifacts 产物引用
        if target.startswith(ARTIFACTS_REF_PREFIX + "/") or target == ARTIFACTS_REF_PREFIX:
            return self._resolve_artifact(target)

        # 2. 绝对路径分支
        if os.path.isabs(target):
            if not self.allow_absolute:
                raise MDRichAccessDeniedError(
                    f"绝对路径未 opt-in 拒绝: {target}",
                    code="E_ACCESS_DENIED",
                )
            cand = os.path.normpath(target)
            return self._finalize(cand, target, skip_root_check=True)

        # 3. 相对路径分支（相对 root 解析）
        if self.strict_dotdot and ".." in target.replace("\\", "/").split("/"):
            raise MDRichAccessDeniedError(
                f"路径含 .. 越权段拒绝: {target}",
                code="E_ACCESS_DENIED",
            )
        cand = os.path.normpath(os.path.join(self.root, target))
        return self._finalize(cand, target)

    # ── @artifacts 产物引用 ─────────────────────────────────

    def _resolve_artifact(self, target: str) -> str:
        """@artifacts 引用解析：优先 artifacts/rich/，兼容旧命名与旧 tmp/。"""
        name = target[len(ARTIFACTS_REF_PREFIX):].lstrip("/")
        if not name:
            raise MDRichPathError("@artifacts 缺少产物名", code="E_PATH_NOT_FOUND")

        # 防伪：产物名不允许含路径分隔符或 .. 段
        name_norm = name.replace("\\", "/")
        if "/" in name_norm or ".." in name_norm.split("/"):
            raise MDRichAccessDeniedError(
                f"@artifacts 产物名含路径分隔符/越权段拒绝: {name}",
                code="E_ACCESS_DENIED",
            )

        candidates: List[str] = []

        # 新落盘位置 artifacts/rich/<name>
        candidates.append(os.path.join(self.artifacts_dir, name))

        # 兼容旧命名 block_{idx}_{name}.txt（新目录下也扫）
        prefix = "block_"
        suffix = f"_{name}.txt"
        if os.path.isdir(self.artifacts_dir):
            for fname in sorted(os.listdir(self.artifacts_dir)):
                if fname.startswith(prefix) and fname.endswith(suffix):
                    candidates.append(os.path.join(self.artifacts_dir, fname))

        # 兼容旧 tmp/ 路径读取（决策 1：export 曾落 build_dir/tmp）
        if os.path.isdir(self.legacy_tmp_dir):
            for fname in sorted(os.listdir(self.legacy_tmp_dir)):
                if fname == name or (fname.startswith(prefix) and fname.endswith(suffix)):
                    candidates.append(os.path.join(self.legacy_tmp_dir, fname))

        for cand in candidates:
            cand = os.path.normpath(cand)
            if os.path.exists(cand):
                return self._finalize(cand, target, check_extension=False)

        raise MDRichPathError(
            f"@artifacts 产物不存在: {name}（已检索 artifacts/rich/ 与旧 tmp/）",
            code="E_PATH_NOT_FOUND",
        )

    # ── 最终校验 ────────────────────────────────────────────

    def _finalize(
        self,
        cand: str,
        original: str,
        check_extension: bool = True,
        skip_root_check: bool = False,
    ) -> str:
        """统一出口：根内校验 + realpath 逃逸校验 + 存在性 + 扩展名白名单。

        skip_root_check=True 仅用于绝对路径 opt-in 分支：用户显式授权访问根外
        路径，此时不做"落在允许根内"校验；realpath 逃逸校验对根外路径同样跳过。
        """
        if not skip_root_check and not self._within_any_root(cand):
            raise MDRichAccessDeniedError(
                f"解析结果越出允许根: {original} -> {cand}",
                code="E_ACCESS_DENIED",
            )

        if not skip_root_check and self.check_realpath:
            # 仅对已存在的父目录做 realpath 校验（文件不存在时先报不存在）
            parent = os.path.dirname(cand)
            if os.path.exists(parent):
                real = os.path.realpath(cand)
                if not self._within_any_root(real):
                    raise MDRichAccessDeniedError(
                        f"符号链接逃逸拒绝: {original} -> {real}",
                        code="E_ACCESS_DENIED",
                    )

        if not os.path.exists(cand):
            raise MDRichPathError(f"目标路径不存在: {cand}", code="E_PATH_NOT_FOUND")

        # @artifacts 产物引用跳过扩展名白名单（产物由 runner export 产出，目录本身受控）
        if check_extension:
            ext = os.path.splitext(cand)[1].lower()
            if self.allowed_extensions and ext not in self.allowed_extensions:
                raise MDRichPathError(
                    f"扩展名不在白名单: {ext or '(无)'}",
                    code="E_UNSUPPORTED_EXT",
                )

        return cand

    def _within_any_root(self, path: str) -> bool:
        p = os.path.abspath(path)
        for r in self._allowed_roots:
            if p == r or p.startswith(r + os.sep):
                return True
        return False
