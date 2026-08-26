import httpx
import pytest
from unittest.mock import MagicMock
import src.api.medal as medal_mod
from src.api.medal import get_medal_levels, filter_by_min_level
from src.api.client import BiliApiError


def _mock_client(pages_responses):
    """pages_responses: list of dict，每个是一页的完整 JSON 响应体。"""
    client = MagicMock()
    client.get = MagicMock(side_effect=[
        httpx.Response(200, json=body) for body in pages_responses
    ])
    return client


def _page(items, *, has_more=False, total_number=0):
    """构造一页 fansMedal/panel 响应体。"""
    return {
        "code": 0,
        "data": {
            "list": items,
            "total_number": total_number,
            "page_info": {"has_more": has_more, "total_page": 1},
        },
    }


def _medal_item(target_id, level, name="x"):
    return {
        "medal": {"target_id": target_id, "level": level, "medal_name": name},
        "anchor_info": {},
        "room_info": {},
        "uinfo_medal": {},
    }


# ---- get_medal_levels ----

def test_parse_single_page():
    body = _page([_medal_item(101, 20, "A牌"), _medal_item(102, 3, "B牌")])
    client = _mock_client([body])
    result = get_medal_levels(client)
    assert result == {101: 20, 102: 3}
    _, kwargs = client.get.call_args
    assert kwargs["params"]["page"] == 1


def test_paginates_until_no_more():
    page1 = _page([_medal_item(1, 10), _medal_item(2, 20)], has_more=True)
    page2 = _page([_medal_item(3, 30)], has_more=False)
    client = _mock_client([page1, page2])
    result = get_medal_levels(client)
    assert result == {1: 10, 2: 20, 3: 30}
    assert client.get.call_count == 2


def test_empty_medals():
    body = _page([], has_more=False)
    client = _mock_client([body])
    assert get_medal_levels(client) == {}


def test_missing_fields_skipped():
    items = [
        _medal_item(101, 5),
        {"medal": {"target_id": 102}},          # 缺 level
        {"medal": {"level": 10}},                # 缺 target_id
        {"medal": {}},                           # 都缺
        {},                                      # 无 medal
    ]
    body = _page(items, has_more=False)
    client = _mock_client([body])
    assert get_medal_levels(client) == {101: 5}


def test_api_error_raises():
    body = {"code": -101, "message": "账号未登录", "data": {}}
    client = _mock_client([body])
    with pytest.raises(BiliApiError):
        get_medal_levels(client)


def test_stops_when_list_empty():
    """list 为空但 has_more=True 时，应停止翻页（空 list 即无数据）。"""
    page1 = _page([_medal_item(1, 10)], has_more=True)
    page2 = _page([], has_more=True)  # 空但 has_more 仍为 True
    client = _mock_client([page1, page2])
    result = get_medal_levels(client)
    assert result == {1: 10}
    assert client.get.call_count == 2


def test_hard_cap_prevents_infinite_pagination(monkeypatch):
    """接口异常永不返回 has_more=False 时，硬上限应兜底停止翻页。"""
    monkeypatch.setattr(medal_mod, "_MAX_PAGES", 3)
    page_body = _page([_medal_item(1, 10)], has_more=True, total_number=99999)
    client = _mock_client([page_body, page_body, page_body])
    result = get_medal_levels(client)
    assert client.get.call_count == 3
    assert result == {1: 10}


def test_page_size_50_in_params():
    """应显式传 page_size=50。"""
    body = _page([], has_more=False)
    client = _mock_client([body])
    get_medal_levels(client)
    _, kwargs = client.get.call_args
    assert kwargs["params"]["page_size"] == 50


# ---- filter_by_min_level ----

def test_filter_keeps_high_level():
    hosts = [
        {"uid": 101, "uname": "A", "room_id": 10},
        {"uid": 102, "uname": "B", "room_id": 20},
        {"uid": 103, "uname": "C", "room_id": 30},
    ]
    levels = {101: 20, 102: 3, 103: 15}
    qualified, filtered = filter_by_min_level(hosts, levels, min_level=15)
    assert [h["uid"] for h in qualified] == [101, 103]
    assert [h["uid"] for h in filtered] == [102]
    assert filtered[0]["reason"] == "粉丝牌等级 3 < 15"
    assert filtered[0]["medal_level"] == 3


def test_filter_no_medal_record():
    hosts = [
        {"uid": 101, "uname": "A", "room_id": 10},
        {"uid": 999, "uname": "X", "room_id": 90},
    ]
    levels = {101: 25}
    qualified, filtered = filter_by_min_level(hosts, levels, min_level=15)
    assert [h["uid"] for h in qualified] == [101]
    assert filtered[0]["uid"] == 999
    assert filtered[0]["medal_level"] is None
    assert "无粉丝牌" in filtered[0]["reason"]


def test_filter_all_qualified():
    hosts = [{"uid": 1, "uname": "A", "room_id": 10}]
    levels = {1: 30}
    qualified, filtered = filter_by_min_level(hosts, levels, min_level=15)
    assert len(qualified) == 1
    assert filtered == []


def test_filter_all_filtered():
    hosts = [{"uid": 1, "uname": "A", "room_id": 10}]
    levels = {1: 5}
    qualified, filtered = filter_by_min_level(hosts, levels, min_level=15)
    assert qualified == []
    assert len(filtered) == 1


def test_filter_preserves_order():
    hosts = [
        {"uid": 1, "uname": "A", "room_id": 10},
        {"uid": 2, "uname": "B", "room_id": 20},
        {"uid": 3, "uname": "C", "room_id": 30},
    ]
    levels = {1: 5, 2: 20, 3: 5}
    qualified, filtered = filter_by_min_level(hosts, levels, min_level=15)
    assert [h["uid"] for h in qualified] == [2]
    assert [h["uid"] for h in filtered] == [1, 3]