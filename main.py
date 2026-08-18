import argparse
import os
import random
import sys
import time

from dotenv import dotenv_values

from src.api.client import BiliClient, BiliApiError, BiliNetworkError
from src.api.follow import get_live_follows
from src.api.gift import (
    get_medal_gift_price, send_medal_gift, GiftError, is_insufficient_balance,
)
from src.storage.sent_log import is_sent_today, mark_sent

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sent_log.json")
AUTH_FAIL_CODE = -101
MAX_CONSEC_AUTH_FAILS = 3


def parse_args():
    p = argparse.ArgumentParser(description="给在播主播送粉丝团灯牌")
    p.add_argument("--dry-run", action="store_true", help="只列出不实际送礼")
    p.add_argument("--min-interval", type=float, default=0.5, help="最小间隔秒（默认0.5）")
    p.add_argument("--max-interval", type=float, default=1.5, help="最大间隔秒（默认1.5）")
    return p.parse_args()


def load_cookies() -> dict:
    base = os.path.dirname(os.path.abspath(__file__))
    # 只读 .env 文件内容作为 cookie，不混入系统环境变量
    cookies = {k: v for k, v in dotenv_values(os.path.join(base, ".env")).items()
               if v and not k.startswith("__")}
    # 校验三个关键字段
    missing = [k for k in ("SESSDATA", "bili_jct", "DedeUserID") if not cookies.get(k)]
    if missing:
        print(f"错误：.env 缺少 {' / '.join(missing)}，请参考 .env.example 填写")
        sys.exit(1)
    return cookies


def main():
    args = parse_args()
    cookies = load_cookies()
    dede_uid = int(cookies["DedeUserID"])
    if not dede_uid:
        print("错误：.env 缺少 DedeUserID")
        sys.exit(1)

    with BiliClient(cookies=cookies) as client:
        # 1. 取在播列表
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 正在获取在播主播列表...")
        try:
            live_list = get_live_follows(client)
        except (BiliApiError, BiliNetworkError) as e:
            print(f"获取在播列表失败: {e}")
            return

        # 2. 去重
        skipped = []
        to_send = []
        for host in live_list:
            if is_sent_today(LOG_FILE, host["uid"]):
                skipped.append(host)
            else:
                to_send.append(host)

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 在播主播共 {len(live_list)} 个，"
              f"今日已送 {len(skipped)} 个，待送 {len(to_send)} 个"
              f"（间隔 {args.min_interval}-{args.max_interval}s）")

        # 3. 预演模式
        if args.dry_run:
            for h in to_send:
                print(f"  [预演] 将送：{h['uname']} (room {h['room_id']})")
            print("==== 预演结束（未实际送礼）====")
            return

        # 4. 取灯牌价格
        try:
            price = get_medal_gift_price(client)
            print(f"灯牌价格: {price} 金瓜子")
        except BiliApiError as e:
            print(f"获取灯牌价格失败: {e}")
            return

        # 5. 逐个送礼
        success = 0
        fail = 0
        stopped_for_balance = False
        stopped_for_auth = False
        consec_auth_fails = 0

        for i, host in enumerate(to_send):
            uid = host["uid"]
            uname = host["uname"]
            room_id = host["room_id"]
            tag = time.strftime("%H:%M:%S")
            try:
                send_medal_gift(client, uid=dede_uid, ruid=uid,
                                room_id=room_id, price=price)
                mark_sent(LOG_FILE, uid=uid, uname=uname,
                          room_id=room_id, status="success")
                print(f"[{tag}] ✓ {uname} (room {room_id}) 送灯牌成功")
                success += 1
                consec_auth_fails = 0
            except GiftError as e:
                if is_insufficient_balance(e):
                    mark_sent(LOG_FILE, uid=uid, uname=uname,
                              room_id=room_id, status="fail", error="余额不足")
                    print(f"[{tag}] ⛔ {uname} (room {room_id}) 余额不足，停止整轮")
                    stopped_for_balance = True
                    fail += 1
                    break
                mark_sent(LOG_FILE, uid=uid, uname=uname,
                          room_id=room_id, status="fail", error=e.message)
                print(f"[{tag}] ✗ {uname} (room {room_id}) 失败: {e.message}")
                fail += 1
                if e.code == AUTH_FAIL_CODE:
                    consec_auth_fails += 1
                    if consec_auth_fails >= MAX_CONSEC_AUTH_FAILS:
                        print("⛔ 连续鉴权失败，停止防呆，请检查 cookie")
                        stopped_for_auth = True
                        break
                else:
                    consec_auth_fails = 0
            except (BiliNetworkError, Exception) as e:
                mark_sent(LOG_FILE, uid=uid, uname=uname,
                          room_id=room_id, status="fail", error=str(e))
                print(f"[{tag}] ✗ {uname} (room {room_id}) 网络错误: {e}")
                fail += 1
                consec_auth_fails = 0

            # 间隔（最后一个不等）
            if i < len(to_send) - 1 and not stopped_for_balance and not stopped_for_auth:
                delay = random.uniform(args.min_interval, args.max_interval)
                time.sleep(delay)

        # 6. 汇总
        remaining = len(to_send) - success - fail
        print("==== 汇总 ====")
        print(f"成功: {success}  失败: {fail}  跳过(今日已送): {len(skipped)}"
              f"  因余额不足停止: {1 if stopped_for_balance else 0}"
              f"  剩余未送: {remaining}")


if __name__ == "__main__":
    main()