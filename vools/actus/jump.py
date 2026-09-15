"""jump.py —— 跳板机文件传输核心逻辑。

提供推/拉/同步的纯 Python 实现，供 .actus.md 动作和测试共用。
"""

import os
import subprocess
import time
import fnmatch
from typing import Dict, List, Optional, Tuple


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
            relpath = os.path.relpath(fpath, local_path)
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
        "-p", str(port),
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
    cmd = f"find {remote_path} -type f -printf '%T@ %s %p\\n' 2>/dev/null"

    ssh_cmd = ["ssh"] + build_ssh_opts(key_path, port, timeout)
    ssh_cmd.extend([remote_target, cmd])

    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
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
                relpath = os.path.relpath(fpath, remote_path)
                if not should_exclude(os.path.basename(relpath), exclude):
                    files[relpath] = {"size": size, "mtime": mtime}
            except (ValueError, OSError):
                continue
        return files
    except subprocess.TimeoutExpired:
        return {"__error__": "远程扫描超时"}
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
        result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=timeout)
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
        result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0
    except Exception:
        return False


# ── 批量传输 ──

def batch_upload(files: List[str], local_path: str, remote_path: str,
                 remote_host: str, remote_user: str,
                 port: int = 22, key_path: str = None,
                 password: str = None, timeout: int = 300) -> dict:
    """批量上传文件。"""
    count = 0
    errors = []
    for relpath in files:
        local_file = os.path.join(local_path, relpath)
        remote_file = os.path.join(remote_path, relpath)
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
    """批量下载文件。"""
    count = 0
    errors = []
    for relpath in files:
        local_file = os.path.join(local_path, relpath)
        remote_file = os.path.join(remote_path, relpath)
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
    """解决文件冲突。"""
    relpath = conflict["relpath"]
    local = conflict["local"]
    remote = conflict["remote"]

    if strategy == "newer":
        if local["mtime"] > remote["mtime"]:
            return upload_single(
                os.path.join(local_path, relpath),
                os.path.join(remote_path, relpath),
                remote_host, remote_user, port, key_path, password, timeout
            )
        else:
            return download_single(
                os.path.join(remote_path, relpath),
                os.path.join(local_path, relpath),
                remote_host, remote_user, port, key_path, password, timeout
            )
    elif strategy == "local":
        return upload_single(
            os.path.join(local_path, relpath),
            os.path.join(remote_path, relpath),
            remote_host, remote_user, port, key_path, password, timeout
        )
    elif strategy == "remote":
        return download_single(
            os.path.join(remote_path, relpath),
            os.path.join(local_path, relpath),
            remote_host, remote_user, port, key_path, password, timeout
        )
    return False


# ── 便捷函数 ──

def push(local_path: str, remote_path: str,
         remote_host: str, remote_user: str,
         port: int = 22, method: str = "scp",
         exclude: List[str] = None, key_path: str = None,
         password: str = None, dry_run: bool = False,
         timeout: int = 300) -> dict:
    """推送本地文件到远程。"""
    files = collect_files(local_path, exclude)
    if not files:
        return {"status": "ok", "files_transferred": 0, "bytes": 0, "message": "没有需要传输的文件"}

    if dry_run:
        return {"status": "ok", "files_transferred": 0, "dry_run": True,
                "files": files[:50], "total_files": len(files)}

    if method == "tar+ssh":
        return _push_tar_ssh(local_path, remote_path, remote_host, remote_user,
                             port, key_path, password, exclude, timeout)
    else:
        return _push_scp(local_path, remote_path, remote_host, remote_user,
                         port, key_path, password, files, timeout)


