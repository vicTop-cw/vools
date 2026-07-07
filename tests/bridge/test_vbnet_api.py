"""
测试 vools.bridge.vbnet.api 模块

测试内容：
- 模块导入测试（不依赖 API.dll 是否安装）
- is_api_available() 函数测试
- APIBridgeError 异常类测试
- _COMObjectCache 基本逻辑测试（使用 mock）
- _BaseModule 基本逻辑测试（使用 mock）
- 各模块类导入测试

注意：不实际调用真实的 COM 方法，避免影响测试环境。
"""

import pytest
import sys
import os
import platform
class TestModuleImport:
    """测试模块导入"""

    def test_import_api_module(self):
        """测试导入 api 模块"""
        from vools.bridge.vbnet import api
        assert api is not None

    def test_import_all_symbols(self):
        """测试 __all__ 中所有符号都能导入"""
        from vools.bridge.vbnet.api import __all__
        from vools.bridge.vbnet import api

        for name in __all__:
            assert hasattr(api, name), f"api 模块缺少 {name}"

    def test_import_base_module(self):
        """测试导入 _base 模块"""
        from vools.bridge.vbnet.api import _base
        assert _base is not None
        assert hasattr(_base, 'APIBridgeError')
        assert hasattr(_base, '_COMObjectCache')
        assert hasattr(_base, '_BaseModule')
        assert hasattr(_base, 'is_api_available')

    def test_import_window_module(self):
        """测试导入 window 模块"""
        from vools.bridge.vbnet.api import window
        assert window is not None
        assert hasattr(window, 'WindowModule')
        assert hasattr(window, 'Window')

    def test_import_mouse_module(self):
        """测试导入 mouse 模块"""
        from vools.bridge.vbnet.api import mouse
        assert mouse is not None
        assert hasattr(mouse, 'MouseModule')
        assert hasattr(mouse, 'Mouse')

    def test_import_keyboard_module(self):
        """测试导入 keyboard 模块"""
        from vools.bridge.vbnet.api import keyboard
        assert keyboard is not None
        assert hasattr(keyboard, 'KeyboardModule')
        assert hasattr(keyboard, 'Keyboard')

    def test_import_image_module(self):
        """测试导入 image 模块"""
        from vools.bridge.vbnet.api import image
        assert image is not None
        assert hasattr(image, 'ImageModule')
        assert hasattr(image, 'Image')

    def test_import_filesystem_module(self):
        """测试导入 filesystem 模块"""
        from vools.bridge.vbnet.api import filesystem
        assert filesystem is not None
        assert hasattr(filesystem, 'FileSystemModule')
        assert hasattr(filesystem, 'FileSystem')

    def test_import_process_module(self):
        """测试导入 process 模块"""
        from vools.bridge.vbnet.api import process
        assert process is not None
        assert hasattr(process, 'ProcessModule')
        assert hasattr(process, 'Process')

    def test_import_network_module(self):
        """测试导入 network 模块"""
        from vools.bridge.vbnet.api import network
        assert network is not None
        assert hasattr(network, 'NetworkModule')
        assert hasattr(network, 'Network')


class TestAPIBridgeError:
    """测试 APIBridgeError 异常类"""

    def test_exception_inheritance(self):
        """测试异常继承关系"""
        from vools.bridge.vbnet.api import APIBridgeError
        assert issubclass(APIBridgeError, Exception)

    def test_exception_with_message(self):
        """测试带消息的异常"""
        from vools.bridge.vbnet.api import APIBridgeError

        err = APIBridgeError("测试错误")
        assert str(err) == "测试错误"
        assert err.cause is None

    def test_exception_with_cause(self):
        """测试带原因的异常"""
        from vools.bridge.vbnet.api import APIBridgeError

        cause = ValueError("原始错误")
        err = APIBridgeError("包装错误", cause=cause)
        assert err.cause is cause
        assert "测试" in str(err) or "包装" in str(err)
        assert "原因" in str(err)

    def test_exception_raise_and_catch(self):
        """测试异常抛出和捕获"""
        from vools.bridge.vbnet.api import APIBridgeError

        with pytest.raises(APIBridgeError) as exc_info:
            raise APIBridgeError("测试抛出")
        assert "测试抛出" in str(exc_info.value)


