import httpx
import pytest
from unittest.mock import MagicMock
from src.api.gift import (
    get_medal_gift_price, send_medal_gift, GiftError,
    is_insufficient_balance, MEDAL_GIFT_ID,
)


def _mock_get_client(json_body):
    client = MagicMock()
    client.get = MagicMock(return_value=httpx.Response(200, json=json_body))
    client.get_cookie = MagicMock(return_value="csrf_token_xxx")
    client.make_rnd = MagicMock(return_value=1700000000000)
    return client


def test_get_price_finds_medal():
    body = {"code": 0, "data": {"list": [
        {"id": 31039, "name": "牛哇牛哇", "price": 100},
        {"id": MEDAL_GIFT_ID, "name": "粉丝团灯牌", "price": 1000},
    ]}}
    client = _mock_get_client(body)
    assert get_medal_gift_price(client) == 1000


def test_get_price_not_found_raises():
    body = {"code": 0, "data": {"list": [
        {"id": 31039, "name": "牛哇牛哇", "price": 100},
    ]}}
    client = _mock_get_client(body)
    with pytest.raises(Exception):
        get_medal_gift_price(client)


def test_send_gift_success():
    # post 返回成功
    client = MagicMock()
    client.get_cookie = MagicMock(return_value="jct_xxx")
    client.make_rnd = MagicMock(return_value=1700000000000)
    client.post = MagicMock(return_value=httpx.Response(200, json={
        "code": 0, "data": {"gift_id": MEDAL_GIFT_ID}
    }))
    result = send_medal_gift(client, uid=100, ruid=200,
                             room_id=999, price=1000)
    assert result["gift_id"] == MEDAL_GIFT_ID
    # 校验 post 调用的 url 和关键字表单字段
    args, kwargs = client.post.call_args
    assert "sendGold" in args[0]
    data = kwargs["data"]
    assert data["gift_id"] == MEDAL_GIFT_ID
    assert data["gift_num"] == 1
    assert data["coin_type"] == "gold"
    assert data["ruid"] == 200
    assert data["biz_id"] == 999
    assert data["csrf"] == "jct_xxx"
    assert data["csrf_token"] == "jct_xxx"
    assert data["price"] == 1000


def test_send_gift_missing_jct_raises():
    client = MagicMock()
    client.get_cookie = MagicMock(return_value=None)
    with pytest.raises(Exception, match="bili_jct"):
        send_medal_gift(client, uid=100, ruid=200, room_id=999, price=1000)


def test_send_gift_api_error_raises_gift_error():
    client = MagicMock()
    client.get_cookie = MagicMock(return_value="jct_xxx")
    client.make_rnd = MagicMock(return_value=1700000000000)
    client.post = MagicMock(return_value=httpx.Response(200, json={
        "code": -403, "message": "账户余额不足"
    }))
    with pytest.raises(GiftError) as exc_info:
        send_medal_gift(client, uid=100, ruid=200, room_id=999, price=1000)
    assert exc_info.value.code == -403


def test_is_insufficient_balance_by_code():
    err = GiftError(code=-403, message="x")
    assert is_insufficient_balance(err) is True


def test_is_insufficient_balance_by_keyword():
    err = GiftError(code=999, message="您的账户余额不足，请充值")
    assert is_insufficient_balance(err) is True


def test_is_insufficient_balance_false_for_other():
    err = GiftError(code=200010, message="该礼物仅限从包裹中送出")
    assert is_insufficient_balance(err) is False