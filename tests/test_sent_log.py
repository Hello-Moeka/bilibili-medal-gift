import json
import os
import time
from src.storage.sent_log import (
    today_str, load_sent, is_sent_today, mark_sent,
)


def test_today_str_format():
    s = today_str()
    assert len(s) == 10
    assert s[4] == "-" and s[7] == "-"


def test_load_sent_missing_file_returns_empty(tmp_log_file):
    assert load_sent(tmp_log_file) == {}


def test_mark_sent_success_then_is_sent_today(tmp_log_file):
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="success")
    assert is_sent_today(tmp_log_file, 12345) is True


def test_mark_sent_fail_not_treated_as_sent(tmp_log_file):
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="fail", error="余额不足")
    # 失败当日可重试，不算已送
    assert is_sent_today(tmp_log_file, 12345) is False


def test_mark_sent_writes_fields(tmp_log_file):
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="success")
    data = load_sent(tmp_log_file)
    today = today_str()
    assert today in data
    rec = data[today]["12345"]
    assert rec["uname"] == "主播A"
    assert rec["room_id"] == 67890
    assert rec["status"] == "success"
    assert "sent_at" in rec
    assert rec["sent_at"].startswith(today)


def test_mark_sent_overwrites_same_uid_same_day(tmp_log_file):
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="fail", error="x")
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="success")
    # 第二次成功后应视为已送
    assert is_sent_today(tmp_log_file, 12345) is True


def test_is_sent_today_other_uid_not_affected(tmp_log_file):
    mark_sent(tmp_log_file, uid=12345, uname="主播A",
              room_id=67890, status="success")
    assert is_sent_today(tmp_log_file, 99999) is False


def test_load_sent_handles_corrupt_file(tmp_log_file):
    with open(tmp_log_file, "w", encoding="utf-8") as f:
        f.write("{not valid json")
    # 损坏文件返回空，不抛异常
    assert load_sent(tmp_log_file) == {}