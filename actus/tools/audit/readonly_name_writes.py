# -*- coding: utf-8 -*-
"""只读命名审计：找出"名字像只读、实际有写副作用"的函数（AST + 调用传递闭包）。

用法:
    python tools/audit/readonly_name_writes.py [--depth 3] [--json out.json]

输出：候选函数 + 直接写符号 + 传递写符号（带调用链），按写严重度排序。
建议在 CI 中作为**告警**运行（不要 fail），让新出现的"名实不符"被看到。

已知局限（第 13/14 轮审计实感）：
  * **kwarg 常量**：看不到 `add_trigger(..., _persist=False)` 这类"传参关闭写"，
    会把 `triggers.load_registry` 误报为写（已人工标注）。
  * **三方库语义**：`subprocess.run` / `Path.unlink` 按名字归类，不区分实际
    参数是否只读；`json.dump(StringIO())` 也会被当写。
  * **动态分派/反射**：`getattr(mod, name)()`、插件注册表调用无法解析。
  * **只覆盖 `vools/actus/`**：`vools/core/` 等下层写操作不会展开。
误报请人工确认后在报告里标注，不要为了"清零"而放宽检测。
"""
import argparse
import ast
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG = os.path.join(ROOT, 'vools', 'actus')
NAME_RE = re.compile(
    r'^(get|list|load|read|query|find|lookup|resolve|inspect|check|status|count|peek|'
    r'fetch|scan|discover|search|summary|stats|describe|preview|validate|verify)_\w*')

WRITE_FUNCS = {
    'open': 'file-open', 'mkstemp': 'tempfile', 'mkdtemp': 'tempfile',
    'NamedTemporaryFile': 'tempfile', 'TemporaryFile': 'tempfile',
    'write_text': 'path-write', 'write_bytes': 'path-write',
    'dump': 'json-dump', 'dump_all': 'yaml-dump',
    'remove': 'os-remove', 'unlink': 'os-remove', 'rmdir': 'os-rmdir',
    'makedirs': 'os-mkdir', 'mkdir': 'os-mkdir', 'rename': 'os-rename',
    'replace': 'os-replace', 'copy': 'shutil', 'copy2': 'shutil',
    'copyfile': 'shutil', 'copytree': 'shutil', 'move': 'shutil',
    'rmtree': 'shutil-rmtree', 'run': 'subprocess', 'call': 'subprocess',
    'check_call': 'subprocess', 'check_output': 'subprocess', 'Popen': 'subprocess',
    'execute': 'sqlite-exec', 'executemany': 'sqlite-exec', 'executescript': 'sqlite',
}
SQL_WRITE = re.compile(r'\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|REPLACE|VACUUM)\b', re.I)


def module_name(path):
    rel = os.path.relpath(path, os.path.join(ROOT, 'vools')).replace(os.sep, '.')
    return rel[:-3] if rel.endswith('.py') else rel


class Fn:
    def __init__(self, module, cls, name, node, path):
        self.module = module
        self.cls = cls
        self.name = name
        self.node = node
        self.path = path
        self.key = (module, cls, name)
        self.qual = '%s.%s' % (module, (cls + '.' if cls else '') + name)
        self.direct = set()
        self.calls = set()

    def __repr__(self):
        return self.qual


def _arg_const(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return ''.join(v.value for v in node.values if isinstance(v, ast.Constant))
    return None


def detect_write(call, ctx_imports):
    """返回 (symbol, detail) 或 None。"""
    func = call.func
    name = None
    qual = None
    if isinstance(func, ast.Name):
        name = func.id
        target = ctx_imports.get(func.id)          # ('module', 'name') 或 ('module', None)
        if target:
            qual = target[1] or func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
        base = func.value
        if isinstance(base, ast.Name):
            target = ctx_imports.get(base.id)
            if target and target[0]:
                qual = target[1] or name
            else:
                qual = '%s.%s' % (base.id, name)
        else:
            qual = name
    if not name:
        return None
    base_name = (qual or name).split('.')[-1]
    if base_name == 'open':
        mode = ''
        for kw in call.keywords:
            if kw.arg == 'mode':
                mode = _arg_const(kw.value) or ''
        if len(call.args) >= 2:
            mode = _arg_const(call.args[1]) or mode
        if any(ch in mode for ch in ('w', 'a', 'x', '+')):
            return ('open(%s)' % mode, call.lineno)
        return None
    if base_name in ('write_text', 'write_bytes'):
        return ('Path.%s' % base_name, call.lineno)
    if base_name in ('dump', 'dump_all'):
        mod = (qual or '').split('.')[0]
        if mod in ('json', 'yaml', 'toml'):
            return ('%s.%s' % (mod, base_name), call.lineno)
        return None
    if base_name in ('execute', 'executemany', 'executescript'):
        sql = None
        if call.args:
            sql = _arg_const(call.args[0])

        if sql and SQL_WRITE.search(sql):
            return ('sqlite.%s[%s]' % (base_name, SQL_WRITE.search(sql).group(1)), call.lineno)
        return None
    module_of = (qual or '').split('.')[0] if qual else ''
    if base_name in WRITE_FUNCS:
        sy = WRITE_FUNCS[base_name]
        if sy == 'subprocess':
            if module_of == 'subprocess':
                return ('subprocess.%s' % base_name, call.lineno)
            return None
        if sy in ('os-remove', 'os-rmdir', 'os-mkdir', 'os-rename', 'os-replace'):
            if module_of == 'os':
                return ('%s.%s' % (module_of, base_name), call.lineno)
            # Path 风格方法（Path.unlink/rmdir/mkdir/replace）单独放行
            if base_name in ('unlink', 'rmdir', 'mkdir'):
                return ('Path.%s' % base_name, call.lineno)
            return None
        if sy.startswith('shutil'):
            if module_of in ('shutil', 'os'):
                return ('%s.%s' % (module_of, base_name), call.lineno)
            return None
        return ('%s(%s)' % (base_name, sy), call.lineno)
    return None


def collect():
    fns = {}
    mods = {}
    for dp, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fn in files:
            if not fn.endswith('.py'):
                continue
            path = os.path.join(dp, fn)
            mod = module_name(path)
            try:
                tree = ast.parse(io.open(path, encoding='utf-8').read())
            except SyntaxError:
                continue
            mods[mod] = (path, tree)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cls = None
                    # 找直接父类：用 parent 映射
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.ClassDef):
                            if node in parent.body:
                                cls = parent.name
                                break
                    fns[(mod, cls, node.name)] = Fn(mod, cls, node.name, node, path)
    return fns, mods


