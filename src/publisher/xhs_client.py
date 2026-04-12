"""小红书 Playwright 自动化客户端 — 登录、发帖、浏览、点赞、评论。

使用 Playwright 控制 Chromium 浏览器与小红书网页版交互。
首次使用需扫码登录，之后通过 Cookie 保持会话。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote

from src.config import DATA_DIR, XHS_HEADLESS
from src.utils.logger import logger

COOKIES_FILE = DATA_DIR / "xhs_cookies.json"

XHS_URL = "https://www.xiaohongshu.com"
CREATOR_URL = "https://creator.xiaohongshu.com"


class XHSClientError(Exception):
    pass


class XHSClient:
    """基于 Playwright 的小红书自动化客户端。"""

    def __init__(self, headless: bool | None = None):
        self.headless = headless if headless is not None else XHS_HEADLESS
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def _start_browser(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )

        self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
            window.chrome = {runtime: {}};
        """)

        # 加载 Cookie: 先读已保存文件，若没有则尝试从 Chrome 导入
        cookies_loaded = False
        if COOKIES_FILE.exists():
            try:
                cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
                if cookies:
                    self._context.add_cookies(cookies)
                    cookies_loaded = True
                    logger.debug("已加载保存的 Cookie")
            except Exception as e:
                logger.warning(f"读取 Cookie 文件失败: {e}")

        if not cookies_loaded:
            cookies_loaded = self._try_import_chrome_cookies()

        self._page = self._context.new_page()

    def _try_import_chrome_cookies(self) -> bool:
        """尝试从本地 Chrome 浏览器导入小红书 Cookie。"""
        try:
            from src.publisher.chrome_cookies import import_chrome_cookies

            cookies = import_chrome_cookies()
            if cookies:
                self._context.add_cookies(cookies)
                self._save_cookies()
                logger.info("已从本地 Chrome 导入小红书 Cookie")
                return True
            else:
                logger.debug("Chrome 中未找到小红书 Cookie")
                return False
        except FileNotFoundError:
            logger.debug("未找到 Chrome Cookies 数据库")
            return False
        except Exception as e:
            logger.debug(f"Chrome Cookie 导入失败: {e}")
            return False

    def _save_cookies(self):
        if self._context:
            cookies = self._context.cookies()
            COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
            COOKIES_FILE.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self):
        """登录小红书。

        优先级: 已保存 Cookie → 从 Chrome 导入 → 扫码登录。
        """
        if not self._page:
            self._start_browser()

        self._page.goto(XHS_URL, wait_until="domcontentloaded")
        time.sleep(3)

        if self._check_page_logged_in():
            logger.info("已通过 Cookie 登录小红书")
            self._save_cookies()
            return

        # Cookie 无效，尝试从 Chrome 重新导入
        logger.info("Cookie 已失效，尝试从本地 Chrome 导入...")
        if self._try_import_chrome_cookies():
            self._page.goto(XHS_URL, wait_until="domcontentloaded")
            time.sleep(3)
            if self._check_page_logged_in():
                logger.info("已通过 Chrome Cookie 登录小红书")
                self._save_cookies()
                return
            logger.info("Chrome Cookie 也已过期")

        # 都失败了，才需要扫码登录
        if self.headless:
            logger.info("需要扫码登录，切换到可见浏览器...")
            self.close()
            self.headless = False
            self._start_browser()
            self._page.goto(XHS_URL, wait_until="domcontentloaded")
            time.sleep(3)

        try:
            login_btn = self._page.locator('div.login-btn, [class*="login-btn"]')
            if login_btn.count() > 0 and login_btn.first.is_visible():
                login_btn.first.click()
                time.sleep(2)
        except Exception:
            pass

        logger.info("=" * 55)
        logger.info("📱 请用小红书 APP 扫描屏幕上的二维码登录")
        logger.info("   登录成功后程序将自动继续...")
        logger.info("=" * 55)

        # 等待登录：只检查 Cookie 变化，绝不刷新页面
        for i in range(180):
            time.sleep(2)
            if self._has_session_cookie():
                time.sleep(3)
                self._save_cookies()
                logger.info("✅ 小红书登录成功!")
                return

        raise XHSClientError("登录超时 — 请在 6 分钟内完成扫码")

    def _has_session_cookie(self) -> bool:
        """仅检查浏览器 Cookie，不触碰页面（用于登录等待轮询）。"""
        try:
            cookies = self._context.cookies(XHS_URL)
            return any(c["name"] == "web_session" for c in cookies)
        except Exception:
            return False

    def _check_page_logged_in(self) -> bool:
        """检查已加载的页面是否处于登录状态（仅在页面已加载后调用）。"""
        try:
            if not self._has_session_cookie():
                return False

            login_btn = self._page.locator('div.login-btn, [class*="login-btn"]')
            if login_btn.count() > 0 and login_btn.first.is_visible():
                return False

            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Creator Platform Auth
    # ------------------------------------------------------------------

    def _on_creator_login_page(self) -> bool:
        """当前是否在创作者平台的登录页。"""
        url = self._page.url
        return "login" in url or "redirectReason" in url

    def login_creator(self):
        """登录小红书创作者平台（发帖用）。

        流程：打开创作者平台 → 如已登录直接返回 →
        否则打开可见浏览器 → 用户手动登录（扫码/短信/密码均可）→
        检测到离开登录页后自动保存 Cookie 并继续。
        """
        if not self._page:
            self._start_browser()

        page = self._page
        logger.info("正在检查创作者平台登录状态...")

        # 先用 headless 尝试，看 Cookie 是否有效
        page.goto(f"{CREATOR_URL}/publish/publish", wait_until="networkidle")
        # 多等几秒让 JS 异步重定向完成
        time.sleep(6)

        if not self._on_creator_login_page():
            logger.info("创作者平台已登录 ✓")
            self._save_cookies()
            return

        # 需要登录 — 必须用可见浏览器
        if self.headless:
            logger.info("切换到可见浏览器...")
            self._save_cookies()
            self.close()
            self.headless = False
            self._start_browser()
            page = self._page

        # 导航到创作者平台登录页
        page.goto(f"{CREATOR_URL}/login", wait_until="networkidle")
        time.sleep(3)

        # 如果已经自动登录了（Cookie 在可见模式下生效）
        if not self._on_creator_login_page():
            logger.info("创作者平台已自动登录 ✓")
            self._save_cookies()
            return

        logger.info("=" * 55)
        logger.info("📱 请在浏览器中登录创作者平台")
        logger.info("   支持：扫码 / 手机验证码 / 密码登录")
        logger.info("   登录成功后程序将自动继续...")
        logger.info("=" * 55)

        # 使用 Playwright 的 wait_for_url 事件驱动等待（非轮询）
        # 登录成功后页面会跳转离开 /login，触发此等待结束
        try:
            page.wait_for_url(
                lambda url: "login" not in url and "redirectReason" not in url,
                timeout=360_000,  # 6 分钟
            )
        except Exception:
            raise XHSClientError("创作者平台登录超时 — 请在 6 分钟内完成登录")

        time.sleep(3)
        self._save_cookies()
        logger.info("✅ 创作者平台登录成功!")

    def create_post(
        self,
        title: str,
        content: str,
        image_paths: list[Path],
        tags: list[str] | None = None,
    ) -> dict:
        """通过小红书创作者平台发布图文笔记。

        注意: 调用前应先调用 login() 和 login_creator()。
        """
        if not self._page:
            raise XHSClientError("浏览器未启动，请先调用 login()")

        page = self._page
        debug_screenshot = DATA_DIR / "debug_publish_page.png"

        # ① 导航到图文发布页（用侧栏链接而非标签页切换）
        self._navigate_to_image_publish(page, debug_screenshot)

        # ② 上传图片
        if image_paths:
            self._upload_images(page, image_paths, debug_screenshot)

        # ③ 填写标题
        # 小红书标题限 20 字，emoji 可能被算作 2 字，保守截断到 16 字
        safe_title = self._truncate_title(title, max_len=16)
        title_filled = self._fill_title(page, safe_title, debug_screenshot)

        # ④ 填写正文
        content_filled = self._fill_content(page, content, debug_screenshot)

        # ⑤ 添加标签
        if tags:
            self._add_tags(tags)

        # 关闭可能残留的话题下拉框（按 Escape + 点击空白处）
        page.keyboard.press("Escape")
        time.sleep(0.5)
        try:
            page.locator("body").click(position={"x": 10, "y": 10})
        except Exception:
            pass
        time.sleep(1)

        # ⑥ 点击发布按钮
        self._click_publish_button(page, safe_title, title_filled, content_filled, debug_screenshot)

        self._save_cookies()
        return {"status": "pending", "title": title}

    # ------------------------------------------------------------------
    #  create_post 子步骤
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate_title(title: str, max_len: int = 16) -> str:
        """安全截断标题，考虑 emoji 在小红书可能被算作多字符。"""
        import unicodedata
        result = []
        count = 0
        for ch in title:
            cat = unicodedata.category(ch)
            # emoji (So = Symbol, other) 和 variation selectors 占 2 个计数
            if cat == "So" or cat == "Mn":
                w = 2
            else:
                w = 1
            if count + w > max_len:
                break
            result.append(ch)
            count += w
        truncated = "".join(result)
        if truncated != title:
            logger.debug(f"标题从 {len(title)} 字截断到 {len(truncated)} 字 (计数 {count})")
        return truncated

    def _navigate_to_image_publish(self, page, debug_screenshot):
        """导航到图文发布页面。

        策略: 先用侧栏「上传图文」链接跳转（最可靠），如果失败则
        直接访问 URL 再点击内容区标签页切换。
        """
        page.goto(f"{CREATOR_URL}/publish/publish", wait_until="domcontentloaded")
        time.sleep(4)

        # 用 JS 找到内容区的「上传图文」标签（不是侧栏的）并点击
        # 内容区标签位于页面上方（y<120）且在侧栏右侧（x>140）
        result = page.evaluate("""() => {
            const candidates = [];
            document.querySelectorAll('*').forEach(el => {
                if (el.children.length === 0 &&
                    el.textContent.trim() === '上传图文') {
                    const rect = el.getBoundingClientRect();
                    candidates.push({
                        el: el,
                        x: rect.left,
                        y: rect.top,
                        w: rect.width,
                        tag: el.tagName
                    });
                }
            });

            // 优先选内容区标签页（上方、侧栏右侧）
            for (const c of candidates) {
                if (c.y < 120 && c.x > 140 && c.w > 0) {
                    c.el.click();
                    return {clicked: 'content_tab', x: c.x, y: c.y, tag: c.tag};
                }
            }

            // 备选：点任意一个
            if (candidates.length > 0) {
                const c = candidates[0];
                c.el.click();
                return {clicked: 'fallback', x: c.x, y: c.y, tag: c.tag};
            }
            return {clicked: 'none'};
        }""")
        logger.info(f"切换图文标签: {result}")
        time.sleep(3)

        # 验证：检查页面上是否有图片上传区域（而非视频上传区域）
        has_video_prompt = page.locator('text="拖拽视频到此或点击上传"').count() > 0
        has_image_upload = page.locator(
            'input[type="file"][accept*=".jpg"], '
            'input[type="file"][accept*="image"]'
        ).count() > 0

        page.screenshot(path=str(debug_screenshot))

        if has_video_prompt and not has_image_upload:
            logger.warning("仍在视频标签页，尝试用侧栏导航...")
            # 点击侧栏「发布笔记」按钮展开下拉，再点「上传图文」
            sidebar_result = page.evaluate("""() => {
                // 找侧栏中的「上传图文」链接并点击
                const links = document.querySelectorAll('a, [role="menuitem"]');
                for (const link of links) {
                    if (link.textContent.trim() === '上传图文' ||
                        link.textContent.includes('上传图文')) {
                        link.click();
                        return 'sidebar_link_clicked';
                    }
                }
                return 'not_found';
            }""")
            logger.info(f"侧栏导航结果: {sidebar_result}")
            time.sleep(4)
            page.screenshot(path=str(debug_screenshot))

        logger.info("已进入图文发布页面")

    def _upload_images(self, page, image_paths, debug_screenshot):
        """上传图片到创作者平台。"""
        file_input = self._find_image_file_input(page, debug_screenshot)
        paths_to_upload = [str(p) for p in image_paths[:18]]
        logger.info(f"正在上传 {len(paths_to_upload)} 张图片...")

        # 先尝试批量上传
        try:
            file_input.set_input_files(paths_to_upload)
            logger.info("批量设置文件成功")
        except Exception:
            logger.info("批量上传不支持，改为逐张上传...")
            for i, p in enumerate(paths_to_upload):
                try:
                    file_input.set_input_files(p)
                    time.sleep(2)
                    logger.debug(f"  第 {i+1}/{len(paths_to_upload)} 张已设置")
                except Exception as e:
                    logger.warning(f"上传失败: {p} — {e}")
                try:
                    file_input = self._find_image_file_input(page, debug_screenshot)
                except Exception:
                    pass

        # 等待上传处理
        logger.info("等待图片处理...")
        time.sleep(8)

        # 验证上传结果：检查是否出现图片预览
        preview_count = page.locator(
            'img[src*="xhscdn"], img[src*="sns-img"], '
            '[class*="preview"] img, [class*="image-item"], '
            '[class*="upload-item"], [class*="coverImg"]'
        ).count()
        logger.info(f"页面上检测到 {preview_count} 个图片预览元素")

        page.screenshot(path=str(debug_screenshot))

        if preview_count == 0:
            logger.warning("未检测到图片预览，上传可能未成功")
            # 打印页面上的关键信息辅助调试
            page_text = page.locator('body').inner_text()[:500]
            logger.debug(f"页面文字摘要: {page_text}")

        logger.info("图片上传步骤完成")

    def _fill_title(self, page, title, debug_screenshot) -> bool:
        """填写标题。"""
        selectors = [
            'input[placeholder*="标题"]',
            '#title',
            '[placeholder*="标题"]',
            'input[class*="title"]',
            'input[name="title"]',
        ]
        for sel in selectors:
            try:
                ti = page.locator(sel)
                ti.first.wait_for(state="visible", timeout=5000)
                ti.first.click()
                ti.first.fill(title)
                logger.info(f"已填入标题: {title}")
                return True
            except Exception:
                continue

        try:
            ti = page.get_by_placeholder("标题", exact=False)
            if ti.count() > 0:
                ti.first.click()
                ti.first.fill(title)
                logger.info(f"已填入标题: {title}")
                return True
        except Exception:
            pass

        logger.warning("未找到标题输入框")
        page.screenshot(path=str(debug_screenshot))
        return False

    def _fill_content(self, page, content, debug_screenshot) -> bool:
        """填写正文。"""
        selectors = [
            '#post-textarea',
            'div.ql-editor[contenteditable="true"]',
            '[contenteditable="true"].ql-editor',
            '[placeholder*="正文"]',
            '[placeholder*="添加正文"]',
            '[data-placeholder*="正文"]',
        ]
        for sel in selectors:
            try:
                ca = page.locator(sel)
                ca.first.wait_for(state="visible", timeout=5000)
                ca.first.click()
                time.sleep(0.3)
                try:
                    ca.first.fill(content[:1000])
                except Exception:
                    page.keyboard.type(content[:1000], delay=10)
                logger.info(f"已填入正文: {len(content[:1000])} 字")
                return True
            except Exception:
                continue

        try:
            editable = page.locator('div[contenteditable="true"]')
            if editable.count() > 0:
                editable.first.click()
                time.sleep(0.3)
                page.keyboard.type(content[:1000], delay=10)
                logger.info(f"已填入正文（备用方式）: {len(content[:1000])} 字")
                return True
        except Exception:
            pass

        logger.warning("未找到正文输入框")
        page.screenshot(path=str(debug_screenshot))
        return False

    def _click_publish_button(self, page, title, title_filled, content_filled, debug_screenshot):
        """点击发布按钮并验证发布结果。"""
        # 先滚动到页面底部，确保发布按钮在视口内
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

        # 截图记录点击前的页面状态
        page.screenshot(path=str(debug_screenshot))
        logger.debug(f"点击发布前截图: {debug_screenshot}")

        # 精确找到表单底部的「发布」按钮
        # 从截图可知：底部有"暂存离开"和红色"发布"两个按钮
        btn = page.locator('button:text-is("发布")')
        if btn.count() == 0:
            btn = page.get_by_role("button", name="发布", exact=True)

        if btn.count() == 0:
            page.screenshot(path=str(debug_screenshot))
            raise XHSClientError(f"未找到发布按钮。请检查 {debug_screenshot}")

        # 可能有多个匹配，取页面最下方那个（表单提交按钮）
        target_btn = btn.last
        try:
            target_btn.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass

        before_url = page.url
        target_btn.click(force=True)
        logger.info("已点击发布按钮，等待页面响应...")

        # 等待页面跳转（发布成功会离开当前页面）
        try:
            page.wait_for_url(
                lambda url: "publish/publish" not in url,
                timeout=15000,
            )
            current_url = page.url
            logger.info(f"✅ 页面已跳转到: {current_url} — 发布成功!")
            page.screenshot(path=str(debug_screenshot))
            return
        except Exception:
            pass

        # 页面没有跳转，检查是否有错误提示
        time.sleep(3)
        page.screenshot(path=str(debug_screenshot))
        logger.warning(f"点击发布后页面未跳转，检查错误...")

        # 检查页面上的错误提示
        error_info = page.evaluate("""() => {
            const msgs = [];
            // 检查常见错误提示元素
            document.querySelectorAll(
                '[class*="toast"], [class*="error"], [class*="tip"], ' +
                '[class*="warn"], [class*="message"], [class*="notice"]'
            ).forEach(el => {
                const text = el.textContent.trim();
                if (text && text.length < 100) msgs.push(text);
            });
            return msgs;
        }""")
        if error_info:
            logger.warning(f"页面提示信息: {error_info}")

        # 检查标题是否超长
        title_warning = page.locator('text=/标题.*20/')
        if title_warning.count() > 0:
            logger.error("❌ 标题超过20字限制！请缩短标题")
            raise XHSClientError("标题超过小红书20字限制，发布被阻止")

        # 再试一次：可能第一次点击被弹窗拦截了，关闭弹窗后重试
        logger.info("尝试重新点击发布按钮...")
        page.keyboard.press("Escape")
        time.sleep(1)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

        try:
            target_btn = page.locator('button:text-is("发布")').last
            target_btn.click(force=True)
            logger.info("已重新点击发布按钮...")
        except Exception as e:
            logger.warning(f"重新点击失败: {e}")

        # 再次等待跳转
        try:
            page.wait_for_url(
                lambda url: "publish/publish" not in url,
                timeout=15000,
            )
            logger.info(f"✅ 重试后发布成功! 跳转到: {page.url}")
            page.screenshot(path=str(debug_screenshot))
            return
        except Exception:
            pass

        page.screenshot(path=str(debug_screenshot))
        logger.warning(
            f"发布可能未成功。标题{'✓' if title_filled else '✗'}，"
            f"正文{'✓' if content_filled else '✗'}。"
            f"请检查截图: {debug_screenshot}"
        )

    def _find_image_file_input(self, page, debug_screenshot):
        """在图文标签页找到图片上传的 file input。"""
        all_inputs = page.locator('input[type="file"]')
        try:
            all_inputs.first.wait_for(state="attached", timeout=10000)
        except Exception:
            # 可能需要点击上传区域来触发 input 渲染
            upload_area = page.locator(
                '[class*="upload"], [class*="drag"], [class*="add-image"]'
            )
            if upload_area.count() > 0:
                upload_area.first.click()
                time.sleep(2)
            try:
                all_inputs.first.wait_for(state="attached", timeout=5000)
            except Exception:
                page.screenshot(path=str(debug_screenshot))
                raise XHSClientError(
                    f"未找到 file input。请检查 {debug_screenshot}"
                )

        count = all_inputs.count()
        logger.debug(f"找到 {count} 个 file input")

        # 列出所有 input 的 accept 属性
        for i in range(count):
            accept = all_inputs.nth(i).get_attribute("accept") or "(无)"
            logger.debug(f"  input #{i}: accept={accept}")

        # 优先找 accept 包含图片格式的（排除含视频格式的）
        video_exts = [".mp4", ".mov", ".flv", ".avi", ".mkv", ".wmv", "video/"]
        for i in range(count):
            inp = all_inputs.nth(i)
            accept = (inp.get_attribute("accept") or "").lower()
            if any(v in accept for v in video_exts):
                continue
            if any(img in accept for img in ["image", ".jpg", ".png", ".jpeg", ".webp", ".gif"]):
                logger.info(f"找到图片 file input #{i} (accept={accept})")
                return inp

        # 找不到带图片 accept 的，取第一个非视频的
        for i in range(count):
            inp = all_inputs.nth(i)
            accept = (inp.get_attribute("accept") or "").lower()
            if any(v in accept for v in video_exts):
                continue
            logger.info(f"使用 file input #{i} (accept={accept})")
            return inp

        # 全部都是视频的，仍然返回最后一个
        if count > 0:
            logger.warning("所有 file input 都可能是视频用的，尝试使用最后一个")
            return all_inputs.nth(count - 1)

        raise XHSClientError(f"未找到 file input。请检查 {debug_screenshot}")

    def _add_tags(self, tags: list[str]):
        """在正文区域添加话题标签。"""
        page = self._page
        try:
            tag_input = page.locator(
                '#post-textarea, '
                '[contenteditable="true"].ql-editor, '
                'div[contenteditable="true"]'
            )
            if tag_input.count() > 0:
                tag_input.first.click()
                for tag in tags[:5]:
                    clean_tag = tag.lstrip("#")
                    tag_input.first.press("Enter")
                    tag_input.first.type(f"#{clean_tag} ", delay=50)
                    time.sleep(0.8)

                    suggestion = page.locator(
                        f'[class*="tag-item"]:has-text("{clean_tag}"), '
                        f'[class*="topic"]:has-text("{clean_tag}")'
                    )
                    if suggestion.count() > 0:
                        suggestion.first.click()
                        time.sleep(0.3)
        except Exception as e:
            logger.warning(f"添加标签时出错: {e}")

    # ------------------------------------------------------------------
    # Browse
    # ------------------------------------------------------------------

    def browse_notes(
        self,
        keyword: str = "",
        count: int = 20,
    ) -> list[dict]:
        """浏览小红书笔记。可搜索关键词或浏览推荐。"""
        if not self._page:
            raise XHSClientError("浏览器未启动，请先调用 login()")

        page = self._page

        if keyword:
            url = f"{XHS_URL}/search_result?keyword={quote(keyword)}&source=web_search_result_notes"
            page.goto(url, wait_until="domcontentloaded")
        else:
            page.goto(f"{XHS_URL}/explore", wait_until="domcontentloaded")

        time.sleep(4)

        for _ in range(3):
            page.mouse.wheel(0, 800)
            time.sleep(1)

        notes = []
        note_cards = page.locator(
            'section.note-item, '
            '[class*="note-item"], '
            'a[href*="/explore/"]'
        )
        card_count = min(note_cards.count(), count)

        for i in range(card_count):
            try:
                card = note_cards.nth(i)
                note = self._parse_note_card(card)
                if note and note.get("id"):
                    notes.append(note)
            except Exception as e:
                logger.debug(f"解析笔记卡片 {i} 失败: {e}")

        logger.info(f"浏览到 {len(notes)} 篇笔记")
        return notes

    def _parse_note_card(self, card) -> dict:
        """从笔记卡片元素中提取信息。"""
        note: dict = {"id": "", "title": "", "author": "", "likes": "0", "url": ""}

        try:
            links = card.locator("a")
            for j in range(links.count()):
                href = links.nth(j).get_attribute("href") or ""
                match = re.search(r"/explore/([a-f0-9]{24})", href)
                if match:
                    note["id"] = match.group(1)
                    note["url"] = f"{XHS_URL}/explore/{note['id']}"
                    break
        except Exception:
            pass

        try:
            title_el = card.locator('[class*="title"], .title, span.title')
            if title_el.count() > 0:
                note["title"] = title_el.first.inner_text().strip()[:60]
        except Exception:
            pass

        try:
            author_el = card.locator('[class*="author"], .author, [class*="name"]')
            if author_el.count() > 0:
                note["author"] = author_el.first.inner_text().strip()
        except Exception:
            pass

        try:
            like_el = card.locator('[class*="like"], .like-wrapper span, [class*="count"]')
            if like_el.count() > 0:
                text = like_el.first.inner_text().strip()
                if text:
                    note["likes"] = text
        except Exception:
            pass

        return note

    # ------------------------------------------------------------------
    # Like
    # ------------------------------------------------------------------

    def like_note(self, note_id_or_url: str) -> dict:
        """给笔记点赞。"""
        if not self._page:
            raise XHSClientError("浏览器未启动")

        url = self._normalize_note_url(note_id_or_url)
        page = self._page
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(3)

        like_btn = page.locator(
            '[class*="like-wrapper"] [class*="like-icon"], '
            '[class*="like-wrapper"]:not([class*="active"]), '
            'span[class*="like-icon"], '
            '.engage-bar .like, '
            '[data-type="like"]'
        )
        if like_btn.count() > 0:
            like_btn.first.click()
            time.sleep(1)
            self._save_cookies()
            logger.info(f"❤️  已点赞: {url}")
            return {"liked": True, "note_id": self._extract_note_id(url)}

        like_container = page.locator('[class*="like"]')
        if like_container.count() > 0:
            like_container.first.click()
            time.sleep(1)
            self._save_cookies()
            logger.info(f"❤️  已点赞: {url}")
            return {"liked": True, "note_id": self._extract_note_id(url)}

        raise XHSClientError(f"未找到点赞按钮: {url}")

    # ------------------------------------------------------------------
    # Comment
    # ------------------------------------------------------------------

    def comment_on_note(self, note_id_or_url: str, content: str) -> dict:
        """给笔记发表评论。"""
        if not self._page:
            raise XHSClientError("浏览器未启动")

        url = self._normalize_note_url(note_id_or_url)
        page = self._page

        if page.url != url:
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(3)

        comment_input = page.locator(
            '#content-textarea, '
            '[placeholder*="评论"], '
            '[placeholder*="说点什么"], '
            'textarea[class*="comment"], '
            '.comment-input'
        )

        if comment_input.count() > 0:
            comment_input.first.click()
            time.sleep(0.5)
            comment_input.first.fill(content[:500])
            time.sleep(0.5)

            submit_btn = page.locator(
                'button:has-text("发送"), '
                '[class*="submit"]:has-text("发送"), '
                'button.comment-btn'
            )
            if submit_btn.count() > 0:
                submit_btn.first.click()
                time.sleep(2)
                self._save_cookies()
                logger.info(f"💬 已评论: {url}")
                return {"commented": True, "note_id": self._extract_note_id(url)}

        raise XHSClientError(f"未找到评论输入框: {url}")

    # ------------------------------------------------------------------
    # Get note detail
    # ------------------------------------------------------------------

    def get_note_detail(self, note_id_or_url: str) -> dict:
        """获取笔记详情（标题、正文、点赞数等）。"""
        if not self._page:
            raise XHSClientError("浏览器未启动")

        url = self._normalize_note_url(note_id_or_url)
        page = self._page
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(3)

        detail: dict = {
            "id": self._extract_note_id(url),
            "url": url,
            "title": "",
            "content": "",
            "author": "",
            "likes": "0",
        }

        try:
            title_el = page.locator('#detail-title, [class*="title"], .title')
            if title_el.count() > 0:
                detail["title"] = title_el.first.inner_text().strip()
        except Exception:
            pass

        try:
            content_el = page.locator('#detail-desc, [class*="desc"], .content, .note-text')
            if content_el.count() > 0:
                detail["content"] = content_el.first.inner_text().strip()
        except Exception:
            pass

        try:
            author_el = page.locator('[class*="author"] .username, [class*="user-name"]')
            if author_el.count() > 0:
                detail["author"] = author_el.first.inner_text().strip()
        except Exception:
            pass

        try:
            like_el = page.locator('[class*="like-wrapper"] span[class*="count"], [class*="like"] .count')
            if like_el.count() > 0:
                detail["likes"] = like_el.first.inner_text().strip()
        except Exception:
            pass

        # 提取当前笔记的轮播图片 URL
        detail["image_urls"] = self._extract_note_images(page)

        return detail

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_note_images(self, page) -> list[str]:
        """从笔记详情页精确提取当前笔记的轮播图片 URL。

        使用 JS 在笔记主容器内查找，避免匹配到推荐笔记等无关图片。
        """
        try:
            urls = page.evaluate("""() => {
                const urls = [];
                const seen = new Set();

                // 策略1: 在笔记主容器内查找轮播图片
                const containers = [
                    document.querySelector('.note-detail-mask'),
                    document.querySelector('#noteContainer'),
                    document.querySelector('[class*="note-detail"]'),
                    document.querySelector('[class*="note-container"]'),
                    document.querySelector('.main-container'),
                ];
                let root = null;
                for (const c of containers) {
                    if (c) { root = c; break; }
                }

                // 策略2: 在根容器内找 swiper/carousel 的图片
                const searchRoot = root || document;
                const swiperImgs = searchRoot.querySelectorAll(
                    '.swiper-slide img, [class*="carousel-item"] img, [class*="slider"] img'
                );
                for (const img of swiperImgs) {
                    const src = img.src || img.getAttribute('src') || '';
                    if (src && src.startsWith('http') && !seen.has(src)) {
                        // 过滤掉缩略图(通常URL带thumbnail)和非内容图(avatar/icon/logo)
                        if (!/avatar|icon|logo|emoji|loading/i.test(src)) {
                            seen.add(src);
                            urls.push(src);
                        }
                    }
                }

                // 策略3: 如果swiper没找到，在根容器内找大图
                if (urls.length === 0 && root) {
                    const allImgs = root.querySelectorAll('img[src]');
                    for (const img of allImgs) {
                        const src = img.src || '';
                        if (!src || !src.startsWith('http') || seen.has(src)) continue;
                        if (/avatar|icon|logo|emoji|loading|qrcode/i.test(src)) continue;

                        // 只要宽度 > 200 的图片（排除小图标）
                        const w = img.naturalWidth || img.width || 0;
                        if (w > 0 && w < 200) continue;

                        seen.add(src);
                        urls.push(src);
                        if (urls.length >= 9) break;
                    }
                }

                return urls;
            }""")
            return urls or []
        except Exception:
            return []

    def _normalize_note_url(self, note_id_or_url: str) -> str:
        if note_id_or_url.startswith("http"):
            return note_id_or_url
        return f"{XHS_URL}/explore/{note_id_or_url}"

    def _extract_note_id(self, url: str) -> str:
        match = re.search(r"/explore/([a-f0-9]{24})", url)
        return match.group(1) if match else url

    def close(self):
        """关闭浏览器并释放资源。"""
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._pw = None
