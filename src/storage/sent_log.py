import json
import os
import time
import threading

_lock = threading.RLock()


def today_str() -> str:
    return time.strftime("%Y-%m-%d")


def load_sent(path: str) -> dict:
    """加载整个记录。文件不存在或损坏返回 {}。"""
    with _lock:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}


def is_sent_today(path: str, uid: int) -> bool:
    """当日组存在该 uid 且 status==success 才返回 True（失败可重试）。"""
    with _lock:
        data = load_sent(path)
        today = today_str()
        rec = data.get(today, {}).get(str(uid))
        return rec is not None and rec.get("status") == "success"


def mark_sent(path: str, uid: int, uname: str, room_id: int,
              status: str, error: str = "") -> None:
    """写入当日组，含 sent_at 时间戳，原子写。"""
    with _lock:
        data = load_sent(path)
        today = today_str()
        if today not in data:
            data[today] = {}
        record = {
            "uname": uname,
            "room_id": room_id,
            "sent_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
        }
        if error:
            record["error"] = error
        data[today][str(uid)] = record
        _atomic_write(path, data)


def _atomic_write(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)