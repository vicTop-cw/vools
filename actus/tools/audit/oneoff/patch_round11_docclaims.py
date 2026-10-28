# -*- coding: utf-8 -*-
"""第 11 轮：清除"文档/docstring 声称有 CLI 入口但实际没有"的同类（README 除外，上报）。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)


def patch(path, old, new):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding='utf-8').read()
    assert old in s, '%s 未匹配: %r' % (path, old[:120])
    s = s.replace(old, new, 1)
    io.open(p, 'w', encoding='utf-8').write(s)
    print('patched:', path)


patch('vools/actus/repo.py',
      '"""建仓（docs/41 §D4 `actus repo create`）。',
      '"""建仓（docs/41 §D4；**库内 API `create_repo`** —— CLI 当前没有 `actus repo` 子命令，\n    旧的 ``actus repo create`` 提法不成立，第 11 轮文档审计修正）。')

patch('vools/actus/visibility.py',
      '已安装方必须重新 `actus install --key`/`actus update` 拿新钥续期。',
      '已安装方必须重新 `actus install --key`（或 `actus sync`）拿新钥续期。')

patch('vools/actus/health.py',
      '"运行 `actus init` 初始化项目"',
      '"运行任意 actus 命令会自动创建 _meta，也可手动 mkdir -p _meta"')

patch('vools/actus/cli.py',
      '`actus exec` 同一条路径，不另造执行器',
      '`actus execute` 同一条路径，不另造执行器')

patch('vools/actus/exec_iface.py',
      '（docs/41 §C2 的 actus check 语义）',
      '（docs/41 §C2 的"只校验不执行"语义；CLI 入口是 `actus validate`，'
      '旧文档里的 `actus check` 子命令不存在）')

patch('vools/actus/scattered.py',
      '只校验不执行（docs/41 §C2 的 `actus check`）。返回结构化报告；',
      '只校验不执行（docs/41 §C2；CLI 入口是 `actus validate` —— 旧文档里的\n    `actus check` 子命令不存在）。返回结构化报告；')

patch('vools/actus/validate.py',
      '列出来供 `actus check` 展示，不作为 errors 计数。',
      '列出来供 `actus validate` 展示，不作为 errors 计数。')
print('done')
