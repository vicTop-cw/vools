"""
32 位 Python 启动器

从父进程接收 JSON-RPC 请求，执行 32 位 DLL 调用，
通过管道返回结果。
"""
import sys
import os
import json
import ctypes

# 设置 DLL 搜索路径
_dll_dir = os.path.join(os.path.dirname(__file__), '..', '_dlls')
os.environ['PATH'] = _dll_dir + os.pathsep + os.environ.get('PATH', '')

def main():
    """主循环: 读取请求、执行、返回结果"""
    while True:
        try:
            # 从 stdin 读取 JSON 请求
            line = sys.stdin.readline()
            if not line:
                break
            
            request = json.loads(line)
            method = request.get('method')
            params = request.get('params', [])
            
            # 执行调用
            result = {'id': request.get('id'), 'result': None, 'error': None}
            
            try:
                if method == 'call_dll':
                    dll_path, func_name, args = params
                    result['result'] = _call_dll(dll_path, func_name, args)
                elif method == 'ping':
                    result['result'] = 'pong'
                else:
                    result['error'] = f'Unknown method: {method}'
            except Exception as e:
                result['error'] = str(e)
            
            # 输出结果
            sys.stdout.write(json.dumps(result) + '\n')
            sys.stdout.flush()
            
        except Exception as e:
            # 输出错误 JSON
            sys.stdout.write(json.dumps({'error': str(e)}) + '\n')
            sys.stdout.flush()

def _call_dll(dll_path, func_name, args):
    """调用 DLL 函数"""
    dll = ctypes.CDLL(dll_path)
    func = getattr(dll, func_name)
    
    # 类型映射和调用
    # ... (根据参数类型调用)
    
    return None  # 返回结果

if __name__ == '__main__':
    main()