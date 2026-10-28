# -*- coding: utf-8 -*-
"""第 14 轮：D 类（vault2.get_secret 只读）+ indexer 只读路径 + MCP tools/list 冷启动不落盘。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)


def patch(path, old, new, count=1):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding='utf-8').read()
    assert old in s, '%s 未匹配:\n%s' % (path, old[:300])
    assert s.count(old) >= count, (path, s.count(old))
    s = s.replace(old, new, count)
    io.open(p, 'w', encoding='utf-8').write(s)
    print('patched:', path)


# ═══════ 1) vault2.py：get_secret(read_only) + resolve_vault_refs 透传 + 显式迁移入口 ═══════
patch('vools/actus/vault2.py',
"""    def get_secret(self, token: str, name: str, caller: str = None) -> dict:
        ok, sess = self._verify_token(token)""",
"""    def get_secret(self, token: str, name: str, caller: str = None,
                   read_only: bool = False) -> dict:
        \"\"\"读取解密一个密钥。

        第 14 轮审计修复（D 类「名实不符的只读」）：本函数名字是 get，但此前：
          * 每次读都 `_audit(...)` → **追加 audit.log**（读也写盘）；
          * 读到 legacy 行（`key_salt IS NULL`）会 `UPDATE secrets ...` **懒迁移**，
            等于"读密钥"改了权威数据 —— 只读文件系统上直接失败。
        现在 `read_only=True` 时：**不写 audit.log、不做懒迁移**，返回值里带
        `legacy: true` 让上层自行决定（显式迁移走 `migrate_legacy_rows()` 或写路径）。
        默认 `read_only=False` 完全保持旧行为（审计 + 懒迁移），兼容既有调用方。
        \"\"\"
        ok, sess = self._verify_token(token)""")

# 4 处 audit 调用：read_only 下不写
patch('vools/actus/vault2.py',
"""            if not row:
                self._audit("get", identity_id, sess["machine_id"], target=name,
                           success=False, reason="not_found", caller=caller)
                return {"status": "error", "message": "凭证不存在"}""",
"""            if not row:
                if not read_only:
                    self._audit("get", identity_id, sess["machine_id"], target=name,
                                success=False, reason="not_found", caller=caller)
                return {"status": "error", "message": "凭证不存在"}""")
patch('vools/actus/vault2.py',
"""            if expires and int(time.time()) > expires:
                self._audit("get", identity_id, sess["machine_id"], target=name,
                           success=False, reason="expired", caller=caller)
                return {"status": "error", "message": "凭证已过期"}""",
"""            if expires and int(time.time()) > expires:
                if not read_only:
                    self._audit("get", identity_id, sess["machine_id"], target=name,
                                success=False, reason="expired", caller=caller)
                return {"status": "error", "message": "凭证已过期"}""")
patch('vools/actus/vault2.py',
"""            except Exception as e:
                self._audit("get", identity_id, sess["machine_id"], target=name,
                           success=False, reason=f"decrypt_error: {e}", caller=caller)
                return {"status": "error", "message": "凭证解密失败（密钥错误？）"}""",
"""            except Exception as e:
                if not read_only:
                    self._audit("get", identity_id, sess["machine_id"], target=name,
                                success=False, reason=f"decrypt_error: {e}", caller=caller)
                return {"status": "error", "message": "凭证解密失败（密钥错误？）"}""")
patch('vools/actus/vault2.py',
"""            # 懒迁移：旧格式读取成功后自动升级为行级加密
            if is_legacy:""",
"""            # 懒迁移：旧格式读取成功后自动升级为行级加密。
            # read_only=True 时**绝不迁移**（只把 legacy 标记回给上层，由显式
            # migrate_legacy_rows()/写路径决定）——"读"不能改权威数据。
            if is_legacy and not read_only:""")
patch('vools/actus/vault2.py',
"""            metadata = json.loads(meta_json) if meta_json else {}
            self._audit("get", identity_id, sess["machine_id"], target=name,
                       success=True, caller=caller)
            return {"status": "ok", "name": name, "value": value,
                    "type": stype, "security_level": level,
                    "expires_at": expires, "metadata": metadata}""",
"""            metadata = json.loads(meta_json) if meta_json else {}
            if not read_only:
                self._audit("get", identity_id, sess["machine_id"], target=name,
                            success=True, caller=caller)
            return {"status": "ok", "name": name, "value": value,
                    "type": stype, "security_level": level,
                    "expires_at": expires, "metadata": metadata,
                    # 第 14 轮：读路径不再自动迁移旧行，把标记透出给上层
                    "legacy": bool(is_legacy)}""")

# resolve_vault_refs 透传 read_only
patch('vools/actus/vault2.py',
"""    def resolve_vault_refs(self, token: str, secrets_config: List[dict]) -> dict:""",
"""    def resolve_vault_refs(self, token: str, secrets_config: List[dict],
                           read_only: bool = False) -> dict:""")
patch('vools/actus/vault2.py',
"""            secret_name = key_ref[len("vault://"):]
            result = self.get_secret(token, secret_name, caller="vault.resolve")""",
"""            secret_name = key_ref[len("vault://"):]
            result = self.get_secret(token, secret_name, caller="vault.resolve",
                                     read_only=read_only)""")

# 模块级包装
patch('vools/actus/vault2.py',
"""def get_secret(token: str, name: str, caller: str = None) -> dict:
    return _get_vault2().get_secret(token, name, caller)""",
"""def get_secret(token: str, name: str, caller: str = None,
               read_only: bool = False) -> dict:
    return _get_vault2().get_secret(token, name, caller, read_only=read_only)""")
patch('vools/actus/vault2.py',
"""def resolve_vault_refs(token: str, secrets_config: List[dict]) -> dict:
    return _get_vault2().resolve_vault_refs(token, secrets_config)""",
"""def resolve_vault_refs(token: str, secrets_config: List[dict],
                       read_only: bool = False) -> dict:
    return _get_vault2().resolve_vault_refs(token, secrets_config,
                                            read_only=read_only)""")

# 显式迁移入口（读路径不迁移；迁移只能显式触发）
patch('vools/actus/vault2.py',
"""def anomaly_check(token: str, window_seconds: int = 3600) -> dict:
    return _get_vault2().anomaly_check(token, window_seconds)""",
"""def migrate_legacy_rows(token: str) -> dict:
    \"\"\"**显式**迁移 legacy 行（key_salt 为空）→ 行级加密。

    第 14 轮：读路径（get_secret(read_only=True)）不再顺手迁移；需要迁移时
    由调用方/运维显式触发本函数（或走会把 read_only=False 的写入口）。
    \"\"\"
    return _get_vault2().migrate_legacy_rows(token)


