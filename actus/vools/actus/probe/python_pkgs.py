"""probe/python_pkgs.py — Python 包探测。

探测关键 Python 包是否已安装及其版本。

包维度并发（本轮）
------------------
65 个包逐个查版本原本串行，实测 6.2–11s，是整条探测链的墙钟地板（它 7.1s 时
`actus probe` wall 7.5s，它 9.7s 时 wall 10.4s）。查版本是 sys.path / dist-info
的文件系统 I/O，天然适合并发：线程池按下标回填，**items 的内容与顺序与串行
逐字一致**（不是按完成顺序合并）。

先按发行名查元数据，再退回 import 名（本轮）
--------------------------------------------
CRITICAL_PACKAGES 是 (发行名, import 名, 是否可选) 三元组，旧实现只用 **import 名**
查元数据 —— 于是 Pillow/PIL、pyyaml/yaml、scikit-learn/sklearn、pywin32/win32api
这类「发行名 ≠ import 名」的包元数据必然查不到，只能走 import 兜底：
`import sklearn` 一项就要 3.6s（实测），而且这与本模块既有契约「版本必须取自
包元数据而非 import」相悖。现在按 (发行名, import 名) 依次查元数据，命中即返回；
import 兜底只在两者都查不到时使用，且**仍然只用 import 名**（与旧行为一致）。

失败不再静默（沿用 compilers.py 的分类口径）
--------------------------------------------
* 「包没装」不是错误：仍是 available=False + version=""，输出与改前逐字相同；
* 元数据/import 抛**非预期**异常 → `error_kind` 进 `ProbeItem.extra`
  （只记异常类型名，不记异常正文，避免把路径等细节带进报告）；
* 整批超预算（`_PKG_BUDGET_SEC`）→ 未完成的包标 `error_kind="budget_exceeded"`
  并在 `_summary` 里计数，绝不静默少算。
"""


__all__ = [
    "PythonPackagesProber",
]

import concurrent.futures
import importlib
import sys
import threading

from .base import Prober, ProbeItem

# 关键包列表：(package_name, import_name, is_optional)
CRITICAL_PACKAGES = [
    ("pandas", "pandas", False),
    ("numpy", "numpy", False),
    ("polars", "polars", False),
    ("openpyxl", "openpyxl", False),
    ("Pillow", "PIL", True),
    ("matplotlib", "matplotlib", True),
    ("seaborn", "seaborn", True),
    ("scipy", "scipy", True),
    ("sympy", "sympy", True),
    ("networkx", "networkx", True),
    ("requests", "requests", False),
    ("httpx", "httpx", True),
    ("aiohttp", "aiohttp", True),
    ("psycopg2", "psycopg2", True),
    ("mysql-connector-python", "mysql.connector", True),
    ("pymongo", "pymongo", True),
    ("paramiko", "paramiko", True),
    ("pytesseract", "pytesseract", True),
    ("openai", "openai", True),
    ("anthropic", "anthropic", True),
    ("ollama", "ollama", True),
    ("transformers", "transformers", True),
    ("torch", "torch", True),
    ("tensorflow", "tensorflow", True),
    ("pytest", "pytest", True),
    ("playwright", "playwright", True),
    ("selenium", "selenium", True),
    ("psutil", "psutil", True),
    ("pywin32", "win32api", True),
    ("platformdirs", "platformdirs", True),
    ("distro", "distro", True),
    ("pydantic", "pydantic", True),
    ("click", "click", True),
    ("typer", "typer", True),
    ("rich", "rich", True),
    ("jinja2", "jinja2", True),
    ("pyyaml", "yaml", True),
    ("tomli", "tomli", True),
    ("click", "click", True),
    ("httpx", "httpx", True),
    ("websockets", "websockets", True),
    ("starlette", "starlette", True),
    ("fastapi", "fastapi", True),
    ("uvicorn", "uvicorn", True),
    ("flask", "flask", True),
    ("django", "django", True),
    ("sqlalchemy", "sqlalchemy", True),
    ("alembic", "alembic", True),
    ("redis", "redis", True),
    ("celery", "celery", True),
    ("boto3", "boto3", True),
    ("google-cloud-storage", "google.cloud.storage", True),
    ("azure-storage-blob", "azure.storage.blob", True),
    ("minio", "minio", True),
    ("duckdb", "duckdb", True),
    ("pyarrow", "pyarrow", True),
    ("scikit-learn", "sklearn", True),
    ("xgboost", "xgboost", True),
    ("lightgbm", "lightgbm", True),
    ("catboost", "catboost", True),
    ("plotly", "plotly", True),
    ("bokeh", "bokeh", True),
    ("altair", "altair", True),
    ("dash", "dash", True),
    ("streamlit", "streamlit", True),
]

