"""vools.rhop.actions.jump - 公开动作集：jump.probe / push / pull / sync

跳板机 SFTP 文件传输公开动作（配置驱动地基 Step 2）。

实现策略（对齐 analysis/rhop-PLAN.md 附录 C C2.2「包装 actus jump 或独立实现」）：
- **独立实现**：rhop 作为地基被 vq/sparksql-exe 与 actus 升级依赖，运行时不得反向
  依赖 actus。传输核心移植自 actus/vools/actus/jump.py 已验证逻辑（paramiko 路线，
  2026-10-13 起真机 47.93.7.122:10022 验证的黄金路径），出参形状保持一致：
      push/pull -> {"status": "ok"|"partial"|"error", "files_transferred", "bytes", "transport"}
      sync      -> {"status": "ok"|"partial"|"error", "uploaded", "downloaded", "conflicts", "transport"}
      probe     -> {"status": "ok", "reachable": bool, "detail": str}
- paramiko 为可选依赖（与 SftpChannel 同策略）：缺失时动作返回明确可执行提示，
  不做静默降级。
- 每个动作统一签名 (cfg, payload) -> dict；cfg 内 sftp 配置兼容 FTP_connect 形态
  {host, port, user, password, key_path, dir}（显式参数优先）。
"""

import os
import posixpath
import stat
import time
from typing import Dict, List, Optional

PARAMIKO_HINT = (
    "缺少 paramiko：pip install paramiko；"
    "jump 公开动作的传输层依赖 paramiko 实现真实 SFTP 读写"
)


def _import_paramiko():
    """惰性导入 paramiko，返回 (module, None) 或 (None, 错误文案)。"""
    try:
        import paramiko  # type: ignore
    except ImportError as e:
        return None, "%s（%s）" % (PARAMIKO_HINT, e)
    return paramiko, None


def _patch_paramiko_filename_decoding():
    """把 paramiko 回包解码换成 surrogateescape，幂等（真机非ASCII文件名防崩）。"""
    try:
        from paramiko.message import Message
    except Exception:
        return False
    if getattr(Message.get_text, "_rhop_surrogateescape", False):
        return True

    def get_text(self):
        raw = self.get_string()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", "surrogateescape")

    get_text._rhop_surrogateescape = True
    Message.get_text = get_text
    return True


# ---- 排除规则与本地扫描（对齐 actus jump） ----

def should_exclude(name: str, patterns: Optional[List[str]]) -> bool:
    """检查文件名是否匹配排除规则（文件名精确/glob + 路径任意部分匹配）。"""
    if not patterns:
        return False
    for pattern in patterns:
        if _fnmatch(name, pattern):
            return True
        parts = name.replace("\\", "/").split("/")
        for part in parts:
            if _fnmatch(part, pattern):
                return True
    return False


def _fnmatch(name, pattern):
    try:
        import fnmatch
        return fnmatch.fnmatch(name, pattern)
    except Exception:
        return name == pattern


def collect_files(local_path: str, exclude: Optional[List[str]] = None) -> List[str]:
    """收集要传输的文件列表（对齐 actus jump.collect_files）。"""
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
                files.append(os.path.join(root, fname))
    return files


def scan_local_files(local_path: str, exclude: Optional[List[str]] = None) -> Dict[str, dict]:
    """扫描本地文件，返回 {相对路径: {size, mtime}}（对齐 actus jump.scan_local_files）。"""
    exclude = exclude or []
    files = {}
    if os.path.isfile(local_path):
        if not should_exclude(os.path.basename(local_path), exclude):
            st = os.stat(local_path)
            files[""] = {"size": st.st_size, "mtime": st.st_mtime}
        return files
    for root, dirs, filenames in os.walk(local_path):
        dirs[:] = [d for d in dirs if not should_exclude(d, exclude)]
        for fname in filenames:
            if should_exclude(fname, exclude):
                continue
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, local_path).replace("\\", "/")
            if not _is_safe_relpath(relpath):
                continue
            try:
                st = os.stat(fpath)
                files[relpath] = {"size": st.st_size, "mtime": st.st_mtime}
            except OSError:
                continue
    return files


def _is_safe_relpath(relpath: str) -> bool:
    """拒绝穿越型相对路径（.. / 绝对路径 / 盘符），对齐 actus jump 安全闸。"""
    if not relpath:
        return True
    p = relpath.replace("\\", "/")
    if p.startswith("/"):
        return False
    if len(p) >= 2 and p[1] == ":":
        return False
    return ".." not in p.split("/")


def _remote_join(base: str, relpath: str) -> str:
    """拼远程路径：远端永远是 POSIX 分隔符。"""
    return posixpath.join(base, relpath.replace("\\", "/"))


# ---- paramiko(SFTP) 传输层（对齐 actus jump 已验证实现） ----

def _sftp_connect(remote_host, remote_user, port=22, key_path=None,
                  password=None, timeout=300):
    """建 SFTP 会话，返回 ((client, sftp), None) 或 (None, 错误 dict)。"""
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