def anomaly_check(token: str, window_seconds: int = 3600) -> dict:
    return _get_vault2().anomaly_check(token, window_seconds)""")

# 方法实现插在 get_secret 之后（set_secret 之前）
patch('vools/actus/vault2.py',
"""    # ── set_secret ──
    def set_secret(self, token: str, name: str, value: str, secret_type: str = "api_key",""",
"""    def migrate_legacy_rows(self, token: str) -> dict:
        \"\"\"显式迁移该身份下的 legacy 行（key_salt 为空 → 行级加密）。

        返回 {'status','checked','migrated','failed'}。
        只在**显式**操作/写路径调用；读路径（read_only=True）绝不自动迁移。
        \"\"\"
        ok, sess = self._verify_token(token)
        if not ok:
            return {"status": "error", "message": "会话无效或已过期，请重新 auth"}
        identity_id = sess["identity_id"]
        with self._db() as conn:
            rows = [r[0] for r in conn.execute(
                "SELECT name FROM secrets WHERE identity_id=? AND key_salt IS NULL",
                (identity_id,)).fetchall()]
        migrated, failed = 0, []
        for name in rows:
            result = self.get_secret(token, name, caller="vault.migrate",
                                     read_only=False)
            if result.get("status") == "ok":
                migrated += 1
            else:
                failed.append({"name": name,
                               "reason": result.get("message")})
        return {"status": "ok", "checked": len(rows),
                "migrated": migrated, "failed": failed}

    # ── set_secret ──
    def set_secret(self, token: str, name: str, value: str, secret_type: str = "api_key",""")

# ═══════ 2) vault.py：resolver 读路径显式 read_only=True ═══════
patch('vools/actus/vault.py',
"""        result = v2.get_secret(token, name, caller='vault.resolver')
    except Exception as exc:  # noqa: BLE001
        return 'unavailable', None, 'v2 读取异常（%s: %s）' % (type(exc).__name__, exc)""",
"""        result = v2.get_secret(token, name, caller='vault.resolver',
                               read_only=True)
    except Exception as exc:  # noqa: BLE001
        return 'unavailable', None, 'v2 读取异常（%s: %s）' % (type(exc).__name__, exc)""")
patch('vools/actus/vault.py',
"""            result = v2.get_secret(token, name, caller='vault.resolver')
        except Exception as exc:  # noqa: BLE001
            return 'unavailable', None, 'v2 读取异常（%s: %s）' % (type(exc).__name__, exc)""",
"""            result = v2.get_secret(token, name, caller='vault.resolver',
                                   read_only=True)
        except Exception as exc:  # noqa: BLE001
            return 'unavailable', None, 'v2 读取异常（%s: %s）' % (type(exc).__name__, exc)""")

# ═══════ 3) indexer.py：写缓存/建索引可控 ═══════
patch('vools/actus/indexer.py',
"""def scan_actions(actions_dir: str = None, validate: bool = True,
                 use_cache: bool = True) -> Dict[str, Action]:""",
"""def scan_actions(actions_dir: str = None, validate: bool = True,
                 use_cache: bool = True, write_cache: bool = True) -> Dict[str, Action]:""")
patch('vools/actus/indexer.py',
"""    # ── 保存 mtime 缓存 ──
    if use_cache and new_mtimes:""",
"""    # ── 保存 mtime 缓存 ──
    # 第 13/14 轮审计：读命令（info/tools/list/executor 解析）也会走这里，
    # write_cache=False 让只读路径不写 _meta/actions.mtimes.json（只读 FS 可用）。
    if use_cache and write_cache and new_mtimes:""")
patch('vools/actus/indexer.py',
"""def build_index(actions_dir: str = None, meta_dir: str = None) -> dict:""",
"""def build_index(actions_dir: str = None, meta_dir: str = None,
                write: bool = True, write_cache: bool = True) -> dict:
    \"\"\"`write=False`：**只在内存构建索引**（不落盘、不写 mtimes 缓存）——
    供只读 RPC（MCP tools/list）冷启动使用；显式命令（registry build/validate）
    仍用默认 write=True 落盘。\"\"\"""")
patch('vools/actus/indexer.py',
"""    meta = meta_dir or _paths_meta_dir()
    actions = scan_actions(actions_dir, validate=False)""",
"""    meta = meta_dir or _paths_meta_dir()
    actions = scan_actions(actions_dir, validate=False,
                           write_cache=write_cache)""")
patch('vools/actus/indexer.py',
"""    if meta_dir or _is_default_target:
        os.makedirs(meta, exist_ok=True)""",
"""    if write and (meta_dir or _is_default_target):
        os.makedirs(meta, exist_ok=True)""")
patch('vools/actus/indexer.py',
"""def load_index(meta_dir: str = None) -> dict:
    \"\"\"读取索引；不存在时先构建。\"\"\"""",
"""def load_index(meta_dir: str = None, build: bool = True) -> dict:
    \"\"\"读取索引；不存在时默认先构建（`build=False` 时**返回空索引、不落盘**）。

    第 13/14 轮审计：`load_index` 被只读入口（MCP tools/list、resolve_target 等）
    调用，索引缺失时 `build_index` 会落盘 `_meta/actions.index.json` +
    `actions.mtimes.json` —— 只读 FS 上直接失败。只读路径应传 `build=False`，
    需要建索引的显式命令仍用默认 `build=True`。
    \"\"\"""")
patch('vools/actus/indexer.py',
"""    path = os.path.join(meta, 'actions.index.json')
    if not os.path.exists(path):
        return build_index(meta_dir=meta)""",
"""    path = os.path.join(meta, 'actions.index.json')
    if not os.path.exists(path):
        if not build:
            return {'actions': {}, 'problems': {}, 'built': False}
        return build_index(meta_dir=meta)""")
patch('vools/actus/indexer.py',
"""def get_action(action_id: str, actions_dir: str = None) -> Action:
    \"\"\"按 id 取动作（实时解析文件，保证最新内容）；不存在抛 action_not_found。\"\"\"
    actions = scan_actions(actions_dir, validate=False)""",
"""def get_action(action_id: str, actions_dir: str = None,
               write_cache: bool = True) -> Action:
    \"\"\"按 id 取动作（实时解析文件，保证最新内容）；不存在抛 action_not_found。

    `write_cache=False`：只读命令（info/preview/run 解析）不写 mtimes 缓存。
    \"\"\"
    actions = scan_actions(actions_dir, validate=False, write_cache=write_cache)""")

# ═══════ 4) mcp_server.py：仅 tools/list 冷启动不落盘 ═══════
patch('vools/actus/mcp_server.py',
"""        tools = []
        if with_dynamic:
            import vools.actus as actuscore
            idx = actuscore.load_index()""",
"""        tools = []
        if with_dynamic:
            import vools.actus as actuscore
            # 第 14 轮审计修复：tools/list 是**只读 RPC**，冷启动（索引缺失）时
            # 旧实现 load_index() 会 build_index 并落盘 actions.index.json /
            # actions.mtimes.json / 审计日志 —— 只读 FS/容器只读挂载直接失败。
            # 现在：先 build=False 读；缺失则在**内存**构建（write=False,
            # write_cache=False），落盘只由显式命令（registry build/validate）触发。
            idx = actuscore.load_index(build=False)
            if not idx.get('actions'):
                from vools.actus.indexer import build_index
                try:
                    idx = build_index(write=False, write_cache=False)
                except Exception:
                    idx = {'actions': {}}""")

print('done')
