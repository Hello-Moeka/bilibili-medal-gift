# 粉丝团灯牌自动赠送工具 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 单账号命令行工具，给 B 站关注列表里正在直播中的主播各送 1 个粉丝团灯牌（gift_id=31164，sendGold），当日去重不重送，余额不足即停。

**Architecture:** Python + httpx 独立轻量项目。`main.py` 编排：加载 .env cookie → 翻页取在播 → 查当日记录去重 → 逐个送礼 → 记录结果 → 汇总。模块按职责分 `api/client`、`api/follow`、`api/gift`、`storage/sent_log`，互不耦合，通过明确接口通信。

**Tech Stack:** Python 3.10+、httpx（HTTP）、python-dotenv（.env 加载）、pytest（测试）、标准库 json/time/random/argparse/os。

## Global Constraints

- 平台：Windows，Python 3.10+
- 依赖：`httpx>=0.27.0`、`python-dotenv>=1.0.0`、`pytest>=8.0.0`（仅测试）
- 灯牌：付费 `gift_id=31164`，走 `sendGold`，price 动态取不硬编码
- 在播判定：仅 `live_status==1`，轮播(2)跳过
- 去重：只跳当日 `status==success` 的，失败当日可重试
- 间隔：每个主播之间随机 0.5–1.5 秒
- cookie 放项目根 `.env`，被 `.gitignore` 排除
- 记录文件 `sent_log.json` 原子写（.tmp + os.replace）
- 错误处理：余额不足→立即停止；普通失败→继续；连续 3 次鉴权失败→停止防呆
- B 站 API：`GetWebList` 翻页取在播；`sendGold` 送礼；`giftConfig` 取价

---

## File Structure

| 文件 | 职责 |
|---|---|
| `requirements.txt` | 运行依赖：httpx、python-dotenv |
| `.env.example` | cookie 配置模板 |
| `.gitignore` | 排除 .env、sent_log.json、__pycache__、.venv |
| `main.py` | 入口：argparse 参数、编排主流程、汇总打印 |
| `src/__init__.py` | 包标记 |
| `src/api/__init__.py` | 包标记 |
| `src/api/client.py` | BiliClient：httpx 会话、UA 池、重试、cookie 加载、CSRF 取值、parse_json |
| `src/api/follow.py` | `get_live_follows(client)` 翻页取在播主播列表 |
| `src/api/gift.py` | `get_medal_gift_price(client)` 取价 + `send_medal_gift(client, ...)` 送礼 |
| `src/storage/__init__.py` | 包标记 |
| `src/storage/sent_log.py` | `load_sent()` / `is_sent_today(uid)` / `mark_sent(...)`，原子写 |
| `tests/__init__.py` | 包标记 |
| `tests/conftest.py` | pytest 公共夹具 |
| `tests/test_sent_log.py` | 记录层测试 |
| `tests/test_follow.py` | 翻页停止逻辑测试 |
| `tests/test_gift.py` | 取价 + 送礼 + 错误识别测试 |

---

### Task 1: 项目脚手架与依赖

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/__init__.py`
- Create: `src/api/__init__.py`
- Create: `src/storage/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: 无
- Produces: 项目目录结构与依赖声明，后续任务在此之上构建

- [ ] **Step 1: 创建 requirements.txt**

```
httpx>=0.27.0
python-dotenv>=1.0.0
```

- [ ] **Step 2: 创建 .env.example**

```env
SESSDATA=你的SESSDATA
bili_jct=你的bili_jct
DedeUserID=你的UID
```

- [ ] **Step 3: 创建 .gitignore**

```gitignore
.env
sent_log.json
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
```

- [ ] **Step 4: 创建包标记文件**

`src/__init__.py`、`src/api/__init__.py`、`src/storage/__init__.py`、`tests/__init__.py` 四个文件，内容均为空。

- [ ] **Step 5: 创建 tests/conftest.py**

```python
import os
import sys
import pytest

# 让测试能 import src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_log_file(tmp_path):
    """提供一个临时 sent_log.json 路径，测试间互不干扰。"""
    return str(tmp_path / "sent_log.json")
```

