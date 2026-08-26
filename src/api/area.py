from typing import List

from src.api.client import BiliClient, parse_json, BiliApiError

_AREA_ROOM_LIST_URL = "https://api.live.bilibili.com/room/v1/Area/getRoomList"

# page_size 实测上限 99（传 100 反而只回 20 条），取 99 减少翻页次数
_PAGE_SIZE = 99
# 翻页硬上限：99×300≈3万，防接口异常导致无谓多翻
_MAX_PAGES = 300


def get_area_live_rooms(client: BiliClient, parent_id: int,
                        page_size: int = _PAGE_SIZE) -> List[dict]:
    """翻页取指定父分区全部在播主播。page 从 1 起。

    终止条件有三（任一满足即停）：
      1. 本页 rooms 为空
      2. 本页数量 < page_size（最后一页）
      3. page 超过 _MAX_PAGES（硬上限，防御接口异常）
    返回列表，每项 {"uid", "uname", "room_id"}，按 uid 去重保持首次出现顺序。
    """
    result = []
    seen_uids = set()
    page = 1
    while page <= _MAX_PAGES:
        resp = client.get(_AREA_ROOM_LIST_URL,
                          params={"parent_id": parent_id, "area_id": 0,
                                  "page": page, "page_size": page_size})
        data = parse_json(resp)
        if data.get("code") != 0:
            raise BiliApiError(data.get("code", -1),
                               data.get("message", "获取分区列表失败"), data)
        rooms = data.get("data", []) or []
        if not rooms:
            break

        for room in rooms:
            uid = room.get("uid")
            if uid is None or uid in seen_uids:
                continue
            seen_uids.add(uid)
            result.append({
                "uid": uid,
                "uname": room.get("uname", ""),
                "room_id": room.get("roomid"),
            })

        if len(rooms) < page_size:
            break
        page += 1
    return result