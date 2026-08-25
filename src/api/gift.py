import json
import os
import time

from src.api.client import BiliClient, parse_json, BiliApiError

MEDAL_GIFT_ID = 31164

_GIFT_CONFIG_URL = "https://api.live.bilibili.com/xlive/web-room/v1/giftPanel/giftConfig"
_SEND_GOLD_URL = "https://api.live.bilibili.com/xlive/revenue/v1/gift/sendGold"

# 灯牌 price 极少变动，本地缓存避免每次运行都拉取全量礼物配置。
# 缓存文件放在项目根目录；可用环境变量 GIFT_PRICE_CACHE_FILE 覆盖路径（便于测试）。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GIFT_PRICE_CACHE_FILE = os.environ.get(
    "GIFT_PRICE_CACHE_FILE",
    os.path.join(_PROJECT_ROOT, "gift_price_cache.json"),
)
GIFT_PRICE_CACHE_TTL = 86400  # 24 小时

# 余额不足：已知 code 或 message 关键词，命中任一即判
INSUFFICIENT_BALANCE_CODES = {-403}
INSUFFICIENT_BALANCE_KEYWORDS = ("余额不足", "电池不足", "账户余额不足", "余额不够")


class GiftError(Exception):
    def __init__(self, code: int, message: str, raw: dict | None = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.raw = raw


def _fetch_gift_price(client: BiliClient) -> int:
    """实际请求 giftConfig 取灯牌 price。找不到抛 BiliApiError。"""
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


def get_medal_gift_price(client: BiliClient) -> int:
    """从 giftConfig 取灯牌 price，带本地文件缓存（TTL 24h）。

    缓存命中直接返回 price，过期或不存在才请求 API。
    找不到礼物抛 BiliApiError。缓存写入失败不影响功能。
    """
    # 先读本地缓存
    if os.path.exists(GIFT_PRICE_CACHE_FILE):
        try:
            with open(GIFT_PRICE_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if time.time() - cache.get("timestamp", 0) < GIFT_PRICE_CACHE_TTL:
                return cache["price"]
        except (json.JSONDecodeError, KeyError, TypeError, OSError):
            pass  # 缓存损坏，回退到请求 API

    # 缓存不存在或过期，请求 API
    price = _fetch_gift_price(client)

    # 写入缓存（失败忽略，不影响主流程）
    try:
        with open(GIFT_PRICE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"price": price, "timestamp": time.time()}, f)
    except (OSError, TypeError):
        pass

    return price


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