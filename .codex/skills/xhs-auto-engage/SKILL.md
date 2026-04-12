---
name: xhs-auto-engage
description: >-
  Automatically browse, like, and AI-comment on Xiaohongshu notes in batch.
  Use when the user wants to auto-engage, boost interaction, auto-like,
  auto-comment, or grow their XHS account through automated engagement.
---

# 自动批量互动（浏览 + 点赞 + AI 评论）

## 前置条件

1. 已登录小红书主站（`python run.py --login` 或 `--import-cookies`）
2. `.env` 中已配置 `LLM_API_KEY`（AI 评论需要大模型）

## 命令

### 自动互动（默认 5 篇，点赞 + AI 评论）

```bash
python run.py --engage
```

### 指定数量

```bash
python run.py --engage --count 10
```

### 仅点赞（不评论）

```bash
python run.py --engage --like-only
```

### 按关键词搜索后互动

```bash
python run.py --engage --keyword "留学" --count 8
```

### 交互式菜单

```bash
python run.py
# 选择 [7] 自动互动
```

## 行为逻辑

1. 浏览推荐笔记或按关键词搜索（获取 `count * 2` 篇备选）
2. 逐篇处理：
   - 点赞笔记
   - 等待 5-12 秒
   - 获取笔记详情 → LLM 生成上下文相关评论 → 发送评论
   - 等待 20-45 秒后处理下一篇
3. 达到目标数量后停止

AI 评论特点：
- 20-80 字，自然口语化
- 从 5 种角度随机切换（共鸣、提问、补充、感谢、轻松互动）
- 与笔记内容强相关，无 AI 味

## 安全建议

- 建议单次互动不超过 10-15 篇
- 每日总互动量控制在合理范围
- 过于频繁可能导致账号被限制

## Python API 调用

```python
from src.engager import engage

engage(count=5, like_only=False, keyword="留学")
```