class TestIsAPIAvailable:
    """测试 is_api_available 函数"""

    def test_returns_bool(self):
        """测试返回值类型为 bool"""
        from vools.bridge.vbnet.api import is_api_available
        result = is_api_available()
        assert isinstance(result, bool)

    def test_non_windows_returns_false(self):
        """非 Windows 平台应返回 False"""
        if platform.system() != 'Windows':
            from vools.bridge.vbnet.api import is_api_available
            assert is_api_available() is False

    def test_does_not_raise(self):
        """测试函数不会抛出异常"""
        from vools.bridge.vbnet.api import is_api_available
        try:
            result = is_api_available()
            assert isinstance(result, bool)
        except Exception as e:
            pytest.fail(f"is_api_available() 不应抛出异常: {e}")


class TestCOMObjectCache:
    """测试 _COMObjectCache 类"""

    def test_create_instance(self):
        """测试创建缓存实例"""
        from vools.bridge.vbnet.api._base import _COMObjectCache
        cache = _COMObjectCache()
        assert cache is not None
        assert cache._cache == {}
        assert cache._failed == {}

    def test_supported_progids(self):
        """测试支持的 ProgID 列表"""
        from vools.bridge.vbnet.api._base import _COMObjectCache
        cache = _COMObjectCache()
        progids = cache.supported_progids
        assert isinstance(progids, tuple)
        assert len(progids) == 7
        assert "API.Window" in progids
        assert "API.Mouse" in progids
        assert "API.Keyboard" in progids
        assert "API.Image" in progids
        assert "API.FileSystem" in progids
        assert "API.Process" in progids
        assert "API.Network" in progids

    def test_has_on_empty_cache(self):
        """测试空缓存的 has 方法"""
        from vools.bridge.vbnet.api._base import _COMObjectCache
        cache = _COMObjectCache()
        assert cache.has("API.Window") is False

    def test_clear_all(self):
        """测试清除全部缓存"""
        from vools.bridge.vbnet.api._base import _COMObjectCache
        cache = _COMObjectCache()
        cache._cache["API.Window"] = "fake_obj"
        cache._failed["API.Mouse"] = Exception("fake")
        cache.clear()
        assert len(cache._cache) == 0
        assert len(cache._failed) == 0

    def test_clear_specific(self):
        """测试清除指定缓存"""
        from vools.bridge.vbnet.api._base import _COMObjectCache
        cache = _COMObjectCache()
        cache._cache["API.Window"] = "fake_obj"
        cache._cache["API.Mouse"] = "fake_obj2"
        cache._failed["API.Keyboard"] = Exception("fake")
        cache.clear("API.Window")
        assert "API.Window" not in cache._cache
        assert "API.Mouse" in cache._cache
        assert "API.Keyboard" in cache._failed

    def test_get_with_mock(self):
        """测试 get 方法（使用 mock）"""
        from unittest.mock import patch, MagicMock
        from vools.bridge.vbnet.api import _base
        from vools.bridge.vbnet.api._base import _COMObjectCache

        cache = _COMObjectCache()
        fake_obj = MagicMock()

        mock_client = MagicMock()
        mock_client.Dispatch.return_value = fake_obj

        with patch.object(_base, '_get_win32com_client', return_value=mock_client):
            obj = cache.get("API.Window")
            assert obj is fake_obj
            assert cache.has("API.Window") is True

            obj2 = cache.get("API.Window")
            assert obj2 is fake_obj
            assert mock_client.Dispatch.call_count == 1

    def test_get_failure_cached(self):
        """测试失败缓存"""
        from unittest.mock import patch, MagicMock
        from vools.bridge.vbnet.api import _base
        from vools.bridge.vbnet.api._base import _COMObjectCache, APIBridgeError

        cache = _COMObjectCache()

        mock_client = MagicMock()
        mock_client.Dispatch.side_effect = Exception("创建失败")

        with patch.object(_base, '_get_win32com_client', return_value=mock_client):
            with pytest.raises(APIBridgeError):
                cache.get("API.Window")

            assert "API.Window" in cache._failed

            with pytest.raises(APIBridgeError) as exc_info:
                cache.get("API.Window")
            assert "之前创建失败" in str(exc_info.value)


