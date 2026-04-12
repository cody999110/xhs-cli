"""从本地 Chrome 浏览器读取小红书相关 Cookie。

macOS 上 Chrome 将 Cookie 保存在 SQLite 数据库中，值使用 Keychain 中的
密钥通过 PBKDF2 + AES-128-CBC 加密（v10 格式）。

这样只要你在 Chrome 里已经登录了小红书，就不用每次在 CLI 里重新扫码。
"""

from __future__ import annotations

import json
import platform
import shutil
import sqlite3
import subprocess
import tempfile
from hashlib import pbkdf2_hmac
from pathlib import Path

from src.utils.logger import logger

# Chrome 默认 profile 下的 Cookies 数据库路径（macOS）
_CHROME_COOKIE_DB = (
    Path.home()
    / "Library/Application Support/Google/Chrome/Default/Cookies"
)

# Chrome 在 macOS Keychain 中存储加密密钥的服务名
_KEYCHAIN_SERVICE = "Chrome Safe Storage"
_KEYCHAIN_ACCOUNT = "Chrome"

# v10 加密参数
_SALT = b"saltysalt"
_ITERATIONS = 1003
_KEY_LEN = 16
_IV = b" " * 16  # 16 字节空格


def _get_chrome_key() -> bytes:
    """从 macOS Keychain 读取 Chrome 的 Cookie 加密密钥。"""
    raw = subprocess.check_output(
        [
            "security",
            "find-generic-password",
            "-w",
            "-s", _KEYCHAIN_SERVICE,
            "-a", _KEYCHAIN_ACCOUNT,
        ],
        stderr=subprocess.DEVNULL,
    )
    password = raw.strip()
    return pbkdf2_hmac("sha1", password, _SALT, _ITERATIONS, dklen=_KEY_LEN)


def _decrypt_v10(key: bytes, encrypted: bytes) -> str:
    """解密 Chrome v10 格式的 Cookie 值 (AES-128-CBC)。

    新版 Chrome 解密后数据前面有 32 字节不可读前缀，
    需要扫描找到实际可读的 cookie 值起始位置。
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    cipher = Cipher(algorithms.AES(key), modes.CBC(_IV))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted) + decryptor.finalize()

    # 去除 PKCS7 padding
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16:
        decrypted = decrypted[:-pad_len]

    # 新版 Chrome 在加密值前有 32 字节二进制前缀，跳过它
    for i in range(len(decrypted)):
        try:
            candidate = decrypted[i:].decode("utf-8")
            if candidate and (candidate.isprintable() or not candidate.startswith("\x00")):
                return candidate
        except UnicodeDecodeError:
            continue

    raise ValueError("无法从解密数据中提取可读值")


def import_chrome_cookies(
    domains: list[str] | None = None,
    cookie_db_path: Path | None = None,
) -> list[dict]:
    """从本地 Chrome 读取指定域名的 Cookie，返回 Playwright 兼容格式。

    Parameters
    ----------
    domains : list[str], optional
        要匹配的域名列表，默认为小红书相关域名。
    cookie_db_path : Path, optional
        Chrome Cookies 数据库路径，默认为系统 Chrome 路径。

    Returns
    -------
    list[dict]
        Playwright 格式的 Cookie 列表。

    Raises
    ------
    FileNotFoundError
        找不到 Chrome Cookies 数据库。
    RuntimeError
        解密失败或不支持的平台。
    """
    if platform.system() != "Darwin":
        raise RuntimeError(
            "Chrome Cookie 自动导入目前仅支持 macOS。"
            "其他系统请手动导出 Cookie 或使用扫码登录。"
        )

    db_path = cookie_db_path or _CHROME_COOKIE_DB
    if not db_path.exists():
        raise FileNotFoundError(
            f"未找到 Chrome Cookies 数据库: {db_path}\n"
            "请确认已安装 Google Chrome 并至少打开过一次。"
        )

    if domains is None:
        domains = [".xiaohongshu.com", "xiaohongshu.com"]

    # Chrome 运行时会锁定数据库，复制到临时文件再读取
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        shutil.copy2(db_path, tmp_path)

        # 获取解密密钥
        key = _get_chrome_key()

        conn = sqlite3.connect(str(tmp_path))
        placeholders = " OR ".join(["host_key LIKE ?"] * len(domains))
        params = [f"%{d}%" for d in domains]

        rows = conn.execute(
            f"SELECT name, encrypted_value, host_key, path, "
            f"is_secure, expires_utc, is_httponly "
            f"FROM cookies WHERE {placeholders}",
            params,
        ).fetchall()
        conn.close()

        cookies: list[dict] = []
        for name, enc_value, host_key, path, is_secure, expires_utc, is_httponly in rows:
            value = ""
            if enc_value:
                if enc_value[:3] == b"v10":
                    try:
                        value = _decrypt_v10(key, enc_value[3:])
                    except Exception:
                        logger.debug(f"解密失败: {name}@{host_key}")
                        continue
                else:
                    try:
                        value = enc_value.decode("utf-8", errors="ignore")
                    except Exception:
                        continue

            if not value:
                continue

            # Playwright Cookie 格式
            cookie = {
                "name": name,
                "value": value,
                "domain": host_key,
                "path": path or "/",
                "secure": bool(is_secure),
                "httpOnly": bool(is_httponly),
            }
            # Chrome 的 expires_utc 是从 1601-01-01 开始的微秒数
            # 转换为 Unix timestamp（秒）
            if expires_utc and expires_utc > 0:
                unix_ts = (expires_utc / 1_000_000) - 11644473600
                if unix_ts > 0:
                    cookie["expires"] = unix_ts

            cookies.append(cookie)

        logger.info(f"从 Chrome 导入了 {len(cookies)} 条小红书 Cookie")
        return cookies

    finally:
        tmp_path.unlink(missing_ok=True)


def save_chrome_cookies_to_file(output_path: Path) -> int:
    """从 Chrome 导入 Cookie 并保存到 JSON 文件。

    Returns
    -------
    int
        导入的 Cookie 数量。
    """
    cookies = import_chrome_cookies()
    if not cookies:
        logger.warning("Chrome 中未找到小红书 Cookie，请先在 Chrome 里登录小红书")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(cookies, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Cookie 已保存到 {output_path}")
    return len(cookies)
