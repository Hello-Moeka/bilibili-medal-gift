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


def test_hard_cap_prevents_infinite_pagination(monkeypatch):
    """接口异常永不返回终止信号时，硬上限应兜底停止翻页。"""
    import src.api.follow as follow_mod
    # 放大上限以缩短测试，验证硬上限逻辑本身
    monkeypatch.setattr(follow_mod, "_MAX_PAGES", 3)
    # 每页都返回全直播中、count 极大，永不触发常规终止条件
    page_body = {"code": 0, "data": {"rooms": [
        {"uid": 1, "uname": "A", "room_id": 10, "live_status": 1},
    ], "count": 99999}}
    client = _mock_client([page_body, page_body, page_body])
    result = get_live_follows(client)
    # 最多翻 _MAX_PAGES 页（3），每页收 1 个 → 3 个
    assert len(result) == 3
    assert client.get.call_count == 3


def test_page_size_passed_in_params():
    """显式 page_size 应进入请求参数。"""
    client = _mock_client([{
        "code": 0, "data": {"rooms": [], "count": 0}
    }])
    get_live_follows(client, page_size=50)
    _, kwargs = client.get.call_args
    assert kwargs["params"]["page_size"] == 50