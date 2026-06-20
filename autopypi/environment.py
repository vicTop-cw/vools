import subprocess
import sys
import shlex
from pathlib import Path


def check_python_version(min_version=(3, 6)):
    """检查 Python 版本"""
    current_version = sys.version_info[:2]
    if current_version < min_version:
        return False, f"Python {min_version[0]}.{min_version[1]}+ required, found {current_version[0]}.{current_version[1]}"
    return True, f"Python version: {current_version[0]}.{current_version[1]}"


def check_dependencies(dependencies):
    """检查依赖是否已安装"""
    missing = []
    for dep in dependencies:
        try:
            __import__(dep)
        except ImportError:
            missing.append(dep)
    return missing


def check_git_repo(project_root):
    """检查是否为 Git 仓库"""
    git_dir = Path(project_root) / ".git"
    return git_dir.exists()


def check_pypirc(config):
    """检查 PyPI 配置文件"""
    pypirc_path = Path(config["pypi"]["pypirc_path"]).expanduser()
    return pypirc_path.exists(), pypirc_path


def run_command(cmd, cwd=None, capture_output=True, env=None):
    """
    运行命令并返回结果

    安全说明：始终使用 shell=False，命令参数以列表形式传递，
    避免 shell 注入风险。如果传入字符串，会使用 shlex.split 安全拆分。
    """
    try:
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)

        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            env=env,
            shell=False
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1
        }


def install_dependencies(requirements_file="requirements.txt"):
    """安装项目依赖"""
    result = run_command(["pip", "install", "-r", requirements_file])
    return result


def install_build_tools():
    """安装构建工具"""
    result = run_command(["pip", "install", "build", "twine"])
    return result