# 包维度并发度。查版本是文件系统 I/O，实测 12 线程即饱和（再高收益递减）。
MAX_PKG_WORKERS = 12

# 整批总预算（秒）。正常一批 1–2s，这个预算只在「某个包卡住」时兜底：
# 超预算的包标 budget_exceeded 并在 _summary 计数，绝不静默丢。
_PKG_BUDGET_SEC = 5.0


def _load_metadata_module():
    """返回可用的 importlib.metadata 模块（py3.6/3.7 回退 backport）；都没有返回 None。"""
    try:
        from importlib import metadata as metadata_module
        return metadata_module
    except ImportError:
        try:
            import importlib_metadata as metadata_module    # py3.6/3.7 backport
            return metadata_module
        except ImportError:
            return None


def _normalize_dist_name(name: str) -> str:
    """PEP 503 规范化：小写 + 连续 [-_.] 折叠成 '-'（与 importlib.metadata 一致）。"""
    normalized = []
    previous_dash = False
    for char in name.strip().lower():
        if char in '-_.':
            if not previous_dash:
                normalized.append('-')
                previous_dash = True
        else:
            normalized.append(char)
            previous_dash = False
    return ''.join(normalized)


def _build_metadata_index():
    """一次扫描建成 {规范化发行名: 版本}，查不到返回 {}。

    为什么要有索引：`metadata.distribution(name)` 每次调用都会扫描整个
    sys.path（含所有 site-packages/*.dist-info），本机实测 65 个包 ×
    每个最多 2 个候选名 = **一百多次全量扫描**，这才是包探测 6–11s 的主因，
    而且它主要是 Python 层的路径遍历 —— 吃 GIL，加线程也压不下去。
    一次 `metadata.distributions()` 扫描 + 字典查找即可，语义不变：
    `distribution(name)` 与按 PEP 503 规范化后的字典键是同一套匹配规则，
    同名多版本时 `setdefault` 保留扫描到的第一个，与 distribution() 一致。
    """
    index = {}
    metadata_module = _load_metadata_module()
    if metadata_module is None:
        return index
    try:
        for distribution in metadata_module.distributions():
            try:
                # 只读一次 METADATA：`.metadata` 与 `.version` 各读一遍文件的话，
                # 348 个发行版就是近 700 次文件读，实测 634ms → 269ms。
                metadata = distribution.metadata
                name = metadata['Name']
                version = metadata['Version']
            except Exception:
                continue          # 单条元数据损坏不该毁掉整个索引
            if not name or not version:
                continue
            index.setdefault(_normalize_dist_name(name), version)
    except Exception:
        return {}                 # 扫描整体失败 → 调用方退回逐名查询
    return index


_PKG_RESOURCES_INDEX = None
_PKG_RESOURCES_LOCK = threading.Lock()