def _sftp_close(client, sftp):
    for closer in (sftp, client):
        try:
            closer.close()
        except Exception:
            pass


def _sftp_makedirs(sftp, remote_dir):
    """SFTP 建多级目录（paramiko 只有 mkdir，没有 mkdir -p）。"""
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


SFTP_KIND_FILE = "file"
SFTP_KIND_DIR = "dir"
SFTP_KIND_OTHER = "other"


def _sftp_entry_kind(attr):
    """判定 SFTP 条目类型（含服务端无类型位时的兜底，对齐 actus）。"""
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


def _sftp_walk_put(sftp, local_root, remote_root, exclude, counter, errors):
    """本地目录 -> 远端，逐文件 put。"""
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
    """远端目录 -> 本地，逐文件 get（符号链接/设备文件跳过并计数）。"""
    for attr in sftp.listdir_attr(remote_root):
        name = attr.filename
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

        if stat.S_ISREG(attr.st_mode):
            target = (os.path.join(local_path, posixpath.basename(remote_path))
                      if os.path.isdir(local_path) else local_path)
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            sftp.get(remote_path, target)
            counter["files"] = 1
            counter["bytes"] = int(getattr(attr, "st_size", 0) or 0)
        elif stat.S_ISDIR(attr.st_mode):
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


def scan_remote_files_paramiko(remote_path, remote_host, remote_user,
                               port=22, key_path=None, password=None,
                               exclude=None, timeout=60,
                               inferred_counter=None):
    """paramiko 版远端扫描：SFTP 递归 stat，不在远端跑任何命令。"""
    exclude = exclude or []
    pair, err = _sftp_connect(remote_host, remote_user, port, key_path,
                              password, timeout)
    if err:
        return {"__error__": err["message"]}
    client, sftp = pair

    files = {}
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
    if inferred_counter is not None:
        inferred_counter.append(inferred_count[0])
    return files


def compute_sync_plan(local_files, remote_files, direction="both",
                      strategy="newer", delete=False):
    """计算同步计划（对齐 actus jump.compute_sync_plan）。"""
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
                    conflict.append({"relpath": relpath,
                                     "local": local, "remote": remote})
    return {"upload": upload, "download": download, "conflict": conflict,
            "skip": skip, "delete": to_delete}


def _sync_paramiko(local_path, remote_path, remote_host, remote_user,
                   port=22, direction="both", strategy="newer", exclude=None,
                   key_path=None, password=None, dry_run=False, timeout=600,
                   delete=False):
    """双向同步的 paramiko 实现：一个 SFTP 会话走完全程。"""
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
            rpath = _remote_join(remote_path, relpath) if relpath else remote_path
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
            rpath = _remote_join(remote_path, relpath)
            lpath = os.path.join(local_path, relpath)
            try:
                parent = os.path.dirname(lpath)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                sftp.get(rpath, lpath)
                counter["files"] += 1
                counter["bytes"] += os.path.getsize(lpath)
                downloaded += 1
            except Exception as e:
                errors.append("下载失败 %s: %s" % (relpath, e))

        for relpath in plan["delete"]:
            rpath = _remote_join(remote_path, relpath)
            try:
                sftp.remove(rpath)
            except Exception as e:
                errors.append("删除失败 %s: %s" % (relpath, e))

        for item in plan["conflict"]:
            relpath = item["relpath"]
            local, remote = item["local"], item["remote"]
            take_local = {"newer": local["mtime"] > remote["mtime"],
                          "local": True, "remote": False}.get(strategy, True)
            try:
                if take_local:
                    lpath = os.path.join(local_path, relpath)
                    rpath = _remote_join(remote_path, relpath)
                    _sftp_makedirs(sftp, posixpath.dirname(rpath))
                    sftp.put(lpath, rpath)
                else:
                    rpath = _remote_join(remote_path, relpath)
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
        out["mode_inferred"] = inferred[0]
    return out


# ---- 配置解析 ----

def _sftp_cfg_of(cfg):
    """从动作 cfg 提取 sftp 配置（兼容 FTP_connect 形态）。"""
    if not isinstance(cfg, dict):
        return {}
    sftp = cfg.get("sftp")
    if sftp is None:
        media = cfg.get("media")
        if isinstance(media, dict):
            sftp = media.get("sftp")
    if sftp is None:
        sftp = cfg
    return sftp or {}


def _payload_str(payload, key, default=""):
    if not isinstance(payload, dict):
        return default
    return payload.get(key, default) or default


def _payload_list(payload, key):
    if not isinstance(payload, dict):
        return []
    v = payload.get(key)
    return v if isinstance(v, list) else []


def _payload_bool(payload, key, default=False):
    if not isinstance(payload, dict):
        return default
    return bool(payload.get(key, default))


# ---- 公开动作 ----