- [ ] **Step 6: 安装依赖并验证**

Run: `pip install -r requirements.txt pytest`
Expected: 安装成功无报错

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example .gitignore src/ tests/conftest.py tests/__init__.py
git commit -m "chore: 项目脚手架与依赖"
```

---

### Task 2: BiliClient 网络层

**Files:**
- Create: `src/api/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `BiliClient(cookies: dict[str, str] | None = None)` — 构造，cookies 设置到 .bilibili.com 域
  - `BiliClient.get(url, params=None) -> httpx.Response` — GET，可重试
  - `BiliClient.post(url, data=None) -> httpx.Response` — POST，不重试
  - `BiliClient.get_cookie(name) -> str | None`
  - `BiliClient.close()`
  - `BiliClient.make_rnd() -> int` — 静态方法，毫秒时间戳
  - `parse_json(resp: httpx.Response) -> dict` — 解析 JSON，非 JSON 或 HTTP 错误抛 BiliNetworkError
  - `BiliApiError(code: int, message: str, raw: dict | None)`
  - `BiliNetworkError`

- [ ] **Step 1: 写失败测试 tests/test_client.py**

```python
import httpx
import pytest
from src.api.client import BiliClient, parse_json, BiliNetworkError


def test_client_sets_cookies():
    client = BiliClient(cookies={"SESSDATA": "abc", "bili_jct": "xyz"})
    assert client.get_cookie("SESSDATA") == "abc"
    assert client.get_cookie("bili_jct") == "xyz"
    client.close()


def test_get_cookie_missing_returns_none():
    client = BiliClient()
    assert client.get_cookie("nope") is None
    client.close()


def test_make_rnd_is_ms_timestamp():
    import time
    rnd = BiliClient.make_rnd()
    now = int(time.time() * 1000)
    assert abs(rnd - now) < 2000  # 2 秒容差


def test_parse_json_valid():
    resp = httpx.Response(200, json={"code": 0, "data": {"ok": True}})
    assert parse_json(resp) == {"code": 0, "data": {"ok": True}}


def test_parse_json_non_json_raises():
    resp = httpx.Response(200, text="not json")
    with pytest.raises(BiliNetworkError):
        parse_json(resp)


def test_parse_json_http_error_raises():
    resp = httpx.Response(500, text="server error")
    with pytest.raises(BiliNetworkError):
        parse_json(resp)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.api.client'`

- [ ] **Step 3: 实现 src/api/client.py**

```python
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
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise BiliNetworkError(f"HTTP {resp.status_code}: {resp.text[:200]}") from e
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_client.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/api/client.py tests/test_client.py
git commit -m "feat: BiliClient 网络层"
```

---

### Task 3: 本地记录与去重（sent_log）

**Files:**
- Create: `src/storage/sent_log.py`
- Test: `tests/test_sent_log.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `today_str() -> str` — 本地日期 `YYYY-MM-DD`
  - `load_sent(path: str) -> dict` — 加载整个记录，文件不存在返回 `{}`
  - `is_sent_today(path: str, uid: int) -> bool` — 当日组存在该 uid 且 `status=="success"` 才返回 True
  - `mark_sent(path: str, uid: int, uname: str, room_id: int, status: str, error: str = "") -> None` — 写入当日组，含 `sent_at` 时间戳，原子写

- [ ] **Step 1: 写失败测试 tests/test_sent_log.py**

```python
import json
import os
import time
from src.storage.sent_log import (
    today_str, load_sent, is_sent_today, mark_sent,
)


def test_today_str_format():
    s = today_str()
    assert len(s) == 10
    assert s[4] == "-" and s[7] == "-"


def test_load_sent_missing_file_returns_empty(tmp_log_file):
    assert load_sent(tmp_log_file) == {}


def test_mark_sent_success_then_is_sent_today(tmp_log_file):
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="success")
    assert is_sent_today(tmp_log_file, 12345) is True


def test_mark_sent_fail_not_treated_as_sent(tmp_log_file):
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="fail", error="余额不足")
    # 失败当日可重试，不算已送
    assert is_sent_today(tmp_log_file, 12345) is False


