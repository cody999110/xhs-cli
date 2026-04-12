---
name: xhs-publish-post
description: >-
  Generate and publish a Xiaohongshu note end-to-end via the XHS KOL Agent CLI.
  Includes content generation, image preparation, and browser-automated
  publishing. Use when the user wants to publish, post, or upload content to
  Xiaohongshu.
---

# 生成 + 发布小红书笔记

## 前置条件

1. 已完成 `.env` 配置（LLM Key + Tavily Key）
2. 已登录创作者平台（`python run.py --login-creator` 或 `--import-cookies`）
3. Cookie 文件存在于 `data/xhs_cookies.json`

## 命令

### 指定主题发布

```bash
python run.py "波士顿租房攻略" --publish
```

### 随机选题发布

```bash
python run.py --random --publish
```

### 渲染图 + 发布（推荐）

```bash
python run.py "波士顿租房攻略" --publish --render-slides
```

### 交互式菜单

```bash
python run.py
# 选择 [5] 生成笔记 + 发布到小红书
```

## 完整流程

```
Step 1: LLM 生成搜索关键词（中英各 2 条）
Step 2: Tavily 搜索素材
Step 3: LLM 生成小红书风格笔记（轮播图 + 正文）
Step 4: 保存 Markdown 到 output/
Step 5: 下载配图 → Playwright 自动发布到小红书
```

发布通过 Playwright 操控 `creator.xiaohongshu.com`：上传图片 → 填写标题和正文 → 点击发布。

## 注意事项

- 发帖间隔建议不低于 5 分钟
- 如果配图搜索失败（API 配额用尽），会跳过发布、仅保存本地
- 发布结果状态：`已发布` 或 `待审核`（小红书可能需审核）
- 设置 `XHS_HEADLESS=false` 可观察浏览器操作过程

## Python API 调用

```python
from src.agent import run

filepath = run("波士顿租房攻略", publish=True, render_slides=True)
```
