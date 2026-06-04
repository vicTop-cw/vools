import os
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent

DEFAULT_CONFIG = {
    "project": {
        "name": "vools",
        "version_file": "vools/__init__.py",
        "changelog_dir": "changelog",
        "dist_dir": "dist",
    },
    "pypi": {
        "repository": "https://upload.pypi.org/legacy/",
        "test_repository": "https://test.pypi.org/legacy/",
        "pypirc_path": "~/.pypirc",
        "use_test_pypi": False,
    },
    "git": {
        "remote_name": "origin",
        "main_branch": "main",
        "create_tag": True,
        "push_tag": True,
    },
    "testing": {
        "run_tests": True,
        "test_dir": "tests",
        "test_command": "pytest",
    },
    "logging": {
        "log_file": "release.log",
        "log_level": "INFO",
        "log_format": "%(asctime)s - %(levelname)s - %(message)s",
    },
}


def load_config(config_path=None):
    """加载配置文件"""
    if config_path is None:
        config_path = BASE_DIR / "config.json"
    
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        return deep_merge(DEFAULT_CONFIG, user_config)
    
    return DEFAULT_CONFIG.copy()


def save_config(config, config_path=None):
    """保存配置文件"""
    if config_path is None:
        config_path = BASE_DIR / "config.json"
    
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def deep_merge(base, update):
    """深度合并配置"""
    result = base.copy()
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_current_version(version_file_path=None):
    """从版本文件获取当前版本"""
    if version_file_path is None:
        version_file_path = PROJECT_ROOT / "vools" / "__init__.py"
    
    with open(version_file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"').strip("'")
    return None


def increment_version(current_version, level="patch"):
    """版本号递增"""
    parts = current_version.split(".")
    major, minor, patch = map(int, parts)
    
    if level == "major":
        major += 1
        minor = 0
        patch = 0
    elif level == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    
    return f"{major}.{minor}.{patch}"


def update_version(new_version, version_file_path=None):
    """更新版本文件"""
    if version_file_path is None:
        version_file_path = PROJECT_ROOT / "vools" / "__init__.py"
    
    with open(version_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    content = content.replace(
        f'__version__ = "{get_current_version(version_file_path)}"',
        f'__version__ = "{new_version}"'
    )
    
    with open(version_file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    return new_version
