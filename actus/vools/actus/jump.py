"""jump.py —— 跳板机文件传输核心逻辑。

提供推/拉/同步的纯 Python 实现，供 .actus.md 动作和测试共用。
"""

import fnmatch
import os
import posixpath
import stat
import subprocess
import time
from typing import Dict, List, Optional, Tuple

from ._proc import run_cmd_safe, kill_tree


def shquote(value) -> str:
    """把一个值安全地引用为【单个】POSIX shell 单词。

    jump 通过 ssh 在远端 shell 里执行 find/mkdir/tar，路径与 --exclude 模式
    历史上用 f-string 裸拼：含空格的路径（文档示例 ``Victor/My Build/x.jar``）
    会被拆成多个词导致传输失败，含 ``;`` / ``$()`` / 反引号的值更可注入任意
    远端命令。这里统一用单引号包裹，并把值内部的单引号转成 ``'\\''``
    （POSIX 安全引用：单引号内一切皆字面量，唯一需要处理的就是单引号本身）。

    非字符串先转字符串；None 转空串。

    Example:
        >>> shquote('a b') == "'a b'"
        True
        >>> shquote("x'y") == "'x'\\\\''y'"
        True
    """
    if value is None:
        value = ""
    return "'" + str(value).replace("'", "'\\''") + "'"


def remote_join(base: str, relpath: str) -> str:
    """拼远程路径 —— 远端永远是 POSIX 分隔符，与跑在哪一侧无关。

    在 Windows 上用 `os.path.join` 会塞进反斜杠（`/tmp/dir\\a.txt`），scp 把整串当
    文件名去远端找 ⇒ 必然找不到；`sync` 的下载半边因此静默返回 0。
    """
    return posixpath.join(base, relpath.replace("\\", "/"))


def _is_safe_relpath(relpath: str) -> bool:
    """拒绝穿越型相对路径（`..`、绝对路径、盘符）。

    正常来源（本地 `os.walk` / 远端 `find`）不会产出这类路径，这里只给「远端文件名被
    恶意构造」这类边角再加一道闸：`os.path.join(local_path, relpath)` 若 relpath 含
    `..` 就会逃出目标目录；含绝对路径/盘符同理（`join` 会直接丢掉 base 用 relpath）。
    空串返回 True —— 表示目标目录本身。
    """
    if not relpath:
        return True
    p = relpath.replace("\\", "/")
    if p.startswith("/"):
        return False
    if len(p) >= 2 and p[1] == ":":
        return False                     # Windows 盘符，如 C:/x
    return ".." not in p.split("/")


# ── 排除规则 ──

def should_exclude(name: str, patterns: List[str]) -> bool:
    """检查文件名是否匹配排除规则。

    支持两种匹配模式：
    1. 文件名精确匹配或 glob 匹配
    2. 路径中任意部分匹配（如 node_modules 能匹配 src/node_modules/foo）
    """
    for pattern in patterns:
        # 直接匹配文件名
        if fnmatch.fnmatch(name, pattern):
            return True
        # 匹配路径中的任意部分
        parts = name.replace("\\", "/").split("/")
        for part in parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def collect_files(local_path: str, exclude: List[str] = None) -> List[str]:
    """收集要传输的文件列表。"""
    exclude = exclude or []
    files = []
    if os.path.isfile(local_path):
        if not should_exclude(os.path.basename(local_path), exclude):
            files.append(local_path)
    else:
        for root, dirs, filenames in os.walk(local_path):
            dirs[:] = [d for d in dirs if not should_exclude(d, exclude)]
            for fname in filenames:
                if should_exclude(fname, exclude):
                    continue
                fpath = os.path.join(root, fname)
                files.append(fpath)
    return files


def scan_local_files(local_path: str, exclude: List[str] = None) -> Dict[str, dict]:
    """扫描本地文件，返回 {相对路径: {size, mtime}} 字典。"""
    exclude = exclude or []
    files = {}
    if os.path.isfile(local_path):
        if not should_exclude(os.path.basename(local_path), exclude):
            stat = os.stat(local_path)
            files[""] = {"size": stat.st_size, "mtime": stat.st_mtime}
        return files

    for root, dirs, filenames in os.walk(local_path):
        dirs[:] = [d for d in dirs if not should_exclude(d, exclude)]
        for fname in filenames:
            if should_exclude(fname, exclude):
                continue
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, local_path).replace("\\", "/")
            if not _is_safe_relpath(relpath):
                continue                 # 防御：os.walk 不追符号链接，理论上不会出现
            try:
                stat = os.stat(fpath)
                files[relpath] = {"size": stat.st_size, "mtime": stat.st_mtime}
            except OSError:
                continue
    return files


# ── SSH 选项构建 ──

def build_ssh_opts(key_path: str = None, port: int = 22,
                   timeout: int = 300) -> List[str]:
    """构建 SSH 选项。"""
    opts = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", f"ConnectTimeout={min(timeout, 30)}",
        "-o", f"Port={port}",
    ]
    if key_path and os.path.isfile(key_path):
        opts.extend(["-i", key_path])
    return opts


# ── 远程文件扫描 ──