def test_mark_sent_writes_fields(tmp_log_file):
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="success")
    data = load_sent(tmp_log_file)
    today = today_str()
    assert today in data
    rec = data[today]["12345"]
    assert rec["uname"] == "主播A"
    assert rec["room_id"] == 67890
    assert rec["status"] == "success"
    assert "sent_at" in rec
    assert rec["sent_at"].startswith(today)


def test_mark_sent_overwrites_same_uid_same_day(tmp_log_file):
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="fail", error="x")
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="success")
    # 第二次成功后应视为已送
    assert is_sent_today(tmp_log_file, 12345) is True


def test_is_sent_today_other_uid_not_affected(tmp_log_file):
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="success")
    assert is_sent_today(tmp_log_file, 99999) is False


def test_load_sent_handles_corrupt_file(tmp_log_file):
    with open(tmp_log_file, "w", encoding="utf-8") as f:
        f.write("{not valid json")
    # 损坏文件返回空，不抛异常
    assert load_sent(tmp_log_file) == {}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_sent_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.storage.sent_log'`

- [ ] **Step 3: 实现 src/storage/sent_log.py**

```python
import json
import os
import time
import threading

_lock = threading.RLock()


def today_str() -> str:
    return time.strftime("%Y-%m-%d")


def load_sent(path: str) -> dict:
    """加载整个记录。文件不存在或损坏返回 {}。"""
    with _lock:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}


def is_sent_today(path: str, uid: int) -> bool:
    """当日组存在该 uid 且 status==success 才返回 True（失败可重试）。"""
    with _lock:
        data = load_sent(path)
        today = today_str()
        rec = data.get(today, {}).get(str(uid))
        return rec is not None and rec.get("status") == "success"


def mark_sent(path: str, uid: int, uname: str, room_id: int,
              status: str, error: str = "") -> None:
    """写入当日组，含 sent_at 时间戳，原子写。"""
    with _lock:
        data = load_sent(path)
        today = today_str()
        if today not in data:
            data[today] = {}
        record = {
            "uname": uname,
            "room_id": room_id,
            "sent_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
        }
        if error:
            record["error"] = error
        data[today][str(uid)] = record
        _atomic_write(path, data)


def _atomic_write(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_sent_log.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/storage/sent_log.py tests/test_sent_log.py
git commit -m "feat: 本地记录与去重（按日期分组、原子写、只跳成功）"
```

---

### Task 4: 在播主播翻页（follow）

**Files:**
- Create: `src/api/follow.py`
- Test: `tests/test_follow.py`

**Interfaces:**
- Consumes: `src.api.client.BiliClient`, `parse_json`
- Produces:
  - `get_live_follows(client: BiliClient) -> list[dict]` — 返回在播主播列表，每项 `{"uid": int, "uname": str, "room_id": int}`。从 page=1 起翻，遇首个 `live_status!=1` 停止；`code!=0` 抛 `BiliApiError`

- [ ] **Step 1: 写失败测试 tests/test_follow.py**