def _build_pkg_resources_index():
    """{规范化发行名: 版本} —— pkg_resources 看到的发行版视图（懒加载单例）。

    为什么光有 importlib.metadata 不够：本机实测 `tomli 2.0.1` 装在
    `setuptools/_vendor` 里，importlib.metadata 扫不到，只有 pkg_resources 的
    working_set 有它。改造前正是靠「pkg_resources 兜底」命中它的，去掉就是
    一条实打实的假阴性回归。

    为什么不逐个 `get_distribution()`：它对「查不到」的包每个要 90–130ms，
    23 个未装包就是 3.7s（实测）。一次性遍历 working_set 建字典，
    之后全是 O(1)；代价是 pkg_resources 首次导入 ~710ms，且只付一次
    （模块级单例缓存，锁保证多线程下只建一次）。
    """
    global _PKG_RESOURCES_INDEX

    with _PKG_RESOURCES_LOCK:
        if _PKG_RESOURCES_INDEX is not None:
            return _PKG_RESOURCES_INDEX

        index = {}
        try:
            import pkg_resources
            working_set = pkg_resources.working_set
        except Exception:
            _PKG_RESOURCES_INDEX = index
            return index

        for distribution in working_set:
            try:
                name = distribution.project_name
                version = distribution.version
            except Exception:
                continue          # 单条坏元数据不影响其它发行版
            if name and version:
                index.setdefault(_normalize_dist_name(name), version)

        _PKG_RESOURCES_INDEX = index
        return index


def _get_pkg_version_detail(package_name: str, import_name: str, index=None):
    """探测单个包的版本，返回 (version, signal)。

    version: 版本串；取不到为 ""（「没装」的正常形态，不是错误）
    signal : None = 正常（含「没装」）；dict = 需要留痕的非预期失败
             （键 error_kind / error，error 只放异常类型名）

    探测顺序（与模块 docstring 的契约一致）：
      1. importlib.metadata 索引（一次建成，O(1) 查找）；
      2. pkg_resources 索引（覆盖 setuptools/_vendor 的 vendored 发行版等
         索引扫不到、只有 pkg_resources 认得的安装）；
      3. import 兜底，**只用 import_name**（能 import 但拿不到元数据版本）。
    索引不可用时（py3.6/3.7 无 importlib.metadata / backport）退回改造前的
    逐名链路，行为不变。
    """
    signal = None
    dist_names = []
    for candidate in (package_name, import_name):
        if candidate and candidate not in dist_names:
            dist_names.append(candidate)

    # ── 1) 发行元数据（首选真源）：优先走一次性索引，避免逐名全量扫描 sys.path ──
    metadata_index = _build_metadata_index() if index is None else index
    if metadata_index:
        for dist_name in dist_names:
            version = metadata_index.get(_normalize_dist_name(dist_name))
            if version:
                return version, None
        # 索引是权威的全量视图：这里查不到，再查 pkg_resources 视图
        # （覆盖 setuptools/_vendor 里的 vendored 发行版与 legacy 安装），
        # 两者都没有才进 import 兜底。**不逐个调 get_distribution**：
        # 它对「查不到」的包每个要 90–130ms，23 个未装包就是 3.7s 纯浪费；
        # 而 import 兜底失败只要 0.3–1.6ms。
        legacy_index = _build_pkg_resources_index()
        for dist_name in dist_names:
            version = legacy_index.get(_normalize_dist_name(dist_name))
            if version:
                return version, None
    else:
        # 索引不可用（py3.6/3.7 没有 importlib.metadata / backport，或扫描失败）
        # → 退回改造前的逐名链路，行为不变。
        metadata_module = _load_metadata_module()
        if metadata_module is not None:
            not_found = getattr(metadata_module, 'PackageNotFoundError', ())
            for dist_name in dist_names:
                try:
                    return metadata_module.distribution(dist_name).version, None
                except not_found:
                    continue                              # 换个候选名，不算错误
                except Exception as exc:                  # 元数据损坏等：留痕继续
                    if signal is None:
                        signal = {'error_kind': 'metadata_error',
                                  'error': type(exc).__name__}
                    continue

        # ── 2) pkg_resources 兜底（仅在没有元数据索引时使用）──
        try:
            import pkg_resources
        except Exception as exc:
            if signal is None:
                signal = {'error_kind': 'metadata_unavailable',
                          'error': type(exc).__name__}
        else:
            for dist_name in dist_names:
                try:
                    return pkg_resources.get_distribution(dist_name).version, None
                except Exception:
                    continue  # DistributionNotFound / 坏元数据：都查不到，继续兜底

    # ── 3) import 兜底（只用 import_name，与旧行为一致）──
    try:
        module = importlib.import_module(import_name)
    except ModuleNotFoundError:
        return '', signal          # 没装：正常形态，不是错误
    except Exception as exc:
        if signal is None:
            signal = {'error_kind': 'import_error',
                      'error': type(exc).__name__}
        return '', signal
    return getattr(module, '__version__', '') or 'installed', None


