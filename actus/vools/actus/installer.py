"""installer.py —— 动作安装器（docs/20 §M1）。

从 Git 仓库安装动作到本地，支持分支/标签/commit 切换、
缓存管理、安装清单记录、多注册表（公共/团队/个人/自定义）、
可见性控制。
"""

import json
import os
import re
import shutil
import subprocess
import time
from typing import Optional, Tuple, List

from . import registry as registry_mod


class ActionInstaller:
    """动作安装器。

    职责：
    - 从 Git 仓库克隆动作
    - 切换分支/标签/commit
    - 管理本地缓存
    - 记录安装清单
    - 卸载和更新
    - 多注册表支持（公共/团队/个人/自定义）
    - 可见性检查
    """

    def __init__(self, install_dir: str = None, cache_dir: str = None,
                 config_dir: str = None):
        """
        参数:
            install_dir: 动作安装根目录（默认 ~/.actus/actions）。
            cache_dir: Git 克隆缓存目录（默认 ~/.actus/cache）。
            config_dir: Actus 配置目录（默认 ~/.actus）。
        """
        if install_dir is None:
            install_dir = os.path.join(os.path.expanduser("~"), ".actus", "actions")
        if cache_dir is None:
            cache_dir = os.path.join(os.path.expanduser("~"), ".actus", "cache")
        if config_dir is None:
            config_dir = os.path.join(os.path.expanduser("~"), ".actus")

        self._install_dir = install_dir
        self._cache_dir = cache_dir
        self._config_dir = config_dir
        os.makedirs(install_dir, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)

    @property
    def install_dir(self) -> str:
        return self._install_dir

    # ── 安装 ──

    def install(self, repo_url: str, branch: str = "main",
                tag: str = None, commit: str = None,
                scope: str = None) -> dict:
        """从 Git 仓库安装动作。

        参数:
            repo_url: Git 仓库 URL。
            branch: 分支名（默认 main）。
            tag: 标签名（与 branch 互斥）。
            commit: commit hash（与 branch/tag 互斥）。
            scope: 权限范围（如 'sandbox', 'trusted'）。

        返回:
            安装结果 {'status': 'ok', 'path': '...', 'actions': [...]}
        """
        cache_key = self._url_to_cache_key(repo_url)
        cache_path = os.path.join(self._cache_dir, cache_key)

        # 克隆或更新仓库
        if os.path.isdir(os.path.join(cache_path, branch, ".git")):
            rc, _, err = self._git_fetch(cache_path, branch)
            if rc != 0:
                return {"status": "error", "message": f"Git fetch failed: {err}"}
        else:
            rc, _, err = self._git_clone(repo_url, cache_path, branch)
            if rc != 0:
                return {"status": "error", "message": f"Git clone failed: {err}"}

        # 切换到指定分支/标签/commit
        if tag:
            self._git_checkout_tag(cache_path, branch, tag)
        elif commit:
            self._git_checkout_commit(cache_path, branch, commit)
        else:
            self._git_checkout_branch(cache_path, branch)

        # 构建索引
        repo_registry_path = os.path.join(cache_path, branch)
        reg = registry_mod.ActionRegistry(cache_dir=self._cache_dir)
        index = reg.build_from_directory(repo_registry_path)

        # 复制到安装目录
        install_name = self._url_to_install_name(repo_url)
        target_dir = os.path.join(self._install_dir, install_name)
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        shutil.copytree(repo_registry_path, target_dir)

        # 记录安装清单
        manifest = reg.record_installation(
            repo_url, target_dir,
            branch=branch, tag=tag, commit=commit
        )

        # 写入 scope 配置
        if scope:
            self._write_scope_config(target_dir, scope)

        return {
            "status": "ok",
            "name": install_name,
            "path": target_dir,
            "url": repo_url,
            "branch": branch,
            "tag": tag,
            "commit": commit,
            "scope": scope,
            "actions": [a["id"] for a in index.get("actions", [])],
            "action_count": len(index.get("actions", []))
        }

    def uninstall(self, repo_url: str = None, name: str = None) -> dict:
        """卸载已安装的动作仓库。

        参数:
            repo_url: 仓库 URL。
            name: 安装名称（与 repo_url 互斥）。

        返回:
            {'status': 'ok', 'removed': '...'}
        """
        install_name = name or (self._url_to_install_name(repo_url) if repo_url else None)
        if not install_name:
            return {"status": "error", "message": "Must provide repo_url or name"}

        target_dir = os.path.join(self._install_dir, install_name)
        if not os.path.isdir(target_dir):
            return {"status": "error", "message": f"Not installed: {install_name}"}

        shutil.rmtree(target_dir)

        # 移除安装清单
        if repo_url:
            reg = registry_mod.ActionRegistry(cache_dir=self._cache_dir)
            reg.remove_installation(repo_url)

        return {"status": "ok", "removed": install_name, "path": target_dir}

    # ── 更新 ──

    def update(self, repo_url: str = None, name: str = None,
               branch: str = None) -> dict:
        """更新已安装的动作仓库。

        参数:
            repo_url: 仓库 URL。
            name: 安装名称。
            branch: 分支名（默认使用原分支）。

        返回:
            更新结果。
        """
        # 加载现有清单
        manifest = self._load_manifest(repo_url, name)
        if not manifest:
            return {"status": "error", "message": "Not installed"}

        url = repo_url or manifest["url"]
        branch = branch or manifest.get("branch", "main")

        # 重新安装（覆盖）
        return self.install(
            repo_url=url,
            branch=branch,
            tag=manifest.get("tag"),
            commit=manifest.get("commit"),
            scope=manifest.get("scope")
        )

    def sync_all(self) -> List[dict]:
        """更新所有已安装的仓库。

        返回:
            各仓库的更新结果列表。
        """
        reg = registry_mod.ActionRegistry(cache_dir=self._cache_dir)
        manifests = reg.list_installed()
        results = []

        for manifest in manifests:
            url = manifest.get("url")
            if not url:
                continue
            result = self.update(repo_url=url)
            results.append({
                "url": url,
                "name": manifest.get("cache_key"),
                "result": result
            })

        return results

    def rollback(self, repo_url: str = None, name: str = None,
                 version: int = None) -> dict:
        """回滚到指定版本（通过 git checkout 到历史 commit）。"""
        manifest = self._load_manifest(repo_url, name)
        if not manifest:
            return {"status": "error", "message": "Not installed"}

        local_path = manifest.get("local_path")
        if not local_path or not os.path.isdir(local_path):
            return {"status": "error", "message": "Local path not found"}

        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-n", str(version + 1)],
                cwd=local_path, capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return {"status": "error", "message": f"Git log failed: {result.stderr}"}

            lines = result.stdout.strip().split("\n")
            if len(lines) <= version:
                return {"status": "error", "message": f"Version {version} not found"}

            target_commit = lines[version].split()[0]
            checkout = subprocess.run(
                ["git", "checkout", target_commit],
                cwd=local_path, capture_output=True, text=True, timeout=10
            )
            if checkout.returncode != 0:
                return {"status": "error", "message": f"Checkout failed: {checkout.stderr}"}

            return {"status": "ok", "message": f"Rolled back to {target_commit}", "commit": target_commit}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def check_update(self, repo_url: str = None, name: str = None) -> dict:
        """检查是否有可用更新（不实际更新）。"""
        manifest = self._load_manifest(repo_url, name)
        if not manifest:
            return {"status": "error", "message": "Not installed"}

        local_path = manifest.get("local_path")
        if not local_path or not os.path.isdir(local_path):
            return {"status": "error", "message": "Local path not found"}

        try:
            local = subprocess.run(["git", "rev-parse", "HEAD"],
                cwd=local_path, capture_output=True, text=True, timeout=10)
            local_commit = local.stdout.strip() if local.returncode == 0 else ""

            remote = subprocess.run(["git", "ls-remote", "origin", "HEAD"],
                cwd=local_path, capture_output=True, text=True, timeout=10)
            remote_commit = remote.stdout.split()[0] if remote.returncode == 0 and remote.stdout else ""

            return {
                "status": "ok",
                "has_update": local_commit != remote_commit and remote_commit != "",
                "local_commit": local_commit,
                "remote_commit": remote_commit,
                "url": manifest.get("url")
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ── 查询 ──

    def list_installed(self) -> List[dict]:
        """列出所有已安装的仓库。"""
        reg = registry_mod.ActionRegistry(cache_dir=self._cache_dir)
        return reg.list_installed()

    def get_install_path(self, repo_url: str = None,
                         name: str = None) -> Optional[str]:
        """获取已安装仓库的本地路径。"""
        install_name = name or (self._url_to_install_name(repo_url) if repo_url else None)
        if not install_name:
            return None

        target_dir = os.path.join(self._install_dir, install_name)
        if os.path.isdir(target_dir):
            return target_dir
        return None

    def is_installed(self, repo_url: str = None, name: str = None) -> bool:
        """检查是否已安装。"""
        return self.get_install_path(repo_url=repo_url, name=name) is not None

    # ── 路径发现 ──

    def discover_actions_dirs(self) -> List[str]:
        """发现所有已安装仓库的动作目录。

        返回:
            所有 actions/ 目录路径列表。
        """
        dirs = []
        if not os.path.isdir(self._install_dir):
            return dirs

        for name in os.listdir(self._install_dir):
            actions_dir = os.path.join(self._install_dir, name, "actions")
            if os.path.isdir(actions_dir):
                dirs.append(actions_dir)

        return dirs

    def resolve_action_path(self, action_id: str) -> Optional[str]:
        """根据动作 ID 解析本地文件路径。

        搜索所有已安装仓库，找到匹配的动作文件。
        """
        for actions_dir in self.discover_actions_dirs():
            for root, dirs, files in os.walk(actions_dir):
                for fname in files:
                    if not fname.endswith(".actus.md"):
                        continue
                    fpath = os.path.join(root, fname)
                    # 快速检查：读取文件中的 id 字段
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            content = f.read()
                        if f'"id": "{action_id}"' in content or f'"id":"{action_id}"' in content:
                            return fpath
                    except (OSError, UnicodeDecodeError):
                        continue
        return None

    # ── Scope 权限 ──

    def get_scope(self, repo_url: str = None, name: str = None) -> Optional[str]:
        """获取已安装仓库的 scope 配置。"""
        install_name = name or (self._url_to_install_name(repo_url) if repo_url else None)
        if not install_name:
            return None

        scope_path = os.path.join(self._install_dir, install_name, ".actus.scope")
        if os.path.isfile(scope_path):
            with open(scope_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return None

    def set_scope(self, scope: str, repo_url: str = None, name: str = None) -> bool:
        """设置已安装仓库的 scope。"""
        install_name = name or (self._url_to_install_name(repo_url) if repo_url else None)
        if not install_name:
            return False

        target_dir = os.path.join(self._install_dir, install_name)
        if not os.path.isdir(target_dir):
            return False

        self._write_scope_config(target_dir, scope)
        return True

    # ── Git 操作 ──

    def _git_clone(self, url: str, dest: str, branch: str):
        """克隆 Git 仓库。"""
        branch_dir = os.path.join(dest, branch)
        os.makedirs(os.path.dirname(branch_dir), exist_ok=True)

        cmd = ["git", "clone", "--branch", branch, "--single-branch", url, branch_dir]
        return self._run_git(cmd)

    def _git_fetch(self, dest: str, branch: str):
        """拉取最新代码。"""
        branch_dir = os.path.join(dest, branch)
        if not os.path.isdir(os.path.join(branch_dir, ".git")):
            return (-1, "", "Not a git repository")

        cmd = ["git", "-C", branch_dir, "fetch", "--all", "--prune"]
        return self._run_git(cmd)

    def _git_checkout_branch(self, dest: str, branch: str):
        """切换到指定分支并拉取最新。"""
        branch_dir = os.path.join(dest, branch)
        if not os.path.isdir(os.path.join(branch_dir, ".git")):
            return

        cmd = ["git", "-C", branch_dir, "checkout", branch]
        self._run_git(cmd)

        cmd = ["git", "-C", branch_dir, "pull", "origin", branch]
        self._run_git(cmd)

    def _git_checkout_tag(self, dest: str, branch: str, tag: str):
        """切换到指定标签。"""
        branch_dir = os.path.join(dest, branch)
        if not os.path.isdir(os.path.join(branch_dir, ".git")):
            return

        # 获取最新标签
        cmd = ["git", "-C", branch_dir, "fetch", "--tags"]
        self._run_git(cmd)

        cmd = ["git", "-C", branch_dir, "checkout", f"tags/{tag}"]
        self._run_git(cmd)

    def _git_checkout_commit(self, dest: str, branch: str, commit: str):
        """切换到指定 commit。"""
        branch_dir = os.path.join(dest, branch)
        if not os.path.isdir(os.path.join(branch_dir, ".git")):
            return

        # 获取最新
        cmd = ["git", "-C", branch_dir, "fetch", "origin", branch]
        self._run_git(cmd)

        cmd = ["git", "-C", branch_dir, "checkout", commit]
        self._run_git(cmd)

    def _run_git(self, cmd: list) -> Tuple[int, str, str]:
        """执行 Git 命令。

        返回:
            (return_code, stdout, stderr)
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Git command timed out"
        except FileNotFoundError:
            return -1, "", "Git not found. Please install Git."
        except Exception as e:
            return -1, "", str(e)

    # ── 私有方法 ──

    def _url_to_cache_key(self, url: str) -> str:
        """URL 转缓存 key。"""
        key = re.sub(r'[^a-zA-Z0-9_-]', '_', url)
        return key[:64]

    def _url_to_install_name(self, url: str) -> str:
        """URL 转安装目录名。"""
        # 从 URL 提取仓库名
        # git@github.com:user/repo.git -> user_repo
        # https://github.com/user/repo -> user_repo
        match = re.search(r'[:/]([^/]+?)(?:\.git)?$', url)
        if match:
            repo_name = match.group(1)
        else:
            repo_name = self._url_to_cache_key(url)

        # 添加作者前缀（如果有）
        author_match = re.search(r'[:/]([^/]+)/[^/]+(?:\.git)?$', url)
        if author_match:
            author = author_match.group(1)
            return f"{author}_{repo_name}"

        return repo_name

    def _write_scope_config(self, target_dir: str, scope: str):
        """写入 scope 配置文件。"""
        scope_path = os.path.join(target_dir, ".actus.scope")
        with open(scope_path, "w", encoding="utf-8") as f:
            f.write(scope)

    def _write_visibility_config(self, target_dir: str, visibility: str,
                                  author: str = "", team: str = ""):
        """写入可见性配置文件。"""
        vis_path = os.path.join(target_dir, ".actus.visibility")
        with open(vis_path, "w", encoding="utf-8") as f:
            json.dump({
                "visibility": visibility,
                "author": author,
                "team": team,
                "configured_at": time.time()
            }, f, indent=2)

    def install_with_visibility(self, repo_url: str, branch: str = "main",
                                 tag: str = None, commit: str = None,
                                 scope: str = None,
                                 visibility: str = "public",
                                 author: str = "",
                                 team: str = "",
                                 registry_name: str = "public",
                                 current_user: str = "") -> dict:
        """从指定注册表安装动作（支持可见性检查）。"""
        # 1) 可见性检查
        if visibility == "private":
            if not author:
                return {"status": "error",
                        "message": "Private actions require an author field"}
            if author != current_user and current_user:
                return {"status": "error",
                        "message": f"Private action access denied. Author: {author}"}

        # 2) 执行标准安装
        result = self.install(repo_url, branch=branch, tag=tag,
                              commit=commit, scope=scope)

        if result.get("status") != "ok":
            return result

        # 3) 记录可见性元数据
        result["visibility"] = visibility
        result["author"] = author
        result["team"] = team
        result["registry_name"] = registry_name

        # 4) 写入可见性配置
        local_path = result.get("path", "")
        if local_path:
            self._write_visibility_config(local_path, visibility, author, team)

        return result

    def _load_manifest(self, repo_url: str = None,
                       name: str = None) -> Optional[dict]:
        """加载安装清单。"""
        reg = registry_mod.ActionRegistry(cache_dir=self._cache_dir)

        if repo_url:
            return reg.load_manifest(repo_url)

        if name:
            # 通过 name 查找
            manifests = reg.list_installed()
            for m in manifests:
                if m.get("cache_key") == name or m.get("local_path", "").endswith(name):
                    return m

        return None


# ── 便捷函数 ──

def install_actions(repo_url: str, branch: str = "main",
                    tag: str = None, commit: str = None,
                    scope: str = None) -> dict:
    """便捷函数：安装动作仓库。"""
    installer = ActionInstaller()
    return installer.install(repo_url, branch=branch, tag=tag,
                             commit=commit, scope=scope)


def install_with_visibility(repo_url: str, branch: str = "main",
                             tag: str = None, commit: str = None,
                             scope: str = None,
                             visibility: str = "public",
                             author: str = "",
                             team: str = "",
                             registry_name: str = "public",
                             current_user: str = "",
                             config_dir: str = None) -> dict:
    """便捷函数：支持可见性的动作安装。

    参数:
        repo_url: Git 仓库 URL。
        branch/tag/commit: 版本锁定参数。
        scope: 权限范围。
        visibility: 可见性级别 (public/unlisted/private/team)。
        author: 动作作者（私有动作需要）。
        team: 团队名称（团队动作需要）。
        registry_name: 注册表名称。
        current_user: 当前用户。
        config_dir: 配置目录。

    返回:
        安装结果。
    """
    installer = ActionInstaller(config_dir=config_dir)
    return installer.install_with_visibility(
        repo_url, branch=branch, tag=tag, commit=commit,
        scope=scope, visibility=visibility, author=author, team=team,
        registry_name=registry_name, current_user=current_user
    )


def resolve_action_path(action_id: str,
                        config_dir: str = None) -> Optional[str]:
    """便捷函数：根据动作 id 查找本地安装路径。"""
    installer = ActionInstaller(config_dir=config_dir)
    return installer.resolve_action_path(action_id)


def uninstall_actions(repo_url: str = None, name: str = None) -> dict:
    """便捷函数：卸载动作仓库。"""
    installer = ActionInstaller()
    return installer.uninstall(repo_url=repo_url, name=name)


def update_actions(repo_url: str = None, name: str = None) -> dict:
    """便捷函数：更新动作仓库。"""
    installer = ActionInstaller()
    return installer.update(repo_url=repo_url, name=name)


def list_installed_actions() -> List[dict]:
    """便捷函数：列出已安装的仓库。"""
    installer = ActionInstaller()
    return installer.list_installed()


__all__ = [
    'ActionInstaller',
    'install_actions',
    'install_with_visibility',
    'list_installed_actions',
    'resolve_action_path',
    'uninstall_actions',
    'update_actions'
]
