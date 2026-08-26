from typing import Dict

from src.api.client import BiliClient, parse_json, BiliApiError

_FANS_MEDAL_PANEL_URL = "https://api.live.bilibili.com/xlive/app-ucenter/v1/fansMedal/panel"

# 接口对 page_size 上限为 50（超过会返回空），用 50 减少翻页次数
_PAGE_SIZE = 50
# 翻页硬上限：防御接口异常导致无谓多翻
_MAX_PAGES = 100


def get_medal_levels(client: BiliClient) -> Dict[int, int]:
    """翻页取全部粉丝牌，返回 {主播uid: 粉丝牌等级} 映射。

    走 fansMedal/panel 接口（page_size 上限 50，靠 page_info.has_more 翻页）。
    code!=0 抛 BiliApiError。无粉丝牌返回空 dict。
    """
    result: Dict[int, int] = {}
    page = 1
    while page <= _MAX_PAGES:
        resp = client.get(_FANS_MEDAL_PANEL_URL,
                          params={"page": page, "page_size": _PAGE_SIZE})
        data = parse_json(resp)
        if data.get("code") != 0:
            raise BiliApiError(data.get("code", -1),
                               data.get("message", "获取粉丝牌失败"), data)
        body = data.get("data", {}) or {}
        items = body.get("list", []) or []
        if not items:
            break

        for item in items:
            medal = item.get("medal") or {}
            target_id = medal.get("target_id")
            level = medal.get("level")
            if target_id is None or level is None:
                continue
            result[int(target_id)] = int(level)

        page_info = body.get("page_info", {}) or {}
        if not page_info.get("has_more"):
            break
        page += 1
    return result


def filter_by_min_level(hosts, medal_levels: Dict[int, int],
                        min_level: int):
    """按最低粉丝牌等级拆分 hosts 列表。

    hosts: [{"uid","uname","room_id"}]
    返回 (qualified, filtered_out)，均保持原顺序。
    无对应等级记录的视为不达标（返回的 filtered_out 会带 reason 字段）。
    """
    qualified = []
    filtered_out = []
    for host in hosts:
        uid = host.get("uid")
        level = medal_levels.get(uid)
        if level is not None and level >= min_level:
            qualified.append(host)
        else:
            out = dict(host)
            out["reason"] = (f"粉丝牌等级 {level} < {min_level}"
                             if level is not None
                             else f"无粉丝牌（阈值 {min_level}）")
            out["medal_level"] = level
            filtered_out.append(out)
    return qualified, filtered_out