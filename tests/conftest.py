"""pytest configuration for vools tests"""
import pytest

@pytest.fixture(autouse=True)
def clear_caches():
    """在每个测试前清理所有缓存"""
    # 清理 sig_cache
    from vools.sig_cache import clear_cache as clear_sig_cache
    clear_sig_cache()
    
    # 清理 overloads 注册表
    from vools.decorators.overloads import _registry, _wrappers_cache
    _registry.clear()
    _wrappers_cache.clear()
    
    yield
    
    # 测试后再次清理
    clear_sig_cache()
    _registry.clear()
    _wrappers_cache.clear()
