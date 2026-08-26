import httpx
import pytest
from unittest.mock import MagicMock
import src.api.area as area_mod
from src.api.area import get_area_live_rooms
from src.api.client import BiliApiError


def _mock_client(pages_responses):
    """pages_responses: list of dict，每页 data 数组内容。"""
    client = MagicMock()
    client.get = MagicMock(side_effect=[
        httpx.Response(200, json={"code": 0, "data": rooms})
        for rooms in pages_responses
    ])
    return client


def _room(uid, roomid=None):
    return {"uid": uid, "uname": f"u{uid}", "roomid": roomid or uid * 10}


def test_single_full_page():
    client = _mock_client([[_room(1), _room(2), _room(3)]])
    result = get_area_live_rooms(client, parent_id=9)
    assert result == [
        {"uid": 1, "uname": "u1", "room_id": 10},
        {"uid": 2, "uname": "u2", "room_id": 20},
        {"uid": 3, "uname": "u3", "room_id": 30},
    ]
    _, kwargs = client.get.call_args
    assert kwargs["params"]["parent_id"] == 9
    assert kwargs["params"]["area_id"] == 0


def test_paginates_until_partial_page():
    client = _mock_client([[_room(1), _room(2)], [_room(3)]])
    result = get_area_live_rooms(client, parent_id=9, page_size=2)
    assert [h["uid"] for h in result] == [1, 2, 3]
    assert client.get.call_count == 2


def test_stops_on_empty_page():
    client = _mock_client([[_room(1)], []])
    result = get_area_live_rooms(client, parent_id=9)
    assert [h["uid"] for h in result] == [1]


def test_dedup_keeps_first_occurrence():
    # page_size=2：p1 满、p2 满且含重复、p3 空页停止
    client = _mock_client([[_room(1), _room(2)],
                           [_room(2), _room(3)],
                           []])
    result = get_area_live_rooms(client, parent_id=9, page_size=2)
    assert [h["uid"] for h in result] == [1, 2, 3]
    assert client.get.call_count == 3


def test_missing_uid_skipped():
    rooms = [{"uname": "noid"}, _room(5)]
    client = _mock_client([rooms])
    result = get_area_live_rooms(client, parent_id=9)
    assert [h["uid"] for h in result] == [5]


def test_api_error_raises():
    client = MagicMock()
    client.get = MagicMock(return_value=httpx.Response(
        200, json={"code": 1, "message": "参数错误", "data": []}))
    with pytest.raises(BiliApiError):
        get_area_live_rooms(client, parent_id=9)


def test_hard_cap_prevents_infinite_pagination(monkeypatch):
    monkeypatch.setattr(area_mod, "_MAX_PAGES", 3)
    full_page = [_room(i) for i in range(99)]
    # 每页都是同一批 uid（接口异常场景），去重后仍只有 99 个
    client = _mock_client([full_page] * 5)
    result = get_area_live_rooms(client, parent_id=9)
    assert client.get.call_count == 3
    assert len(result) == 99


def test_custom_page_size():
    client = _mock_client([[_room(1)]])
    get_area_live_rooms(client, parent_id=9, page_size=50)
    _, kwargs = client.get.call_args
    assert kwargs["params"]["page_size"] == 50