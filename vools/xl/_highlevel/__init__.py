"""高级便捷函数"""
from .utils import (
    read_excel,
    write_excel,
    read_excel_rows,
    write_excel_rows,
    read_excel_matrix,
    write_excel_matrix,
)

# 引擎适配层
from .engines import (
    BaseEngine,
    VoolsEngine,
    PandasEngine,
    register_engine,
    get_engine,
    list_engines,
)

# pandas 接口（可选）
try:
    from .pandas_io import (
        read_excel_df,
        write_excel_df,
    )
    __all__ = [
        'read_excel',
        'write_excel',
        'read_excel_rows',
        'write_excel_rows',
        'read_excel_matrix',
        'write_excel_matrix',
        'BaseEngine',
        'VoolsEngine',
        'PandasEngine',
        'register_engine',
        'get_engine',
        'list_engines',
        'read_excel_df',
        'write_excel_df',
    ]
except ImportError:
    __all__ = [
        'read_excel',
        'write_excel',
        'read_excel_rows',
        'write_excel_rows',
        'read_excel_matrix',
        'write_excel_matrix',
        'BaseEngine',
        'VoolsEngine',
        'PandasEngine',
        'register_engine',
        'get_engine',
        'list_engines',
    ]
