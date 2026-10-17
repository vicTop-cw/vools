# vools.bridge.md.rich — md 富文本/富输出子模块

提供 Markdown 桥接框架的**富文本**能力：格式化渲染、HTML 转 Markdown、
富代码块/表格支持等。是 `vools.bridge.md` 的可选增强层。

## 公开符号

各模块显式声明 `__all__`，典型符号如 `HtmlRenderer`、`RichTextParser` 等
（见文件内 `__all__` 定义）。

## 约定

- 不阻塞 `vools.bridge.md` 冷启动（惰性导入 + `__getattr__`）。
- py3.6 兼容：模块级 `__getattr__` 在 py3.6 下是死函数，须保留
  `if sys.version_info < (3, 7):` 兜底块手动绑定导出名。