class TestBaseModule:
    """测试 _BaseModule 基类"""

    def test_create_instance(self):
        """测试创建基类实例"""
        from vools.bridge.vbnet.api._base import _BaseModule
        module = _BaseModule()
        assert module is not None
        assert module._com_obj is None
        assert module._prog_id == ""

    def test_call_bool_with_none(self):
        """测试 _call_bool 处理 None 返回值"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_com_obj.TestMethod.return_value = None

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_bool("TestMethod")
            assert result is False

    def test_call_bool_with_true(self):
        """测试 _call_bool 处理 True 返回值"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_com_obj.TestMethod.return_value = True

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_bool("TestMethod")
            assert result is True

    def test_call_int_with_none(self):
        """测试 _call_int 处理 None 返回值"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_com_obj.TestMethod.return_value = None

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_int("TestMethod")
            assert result == 0

    def test_call_int_with_value(self):
        """测试 _call_int 处理整数返回值"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_com_obj.TestMethod.return_value = 42

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_int("TestMethod")
            assert result == 42

    def test_call_str_with_none(self):
        """测试 _call_str 处理 None 返回值"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_com_obj.TestMethod.return_value = None

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_str("TestMethod")
            assert result == ""

    def test_call_str_with_value(self):
        """测试 _call_str 处理字符串返回值"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_com_obj.TestMethod.return_value = "hello"

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_str("TestMethod")
            assert result == "hello"

    def test_call_rect_with_object_properties(self):
        """测试 _call_rect 处理带属性的对象"""
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_rect = SimpleNamespace(Left=10, Top=20, Right=100, Bottom=200)
        fake_com_obj = MagicMock()
        fake_com_obj.GetRect.return_value = fake_rect

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_rect("GetRect")
            assert result == (10, 20, 100, 200)

    def test_call_rect_with_list(self):
        """测试 _call_rect 处理列表格式"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_com_obj.GetRect.return_value = [10, 20, 100, 200]

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_rect("GetRect")
            assert result == (10, 20, 100, 200)

    def test_call_rect_with_none(self):
        """测试 _call_rect 处理 None 返回值"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_com_obj.GetRect.return_value = None

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_rect("GetRect")
            assert result == (0, 0, 0, 0)

    def test_call_list_with_iterable(self):
        """测试 _call_list 处理可迭代对象"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_com_obj.GetItems.return_value = [1, 2, 3]

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_list("GetItems")
            assert result == [1, 2, 3]

    def test_call_list_with_none(self):
        """测试 _call_list 处理 None 返回值"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_com_obj.GetItems.return_value = None

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_list("GetItems")
            assert result == []

    def test_call_list_with_single_object(self):
        """测试 _call_list 处理单个对象"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_obj = object()
        fake_com_obj.GetItems.return_value = fake_obj

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            result = module._call_list("GetItems")
            assert result == [fake_obj]

    def test_call_exception_wrapping(self):
        """测试 _call 异常包装"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache, APIBridgeError

        module = _BaseModule()
        module._prog_id = "API.Test"

        fake_com_obj = MagicMock()
        fake_com_obj.BadMethod.side_effect = Exception("COM 错误")

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            with pytest.raises(APIBridgeError) as exc_info:
                module._call("BadMethod")
            assert "BadMethod" in str(exc_info.value)
            assert "API.Test" in str(exc_info.value)

    def test_call_preserves_abriderror(self):
        """测试 _call 不重复包装 APIBridgeError"""
        from unittest.mock import MagicMock, patch
        from vools.bridge.vbnet.api._base import _BaseModule, _com_object_cache, APIBridgeError

        module = _BaseModule()
        module._prog_id = "API.Test"

        original_error = APIBridgeError("原始错误")
        fake_com_obj = MagicMock()
        fake_com_obj.Method.side_effect = original_error

        with patch.object(_com_object_cache, 'get', return_value=fake_com_obj):
            with pytest.raises(APIBridgeError) as exc_info:
                module._call("Method")
            assert exc_info.value is original_error


