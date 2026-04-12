---
name: xhs-generate-post
description: >-
  Generate a Xiaohongshu-style note from a topic using the XHS KOL Agent CLI.
  Searches web for material, plans carousel slides, fetches images, and writes
  XHS-style copy. Use when the user wants to create, generate, or write a
  Xiaohongshu post or note without publishing.
---

# 生成小红书笔记

## Pipeline 流程

```
输入主题 → LLM 生成搜索词 → Tavily 搜索素材 → LLM 规划轮播图
→ 配图（素材图 or 渲染图）→ LLM 撰写正文 → 保存 Markdown
```

## 命令

### 指定主题生成

```bash
python run.py "波士顿租房攻略"
```

### 随机选题生成

```bash
python run.py --random
```

### 使用渲染图模式（推荐，无需图片 API）

```bash
python run.py "波士顿租房攻略" --render-slides
```

### 交互式菜单

```bash
python run.py
# 选择 [4] 生成笔记
```

## 图片模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| 素材图（默认） | 从 Unsplash/Pexels/Pixabay 搜索竖屏配图 | 需要真实摄影图片 |
| 渲染图 (`--render-slides`) | HTML 模板渲染小红书风格排版图 | 推荐，无需图片 API Key |

## 输出

生成的笔记保存在 `output/` 目录，格式为 Markdown，文件名包含时间戳和标题。

内容包括：
- 标题（带 emoji 的爆款标题）
- 6-9 页轮播图规划（每页一个知识点）
- 配图 URL 或本地渲染图路径
- 300-500 字小红书风格正文（含 emoji、分段、hashtag）

## 自定义

- **主题池**: 编辑 `config/topics.yaml`
- **写作风格**: 修改 `src/generator/pipeline.py` 中的 Prompt
- **查看主题池**: `python run.py --list`

## Python API 调用

```python
from src.agent import run, pick_random_topic

topic = pick_random_topic()
filepath = run(topic, publish=False, render_slides=True)
```
