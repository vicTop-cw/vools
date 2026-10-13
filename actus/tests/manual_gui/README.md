# manual_gui/ — 手动 GUI 调试脚本（不进自动测试套件）

这里的脚本需要**真实桌面环境**：WebView2 / CEF(cefpython3) / pywebview /
pythonnet(clr)，多数还会真实弹窗并需要人工观察，无法在 headless CI 里运行。

它们也不符合 pytest 收集约定：历史上用 `importlib.util.spec_from_file_location`
把 `bridges/.../md/webview2.py` 当**顶层模块**加载，导致其包内相对导入
（`from ..core...`）在收集期直接 `ImportError`，并污染整个 `pytest tests/`
（一个收集失败会中断同批其它测试）。

## 现状

- 自动收集已通过 `pyproject.toml` 的 `norecursedirs = [..., "manual_gui"]`
  跳过本目录。
- 保留脚本供本机**手动**调试浏览器渲染：

```powershell
python tests/manual_gui/test_webview2_direct.py
```

## 如果将来要把它们变成真测试

不要用 `spec_from_file_location` 顶层加载；改为走正常包导入
（参考 `tests/_ai_local_bootstrap.py`）：

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _ai_local_bootstrap  # noqa
_ai_local_bootstrap.install()
from vools.bridge.md import webview2   # 作为正规包子模块导入
```

并对 GUI 依赖缺失做 `pytest.importorskip("webview")` / 平台判断，
使无桌面环境时**skip 而不是 error**。
