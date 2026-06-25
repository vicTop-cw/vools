import json
import urllib.request
from pathlib import Path

from .environment import run_command


def get_pypi_latest_version(package_name, test=False):
    """从 PyPI 获取最新版本号"""
    if test:
        url = f"https://test.pypi.org/pypi/{package_name}/json"
    else:
        url = f"https://pypi.org/pypi/{package_name}/json"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("info", {}).get("version")
    except Exception:
        return None


def compare_versions(version_a, version_b):
    """比较版本号，返回 -1/0/1"""
    try:
        parts_a = list(map(int, version_a.split(".")))
        parts_b = list(map(int, version_b.split(".")))
        for i in range(max(len(parts_a), len(parts_b))):
            a = parts_a[i] if i < len(parts_a) else 0
            b = parts_b[i] if i < len(parts_b) else 0
            if a < b:
                return -1
            if a > b:
                return 1
        return 0
    except Exception:
        return None


def publish_to_pypi(project_root, config, test=False):
    """发布到 PyPI"""
    dist_dir = Path(project_root) / config["project"]["dist_dir"]
    
    if test:
        repository = config["pypi"].get("test_repository", "https://test.pypi.org/legacy/")
        result = run_command(f"twine upload --repository-url {repository} --disable-progress-bar {dist_dir}/*")
    else:
        result = run_command(f"twine upload --disable-progress-bar {dist_dir}/*")
    
    return result


def test_install_package(package_name, version=None):
    """测试安装包"""
    if version:
        result = run_command(f"pip install {package_name}=={version}")
    else:
        result = run_command(f"pip install {package_name}")
    return result


def verify_installation(package_name):
    """验证安装是否成功"""
    result = run_command(f"python -c \"import {package_name}; print({package_name}.__version__)\"")
    return result