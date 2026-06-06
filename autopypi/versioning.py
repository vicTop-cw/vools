import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from environment import run_command
from config import get_current_version, increment_version, update_version


def get_git_log_since_last_tag(project_root):
    """获取从上一个标签到当前的提交记录"""
    try:
        # 获取最近的标签
        result = run_command("git describe --tags --abbrev=0", cwd=project_root)
        if result["success"] and result["output"]:
            last_tag = result["output"].strip()
            # 获取从上次标签到当前的提交
            result = run_command(f"git log {last_tag}..HEAD --oneline", cwd=project_root)
            if result["success"] and result["output"]:
                return result["output"].strip().split('\n')
        # 如果没有标签，获取最近的提交
        result = run_command("git log --oneline -n 20", cwd=project_root)
        if result["success"] and result["output"]:
            return result["output"].strip().split('\n')
    except Exception:
        pass
    return []


def parse_git_commits(commits):
    """解析 Git 提交记录，按类型分类"""
    categories = {
        "fix": [],
        "feat": [],
        "improve": [],
        "docs": [],
        "refactor": [],
        "test": [],
        "other": []
    }
    
    for commit in commits:
        if not commit.strip():
            continue
        
        # 解析提交信息（格式: hash message）
        parts = commit.split(' ', 1)
        if len(parts) == 2:
            commit_hash = parts[0]
            message = parts[1]
            
            # 根据关键词分类
            message_lower = message.lower()
            if message_lower.startswith("fix:") or "fix" in message_lower:
                categories["fix"].append(f"- {message}")
            elif message_lower.startswith("feat:") or "feature" in message_lower or "新功能" in message:
                categories["feat"].append(f"- {message}")
            elif message_lower.startswith("impr:") or "improve" in message_lower or "优化" in message:
                categories["improve"].append(f"- {message}")
            elif message_lower.startswith("docs:") or "doc" in message_lower or "文档" in message:
                categories["docs"].append(f"- {message}")
            elif message_lower.startswith("refactor:") or "refactor" in message_lower:
                categories["refactor"].append(f"- {message}")
            elif message_lower.startswith("test:") or "test" in message_lower:
                categories["test"].append(f"- {message}")
            else:
                categories["other"].append(f"- {message}")
    
    return categories


def create_changelog(version, changelog_dir, notes=""):
    """创建版本更新日志（从 Git 提交自动生成）"""
    changelog_path = Path(changelog_dir) / f"v{version}.md"
    
    # 获取项目根目录
    project_root = Path(__file__).parent.parent
    
    # 获取提交记录并分类
    commits = get_git_log_since_last_tag(project_root)
    categories = parse_git_commits(commits)
    
    # 构建内容
    content = f"# v{version} 更新日志\n\n"
    content += f"> 发布日期: {get_current_date()}\n\n"
    
    if notes:
        content += f"## 概述\n\n{notes}\n\n"
    
    # 添加分类内容
    if categories["feat"]:
        content += "## 新功能\n\n" + "\n".join(categories["feat"]) + "\n\n"
    
    if categories["improve"]:
        content += "## 改进\n\n" + "\n".join(categories["improve"]) + "\n\n"
    
    if categories["fix"]:
        content += "## 修复\n\n" + "\n".join(categories["fix"]) + "\n\n"
    
    if categories["docs"]:
        content += "## 文档\n\n" + "\n".join(categories["docs"]) + "\n\n"
    
    if categories["refactor"]:
        content += "## 重构\n\n" + "\n".join(categories["refactor"]) + "\n\n"
    
    if categories["test"]:
        content += "## 测试\n\n" + "\n".join(categories["test"]) + "\n\n"
    
    if categories["other"]:
        content += "## 其他\n\n" + "\n".join(categories["other"]) + "\n\n"
    
    # 如果没有提交记录，显示提示
    if not commits:
        content += """## 修复

## 改进

## 新功能

## 兼容性

> 提示: 请在此添加本次版本的更新内容
"""
    
    with open(changelog_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    return str(changelog_path)


def get_current_date():
    """获取当前日期"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")


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