def pull(remote_path: str, local_path: str,
         remote_host: str, remote_user: str,
         port: int = 22, method: str = "scp",
         exclude: List[str] = None, key_path: str = None,
         password: str = None, dry_run: bool = False,
         timeout: int = 300) -> dict:
    """从远程拉取文件到本地。"""
    os.makedirs(local_path, exist_ok=True)

    if dry_run:
        return {"status": "ok", "files_transferred": 0, "dry_run": True,
                "message": "预览模式"}

    if method == "tar+ssh":
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
         delete: bool = False) -> dict:
    """双向同步。"""
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

    if os.path.isfile(local_path):
        scp_cmd.extend([local_path, remote_target])
    else:
        ssh_cmd = ["ssh"] + build_ssh_opts(key_path, port, timeout)
        ssh_cmd.extend([f"{remote_user}@{remote_host}", f"mkdir -p {remote_path}"])
        subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
        scp_cmd.extend([local_path, remote_target])

    try:
        result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return {"status": "error", "message": result.stderr}
        total_bytes = sum(os.path.getsize(f) for f in files if os.path.isfile(f))
        return {"status": "ok", "files_transferred": len(files), "bytes": total_bytes}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"传输超时（{timeout}秒）"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _push_tar_ssh(local_path, remote_path, remote_host, remote_user,
                  port, key_path, password, exclude, timeout):
    """tar+ssh 推送。"""
    remote_target = f"{remote_user}@{remote_host}"
    remote_cmd = f"mkdir -p {remote_path} && tar xzf - -C {remote_path}"
    tar_cmd = ["tar", "czf", "-"]
    for pattern in exclude or []:
        tar_cmd.extend(["--exclude", pattern])
    if os.path.isfile(local_path):
        tar_cmd.extend(["-C", os.path.dirname(local_path), os.path.basename(local_path)])
    else:
        tar_cmd.extend(["-C", local_path, "."])

    try:
        tar_proc = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ssh_cmd = ["ssh"] + build_ssh_opts(key_path, port, timeout) + [remote_target, remote_cmd]
        ssh_proc = subprocess.Popen(ssh_cmd, stdin=tar_proc.stdout,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ssh_proc.communicate(timeout=timeout)
        tar_proc.wait(timeout=10)
        if ssh_proc.returncode != 0:
            return {"status": "error", "message": "ssh 失败"}
        files = collect_files(local_path, exclude)
        total_bytes = sum(os.path.getsize(f) for f in files if os.path.isfile(f))
        return {"status": "ok", "files_transferred": len(files), "bytes": total_bytes}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"传输超时（{timeout}秒）"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _pull_scp(remote_path, local_path, remote_host, remote_user,
              port, key_path, password, timeout):
    """scp 拉取。"""
    remote_target = f"{remote_user}@{remote_host}:{remote_path}"
    scp_cmd = ["scp", "-r"] + build_ssh_opts(key_path, port, timeout)
    scp_cmd.extend([remote_target, local_path])
    try:
        result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=timeout)
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
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"传输超时（{timeout}秒）"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _pull_tar_ssh(remote_path, local_path, remote_host, remote_user,
                  port, key_path, password, exclude, timeout):
    """tar+ssh 拉取。"""
    remote_target = f"{remote_user}@{remote_host}"
    remote_tar_cmd = "tar czf -"
    for pattern in exclude or []:
        remote_tar_cmd += f" --exclude '{pattern}'"
    remote_tar_cmd += f" -C {os.path.dirname(remote_path)} {os.path.basename(remote_path)}"

    try:
        ssh_cmd = ["ssh"] + build_ssh_opts(key_path, port, timeout) + [remote_target, remote_tar_cmd]
        ssh_proc = subprocess.Popen(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tar_cmd = ["tar", "xzf", "-", "-C", local_path]
        tar_proc = subprocess.Popen(tar_cmd, stdin=ssh_proc.stdout,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tar_proc.communicate(timeout=timeout)
        ssh_proc.wait(timeout=10)
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
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"传输超时（{timeout}秒）"}
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
    'resolve_conflict',
    'scan_local_files',
    'scan_remote_files',
    'should_exclude',
    'sync',
    'upload_single'
]
