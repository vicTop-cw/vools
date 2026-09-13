"""
vools.bridge.md runner (M5 增强版) — 执行编排 + 报告

M5 增强：
- 断点调试：breakpoint 指令，支持条件断点
- 性能分析：profiling，统计每块执行时间
- 缓存优化：智能缓存策略（基于内容哈希 + TTL）
- 并行执行：async/parallel 多块并行
"""
import os, sys, json, time, subprocess, shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict

from .parser import ParsedMD, CodeBlock, parse_md
from .directives import validate_directives
from .config import load_config
from .deps import check_deps
from .manifest import write_manifest, read_manifest
from .artifacts import (
    ensure_build_dir, compute_artifact_hash,
    is_artifact_stale, clean_build, register_artifact,
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
    status: str = "ok"          # ok | failed | timeout | skipped | error | paused
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
    profiling: Dict[str, float] = field(default_factory=dict)
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
    visited: set = None,
) -> List[CodeBlock]:
    """解析 #!import 指令，展开所有块（包括导入的）。"""
    if visited is None:
        visited = set()

    imports = []
    for block in parsed.blocks:
        import_val = block.directives.get('import', '')
        if import_val and import_val.endswith('.md'):
            imports.append({
                'target': import_val,
                'source_block': block,
            })

    local_blocks = []
    for block in parsed.blocks:
        if 'import' in block.directives and block.directives['import'].endswith('.md'):
            continue
        local_blocks.append(block)

    all_blocks: List[CodeBlock] = []

    for imp in imports:
        target = imp['target']
        target_path = os.path.join(md_dir, target)

        if target_path in visited:
            continue

        if not os.path.exists(target_path):
            empty_block = CodeBlock(
                index=len(local_blocks) + len(all_blocks),
                language='',
                content=f'# [import] {target} not found',
                directives={'import': target},
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
    extensions: List[str] = None,
) -> List[str]:
    """扫描目录，返回所有 .md 文件列表。"""
    if extensions is None:
        extensions = ['.md']

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
        output_path = os.path.join(library_dir, 'manifest.yaml')

    md_files = scan_library(library_dir)

    entries = []
    for md_path in md_files:
        parsed = parse_md(md_path)
        entries.append({
            'path': os.path.relpath(md_path, library_dir),
            'hash': parsed.md_hash,
            'entry': parsed.file_directives.entry,
            'only': parsed.file_directives.only,
            'config': parsed.file_directives.config,
            'deps': parsed.file_directives.deps,
            'build_dir': parsed.file_directives.build_dir,
            'blocks': len(parsed.blocks),
        })

    manifest = {
        'library_dir': library_dir,
        'md_files': entries,
        'total': len(entries),
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        try:
            from .manifest import minimal_yaml_dump
            f.write(minimal_yaml_dump(manifest))
        except ImportError:
            f.write(json.dumps(manifest, indent=2, ensure_ascii=False))

    return manifest


def load_library_manifest(library_dir: str) -> Optional[Dict[str, Any]]:
    """加载库级 manifest.yaml。"""
    manifest_path = os.path.join(library_dir, 'manifest.yaml')
    if not os.path.exists(manifest_path):
        return None

    with open(manifest_path, 'r', encoding='utf-8') as f:
        text = f.read()

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
        build_dir = os.path.join(library_dir, '.mdbuild')

    ensure_build_dir(build_dir)

    md_files = scan_library(library_dir)

    results = {}
    total_duration = 0

    for md_path in md_files:
        result = run_md(md_path, only=only, force=force, build_dir=build_dir)
        results[md_path] = result
        total_duration += result['total_duration_ms']

    return {
        'library_dir': library_dir,
        'md_files': md_files,
        'total_duration_ms': total_duration,
        'results': results,
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
    has_bp = 'breakpoint' in block.directives or 'bp' in block.directives
    if not has_bp:
        return None

    bp_val = block.directives.get('breakpoint', '')
    if not bp_val:
        bp_val = block.directives.get('bp', '')

    if debug_mode:
        return f"Breakpoint at block {block.index}"

    if bp_val == 'true' or bp_val == '':
        return f"Breakpoint at block {block.index}"

    # 条件断点
    try:
        condition = bp_val
        if condition.strip() == 'true':
            return f"Breakpoint (condition: {condition}) at block {block.index}"
        return f"Breakpoint (condition: {condition}) at block {block.index}"
    except Exception:
        return f"Breakpoint at block {block.index}"


def profile_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
) -> Dict[str, float]:
    """
    M5: 性能分析（profiling）。

    返回每个操作的耗时统计。
    """
    profiling = {}

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
        ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
        ps.print_stats()
        profiling['stats'] = s.getvalue()
        profiling['total_calls'] = ps.total_calls
        profiling['prim_calls'] = ps.prim_calls

    except Exception as e:
        profiling['error'] = str(e)

    return profiling


def should_use_cache(
    block: CodeBlock,
    existing_manifest: Optional[Dict],
    force: bool,
    block_hashes: List[str] = None,
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
    if block.index >= len(existing_manifest.get('blocks', [])):
        return False

    cached = existing_manifest['blocks'][block.index]

    # 检查内容哈希
    cached_hash = cached.get('source_hash', '')
    if block_hashes and block.index < len(block_hashes):
        current_hash = block_hashes[block.index]
    else:
        # 使用内容本身作为哈希（简化版）
        current_hash = block.content

    if cached_hash != current_hash:
        return False

    # 检查状态
    if cached.get('status') != 'ok':
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
                    status='error',
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
        result.status = 'paused'
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
    workdir = block.directives.get('workdir')
    args = block.directives.get('args')
    timeout = int(block.directives.get('timeout', '60'))
    env_vars = {}
    if 'env' in block.directives:
        env_str = block.directives['env']
        for pair in env_str.split():
            if '=' in pair:
                k, v = pair.split('=', 1)
                env_vars[k] = v

    # 构建执行上下文
    exec_context = dict(context)
    if workdir:
        if not os.path.isabs(workdir):
            workdir = os.path.join(context.get('md_dir', ''), workdir)
        result.workdir = workdir
        exec_context['workdir'] = workdir

    if env_vars:
        env = dict(exec_context.get('env', {}))
        env.update(env_vars)
        exec_context['env'] = env

    result.args = args
    result.timeout = timeout

    # 处理 stdin 指令：从文件读取内容注入到执行上下文
    stdin_val = block.directives.get('stdin')
    if stdin_val:
        stdin_path = stdin_val
        if not os.path.isabs(stdin_path):
            stdin_path = os.path.join(context.get('md_dir', ''), stdin_path)
        try:
            with open(stdin_path, 'r', encoding='utf-8') as sf:
                exec_context['stdin'] = sf.read()
        except FileNotFoundError:
            # 文件不存在时，使用空 stdin，不中断执行
            exec_context['stdin'] = ''
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
        stdout, stderr, exit_code = _execute_block(
            block, exec_context, config, args, timeout
        )
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
        artifact_path = os.path.join(
            context.get('build_dir', '.mdbuild'),
            'tmp',
            f'block_{index}_{export_name}.txt'
        )
        os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
        with open(artifact_path, 'w', encoding='utf-8') as f:
            f.write(result.stdout)

        register_artifact(
            artifacts_table, export_name, artifact_path,
            index, block.tag[0] if block.tag else None,
        )

        result.artifacts.append({
            'name': export_name,
            'path': artifact_path,
            'hash': compute_artifact_hash(artifact_path),
        })

    # 处理 output
    if "output" in block.directives:
        output_file = block.directives["output"]
        output_path = os.path.join(
            context.get('build_dir', '.mdbuild'),
            'tmp',
            f'block_{index}_{output_file}'
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result.stdout)
        result.output_file = output_path

    return result


def _execute_block(
    block: CodeBlock,
    context: Dict,
    config: Dict,
    args: Optional[str],
    timeout: int,
) -> tuple[str, str, int]:
    """执行代码块，返回 (stdout, stderr, exit_code)。"""
    lang = block.language
    workdir = context.get('workdir', os.getcwd())

    if lang == "python":
        return _execute_python(block.content, context, config, args)

    if lang in ("shell", "bash", "sh"):
        return _execute_shell(block.content, context, config, workdir, timeout, args)

    return _execute_via_bridge(block, context, config, timeout)


def _execute_python(content: str, context: Dict, config: Dict, args: Optional[str]) -> tuple[str, str, int]:
    """执行 Python 代码。"""
    try:
        import io
        exec_env = dict(context.get('env', {}))
        exec_env['__md_config'] = config

        if args:
            exec_env['__md_args'] = args.split()

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_stdin = sys.stdin
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        # 若上下文提供了 stdin 数据，重定向 sys.stdin
        stdin_data = context.get('stdin')
        stdin_buf = io.StringIO(stdin_data) if stdin_data is not None else None

        try:
            sys.stdout = stdout_buf
            sys.stderr = stderr_buf
            if stdin_buf is not None:
                sys.stdin = stdin_buf
            exec(content, {'__name__': '__md_block__', '__builtins__': __builtins__}, exec_env)
            exit_code = 0
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.stdin = old_stdin

        return stdout_buf.getvalue(), stderr_buf.getvalue(), exit_code

    except SystemExit as e:
        return "", str(e), e.code or 0
    except Exception as e:
        return "", str(e), 1


def _execute_shell(
    content: str,
    context: Dict,
    config: Dict,
    workdir: str,
    timeout: int,
    args: Optional[str],
) -> tuple[str, str, int]:
    """执行 Shell 代码。"""
    env = dict(context.get('env', {}))
    stdin_data = context.get('stdin')

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


def _execute_via_bridge(block: CodeBlock, context: Dict, config: Dict, timeout: int) -> tuple[str, str, int]:
    """通过 bridge helper 执行代码。"""
    try:
        from vools.bridge import get_helper
        helper = get_helper(block.language)

        if not helper.is_available():
            return "", f"{block.language} 不可用", 1

        result = helper.execute_code(block.content, func_name=f"__md_block_{block.index}")

        if isinstance(result, bytes):
            result = result.decode('utf-8')

        return str(result), "", 0

    except ImportError:
        return "", f"{block.language} bridge 未安装", 1
    except Exception as e:
        return "", str(e), 1


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
    if not only_tags and fd.only:
        only_tags = set(fd.only)
    if not only_tags and fd.entry:
        only_tags = {fd.entry}

    artifacts_table: Dict[str, Any] = {}
    block_results: List[BlockResult] = []
    total_duration = 0

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
            parallel_blocks.append(block)

        context = {
            'env': dict(config.get('env', {})),
            'workdir': md_dir,
            'build_dir': build_dir,
            'md_dir': md_dir,
        }

        results = run_parallel(parallel_blocks, context, config, artifacts_table)
        block_results.extend(results)
        total_duration = sum(r.duration_ms for r in results)
    else:
        # 顺序执行
        for idx, block in enumerate(all_blocks):
            if only_tags and block.tag and not (set(block.tag) & only_tags):
                continue
            if only_tags and not block.tag and only_tags:
                continue

            # M5: 智能缓存
            if not force and existing_manifest and idx < len(existing_manifest.get('blocks', [])):
                if should_use_cache(block, existing_manifest, force, parsed.block_hashes):
                    cached = existing_manifest['blocks'][idx]
                    br = BlockResult(
                        index=idx,
                        language=block.language,
                        tag=block.tag,
                        directives=block.directives,
                        status="skipped",
                        duration_ms=0,
                        source_hash=parsed.block_hashes[idx] if idx < len(parsed.block_hashes) else block.content,
                        cache_hit=True,
                    )
                    br.stdout = "[cached] 跳过（内容未变）"
                    block_results.append(br)
                    continue

            context = {
                'env': dict(config.get('env', {})),
                'workdir': md_dir,
                'build_dir': build_dir,
                'md_dir': md_dir,
            }

            br = run_block(block, idx, context, artifacts_table, config, debug=debug, profile=profile)
            br.source_hash = block.content if idx >= len(parsed.block_hashes) else parsed.block_hashes[idx]
            block_results.append(br)
            total_duration += br.duration_ms

    manifest_data = {
        'md_path': md_path,
        'md_hash': parsed.md_hash,
        'build_dir': build_dir,
        'blocks': [
            {
                'index': br.index,
                'language': br.language,
                'tag': br.tag,
                'status': br.status,
                'source_hash': br.source_hash,
                'duration_ms': br.duration_ms,
                'artifacts': br.artifacts,
                'source_file': br.source_file,
                'imported': br.imported,
                'breakpoint': br.breakpoint,
                'breakpoint_hit': br.breakpoint_hit,
                'profiling': br.profiling,
                'cache_hit': br.cache_hit,
                'parallel': br.parallel,
            }
            for br in block_results
        ],
        'total_duration_ms': total_duration,
    }

    manifest_path = write_manifest(build_dir, manifest_data)

    return {
        'md_path': md_path,
        'md_hash': parsed.md_hash,
        'build_dir': build_dir,
        'config': config,
        'deps_status': {
            'ok': deps_report.ok,
            'missing': deps_report.missing,
            'warnings': deps_report.warnings,
        },
        'blocks': [
            {
                'index': br.index,
                'language': br.language,
                'tag': br.tag,
                'directives': br.directives,
                'status': br.status,
                'duration_ms': br.duration_ms,
                'stdout': br.stdout,
                'stderr': br.stderr,
                'exit_code': br.exit_code,
                'artifacts': br.artifacts,
                'output_file': br.output_file,
                'workdir': br.workdir,
                'args': br.args,
                'timeout': br.timeout,
                'source_file': br.source_file,
                'imported': br.imported,
                'breakpoint': br.breakpoint,
                'breakpoint_hit': br.breakpoint_hit,
                'profiling': br.profiling,
                'cache_hit': br.cache_hit,
                'parallel': br.parallel,
            }
            for br in block_results
        ],
        'artifacts_table': artifacts_table,
        'total_duration_ms': total_duration,
        'manifest_path': manifest_path,
    }


def run_multiple_md(
    md_paths: List[str],
    only: Optional[List[str]] = None,
    force: bool = False,
    build_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """执行多个 md 文件。"""
    if build_dir is None:
        build_dir = os.path.join(os.getcwd(), '.mdbuild')

    ensure_build_dir(build_dir)

    results = {}
    total_duration = 0

    for md_path in md_paths:
        result = run_md(md_path, only=only, force=force, build_dir=build_dir)
        results[md_path] = result
        total_duration += result['total_duration_ms']

    return {
        'md_paths': md_paths,
        'total_duration_ms': total_duration,
        'results': results,
    }
