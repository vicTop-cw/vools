"""installer.py —— 动作安装器（docs/20 §M1）。

从 Git 仓库安装动作到本地，支持分支/标签/commit 切换、
缓存管理、安装清单记录、多注册表（公共/团队/个人/自定义）、
可见性控制。
"""

import json
import os
import re
import shutil
import stat
import time
from typing import Optional, Tuple, List

from . import registry as registry_mod
from ._proc import run_cmd_safe
from .constants import is_action_file

# 安装目录里由**用户/前一次安装**留下的配置文件。重装会 rmtree 整个目标目录，
# 所以这两个文件必须在删除前快照、复制后还原 —— 否则用户手改的 scope/可见性
# 会连同目录一起消失（不是"被覆盖"，是"整个目录被删了重建"）。
_PRESERVED_CONFIG_FILES = ('.actus.scope', '.actus.visibility')


def _snapshot_user_configs(target_dir: str) -> dict:
    """在 rmtree 之前读取目标目录里的配置文件内容。"""
    saved = {}
    for name in _PRESERVED_CONFIG_FILES:
        path = os.path.join(target_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                saved[name] = handle.read()
        except OSError:
            continue
    return saved


def _restore_user_configs(target_dir: str, saved: dict) -> List[str]:
    """把快照里的配置写回新目录，返回还原了的文件名列表。"""
    restored = []
    for name, text in (saved or {}).items():
        try:
            with open(os.path.join(target_dir, name), 'w', encoding='utf-8') as handle:
                handle.write(text)
            restored.append(name)
        except OSError:
            continue
    return restored


def _rmtree_force(path: str) -> None:
    """删除目录；遇到只读文件先去掉只读位再删。

    审计修：Windows 上 `git clone` 出来的对象文件是**只读**的，而安装会把这些
    `.git` 一起 copytree 进安装目录 —— 于是重装/卸载时的 `shutil.rmtree` 直接抛
    `PermissionError`（实测重装必然踩到），而且**删到一半才失败**，安装目录被留成
    半成品（旧安装已残缺、新安装还没拷）。这里先试一次普通删除，失败则清掉剩余
    文件的只读位再删。
    """
    try:
        shutil.rmtree(path)
        return
    except OSError:
        pass
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                os.chmod(os.path.join(root, name), stat.S_IWRITE)
            except OSError:
                continue
    shutil.rmtree(path)


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

    # ── 可见性门禁 ──

    def enforce_visibility_gate(self, repo_dir: str, repo_url: str = '',
                                key: str = None, action_id: str = None) -> dict:
        """安装前按 docs/41 §B1 判可见性：gated 需密钥、internal 一律不装。

        判据真源在 `vools.actus.visibility`（GatedKeyStore 的动作级/仓级两档粒度），
        这里只负责"把仓里每个动作的 visibility 读出来喂进去"，不另写一套规则。

        `action_id` 非空时只判那一个动作（`<owner>/<name>.actus:<action_id>` 形态）。
        返回 {'status':'ok'|'error', 'code':..., 'message':...}。
        """
        try:
            from vools.actus.visibility import (AUTH_REQUIRED, GatedKeyStore,
                                                is_internal_path)
        except ImportError as exc:                       # noqa: BLE001
            return {"status": "error", "code": "internal",
                    "message": f"可见性引擎不可用：{exc}"}

        repo_name = ''
        try:
            from vools.actus.repo import parse_ref
            repo_name = parse_ref(repo_url).get('repo') or ''
        except Exception:                                # noqa: BLE001
            repo_name = (repo_url or '').rstrip('/').rsplit('/', 1)[-1].replace('.git', '')

        gated_hits: list = []
        for dirpath, dirnames, filenames in os.walk(repo_dir):
            dirnames[:] = [d for d in dirnames if d not in ('.git', '__pycache__')]
            for fn in sorted(filenames):
                if not is_action_file(fn):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    from vools.actus.model import parse_cfg_from_file
                    action = parse_cfg_from_file(full)
                except Exception:                        # noqa: BLE001
                    continue                             # 解析失败留给契约校验报
                aid = action.meta.get('id') or ''
                if action_id and aid != action_id:
                    continue
                vis = (action.meta.get('visibility') or '').strip().lower()
                if vis == 'internal':
                    return {"status": "error", "code": "visibility_denied",
                            "message": (f"internal 动作 {aid!r} 不经安装分发"
                                        f"（随引擎落位 actions/system/_internal/）"),
                            "details": {"action_id": aid, "visibility": vis}}
                if vis == 'gated':
                    gated_hits.append({'action_id': aid, 'path': full})

        if not gated_hits:
            return {"status": "ok", "gated": [], "repo": repo_name}
        if not key:
            ids = [g['action_id'] for g in gated_hits]
            return {"status": "error", "code": AUTH_REQUIRED,
                    "message": (f"仓 {repo_name or repo_url} 含 gated 动作 {ids}，"
                                f"安装需带 --key <gated_key>（docs/41 §B2.3）"),
                    "details": {"gated": ids, "repo": repo_name}}
        try:
            store = GatedKeyStore()
        except RuntimeError as exc:
            return {"status": "error", "code": AUTH_REQUIRED, "message": str(exc)}
        denied = [g['action_id'] for g in gated_hits
                  if not store.verify(key, action_id=g['action_id'], repo=repo_name)]
        if denied:
            return {"status": "error", "code": AUTH_REQUIRED,
                    "message": (f"密钥对动作 {denied} 无效或已被轮换撤销"
                                f"（作者轮换后需重新获取，docs/41 §B2.5）"),
                    "details": {"denied": denied, "repo": repo_name}}
        return {"status": "ok", "gated": [g['action_id'] for g in gated_hits],
                "repo": repo_name}

    # ── 安装 ──

    def install(self, repo_url: str, branch: str = "main",
                tag: str = None, commit: str = None,
                scope: str = None, key: str = None,
                action_id: str = None,
                overwrite_config: bool = False) -> dict:
        """从 Git 仓库安装动作。

        参数:
            repo_url: Git 仓库 URL。
            branch: 分支名（默认 main）。
            tag: 标签名（与 branch 互斥）。
            commit: commit hash（与 branch/tag 互斥）。
            scope: 权限范围（如 'sandbox', 'trusted'）。
            key: gated 动作的授权密钥（docs/41 §B2.3）；未带或无效 ⇒ auth_required。
            action_id: 只装这一个动作（`<owner>/<name>.actus:<action_id>` 形态）。
            overwrite_config: 是否覆盖已有的 `.actus.scope` / `.actus.visibility`。
                **默认 False = 保留用户手改**（审计修：改前重装会 rmtree 整个目录，
                用户手改的配置连同目录一起消失，等于静默丢失）。

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

        # ── 可见性门禁（docs/41 §B1/§B2.3 / §D3）※必须在 copytree 之前 ──
        # 装完再判等于"先落盘再拒绝"，被拒的动作已经在本地文件系统里了。
        gate = self.enforce_visibility_gate(repo_registry_path, repo_url,
                                            key=key, action_id=action_id)
        if gate.get('status') != 'ok':
            return gate

        reg = registry_mod.ActionRegistry(cache_dir=self._cache_dir)
        index = reg.build_from_directory(repo_registry_path)

        # 复制到安装目录
        install_name = self._url_to_install_name(repo_url)
        # ── 审计修（P0：写侧越界）──
        # `_url_to_install_name` 的正则只认 `/` 和 `:`：传 Windows 本地路径
        # （`C:\Users\me\projects\myrepo`）时会把**整串带反斜杠的路径**当名字，
        # `os.path.join(install_dir, name)` 于是跳出 install_dir —— 紧接着的
        # `shutil.rmtree(target_dir)` 会删掉仓外的树（实测 rmtree 打到了源仓的
        # .git，被 Windows 只读属性拦下才没造成更大破坏）。
        # 这里两层防护：①名字只取最后一段（本地路径也能装成 `install/myrepo`）；
        # ②沿用 uninstall 那把尺子 `_inside_install_dir` 做兜底拒绝。
        install_name = os.path.basename(
            str(install_name).replace('\\', '/').rstrip('/')) or 'repo'
        if not self._inside_install_dir(install_name):
            return {"status": "error",
                    "message": f"安装名会越出安装目录，已拒绝: {install_name}"}
        target_dir = os.path.join(self._install_dir, install_name)
        # 重装 = rmtree + copytree：用户手改的 scope/可见性必须先快照，
        # 否则它们随目录一起消失（默认还原；overwrite_config=True 时不还原）。
        saved_configs = {} if overwrite_config else _snapshot_user_configs(target_dir)
        if os.path.exists(target_dir):
            _rmtree_force(target_dir)      # 只读 .git 对象：普通 rmtree 会半途 PermissionError
        shutil.copytree(repo_registry_path, target_dir)
        restored_configs = _restore_user_configs(target_dir, saved_configs)

        # 记录安装清单
        manifest = reg.record_installation(
            repo_url, target_dir,
            branch=branch, tag=tag, commit=commit
        )

        # 写入 scope 配置（已有用户配置时默认保留，写入与否见返回值）
        scope_written = False
        if scope:
            scope_written = self._write_scope_config(
                target_dir, scope, overwrite=overwrite_config)

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
            "action_count": len(index.get("actions", [])),
            # 诚实信号：哪些配置是**沿用用户既有值**（没被这次安装修改）
            "config_preserved": restored_configs,
            "scope_written": scope_written,
        }

    def _inside_install_dir(self, install_name: str) -> bool:
        """安装名解析后必须**严格落在** install_dir 之内。

        三条边共用这把尺子（BUG-0019 的删、BUG-0020 的写、以及读侧的 get_install_path）：
        - realpath 之后再比，顺带挡住软链/junction 指到外面的情形；
        - 用 startswith(root + sep) 而不是允许 `== root` —— 否则 name='.' 会把自己
          所在的整棵安装目录当成「一个仓库」删掉（这条是在写 quick win 时自查出来的）。
        """
        root = os.path.realpath(self._install_dir)
        real = os.path.realpath(os.path.join(self._install_dir, install_name))
        return real.startswith(root + os.sep)

    def _find_manifest_for_path(self, target_dir: str) -> Optional[dict]:
        """安装清单里 `local_path` 命中 target_dir 的那条记录；没有返回 None。"""
        try:
            reg = registry_mod.ActionRegistry(cache_dir=self._cache_dir)
            manifests = reg.list_installed()
        except Exception:
            return None
        wanted = os.path.realpath(target_dir)
        for manifest in manifests:
            local_path = manifest.get('local_path') or ''
            if local_path and os.path.realpath(local_path) == wanted:
                return manifest
        return None

    def uninstall(self, repo_url: str = None, name: str = None,
                  force: bool = False) -> dict:
        """卸载已安装的动作仓库。

        参数:
            repo_url: 仓库 URL。
            name: 安装名称（与 repo_url 互斥）。
            force: 目标目录**不在安装清单里**时是否仍允许删除（默认 False = 拒绝）。

        契约（审计修，已批准）：**默认只删安装清单里记录过的目录**。
        改前只要传个 name 就 rmtree install_dir 下任意子目录 —— 实测把一个
        「从未由 actus 安装、内含用户文件」的目录传错名字就整个删掉了，
        报的还是 status=ok。现在：清单里没有该 local_path → 拒绝并提示 force。
        """
        install_name = name or (self._url_to_install_name(repo_url) if repo_url else None)
        if not install_name:
            return {"status": "error", "message": "Must provide repo_url or name"}
        # 与 install 保持一致：名字里的路径分隔符只取最后一段
        install_name = os.path.basename(
            str(install_name).replace('\\', '/').rstrip('/')) or install_name

        target_dir = os.path.join(self._install_dir, install_name)
        # 安装名是调用方直接给的字符串：url 那条路有 _url_to_install_name 清洗，这条路没有。
        # 越界的 name 能把安装目录之外的树 rmtree 掉（BUG-0019）—— 尺子抽成 _inside_install_dir，
        # uninstall / set_scope / get_scope / get_install_path 共用（BUG-0020 是同族的写侧）。
        if not self._inside_install_dir(install_name):
            return {"status": "error",
                    "message": f"安装名会越出安装目录，已拒绝: {install_name}"}
        if not os.path.isdir(target_dir):
            return {"status": "error", "message": f"Not installed: {install_name}"}

        manifest = self._find_manifest_for_path(target_dir)
        if manifest is None and not force:
            return {"status": "error",
                    "message": (f'该目录不在安装清单里，拒绝删除: {target_dir}'
                                f'（确需删除这个非 actus 安装的目录，请显式传 force=True / --force）'),
                    "details": {"path": os.path.abspath(target_dir),
                                "install_name": install_name}}

        _rmtree_force(target_dir)          # 只读 .git 对象：普通 rmtree 会 PermissionError

        # 移除安装清单：按 local_path 命中即可，不再要求调用方必须传 repo_url，
        # 否则用 name 卸载会留下一份指向已删目录的陈旧清单条目。
        removed_manifest = False
        if manifest is not None:
            try:
                reg = registry_mod.ActionRegistry(cache_dir=self._cache_dir)
                reg.remove_installation(manifest.get('url') or repo_url)
                removed_manifest = True
            except Exception:
                removed_manifest = False

        return {"status": "ok", "removed": install_name, "path": target_dir,
                "manifest_removed": removed_manifest,
                "forced": bool(manifest is None and force)}

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
            result = run_cmd_safe(
                ["git", "log", "--oneline", "-n", str(version + 1)],
                cwd=local_path, timeout=10
            )
            if result.returncode != 0:
                return {"status": "error", "message": f"Git log failed: {result.stderr}"}

            lines = result.stdout.strip().split("\n")
            if len(lines) <= version:
                return {"status": "error", "message": f"Version {version} not found"}

            target_commit = lines[version].split()[0]
            checkout = run_cmd_safe(
                ["git", "checkout", target_commit],
                cwd=local_path, timeout=10
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
            local = run_cmd_safe(["git", "rev-parse", "HEAD"],
                cwd=local_path, timeout=10)
            local_commit = local.stdout.strip() if local.returncode == 0 else ""

            remote = run_cmd_safe(["git", "ls-remote", "origin", "HEAD"],
                cwd=local_path, timeout=10)
            remote_commit = remote.stdout.split()[0] if remote.returncode == 0 and remote.stdout else ""

            # 审计修：查不到 ≠ 已是最新。
            # 改前 `has_update = local != remote and remote != ""`，在「目录不是 git 仓 /
            # 没有 origin / git 不可用 / 网络不通」时 remote 为空 → has_update=False 且
            # status=ok，CLI 于是打印「✅ 已是最新版本」——**根本没比对过**。
            # 现在：任一 commit 拿不到就返回 status='unknown'（has_update=None），
            # 明确告诉调用方「无法确认」，让 CLI/脚本不会误判成"最新"。
            if not local_commit or not remote_commit:
                reasons = []
                if not local_commit:
                    reasons.append('本地 git 版本未知（目录可能不是 git 仓或 git 不可用）')
                if not remote_commit:
                    reasons.append('远端版本未知（remote 不可达 / 未配置 origin / 网络不通）')
                return {
                    "status": "unknown",
                    "has_update": None,
                    "message": '无法确认远端版本：' + '；'.join(reasons),
                    "local_commit": local_commit,
                    "remote_commit": remote_commit,
                    "url": manifest.get("url")
                }

            return {
                "status": "ok",
                "has_update": local_commit != remote_commit,
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
        if not self._inside_install_dir(install_name):
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
        按**解析后的 meta['id']** 比对（格式无关）——原实现用字符串搜
        `"id": "xxx"` 只认旧格式 JSON，新格式 .actus.schema.md 全部找不到。
        """
        try:
            from .resolver import find_action_file
        except Exception:
            return None
        for actions_dir in self.discover_actions_dirs():
            hit = find_action_file(action_id, actions_dir)
            if hit:
                return hit
        return None

    # ── Scope 权限 ──

    def get_scope(self, repo_url: str = None, name: str = None) -> Optional[str]:
        """获取已安装仓库的 scope 配置。"""
        install_name = name or (self._url_to_install_name(repo_url) if repo_url else None)
        if not install_name:
            return None
        # 读侧同样不许越界：拿别人目录里的 .actus.scope 也是把权限边界读错了地方
        if not self._inside_install_dir(install_name):
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
        # BUG-0020：scope 是权限配置，写到安装目录之外等于把权限边界落错地方
        if not self._inside_install_dir(install_name):
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
            result = run_cmd_safe(cmd, timeout=120)
            if result.returncode == -9:
                return -1, "", "Git command timed out"
            if result.returncode == -1:
                # run_cmd_safe 把 Popen 抛的 FileNotFoundError 等吞成 rc=-1，
                # stderr 是异常字符串。git 不存在时按可读文案报，
                # 而不是把裸异常消息透传（BUG-13.26 同族）。
                return -1, "", "Git not found. Please install Git."
            return result.returncode, result.stdout, result.stderr
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

    def _write_scope_config(self, target_dir: str, scope: str,
                            overwrite: bool = False) -> bool:
        """写入 scope 配置文件；返回是否真的写了。

        **审计修（配置覆盖保护）**：改前无条件 `open(..., 'w')` —— 用户手工改过
        `.actus.scope` 后，重装/update 会静默覆盖回默认值（实测 hand-edit
        `trusted` 后重装变回 `sandbox`，且没有任何提示）。
        现在的语义：
          * 文件不存在 → 写（首次安装）；
          * 内容相同 → 不写（幂等）；
          * 内容不同且 overwrite=False（默认）→ **保留用户的**，返回 False，
            由调用方把「配置被保留」报给用户（不静默）；
          * overwrite=True → 显式覆盖（调用方明确要求时）。
        """
        scope_path = os.path.join(target_dir, ".actus.scope")
        if not overwrite and os.path.isfile(scope_path):
            try:
                with open(scope_path, "r", encoding="utf-8") as f:
                    existing = f.read()
            except OSError:
                existing = None
            if existing is not None:
                if existing == scope:
                    return False          # 幂等：内容一致，不必重写
                return False              # 保留用户手改，绝不静默覆盖
        with open(scope_path, "w", encoding="utf-8") as f:
            f.write(scope)
        return True

    def _write_visibility_config(self, target_dir: str, visibility: str,
                                  author: str = "", team: str = "",
                                  overwrite: bool = False) -> bool:
        """写入可见性配置文件；返回是否真的写了（保护语义同 `_write_scope_config`）。

        改前同样无条件覆盖：用户手改 `.actus.visibility`（例如改成 private）
        后重装会静默回退成 public —— 对私有动作是**权限语义被悄悄放宽**。
        """
        vis_path = os.path.join(target_dir, ".actus.visibility")
        if not overwrite and os.path.isfile(vis_path):
            try:
                with open(vis_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (OSError, ValueError):
                existing = None
            if isinstance(existing, dict):
                same = (existing.get("visibility") == visibility
                        and existing.get("author", "") == author
                        and existing.get("team", "") == team)
                if same:
                    return False          # 幂等
                return False              # 保留用户手改
        with open(vis_path, "w", encoding="utf-8") as f:
            json.dump({
                "visibility": visibility,
                "author": author,
                "team": team,
                "configured_at": time.time()
            }, f, indent=2)
        return True

    def install_with_visibility(self, repo_url: str, branch: str = "main",
                                 tag: str = None, commit: str = None,
                                 scope: str = None,
                                 visibility: str = "public",
                                 author: str = "",
                                 team: str = "",
                                 registry_name: str = "public",
                                 current_user: str = "",
                                 overwrite_config: bool = False) -> dict:
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
                              commit=commit, scope=scope,
                              overwrite_config=overwrite_config)

        if result.get("status") != "ok":
            return result

        # 3) 记录可见性元数据
        result["visibility"] = visibility
        result["author"] = author
        result["team"] = team
        result["registry_name"] = registry_name

        # 4) 写入可见性配置（已有用户配置时默认保留，不当静默覆盖）
        local_path = result.get("path", "")
        if local_path:
            result["visibility_written"] = self._write_visibility_config(
                local_path, visibility, author, team,
                overwrite=overwrite_config)

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


def uninstall_actions(repo_url: str = None, name: str = None,
                      force: bool = False) -> dict:
    """便捷函数：卸载动作仓库（force=True 才允许删非安装清单目录）。"""
    installer = ActionInstaller()
    return installer.uninstall(repo_url=repo_url, name=name, force=force)


def update_actions(repo_url: str = None, name: str = None) -> dict:
    """便捷函数：更新动作仓库。"""
    installer = ActionInstaller()
    return installer.update(repo_url=repo_url, name=name)


def list_installed_actions() -> List[dict]:
    """便捷函数：列出已安装的仓库。"""
    installer = ActionInstaller()
    return installer.list_installed()