def imports_of(tree, mod):
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                out[a.asname or a.name.split('.')[0]] = (a.name, None)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                parts = mod.split('.')
                base = '.'.join(parts[:len(parts) - node.level] + ([base] if base else []))
            for a in node.names:
                out[a.asname or a.name] = (base, a.name)
    return out


def resolve_callee(fn, call, fns, imports):
    func = call.func
    if isinstance(func, ast.Name):
        name = func.id
        # 同模块顶层 / 同 class
        for cand in ((fn.module, fn.cls, name), (fn.module, None, name)):
            if cand in fns:
                return fns[cand]
        target = imports.get(name)
        if target:
            mod, nm = target
            for cand in ((mod, None, nm),):
                if cand in fns:
                    return fns[cand]
        return None
    if isinstance(func, ast.Attribute):
        attr = func.attr
        base = func.value
        if isinstance(base, ast.Name) and base.id == 'self' and fn.cls:
            cand = (fn.module, fn.cls, attr)
            return fns.get(cand)
        if isinstance(base, ast.Name):
            target = imports.get(base.id)
            if target:
                mod = target[0]
                return fns.get((mod, None, attr)) or fns.get((mod, attr, attr))
        # 形如 a.b.func（模块路径）
        path = []
        node = func
        while isinstance(node, ast.Attribute):
            path.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            path.append(node.id)
            path.reverse()
            for i in range(1, len(path)):
                mod = '.'.join(path[:i])
                cand = (mod, None, '.'.join(path[i:]))
                if cand in fns:
                    return fns[cand]
    return None


def analyze(depth):
    fns, mods = collect()
    imp = {mod: imports_of(tree, mod) for mod, (_p, tree) in mods.items()}
    for key, fn in fns.items():
        for node in ast.walk(fn.node):
            if isinstance(node, ast.Call):
                w = detect_write(node, imp.get(fn.module, {}))
                if w:
                    fn.direct.add(w)
                callee = resolve_callee(fn, node, fns, imp.get(fn.module, {}))
                if callee is not None and callee.key != fn.key:
                    fn.calls.add(callee.key)
    rows = []
    for key, fn in fns.items():
        if not NAME_RE.match(fn.name) or fn.name.startswith('__'):
            continue
        reached = {}          # symbol -> chain
        frontier = [(fn.key, fn.name, 0)]
        seen = {fn.key}
        while frontier:
            cur_key, chain, d = frontier.pop(0)
            cur = fns[cur_key]
            for sym, line in cur.direct:
                reached.setdefault(sym, (chain, line))
            if d >= depth:
                continue
            for callee_key in cur.calls:
                if callee_key in seen:
                    continue
                seen.add(callee_key)
                frontier.append((callee_key, chain + ' -> ' + fns[callee_key].name, d + 1))
        if not reached:
            continue
        rows.append({
            'qual': fn.qual, 'file': os.path.relpath(fn.path, ROOT).replace(os.sep, '/'),
            'line': fn.node.lineno, 'name': fn.name,
            'direct': sorted({s for s, _l in fn.direct}),
            'transitive': {s: {'chain': c, 'at_line': l} for s, (c, l) in reached.items()},
            'has_direct': bool(fn.direct),
        })
    rows.sort(key=lambda r: (not r['has_direct'], r['qual']))
    return rows, fns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--depth', type=int, default=3)
    ap.add_argument('--json', default='')
    args = ap.parse_args()
    rows, _fns = analyze(args.depth)
    print('候选（只读命名且有写）: %d 条（depth=%d）\n' % (len(rows), args.depth))
    for r in rows:
        print('%-70s %s:%d' % (r['qual'], r['file'], r['line']))
        if r['direct']:
            print('  直接写: %s' % ', '.join(r['direct']))
        for sym, info in sorted(r['transitive'].items()):
            if sym in r['direct']:
                continue
            print('  传递写: %-28s <- %s' % (sym, info['chain']))
    if args.json:
        io.open(args.json, 'w', encoding='utf-8').write(
            json.dumps(rows, ensure_ascii=False, indent=2))
        print('\nJSON 写出:', args.json)


if __name__ == '__main__':
    main()
