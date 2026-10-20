# Image Viewer 演示

> 本文件是 `actus.basics.image_viewer` 的演示（`demo:` 字段指向这里）。
> 演示动作 = `kind: demo` 的非可执行资产：只展示主动作的用法与预期形态，
> 不进资产池执行（docs/03 §2.1 kind 表 + §5.4 demo 字段）。

## 运行

```bash
actus run actus.basics.image_viewer
```

## 预期

弹出一个 900×700 可缩放的 WebView2 窗口：图片浏览、缩放、
目录内前后翻页（purpose: source——只读外部文件，不写回）。

## 参数

无（GUI 动作，零入参）。

## 溯源

- 主动作：`vools/actus/actions/basics/image-viewer.actus.schema.md`
- kind: exec · purpose: [source] · trust: sandbox · license: mit
