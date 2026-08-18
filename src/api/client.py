import httpx
import time
import random
from typing import Optional, Dict

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://live.bilibili.com/",
    "Origin": "https://live.bilibili.com",
}

_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
_RETRY_BACKOFF = [0.5, 1.5, 4.0]


def random_ua() -> str:
    return random.choice(_UA_POOL)


class BiliApiError(Exception):
    def __init__(self, code: int, message: str, raw: Optional[dict] = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.raw = raw


class BiliNetworkError(Exception):
    pass


def parse_json(resp: httpx.Response) -> dict:
    if resp.status_code >= 400:
        raise BiliNetworkError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except Exception as e:
        raise BiliNetworkError(f"非 JSON 响应: {resp.text[:200]}") from e


class BiliClient:
    def __init__(self, cookies: Optional[Dict[str, str]] = None):
        headers = DEFAULT_HEADERS.copy()
        headers["User-Agent"] = random_ua()
        self.session = httpx.Client(
            headers=headers, timeout=_TIMEOUT, follow_redirects=True,
        )
        if cookies:
            for key, value in cookies.items():
                self.session.cookies.set(key, value, domain=".bilibili.com")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _request(self, method: str, url: str, *, retryable: bool,
                 params=None, data=None, **kwargs) -> httpx.Response:
        last_exc = None
        attempts = len(_RETRY_BACKOFF) if retryable else 1
        for i in range(attempts):
            try:
                if method == "GET":
                    return self.session.get(url, params=params, **kwargs)
                return self.session.post(url, data=data, **kwargs)
            except (httpx.TransportError, httpx.RemoteProtocolError) as e:
                last_exc = e
                if not retryable or i == attempts - 1:
                    raise BiliNetworkError(f"请求失败: {e}") from e
                time.sleep(_RETRY_BACKOFF[i])
            except httpx.HTTPStatusError as e:
                last_exc = e
                if not retryable or i == attempts - 1 or e.response.status_code < 500:
                    raise BiliNetworkError(f"HTTP {e.response.status_code}") from e
                time.sleep(_RETRY_BACKOFF[i])
        raise BiliNetworkError(f"请求失败: {last_exc}")

    def get(self, url: str, params: Optional[Dict] = None, **kwargs) -> httpx.Response:
        return self._request("GET", url, retryable=True, params=params, **kwargs)

    def post(self, url: str, data: Optional[Dict] = None, **kwargs) -> httpx.Response:
        return self._request("POST", url, retryable=False, data=data, **kwargs)

    def get_cookies(self) -> Dict[str, str]:
        return dict(self.session.cookies)

    def get_cookie(self, name: str) -> Optional[str]:
        return self.session.cookies.get(name)

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass

    @staticmethod
    def make_rnd() -> int:
        return int(time.time() * 1000)