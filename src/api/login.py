import time
from enum import Enum
from typing import Optional
import qrcode

from src.api.client import BiliClient, parse_json, BiliApiError

_QRCODE_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_QRCODE_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"

# poll 接口 code 含义
_POLL_WAITING = 86101   # 未扫码
_POLL_SCANNED = 86090   # 已扫码未确认
_POLL_EXPIRED = 86038   # 二维码已过期
_POLL_SUCCESS = 0


class QrStatus(Enum):
    WAITING = "waiting"
    SCANNED = "scanned"
    EXPIRED = "expired"
    SUCCESS = "success"
    UNKNOWN = "unknown"


class QrLogin:
    """命令行二维码扫码登录。成功后返回全部 cookie dict。"""

    def __init__(self):
        self.client = BiliClient()
        self.qrcode_key: Optional[str] = None
        self.qr_url: Optional[str] = None

    def generate(self) -> str:
        """生成二维码，返回二维码 URL，并在终端打印 ASCII 二维码。"""
        resp = self.client.get(_QRCODE_GENERATE, params={"source": "main-fe-header"})
        data = parse_json(resp)
        if data.get("code") != 0:
            raise BiliApiError(data.get("code", -1),
                               data.get("message", "生成二维码失败"), data)
        body = data.get("data", {}) or {}
        self.qrcode_key = body.get("qrcode_key")
        self.qr_url = body.get("url")
        if not self.qrcode_key or not self.qr_url:
            raise BiliApiError(-1, "二维码响应缺少字段", data)
        self._print_ascii_qr(self.qr_url)
        return self.qr_url

    def _print_ascii_qr(self, url: str) -> None:
        """在终端打印 ASCII 二维码。"""
        qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
        qr.add_data(url)
        qr.make(fit=True)
        print("\n请用哔哩哔哩 APP 扫描下方二维码登录：\n")
        qr.print_ascii(invert=True)
        print()

    def _parse_status(self, resp) -> tuple:
        """解析 poll 响应，返回 (QrStatus, message)。
        B 站 poll 接口外层 code 恒为 0，真实状态在内层 data.code。"""
        data = parse_json(resp)
        inner = data.get("data", {}) or {}
        code = inner.get("code", -1)
        msg = inner.get("message", "") or data.get("message", "")
        if code == _POLL_SUCCESS:
            return QrStatus.SUCCESS, msg
        if code == _POLL_WAITING:
            return QrStatus.WAITING, "等待扫码"
        if code == _POLL_SCANNED:
            return QrStatus.SCANNED, "已扫码，请在手机确认"
        if code == _POLL_EXPIRED:
            return QrStatus.EXPIRED, "二维码已过期"
        return QrStatus.UNKNOWN, f"未知状态 code={code}"

    def poll_once(self) -> tuple:
        """轮询一次，返回 (QrStatus, cookies_or_None, message)。
        成功时合并 set-cookie 头与 body url 查询参数两处 cookie。"""
        if not self.qrcode_key:
            raise BiliApiError(-1, "请先调用 generate()", None)
        resp = self.client.get(_QRCODE_POLL, params={
            "qrcode_key": self.qrcode_key, "source": "main-fe-header",
        })
        data = parse_json(resp)
        status, msg = self._parse_status(resp)
        cookies = None
        if status == QrStatus.SUCCESS:
            cookies = {}
            # 1. 从 set-cookie 头提取
            set_cookies = resp.headers.get_list("set-cookie")
            cookies.update(parse_login_cookies(set_cookies))
            # 2. 从 body 的 url 查询参数补充（DedeUserID 等常在此）
            url = data.get("data", {}).get("url", "")
            if url:
                cookies.update(_parse_cookies_from_url(url))
        return status, cookies, msg

    def wait_for_login(self, timeout: int = 180, interval: float = 2.0) -> dict:
        """阻塞轮询直到登录成功或过期/超时。成功返回 cookie dict。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            status, cookies, msg = self.poll_once()
            if status == QrStatus.SUCCESS:
                return cookies
            if status == QrStatus.EXPIRED:
                raise BiliApiError(_POLL_EXPIRED, "二维码已过期，请重新运行", None)
            if status == QrStatus.SCANNED:
                print(f"\r{msg}            ", end="", flush=True)
            time.sleep(interval)
        raise BiliApiError(-1, "登录超时", None)

    def close(self):
        self.client.close()


def parse_login_cookies(set_cookie_list) -> dict:
    """从 set-cookie 头列表解析出 cookie dict（取每条的 name=value 部分）。"""
    cookies = {}
    for raw in set_cookie_list:
        # 形如 "SESSDATA=abc; Path=/; Domain=.bilibili.com"
        pair = raw.split(";", 1)[0].strip()
        if "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            cookies[name] = value
    return cookies


def _parse_cookies_from_url(url: str) -> dict:
    """从 crossDomain URL 的查询参数提取 cookie（DedeUserID/SESSDATA/bili_jct 等）。"""
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    cookies = {}
    for key, vals in qs.items():
        if vals:
            cookies[key] = vals[0]
    return cookies


def extract_dede_uid(cookies: dict) -> int:
    """从 cookie dict 取 DedeUserID 转 int，缺失返回 0。"""
    try:
        return int(cookies.get("DedeUserID", 0) or 0)
    except (ValueError, TypeError):
        return 0