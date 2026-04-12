---
name: xhs-interact
description: >-
  Like or comment on a specific Xiaohongshu note by its ID. Supports manual
  comment text or AI-generated comments. Use when the user wants to like, heart,
  comment on, or interact with a specific XHS note.
---

# 单篇笔记互动（点赞 / 评论）

## 前置条件

已登录小红书主站（`python run.py --login` 或 `--import-cookies`）

## 获取笔记 ID

笔记 ID 是 24 位十六进制字符串，可通过以下方式获取：
- 浏览笔记列表：`python run.py --browse` 或 `python run.py --browse --keyword "留学"`
- 从笔记 URL 中提取：`https://www.xiaohongshu.com/explore/64c2a1b2c3d4e5f6a7b8c9d0`

## 命令

### 点赞指定笔记

```bash
python run.py --like 64c2a1b2c3d4e5f6a7b8c9d0
```

### AI 自动生成评论

```bash
python run.py --comment 64c2a1b2c3d4e5f6a7b8c9d0
```

自动获取笔记详情，LLM 根据内容生成自然评论（20-80 字）。

### 自定义评论内容

```bash
python run.py --comment 64c2a1b2c3d4e5f6a7b8c9d0 -m "太实用了！正好下周要去"
```

### 浏览笔记列表

```bash
python run.py --browse                  # 推荐笔记
python run.py --browse --keyword "美食"  # 按关键词搜索
```

### 交互式菜单

```bash
python run.py
# [6] 浏览笔记  [8] 点赞  [9] 评论
```

## Python API 调用

```python
from src.engager import like_single_note, comment_single_note, browse_notes

browse_notes(keyword="留学")
like_single_note("64c2a1b2c3d4e5f6a7b8c9d0")
comment_single_note("64c2a1b2c3d4e5f6a7b8c9d0")              # AI 评论
comment_single_note("64c2a1b2c3d4e5f6a7b8c9d0", content="手动评论内容")
```