def jump_probe(cfg, payload=None):
    """探测 SFTP 跳板机可达性（TCP 端口探测优先，paramiko 可用时真实连接）。"""
    sftp = _sftp_cfg_of(cfg)
    host = sftp.get("host")
    port = int(sftp.get("port", 22) or 22)
    if not host:
        return {"status": "ok", "reachable": False,
                "detail": "缺少 sftp.host 配置（视为不可达）", "transport": "none"}
    paramiko, _ = _import_paramiko()
    try:
        if paramiko is not None:
            pair, err = _sftp_connect(host, sftp.get("user", ""), port,
                                      sftp.get("key_path"), sftp.get("password"),
                                      timeout=int(sftp.get("timeout", 10) or 10))
            if err:
                return {"status": "ok", "reachable": False,
                        "detail": err.get("message", "连接失败"), "transport": "paramiko"}
            client, sftp_conn = pair
            _sftp_close(client, sftp_conn)
            return {"status": "ok", "reachable": True,
                    "detail": "SFTP 连接成功 %s@%s:%s" % (sftp.get("user", ""), host, port),
                    "transport": "paramiko"}
        import socket
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        return {"status": "ok", "reachable": True,
                "detail": "TCP 端口可达 %s:%s" % (host, port), "transport": "tcp"}
    except Exception as e:
        return {"status": "ok", "reachable": False, "detail": str(e)}


def jump_push(cfg, payload=None):
    """推送本地文件/目录到远端（paramiko 优先）。"""
    sftp = _sftp_cfg_of(cfg)
    host = sftp.get("host")
    user = sftp.get("user", "") or sftp.get("username", "")
    if not host:
        return {"status": "error", "message": "缺少 sftp.host 配置"}
    local_path = _payload_str(payload, "local_path", "")
    remote_path = _payload_str(payload, "remote_path", "")
    if not local_path or not remote_path:
        return {"status": "error",
                "message": "payload 需要 local_path 与 remote_path"}
    exclude = _payload_list(payload, "exclude")
    dry_run = _payload_bool(payload, "dry_run")

    files = collect_files(local_path, exclude)
    if not files:
        return {"status": "ok", "files_transferred": 0, "bytes": 0,
                "message": "没有需要传输的文件", "transport": "paramiko"}
    if dry_run:
        return {"status": "ok", "files_transferred": 0, "dry_run": True,
                "files": files[:50], "total_files": len(files),
                "transport": "paramiko"}
    return _push_paramiko(local_path, remote_path, host, user,
                          int(sftp.get("port", 22) or 22),
                          sftp.get("key_path"), sftp.get("password"),
                          exclude, int(sftp.get("timeout", 300) or 300))


def jump_pull(cfg, payload=None):
    """从远端拉取文件/目录到本地（paramiko 优先）。"""
    sftp = _sftp_cfg_of(cfg)
    host = sftp.get("host")
    user = sftp.get("user", "") or sftp.get("username", "")
    if not host:
        return {"status": "error", "message": "缺少 sftp.host 配置"}
    remote_path = _payload_str(payload, "remote_path", "")
    local_path = _payload_str(payload, "local_path", "")
    if not remote_path or not local_path:
        return {"status": "error",
                "message": "payload 需要 remote_path 与 local_path"}
    exclude = _payload_list(payload, "exclude")
    dry_run = _payload_bool(payload, "dry_run")
    if dry_run:
        return {"status": "ok", "files_transferred": 0, "bytes": 0,
                "dry_run": True, "transport": "paramiko", "message": "预览模式"}
    return _pull_paramiko(remote_path, local_path, host, user,
                          int(sftp.get("port", 22) or 22),
                          sftp.get("key_path"), sftp.get("password"),
                          exclude, int(sftp.get("timeout", 300) or 300))


def jump_sync(cfg, payload=None):
    """双向同步（paramiko 优先）。"""
    sftp = _sftp_cfg_of(cfg)
    host = sftp.get("host")
    user = sftp.get("user", "") or sftp.get("username", "")
    if not host:
        return {"status": "error", "message": "缺少 sftp.host 配置"}
    local_path = _payload_str(payload, "local_path", "")
    remote_path = _payload_str(payload, "remote_path", "")
    if not local_path or not remote_path:
        return {"status": "error",
                "message": "payload 需要 local_path 与 remote_path"}
    direction = _payload_str(payload, "direction", "both")
    strategy = _payload_str(payload, "strategy", "newer")
    exclude = _payload_list(payload, "exclude")
    dry_run = _payload_bool(payload, "dry_run")
    delete = _payload_bool(payload, "delete")
    return _sync_paramiko(local_path, remote_path, host, user,
                          int(sftp.get("port", 22) or 22),
                          direction, strategy, exclude,
                          sftp.get("key_path"), sftp.get("password"),
                          dry_run, int(sftp.get("timeout", 600) or 600),
                          delete)


# ---- 注册表 ----

ACTIONS = {
    "jump.probe": jump_probe,
    "jump.push": jump_push,
    "jump.pull": jump_pull,
    "jump.sync": jump_sync,
}