```python
import httpx
import pytest
from unittest.mock import MagicMock
from src.api.follow import get_live_follows
from src.api.client import BiliApiError


def _mock_client(pages_responses):
    """pages_responses: list of dict，每个是一页的完整 JSON 响应体。"""
    client = MagicMock()
    client.get = MagicMock(side_effect=[
        httpx.Response(200, json=body) for body in pages_responses
    ])
    return client


def test_single_page_all_live():
    client = _mock_client([{
        "code": 0, "data": {"rooms": [
            {"uid": 1, "uname": "A", "room_id": 10, "live_status": 1},
            {"uid": 2, "uname": "B", "room_id": 20, "live_status": 1},
        ], "count": 2}
    }])
    result = get_live_follows(client)
    assert result == [
        {"uid": 1, "uname": "A", "room_id": 10},
        {"uid": 2, "uname": "B", "room_id": 20},
    ]


def test_stops_at_first_not_live():
    # 第1页：1个直播中 + 1个未开播 → 停在未开播，不翻第2页
    client = _mock_client([{
        "code": 0, "data": {"rooms": [
            {"uid": 1, "uname": "A", "room_id": 10, "live_status": 1},
            {"uid": 2, "uname": "B", "room_id": 20, "live_status": 0},
        ], "count": 2}
    }])
    result = get_live_follows(client)
    assert result == [{"uid": 1, "uname": "A", "room_id": 10}]


def test_paginates_until_not_live():
    # 第1页全直播中，第2页出现未开播 → 停
    client = _mock_client([
        {"code": 0, "data": {"rooms": [
            {"uid": 1, "uname": "A", "room_id": 10, "live_status": 1},
            {"uid": 2, "uname": "B", "room_id": 20, "live_status": 1},
        ], "count": 3}},
        {"code": 0, "data": {"rooms": [
            {"uid": 3, "uname": "C", "room_id": 30, "live_status": 0},
        ], "count": 3}},
    ])
    result = get_live_follows(client)
    assert result == [
        {"uid": 1, "uname": "A", "room_id": 10},
        {"uid": 2, "uname": "B", "room_id": 20},
    ]


def test_skips_round_status_2_but_keeps_scanning():
    # 轮播(2)跳过，但不停翻页；遇到未开播(0)才停
    client = _mock_client([{
        "code": 0, "data": {"rooms": [
            {"uid": 1, "uname": "A", "room_id": 10, "live_status": 1},
            {"uid": 2, "uname": "B", "room_id": 20, "live_status": 2},
            {"uid": 3, "uname": "C", "room_id": 30, "live_status": 0},
        ], "count": 3}
    }])
    result = get_live_follows(client)
    assert result == [{"uid": 1, "uname": "A", "room_id": 10}]


def test_empty_rooms():
    client = _mock_client([{"code": 0, "data": {"rooms": [], "count": 0}}])
    assert get_live_follows(client) == []


def test_api_error_raises():
    client = _mock_client([{"code": 1, "message": "参数错误", "data": {}}])
    with pytest.raises(BiliApiError):
        get_live_follows(client)


def test_stops_when_no_more_pages():
    # rooms 为空表示无更多数据，停止
    client = _mock_client([
        {"code": 0, "data": {"rooms": [
            {"uid": 1, "uname": "A", "room_id": 10, "live_status": 1},
        ], "count": 1}},
        {"code": 0, "data": {"rooms": [], "count": 1}},
    ])
    result = get_live_follows(client)
    assert result == [{"uid": 1, "uname": "A", "room_id": 10}]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_follow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.api.follow'`

- [ ] **Step 3: 实现 src/api/follow.py**

```python
from typing import List
from src.api.client import BiliClient, parse_json, BiliApiError

_GET_WEB_LIST_URL = "https://api.live.bilibili.com/xlive/web-ucenter/v1/xfetter/GetWebList"


def get_live_follows(client: BiliClient) -> List[dict]:
    """翻页取在播主播。page 从 1 起，遇首个 live_status!=1 停止。

    返回列表，每项 {"uid", "uname", "room_id"}。
    仅 live_status==1（直播中）才收入；轮播(2)跳过但不停翻页。
    """
    result = []
    page = 1
    while True:
        resp = client.get(_GET_WEB_LIST_URL, params={"page": page})
        data = parse_json(resp)
        if data.get("code") != 0:
            raise BiliApiError(data.get("code", -1),
                               data.get("message", "未知错误"), data)
        rooms = data.get("data", {}).get("rooms", []) or []
        if not rooms:
            break  # 无更多数据
        has_not_live = False
        for room in rooms:
            live_status = room.get("live_status", 0)
            if live_status != 1:
                # 遇到第一个非直播中（含未开播0、轮播2）→ 停止翻页
                has_not_live = True
                break
            result.append({
                "uid": room.get("uid"),
                "uname": room.get("uname", ""),
                "room_id": room.get("room_id"),
            })
        if has_not_live:
            break
        page += 1
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_follow.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/api/follow.py tests/test_follow.py
git commit -m "feat: 在播主播翻页取列表（遇未开播停止）"
```

