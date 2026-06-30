# Tasks - vools 文档站点建设

## 阶段一：基础环境搭建

- [ ] Task 1: 安装 MkDocs 及相关依赖
  - 安装 mkdocs
  - 安装 mkdocs-material
  - 安装 PyMdown Extensions
  - 创建 pyproject.toml 依赖条目

- [ ] Task 2: 创建 MkDocs 配置文件
  - 创建 mkdocs.yml 主配置
  - 配置主题 Material
  - 配置导航结构
  - 配置搜索功能
  - 配置代码高亮

- [ ] Task 3: 创建文档目录结构
  - 创建 docs/ 目录
  - 创建各模块子目录
  - 创建附件目录

## 阶段二：核心文档编写

- [ ] Task 4: 编写主页 (#001)
  - 编写项目定位
  - 编写核心特性卡片
  - 添加快速代码示例
  - 添加徽章和链接

- [ ] Task 5: 编写安装和快速开始文档
  - 编写 installation.md (#002)
  - 编写 quickstart.md (#003)
  - 添加测试验证的示例代码

- [ ] Task 6: 编写核心功能文档
  - 编写 decorators.md (#004)
  - 编写 placeholder.md (#005)
  - 编写 overload.md (#006)
  - 编写 curry.md (#007)
  - 编写 memoize.md (#008)

- [ ] Task 7: 编写函数式编程文档
  - 编写 pipe.md (#009)
  - 编写 seq.md (#010)
  - 编写 box.md (#011)
  - 编写 result.md (#012)

## 阶段三：高级功能文档

- [ ] Task 8: 编写响应式编程文档
  - 编写 overview.md (#013)
  - 编写 observable.md (#014)
  - 编写 operators.md (#015)
  - 编写 monitoring.md (#016)

- [ ] Task 9: 编写数据处理文档
  - 编写 vlist.md (#017)
  - 编写 vtext.md (#018)
  - 编写 vdate.md (#019)

- [ ] Task 10: 编写多语言桥接文档
  - 编写 bridge/overview.md (#020)
  - 编写 bridge/rust.md (#021)
  - 编写 bridge/nim.md (#022)
  - 编写 bridge/go.md (#023)
  - 编写 bridge/others.md (#024)

## 阶段四：SQL 和附录文档

- [ ] Task 11: 编写 SQL 工具文档
  - 编写 sql/overview.md (#025)
  - 编写 sql/sqlite.md (#026)
  - 编写 sql/spark.md (#027)

- [ ] Task 12: 编写附录文档
  - 编写 appendix/changelog.md (#A01)
  - 编写 appendix/faq.md (#A02)
  - 编写 appendix/benchmark.md (#A03)
  - 编写 appendix/platform.md (#A04)
  - 编写 appendix/contribute.md (#A05)
  - 编写 api/reference.md (#A06)

## 阶段五：文档同步与验证

- [ ] Task 13: 同步现有 README 文档
  - 对比现有 README.md 与源代码
  - 更新不一致的内容
  - 补充缺失的示例

- [ ] Task 14: 验证所有示例代码
  - 运行现有测试
  - 为每个示例编写验证脚本
  - 确保示例代码可独立运行
  - 验证输出结果正确
  - 标注测试状态

- [ ] Task 15: 配置 GitHub Pages 部署
  - 配置 .github/workflows/docs.yml
  - 测试本地预览
  - 验证 GitHub Actions 自动部署

## 阶段六：清理与上线

- [ ] Task 16: 清理旧文档
  - 删除旧的 docs/ 目录（如有冲突）
  - 删除旧的 guide/ 目录
  - 更新主 README.md 指向新文档

- [ ] Task 17: 最终验证
  - 本地构建测试
  - 检查所有链接
  - 验证导航结构

## 任务依赖关系

```
Task 1 ─┬─> Task 2 ─> Task 3 ─┬─> Task 4 ─┬─> Task 13 ─> Task 14 ─┬─> Task 15 ─> Task 16 ─> Task 17
        │                     │           │                        │
        │                     │           ├─> Task 5 ─────────────┤
        │                     │           │                        │
        │                     │           ├─> Task 6 ─────────────┤
        │                     │           │                        │
        │                     │           ├─> Task 7 ─────────────┤
        │                     │           │                        │
        │                     │           ├─> Task 8 ─────────────┤
        │                     │           │                        │
        │                     │           ├─> Task 9 ─────────────┤
        │                     │           │                        │
        │                     │           ├─> Task 10 ────────────┤
        │                     │           │                        │
        │                     │           └─> Task 11 ────────────┤
        │                     │                                    │
        └─────────────────────┴─> Task 12 ────────────────────────┘
```
