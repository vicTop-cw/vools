"""
vools 性能基准测试套件
"""

from .hash_suite import HashSuite, run_hash_benchmarks, get_hash_suite
from .serialize_suite import get_serialize_suite
from .base64_suite import get_base64_suite
from .json_suite import get_json_suite
from .env_suite import get_env_suite, EnvSuite
from .compress_suite import get_compress_suite
from .sigcache_suite import get_sigcache_suite

__all__ = [
    'HashSuite',
    'run_hash_benchmarks',
    'get_hash_suite',
    'get_serialize_suite',
    'get_base64_suite',
    'get_json_suite',
    'get_env_suite',
    'EnvSuite',
    'get_compress_suite',
    'get_sigcache_suite',
]


def get_all_suites():
    """获取所有基准测试套件"""
    suites = {}
    for name in ['serialize', 'base64', 'json', 'env', 'compress', 'sigcache']:
        getter = globals().get(f'get_{name}_suite')
        if getter:
            suites[name] = getter()
    return suites
