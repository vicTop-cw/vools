# -*- coding: utf-8 -*-
"""Wrapper: 运行 plan_audit_actus.py 并捕获完整 traceback 到文件。"""
import os
import sys
import traceback

LOG = os.path.join(os.environ.get('TEMP', '.'), 'audit_actus_full.txt')

def main():
    os.chdir(r'E:\IDEProjects\AI\vools\actus')
    sys.path.insert(0, r'E:\IDEProjects\AI\vools')
    sys.path.insert(0, r'E:\IDEProjects\AI\vools\actus')
    sys.argv = ['plan_audit_actus.py']
    try:
        import runpy
        runpy.run_path(r'E:\IDEProjects\AI\vools\actus\tools\audit\plan_audit_actus.py',
                       run_name='__main__')
        rc = 0
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 0
    except BaseException:
        with open(LOG, 'w', encoding='utf-8') as f:
            f.write(traceback.format_exc())
        rc = 2
    else:
        with open(LOG, 'w', encoding='utf-8') as f:
            f.write('OK_NO_EXCEPTION')
    return rc

if __name__ == '__main__':
    sys.exit(main())
