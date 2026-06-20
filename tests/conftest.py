"""pytest configuration for vools tests"""
import pytest

@pytest.fixture(autouse=True)
def clear_caches():
    """在每个测试前清理所有缓存"""
    # 清理 cache
    from vools.cache import clear_cache as clear_sig_cache
    clear_sig_cache()
    
    # 清理 overloads 注册表
    from vools.decorators.overload import reset_registry
    reset_registry()
    
    yield
    
    # 测试后再次清理
    clear_sig_cache()
    reset_registry()