class TestWindowModule:
    """测试 WindowModule 类"""

    def test_prog_id(self):
        """测试 ProgID 设置"""
        from vools.bridge.vbnet.api.window import WindowModule
        assert WindowModule._prog_id == "API.Window"

    def test_singleton_instance(self):
        """测试单例实例"""
        from vools.bridge.vbnet.api.window import Window, WindowModule
        assert isinstance(Window, WindowModule)

    def test_methods_exist(self):
        """测试主要方法存在"""
        from vools.bridge.vbnet.api.window import WindowModule
        methods = [
            'FindWindow', 'FindWindowEx', 'GetWindowText', 'SetWindowText',
            'GetWindowRect', 'GetClientRect', 'MoveWindow', 'ShowWindow',
            'CloseWindow', 'EnableWindow', 'IsWindowExists', 'GetClassName',
            'GetParent', 'SetParent', 'GetForegroundWindow', 'SetForegroundWindow',
            'GetDesktopWindow', 'GetWindowProcessId', 'BringWindowToTop'
        ]
        for method in methods:
            assert hasattr(WindowModule, method), f"WindowModule 缺少方法: {method}"


class TestMouseModule:
    """测试 MouseModule 类"""

    def test_prog_id(self):
        """测试 ProgID 设置"""
        from vools.bridge.vbnet.api.mouse import MouseModule
        assert MouseModule._prog_id == "API.Mouse"

    def test_singleton_instance(self):
        """测试单例实例"""
        from vools.bridge.vbnet.api.mouse import Mouse, MouseModule
        assert isinstance(Mouse, MouseModule)

    def test_methods_exist(self):
        """测试主要方法存在"""
        from vools.bridge.vbnet.api.mouse import MouseModule
        methods = [
            'MouseMove', 'LeftDown', 'LeftUp', 'LeftClick',
            'RightDown', 'RightUp', 'RightClick', 'MiddleDown',
            'MiddleUp', 'MiddleClick', 'DoubleClick', 'MouseWheel'
        ]
        for method in methods:
            assert hasattr(MouseModule, method), f"MouseModule 缺少方法: {method}"


class TestKeyboardModule:
    """测试 KeyboardModule 类"""

    def test_prog_id(self):
        """测试 ProgID 设置"""
        from vools.bridge.vbnet.api.keyboard import KeyboardModule
        assert KeyboardModule._prog_id == "API.Keyboard"

    def test_singleton_instance(self):
        """测试单例实例"""
        from vools.bridge.vbnet.api.keyboard import Keyboard, KeyboardModule
        assert isinstance(Keyboard, KeyboardModule)

    def test_methods_exist(self):
        """测试主要方法存在"""
        from vools.bridge.vbnet.api.keyboard import KeyboardModule
        methods = [
            'SendKeys', 'KeyDown', 'KeyUp', 'KeyDownUp',
            'GetKeyPressed', 'GetKeyOpened', 'AltKeyPressed',
            'CtrlKeyPressed', 'ShiftKeyPressed', 'CapsLockOpened',
            'NumLockOpened', 'ScrollLockOpened'
        ]
        for method in methods:
            assert hasattr(KeyboardModule, method), f"KeyboardModule 缺少方法: {method}"


