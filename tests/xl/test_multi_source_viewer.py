"""测试表格查看器多数据源支持（不创建窗口）"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_imports():
    """测试导入"""
    print("=" * 60)
    print("测试1: 导入测试")
    print("=" * 60)

    try:
        from vools.xl import show_table
        print(f"✓ from vools.xl import show_table 成功")
    except ImportError as e:
        print(f"✗ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    try:
        from vools.xl import TableViewer
        print(f"✓ from vools.xl import TableViewer 成功")
    except ImportError as e:
        print(f"✗ 导入失败: {e}")
        return False

    print()
    return True


def test_helper_functions():
    """测试辅助函数"""
    print("=" * 60)
    print("测试2: 辅助函数导入和类型检测")
    print("=" * 60)

    try:
        from vools.xl.viewer.viewer import (
            sheet_to_2d_list,
            book_to_sheets_data,
            dataframe_to_2d_list,
            _normalize_data,
            _is_sheet_obj,
            _is_book_obj,
            _is_dataframe,
            _pandas_available,
        )
        print(f"✓ 辅助函数导入成功")
        print(f"  pandas available: {_pandas_available}")
    except ImportError as e:
        print(f"✗ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    try:
        from vools.xl import Book

        with Book() as book:
            sheet = book.add_sheet("TestSheet")
            sheet.write_str(1, 0, "Name")
            sheet.write_str(1, 1, "Age")
            sheet.write_str(2, 0, "Alice")
            sheet.write_num(2, 1, 25)
            sheet.write_str(3, 0, "Bob")
            sheet.write_num(3, 1, 30)

            print(f"✓ _is_sheet_obj(sheet) = {_is_sheet_obj(sheet)}")
            print(f"✓ _is_book_obj(book) = {_is_book_obj(book)}")
            print(f"✓ _is_dataframe([]) = {_is_dataframe([])}")

            data = sheet_to_2d_list(sheet)
            print(f"✓ sheet_to_2d_list 转换成功，行数: {len(data)}")
            if data:
                print(f"  第1行: {data[0]}")
                if len(data) > 1:
                    print(f"  第2行: {data[1]}")

            sheet2 = book.add_sheet("Sheet2")
            sheet2.write_str(1, 0, "Product")
            sheet2.write_str(2, 0, "Apple")

            sheets_data, sheet_names = book_to_sheets_data(book)
            print(f"✓ book_to_sheets_data 转换成功")
            print(f"  工作表数量: {len(sheets_data)}")
            print(f"  工作表名称: {sheet_names}")

            sheets_data2, names2 = book_to_sheets_data(book, sheet_names=["TestSheet"])
            print(f"✓ book_to_sheets_data 过滤成功")
            print(f"  过滤后数量: {len(sheets_data2)}, 名称: {names2}")

            print(f"\n✓ Sheet.show() 方法存在: {hasattr(sheet, 'show')}")
            print(f"✓ Book.show() 方法存在: {hasattr(book, 'show')}")

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()
    return True


def test_normalize_data():
    """测试 _normalize_data 函数"""
    print("=" * 60)
    print("测试3: _normalize_data 类型识别")
    print("=" * 60)

    try:
        from vools.xl.viewer.viewer import _normalize_data, _pandas_available
        from vools.xl import Book

        list_data = [
            ['Name', 'Age', 'City'],
            ['Alice', 25, 'New York'],
            ['Bob', 30, 'Los Angeles'],
        ]

        norm_list = _normalize_data(list_data)
        print(f"✓ 二维列表识别: {norm_list['type']}")
        print(f"  数据行数: {len(norm_list['data'])}")

        with Book() as book:
            sheet = book.add_sheet("TestSheet")
            sheet.write_str(1, 0, "Name")
            sheet.write_str(2, 0, "Alice")

            norm_sheet = _normalize_data(sheet)
            print(f"✓ Sheet 对象识别: {norm_sheet['type']}")
            print(f"  sheet name: {norm_sheet['name']}")

            sheet2 = book.add_sheet("Sheet2")
            sheet2.write_str(1, 0, "Product")

            norm_book = _normalize_data(book)
            print(f"✓ Book 对象识别: {norm_book['type']}")
            print(f"  工作表数量: {len(norm_book['sheets'])}")
            print(f"  工作表名称: {norm_book['names']}")

        if _pandas_available:
            import pandas as pd
            df = pd.DataFrame({'A': [1, 2], 'B': [3, 4]})
            norm_df = _normalize_data(df)
            print(f"✓ DataFrame 识别: {norm_df['type']}")
            print(f"  数据行数: {len(norm_df['data'])}")

        try:
            _normalize_data(123)
            print("✗ 应该对不支持的类型抛出 TypeError")
            return False
        except TypeError as e:
            print(f"✓ 不支持类型正确抛出 TypeError")

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()
    return True


def test_dataframe_conversion():
    """测试 DataFrame 转换"""
    print("=" * 60)
    print("测试4: DataFrame 转换")
    print("=" * 60)

    try:
        from vools.xl.viewer.viewer import _pandas_available, dataframe_to_2d_list

        if not _pandas_available:
            print("⚠ pandas 不可用，跳过 DataFrame 转换测试")
            print()
            return True

        import pandas as pd

        df = pd.DataFrame({
            'Name': ['Alice', 'Bob', 'Charlie'],
            'Age': [25, 30, 35],
            'City': ['New York', 'Los Angeles', 'Chicago']
        })

        print(f"✓ 创建 DataFrame 成功，形状: {df.shape}")

        data = dataframe_to_2d_list(df)
        print(f"✓ dataframe_to_2d_list 转换成功")
        print(f"  表头: {data[0]}")
        print(f"  数据行数: {len(data) - 1}")
        print(f"  第1行数据: {data[1]}")

        data_with_index = dataframe_to_2d_list(df, show_index=True)
        print(f"✓ dataframe_to_2d_list(show_index=True) 成功")
        print(f"  带索引表头: {data_with_index[0]}")

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()
    return True


def test_show_method_signature():
    """测试 show 方法签名"""
    print("=" * 60)
    print("测试5: show() 方法签名检查")
    print("=" * 60)

    try:
        import inspect
        from vools.xl import Book

        with Book() as book:
            sheet = book.add_sheet("Test")

            sheet_sig = inspect.signature(sheet.show)
            print(f"✓ Sheet.show() 参数: {list(sheet_sig.parameters.keys())}")

            book_sig = inspect.signature(book.show)
            print(f"✓ Book.show() 参数: {list(book_sig.parameters.keys())}")

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    print()
    return True


def main():
    print("\n" + "=" * 60)
    print("表格查看器多数据源支持 - 测试套件")
    print("=" * 60 + "\n")

    results = []

    results.append(("导入测试", test_imports()))
    results.append(("辅助函数与类型检测", test_helper_functions()))
    results.append(("_normalize_data 类型识别", test_normalize_data()))
    results.append(("DataFrame 转换", test_dataframe_conversion()))
    results.append(("show 方法签名", test_show_method_signature()))

    print("=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = 0
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {status} - {name}")
        if result:
            passed += 1

    print(f"\n总计: {passed}/{total} 通过")

    return passed == total


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
