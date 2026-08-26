import httpx
import pytest
from unittest.mock import MagicMock
import src.api.area as area_mod
from src.api.area import get_area_live_rooms
from src.api.client import BiliApiError


def _page_body(rooms):
    return {"code": 0, "data": {"list": rooms}}


def _room(uid, roomid=None, online=100):
    return {"uid": uid, "uname": f"u{uid}", "roomid": roomid or uid * 10,
            "online": online}


_CTX = {"mixin_key": "x" * 32, "w_webid": "tok"}


def _mock_client(page_bodies, verify_resps=None):
    """按 URL 路由的 mock：
    - second/getList 依序返回 page_bodies（dict 为完整响应体，list 视为 data.list）
      耗尽后无限返回空页（模拟末页）；
    - room_init 依序返回 verify_resps（耗尽后返回在播）。"""
    pages = [b if isinstance(b, dict) else _page_body(b) for b in page_bodies]
    verifies = list(verify_resps or [])
    state = {"page": 0}

    def side_effect(url, params=None, headers=None, **kw):
        if "second/getList" in url:
            idx = state["page"]
            state["page"] += 1
            if idx < len(pages):
                return httpx.Response(200, json=pages[idx])
            return httpx.Response(200, json=_page_body([]))
        if verifies:
            return verifies.pop(0)
        # 空页复确认时 page 序列也要继续走
        return httpx.Response(200, json=_page_body([]))

    client = MagicMock()
    client.get = MagicMock(side_effect=side_effect)
    client.session.cookies.set = MagicMock()
    return client


@pytest.fixture(autouse=True)
def patch_wbi_context(monkeypatch):
    monkeypatch.setattr(area_mod, "get_wbi_context",
                        lambda client, parent_id: dict(_CTX))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    for attr in ("_EMPTY_CONFIRM_SLEEP", "_VERIFY_SLEEP", "_PAGE_SLEEP"):
        monkeypatch.setattr(area_mod, attr, 0)
    monkeypatch.setattr(area_mod, "_RISK_RETRY_BACKOFF", (0, 0))


# ---- 分区列表 ----

def test_single_page():
    client = _mock_client([[_room(1), _room(2)]])
    result = get_area_live_rooms(client, parent_id=9)
    assert result == [
        {"uid": 1, "uname": "u1", "room_id": 10},
        {"uid": 2, "uname": "u2", "room_id": 20},
    ]
    _, kwargs = client.get.call_args_list[0]
    assert kwargs["params"]["parent_area_id"] == "9"
    assert kwargs["params"]["area_id"] == "0"
    assert kwargs["params"]["page"] == "1"
    assert {"w_rid", "wts", "w_webid"} <= set(kwargs["params"])


def test_paginates_until_empty_with_reconfirmation():
    p1 = [_room(i) for i in range(1, 21)]
    p2 = [_room(21), _room(22)]
    client = _mock_client([p1, p2])
    result = get_area_live_rooms(client, parent_id=9)
    assert [h["uid"] for h in result] == list(range(1, 23))
    # 空页要复确认一次才停（至少 p1 + p2 + 空×2 = 4 次请求）
    page_calls = [c for c in client.get.call_args_list]
    assert len(page_calls) >= 4


def test_dedup_keeps_first_and_skips_online_zero():
    client = _mock_client([
        [_room(1), _room(2, online=0)],
        [_room(2), _room(3)],
    ])
    result = get_area_live_rooms(client, parent_id=9)
    # uid=2 首现时 online=0 被剔且未记为已见，次页出现正常数据则收录
    assert [h["uid"] for h in result] == [1, 2, 3]


def test_online_zero_skipped_entirely_when_only_seen_offline():
    client = _mock_client([
        [_room(1), _room(2, online=0)],
        [],
    ])
    result = get_area_live_rooms(client, parent_id=9)
    assert [h["uid"] for h in result] == [1]


def test_missing_uid_skipped():
    rooms = [{"uname": "noid", "online": 5}, _room(5)]
    client = _mock_client([rooms])
    result = get_area_live_rooms(client, parent_id=9)
    assert [h["uid"] for h in result] == [5]


def test_api_error_raises():
    client = MagicMock()
    client.get = MagicMock(return_value=httpx.Response(
        200, json={"code": 1, "message": "参数错误", "data": {}}))
    with pytest.raises(BiliApiError):
        get_area_live_rooms(client, parent_id=9)


def test_verify_filters_offline_rooms():
    verify_resps = [
        httpx.Response(200, json={"code": 0, "data": {"live_status": 1}}),
        httpx.Response(200, json={"code": 0, "data": {"live_status": 0}}),
        httpx.Response(200, json={"code": 1, "data": {}}),
    ]
    client = _mock_client([[_room(1), _room(2), _room(3)]],
                          verify_resps=verify_resps)
    result = get_area_live_rooms(client, parent_id=9, verify=True)
    assert [h["uid"] for h in result] == [1]


def test_hard_cap_prevents_infinite_pagination(monkeypatch):
    monkeypatch.setattr(area_mod, "_MAX_PAGES", 3)
    full_page = [_room(i) for i in range(20)]
    client = MagicMock()
    client.get = MagicMock(return_value=httpx.Response(
        200, json=_page_body(full_page)))
    result = get_area_live_rooms(client, parent_id=9)
    assert client.get.call_count == 3
    assert len(result) == 20


def test_risk_control_retries_then_succeeds(monkeypatch):
    """-352 风控：首次命中退避重试，第二次成功。"""
    resp_seq = [
        httpx.Response(200, json={"code": -352, "message": "-352"}),
        httpx.Response(200, json=_page_body([_room(1)])),
        httpx.Response(200, json=_page_body([])),
        httpx.Response(200, json=_page_body([])),
    ]
    client = MagicMock()
    client.get = MagicMock(side_effect=lambda *a, **kw: resp_seq.pop(0))
    result = get_area_live_rooms(client, parent_id=9)
    assert [h["uid"] for h in result] == [1]
    assert client.get.call_count == 4


def test_risk_control_raises_after_backoff_exhausted():
    client = MagicMock()
    client.get = MagicMock(return_value=httpx.Response(
        200, json={"code": -352, "message": "-352"}))
    with pytest.raises(BiliApiError):
        get_area_live_rooms(client, parent_id=9)