def scan_remote_files(remote_path: str, remote_host: str, remote_user: str,
                      port: int = 22, key_path: str = None,
                      password: str = None, exclude: List[str] = None,
                      timeout: int = 60) -> Dict[str, dict]:
    """扫描远程文件，返回 {相对路径: {size, mtime}} 字典。"""
    exclude = exclude or []
    remote_target = f"{remote_user}@{remote_host}"
    cmd = ("find " + shquote(remote_path)
           + " -type f -printf '%T@ %s %p\\n' 2>/dev/null")

    ssh_cmd = ["ssh"] + build_ssh_opts(key_path, port, timeout)
    ssh_cmd.extend([remote_target, cmd])

    try:
        result = run_cmd_safe(ssh_cmd, timeout=timeout)
        if result.returncode != 0:
            return {"__error__": result.stderr.strip()}

        files = {}
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.strip().split(' ', 2)
            if len(parts) < 3:
                continue
            try:
                mtime = float(parts[0])
                size = int(parts[1])
                fpath = parts[2]
                relpath = posixpath.relpath(fpath, remote_path)
                if not _is_safe_relpath(relpath):
                    continue             # 防御：远端文件名被恶意构造时拒绝出逃
                if not should_exclude(os.path.basename(relpath), exclude):
                    files[relpath] = {"size": size, "mtime": mtime}
            except (ValueError, OSError):
                continue
        return files
    except Exception as e:
        return {"__error__": str(e)}


# ── 同步计划计算 ──

def compute_sync_plan(local_files: Dict[str, dict],
                      remote_files: Dict[str, dict],
                      direction: str = "both",
                      strategy: str = "newer",
                      delete: bool = False) -> dict:
    """计算同步计划。"""
    upload = []
    download = []
    conflict = []
    skip = []
    to_delete = []

    all_files = set(list(local_files.keys()) + list(remote_files.keys()))

    for relpath in all_files:
        in_local = relpath in local_files
        in_remote = relpath in remote_files

        if in_local and not in_remote:
            if direction in ("upload", "both"):
                upload.append(relpath)
            else:
                skip.append(relpath)

        elif in_remote and not in_local:
            if direction in ("download", "both"):
                download.append(relpath)
            elif direction == "upload" and delete:
                to_delete.append(relpath)
            else:
                skip.append(relpath)

        else:
            local = local_files[relpath]
            remote = remote_files[relpath]

            if local["size"] == remote["size"] and abs(local["mtime"] - remote["mtime"]) < 2:
                skip.append(relpath)
            else:
                if direction == "upload":
                    upload.append(relpath)
                elif direction == "download":
                    download.append(relpath)
                else:
                    conflict.append({
                        "relpath": relpath,
                        "local": local,
                        "remote": remote
                    })

    return {
        "upload": upload,
        "download": download,
        "conflict": conflict,
        "skip": skip,
        "delete": to_delete
    }


# ── 单文件传输 ──

def upload_single(local_file: str, remote_file: str,
                  remote_host: str, remote_user: str,
                  port: int = 22, key_path: str = None,
                  password: str = None, timeout: int = 300) -> bool:
    """上传单个文件。"""
    remote_target = f"{remote_user}@{remote_host}:{os.path.dirname(remote_file)}"
    scp_cmd = ["scp"] + build_ssh_opts(key_path, port, timeout)
    scp_cmd.extend([local_file, remote_target])
    try:
        result = run_cmd_safe(scp_cmd, timeout=timeout)
        return result.returncode == 0
    except Exception:
        return False


def download_single(remote_file: str, local_file: str,
                    remote_host: str, remote_user: str,
                    port: int = 22, key_path: str = None,
                    password: str = None, timeout: int = 300) -> bool:
    """下载单个文件。"""
    os.makedirs(os.path.dirname(local_file), exist_ok=True)
    remote_target = f"{remote_user}@{remote_host}:{remote_file}"
    scp_cmd = ["scp"] + build_ssh_opts(key_path, port, timeout)
    scp_cmd.extend([remote_target, local_file])
    try:
        result = run_cmd_safe(scp_cmd, timeout=timeout)
        return result.returncode == 0
    except Exception:
        return False


# ── 批量传输 ──

def batch_upload(files: List[str], local_path: str, remote_path: str,
                 remote_host: str, remote_user: str,
                 port: int = 22, key_path: str = None,
                 password: str = None, timeout: int = 300) -> dict:
    """批量上传文件。

    files 是调用方直接传入的相对路径清单（可能来自被持久化/再加载的同步计划，
    而非当场由 scan_* 生成）。scan_* 已在入口过 _is_safe_relpath，但公开 API
    不能依赖调用方一定先过扫描 —— 与 8425cfb 同一道闸补齐：含 `..`/绝对路径/
    盘符的条目在这里【拒绝并记入 errors】，绝不参与 os.path.join 拼接
    （否则 `os.path.join(local_path, '../../x')` 会逃出 local_path，
    remote_join 同理丢 base）。
    """
    count = 0
    errors = []
    for relpath in files:
        if not _is_safe_relpath(relpath):
            errors.append("拒绝不安全相对路径: %s" % relpath)
            continue
        local_file = os.path.join(local_path, relpath)
        remote_file = remote_join(remote_path, relpath)
        if upload_single(local_file, remote_file, remote_host, remote_user,
                         port, key_path, password, timeout):
            count += 1
        else:
            errors.append(f"上传失败: {relpath}")
    return {"count": count, "errors": errors}


def batch_download(files: List[str], local_path: str, remote_path: str,
                   remote_host: str, remote_user: str,
                   port: int = 22, key_path: str = None,
                   password: str = None, timeout: int = 300) -> dict:
    """批量下载文件。安全闸同 batch_upload（下载写【进】local_path，穿越后果更直接）。"""
    count = 0
    errors = []
    for relpath in files:
        if not _is_safe_relpath(relpath):
            errors.append("拒绝不安全相对路径: %s" % relpath)
            continue
        local_file = os.path.join(local_path, relpath)
        remote_file = remote_join(remote_path, relpath)
        if download_single(remote_file, local_file, remote_host, remote_user,
                           port, key_path, password, timeout):
            count += 1
        else:
            errors.append(f"下载失败: {relpath}")
    return {"count": count, "errors": errors}


# ── 冲突解决 ──

