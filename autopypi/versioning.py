import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from environment import run_command
from config import get_current_version, increment_version, update_version


def create_changelog(version, changelog_dir, notes=""):
    """创建版本更新日志"""
    changelog_path = Path(changelog_dir) / f"v{version}.md"
    
    content = f"# v{version} 更新日志\n\n"
    if notes:
        content += f"{notes}\n"
    else:
        content += """## 修复

## 改进

## 新功能

## 兼容性
"""
    
    with open(changelog_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    return str(changelog_path)


def git_add_all(project_root):
    """添加所有变更到 Git"""
    result = run_command("git add .", cwd=project_root)
    return result


def git_commit(project_root, message):
    """提交变更"""
    result = run_command(f'git commit -m "{message}"', cwd=project_root)
    return result


def git_create_tag(project_root, version, message=None):
    """创建版本标签"""
    if message is None:
        message = f"Version {version}"
    result = run_command(f'git tag -a v{version} -m "{message}"', cwd=project_root)
    return result


def git_push(project_root, remote_name="origin", branch="main"):
    """推送到远程仓库"""
    result = run_command(f"git push {remote_name} {branch}", cwd=project_root)
    return result


def git_push_tag(project_root, remote_name="origin", version=None):
    """推送标签到远程仓库"""
    if version is None:
        version = get_current_version()
    result = run_command(f"git push {remote_name} v{version}", cwd=project_root)
    return result


def get_git_status(project_root):
    """获取 Git 状态"""
    result = run_command("git status", cwd=project_root)
    return result


def get_git_log(project_root, limit=5):
    """获取最近提交记录"""
    result = run_command(f"git log --oneline -n {limit}", cwd=project_root)
    return result