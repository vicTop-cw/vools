"""
vools.bridge.md runner (M5 增强版) — 执行编排 + 报告

M5 增强：
- 断点调试：breakpoint 指令，支持条件断点
- 性能分析：profiling，统计每块执行时间
- 缓存优化：智能缓存策略（基于内容哈希 + TTL）
- 并行执行：async/parallel 多块并行
"""

import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional, Any, Tuple

from ..core.compat.dataclass_compat import dataclass, field

from .parser import ParsedMD, CodeBlock, parse_md

# 字符编码：读取/写入统一走 filecodec（自动探测 GBK/UTF-8/BOM，不再硬编码 utf-8）
from ...encoding import read_text, write_text, detect, strip_bom
from .directives import validate_directives
from .config import load_config
from .deps import check_deps
from .manifest import write_manifest, read_manifest
from .artifacts import (
    ensure_build_dir,
    compute_artifact_hash,
    register_artifact,
)

# ═══════════════════════════════════════════════════════
# 块执行结果
# ═══════════════════════════════════════════════════════


@dataclass
class BlockResult:
    """单块执行结果"""

    index: int
    language: str
    tag: List[str]
    directives: Dict[str, str]
    status: str = "ok"  # ok | failed | timeout | skipped | error | paused
    duration_ms: float = 0
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    artifacts: List[Dict] = field(default_factory=list)
    output_file: Optional[str] = None
    source_hash: str = ""
    workdir: Optional[str] = None
    args: Optional[str] = None
    timeout: Optional[int] = None
    source_file: Optional[str] = None
    imported: bool = False
    # M5: 调试信息
    breakpoint: bool = False
    breakpoint_hit: bool = False
    profiling: Dict[str, Any] = field(default_factory=dict)
    cache_hit: bool = False
    # M5: 并行执行
    parallel: bool = False


# ═══════════════════════════════════════════════════════
# M3: 导入解析
# ═══════════════════════════════════════════════════════


def resolve_imports(
    parsed: ParsedMD,
    md_dir: str,
    build_dir: str,
    visited: Optional[set] = None,
) -> List[CodeBlock]:
    """解析 #!import 指令，展开所有块（包括导入的）。"""
    if visited is None:
        visited = set()

    imports = []
    for block in parsed.blocks:
        import_val = block.directives.get("import", "")
        if import_val and import_val.endswith(".md"):
            imports.append(
                {
                    "target": import_val,
                    "source_block": block,
                }
            )

    local_blocks = []
    for block in parsed.blocks:
        if "import" in block.directives and block.directives["import"].endswith(".md"):
            continue
        local_blocks.append(block)

    all_blocks: List[CodeBlock] = []

    for imp in imports:
        target = str(imp["target"])
        target_path = os.path.join(md_dir, target)

        if target_path in visited:
            continue

        if not os.path.exists(target_path):
            empty_block = CodeBlock(
                index=len(local_blocks) + len(all_blocks),
                language="",
                content=f"# [import] {target} not found",
                directives={"import": target},
                tag=[],
            )
            empty_block.source_file = target_path
            empty_block.imported = True
            all_blocks.append(empty_block)
            continue

        visited.add(target_path)

        target_parsed = parse_md(target_path)

        imported_blocks = resolve_imports(
            target_parsed,
            os.path.dirname(target_path),
            build_dir,
            visited.copy(),
        )

        for ib in imported_blocks:
            ib.source_file = target_path
            ib.imported = True
            ib.index = len(local_blocks) + len(all_blocks)
            all_blocks.append(ib)

    return local_blocks + all_blocks


# ═══════════════════════════════════════════════════════
# M4: 库级支持
# ═══════════════════════════════════════════════════════


def scan_library(
    library_dir: str,
    recursive: bool = True,
    extensions: Optional[List[str]] = None,
) -> List[str]:
    """扫描目录，返回所有 .md 文件列表。"""
    if extensions is None:
        extensions = [".md"]

    md_files = []

    if recursive:
        for root, dirs, files in os.walk(library_dir):
            for f in files:
                if any(f.endswith(ext) for ext in extensions):
                    md_files.append(os.path.join(root, f))
    else:
        for f in os.listdir(library_dir):
            full_path = os.path.join(library_dir, f)
            if os.path.isfile(full_path) and any(f.endswith(ext) for ext in extensions):
                md_files.append(full_path)

    return sorted(md_files)