def resolve_conflict(conflict: dict, local_path: str, remote_path: str,
                     remote_host: str, remote_user: str,
                     port: int = 22, key_path: str = None,
                     password: str = None, strategy: str = "newer",
                     timeout: int = 300) -> bool:
    """解决文件冲突。

    公开入口、conflict 由调用方传入（可能是持久化再加载的计划）——与
    batch_upload/batch_download 同口径先过 _is_safe_relpath，不安全条目
    直接判失败，绝不参与本地/远端路径拼接（BUG-62/63 同族）。
    """
    relpath = conflict["relpath"]
    if not _is_safe_relpath(relpath):
        return False
    local = conflict["local"]
    remote = conflict["remote"]

    if strategy == "newer":
        if local["mtime"] > remote["mtime"]:
            return upload_single(
                os.path.join(local_path, relpath),
                remote_join(remote_path, relpath),
                remote_host, remote_user, port, key_path, password, timeout
            )
        else:
            return download_single(
                remote_join(remote_path, relpath),
                os.path.join(local_path, relpath),
                remote_host, remote_user, port, key_path, password, timeout
            )
    elif strategy == "local":
        return upload_single(
            os.path.join(local_path, relpath),
            remote_join(remote_path, relpath),
            remote_host, remote_user, port, key_path, password, timeout
        )
    elif strategy == "remote":
        return download_single(
            remote_join(remote_path, relpath),
            os.path.join(local_path, relpath),
            remote_host, remote_user, port, key_path, password, timeout
        )
    return False


# ── 便捷函数 ──

def push(local_path: str, remote_path: str,
         remote_host: str, remote_user: str,
         port: int = 22, method: str = "paramiko",
         exclude: List[str] = None, key_path: str = None,
         password: str = None, dry_run: bool = False,
         timeout: int = 300) -> dict:
    """推送本地文件到远程。

    method 三条路，默认 paramiko（纯 Python SFTP，见 _push_paramiko）：
    - paramiko/sftp：纯 Python，不依赖远端有 ssh/lftp 工具，排除规则本地判定
    - tar+ssh：走系统 ssh + tar
    - 其它（scp 等）：走系统 scp
    """
    files = collect_files(local_path, exclude)
    if not files:
        return {"status": "ok", "files_transferred": 0, "bytes": 0, "message": "没有需要传输的文件"}

    if dry_run:
        return {"status": "ok", "files_transferred": 0, "dry_run": True,
                "files": files[:50], "total_files": len(files)}

    if method in ("paramiko", "sftp"):
        return _push_paramiko(local_path, remote_path, remote_host, remote_user,
                              port, key_path, password, exclude, timeout)
    elif method == "tar+ssh":
        return _push_tar_ssh(local_path, remote_path, remote_host, remote_user,
                             port, key_path, password, exclude, timeout)
    else:
        return _push_scp(local_path, remote_path, remote_host, remote_user,
                         port, key_path, password, files, timeout)


def pull(remote_path: str, local_path: str,
         remote_host: str, remote_user: str,
         port: int = 22, method: str = "paramiko",
         exclude: List[str] = None, key_path: str = None,
         password: str = None, dry_run: bool = False,
         timeout: int = 300) -> dict:
    """从远程拉取文件到本地（method 语义同 push，默认 paramiko）。"""
    os.makedirs(local_path, exist_ok=True)

    if dry_run:
        # files_transferred/bytes 显式给 0：dry_run 的出参形状必须与真跑一致，
        # 否则调用方要按两套形状处理。
        return {"status": "ok", "files_transferred": 0, "bytes": 0,
                "dry_run": True, "transport": method, "message": "预览模式"}

    if method in ("paramiko", "sftp"):
        return _pull_paramiko(remote_path, local_path, remote_host, remote_user,
                              port, key_path, password, exclude, timeout)
    elif method == "tar+ssh":
        return _pull_tar_ssh(remote_path, local_path, remote_host, remote_user,
                             port, key_path, password, exclude, timeout)
    else:
        return _pull_scp(remote_path, local_path, remote_host, remote_user,
                         port, key_path, password, timeout)


def sync(local_path: str, remote_path: str,
         remote_host: str, remote_user: str,
         port: int = 22, direction: str = "both",
         strategy: str = "newer", exclude: List[str] = None,
         key_path: str = None, password: str = None,
         dry_run: bool = False, timeout: int = 600,
         delete: bool = False, method: str = "paramiko") -> dict:
    """双向同步（method 语义同 push，默认 paramiko）。

    method 加在**参数表末尾**：jump_sync 动作按位置传前 13 个实参，
    插在中间会把 direction/strategy 整列错位。
    """
    if method in ("paramiko", "sftp"):
        return _sync_paramiko(local_path, remote_path, remote_host, remote_user,
                              port, direction, strategy, exclude, key_path,
                              password, dry_run, timeout, delete)

    local_files = scan_local_files(local_path, exclude)
    remote_files = scan_remote_files(remote_path, remote_host, remote_user,
                                     port, key_path, password, exclude, timeout)

    if isinstance(remote_files, dict) and "__error__" in remote_files:
        return {"status": "error", "message": remote_files["__error__"]}

    plan = compute_sync_plan(local_files, remote_files, direction, strategy)

    if dry_run:
        return {"status": "ok", "dry_run": True,
                "upload": len(plan["upload"]), "download": len(plan["download"]),
                "conflicts": len(plan["conflict"]), "skip": len(plan["skip"])}

    uploaded = 0
    downloaded = 0
    conflicts_resolved = 0
    errors = []

    if plan["upload"]:
        result = batch_upload(plan["upload"], local_path, remote_path,
                              remote_host, remote_user, port, key_path, password, timeout)
        uploaded = result["count"]
        errors.extend(result["errors"])

    if plan["download"]:
        result = batch_download(plan["download"], local_path, remote_path,
                                remote_host, remote_user, port, key_path, password, timeout)
        downloaded = result["count"]
        errors.extend(result["errors"])

    for conflict in plan["conflict"]:
        if resolve_conflict(conflict, local_path, remote_path,
                            remote_host, remote_user, port, key_path, password,
                            strategy, timeout):
            conflicts_resolved += 1

    return {"status": "ok" if not errors else "partial",
            "uploaded": uploaded, "downloaded": downloaded,
            "conflicts": conflicts_resolved, "errors": errors[:10]}