---

### Task 5: 灯牌取价与送礼（gift）

**Files:**
- Create: `src/api/gift.py`
- Test: `tests/test_gift.py`

**Interfaces:**
- Consumes: `src.api.client.BiliClient`, `parse_json`, `BiliApiError`
- Produces:
  - `MEDAL_GIFT_ID = 31164`
  - `INSUFFICIENT_BALANCE_KEYWORDS` — 余额不足关键词集合
  - `get_medal_gift_price(client: BiliClient) -> int` — 从 giftConfig 取灯牌 price；找不到抛 `BiliApiError`
  - `send_medal_gift(client: BiliClient, uid: int, ruid: int, room_id: int, price: int) -> dict` — 走 sendGold 送 1 个灯牌，返回 data；非 code==0 抛 `GiftError`（带 code/message/raw）
  - `GiftError(code: int, message: str, raw: dict | None)` — 送礼失败异常
  - `is_insufficient_balance(err: GiftError) -> bool` — 判定是否余额不足

- [ ] **Step 1: 写失败测试 tests/test_gift.py**

```python
import httpx
import pytest
from unittest.mock import MagicMock
from src.api.gift import (
    get_medal_gift_price, send_medal_gift, GiftError,
    is_insufficient_balance, MEDAL_GIFT_ID,
)


def _mock_get_client(json_body):
    client = MagicMock()
    client.get = MagicMock(return_value=httpx.Response(200, json=json_body))
    client.get_cookie = MagicMock(return_value="csrf_token_xxx")
    client.make_rnd = MagicMock(return_value=1700000000000)
    return client


def test_get_price_finds_medal():
    body = {"code": 0, "data": {"list": [
        {"id": 31039, "name": "牛哇牛哇", "price": 100},
        {"id": MEDAL_GIFT_ID, "name": "粉丝团灯牌", "price": 1000},
    ]}}
    client = _mock_get_client(body)
    assert get_medal_gift_price(client) == 1000


def test_get_price_not_found_raises():
    body = {"code": 0, "data": {"list": [
        {"id": 31039, "name": "牛哇牛哇", "price": 100},
    ]}}
    client = _mock_get_client(body)
    with pytest.raises(Exception):
        get_medal_gift_price(client)


def test_send_gift_success():
    # post 返回成功
    client = MagicMock()
    client.get_cookie = MagicMock(return_value="jct_xxx")
    client.make_rnd = MagicMock(return_value=1700000000000)
    client.post = MagicMock(return_value=httpx.Response(200, json={
        "code": 0, "data": {"gift_id": MEDAL_GIFT_ID}
    }))
    result = send_medal_gift(client, uid=100, ruid=200,
                             room_id=999, price=1000)
    assert result["gift_id"] == MEDAL_GIFT_ID
    # 校验 post 调用的 url 和关键字表单字段
    args, kwargs = client.post.call_args
    assert "sendGold" in args[0]
    data = kwargs["data"]
    assert data["gift_id"] == MEDAL_GIFT_ID
    assert data["gift_num"] == 1
    assert data["coin_type"] == "gold"
    assert data["ruid"] == 200
    assert data["biz_id"] == 999
    assert data["csrf"] == "jct_xxx"
    assert data["csrf_token"] == "jct_xxx"
    assert data["price"] == 1000


def test_send_gift_missing_jct_raises():
    client = MagicMock()
    client.get_cookie = MagicMock(return_value=None)
    with pytest.raises(Exception, match="bili_jct"):
        send_medal_gift(client, uid=100, ruid=200, room_id=999, price=1000)


def test_send_gift_api_error_raises_gift_error():
    client = MagicMock()
    client.get_cookie = MagicMock(return_value="jct_xxx")
    client.make_rnd = MagicMock(return_value=1700000000000)
    client.post = MagicMock(return_value=httpx.Response(200, json={
        "code": -403, "message": "账户余额不足"
    }))
    with pytest.raises(GiftError) as exc_info:
        send_medal_gift(client, uid=100, ruid=200, room_id=999, price=1000)
    assert exc_info.value.code == -403


def test_is_insufficient_balance_by_code():
    err = GiftError(code=-403, message="x")
    assert is_insufficient_balance(err) is True


def test_is_insufficient_balance_by_keyword():
    err = GiftError(code=999, message="您的账户余额不足，请充值")
    assert is_insufficient_balance(err) is True


def test_is_insufficient_balance_false_for_other():
    err = GiftError(code=200010, message="该礼物仅限从包裹中送出")
    assert is_insufficient_balance(err) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_gift.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.api.gift'`

