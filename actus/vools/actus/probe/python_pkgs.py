"""probe/python_pkgs.py — Python 包探测。

探测关键 Python 包是否已安装及其版本。
"""


__all__ = [
    "PythonPackagesProber",
    "probe",
]

import sys
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


def _get_pkg_version(import_name: str) -> str:
    """获取包的版本号（跨 Python 版本可靠来源，py3.6 兼容）。

    版本必须取自包元数据而非 import：
    - py3.8+ 用 stdlib importlib.metadata；py3.6/3.7 无该模块（实测
      `import importlib.metadata` 在 E:\\Python36 抛 ImportError），回退
      importlib_metadata backport / pkg_resources。
    - 旧实现整条链路吊在 `import importlib.metadata` 上：异常被外层
      except 吞掉后恒返回 "" —— py3.6 下整个包探测恒为「未安装」（假阴性）。
    - 且 import 成功 ≠ 版本可靠：许多包不定义 __version__（numpy 2.x 已移除），
      兜底 import 只在元数据缺失时使用。
    """
    try:
        try:
            from importlib import metadata as _im
        except ImportError:
            try:
                import importlib_metadata as _im  # py3.6/3.7 backport
            except ImportError:
                _im = None
        if _im is not None:
            try:
                return _im.distribution(import_name).version
            except Exception:
                pass
        import pkg_resources
        return pkg_resources.get_distribution(import_name).version
    except Exception:
        pass
    # 最后兜底：能 import 但拿不到元数据版本（如非 pip 安装的包）
    try:
        import importlib
        mod = importlib.import_module(import_name)
        return getattr(mod, "__version__", "") or "installed"
    except Exception:
        return ""


class PythonPackagesProber(Prober):
    """Python 包探测器。"""

    def probe(self) -> list:
        results = []
        installed_count = 0

        for pkg_name, import_name, is_optional in CRITICAL_PACKAGES:
            version = _get_pkg_version(import_name)
            available = bool(version)
            if available:
                installed_count += 1

            results.append(ProbeItem(
                name=pkg_name,
                category="python_packages",
                available=available,
                version=version,
                extra={"is_optional": is_optional},
            ))

        # 添加汇总项
        results.append(ProbeItem(
            name="_summary",
            category="python_packages",
            available=True,
            extra={
                "total_checked": len(CRITICAL_PACKAGES),
                "installed": installed_count,
                "not_installed": len(CRITICAL_PACKAGES) - installed_count,
            },
        ))

        return results