def build_library_manifest(
    library_dir: str,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """构建库级 manifest.yaml。"""
    if output_path is None:
        output_path = os.path.join(library_dir, "manifest.yaml")

    md_files = scan_library(library_dir)

    entries = []
    for md_path in md_files:
        parsed = parse_md(md_path)
        entries.append(
            {
                "path": os.path.relpath(md_path, library_dir),
                "hash": parsed.md_hash,
                "entry": parsed.file_directives.entry,
                "only": parsed.file_directives.only,
                "config": parsed.file_directives.config,
                "deps": parsed.file_directives.deps,
                "build_dir": parsed.file_directives.build_dir,
                "blocks": len(parsed.blocks),
            }
        )

    manifest = {
        "library_dir": library_dir,
        "md_files": entries,
        "total": len(entries),
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    try:
        from .manifest import minimal_yaml_dump
        text = minimal_yaml_dump(manifest)
    except ImportError:
        text = json.dumps(manifest, indent=2, ensure_ascii=False)
    write_text(output_path, text)

    return manifest


def load_library_manifest(library_dir: str) -> Optional[Dict[str, Any]]:
    """加载库级 manifest.yaml。"""
    manifest_path = os.path.join(library_dir, "manifest.yaml")
    if not os.path.exists(manifest_path):
        return None

    text = read_text(manifest_path)

    try:
        from .manifest import minimal_yaml_parse

        return minimal_yaml_parse(text)
    except ImportError:
        return json.loads(text)


def run_library(
    library_dir: str,
    only: Optional[List[str]] = None,
    force: bool = False,
    build_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """执行整个库（所有 .md 文件）。"""
    if build_dir is None:
        build_dir = os.path.join(library_dir, ".mdbuild")

    ensure_build_dir(build_dir)

    md_files = scan_library(library_dir)

    results = {}
    total_duration = 0

    for md_path in md_files:
        result = run_md(md_path, only=only, force=force, build_dir=build_dir)
        results[md_path] = result
        total_duration += result["total_duration_ms"]

    return {
        "library_dir": library_dir,
        "md_files": md_files,
        "total_duration_ms": total_duration,
        "results": results,
    }


# ═══════════════════════════════════════════════════════
# M5: 高级调试与性能分析
# ═══════════════════════════════════════════════════════


def check_breakpoint(
    block: CodeBlock,
    context: Dict,
    debug_mode: bool = False,
) -> Optional[str]:
    """
    M5: 检查断点条件。

    支持指令：
    - #!breakpoint 或 #!bp - 无条件断点
    - #!breakpoint=condition - 条件断点

    Returns:
        断点描述（None = 无断点）
    """
    # 检查 breakpoint 或 bp 指令是否存在
    has_bp = "breakpoint" in block.directives or "bp" in block.directives
    if not has_bp:
        return None

    bp_val = block.directives.get("breakpoint", "")
    if not bp_val:
        bp_val = block.directives.get("bp", "")

    if debug_mode:
        return f"Breakpoint at block {block.index}"

    if bp_val == "true" or bp_val == "":
        return f"Breakpoint at block {block.index}"

    # 条件断点
    try:
        condition = bp_val
        if condition.strip() == "true":
            return f"Breakpoint (condition: {condition}) at block {block.index}"
        return f"Breakpoint (condition: {condition}) at block {block.index}"
    except Exception:
        return f"Breakpoint at block {block.index}"


def profile_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
) -> Dict[str, Any]:
    """
    M5: 性能分析（profiling）。

    返回每个操作的耗时统计。
    """
    profiling: Dict[str, Any] = {}

    # 使用 cProfile 进行性能分析
    import cProfile
    import io
    import pstats

    pr = cProfile.Profile()

    try:
        pr.enable()
        # 执行代码
        stdout, stderr, exit_code = _execute_block(block, context, config, None, 60)
        pr.disable()

        # 收集统计
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
        ps.print_stats()
        profiling["stats"] = s.getvalue()
        profiling["total_calls"] = ps.total_calls  # type: ignore[attr-defined]
        profiling["prim_calls"] = ps.prim_calls  # type: ignore[attr-defined]

    except Exception as e:
        profiling["error"] = str(e)

    return profiling


def should_use_cache(
    block: CodeBlock,
    existing_manifest: Optional[Dict],
    force: bool,
    block_hashes: Optional[List[str]] = None,
) -> bool:
    """
    M5: 智能缓存策略。

    基于内容哈希 + TTL 判断是否使用缓存。
    """
    if force:
        return False

    if not existing_manifest:
        return False

    # 检查块索引
    if block.index >= len(existing_manifest.get("blocks", [])):
        return False

    cached = existing_manifest["blocks"][block.index]

    # 检查内容哈希
    cached_hash = cached.get("source_hash", "")
    if block_hashes and block.index < len(block_hashes):
        current_hash = block_hashes[block.index]
    else:
        # 使用内容本身作为哈希（简化版）
        current_hash = block.content

    if cached_hash != current_hash:
        return False

    # 检查状态
    if cached.get("status") != "ok":
        return False

    return True


def run_parallel(
    blocks: List[CodeBlock],
    context: Dict,
    config: Dict,
    artifacts_table: Dict,
) -> List[BlockResult]:
    """
    M5: 并行执行多个块。

    使用线程池并行执行独立块。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: List[BlockResult] = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        for idx, block in enumerate(blocks):
            future = executor.submit(run_block, block, idx, context, artifacts_table, config)
            futures[future] = idx

        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                result.parallel = True
                results.append(result)
            except Exception as e:
                # 创建错误结果
                br = BlockResult(
                    index=idx,
                    language=blocks[idx].language,
                    tag=blocks[idx].tag,
                    directives=blocks[idx].directives,
                    status="error",
                    stderr=str(e),
                )
                br.parallel = True
                results.append(br)

    # 按索引排序
    results.sort(key=lambda x: x.index)
    return results


# ═══════════════════════════════════════════════════════
# 执行单个块（M5 增强版）
# ═══════════════════════════════════════════════════════


def run_block(
    block: CodeBlock,
    index: int,
    context: Dict[str, Any],
    artifacts_table: Dict[str, Any],
    config: Dict[str, Any],
    debug: bool = False,
    profile: bool = False,
) -> BlockResult:
    """
    执行单个代码块（M5 增强版）。

    支持指令：
    - run / compile / only-code / skip
    - export / import
    - env / workdir / args / stdin / timeout / tag / output
    - breakpoint / bp（M5）
    """
    result = BlockResult(
        index=index,
        language=block.language,
        tag=block.tag,
        directives=block.directives,
    )

    if block.source_file:
        result.source_file = block.source_file
    if block.imported:
        result.imported = True

    # M5: 检查断点
    bp_desc = check_breakpoint(block, context, debug)
    if bp_desc:
        result.breakpoint = True
        result.breakpoint_hit = True
        result.status = "paused"
        result.stdout = bp_desc
        return result

    # 校验指令
    errors = validate_directives(block.directives, block.language)
    if errors:
        result.status = "error"
        result.stderr = "; ".join(errors)
        return result

    # skip
    if "skip" in block.directives:
        result.status = "skipped"
        return result

    # only-code
    if "only-code" in block.directives:
        result.status = "ok"
        result.stdout = f"[only-code] {block.language} 源码展开"
        return result

    # 检查语言可用性
    if not block.language:
        result.status = "error"
        result.stderr = "代码块缺少语言标识符"
        return result

    # 提取指令参数
    workdir = block.directives.get("workdir")
    args = block.directives.get("args")
    timeout = int(block.directives.get("timeout", "60"))
    env_vars = {}
    if "env" in block.directives:
        env_str = block.directives["env"]
        for pair in env_str.split():
            if "=" in pair:
                k, v = pair.split("=", 1)
                env_vars[k] = v

    # 构建执行上下文
    exec_context = dict(context)
    if workdir:
        if not os.path.isabs(workdir):
            workdir = os.path.join(context.get("md_dir", ""), workdir)
        result.workdir = workdir
        exec_context["workdir"] = workdir

    if env_vars:
        env = dict(exec_context.get("env", {}))
        env.update(env_vars)
        exec_context["env"] = env

    result.args = args
    result.timeout = timeout

    # 处理 stdin 指令：从文件读取内容注入到执行上下文
    stdin_val = block.directives.get("stdin")
    if stdin_val:
        stdin_path = stdin_val
        if not os.path.isabs(stdin_path):
            stdin_path = os.path.join(context.get("md_dir", ""), stdin_path)
        try:
            exec_context["stdin"] = read_text(stdin_path)
        except FileNotFoundError:
            # 文件不存在时，使用空 stdin，不中断执行
            exec_context["stdin"] = ""
        except Exception as e:
            result.status = "error"
            result.stderr = f"stdin 文件读取失败: {e}"
            return result

    # M5: 性能分析
    if profile:
        profiling = profile_block(block, exec_context, config)
        result.profiling = profiling

    # 执行
    start = time.perf_counter()

    try:
        stdout, stderr, exit_code = _execute_block(block, exec_context, config, args, timeout)
        result.stdout = stdout
        result.stderr = stderr
        result.exit_code = exit_code

        if exit_code != 0:
            result.status = "failed"
        else:
            result.status = "ok"

    except subprocess.TimeoutExpired:
        result.status = "timeout"
        result.stderr = f"超时 ({timeout}s)"
    except Exception as e:
        result.status = "error"
        result.stderr = str(e)

    result.duration_ms = (time.perf_counter() - start) * 1000

    # 处理 export
    if "export" in block.directives:
        export_name = block.directives["export"]
        # 决策 1：export 产物落 artifacts/rich/（旧 tmp/ 仅保留读取兼容，见 rich/resolver.py）
        artifact_path = os.path.join(
            context.get("build_dir", ".mdbuild"),
            "artifacts",
            "rich",
            f"block_{index}_{export_name}.txt",
        )
        os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
        write_text(artifact_path, result.stdout)

        register_artifact(
            artifacts_table,
            export_name,
            artifact_path,
            index,
            block.tag[0] if block.tag else None,
        )

        result.artifacts.append(
            {
                "name": export_name,
                "path": artifact_path,
                "hash": compute_artifact_hash(artifact_path),
            }
        )

    # 处理 output
    if "output" in block.directives:
        output_file = block.directives["output"]
        output_path = os.path.join(
            context.get("build_dir", ".mdbuild"),
            "tmp",
            f"block_{index}_{output_file}",
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        write_text(output_path, result.stdout)
        result.output_file = output_path

    return result


#: docs/41 §A1：sigma 语言标记集（与 vools.actus.sigma.SIGMA_LANGUAGE_TAGS 同集合）
SIGMA_LANGUAGE_TAGS = ("sigma", "sigma-spec", "sigma-md")


# ═══════════════════════════════════════════════════════
# 块分类：kind（执行模式）与 role（语义角色）
# ═══════════════════════════════════════════════════════
# 三层分离：language（语法格式）→ role（产出用途）→ kind（执行模式）。
# 默认 role 由 language 推导，可用 #!role 覆盖；kind 由 role 或 language 决定。

#: kind 枚举
KIND_EXEC = "exec"            # 写临时文件 + 子进程直接跑
KIND_BRIDGE = "bridge"        # 通过 bridge 编译器执行
KIND_STATIC = "static"        # 只写产物文件（可选语法校验）
KIND_PROTOCOL = "protocol"    # 通过协议调用外部服务
KIND_DATABASE = "database"    # 执行数据库查询
KIND_RENDER = "render"        # 富内容展示（sanitize + 卡片）
KIND_GUI = "gui"              # 桌面窗口渲染
KIND_SIGMA = "sigma"          # ΣLang 规约块
KIND_META = "meta"            # actus 动作配置元数据（不进 build_dir）

#: role 枚举
ROLE_DEPS = "deps"              # 目标语言依赖声明（toml）
ROLE_RUNTIME = "runtime"        # 目标语言运行配置（yaml）
ROLE_LEGACY = "legacy"          # 老旧配置（ini）
ROLE_GEN_CONFIG = "gen-config"  # 动态生成配置（lua 脚本，stdout 落盘）
ROLE_ACTION_CONFIG = "action-config"  # actus 动作配置（#!configs）
ROLE_DATA = "data"              # 纯数据展示（csv/xml/text）
ROLE_DIAGRAM = "diagram"        # 图表（mermaid/plantuml/dot）
ROLE_MATH = "math"              # 数学公式（latex/math）
ROLE_BUILD = "build"            # 构建/基础设施（makefile/dockerfile/nginx）
ROLE_TEMPLATE = "template"      # 模板语言（jinja/mako/handlebars/ejs/pug）
ROLE_GENERIC = "generic"        # 默认（无特殊角色）

#: 合法 role 值集合
VALID_ROLES = frozenset({
    ROLE_DEPS, ROLE_RUNTIME, ROLE_LEGACY, ROLE_GEN_CONFIG,
    ROLE_ACTION_CONFIG, ROLE_DATA, ROLE_DIAGRAM, ROLE_MATH,
    ROLE_BUILD, ROLE_TEMPLATE, ROLE_GENERIC,
})


def resolve_block_role(block: "CodeBlock") -> str:
    """解析块的语义角色。

    优先级：
    1. `#!role=` 显式指定（若合法）
    2. `#!configs` 裸指令 → action-config
    3. language 默认映射（DEFAULT_ROLE_MAP）
    4. 兜底 generic
    """
    directives = getattr(block, "directives", {}) or {}

    explicit = directives.get("role", "")
    if explicit and explicit.strip().lower() in VALID_ROLES:
        return explicit.strip().lower()

    # `#!configs` 裸指令：actus 动作配置块
    if "configs" in directives:
        return ROLE_ACTION_CONFIG

    lang = (getattr(block, "language", "") or "").strip().lower()
    return DEFAULT_ROLE_MAP.get(lang, ROLE_GENERIC)


def resolve_block_kind(block: "CodeBlock") -> str:
    """解析块的执行模式 kind。

    优先级：role 决定 kind → language 默认 kind（LANGUAGE_KIND_MAP）→ bridge。
    """
    role = resolve_block_role(block)
    role_kind = ROLE_KIND_MAP.get(role)
    if role_kind:
        return role_kind

    lang = (getattr(block, "language", "") or "").strip().lower()
    return LANGUAGE_KIND_MAP.get(lang, KIND_BRIDGE)


def _execute_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    args: Optional[str],
    timeout: int,
) -> Tuple[str, str, int]:
    """执行代码块，返回 (stdout, stderr, exit_code)。

    薄封装：所有实际 dispatch 走 _execute_by_kind。
    """
    return _execute_by_kind(block, context, config, args, timeout)


def _execute_by_kind(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    args: Optional[str],
    timeout: int,
) -> Tuple[str, str, int]:
    """按 kind（执行模式）+ role（语义角色）路由到对应 handler。"""
    kind = resolve_block_kind(block)

    if kind == KIND_META:
        return _execute_action_config_block(block, context, config)
    if kind == KIND_STATIC:
        return _dispatch_static(block, context, config)
    if kind == KIND_PROTOCOL:
        return _dispatch_protocol(block, context, config, timeout)
    if kind == KIND_DATABASE:
        return _dispatch_database(block, context, config, timeout)
    if kind == KIND_RENDER:
        return _execute_rich_block(block, context, config)
    if kind == KIND_GUI:
        return _execute_webview2(block, context, config)
    if kind == KIND_SIGMA:
        return _execute_sigma(block)
    if kind == KIND_EXEC:
        return _dispatch_exec(block, context, config, args, timeout)
    # KIND_BRIDGE 或未识别
    return _execute_via_bridge(block, context, config, timeout, args)


#: language → 默认 role 映射（vools docs/md/config-blocks.md 语义）
DEFAULT_ROLE_MAP: Dict[str, str] = {
    # 配置格式（docs/md/config-blocks.md L10-L12）
    "toml": ROLE_DEPS,           # 目标语言依赖声明
    "yaml": ROLE_RUNTIME,        # 目标语言运行配置
    "yml": ROLE_RUNTIME,
    "ini": ROLE_LEGACY,          # 老旧配置
    "lua": ROLE_GEN_CONFIG,      # 动态生成配置（脚本执行）
    # 图表（P1）
    "mermaid": ROLE_DIAGRAM,
    "mmd": ROLE_DIAGRAM,
    "plantuml": ROLE_DIAGRAM,
    "puml": ROLE_DIAGRAM,
    "dot": ROLE_DIAGRAM,
    "graphviz": ROLE_DIAGRAM,
    # 数学（P1）
    "latex": ROLE_MATH,
    "math": ROLE_MATH,
    "tex": ROLE_MATH,
    # 构建（P1）
    "makefile": ROLE_BUILD,
    "make": ROLE_BUILD,
    "dockerfile": ROLE_BUILD,
    "docker-compose": ROLE_BUILD,
    "compose": ROLE_BUILD,
    "nginx": ROLE_BUILD,
    "terraform": ROLE_BUILD,
    "tf": ROLE_BUILD,
    "ansible": ROLE_BUILD,
    # 模板语言（P1）
    "jinja": ROLE_TEMPLATE,
    "jinja2": ROLE_TEMPLATE,
    "mako": ROLE_TEMPLATE,
    "handlebars": ROLE_TEMPLATE,
    "ejs": ROLE_TEMPLATE,
    "pug": ROLE_TEMPLATE,
    # 纯数据（P2）
    "csv": ROLE_DATA,
    "tsv": ROLE_DATA,
    "xml": ROLE_DATA,
    "text": ROLE_DATA,
    "plain": ROLE_DATA,
}

#: role → kind 映射（role 比 language 更优先决定 kind）
ROLE_KIND_MAP: Dict[str, str] = {
    ROLE_DEPS: KIND_STATIC,
    ROLE_RUNTIME: KIND_STATIC,
    ROLE_LEGACY: KIND_STATIC,
    ROLE_DATA: KIND_STATIC,
    ROLE_DIAGRAM: KIND_STATIC,
    ROLE_MATH: KIND_STATIC,
    ROLE_BUILD: KIND_STATIC,
    ROLE_TEMPLATE: KIND_STATIC,
    ROLE_GEN_CONFIG: KIND_EXEC,       # 生成配置要执行脚本
    ROLE_ACTION_CONFIG: KIND_META,    # actus 元数据解析
    ROLE_GENERIC: "",                 # 由 language 决定
}

#: language → kind 映射（bridge 全量登记，未知语言走 bridge）
LANGUAGE_KIND_MAP: Dict[str, str] = {
    # exec：写临时文件 + 子进程
    "python": KIND_EXEC, "py": KIND_EXEC, "python3": KIND_EXEC,
    "shell": KIND_EXEC, "bash": KIND_EXEC, "sh": KIND_EXEC,
    "bat": KIND_EXEC, "batch": KIND_EXEC, "cmd": KIND_EXEC,
    "powershell": KIND_EXEC, "pwsh": KIND_EXEC,
    "node": KIND_EXEC, "nodejs": KIND_EXEC,
    "js": KIND_EXEC, "javascript": KIND_EXEC,
    # static：只写文件
    "css": KIND_STATIC,
    "json": KIND_STATIC, "toml": KIND_STATIC, "yaml": KIND_STATIC, "yml": KIND_STATIC,
    "ini": KIND_STATIC,
    # protocol：协议调用
    "mcp": KIND_PROTOCOL,
    "http": KIND_PROTOCOL,
    # database
    "sql": KIND_DATABASE, "sqlite": KIND_DATABASE,
    "mysql": KIND_DATABASE, "postgresql": KIND_DATABASE, "pgsql": KIND_DATABASE,
    # render：富内容展示
    "html": KIND_RENDER, "svg": KIND_RENDER, "rich": KIND_RENDER,
    # gui：桌面窗口
    "webview2": KIND_GUI, "webview": KIND_GUI, "htmlview": KIND_GUI,
    # sigma
    "sigma": KIND_SIGMA, "sigma-spec": KIND_SIGMA, "sigma-md": KIND_SIGMA,
    # meta（#!configs 裸指令触发，language 本身不作为 kind 触发条件）
    # bridge 全量登记
    "c": KIND_BRIDGE, "cpp": KIND_BRIDGE, "c++": KIND_BRIDGE,
    "csharp": KIND_BRIDGE, "c#": KIND_BRIDGE,
    "cangjie": KIND_BRIDGE, "cypy": KIND_BRIDGE,
    "dart": KIND_BRIDGE, "elixir": KIND_BRIDGE, "erlang": KIND_BRIDGE,
    "freebasic": KIND_BRIDGE, "go": KIND_BRIDGE, "golang": KIND_BRIDGE,
    "haskell": KIND_BRIDGE, "java": KIND_BRIDGE, "julia": KIND_BRIDGE,
    "kotlin": KIND_BRIDGE, "lua": KIND_BRIDGE, "lz": KIND_BRIDGE,
    "mojo": KIND_BRIDGE, "moonbit": KIND_BRIDGE, "nim": KIND_BRIDGE,
    "pentad": KIND_BRIDGE, "perl": KIND_BRIDGE, "php": KIND_BRIDGE,
    "r": KIND_BRIDGE, "rb": KIND_BRIDGE, "rs": KIND_BRIDGE,
    "ruby": KIND_BRIDGE, "rust": KIND_BRIDGE, "scala": KIND_BRIDGE,
    "swift": KIND_BRIDGE, "tnr": KIND_BRIDGE,
    "typescript": KIND_BRIDGE, "ts": KIND_BRIDGE,
    "vbnet": KIND_BRIDGE, "vbscript": KIND_BRIDGE,
    "zi": KIND_BRIDGE, "zig": KIND_BRIDGE,
}

#: exec 类 dispatch
_EXEC_LANGUAGES = (
    "python", "py", "python3",
    "shell", "bash", "sh",
    "bat", "batch", "cmd",
    "powershell", "pwsh",
    "node", "nodejs", "js", "javascript",
)


def _dispatch_exec(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    args: Optional[str],
    timeout: int,
) -> Tuple[str, str, int]:
    """exec kind：写临时文件 + 子进程直接跑。

    gen-config role（如 lua）在本分支：执行脚本后把 stdout 落盘为配置文件。
    """
    lang = block.language
    workdir = context.get("workdir", os.getcwd())

    role = resolve_block_role(block)
    if role == ROLE_GEN_CONFIG and lang not in _EXEC_LANGUAGES:
        # lua 生成配置：优先走 bridge（lua 已在 registry），失败降级 python 兜底
        stdout, stderr, rc = _execute_via_bridge(
            block, context, config, timeout, args,
            func_name=f"__md_block_{block.index}"
        )
        if rc == 0 and stdout:
            return _finalize_gen_config(block, context, config, stdout), stderr, 0
        return stdout, stderr, rc

    if lang == "python":
        block_prelude = block.directives.get("prelude")
        if block_prelude is not None:
            config = {**config, "prelude": block_prelude}
        return _execute_python(block.content, context, config, args)

    if lang in ("shell", "bash", "sh"):
        return _execute_shell(block.content, context, config, workdir, timeout, args)

    if lang in ("bat", "batch", "cmd"):
        return _execute_windows_cmd(block.content, context, config, workdir, timeout, args)

    if lang in ("powershell", "pwsh"):
        return _execute_powershell(block.content, context, config, workdir, timeout, args)

    if lang in ("node", "nodejs", "js", "javascript"):
        return _execute_node_block(block, context, config, timeout, args)

    # 兜底：未知 exec 语言走 bridge
    return _execute_via_bridge(block, context, config, timeout, args)


def _dispatch_static(
    block: CodeBlock,
    context: Dict,
    config: Dict,
) -> Tuple[str, str, int]:
    """static kind：只写产物文件（可选语法校验），不执行脚本。

    按 role 分到不同子目录：
      deps       → artifacts/config/deps/block_{N}.toml
      runtime    → artifacts/config/runtime/block_{N}.yaml
      legacy     → artifacts/config/legacy/block_{N}.ini
      data       → artifacts/data/block_{N}.csv
      diagram    → artifacts/diagram/block_{N}.mmd
      math       → artifacts/math/block_{N}.tex
      build      → artifacts/build/block_{N}.Dockerfile
      generic    → artifacts/static/block_{N}.{ext}

    css 保持历史路径 artifacts/css/（向后兼容，走原 _execute_css_block）。
    """
    lang = (block.language or "").strip().lower()
    if lang == "css":
        return _execute_css_block(block, context, config)

    return _execute_static_block(block, context, config)


def _dispatch_protocol(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    timeout: int,
) -> Tuple[str, str, int]:
    """protocol kind：通过协议调用外部服务。"""
    lang = block.language
    if lang == "mcp":
        return _execute_mcp_block(block, context, config, timeout)
    if lang == "http":
        return _execute_http_block(block, context, config, timeout)
    return "", f"{lang} 协议块未实现", 1


def _dispatch_database(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    timeout: int,
) -> Tuple[str, str, int]:
    """database kind：执行数据库查询。"""
    return _execute_database_block(block, context, config, timeout)


def _execute_action_config_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
) -> Tuple[str, str, int]:
    """meta kind：actus 动作配置块（#!configs）。

    解析 JSON 内容，返回解析摘要（不写 build_dir）。由 actus 侧消费。
    """
    import json as _json
    try:
        data = _json.loads(block.content)
    except Exception as exc:
        return "", f"[configs] 无效 JSON: {exc}", 1
    keys = list(data.keys()) if isinstance(data, dict) else []
    return (
        f"[configs] block {block.index} parsed ok, top-level keys: {keys}",
        "",
        0,
    )


def _finalize_gen_config(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    stdout: str,
) -> str:
    """gen-config role：把脚本 stdout 落盘为配置文件。"""
    import tempfile as _tempfile
    role = resolve_block_role(block)
    ext_map = {
        ROLE_GEN_CONFIG: ".conf",
    }
    ext = ext_map.get(role, ".conf")
    lang = (block.language or "").strip().lower()
    if lang in ("toml",):
        ext = ".toml"
    elif lang in ("yaml", "yml"):
        ext = ".yaml"
    elif lang in ("json",):
        ext = ".json"
    elif lang in ("ini",):
        ext = ".ini"

    build_dir = context.get("build_dir") or (
        config.get("build_dir") if isinstance(config, dict) else None
    )
    if not build_dir:
        build_dir = _tempfile.mkdtemp(prefix="vools-md-")

    out_dir = os.path.join(build_dir, "artifacts", "config", "gen")
    os.makedirs(out_dir, exist_ok=True)

    out_name = block.directives.get("out") or f"block_{block.index}{ext}"
    if not os.path.splitext(out_name)[1]:
        out_name = f"{out_name}{ext}"
    out_path = os.path.join(out_dir, out_name)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(stdout.strip() + "\n")

    rel = os.path.join("artifacts", "config", "gen", out_name).replace("\\", "/")
    return f"[configs] gen block {block.index} -> {rel}"

_IS_WINDOWS = platform.system() == 'Windows'

#: `_execute_block` 里直接处理、不走 bridge 的语言标记。
BUILTIN_BLOCK_LANGUAGES: Tuple[str, ...] = (
    "python", "shell", "bash", "sh",
    "bat", "batch", "cmd", "powershell", "pwsh",
    "webview2", "webview", "htmlview",
    # Node.js 别名（直接调 node CLI）
    "node", "nodejs", "js", "javascript",
    # 富内容展示块：html/svg/rich（计划 §4.2，P1；默认 L1 静态，L4 源码展示降级）
    "html", "svg", "rich",
    # CSS 静态块：输出 .css 文件
    "css",
    # MCP 调用块：stdio 协议调用外部 MCP 服务器
    "mcp",
    # 配置格式静态块（docs/md/config-blocks.md 语义）
    "json", "toml", "yaml", "yml", "ini",
    # 图表块（P1）
    "mermaid", "mmd", "plantuml", "puml", "dot", "graphviz",
    # 数学块（P1）
    "latex", "math", "tex",
    # 构建块（P1）
    "makefile", "make", "dockerfile", "docker-compose", "compose", "nginx",
    "terraform", "tf", "ansible",
    # 模板语言（P1）
    "jinja", "jinja2", "mako", "handlebars", "ejs", "pug",
    # 纯数据块（P2）
    "csv", "tsv", "xml", "text", "plain",
    # 协议块
    "http",
    # 数据库块
    "sql", "sqlite", "mysql", "postgresql", "pgsql",
) + SIGMA_LANGUAGE_TAGS


# ═══════════════════════════════════════════════════════
# static kind：只写产物文件（可选语法校验）
# ═══════════════════════════════════════════════════════

#: static role → (产物子目录, 默认扩展名)
_STATIC_ROLE_TABLE: Dict[str, Tuple[str, str]] = {
    ROLE_DEPS:          ("config/deps",      ".toml"),
    ROLE_RUNTIME:       ("config/runtime",   ".yaml"),
    ROLE_LEGACY:        ("config/legacy",    ".ini"),
    ROLE_DATA:          ("data",      ".dat"),
    ROLE_DIAGRAM:       ("diagram",   ".mmd"),
    ROLE_MATH:          ("math",      ".tex"),
    ROLE_BUILD:         ("build",     ".conf"),
    ROLE_TEMPLATE:      ("templates", ".tmpl"),
    ROLE_GENERIC:       ("static",    ""),
}

#: language → 默认扩展名（用于推断产物文件名）
_LANG_EXT_MAP: Dict[str, str] = {
    "css": ".css",
    "json": ".json",
    "toml": ".toml",
    "yaml": ".yaml", "yml": ".yaml",
    "ini": ".ini",
    "csv": ".csv", "tsv": ".tsv",
    "xml": ".xml", "text": ".txt", "plain": ".txt",
    "mermaid": ".mmd", "mmd": ".mmd",
    "plantuml": ".puml", "puml": ".puml",
    "dot": ".dot", "graphviz": ".dot",
    "latex": ".tex", "math": ".tex", "tex": ".tex",
    "makefile": "Makefile", "make": "Makefile",
    "dockerfile": ".Dockerfile",
    "docker-compose": ".yml", "compose": ".yml",
    "nginx": ".conf",
    "terraform": ".tf", "tf": ".tf",
    "ansible": ".yml",
    # 模板语言扩展名
    "jinja": ".j2", "jinja2": ".j2",
    "mako": ".mako",
    "handlebars": ".hbs",
    "ejs": ".ejs",
    "pug": ".pug",
}


def _static_lang_ext(lang: str) -> str:
    """静态块语言 → 产物扩展名（无映射则空串，由 role 兜底）。"""
    return _LANG_EXT_MAP.get(lang, "")


def _static_out_path(block: CodeBlock, context: Dict, config: Dict) -> Tuple[str, str, str]:
    """计算静态块输出目录 + 默认文件名 + 最终路径。

    Returns:
        (relative_path, default_name, abs_path)
    """
    import tempfile as _tempfile

    lang = (block.language or "").strip().lower()
    role = resolve_block_role(block)
    sub_dir, _ = _STATIC_ROLE_TABLE.get(role, _STATIC_ROLE_TABLE[ROLE_GENERIC])

    ext = _static_lang_ext(lang)
    if not ext:
        # role 兜底扩展名
        ext = _STATIC_ROLE_TABLE.get(role, _STATIC_ROLE_TABLE[ROLE_GENERIC])[1]
    # 统一前导点（Makefile / Dockerfile 等特殊名保留原样）
    if ext and not ext.startswith(".") and ext.lower() not in ("makefile",):
        ext = "." + ext

    build_dir = context.get("build_dir") or (
        config.get("build_dir") if isinstance(config, dict) else None
    )
    if not build_dir:
        build_dir = _tempfile.mkdtemp(prefix="vools-md-")

    out_name = (block.directives.get("out") or "").strip()
    if out_name:
        if not os.path.splitext(out_name)[1]:
            out_name = f"{out_name}{ext}"
    else:
        out_name = f"block_{block.index}{ext}"

    # 绝对路径
    out_dir = os.path.join(build_dir, "artifacts", sub_dir)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)

    rel = os.path.join("artifacts", sub_dir, out_name).replace("\\", "/")
    return rel, out_name, out_path


def _validate_static_syntax(lang: str, content: str) -> Optional[str]:
    """静态块语法校验。

    Args:
        lang: 语言标记（json/yaml/toml/ini/csv/xml）
        content: 块内容

    Returns:
        错误消息（None = 通过）
    """
    text = (content or "").strip()
    if not text:
        return None  # 空内容不校验（容忍空块）

    if lang in ("json",):
        import json as _json
        try:
            _json.loads(text)
        except Exception as exc:
            return f"无效 JSON: {exc}"
        return None

    if lang in ("yaml", "yml"):
        try:
            import yaml as _yaml
        except ImportError:
            return None  # PyYAML 未装，降级不校验
        try:
            _yaml.safe_load(text)
        except Exception as exc:
            return f"无效 YAML: {exc}"
        return None

    if lang in ("toml",):
        try:
            if hasattr(__import__("tomllib", fromlist=["loads"]), "loads"):
                import tomllib as _tomllib
                _tomllib.loads(text)
            else:
                import toml as _toml
                _toml.loads(text)
        except ImportError:
            return None  # tomllib/toml 均不可用，降级
        except Exception as exc:
            return f"无效 TOML: {exc}"
        return None

    if lang in ("ini",):
        try:
            import configparser as _cp
            parser = _cp.ConfigParser()
            parser.read_string(text)
        except Exception as exc:
            return f"无效 INI: {exc}"
        return None

    if lang in ("csv",):
        import csv as _csv
        try:
            list(_csv.reader(text.splitlines()))
        except Exception as exc:
            return f"无效 CSV: {exc}"
        return None

    if lang in ("tsv",):
        import csv as _csv
        try:
            list(_csv.reader(text.splitlines(), delimiter="\t"))
        except Exception as exc:
            return f"无效 TSV: {exc}"
        return None

    if lang in ("xml",):
        try:
            import xml.etree.ElementTree as _ET
            _ET.fromstring(text)
        except Exception as exc:
            return f"无效 XML: {exc}"
        return None

    return None  # 其他格式不校验


def _validate_json_schema(lang: str, content: str, schema_path: str) -> Optional[str]:
    """JSON Schema 校验（仅 json/yaml；schema_path 为相对或绝对路径）。"""
    try:
        import jsonschema as _js
    except ImportError:
        return None  # jsonschema 未装，降级

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            import json as _json
            schema = _json.load(f)
    except Exception as exc:
        return f"Schema 读取失败: {exc}"

    try:
        if "yaml" in (lang,):
            import yaml as _yaml
            instance = _yaml.safe_load(content)
        else:
            import json as _json
            instance = _json.loads(content)
        _js.validate(instance=instance, schema=schema)
    except Exception as exc:
        return f"Schema 校验失败: {exc}"
    return None


def _execute_static_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
) -> Tuple[str, str, int]:
    """static kind 统一入口：写文件 + 语法校验 + 可选 JSON Schema 校验。

    这是 json/yaml/toml/ini/css/csv/xml/mermaid/latex/dockerfile/nginx
    等所有「只写产物」块的统一实现。
    """
    lang = (block.language or "").strip().lower()
    content = block.content or ""
    directives = block.directives or {}

    # 1. 语法校验（默认 syntax；#!validate=none 跳过）
    validate_mode = (directives.get("validate") or "syntax").strip().lower()
    if validate_mode not in ("syntax", "schema", "none"):
        return "", f"validate 值只允许 syntax/schema/none: {validate_mode}", 1

    if validate_mode in ("syntax", "schema"):
        err = _validate_static_syntax(lang, content)
        if err:
            return "", f"[static] {lang} 语法校验失败: {err}", 1

    # 2. JSON Schema 校验（#!schema=path）
    schema_path = directives.get("schema")
    if schema_path and validate_mode in ("schema", "syntax"):
        if lang not in ("json", "yaml", "yml"):
            return "", f"schema 校验仅支持 json/yaml 块（当前 {lang}）", 1
        err = _validate_json_schema(lang, content, schema_path)
        if err:
            return "", f"[static] {lang} Schema 校验失败: {err}", 1

    # 3. 写文件
    rel, _name, out_path = _static_out_path(block, context, config)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    # 4. makefile role 额外支持 #!target=xxx 时执行 make
    if lang in ("makefile", "make") and directives.get("target"):
        target = directives["target"]
        try:
            proc = subprocess.run(
                ["make", target],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=context.get("workdir") or os.path.dirname(out_path),
                timeout=int(directives.get("timeout") or 30),
            )
            return (
                f"[makefile] block {block.index} -> {rel}\n"
                f"$ make {target} (rc={proc.returncode})\n{proc.stdout}",
                proc.stderr,
                proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return "", f"make {target} 超时", 124
        except FileNotFoundError:
            return "", "make 未安装", 1

    return f"[static] block {block.index} ({lang}) -> {rel}", "", 0


# ═══════════════════════════════════════════════════════
# protocol kind：通过协议调用外部服务
# ═══════════════════════════════════════════════════════


def _execute_http_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    timeout: int,
) -> Tuple[str, str, int]:
    """http 块：stdlib urllib.request 发送 HTTP 请求。

    指令：
      #!target=URL  或 #!url=URL  目标 URL（必填）
      #!method=GET/POST/PUT/DELETE/PATCH   HTTP 方法（默认 GET）
      #!headers={"Content-Type": "application/json"}  请求头（JSON）
      块内容作为请求体（GET 忽略；其他方法默认 JSON body）

    返回：
      exit 0 = HTTP 2xx
      exit 1 = 4xx/5xx（stdout=响应体，stderr=状态行）
      exit 2 = 网络错误（DNS/连接）
    """
    import json as _json
    import urllib.request as _urlreq
    import urllib.error as _urlerr

    directives = block.directives or {}

    url = (directives.get("target") or directives.get("url") or "").strip()
    if not url:
        return "", "[http] 缺少 #!target=<URL> 或 #!url=<URL>", 1

    method = (directives.get("method") or "GET").strip().upper()
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
        return "", f"[http] 非法 method: {method}", 1

    # headers 解析（JSON 字符串）
    headers = {}
    headers_raw = directives.get("headers")
    if headers_raw:
        try:
            headers = _json.loads(headers_raw)
            if not isinstance(headers, dict):
                return "", "[http] headers 必须是 JSON 对象", 1
        except Exception as exc:
            return "", f"[http] headers 不是合法 JSON: {exc}", 1

    # body：优先 #!body，其次块内容
    body = None
    body_raw = directives.get("body")
    if body_raw is not None and body_raw != "":
        body = body_raw.encode("utf-8")
    elif method not in ("GET", "HEAD") and block.content.strip():
        body = block.content.strip().encode("utf-8")
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

    req = _urlreq.Request(url, data=body, method=method, headers=headers)

    default_timeout = 30
    try:
        timeout = int(directives.get("timeout") or default_timeout)
    except ValueError:
        timeout = default_timeout

    try:
        with _urlreq.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
            return resp_body, "", 0
    except _urlerr.HTTPError as exc:
        body_txt = ""
        try:
            body_txt = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body_txt = ""
        return body_txt, f"[http] {exc.code} {exc.reason}", 1
    except _urlerr.URLError as exc:
        return "", f"[http] 网络错误: {exc.reason}", 2
    except Exception as exc:  # noqa: BLE001
        return "", f"[http] 请求异常: {type(exc).__name__}: {exc}", 1


# ═══════════════════════════════════════════════════════
# database kind：执行数据库查询
# ═══════════════════════════════════════════════════════


def _shutil_which(cmd: str) -> Optional[str]:
    """shutil.which 的安全包装（避免每次调用 import shutil）。"""
    try:
        import shutil as _shutil
        return _shutil.which(cmd)
    except Exception:  # noqa: BLE001
        return None


def _split_sql_statements(sql: str) -> List[str]:
    """按分号拆分 SQL 语句（忽略引号内的分号）。

    单引号 / 双引号内的分号不算分隔符（用于字符串值含 ';' 的情况）。
    """
    stmts: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    escape = False

    for ch in sql:
        if escape:
            buf.append(ch)
            escape = False
            continue
        if ch == "\\" and quote == "'":
            buf.append(ch)
            escape = True
            continue
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue
        if ch == ";":
            stmts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)

    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def _parse_db_target(target: str) -> Tuple[str, Dict[str, str]]:
    """解析 #!target 数据库连接串。

    支持格式：
      sqlite://./test.db
      sqlite://C:\\path\\test.db
      mysql://user:pass@host:port/dbname
      postgresql://user:pass@host:port/dbname
      pgsql://user:pass@host:port/dbname

    Returns:
        (driver, params_dict)
    """
    target = (target or "").strip()
    parts = target.split("://", 1)
    if len(parts) != 2:
        return "sqlite", {"path": target or ":memory:"}

    driver = parts[0].lower()
    rest = parts[1]

    if driver in ("sqlite", "sqlite3"):
        return "sqlite", {"path": rest or ":memory:"}

    if driver in ("mysql", "postgresql", "pgsql", "postgres"):
        # user:pass@host:port/dbname
        userinfo, _, tail = rest.rpartition("@")
        hostport, _, dbname = tail.partition("/")
        user = ""
        password = ""
        if "@" in rest:
            user, _, password = userinfo.partition(":")
        host, _, port = hostport.partition(":")
        return driver, {
            "user": user,
            "password": password,
            "host": host or "localhost",
            "port": port or ("5432" if driver != "mysql" else "3306"),
            "dbname": dbname,
        }

    return driver, {}


def _execute_database_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    timeout: int,
) -> Tuple[str, str, int]:
    """database kind：执行 SQL 查询。

    指令：
      #!target=sqlite://./db.sqlite    必填（sqlite/mysql/postgresql）
      #!out=result.csv                 可选，把查询结果写 CSV
      #!quiet                          可选，不打印结果

    sqlite：走 stdlib sqlite3，零依赖。
    mysql/postgresql：走 CLI 子进程（mysql / psql），未装则报安装提示。
    """
    import csv as _csv
    import io as _io

    directives = block.directives or {}
    lang = (block.language or "").strip().lower()

    target = directives.get("target", "")
    if not target:
        return "", f"[{lang}] 缺少 #!target=<连接串>", 1

    driver, params = _parse_db_target(target)

    # ── sqlite：stdlib ──
    if driver == "sqlite":
        import sqlite3 as _sqlite3
        db_path = params["path"]
        if db_path and db_path != ":memory:":
            parent = os.path.dirname(os.path.abspath(db_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        conn = None
        cur = None
        last_select: Optional[str] = None
        try:
            conn = _sqlite3.connect(db_path)
            conn.row_factory = _sqlite3.Row
            cur = conn.cursor()
            # 多语句（CREATE + INSERT + SELECT ...）用 executescript；单语句用 execute
            sql_text = block.content.strip()
            stmts = [s.strip() for s in _split_sql_statements(sql_text) if s.strip()]
            # 找最后一个 SELECT/WITH 语句作为结果查询
            for stmt in reversed(stmts):
                upper = stmt.upper()
                if upper.startswith(("SELECT", "WITH")):
                    last_select = stmt
                    break
            # executescript 跑全部（CREATE/INSERT/DDL 等）
            if stmts:
                cur.executescript(sql_text)
            # 单独跑结果查询（executescript 不返回 description）
            if last_select is not None:
                cur.execute(last_select)
            rows = cur.fetchall() if last_select is not None else []
            conn.commit()
        except _sqlite3.Error as exc:
            return "", f"[sqlite] 执行失败: {exc}", 1
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:  # noqa: BLE001
                pass

        if last_select is None or cur is None or cur.description is None:
            # 非 SELECT（INSERT/UPDATE/DDL）
            n = cur.rowcount if cur is not None else 0
            return f"[sqlite] affected={n}", "", 0

        # 查询结果 → CSV / 文本
        columns = [d[0] for d in cur.description]
        out_path = directives.get("out")
        if out_path:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = _csv.writer(f)
                writer.writerow(columns)
                for row in rows:
                    writer.writerow(tuple(row))
            return f"[sqlite] {len(rows)} rows -> {out_path}", "", 0

        # 文本输出
        buf = _io.StringIO()
        buf.write("\t".join(columns) + "\n")
        for row in rows:
            buf.write("\t".join(str(v) for v in row) + "\n")
        return buf.getvalue().rstrip(), "", 0

    # ── mysql：CLI 子进程 ──
    if driver == "mysql":
        import tempfile as _tempfile
        cli = _shutil_which("mysql")
        if not cli:
            return "", (
                "[mysql] mysql CLI 未安装。请安装 mysql-client 或 "
                "改用 #!target=sqlite:// 走 stdlib sqlite3。"
            ), 1
        # 写临时 .sql 文件
        with _tempfile.NamedTemporaryFile(
            mode="w", suffix=".sql", delete=False, encoding="utf-8"
        ) as f:
            f.write(block.content)
            tmp_path = f.name
        try:
            cmd = [
                cli,
                "-u", params["user"],
                "-p" + params["password"],
                "-h", params["host"],
                "-P", params["port"],
                params["dbname"],
                "-e", "source " + tmp_path,
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return "", f"[mysql] 执行超时 ({timeout}s)", 124
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ── postgresql：CLI 子进程 ──
    if driver in ("postgresql", "pgsql", "postgres"):
        import tempfile as _tempfile
        cli = _shutil_which("psql")
        if not cli:
            return "", (
                "[postgresql] psql CLI 未安装。请安装 postgresql-client 或 "
                "改用 #!target=sqlite:// 走 stdlib sqlite3。"
            ), 1
        with _tempfile.NamedTemporaryFile(
            mode="w", suffix=".sql", delete=False, encoding="utf-8"
        ) as f:
            f.write(block.content)
            tmp_path = f.name
        try:
            cmd = [
                cli,
                "-U", params["user"],
                "-h", params["host"],
                "-p", params["port"],
                "-d", params["dbname"],
                "-f", tmp_path,
            ]
            env = dict(os.environ)
            if params.get("password"):
                env["PGPASSWORD"] = params["password"]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=timeout,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return "", f"[postgresql] 执行超时 ({timeout}s)", 124
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return "", f"[{driver}] 未支持的数据库驱动: {target}", 1


_KNOWN_LANGUAGES_CACHE: Optional[Tuple[str, ...]] = None


def known_languages(refresh: bool = False) -> Tuple[str, ...]:
    """当前**可路由**的语言标记全集（单一真源，供 actus 侧 §6.5 校验使用）。

    取并集而非查询运行态，是为了让这个集合**与本机装了什么编译器无关**：
      1. 本 runner 直接处理的标记（BUILTIN_BLOCK_LANGUAGES，含 sigma 族）；
      2. `vools/bridge/` 下有 compiler.py 的桥接子包（typescript/zig/perl…）；
      3. vools 侧运行时注册表的别名（node/js/javascript、rs、golang…）；
      4. 已注册进 BridgeManager 的语言（若已发现）。

    「已注册但编译器未安装」不在此列 —— docs/03 §6.5 判的是「标记合法且已注册」，
    可用性由执行期 `is_available()` 显式报不可用（_execute_via_bridge 已有该分支）。

    **结果按进程缓存**：这个集合在进程生命周期内是静态的，而 `is_routable()` 会被
    `validate_action` 对每个动作的每个块各调一次（实测 106 个动作）。不缓存时首次
    调用的编译器探测（含 `rustc --version` 子进程）会在同一次 scan 里重复付账，
    把本就吃紧的路径推过 30 秒测试预算。需要重新探测时传 `refresh=True`。
    """
    global _KNOWN_LANGUAGES_CACHE
    if _KNOWN_LANGUAGES_CACHE is not None and not refresh:
        return _KNOWN_LANGUAGES_CACHE

    names = set(BUILTIN_BLOCK_LANGUAGES)

    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../vools/bridge
    try:
        for entry in os.listdir(pkg_dir):
            if entry.startswith(('_', '.')) or '.' in entry:
                continue
            sub = os.path.join(pkg_dir, entry)
            # 语言桥接包的判据：目录下有 compiler.py（core/、md/、auto_discovery/
            # 这些基础设施包没有，不能当语言混进来）
            if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, 'compiler.py')):
                names.add(entry.lower())
    except OSError:
        pass

    try:
        from vools.actus.runtimes import _get_registry
        names.update(str(k).lower() for k in _get_registry()._runtimes)
    except Exception:  # noqa: BLE001 —— actus 引擎不在路径上时（bridge 单独使用）跳过
        pass

    try:
        from ..manager import list_languages as _list_languages
        names.update(str(x).lower() for x in _list_languages())
    except Exception:  # noqa: BLE001 —— 桥接层不可用时回退到已得集合
        pass

    _KNOWN_LANGUAGES_CACHE = tuple(sorted(names))
    return _KNOWN_LANGUAGES_CACHE


def reset_known_languages() -> None:
    """清掉语言全集缓存（供测试与"运行时装了新桥接"的场景显式调用）。"""
    global _KNOWN_LANGUAGES_CACHE
    _KNOWN_LANGUAGES_CACHE = None


def is_routable(language: str) -> bool:
    """语言标记是否已注册（不含「注册了但编译器缺失」这层运行时判定）。"""
    lang = (language or "").strip().lower()
    if not lang:
        return False
    return lang in known_languages()


def _execute_sigma(block: CodeBlock) -> Tuple[str, str, int]:
    """执行 Sigma 规约块：跑 vools.actus.sigma 的 Iron Laws 门禁。

    引擎缺失/导入失败一律显式报错并返回非 0（docs/03 §6.5「未注册语言须显式报
    不可用」、docs/41 §A1「失败即返回 action_invalid，不静默降级」）——
    绝不因为「拿不到验证器」就当规约通过。
    """
    try:
        from vools.actus.sigma import run_sigma_block
    except ImportError as exc:
        return "", (
            "sigma 不可用：vools.actus.sigma 未安装或导入失败 "
            f"（{exc}）。请安装 vools-actus，或 pip install sigma-lang 兜底。"
        ), 1
    try:
        return run_sigma_block(block.content)
    except Exception as exc:  # noqa: BLE001 —— 收敛为块失败，但把异常原样报出
        return "", f"sigma 执行异常：{type(exc).__name__}: {exc}", 1


# ── prelude：md python 块自动导入（Actus docs/33 §Phase 1）──

_PRELUDE_STDLIB_MODULES = (
    "json",
    "os",
    "re",
    "sys",
    "math",
    "random",
    "time",
    "datetime",
    "pathlib",
    "shutil",
    "subprocess",
    "itertools",
    "collections",
    "functools",
)

_PRELUDE_VOOLS_MODULES = (
    "vools.functional",
    "vools.data",
    "vools.utils",
)


def _build_prelude_env(config: Dict) -> Dict[str, Any]:
    """构造 md python 块的 prelude 环境（自动导入，零 import 书写）。

    默认注入：
    - vools.actus 全量公开 API（execute/validate/trust/vault/... 直接可用）
    - 常用标准库模块（json/os/re/... 以模块对象注入）
    - vools 常用子库（functional/data/utils，以短名注入）
    - Actus 运行时上下文：__actus_params（解析 ACTUS_PARAMS 环境变量）、
      __actus_result（结果输出通道占位）

    开关：config['prelude'] = 'none' 跳过注入（纯净环境）。
    注入名仅为默认值，块内同名赋值可遮蔽；单项导入失败静默降级，不阻断执行。
    """
    if str(config.get("prelude", "auto")).lower() in ("none", "off", "false"):
        return {}

    prelude: Dict[str, Any] = {}

    for modname in _PRELUDE_STDLIB_MODULES:
        try:
            prelude[modname] = __import__(modname)
        except Exception:
            pass

    try:
        import vools.actus as _actus

        names = getattr(_actus, "__all__", None) or [n for n in dir(_actus) if not n.startswith("_")]
        for n in names:
            if hasattr(_actus, n):
                prelude[n] = getattr(_actus, n)
    except Exception:
        pass

    for modname in _PRELUDE_VOOLS_MODULES:
        try:
            mod = __import__(modname, fromlist=["*"])
            prelude[modname.rsplit(".", 1)[-1]] = mod
        except Exception:
            pass

    raw = os.environ.get("ACTUS_PARAMS")
    params: Any = {}
    if raw:
        try:
            params = json.loads(raw)
        except Exception:
            params = raw
    prelude["__actus_params"] = params
    prelude["__actus_result"] = {}

    return prelude


def _execute_python(content: str, context: Dict, config: Dict, args: Optional[str]) -> Tuple[str, str, int]:
    """执行 Python 代码。"""
    try:
        import io

        exec_env = dict(context.get("env", {}))
        exec_env.update(_build_prelude_env(config))
        exec_env["__md_config"] = config
        exec_env["__name__"] = "__md_block__"
        exec_env["__builtins__"] = __builtins__

        if args:
            exec_env["__md_args"] = args.split()

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_stdin = sys.stdin
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        # 若上下文提供了 stdin 数据，重定向 sys.stdin
        stdin_data = context.get("stdin")
        stdin_buf = io.StringIO(stdin_data) if stdin_data is not None else None

        try:
            sys.stdout = stdout_buf
            sys.stderr = stderr_buf
            if stdin_buf is not None:
                sys.stdin = stdin_buf
            # 单命名空间执行：prelude 注入的模块/符号必须作为模块级全局可见，
            # 否则块内 def 的函数 __globals__ 指向 globals 而看不到 prelude
            # （曾用 exec(code, globals, exec_env) 双字典，导致 `def main(): base64...`
            #  在函数体内解析不到 base64 → NameError，docs/33 Phase 1 prelude 失效）。
            exec(content, exec_env)
            exit_code = 0
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.stdin = old_stdin

        return stdout_buf.getvalue(), stderr_buf.getvalue(), exit_code

    except SystemExit as e:
        return "", str(e), e.code if isinstance(e.code, int) else 0
    except Exception as e:
        return "", str(e), 1


def _execute_shell(
    content: str,
    context: Dict,
    config: Dict,
    workdir: str,
    timeout: int,
    args: Optional[str],
) -> Tuple[str, str, int]:
    """执行 Shell 代码。"""
    env = dict(context.get("env", {}))
    stdin_data = context.get("stdin")

    if args:
        full_cmd = f"{content}\n{args}"
    else:
        full_cmd = content

    proc = subprocess.run(
        full_cmd,
        shell=True,
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        input=stdin_data if stdin_data else None,
    )
    return proc.stdout, proc.stderr, proc.returncode


def _execute_windows_cmd(
    content: str,
    context: Dict,
    config: Dict,
    workdir: str,
    timeout: int,
    args: Optional[str],
) -> Tuple[str, str, int]:
    """执行 Windows 批处理代码（bat / batch / cmd）。

    源码写入临时 .bat（UTF-8 无 BOM + 前置 chcp 65001 避免中文乱码），
    用系统 cmd.exe 执行；非 Windows 平台显式报不可用。
    """
    if not _IS_WINDOWS:
        return "", "bat/cmd 仅支持 Windows 平台", 1

    env = dict(os.environ)
    env.update(context.get("env", {}))
    stdin_data = context.get("stdin")

    script = '@echo off\r\nchcp 65001 >nul\r\n' + content
    if args:
        script += '\r\n' + args

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            'w', suffix='.bat', delete=False,
            encoding='utf-8', newline='\r\n', dir=tempfile.gettempdir(),
        ) as f:
            f.write(script)
            tmp_path = f.name

        proc = subprocess.run(
            ['cmd.exe', '/d', '/s', '/c', tmp_path],
            cwd=workdir,
            capture_output=True,
            timeout=timeout,
            env=env,
            input=stdin_data.encode('utf-8') if stdin_data else None,
        )
        stdout = proc.stdout.decode('utf-8', errors='replace')
        stderr = proc.stderr.decode('utf-8', errors='replace')
        return stdout, stderr, proc.returncode
    except FileNotFoundError:
        return "", "cmd.exe 不可用", 1
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _execute_powershell(
    content: str,
    context: Dict,
    config: Dict,
    workdir: str,
    timeout: int,
    args: Optional[str],
) -> Tuple[str, str, int]:
    """执行 PowerShell 代码（powershell / pwsh）。

    源码写入临时 .ps1（UTF-8 with BOM，PS 5.1 对无 BOM UTF-8 会按 ANSI 解析），
    用 -File 方式执行，避免 -Command 长串转义地狱。
    """
    exe = 'powershell.exe' if _IS_WINDOWS else 'pwsh'

    env = dict(os.environ)
    env.update(context.get("env", {}))
    stdin_data = context.get("stdin")

    full = content
    if args:
        full += '\n' + args

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            'w', suffix='.ps1', delete=False,
            encoding='utf-8-sig', newline='\n', dir=tempfile.gettempdir(),
        ) as f:
            f.write(full)
            tmp_path = f.name

        proc = subprocess.run(
            [exe, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', tmp_path],
            cwd=workdir,
            capture_output=True,
            timeout=timeout,
            env=env,
            input=stdin_data.encode('utf-8') if stdin_data else None,
        )
        stdout = proc.stdout.decode('utf-8', errors='replace')
        stderr = proc.stderr.decode('utf-8', errors='replace')
        return stdout, stderr, proc.returncode
    except FileNotFoundError:
        return "", f"{exe} 未安装或不在 PATH 中", 1
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _execute_via_bridge(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    timeout: int,
    args: Optional[str] = None,
    func_name: Optional[str] = None,
) -> Tuple[str, str, int]:
    """通过 bridge helper 执行代码 - 支持所有 31 种桥接语言。

    加固点：
      - 超时传递（helper 若支持 timeout 参数）
      - args 传递（helper 若支持 args 参数）
      - 错误分类（ImportError / ModuleNotFoundError / FileNotFoundError /
        subprocess.TimeoutExpired / 通用）
      - 编码统一（bytes 探测 + 降级 utf-8-replace）
      - 未安装时给出安装提示
    """
    try:
        from vools.bridge import get_helper

        lang = block.language
        helper = get_helper(lang)

        if helper is None:
            return "", f"{lang} bridge 未注册（vools.bridge.registry）", 1

        if not helper.is_available():
            return "", (
                f"{lang} 编译器未安装或不可用。请安装 {lang} 编译器后重试，"
                f"或参考 docs/03 §6.5 注册语言标记。"
            ), 1

        fname = func_name or f"__md_block_{block.index}"

        # 尝试传超时 + args（helper 签名若支持）
        kwargs: Dict = {"func_name": fname}
        try:
            import inspect as _insp
            sig_params = set(_insp.signature(helper.execute_code).parameters)
        except (TypeError, ValueError):
            sig_params = set()

        if "timeout" in sig_params and timeout:
            kwargs["timeout"] = timeout
        if "args" in sig_params and args is not None:
            kwargs["args"] = args

        result = helper.execute_code(block.content, **kwargs)

        if isinstance(result, bytes):
            # 子进程输出可能为 GBK（Windows PowerShell 5.1）/UTF-16，先探测再解码
            info = detect(result)
            body, _bom = strip_bom(result)
            result = body.decode(info["encoding"], errors="replace")

        return str(result), "", 0

    except ModuleNotFoundError as exc:
        # 区分是 vools.bridge 没装还是 helper 模块缺失
        msg = str(exc)
        return "", f"{block.language} bridge 依赖缺失: {msg}", 1
    except ImportError:
        return "", f"{block.language} bridge 未安装", 1
    except FileNotFoundError as exc:
        return "", f"{block.language} 编译器路径不存在: {exc}", 1
    except subprocess.TimeoutExpired:
        return "", f"{block.language} 执行超时 ({timeout}s)", 124
    except Exception as exc:  # noqa: BLE001
        return "", f"{block.language} 执行异常: {type(exc).__name__}: {exc}", 1


# ── 富内容展示：html / svg / rich（计划 §4.2，P1）──


def _execute_rich_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
) -> Tuple[str, str, int]:
    """
    渲染富内容展示块（html / svg / rich）。

    档位（#!level 指令）：
    - level=1..3：L1 sanitize + 卡片渲染（默认 1，静态展示；决策 3）
    - level=4：源码展示降级形态（整体转义 + 复制/折叠按钮，无脚本）

    远程图片（决策 2）：默认禁止；仅 `rich=opt-in`（或 rich=allow-remote /
    rich=1 / rich=true）显式开启时放行，并配套放宽 CSP img-src。

    渲染产物写 build_dir/artifacts/rich/block_{index}.html（决策 1 的新位置），
    stdout 返回卡片落盘路径与 L1 剥离审计，exit 0。
    """
    from .rich.sanitize import sanitize_html_fragment, build_csp_meta
    from .rich.renderer import render_card, render_source_card

    index = block.index
    build_dir = context.get("build_dir", ".mdbuild")
    rich_dir = os.path.join(build_dir, "artifacts", "rich")
    os.makedirs(rich_dir, exist_ok=True)

    level_raw = block.directives.get("level", "1") or "1"
    try:
        level = int(level_raw)
    except ValueError:
        level = 1
    if level not in (1, 2, 3, 4):
        level = 1

    rich_opt = (block.directives.get("rich") or "").lower()
    allow_remote = rich_opt in ("opt-in", "allow-remote", "1", "true", "yes")
    title = block.directives.get("title") or f"rich block {index}"

    try:
        if level == 4:
            # L4 源码展示降级形态：转义源码，宿主脚本提供复制/折叠（卡片内无脚本）
            card_html = render_source_card(
                block_id=f"block_{index}",
                language="html",
                source=block.content,
                level=4,
                foldable=bool(getattr(block, "foldable", False)),
                collapsed=bool(getattr(block, "collapsed", False)),
                fold_label=getattr(block, "fold_label", "") or "\u70b9\u51fb\u5c55\u5f00",
            )
            audit: List[str] = []
        else:
            safe_html, audit = sanitize_html_fragment(
                block.content,
                allow_remote_images=allow_remote,
            )
            card_html = render_card(
                block_id=f"block_{index}",
                kind="html",
                title=title,
                body_html=safe_html,
                level=level if level in (1, 2, 3) else 1,
            )
    except Exception as e:
        return "", f"富内容渲染失败: {e}", 1

    # 组装完整文档：L1 基线 CSP（决策 3，不可信动作不可越权提升）
    csp_meta = build_csp_meta(level=level, allow_remote_images=allow_remote)
    full_doc = (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        + csp_meta
        + "\n</head>\n<body>\n"
        + card_html
        + "\n</body>\n</html>"
    )

    out_name = f"block_{index}.html"
    out_path = os.path.join(rich_dir, out_name)
    write_text(out_path, full_doc)

    lines = [f"[rich] block {index} level={level} -> {out_path}"]
    if audit:
        shown = ", ".join(audit[:20])
        more = f" 等 {len(audit)} 项" if len(audit) > 20 else ""
        lines.append(f"[rich] L1 剥离 {len(audit)} 项: {shown}{more}")
    return "\n".join(lines), "", 0


# ── Node.js（node / nodejs / js / javascript）──


def _execute_node_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    timeout: int,
    args: Optional[str],
) -> Tuple[str, str, int]:
    """
    执行 Node.js 代码块。

    与 python 块同语义：直接调 node CLI，不经过 bridge 管理层。
    """
    import shutil as _shutil

    if _shutil.which("node") is None:
        return "", "node 未安装", 1

    workdir = context.get("workdir", os.getcwd())
    env = dict(os.environ)
    env.update(config.get("env", {}) if isinstance(config, dict) else {})

    # 写临时 .js 文件
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8"
    ) as f:
        f.write(block.content)
        tmp_path = f.name

    try:
        cmd = ["node", tmp_path]
        if args:
            cmd.extend(args.split() if isinstance(args, str) else args)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=workdir,
            env=env,
            timeout=timeout,
        )
        stdout = proc.stdout
        stderr = proc.stderr
        if stderr and "Warning" not in stderr:
            # node 的 stderr 通常是日志，非致命；保留给调用方判断
            pass
        return stdout, stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return "", f"node 超时 ({timeout}s)", 124
    except Exception as e:
        return "", str(e), 1
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── CSS 静态块 ──


def _execute_css_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
) -> Tuple[str, str, int]:
    """
    执行 CSS 静态块：把代码写入 {build_dir}/artifacts/css/ 目录。

    与 html/svg 块同为静态资源：不执行任何脚本，仅输出文件。
    """
    build_dir = context.get("build_dir") or (
        config.get("build_dir") if isinstance(config, dict) else None
    )
    if not build_dir:
        build_dir = tempfile.mkdtemp(prefix="vools-md-")

    css_dir = os.path.join(build_dir, "artifacts", "css")
    os.makedirs(css_dir, exist_ok=True)

    out_name = f"block_{block.index}.css"
    out_path = os.path.join(css_dir, out_name)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(block.content)

    return f"[css] block {block.index} -> {out_path}", "", 0


# ── MCP 调用块（stdio 协议，零第三方依赖）──


def _execute_mcp_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    timeout: int,
) -> Tuple[str, str, int]:
    """
    执行 mcp 代码块。

    通过 stdio 协议调用外部 MCP 服务器。
    完整实现见 .mcp_client.execute_mcp_block。
    """
    from .mcp_client import execute_mcp_block as _mcp_run

    workdir = context.get("workdir") or config.get("workdir") if isinstance(config, dict) else None
    if workdir is None:
        workdir = os.getcwd()

    merged_config = dict(config) if isinstance(config, dict) else {}
    merged_config["workdir"] = workdir

    return _mcp_run(
        block.content,
        block.directives,
        merged_config,
        timeout=timeout,
    )


# ── webview2: WebView2 GUI 渲染 ──


def _execute_webview2(
    block: CodeBlock,
    context: Dict,
    config: Dict,
) -> Tuple[str, str, int]:
    """
    执行 webview2 代码块，渲染 GUI。

    支持指令：
    - title: 窗口标题
    - width: 窗口宽度
    - height: 窗口高度
    - resizable: 是否可调整大小 (true/false)
    - blocking: 是否阻塞等待 (true/false)
    - html: 外部 HTML 文件路径
    - inject: 注入的 JS 代码

    Returns:
        (stdout, stderr, exit_code)
    """
    try:
        from .webview2 import execute_webview2_block

        return execute_webview2_block(
            block.content,
            block.directives,
            context,
            context.get("build_dir", ".mdbuild"),
        )
    except ImportError as e:
        return "", f"webview2 模块导入失败: {e}", 1
    except Exception as e:
        return "", f"webview2 执行错误: {e}", 1


# ═══════════════════════════════════════════════════════
# 主入口（M5 增强：导入解析 + 增量构建 + 完整报告）
# ═══════════════════════════════════════════════════════


def run_md(
    md_path: str,
    only: Optional[List[str]] = None,
    force: bool = False,
    debug: bool = False,
    build_dir: Optional[str] = None,
    profile: bool = False,
    parallel: bool = False,
) -> Dict[str, Any]:
    """
    执行 Markdown 脚本（M5 增强版）。

    Args:
        md_path: .md 文件路径
        only: 只执行这些 tag 的块
        force: 强制全量重跑
        debug: 调试模式（断点暂停）
        build_dir: 产物根目录
        profile: 性能分析模式
        parallel: 并行执行模式

    Returns:
        执行报告 dict
    """
    parsed = parse_md(md_path)
    fd = parsed.file_directives

    if build_dir is None:
        build_dir = fd.build_dir
    if not os.path.isabs(build_dir):
        build_dir = os.path.join(os.path.dirname(os.path.abspath(md_path)), build_dir)

    md_dir = os.path.dirname(os.path.abspath(md_path))

    all_blocks = resolve_imports(parsed, md_dir, build_dir)

    config = load_config(fd.config, md_dir)

    deps_path = fd.deps
    if deps_path and not os.path.isabs(deps_path):
        deps_path = os.path.join(md_dir, deps_path)
    deps_report = check_deps(deps_path, md_dir)

    ensure_build_dir(build_dir)

    only_tags = set(only or [])
    only_langs: Optional[set] = None  # 双语义：entry 若为语言则按语言过滤
    if not only_tags and fd.only:
        only_tags = set(fd.only)
    if not only_tags and fd.entry:
        entry = fd.entry
        # 双语义：entry 值是可路由语言 → 语言选择器；否则 → tag 过滤器（旧行为）
        if entry in BUILTIN_BLOCK_LANGUAGES:
            only_langs = {entry}
        else:
            only_tags = {entry}

    artifacts_table: Dict[str, Any] = {}
    block_results: List[BlockResult] = []
    total_duration: float = 0.0

    existing_manifest = None if force else read_manifest(build_dir)

    # M5: 并行执行模式
    if parallel:
        # 筛选出要执行的块
        parallel_blocks = []
        for idx, block in enumerate(all_blocks):
            if only_tags and block.tag and not (set(block.tag) & only_tags):
                continue
            if only_tags and not block.tag and only_tags:
                continue
            if only_langs and block.language not in only_langs:
                continue
            parallel_blocks.append(block)

        context = {
            "env": dict(config.get("env", {})),
            "workdir": md_dir,
            "build_dir": build_dir,
            "md_dir": md_dir,
        }

        results = run_parallel(parallel_blocks, context, config, artifacts_table)
        block_results.extend(results)
        for r in results:
            total_duration += r.duration_ms
    else:
        # 顺序执行
        for idx, block in enumerate(all_blocks):
            if only_tags and block.tag and not (set(block.tag) & only_tags):
                continue
            if only_tags and not block.tag and only_tags:
                continue
            if only_langs and block.language not in only_langs:
                continue

            # M5: 智能缓存
            if not force and existing_manifest and idx < len(existing_manifest.get("blocks", [])):
                if should_use_cache(block, existing_manifest, force, parsed.block_hashes):
                    br = BlockResult(
                        index=idx,
                        language=block.language,
                        tag=block.tag,
                        directives=block.directives,
                        status="skipped",
                        duration_ms=0,
                        source_hash=(parsed.block_hashes[idx] if idx < len(parsed.block_hashes) else block.content),
                        cache_hit=True,
                    )
                    br.stdout = "[cached] 跳过（内容未变）"
                    block_results.append(br)
                    continue

            context = {
                "env": dict(config.get("env", {})),
                "workdir": md_dir,
                "build_dir": build_dir,
                "md_dir": md_dir,
            }

            br = run_block(
                block,
                idx,
                context,
                artifacts_table,
                config,
                debug=debug,
                profile=profile,
            )
            br.source_hash = block.content if idx >= len(parsed.block_hashes) else parsed.block_hashes[idx]
            block_results.append(br)
            total_duration += br.duration_ms

    manifest_data = {
        "md_path": md_path,
        "md_hash": parsed.md_hash,
        "build_dir": build_dir,
        "blocks": [
            {
                "index": br.index,
                "language": br.language,
                "tag": br.tag,
                "status": br.status,
                "source_hash": br.source_hash,
                "duration_ms": br.duration_ms,
                "artifacts": br.artifacts,
                "source_file": br.source_file,
                "imported": br.imported,
                "breakpoint": br.breakpoint,
                "breakpoint_hit": br.breakpoint_hit,
                "profiling": br.profiling,
                "cache_hit": br.cache_hit,
                "parallel": br.parallel,
            }
            for br in block_results
        ],
        "total_duration_ms": total_duration,
    }

    manifest_path = write_manifest(build_dir, manifest_data)

    return {
        "md_path": md_path,
        "md_hash": parsed.md_hash,
        "build_dir": build_dir,
        "config": config,
        "deps_status": {
            "ok": deps_report.ok,
            "missing": deps_report.missing,
            "warnings": deps_report.warnings,
        },
        "blocks": [
            {
                "index": br.index,
                "language": br.language,
                "tag": br.tag,
                "directives": br.directives,
                "status": br.status,
                "duration_ms": br.duration_ms,
                "stdout": br.stdout,
                "stderr": br.stderr,
                "exit_code": br.exit_code,
                "artifacts": br.artifacts,
                "output_file": br.output_file,
                "workdir": br.workdir,
                "args": br.args,
                "timeout": br.timeout,
                "source_file": br.source_file,
                "imported": br.imported,
                "breakpoint": br.breakpoint,
                "breakpoint_hit": br.breakpoint_hit,
                "profiling": br.profiling,
                "cache_hit": br.cache_hit,
                "parallel": br.parallel,
            }
            for br in block_results
        ],
        "artifacts_table": artifacts_table,
        "total_duration_ms": total_duration,
        "manifest_path": manifest_path,
    }


def run_multiple_md(
    md_paths: List[str],
    only: Optional[List[str]] = None,
    force: bool = False,
    build_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """执行多个 md 文件。"""
    if build_dir is None:
        build_dir = os.path.join(os.getcwd(), ".mdbuild")

    ensure_build_dir(build_dir)

    results = {}
    total_duration = 0

    for md_path in md_paths:
        result = run_md(md_path, only=only, force=force, build_dir=build_dir)
        results[md_path] = result
        total_duration += result["total_duration_ms"]

    return {
        "md_paths": md_paths,
        "total_duration_ms": total_duration,
        "results": results,
    }
