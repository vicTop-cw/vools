"""
测试脚本 - TableViewer 功能验证
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.xl.viewer import TableViewer, show_table


def test_import():
    print("Test 1: Import test")
    from vools.xl.viewer import TableViewer, show_table
    print("  - TableViewer imported successfully")
    print("  - show_table imported successfully")
    print("  PASSED")
    print()


def test_dll_loading():
    print("Test 2: DLL loading test")
    from vools.xl.viewer.viewer import _get_dll
    dll = _get_dll()
    assert dll.dll is not None, "DLL should be loaded"
    assert hasattr(dll.dll, 'TV_CREATE'), "TV_CREATE should exist"
    assert hasattr(dll.dll, 'TV_SET_SHEET_DATA'), "TV_SET_SHEET_DATA should exist"
    assert hasattr(dll.dll, 'TV_SHOW_MODAL'), "TV_SHOW_MODAL should exist"
    assert hasattr(dll.dll, 'TV_CLOSE'), "TV_CLOSE should exist"
    assert hasattr(dll.dll, 'TV_GET_SELECTED'), "TV_GET_SELECTED should exist"
    assert hasattr(dll.dll, 'TV_GET_SELECTED_VALUE'), "TV_GET_SELECTED_VALUE should exist"
    assert hasattr(dll.dll, 'TV_FREE_STRING'), "TV_FREE_STRING should exist"
    print("  - DLL loaded successfully")
    print("  - All required functions present")
    print("  PASSED")
    print()


def test_data_conversion():
    print("Test 3: Data conversion test")
    from vools.xl.viewer.viewer import _convert_2d_list_to_c_array
    
    data = [
        ['Name', 'Age', 'City'],
        ['Alice', '25', 'New York'],
        ['Bob', '30', 'London'],
    ]
    
    c_array, rows, cols, refs = _convert_2d_list_to_c_array(data)
    assert rows == 3, f"Expected 3 rows, got {rows}"
    assert cols == 3, f"Expected 3 cols, got {cols}"
    assert c_array is not None, "c_array should not be None"
    assert len(refs) == 3, f"Expected 3 ref arrays, got {len(refs)}"
    print(f"  - Rows: {rows}")
    print(f"  - Cols: {cols}")
    print("  - Conversion successful")
    print("  PASSED")
    print()


def test_table_viewer_creation():
    print("Test 4: TableViewer creation test (no window show)")
    data = [
        ['Name', 'Age', 'City'],
        ['Alice', '25', 'New York'],
        ['Bob', '30', 'London'],
    ]
    
    viewer = TableViewer(data=data, title="Test Table", has_header=True)
    assert viewer._hWnd is not None and viewer._hWnd != 0, "Window should be created"
    print(f"  - Window handle: {viewer._hWnd}")
    print("  - Window created successfully")
    
    viewer.close()
    print("  - Window closed successfully")
    print("  PASSED")
    print()


def test_show_table_function():
    print("Test 5: show_table function signature test")
    import inspect
    sig = inspect.signature(show_table)
    params = list(sig.parameters.keys())
    assert 'data' in params, "data parameter should exist"
    assert 'title' in params, "title parameter should exist"
    assert 'has_header' in params, "has_header parameter should exist"
    assert 'modal' in params, "modal parameter should exist"
    print(f"  - Parameters: {params}")
    print("  - Function signature correct")
    print("  PASSED")
    print()


def main():
    print("=" * 60)
    print("TableViewer Test Suite")
    print("=" * 60)
    print()
    
    try:
        test_import()
        test_dll_loading()
        test_data_conversion()
        test_table_viewer_creation()
        test_show_table_function()
        
        print("=" * 60)
        print("All tests PASSED!")
        print("=" * 60)
        print()
        print("Note: Visual test (showing actual window) requires manual run.")
        print("Run 'python test_viewer.py --visual' for visual test.")
    except Exception as e:
        print(f"Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    if '--visual' in sys.argv:
        print("Running visual test...")
        data = [
            ['Name', 'Age', 'City'],
            ['Alice', '25', 'New York'],
            ['Bob', '30', 'London'],
            ['Charlie', '35', 'Tokyo'],
        ]
        show_table(data, title="Test Table", has_header=True)
    else:
        main()
