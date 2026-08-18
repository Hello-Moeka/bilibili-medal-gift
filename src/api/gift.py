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