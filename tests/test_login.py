import httpx
import pytest
from unittest.mock import MagicMock, patch
from src.api.login import (
    QrLogin, QrStatus, parse_login_cookies, extract_dede_uid,
    _parse_cookies_from_url,
)


def _poll_resp(code, set_cookies=None):
    """构造一个 poll 响应：外层 code 恒 0（B 站接口如此），真实状态在内层 data.code。"""
    headers = []
    if set_cookies:
        for c in set_cookies:
            headers.append(("set-cookie", c))
    inner = {"code": code}
    if code == 0:
        inner["url"] = ("https://passport.biligame.com/x/passport-login/web/crossDomain?"
                        "DedeUserID=10450385&DedeUserID__ckMd5=xxx&SESSDATA=yyy&bili_jct=zzz")
    body = {"code": 0, "data": inner}
    return httpx.Response(200, json=body, headers=headers)


def test_parse_status_waiting():
    resp = _poll_resp(86101)  # 未扫码
    login = QrLogin.__new__(QrLogin)
    status, msg = login._parse_status(resp)
    assert status == QrStatus.WAITING
    assert msg


def test_parse_status_scanned():
    resp = _poll_resp(86090)  # 已扫码未确认
    login = QrLogin.__new__(QrLogin)
    status, msg = login._parse_status(resp)
    assert status == QrStatus.SCANNED


def test_parse_status_expired():
    resp = _poll_resp(86038)  # 二维码过期
    login = QrLogin.__new__(QrLogin)
    status, msg = login._parse_status(resp)
    assert status == QrStatus.EXPIRED


def test_parse_status_success():
    resp = _poll_resp(0)
    login = QrLogin.__new__(QrLogin)
    status, msg = login._parse_status(resp)
    assert status == QrStatus.SUCCESS


def test_parse_status_unknown_code():
    resp = _poll_resp(99999)
    login = QrLogin.__new__(QrLogin)
    status, msg = login._parse_status(resp)
    assert status == QrStatus.UNKNOWN


def test_parse_login_cookies_from_set_cookie():
    cookies_list = [
        "SESSDATA=abc%2C123; Path=/; Domain=.bilibili.com; HttpOnly",
        "bili_jct=xyz; Path=/; Domain=.bilibili.com",
        "DedeUserID=10450385; Path=/; Domain=.bilibili.com",
        "buvid3=somebuvid; Path=/; Domain=.bilibili.com",
    ]
    cookies = parse_login_cookies(cookies_list)
    assert cookies["SESSDATA"] == "abc%2C123"
    assert cookies["bili_jct"] == "xyz"
    assert cookies["DedeUserID"] == "10450385"
    assert cookies["buvid3"] == "somebuvid"


def test_parse_login_cookies_ignores_irrelevant():
    cookies_list = [
        "SESSDATA=abc; Path=/; Domain=.bilibili.com",
        "bili_jct=xyz; Path=/; Domain=.bilibili.com",
    ]
    cookies = parse_login_cookies(cookies_list)
    assert cookies == {"SESSDATA": "abc", "bili_jct": "xyz"}


def test_extract_dede_uid():
    assert extract_dede_uid({"DedeUserID": "10450385"}) == 10450385


def test_extract_dede_uid_missing():
    assert extract_dede_uid({}) == 0


def test_parse_cookies_from_url():
    url = ("https://passport.biligame.com/x/passport-login/web/crossDomain?"
           "DedeUserID=10450385&DedeUserID__ckMd5=abc&SESSDATA=yyy&bili_jct=zzz")
    cookies = _parse_cookies_from_url(url)
    assert cookies["DedeUserID"] == "10450385"
    assert cookies["SESSDATA"] == "yyy"
    assert cookies["bili_jct"] == "zzz"
    assert cookies["DedeUserID__ckMd5"] == "abc"


def test_parse_cookies_from_url_empty():
    assert _parse_cookies_from_url("https://example.com/noquery") == {}