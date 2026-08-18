import httpx
import pytest
from src.api.client import BiliClient, parse_json, BiliNetworkError


def test_client_sets_cookies():
    client = BiliClient(cookies={"SESSDATA": "abc", "bili_jct": "xyz"})
    assert client.get_cookie("SESSDATA") == "abc"
    assert client.get_cookie("bili_jct") == "xyz"
    client.close()


def test_get_cookie_missing_returns_none():
    client = BiliClient()
    assert client.get_cookie("nope") is None
    client.close()


def test_make_rnd_is_ms_timestamp():
    import time
    rnd = BiliClient.make_rnd()
    now = int(time.time() * 1000)
    assert abs(rnd - now) < 2000  # 2 秒容差


def test_parse_json_valid():
    resp = httpx.Response(200, json={"code": 0, "data": {"ok": True}})
    assert parse_json(resp) == {"code": 0, "data": {"ok": True}}


def test_parse_json_non_json_raises():
    resp = httpx.Response(200, text="not json")
    with pytest.raises(BiliNetworkError):
        parse_json(resp)


def test_parse_json_http_error_raises():
    resp = httpx.Response(500, text="server error")
    with pytest.raises(BiliNetworkError):
        parse_json(resp)