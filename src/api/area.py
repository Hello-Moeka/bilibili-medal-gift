import time
from typing import List

from src.api.client import BiliClient, parse_json, BiliApiError
from src.api.wbi import get_wbi_context, sign_area_params

_SECOND_LIST_URL = "https://api.live.bilibili.com/xlive/web-interface/v1/second/getList"
_ROOM_INIT_URL = "https://api.live.bilibili.com/room/v1/Room/room_init"

# second/getList 的风控拒绝码
_RISK_CTRL_CODE = -352

# 服务端固定每页 20 条
_PAGE_SIZE = 20
# 每页请求间隔秒：该接口有行为风控，高频连续翻页会触发 -352/412
_PAGE_SLEEP = 0.5
# -352 命中后的退避重试：累计等待约 30s+60s，再失败视为风控锁死抛错
_RISK_RETRY_BACKOFF = (30, 60)
# 空页复确认等待秒（接口偶发抖动）
_EMPTY_CONFIRM_SLEEP = 0.3
# 翻页硬上限：20 条/页 × 200 页兜底（实测单分区约百余页）
_MAX_PAGES = 200
# 逐房间复核开播状态的间隔秒
_VERIFY_SLEEP = 0.05


def get_area_live_rooms(client: BiliClient, parent_id: int,
                        verify: bool = False) -> List[dict]:
    """翻页取指定父分区全部在播主播。page 从 1 起。

    走 web 端 second/getList（Wbi 签名 + w_webid 令牌，见 src/api/wbi.py）。
    该接口只返回开播中的直播间；列表含极少量刚下线的条目，
    以 online>0 预过滤 + 按 uid 去重保持首次出现顺序。
    行为风控存在：按 _PAGE_SLEEP 节流，命中 -352 时退避重试，
    重试耗尽抛 BiliApiError。verify=True 时逐房间调 room_init 复核
    live_status==1（慢但准）。
    终止条件有三（任一满足即停）：
      1. 连续两次本页为空（防接口抖动误判末页）
      2. page 超过 _MAX_PAGES
    返回列表，每项 {"uid", "uname", "room_id"}。
    """
    ctx = get_wbi_context(client, parent_id)
    result = []
    seen_uids = set()
    page = 1
    while page <= _MAX_PAGES:
        rooms = _fetch_page_with_retry(client, ctx, parent_id, page)
        if not rooms:
            time.sleep(_EMPTY_CONFIRM_SLEEP)
            rooms = _fetch_page_with_retry(client, ctx, parent_id, page)
            if not rooms:
                break

        for room in rooms:
            uid = room.get("uid")
            if uid is None or uid in seen_uids or not room.get("online"):
                continue
            seen_uids.add(uid)
            result.append({
                "uid": uid,
                "uname": room.get("uname", ""),
                "room_id": room.get("roomid"),
            })
        time.sleep(_PAGE_SLEEP)
        page += 1

    if verify and result:
        verified = []
        for i, host in enumerate(result, 1):
            if _is_live(client, host["room_id"]):
                verified.append(host)
            if i % 100 == 0:
                print(f"  [复核] 已检查 {i}/{len(result)}，"
                      f"确认在播 {len(verified)}")
        return verified
    return result


def _fetch_page_with_retry(client: BiliClient, ctx, parent_id: int,
                           page: int) -> list:
    """取一页；命中风控 -352 时退避重试，耗尽后抛 BiliApiError。"""
    last_err = None
    for attempt in range(len(_RISK_RETRY_BACKOFF) + 1):
        resp = client.get(_SECOND_LIST_URL,
                          params=sign_area_params(ctx, page=page,
                                                  parent_id=parent_id))
        data = parse_json(resp)
        if data.get("code") == _RISK_CTRL_CODE:
            last_err = BiliApiError(_RISK_CTRL_CODE, "触发风控(-352)", data)
            if attempt < len(_RISK_RETRY_BACKOFF):
                wait = _RISK_RETRY_BACKOFF[attempt]
                print(f"  [风控] second/getList 返回 -352，"
                      f"退避 {wait}s 后重试（第 {attempt + 1} 次）...")
                time.sleep(wait)
                continue
            raise last_err
        if data.get("code") != 0:
            raise BiliApiError(data.get("code", -1),
                               data.get("message", "获取分区列表失败"), data)
        return (data.get("data", {}) or {}).get("list", []) or []
    raise last_err


def _is_live(client: BiliClient, room_id: int) -> bool:
    try:
        resp = client.get(_ROOM_INIT_URL, params={"id": room_id})
        data = parse_json(resp)
        return (data.get("code") == 0
                and (data.get("data", {}) or {}).get("live_status") == 1)
    except Exception:
        return False
    finally:
        time.sleep(_VERIFY_SLEEP)