def _get_pkg_version(import_name: str) -> str:
    """获取包的版本号（跨 Python 版本可靠来源，py3.6 兼容）。

    版本必须取自包元数据而非 import：
    - py3.8+ 用 stdlib importlib.metadata；py3.6/3.7 无该模块（实测
      `import importlib.metadata` 在 E:\\\\Python36 抛 ImportError），回退
      importlib_metadata backport / pkg_resources。
    - 旧实现整条链路吊在 `import importlib.metadata` 上：异常被外层
      except 吞掉后恒返回 "" —— py3.6 下整个包探测恒为「未安装」（假阴性）。
    - 且 import 成功 ≠ 版本可靠：许多包不定义 __version__（numpy 2.x 已移除），
      兜底 import 只在元数据缺失时使用。

    保留这个单参入口是为了向后兼容（既有调用点/测试按 `_get_pkg_version(name)`
    取版本）；需要失败原因时用 `_get_pkg_version_detail`。
    """
    version, _signal = _get_pkg_version_detail(import_name, import_name)
    return version


class PythonPackagesProber(Prober):
    """Python 包探测器（包维度并发）。"""

    def probe(self) -> list:
        entries = list(CRITICAL_PACKAGES)
        total = len(entries)
        versions = [None] * total        # None = 没跑完（预算耗尽）
        signals = [None] * total
        workers = max(1, min(MAX_PKG_WORKERS, total))

        # 元数据索引只建一次（一次 sys.path 扫描），线程内只做字典查找。
        metadata_index = _build_metadata_index()

        def _task(index, package_name, import_name):
            version, signal = _get_pkg_version_detail(
                package_name, import_name, metadata_index)
            return index, version, signal

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        try:
            futures = {}
            for index, (package_name, import_name, _is_optional) in enumerate(entries):
                futures[executor.submit(_task, index, package_name, import_name)] = index
            try:
                for future in concurrent.futures.as_completed(
                        futures, timeout=_PKG_BUDGET_SEC):
                    index, version, signal = future.result()
                    versions[index] = version
                    signals[index] = signal
            except concurrent.futures.TimeoutError:
                pass    # 未完成的保持在 None → 下面统一标 budget_exceeded
        finally:
            # 预算耗尽时不等待卡住的包：取消排队中的任务，已在跑的随解释器退出。
            executor.shutdown(wait=False, cancel_futures=True)

        results = []
        installed_count = 0
        budget_exceeded = 0

        for index, (package_name, import_name, is_optional) in enumerate(entries):
            version = versions[index]
            if version is None:
                budget_exceeded += 1
                results.append(ProbeItem(
                    name=package_name,
                    category="python_packages",
                    available=False,
                    version="",
                    extra={
                        "is_optional": is_optional,
                        "error_kind": "budget_exceeded",
                        "error": "整批探测超出 %.1fs 预算，本包未完成" % _PKG_BUDGET_SEC,
                    },
                ))
                continue

            available = bool(version)
            if available:
                installed_count += 1

            extra = {"is_optional": is_optional}
            signal = signals[index]
            if signal:
                extra.update(signal)

            results.append(ProbeItem(
                name=package_name,
                category="python_packages",
                available=available,
                version=version,
                extra=extra,
            ))

        # 添加汇总项（正常路径与改前逐字相同：budget_exceeded 只为 0 时不写这个键）
        # 三个数字互斥且加和为 total：没超预算时 not_installed 的算法与改前一致。
        summary_extra = {
            "total_checked": total,
            "installed": installed_count,
            "not_installed": total - installed_count - budget_exceeded,
        }
        if budget_exceeded:
            summary_extra["budget_exceeded"] = budget_exceeded
        results.append(ProbeItem(
            name="_summary",
            category="python_packages",
            available=True,
            extra=summary_extra,
        ))

        return results
