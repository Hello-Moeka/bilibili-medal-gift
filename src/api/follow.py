from typing import List
from src.api.client import BiliClient, parse_json, BiliApiError

_GET_WEB_LIST_URL = "https://api.live.bilibili.com/xlive/web-ucenter/v1/xfetter/GetWebList"

# live_status: 0=未开播 1=直播中 2=轮播
_LIVE_LIVING = 1
_LIVE_OFFLINE = 0

# 翻页硬上限：防御性保护，避免接口异常导致无谓多翻
_MAX_PAGES = 50
# 显式传 page_size，减少翻页次数（接口默认偏小）
_DEFAULT_PAGE_SIZE = 50


def get_live_follows(client: BiliClient, page_size: int = _DEFAULT_PAGE_SIZE) -> List[dict]:
    """翻页取在播主播。page 从 1 起。

    语义：仅收入 live_status==1（直播中）；轮播(2)跳过但继续翻页；
    遇到首个未开播(0)即停止翻页。终止条件有四（任一满足即停）：
      1. 遇到未开播主播
      2. 本页 rooms 为空（无更多数据）
      3. 已收集数量 >= count（关注列表的在播总数已取完）
      4. page 超过 _MAX_PAGES（硬上限，防御接口异常）
    返回列表，每项 {"uid", "uname", "room_id"}。
    """
    result = []
    page = 1
    total_live = None
    while page <= _MAX_PAGES:
        resp = client.get(_GET_WEB_LIST_URL,
                          params={"page": page, "page_size": page_size})
        data = parse_json(resp)
        if data.get("code") != 0:
            raise BiliApiError(data.get("code", -1),
                               data.get("message", "未知错误"), data)
        body = data.get("data", {}) or {}
        rooms = body.get("rooms", []) or []
        if total_live is None:
            total_live = body.get("count", 0) or 0

        if not rooms:
            break  # 无更多数据

        should_stop = False
        for room in rooms:
            live_status = room.get("live_status", 0)
            if live_status == _LIVE_OFFLINE:
                # 遇到未开播 → 停止翻页
                should_stop = True
                break
            if live_status == _LIVE_LIVING:
                result.append({
                    "uid": room.get("uid"),
                    "uname": room.get("uname", ""),
                    "room_id": room.get("room_id"),
                })
            # live_status==2（轮播）跳过，继续看下一个

        if should_stop:
            break
        # 已取完在播总数，不再翻页
        if total_live and len(result) >= total_live:
            break
        page += 1
    return result