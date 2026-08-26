import hashlib
import json
import re
import time
import urllib.parse
from typing import Dict

from src.api.client import BiliClient, parse_json, BiliNetworkError

_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
_SPI_URL = "https://api.bilibili.com/x/frontend/finger/spi"
_AREA_TAGS_URL = ("https://live.bilibili.com/p/eden/area-tags"
                  "?parentAreaId={parent_id}&areaId=0")

# Wbi 混淆表（bilibili-API-collect），对 img_key+sub_key 重排后取前 32 位
_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

_JWT_RE = re.compile(
    r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")


def get_wbi_context(client: BiliClient, parent_id: int) -> Dict[str, str]:
    """获取分区接口所需的签名上下文 {mixin_key, w_webid}。

    顺序敏感：
      1. finger/spi 取设备指纹并写入 buvid3/buvid4 cookie——gaia 下发的
         JWT 会携带 buvid 声明，缺它接口一律 -352；
      2. nav 取 wbi_img 的 img/sub key 混淆出签名盐；
      3. 访问直播分区页，从 HTML 中提取 w_webid（JWT 令牌）。
    """
    resp = client.get(_SPI_URL)
    spi = parse_json(resp)
    if spi.get("code") == 0:
        fp = spi.get("data", {}) or {}
        b3, b4 = fp.get("b_3"), fp.get("b_4")
        if b3:
            client.session.cookies.set("buvid3", b3, domain=".bilibili.com")
        if b4:
            client.session.cookies.set("buvid4", b4, domain=".bilibili.com")

    resp = client.get(_NAV_URL)
    nav = parse_json(resp)
    wbi = ((nav.get("data") or {}).get("wbi_img")) or {}
    img = wbi.get("img_url", "")
    sub = wbi.get("sub_url", "")
    if not img or not sub:
        raise BiliNetworkError(f"nav 响应缺少 wbi_img: code={nav.get('code')}")
    raw = (img.rsplit("/", 1)[-1].split(".")[0]
           + sub.rsplit("/", 1)[-1].split(".")[0])
    # 真实 wbi key 为 img+sub 各 32 位共 64 位；防御性容忍更短的输入，
    # 混淆表索引越界处直接跳过
    mixed = "".join(raw[i] for i in _MIXIN_KEY_ENC_TAB if i < len(raw))
    mixin_key = mixed[:32]

    resp = client.get(_AREA_TAGS_URL.format(parent_id=parent_id))
    tokens = _JWT_RE.findall(resp.text)
    # 取最长的 JWT（页面可能内嵌多个），即 gaia 为本页签发的令牌
    token = max(tokens, key=len) if tokens else ""
    if not token:
        raise BiliNetworkError("分区页面未找到 w_webid 令牌")
    return {"mixin_key": mixin_key, "w_webid": token}


def sign_area_params(ctx: Dict[str, str], page: int,
                     parent_id: int, sort_type: str = "online",
                     ts: int = None) -> Dict[str, str]:
    """构造 second/getList 的完整签名参数。

    除 w_rid 外的所有参数（含 w_webid、web_location、wts）都参与 md5。
    """
    merged = {
        "platform": "web",
        "parent_area_id": str(parent_id),
        "area_id": "0",
        "sort_type": sort_type,
        "page": str(page),
        "web_location": "444.253",
        "w_webid": ctx["w_webid"],
        "wts": str(ts if ts is not None else int(time.time())),
    }
    query = urllib.parse.urlencode(
        sorted((k, "".join(ch for ch in v if ch not in "!'()*"))
               for k, v in merged.items()))
    merged["w_rid"] = hashlib.md5((query + ctx["mixin_key"]).encode()).hexdigest()
    return merged