class TestImageModule:
    """测试 ImageModule 类"""

    def test_prog_id(self):
        """测试 ProgID 设置"""
        from vools.bridge.vbnet.api.image import ImageModule
        assert ImageModule._prog_id == "API.Image"

    def test_singleton_instance(self):
        """测试单例实例"""
        from vools.bridge.vbnet.api.image import Image, ImageModule
        assert isinstance(Image, ImageModule)

    def test_methods_exist(self):
        """测试主要方法存在"""
        from vools.bridge.vbnet.api.image import ImageModule
        methods = [
            'ScreenCapture', 'CaptureFullScreen', 'OpenImage', 'SaveImage',
            'GetPixelColor', 'SetPixelColor', 'ChangeSize', 'CropImage',
            'RotateFlip', 'CreateNewBitmap'
        ]
        for method in methods:
            assert hasattr(ImageModule, method), f"ImageModule 缺少方法: {method}"


class TestFileSystemModule:
    """测试 FileSystemModule 类"""

    def test_prog_id(self):
        """测试 ProgID 设置"""
        from vools.bridge.vbnet.api.filesystem import FileSystemModule
        assert FileSystemModule._prog_id == "API.FileSystem"

    def test_singleton_instance(self):
        """测试单例实例"""
        from vools.bridge.vbnet.api.filesystem import FileSystem, FileSystemModule
        assert isinstance(FileSystem, FileSystemModule)

    def test_methods_exist(self):
        """测试主要方法存在"""
        from vools.bridge.vbnet.api.filesystem import FileSystemModule
        methods = [
            'CreateDirectory', 'DeleteDirectory', 'DeleteFile',
            'ReadAllText', 'WriteAllText', 'CombinePath',
            'DirectoryExists', 'FileExists', 'GetParentPath',
            'CopyFile', 'MoveFile', 'RenameFile'
        ]
        for method in methods:
            assert hasattr(FileSystemModule, method), f"FileSystemModule 缺少方法: {method}"


class TestProcessModule:
    """测试 ProcessModule 类"""

    def test_prog_id(self):
        """测试 ProgID 设置"""
        from vools.bridge.vbnet.api.process import ProcessModule
        assert ProcessModule._prog_id == "API.Process"

    def test_singleton_instance(self):
        """测试单例实例"""
        from vools.bridge.vbnet.api.process import Process, ProcessModule
        assert isinstance(Process, ProcessModule)

    def test_methods_exist(self):
        """测试主要方法存在"""
        from vools.bridge.vbnet.api.process import ProcessModule
        methods = [
            'Start', 'Shell', 'GetProcesses', 'GetProcessesByName',
            'Kill', 'WaitForExit', 'HasExited', 'GetProcessId'
        ]
        for method in methods:
            assert hasattr(ProcessModule, method), f"ProcessModule 缺少方法: {method}"


class TestNetworkModule:
    """测试 NetworkModule 类"""

    def test_prog_id(self):
        """测试 ProgID 设置"""
        from vools.bridge.vbnet.api.network import NetworkModule
        assert NetworkModule._prog_id == "API.Network"

    def test_singleton_instance(self):
        """测试单例实例"""
        from vools.bridge.vbnet.api.network import Network, NetworkModule
        assert isinstance(Network, NetworkModule)

    def test_methods_exist(self):
        """测试主要方法存在"""
        from vools.bridge.vbnet.api.network import NetworkModule
        methods = [
            'NetworkIsAvailable', 'DownloadFile', 'UrlEncode', 'UrlDecode',
            'GetWebSourceCode', 'GetIPAddresses'
        ]
        for method in methods:
            assert hasattr(NetworkModule, method), f"NetworkModule 缺少方法: {method}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
