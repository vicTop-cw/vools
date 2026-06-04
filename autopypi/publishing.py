import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from environment import run_command


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