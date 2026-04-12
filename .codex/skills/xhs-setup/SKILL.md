---
name: xhs-setup
description: >-
  Set up the XHS KOL Agent project: install Python dependencies, configure API
  keys in .env, import Chrome cookies or scan QR code to login. Use when the
  user wants to initialize, configure, or fix login issues for the XHS CLI.
---

# XHS CLI 项目初始化与登录

## 前置条件

- Python 3.10+
- Chrome 浏览器（推荐，用于导入 Cookie）

## 工作流

```
Task Progress:
- [ ] Step 1: 安装 Python 依赖
- [ ] Step 2: 安装 Playwright 浏览器
- [ ] Step 3: 配置 .env 环境变量
- [ ] Step 4: 导入登录状态
```

### Step 1: 安装 Python 依赖

```bash
cd <project_root>
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: 安装 Playwright 浏览器

```bash
playwright install chromium
```

### Step 3: 配置 .env

复制模板并填写 API Key：

```bash
cp .env.example .env
```

必填项：
- `LLM_API_KEY` + `LLM_BASE_URL` + `LLM_MODEL` — 大模型配置（参考 `.env.example` 中的多模型示例）
- `TAVILY_API_KEY` — 互联网搜索

推荐填写（图片源，配置越多越稳定）：
- `UNSPLASH_ACCESS_KEY` — Unsplash 图片
- `PEXELS_API_KEY` — Pexels 图片
- `PIXABAY_API_KEY` — Pixabay 图片（支持中文搜索）

向后兼容：旧的 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` 仍可用。

### Step 4: 导入登录状态

**方式一：从 Chrome 导入（推荐）**

先在 Chrome 浏览器中登录 `www.xiaohongshu.com` 和 `creator.xiaohongshu.com`，然后：

```bash
python run.py --import-cookies
```

**方式二：扫码登录**

```bash
python run.py --login           # 主站（浏览/互动）
python run.py --login-creator   # 创作者平台（发帖）
```

Cookie 保存在 `data/xhs_cookies.json`，后续无需重复登录。

## 验证

运行以下命令确认环境正常：

```bash
python run.py --list   # 应输出主题池列表
python run.py --browse  # 应能浏览笔记（需已登录）
```

## 常见问题

- **Chrome Cookie 导入失败**：确保 Chrome 已关闭，或改用扫码登录
- **Cookie 失效**：重新执行 Step 4
- **LLM 报错**：检查 `.env` 中的 `LLM_API_KEY` 和 `LLM_BASE_URL` 是否正确
