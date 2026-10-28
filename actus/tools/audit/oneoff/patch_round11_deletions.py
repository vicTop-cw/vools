# -*- coding: utf-8 -*-
"""第 11 轮 P3 删除（续）：按真实签名删除 + 清理 __all__。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)


def delete_block(path, header, name, prefix_len=1):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding='utf-8').read()
    idx = s.index(header)
    nxt = s.find('\ndef ', idx + len(header))
    if nxt == -1:
        nxt = s.find('\nclass ', idx + len(header))
    if nxt == -1:
        nxt = len(s)
    # 保留头部前面的缩进层级上下文：从函数起点删到下一个顶层定义
    s = s[:idx] + s[nxt + 1:]
    io.open(p, 'w', encoding='utf-8').write(s)
    print('deleted:', name)


def delete_method(path, header, name):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding='utf-8').read()
    idx = s.index(header)
    nxt = s.find('\n    def ', idx + len(header))
    if nxt == -1:
        nxt = len(s)
    s = s[:idx] + s[nxt + 1:]
    io.open(p, 'w', encoding='utf-8').write(s)
    print('deleted:', name)


delete_block('vools/actus/runtimes.py', 'def reset_registry():',
             'runtimes.reset_registry')
delete_block('vools/actus/vault.py', 'def reset_vault_singleton():',
             'vault.reset_vault_singleton')
delete_block('vools/actus/vault2.py', 'def reset_singleton():',
             'vault2.reset_singleton')
delete_block('vools/actus/calllog.py', 'def reset_store() -> None:',
             'calllog.reset_store')
delete_method('vools/actus/sigma.py',
              '    def register_builtin(self, name: str, fn: Callable) -> None:',
              'SigmaEngine.register_builtin')
delete_method('vools/actus/calllog.py', '    def count(self) -> int:',
              'CallLogStore.count')

# 清理 __all__ 中已删符号
for path, names in (
        ('vools/actus/calllog.py', ["'reset_store'"]),
        ('vools/actus/vault.py', ["'reset_vault_singleton'"]),
        ('vools/actus/vault2.py', ["'reset_singleton'"])):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding='utf-8').read()
    for n in names:
        s = s.replace(', ' + n, '').replace(n + ', ', '')
    io.open(p, 'w', encoding='utf-8').write(s)
    print('__all__ cleaned:', path)
print('done')
