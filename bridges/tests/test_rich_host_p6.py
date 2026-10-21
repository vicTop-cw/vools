# -*- coding: utf-8 -*-
"""
P6 宿主集成测试 - 内置查看器 + L1/L2 热更新挂钩（mock，不真实开窗）

覆盖：
- WebView2Manager._prepare_preview_config：隔离配置/block_id/CSP 默认策略
- WebView2Manager.refresh_preview：空 patch 短路 + execute_script 转发
- RichPreviewHost.open：scan_rich → render → open_preview 闭环
- PreviewSession.refresh：L1 全文补丁 / L2 区域 diff 补丁推送选择
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from vools.bridge.md.webview2 import WebView2Config, WebView2Result, WebView2Manager
from vools.bridge.md.rich.host import PreviewSession, RichPreviewHost


def _sample_md(tmpdir: str) -> str:
    """构造含 #!rich + 内嵌 HTML 的最小 md。"""
    path = os.path.join(tmpdir, "sample.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "#!rich=hot_reload=l2\n\n"
            "# 富内容样例\n\n"
            "正文文本。\n\n"
            '<section class="frag"><p>frag A</p></section>\n'
        )
    return path


class TestPreparePreviewConfig(unittest.TestCase):
    """P6 预览配置准备（纯逻辑，无窗口）。"""

    def test_default_isolated_config(self):
        manager = WebView2Manager()
        cfg, bid = manager._prepare_preview_config("<html>x</html>", None, "")
        self.assertIsInstance(cfg, WebView2Config)
        self.assertTrue(bid.startswith("rich_preview_"))
        self.assertFalse(cfg.blocking, "内置查看器必须非阻塞，便于热更新推送")
        self.assertEqual(cfg.csp_policy, "off", "容器默认不注入 CSP，内层文档自带 L1")
        self.assertTrue(cfg.user_data_dir, "未显式指定时必须自动分配隔离目录")
        self.assertIn("vools_md_preview", cfg.user_data_dir)

    def test_rich_open_root_and_csp_l1(self):
        manager = WebView2Manager()
        cfg, bid = manager._prepare_preview_config(
            "<html>x</html>",
            None,
            "bid-1",
            rich_open_root="D:/docs",
            csp_policy="l1",
        )
        self.assertEqual(bid, "bid-1")
        self.assertEqual(cfg.rich_open_root, "D:/docs")
        self.assertEqual(cfg.csp_policy, "l1")

    def test_existing_config_preserved(self):
        manager = WebView2Manager()
        base = WebView2Config(title="t", user_data_dir="D:/uv")
        cfg, _ = manager._prepare_preview_config("<html>x</html>", base, "")
        self.assertEqual(cfg.title, "t")
        self.assertEqual(cfg.user_data_dir, "D:/uv", "显式 user_data_dir 不被覆盖")


class TestRefreshPreview(unittest.TestCase):
    """P6 热更新推送转发。"""

    def test_empty_patch_short_circuit(self):
        manager = WebView2Manager()
        with mock.patch.object(manager, "execute_script", return_value=True) as esc:
            self.assertFalse(manager.refresh_preview("bid", ""))
            esc.assert_not_called()

    def test_patch_forwards_to_execute_script(self):
        manager = WebView2Manager()
        with mock.patch.object(manager, "execute_script", return_value=True) as esc:
            self.assertTrue(manager.refresh_preview("bid", "alert(1);"))
            esc.assert_called_once_with("bid", "alert(1);")


class TestRichPreviewHost(unittest.TestCase):
    """P6 host 闭环：open → PreviewSession。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vools_p6_host_")
        self.md = _sample_md(self.tmp)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_open_returns_session_with_block_id(self):
        mgr = mock.Mock(spec=WebView2Manager)
        mgr.open_preview.return_value = WebView2Result(status="ok")
        host = RichPreviewHost(manager=mgr)
        session = host.open(self.md, hot_reload="l2", rich_open_root=self.tmp)
        self.assertIsInstance(session, PreviewSession)
        self.assertTrue(session.block_id.startswith("rich_preview_"))
        # open_preview 收到 renderer 产出的 HTML 与隔离配置
        mgr.open_preview.assert_called_once()
        args, kwargs = mgr.open_preview.call_args
        self.assertIn("block_id", kwargs)
        self.assertEqual(kwargs["rich_open_root"], self.tmp)

    def test_open_failure_raises(self):
        mgr = mock.Mock(spec=WebView2Manager)
        mgr.open_preview.return_value = WebView2Result(status="error", error="boom")
        host = RichPreviewHost(manager=mgr)
        with self.assertRaises(RuntimeError):
            host.open(self.md)

    def test_close_uses_close_window(self):
        mgr = mock.Mock(spec=WebView2Manager)
        mgr.open_preview.return_value = WebView2Result(status="ok")
        mgr.close_window.return_value = True
        host = RichPreviewHost(manager=mgr)
        session = host.open(self.md)
        self.assertTrue(session.close())
        mgr.close_window.assert_called_once_with(session.block_id)


class TestPreviewSessionRefresh(unittest.TestCase):
    """P6 热更新补丁选择与推送。"""

    def test_l1_refresh_pushes_full_html_patch(self):
        self.tmp = tempfile.mkdtemp(prefix="vools_p6_l1_")
        try:
            md = _sample_md(self.tmp)
            mgr = mock.Mock(spec=WebView2Manager)
            mgr.refresh_preview.return_value = True
            sess = PreviewSession(
                md_path=md,
                manager=mgr,
                block_id="bid-l1",
                build_dir=self.tmp,
                mode="l1",
            )
            patch = sess.refresh()
            self.assertTrue(patch)
            self.assertIn("srcdoc", patch, "L1 补丁应替换 iframe srcdoc")
            mgr.refresh_preview.assert_called_once()
            mgr.refresh_preview.assert_called_once_with("bid-l1", patch)
        finally:
            import shutil

            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_l2_refresh_pushes_region_patch(self):
        self.tmp = tempfile.mkdtemp(prefix="vools_p6_l2_")
        try:
            md = _sample_md(self.tmp)
            mgr = mock.Mock(spec=WebView2Manager)
            mgr.refresh_preview.return_value = True
            sess = PreviewSession(
                md_path=md,
                manager=mgr,
                block_id="bid-l2",
                build_dir=self.tmp,
                mode="l2",
            )
            patch = sess.refresh()
            self.assertTrue(patch)
            self.assertIn("replaceChildren", patch, "L2 补丁应使用 replaceChildren")
            mgr.refresh_preview.assert_called_once_with("bid-l2", patch)
        finally:
            import shutil

            shutil.rmtree(self.tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
