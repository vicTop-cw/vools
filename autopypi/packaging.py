import shutil
from pathlib import Path

from .environment import run_command


def clean_dist_dir(dist_dir):
    """清理旧的构建产物"""
    dist_path = Path(dist_dir)
    if dist_path.exists():
        shutil.rmtree(dist_path)
    dist_path.mkdir(parents=True, exist_ok=True)
    return True


def build_package(project_root, config):
    """构建 Python 包"""
    dist_dir = Path(project_root) / config["project"]["dist_dir"]
    clean_dist_dir(dist_dir)
    
    result = run_command("python -m build", cwd=project_root)
    return result


def check_package(project_root, config, version):
    """检查构建产物"""
    dist_dir = Path(project_root) / config["project"]["dist_dir"]
    
    expected_files = [
        f"{config['project']['name']}-{version}.tar.gz",
        f"{config['project']['name']}-{version}-py3-none-any.whl"
    ]
    
    found_files = []
    missing_files = []
    
    for expected in expected_files:
        file_path = dist_dir / expected
        if file_path.exists():
            found_files.append(expected)
        else:
            missing_files.append(expected)
    
    return {
        "success": len(missing_files) == 0,
        "found": found_files,
        "missing": missing_files,
        "dist_dir": str(dist_dir)
    }


def verify_package(config):
    """使用 twine 验证包"""
    project_root = Path(__file__).parent.parent
    dist_dir = project_root / config["project"]["dist_dir"]
    result = run_command(f"twine check {dist_dir}/*")
    return result