- [ ] **Step 3: 实现 src/api/gift.py**

```python
from src.api.client import BiliClient, parse_json, BiliApiError

MEDAL_GIFT_ID = 31164

_GIFT_CONFIG_URL = "https://api.live.bilibili.com/xlive/web-room/v1/giftPanel/giftConfig"
_SEND_GOLD_URL = "https://api.live.bilibili.com/xlive/revenue/v1/gift/sendGold"

# 余额不足：已知 code 或 message 关键词，命中任一即判
INSUFFICIENT_BALANCE_CODES = {-403}
INSUFFICIENT_BALANCE_KEYWORDS = ("余额不足", "电池不足", "账户余额不足", "余额不够")


class GiftError(Exception):
    def __init__(self, code: int, message: str, raw: dict | None = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.raw = raw


def get_medal_gift_price(client: BiliClient) -> int:
    """从 giftConfig 取灯牌 price。找不到抛 BiliApiError。"""
    resp = client.get(_GIFT_CONFIG_URL,
                     params={"platform": "pc", "source": "live"})
    data = parse_json(resp)
    if data.get("code") != 0:
        raise BiliApiError(data.get("code", -1),
                           data.get("message", "获取礼物配置失败"), data)
    for item in data.get("data", {}).get("list", []) or []:
        if item.get("id") == MEDAL_GIFT_ID:
            return item.get("price", 0)
    raise BiliApiError(-1, f"未找到灯牌礼物 gift_id={MEDAL_GIFT_ID}", data)


def send_medal_gift(client: BiliClient, uid: int, ruid: int,
                    room_id: int, price: int) -> dict:
    """走 sendGold 送 1 个灯牌。code!=0 抛 GiftError。"""
    bili_jct = client.get_cookie("bili_jct")
    if not bili_jct:
        raise GiftError(-1, "缺少 bili_jct cookie，请检查 .env")

    data = {
        "uid": uid,
        "gift_id": MEDAL_GIFT_ID,
        "gift_num": 1,
        "price": price,
        "coin_type": "gold",
        "ruid": ruid,
        "biz_code": "live",
        "biz_id": room_id,
        "platform": "pc",
        "bag_id": 0,
        "storm_beat_id": 0,
        "send_ruid": 0,
        "rnd": client.make_rnd(),
        "visit_id": "",
        "csrf": bili_jct,
        "csrf_token": bili_jct,
    }
    resp = client.post(_SEND_GOLD_URL, data=data)
    result = parse_json(resp)
    if result.get("code") != 0:
        raise GiftError(result.get("code", -1),
                        result.get("message", "送礼失败"), result)
    return result.get("data", {}) or {}


def is_insufficient_balance(err: GiftError) -> bool:
    """判定是否余额不足：code 命中或 message 含关键词，任一即真。"""
    if err.code in INSUFFICIENT_BALANCE_CODES:
        return True
    msg = err.message or ""
    return any(kw in msg for kw in INSUFFICIENT_BALANCE_KEYWORDS)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/test_gift.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/api/gift.py tests/test_gift.py
git commit -m "feat: 灯牌取价与送礼（sendGold、余额不足识别）"
```

---

### Task 6: 主流程编排（main.py）

**Files:**
- Create: `main.py`

**Interfaces:**
- Consumes: `src.api.client.BiliClient`、`src.api.follow.get_live_follows`、`src.api.gift`（取价/送礼/余额判定）、`src.storage.sent_log`（去重/记录）、`dotenv`、`argparse`
- Produces: 可执行入口 `python main.py [--dry-run] [--min-interval N] [--max-interval N]`