# ── 内部实现 ──

def _push_scp(local_path, remote_path, remote_host, remote_user,
              port, key_path, password, files, timeout):
    """scp 推送。"""
    remote_target = f"{remote_user}@{remote_host}:{remote_path}"
    scp_cmd = ["scp", "-r"] + build_ssh_opts(key_path, port, timeout)

    # 两种入参形状都要先把远端目录建出来 —— scp 不会自己建，单文件分支以前跳过
    # 这一步：`scp: dest open "/tmp/…/push_1": No such file or directory`。
    ssh_cmd = ["ssh"] + build_ssh_opts(key_path, port, timeout)
    ssh_cmd.extend([f"{remote_user}@{remote_host}",
                    "mkdir -p " + shquote(remote_path)])
    run_cmd_safe(ssh_cmd, timeout=30)
    scp_cmd.extend([local_path, remote_target])

    try:
        result = run_cmd_safe(scp_cmd, timeout=timeout)
        if result.returncode != 0:
            return {"status": "error", "message": result.stderr}
        total_bytes = sum(os.path.getsize(f) for f in files if os.path.isfile(f))
        return {"status": "ok", "files_transferred": len(files), "bytes": total_bytes}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _push_tar_ssh(local_path, remote_path, remote_host, remote_user,
                  port, key_path, password, exclude, timeout):
    """tar+ssh 推送。"""
    remote_target = f"{remote_user}@{remote_host}"
    qrp = shquote(remote_path)
    remote_cmd = "mkdir -p " + qrp + " && tar xzf - -C " + qrp
    tar_cmd = ["tar", "czf", "-"]
    for pattern in exclude or []:
        tar_cmd.extend(["--exclude", pattern])
    if os.path.isfile(local_path):
        tar_cmd.extend(["-C", os.path.dirname(local_path), os.path.basename(local_path)])
    else:
        tar_cmd.extend(["-C", local_path, "."])

    try:
        tar_proc = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            ssh_cmd = ["ssh"] + build_ssh_opts(key_path, port, timeout) + [remote_target, remote_cmd]
            ssh_proc = subprocess.Popen(ssh_cmd, stdin=tar_proc.stdout,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception:
            # ssh 缺失/无法启动：tar 已起但无人消费管道 → 必须杀掉，否则孤儿进程
            # 继续写管道直到写满后挂死（与超时同族：整树安全）。
            kill_tree(tar_proc)
            raise
        try:
            ssh_proc.communicate(timeout=timeout)
            tar_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # 管线超时：tar 与 ssh 都要杀掉，否则 tar 的孤儿进程继续写管道
            kill_tree(ssh_proc)
            kill_tree(tar_proc)
            return {"status": "error", "message": f"传输超时（{timeout}秒）"}
        if ssh_proc.returncode != 0:
            return {"status": "error", "message": "ssh 失败"}
        files = collect_files(local_path, exclude)
        total_bytes = sum(os.path.getsize(f) for f in files if os.path.isfile(f))
        return {"status": "ok", "files_transferred": len(files), "bytes": total_bytes}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _pull_scp(remote_path, local_path, remote_host, remote_user,
              port, key_path, password, timeout):
    """scp 拉取。"""
    remote_target = f"{remote_user}@{remote_host}:{remote_path}"
    scp_cmd = ["scp", "-r"] + build_ssh_opts(key_path, port, timeout)
    scp_cmd.extend([remote_target, local_path])
    try:
        result = run_cmd_safe(scp_cmd, timeout=timeout)
        if result.returncode != 0:
            return {"status": "error", "message": result.stderr}
        file_count = 0
        total_bytes = 0
        for root, dirs, files in os.walk(local_path):
            for f in files:
                fpath = os.path.join(root, f)
                if os.path.isfile(fpath):
                    file_count += 1
                    total_bytes += os.path.getsize(fpath)
        return {"status": "ok", "files_transferred": file_count, "bytes": total_bytes}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _pull_tar_ssh(remote_path, local_path, remote_host, remote_user,
                  port, key_path, password, exclude, timeout):
    """tar+ssh 拉取。"""
    remote_target = f"{remote_user}@{remote_host}"
    qrp = shquote(remote_path)
    remote_tar_cmd = "tar czf -"
    for pattern in exclude or []:
        # 不能手工包单引号：pattern 内含单引号即闭合注入；统一走 shquote
        remote_tar_cmd += " --exclude " + shquote(pattern)
    # dirname/basename 后再引用：POSIX 远端，用 posixpath 切（remote_path 是远端路径）
    remote_tar_cmd += (" -C " + shquote(posixpath.dirname(remote_path))
                       + " " + shquote(posixpath.basename(remote_path)))

    try:
        ssh_cmd = ["ssh"] + build_ssh_opts(key_path, port, timeout) + [remote_target, remote_tar_cmd]
        ssh_proc = subprocess.Popen(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            tar_cmd = ["tar", "xzf", "-", "-C", local_path]
            tar_proc = subprocess.Popen(tar_cmd, stdin=ssh_proc.stdout,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception:
            # tar 缺失/无法启动：ssh 已起但无人读管道 → 远端 tar 继续写会挂死，
            # 本地 ssh 进程也必须杀掉（与超时同族：整树安全）。
            kill_tree(ssh_proc)
            raise
        try:
            tar_proc.communicate(timeout=timeout)
            ssh_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # 管线超时：tar 与 ssh 都要杀掉，否则 ssh 的孤儿进程继续写管道
            kill_tree(tar_proc)
            kill_tree(ssh_proc)
            return {"status": "error", "message": f"传输超时（{timeout}秒）"}
        if tar_proc.returncode != 0:
            return {"status": "error", "message": "解压失败"}
        file_count = 0
        total_bytes = 0
        for root, dirs, files in os.walk(local_path):
            for f in files:
                fpath = os.path.join(root, f)
                if os.path.isfile(fpath):
                    file_count += 1
                    total_bytes += os.path.getsize(fpath)
        return {"status": "ok", "files_transferred": file_count, "bytes": total_bytes}
    except Exception as e:
        return {"status": "error", "message": str(e)}
__all__ = [
    'batch_download',
    'batch_upload',
    'build_ssh_opts',
    'collect_files',
    'compute_sync_plan',
    'download_single',
    'pull',
    'push',
    'remote_join',
    'scan_remote_files_paramiko',
    '_sync_paramiko',
    '_pull_paramiko',
    '_push_paramiko',
    '_sftp_makedirs',
    '_sftp_close',
    '_sftp_connect',
    '_import_paramiko',
    'PARAMIKO_HINT',
    'remote_join',
    'resolve_conflict',
    'scan_local_files',
    'scan_remote_files',
    'shquote',
    'should_exclude',
    'sync',
    'upload_single'
]


# ============================================================
# paramiko(SFTP) 后端 —— 默认传输路径
# ============================================================
#
# 为什么排在 scp/tar+ssh 前面（owner 2026-10-13 定：优先使用 paramiko）：
#
# 1. **纯 Python，不依赖外部工具**。scp/ssh/tar 三条老路都要本机装 OpenSSH 客户端
#    （Windows 10 1809 以后才有 scp，还常缺 tar）；paramiko 只要能 import。
# 2. **不依赖远端有命令**。tar+ssh 在远端跑 `tar xzf`，缺 tar 就整条失败。
# 3. **排除规则本地判定完**，远端零命令（老路的 tar --exclude 是远端执行的）。
# 4. **一次连接传所有文件**。老路的 batch_upload 是**每个文件起一个 scp 进程**
#    （upload_single 里 subprocess.run），传 1000 个文件就是 1000 次 TCP+握手。
# 5. **主机密钥策略可控**：AutoAddPolicy 等价于老路的 StrictHostKeyChecking=no，
#    但显式写出来比藏在 ssh 命令行里好审计。
#
# 代价与边界：
# - paramiko 不是 stdlib，按可选依赖惰性导入（见 _import_paramiko）；缺失时给
#   可执行提示而不是静默回退到 scp（docs/38 §1：严禁静默降级）。
# - 密钥认证走 paramiko 自己的 agent/look_for_keys，与 ssh 的 ~/.ssh/config
#   （IdentityFile、ProxyJump 等）**不等价**：需要跳板链时仍走 tar+ssh 或 ssh -J。

PARAMIKO_HINT = (
    "缺少 paramiko：pip install paramiko；"
    "或显式指定 method=tar+ssh / scp 走系统 ssh 工具"
)


def _import_paramiko():
    """惰性导入 paramiko，返回 (module, None) 或 (None, 错误文案)。

    为什么不放在模块顶层：paramiko 是可选依赖，顶层硬 import 会让**整个模块**
    在没装它的机器上不可用 —— 而 scp/tar+ssh 两条路根本不需要它。
    """
    try:
        import paramiko
    except ImportError as e:
        return None, "%s（%s）" % (PARAMIKO_HINT, e)
    return paramiko, None


def _patch_paramiko_filename_decoding():
    """把 paramiko 的回包解码改成 surrogateescape，幂等；返回是否成功。

    实测坑（2026-10-13 真机 47.93.7.122:10022）：远端目录里只要有一个非ASCII
    文件名，`listdir_attr` / `listdir` 就抛
        UnicodeDecodeError: 'utf-8' codec can't decode bytes in position 61-62
    栈在 paramiko/message.py 的 `get_text -> util.u -> s.decode('utf-8')`。
    根因是同一批回包里两个字段编码不同：
      - filename：SFTP 协议规定的字节，我们自己按 utf-8 传的 ⇒ 合法；
      - longname：服务端按**本地 locale** 生成的 `ls -l` 可读行 ⇒ 非 utf-8。
    而 longname 的内容我们从不读（只用 filename/st_mode/st_size/st_mtime），
    却要为它的解码失败整条传输/扫描买单。

    修法：只把解码策略换成 surrogateescape —— 非法字节保留原样、可往返回服务端，
    合法 utf-8 完全不受影响。**不改 paramiko 源码**，只在本进程内换掉
    Message.get_text（幂等：打过一次就不再打）。
    """
    try:
        from paramiko.message import Message
    except Exception:
        return False
    if getattr(Message.get_text, "_actus_surrogateescape", False):
        return True

    def get_text(self):
        raw = self.get_string()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            # 保留原字节（surrogateescape 可往返）：发给服务端的路径因此还是对的
            return raw.decode("utf-8", "surrogateescape")

    get_text._actus_surrogateescape = True
    Message.get_text = get_text
    return True


def _sftp_connect(remote_host, remote_user, port=22, key_path=None,
                  password=None, timeout=300):
    """建 SFTP 会话。

    返回 ((client, sftp), None) 或 (None, 错误 dict)；调用方负责 close。
    主机密钥策略用 AutoAddPolicy —— 与 build_ssh_opts 里那两条
    StrictHostKeyChecking=no / UserKnownHostsFile=/dev/null 对齐；
    不设的话首次连任何机器都会抛 "not found in known_hosts"。
    """
    _patch_paramiko_filename_decoding()
    paramiko, err = _import_paramiko()
    if paramiko is None:
        return None, {"status": "error", "message": err}

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = {
        "hostname": remote_host,
        "username": remote_user,
        "port": int(port),
        "timeout": timeout,
        "auth_timeout": timeout,
        "banner_timeout": timeout,
        "allow_agent": True,
        "look_for_keys": True,
    }
    if key_path and os.path.isfile(key_path):
        kwargs["key_filename"] = key_path
    if password:
        kwargs["password"] = password

    try:
        client.connect(**kwargs)
    except Exception as e:
        try:
            client.close()
        except Exception:
            pass
        return None, {"status": "error", "message": "SSH 连接失败: %s" % e}

    try:
        sftp = client.open_sftp()
    except Exception as e:
        try:
            client.close()
        except Exception:
            pass
        return None, {"status": "error", "message": "打开 SFTP 通道失败: %s" % e}
    return (client, sftp), None


SFTP_KIND_FILE = "file"
SFTP_KIND_DIR = "dir"
SFTP_KIND_OTHER = "other"


def _sftp_entry_kind(attr):
    """判定一个 SFTP 条目是目录 / 普通文件 / 其他，并回报是否靠了兜底。

    为什么不能直接信 S_ISREG/S_ISDIR —— 实测这台跳板机的 sftp-server 对**文件**
    返回的 st_mode 只有权限位（0o666），**没有 S_IFREG 类型位**（正常 Linux 会给
    0o100666）；目录的类型位倒是全的（0o40666）。于是 S_ISREG(0o666) -> False，
    所有文件被静默跳过：scan 返回 {}、pull 报"成功"却传 0 个字节，全程不报错
    （单测的 FakeSFTP 造的是标准 S_IFREG|0o644，所以这类用例全绿也抓不到）。

    判定顺序（先看类型位，再兜底）：
        S_IFDIR                -> dir
        S_IFREG                -> file
        类型位全 0 且权限位非 0  -> file（服务端没给类型位，兜底）
        类型位非 0 且非 DIR/REG  -> other（符号链接/设备/fifo，不传）
        全 0                    -> other（无从判断，不猜）

    返回 (kind, inferred)：inferred=True 表示这条是靠兜底判的，调用方把它
    如实报进出参（mode_inferred），免得"兜底"又变成一件看不见的事。
    """
    mode = getattr(attr, "st_mode", 0) or 0
    if stat.S_ISDIR(mode):
        return SFTP_KIND_DIR, False
    if stat.S_ISREG(mode):
        return SFTP_KIND_FILE, False
    type_bits = mode & 0o170000
    if type_bits == 0:
        if mode & 0o777:
            return SFTP_KIND_FILE, True
        return ((SFTP_KIND_FILE, True) if getattr(attr, "st_size", 0)
                else (SFTP_KIND_OTHER, True))
    return SFTP_KIND_OTHER, False


def _sftp_close(client, sftp):
    """关会话：两个 close 都要试 —— 一处抛异常不能连带另一处漏关（漏的是连接）。"""
    for closer in (sftp, client):
        try:
            closer.close()
        except Exception:
            pass


def _sftp_makedirs(sftp, remote_dir):
    """SFTP 建多级目录（paramiko 只有 mkdir，没有 mkdir -p）。

    已存在就跳过；"刚被别人建好"那种竞态再 stat 一次确认，确认存在即当成功
    —— 否则并发写同一目录时第二个写者会拿到一个假的失败。
    """
    if not remote_dir:
        return
    normalized = remote_dir.replace("\\", "/")
    cur = "/" if normalized.startswith("/") else ""
    for part in [p for p in normalized.split("/") if p]:
        cur = posixpath.join(cur, part) if cur else part
        try:
            sftp.stat(cur)
            continue
        except IOError:
            pass
        try:
            sftp.mkdir(cur)
        except IOError:
            try:
                sftp.stat(cur)
            except IOError:
                raise


def _sftp_walk_put(sftp, local_root, remote_root, exclude, counter, errors):
    """本地目录 → 远端，逐文件 put（counter/errors 由调用方持有便于汇总）。"""
    for name in sorted(os.listdir(local_root)):
        lpath = os.path.join(local_root, name)
        if os.path.isdir(lpath):
            if should_exclude(name, exclude):
                continue
            rpath = posixpath.join(remote_root, name)
            _sftp_makedirs(sftp, rpath)
            _sftp_walk_put(sftp, lpath, rpath, exclude, counter, errors)
        elif os.path.isfile(lpath):
            if should_exclude(name, exclude):
                continue
            rpath = posixpath.join(remote_root, name)
            try:
                sftp.put(lpath, rpath)
                counter["files"] += 1
                counter["bytes"] += os.path.getsize(lpath)
            except Exception as e:
                errors.append("上传失败 %s: %s" % (rpath, e))


def _sftp_walk_get(sftp, remote_root, local_root, exclude, counter, errors):
    """远端目录 → 本地，逐文件 get。

    符号链接/设备文件一类非普通文件**跳过**（SFTP 读不出目标内容），
    计数进 counter["skipped"]，不混进 errors —— 它们不是失败，是有意不传。
    """
    for attr in sftp.listdir_attr(remote_root):
        name = attr.filename
        # 远端可控文件名：恶意服务端可让 listdir 返回名为 `../escape` 的条目，
        # 下面 os.path.join(local_root, name) 就把本地写点带出 local_root
        # （sftp.get / makedirs 同理）。与 scan_remote_files_paramiko(BUG-63)、
        # ssh 路 scan_remote_files(8425cfb) 同一道 _is_safe_relpath 闸，补这条
        # 递归直拉路径（_pull_paramiko 对目录走的正是这里，不经过 scan）。
        if not _is_safe_relpath(name):
            continue
        if should_exclude(name, exclude):
            continue
        rpath = posixpath.join(remote_root, name)
        lpath = os.path.join(local_root, name)
        kind, inferred = _sftp_entry_kind(attr)
        if kind == SFTP_KIND_DIR:
            os.makedirs(lpath, exist_ok=True)
            _sftp_walk_get(sftp, rpath, lpath, exclude, counter, errors)
        elif kind == SFTP_KIND_FILE:
            try:
                sftp.get(rpath, lpath)
                counter["files"] += 1
                counter["bytes"] += int(getattr(attr, "st_size", 0) or 0)
                if inferred:
                    counter["mode_inferred"] = counter.get("mode_inferred", 0) + 1
            except Exception as e:
                errors.append("下载失败 %s: %s" % (rpath, e))
        else:
            counter["skipped"] += 1


def _paramiko_result(counter, errors, extra=None):
    """paramiko 各路共用的出参形状：ok / partial + 计数 + transport 自报家门。"""
    status = "ok" if not errors else "partial"
    out = {
        "status": status,
        "files_transferred": counter["files"],
        "bytes": counter["bytes"],
        "transport": "paramiko",
    }
    if counter.get("skipped"):
        out["skipped_non_regular"] = counter["skipped"]
    if counter.get("mode_inferred"):
        # 服务端没给 st_mode 文件类型位、靠兜底判成文件的条数。如实报出：
        # 计数只在 counter 里、出参不露的话，"判定是兜底的"这件事就又是看不见的。
        out["mode_inferred"] = counter["mode_inferred"]
    if errors:
        out["errors"] = errors[:10]
    if extra:
        out.update(extra)
    return out


def _push_paramiko(local_path, remote_path, remote_host, remote_user,
                   port=22, key_path=None, password=None, exclude=None,
                   timeout=300):
    """paramiko(SFTP) 推送：目录递归建 + 逐文件 put；单文件按全路径 put。"""
    pair, err = _sftp_connect(remote_host, remote_user, port, key_path,
                              password, timeout)
    if err:
        return err
    client, sftp = pair

    counter = {"files": 0, "bytes": 0, "skipped": 0}
    errors = []
    try:
        if os.path.isfile(local_path):
            # 单文件：remote_path 就是**文件全路径**，不能再拼一层 basename
            # （scp 老路在这里踩过 dest open .../push_1: No such file or directory）。
            remote_dir = posixpath.dirname(remote_path.replace("\\", "/"))
            if remote_dir:
                _sftp_makedirs(sftp, remote_dir)
            sftp.put(local_path, remote_path)
            counter["files"] = 1
            counter["bytes"] = os.path.getsize(local_path)
        elif os.path.isdir(local_path):
            _sftp_makedirs(sftp, remote_path)
            _sftp_walk_put(sftp, local_path, remote_path, exclude or [],
                           counter, errors)
        else:
            return {"status": "error", "message": "本地路径不存在: %s" % local_path}
    except Exception as e:
        return {"status": "error", "message": "SFTP 推送失败: %s" % e}
    finally:
        _sftp_close(client, sftp)
    return _paramiko_result(counter, errors)


def _pull_paramiko(remote_path, local_path, remote_host, remote_user,
                   port=22, key_path=None, password=None, exclude=None,
                   timeout=300):
    """paramiko(SFTP) 拉取：远端是文件就落到 local_path，是目录就递归取。"""
    import stat as _stat

    pair, err = _sftp_connect(remote_host, remote_user, port, key_path,
                              password, timeout)
    if err:
        return err
    client, sftp = pair

    counter = {"files": 0, "bytes": 0, "skipped": 0}
    errors = []
    try:
        remote_path = remote_path.replace("\\", "/")
        try:
            attr = sftp.stat(remote_path)
        except IOError as e:
            return {"status": "error",
                    "message": "远端路径不可读: %s（%s）" % (remote_path, e)}

        if _stat.S_ISREG(attr.st_mode):
            # local_path 已是目录 → 放进去（对齐 scp -r 的落位行为）
            target = (os.path.join(local_path, posixpath.basename(remote_path))
                      if os.path.isdir(local_path) else local_path)
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            sftp.get(remote_path, target)
            counter["files"] = 1
            counter["bytes"] = int(getattr(attr, "st_size", 0) or 0)
        elif _stat.S_ISDIR(attr.st_mode):
            os.makedirs(local_path, exist_ok=True)
            _sftp_walk_get(sftp, remote_path, local_path, exclude or [],
                           counter, errors)
        else:
            return {"status": "error",
                    "message": "远端路径既不是文件也不是目录: %s" % remote_path}
    except Exception as e:
        return {"status": "error", "message": "SFTP 拉取失败: %s" % e}
    finally:
        _sftp_close(client, sftp)
    return _paramiko_result(counter, errors)


def scan_remote_files_paramiko(remote_path: str, remote_host: str,
                               remote_user: str, port: int = 22,
                               key_path: str = None, password: str = None,
                               exclude: List[str] = None,
                               timeout: int = 60,
                               inferred_counter: list = None) -> Dict[str, dict]:
    """paramiko 版远端扫描：SFTP 递归 stat，不在远端跑任何命令。

    ssh 版 scan_remote_files 依赖远端 `find <path> -type f -printf '%T@ %s %p'`：
    minimal 容器常常没有 find，或 busybox find 不支持 -printf ⇒ 整次扫描直接失败，
    sync 于是把"扫不出来"当成"远端没有文件"，plan 全落到 upload 侧。
    SFTP 这条路只需要远端开 SSH 子系统。
    """
    exclude = exclude or []
    pair, err = _sftp_connect(remote_host, remote_user, port, key_path,
                              password, timeout)
    if err:
        return {"__error__": err["message"]}
    client, sftp = pair

    files: Dict[str, dict] = {}

    inferred_count = [0]

    def walk(remote_dir, rel_base):
        try:
            entries = sftp.listdir_attr(remote_dir)
        except IOError as e:
            raise RuntimeError("列目录失败 %s: %s" % (remote_dir, e))
        for attr in entries:
            if should_exclude(attr.filename, exclude):
                continue
            relpath = (posixpath.join(rel_base, attr.filename)
                       if rel_base else attr.filename)
            # 与 ssh 侧 scan_remote_files（含 8425cfb 的 _is_safe_relpath 闸）对齐：
            # attr.filename 由远端控制，含 `..`/绝对/盘符时 relpath 会把「远端文件」
            # 带出同步根。不拦的话它在 compute_sync_plan 里进 plan["download"]，
            # 下游 `os.path.join(local_path, relpath)` + makedirs + sftp.get 就成了
            # 恶意远端列表驱动的本地越界写（pull/sync 全程无需本地文件配合）。
            if not _is_safe_relpath(relpath):
                continue
            kind, inferred = _sftp_entry_kind(attr)
            if kind == SFTP_KIND_DIR:
                walk(posixpath.join(remote_dir, attr.filename), relpath)
            elif kind == SFTP_KIND_FILE:
                files[relpath] = {
                    "size": int(getattr(attr, "st_size", 0) or 0),
                    "mtime": float(getattr(attr, "st_mtime", 0) or 0),
                }
                if inferred:
                    inferred_count[0] += 1

    try:
        walk(remote_path.replace("\\", "/"), "")
    except Exception as e:
        return {"__error__": str(e)}
    finally:
        _sftp_close(client, sftp)
    # "有多少条是靠兜底判成文件的"（服务端没给 st_mode 类型位）通过 out 参数回传，
    # **不塞进返回值** —— 返回值的契约是 {relpath: {size, mtime}}，多一个
    # __mode_inferred__ 整数键会被 compute_sync_plan 当成文件去取 ["size"] 而TypeError。
    if inferred_counter is not None:
        inferred_counter.append(inferred_count[0])
    return files


def _sync_paramiko(local_path, remote_path, remote_host, remote_user,
                   port=22, direction="both", strategy="newer", exclude=None,
                   key_path=None, password=None, dry_run=False, timeout=600,
                   delete=False):
    """双向同步的 paramiko 实现：一个 SFTP 会话走完全程。

    与 sync 老路同一份 plan（compute_sync_plan），差别只在传输层：
    老路每个文件一次 scp 子进程，这里一次连接 + 复用。
    """
    exclude = exclude or []
    local_files = scan_local_files(local_path, exclude)
    inferred = []
    remote_files = scan_remote_files_paramiko(remote_path, remote_host,
                                              remote_user, port, key_path,
                                              password, exclude, timeout,
                                              inferred_counter=inferred)
    if isinstance(remote_files, dict) and "__error__" in remote_files:
        return {"status": "error", "message": remote_files["__error__"]}

    plan = compute_sync_plan(local_files, remote_files, direction, strategy,
                             delete)
    if dry_run:
        return {"status": "ok", "dry_run": True, "transport": "paramiko",
                "upload": len(plan["upload"]), "download": len(plan["download"]),
                "conflicts": len(plan["conflict"]), "skip": len(plan["skip"]),
                "delete": len(plan["delete"])}

    pair, err = _sftp_connect(remote_host, remote_user, port, key_path,
                              password, timeout)
    if err:
        return err
    client, sftp = pair

    counter = {"files": 0, "bytes": 0, "skipped": 0}
    errors = []
    conflicts_resolved = 0
    uploaded = downloaded = 0
    try:
        for relpath in plan["upload"]:
            lpath = os.path.join(local_path, relpath) if relpath else local_path
            rpath = remote_join(remote_path, relpath) if relpath else remote_path
            try:
                if relpath:
                    _sftp_makedirs(sftp, posixpath.dirname(rpath))
                sftp.put(lpath, rpath)
                counter["files"] += 1
                counter["bytes"] += os.path.getsize(lpath)
                uploaded += 1
            except Exception as e:
                errors.append("上传失败 %s: %s" % (relpath or ".", e))

        for relpath in plan["download"]:
            rpath = remote_join(remote_path, relpath)
            lpath = os.path.join(local_path, relpath)
            try:
                parent = os.path.dirname(lpath)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                sftp.get(rpath, lpath)
                counter["files"] += 1
                downloaded += 1
            except Exception as e:
                errors.append("下载失败 %s: %s" % (relpath, e))

        for relpath in plan["delete"]:
            rpath = remote_join(remote_path, relpath)
            try:
                sftp.remove(rpath)
            except Exception as e:
                errors.append("删除失败 %s: %s" % (relpath, e))

        for item in plan["conflict"]:
            relpath = item["relpath"]
            local, remote = item["local"], item["remote"]
            # newer：本地新就推、远端新就拉；local/remote：单边强制
            take_local = {"newer": local["mtime"] > remote["mtime"],
                          "local": True, "remote": False}.get(strategy, True)
            try:
                if take_local:
                    lpath = os.path.join(local_path, relpath)
                    rpath = remote_join(remote_path, relpath)
                    _sftp_makedirs(sftp, posixpath.dirname(rpath))
                    sftp.put(lpath, rpath)
                else:
                    rpath = remote_join(remote_path, relpath)
                    lpath = os.path.join(local_path, relpath)
                    parent = os.path.dirname(lpath)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    sftp.get(rpath, lpath)
                conflicts_resolved += 1
            except Exception as e:
                errors.append("冲突解决失败 %s: %s" % (relpath, e))
    except Exception as e:
        return {"status": "error", "message": "SFTP 同步失败: %s" % e}
    finally:
        _sftp_close(client, sftp)

    out = _paramiko_result(counter, errors)
    out.update({"uploaded": uploaded, "downloaded": downloaded,
                "conflicts": conflicts_resolved, "skipped": len(plan["skip"])})
    if inferred and inferred[0]:
        # 服务端没给 st_mode 类型位、靠兜底判成文件的条数（如实报出，不静默）
        out["mode_inferred"] = inferred[0]
    return out
