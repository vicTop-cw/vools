---
id: actus.basics.text_editor.demo
name: Text Editor Demo
version: 1.0.0
trust: sandbox
kind: demo
platform: desktop
description: Text Editor 的用法演示（kind=demo 的非可执行资产）
---

# Text Editor 演示

> 本文件是 `actus.basics.text_editor` 的演示（`demo:` 字段指向这里）。
> 演示动作 = `kind: demo` 的非可执行资产：只展示主动作的用法与预期形态，
> 不进资产池执行（docs/03 §2.1 kind 表 + §5.4 demo 字段）。

## 运行

```bash
actus run actus.basics.text_editor
```

## 预期

弹出一个 800×600 可缩放的 WebView2 窗口：多标签文本编辑、
打开/保存本地文件（declared_features: file-write）。

## 参数

无（GUI 动作，零入参）。

## 溯源

- 主动作：`vools/actus/actions/basics/text-editor.actus.schema.md`
- kind: exec · purpose: [control, data-store] · trust: sandbox · license: mit