- [ ] **Step 1: 实现 main.py**

```python
import argparse
import os
import random
import sys
import time

from dotenv import load_dotenv

from src.api.client import BiliClient, BiliApiError, BiliNetworkError
from src.api.follow import get_live_follows
from src.api.gift import (
    get_medal_gift_price, send_medal_gift, GiftError, is_insufficient_balance,
)
from src.storage.sent_log import is_sent_today, mark_sent

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sent_log.json")
AUTH_FAIL_CODE = -101
MAX_CONSEC_AUTH_FAILS = 3


def parse_args():
    p = argparse.ArgumentParser(description="给在播主播送粉丝团灯牌")
    p.add_argument("--dry-run", action="store_true", help="只列出不实际送礼")
    p.add_argument("--min-interval", type=float, default=0.5, help="最小间隔秒（默认0.5）")
    p.add_argument("--max-interval", type=float, default=1.5, help="最大间隔秒（默认1.5）")
    return p.parse_args()


def load_cookies() -> dict:
    load_dotenv()
    sessdata = os.getenv("SESSDATA")
    bili_jct = os.getenv("bili_jct")
    if not sessdata or not bili_jct:
        print("错误：.env 缺少 SESSDATA 或 bili_jct，请参考 .env.example 填写")
        sys.exit(1)
    cookies = {"SESSDATA": sessdata, "bili_jct": bili_jct}
    dede = os.getenv("DedeUserID")
    if dede:
        cookies["DedeUserID"] = dede
    return cookies


def main():
    args = parse_args()
    cookies = load_cookies()
    dede_uid = int(os.getenv("DedeUserID") or 0)
    if not dede_uid:
        print("错误：.env 缺少 DedeUserID")
        sys.exit(1)

    with BiliClient(cookies=cookies) as client:
        # 1. 取在播列表
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 正在获取在播主播列表...")
        try:
            live_list = get_live_follows(client)
        except (BiliApiError, BiliNetworkError) as e:
            print(f"获取在播列表失败: {e}")
            return

        # 2. 去重
        skipped = []
        to_send = []
        for host in live_list:
            if is_sent_today(LOG_FILE, host["uid"]):
                skipped.append(host)
            else:
                to_send.append(host)

        now = time.strftime("%H:%M:%S")
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 在播主播共 {len(live_list)} 个，"
              f"今日已送 {len(skipped)} 个，待送 {len(to_send)} 个"
              f"（间隔 {args.min_interval}-{args.max_interval}s）")

        # 3. 预演模式
        if args.dry_run:
            for h in to_send:
                print(f"  [预演] 将送：{h['uname']} (room {h['room_id']})")
            print("==== 预演结束（未实际送礼）====")
            return

        # 4. 取灯牌价格
        try:
            price = get_medal_gift_price(client)
            print(f"灯牌价格: {price} 金瓜子")
        except BiliApiError as e:
            print(f"获取灯牌价格失败: {e}")
            return

        # 5. 逐个送礼
        success = 0
        fail = 0
        stopped_for_balance = False
        stopped_for_auth = False
        consec_auth_fails = 0

        for i, host in enumerate(to_send):
            uid = host["uid"]
            uname = host["uname"]
            room_id = host["room_id"]
            tag = time.strftime("%H:%M:%S")
            try:
                send_medal_gift(client, uid=dede_uid, ruid=uid,
                                room_id=room_id, price=price)
                mark_sent(LOG_FILE, uid=uid, uname=uname,
                          room_id=room_id, status="success")
                print(f"[{tag}] ✓ {uname} (room {room_id}) 送灯牌成功")
                success += 1
                consec_auth_fails = 0
            except GiftError as e:
                if is_insufficient_balance(e):
                    mark_sent(LOG_FILE, uid=uid, uname=uname,
                              room_id=room_id, status="fail", error="余额不足")
                    print(f"[{tag}] ⛔ {uname} (room {room_id}) 余额不足，停止整轮")
                    stopped_for_balance = True
                    fail += 1
                    break
                mark_sent(LOG_FILE, uid=uid, uname=uname,
                          room_id=room_id, status="fail", error=e.message)
                print(f"[{tag}] ✗ {uname} (room {room_id}) 失败: {e.message}")
                fail += 1
                if e.code == AUTH_FAIL_CODE:
                    consec_auth_fails += 1
                    if consec_auth_fails >= MAX_CONSEC_AUTH_FAILS:
                        print("⛔ 连续鉴权失败，停止防呆，请检查 cookie")
                        stopped_for_auth = True
                        break
                else:
                    consec_auth_fails = 0
            except (BiliNetworkError, Exception) as e:
                mark_sent(LOG_FILE, uid=uid, uname=uname,
                          room_id=room_id, status="fail", error=str(e))
                print(f"[{tag}] ✗ {uname} (room {room_id}) 网络错误: {e}")
                fail += 1
                consec_auth_fails = 0

            # 间隔（最后一个不等）
            if i < len(to_send) - 1 and not stopped_for_balance and not stopped_for_auth:
                delay = random.uniform(args.min_interval, args.max_interval)
                time.sleep(delay)

        # 6. 汇总
        remaining = len(to_send) - success - fail
        print("==== 汇总 ====")
        print(f"成功: {success}  失败: {fail}  跳过(今日已送): {len(skipped)}"
              f"  因余额不足停止: {1 if stopped_for_balance else 0}"
              f"  剩余未送: {remaining}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证 --dry-run 模式语法正确（无 cookie 也能测参数解析）**

Run: `python main.py --dry-run 2>&1 | head -3`
Expected: 报"错误：.env 缺少 SESSDATA 或 bili_jct"并退出（证明参数解析和 cookie 检查工作正常，未崩溃在 import）

- [ ] **Step 3: 验证 --help**

Run: `python main.py --help`
Expected: 显示帮助文本，含 `--dry-run`、`--min-interval`、`--max-interval`

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: 主流程编排（加载cookie→取在播→去重→送礼→汇总）"
```

