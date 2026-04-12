# 小红书 KOL Agent — Agent 操作指南

本项目是一个 AI 驱动的小红书自动化 CLI 工具，支持内容生成、发布和互动。以下是 Agent 可直接执行的核心工作流。

## 项目概览

```
入口: python run.py [args]     # 命令行模式
入口: python run.py            # 交互式菜单（无参数）
配置: .env                     # API Key 等环境变量
输出: output/                  # 生成的笔记 Markdown
数据: data/                    # Cookie 缓存、下载的图片
```

## 环境要求

- Python 3.10+, 依赖见 `requirements.txt`
- Playwright Chromium (`playwright install chromium`)
- `.env` 文件配置完成（复制自 `.env.example`）

---

## 工作流 1: 项目初始化

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, TAVILY_API_KEY 等
python run.py --import-cookies   # 从 Chrome 导入登录状态
```

`.env` 中的 LLM 配置支持多种模型（DeepSeek/ChatGPT/通义千问/智谱GLM/Kimi/文心一言/SiliconFlow），详见 `.env.example`。

## 工作流 2: 生成笔记（不发布）

```bash
python run.py "主题名称"                    # 指定主题，素材图模式
python run.py "主题名称" --render-slides    # 指定主题，渲染图模式（推荐）
python run.py --random                      # 随机选题
python run.py --random --render-slides      # 随机选题 + 渲染图
python run.py --list                        # 查看主题池
```

流程: 输入主题 → LLM 生成搜索词 → Tavily 搜索 → LLM 规划轮播图 → 配图 → LLM 写正文 → 保存到 `output/`

## 工作流 3: 生成 + 发布到小红书

```bash
python run.py "主题名称" --publish                    # 生成并发布
python run.py "主题名称" --publish --render-slides    # 渲染图 + 发布（推荐）
python run.py --random --publish                      # 随机选题 + 发布
```

前提: 已通过 `--import-cookies` 或 `--login-creator` 完成创作者平台登录。

## 工作流 4: 自动批量互动

```bash
python run.py --engage                             # 默认 5 篇，点赞+AI评论
python run.py --engage --count 10                  # 10 篇
python run.py --engage --like-only                 # 仅点赞
python run.py --engage --keyword "留学" --count 8  # 按关键词
```

行为: 浏览笔记 → 逐篇点赞 → AI 生成评论 → 发送，每篇间隔 20-45 秒。

## 工作流 5: 单篇笔记互动

```bash
python run.py --browse                                    # 浏览推荐笔记
python run.py --browse --keyword "美食"                    # 搜索笔记
python run.py --like <note_id>                            # 点赞
python run.py --comment <note_id>                         # AI 评论
python run.py --comment <note_id> -m "自定义评论内容"      # 手动评论
```

## 工作流 6: 登录管理

```bash
python run.py --import-cookies    # 从 Chrome 导入（推荐）
python run.py --login             # 扫码登录主站
python run.py --login-creator     # 扫码登录创作者平台
```

---

## Python API（供 Agent 编程调用）

```python
from src.agent import run, pick_random_topic, list_topics
from src.engager import engage, browse_notes, like_single_note, comment_single_note

# 生成笔记
filepath = run("波士顿租房攻略", publish=False, render_slides=True)

# 生成 + 发布
filepath = run("波士顿租房攻略", publish=True, render_slides=True)

# 随机选题
topic = pick_random_topic()

# 批量互动
engage(count=5, like_only=False, keyword="留学")

# 单篇互动
notes = browse_notes(keyword="美食")
like_single_note("64c2a1b2c3d4e5f6a7b8c9d0")
comment_single_note("64c2a1b2c3d4e5f6a7b8c9d0")
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `run.py` | CLI 入口 |
| `src/agent.py` | 主编排器（搜索→生成→保存→发布） |
| `src/llm.py` | LLM 客户端（兼容所有 OpenAI API 格式） |
| `src/engager.py` | 互动引擎（浏览+点赞+AI评论） |
| `src/research/image_searcher.py` | 图片搜索（Unsplash/Pexels/Pixabay/Tavily） |
| `src/generator/pipeline.py` | 内容生成流水线 |
| `src/publisher/publisher.py` | 发布编排器 |
| `src/publisher/xhs_client.py` | Playwright 浏览器自动化 |
| `config/topics.yaml` | 主题池 |
| `.env.example` | 环境变量模板 |

## 注意事项

- 发帖间隔建议 ≥ 5 分钟，互动间隔 20-45 秒
- 单次互动建议不超过 10-15 篇
- Cookie 失效后需重新登录
- 仅供学习和研究使用，请遵守小红书社区规范
