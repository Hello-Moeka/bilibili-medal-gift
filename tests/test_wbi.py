import base64
import hashlib
import urllib.parse
from unittest.mock import MagicMock

import httpx
import pytest

import src.api.wbi as wbi_mod
from src.api.wbi import sign_area_params, get_wbi_context, _MIXIN_KEY_ENC_TAB


def _wbi_response():
    """img_key=abcdefghij, sub_key=klmnopqrst 的 nav 响应。"""
    return httpx.Response(200, json={
        "code": 0,
        "data": {"wbi_img": {
            "img_url": "https://i0.hdslb.com/bfs/wbi/abcdefghij.png",
            "sub_url": "https://i0.hdslb.com/bfs/wbi/klmnopqrst.png",
        }}}
    )


# ---- sign_area_params ----

def test_sign_includes_all_params_and_rid():
    ctx = {"mixin_key": "a" * 32, "w_webid": "TOKEN"}
    p = sign_area_params(ctx, page=4, parent_id=9)
    assert p["platform"] == "web"
    assert p["parent_area_id"] == "9"
    assert p["area_id"] == "0"
    assert p["sort_type"] == "online"
    assert p["page"] == "4"
    assert p["web_location"] == "444.253"
    assert p["w_webid"] == "TOKEN"
    assert {"wts", "w_rid"} <= set(p)


def test_sign_is_computable_and_deterministic():
    """用固定 ts 复算 md5 验证签名公式：排序 urlencode + mixin 盐。"""
    ctx = {"mixin_key": "k" * 32, "w_webid": "T"}
    p = sign_area_params(ctx, page=1, parent_id=9, ts=1700000000)
    expected = {
        "platform": "web", "parent_area_id": "9", "area_id": "0",
        "sort_type": "online", "page": "1", "web_location": "444.253",
        "w_webid": "T", "wts": "1700000000",
    }
    q = urllib.parse.urlencode(sorted(expected.items()))
    assert p["w_rid"] == hashlib.md5((q + "k" * 32).encode()).hexdigest()


def test_sign_filters_special_chars():
    """值中的 !'()* 应被剔除后再参与签名。"""
    ctx = {"mixin_key": "a" * 32, "w_webid": "(tok)*en!"}
    p = sign_area_params(ctx, page=1, parent_id=9, ts=123)
    assert p["w_webid"] == "(tok)*en!"  # 原值保留
    # 签名输入中不含特殊字符——手动复算
    merged = dict(p)
    del merged["w_rid"]
    q = urllib.parse.urlencode(sorted(
        (k, "".join(c for c in v if c not in "!'()*"))
        for k, v in merged.items()))
    assert p["w_rid"] == hashlib.md5((q + "a" * 32).encode()).hexdigest()


# ---- get_wbi_context ----

def _spi_response():
    return httpx.Response(200, json={
        "code": 0, "data": {"b_3": "BUVID3VAL", "b_4": "BUVID4VAL"}})


def test_context_sets_buvid_cookies():
    client = MagicMock()
    client.get = MagicMock(side_effect=[
        _spi_response(),
        _wbi_response(),
        httpx.Response(200, text='x <script>"'
                                'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9xx.'
                                'eyJzcG1faWQiOiI0NDQuMjUzIn0xxxxxxxxxxx.'
                                'SIGzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz" y'),
    ])
    ctx = get_wbi_context(client, parent_id=9)
    # buvid 已写入 cookie
    set_calls = client.session.cookies.set.call_args_list
    assert set_calls[0].args[:2] == ("buvid3", "BUVID3VAL")
    assert set_calls[1].args[:2] == ("buvid4", "BUVID4VAL")
    # 访问的是对应分区页
    third_url = client.get.call_args_list[2].args[0]
    assert "parentAreaId=9" in third_url


def test_mixin_key_from_tab_order():
    raw = "".join(chr(ord("a") + i) for i in range(20))  #abcdefghijklmnopqrst
    client = MagicMock()
    client.get = MagicMock(side_effect=[
        _spi_response(),
        httpx.Response(200, json={
            "code": 0,
            "data": {"wbi_img": {
                "img_url": f"https://x/{raw}.png",
                "sub_url": "https://x/q.png",
            }}}),
        httpx.Response(200, text="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9xx.e30xxxxxxxxxxxxxxxxxxx.sigXXXXXXXXXXXXXXXXXXXXXXXXXXX"),
    ])
    ctx = get_wbi_context(client, parent_id=9)
    expect_raw = raw + "q"
    expected = "".join(expect_raw[i] for i in _MIXIN_KEY_ENC_TAB if i < len(expect_raw))[:32]
    assert ctx["mixin_key"] == expected


def test_missing_token_raises():
    import re as _re
    from src.api.client import BiliNetworkError
    client = MagicMock()
    client.get = MagicMock(side_effect=[
        _spi_response(),
        _wbi_response(),
        httpx.Response(200, text="<html>no token here</html>"),
    ])
    with pytest.raises(BiliNetworkError):
        get_wbi_context(client, parent_id=9)