---

### Task 7: 全量测试与最终验证

**Files:**
- 无新增，验证所有任务

- [ ] **Step 1: 运行全部测试**

Run: `pytest tests/ -v`
Expected: 全部 passed（test_client 6 + test_sent_log 8 + test_follow 7 + test_gift 9 = 30 passed）

- [ ] **Step 2: 验证 --dry-run 端到端（需真实 cookie）**

如有 `.env`（含真实 SESSDATA/bili_jct/DedeUserID）：
Run: `python main.py --dry-run`
Expected: 打印在播主播列表 + "预演结束（未实际送礼）"，**不花钱**

- [ ] **Step 3: 最终 commit（如有遗漏）**

```bash
git add -A
git status  # 确认干净
```

- [ ] **Step 4: 写 README 使用说明**

Create: `README.md`

```markdown
# 粉丝团灯牌自动赠送工具

给 B 站关注列表里正在直播中的主播各送 1 个粉丝团灯牌，当日去重不重送。

## 快速开始

1. 复制 `.env.example` 为 `.env`，填入你的 `SESSDATA`、`bili_jct`、`DedeUserID`
   （从浏览器登录 B 站直播后，开发者工具 → Application → Cookies 获取）
2. 安装依赖：`pip install -r requirements.txt`
3. 预演（不花钱验证）：`python main.py --dry-run`
4. 正式运行：`python main.py`

## 参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--dry-run` | 只列出不实际送礼 | 关 |
| `--min-interval` | 最小送礼间隔秒 | 0.5 |
| `--max-interval` | 最大送礼间隔秒 | 1.5 |

## 本地记录

送礼结果存于 `sent_log.json`，按日期分组。当日已成功赠送的主播不会重送；
失败的主播当日可重试。跨天自动新建当日记录。

## 说明

- 仅送 `live_status==1`（直播中）的主播，轮播跳过
- 余额不足立即停止整轮
- 灯牌为付费礼物（gift_id=31164，约 1 元/个），请知悉
```

- [ ] **Step 5: Commit README**

```bash
git add README.md
git commit -m "docs: README 使用说明"
```