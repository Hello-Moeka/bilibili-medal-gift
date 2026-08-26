import argparse
import os
import random
import sys
import time

from dotenv import dotenv_values

from src.api.client import BiliClient, BiliApiError, BiliNetworkError
from src.api.follow import get_live_follows
from src.api.area import get_area_live_rooms
from src.api.gift import (
    get_medal_gift_price, send_medal_gift, GiftError, is_insufficient_balance,
)
from src.api.login import QrLogin, extract_dede_uid, BiliApiError as LoginError
from src.api.medal import (
    get_medal_levels, filter_by_min_level, filter_no_medal,
)
from src.storage.sent_log import is_sent_today, mark_sent

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sent_log.json")
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
AUTH_FAIL_CODE = -101
MAX_CONSEC_AUTH_FAILS = 3
# 写入 .env 的 cookie 字段白名单（其余无关 cookie 不存）
ENV_COOKIE_FIELDS = (
    "SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5",
    "buvid3", "buvid4", "buvid_fp", "fingerprint", "LIVE_BUVID",
    "bili_ticket", "bili_ticket_expires", "sid", "b_nut", "b_lsid",
)


def parse_args():
    p = argparse.ArgumentParser(description="给在播主播送粉丝团灯牌")
    p.add_argument("--dry-run", action="store_true", help="只列出不实际送礼")
    p.add_argument("--login", action="store_true", help="扫码登录重新获取 cookie")
    p.add_argument("--min-interval", type=float, default=0.5, help="最小间隔秒（默认0.5）")
    p.add_argument("--max-interval", type=float, default=1.5, help="最大间隔秒（默认1.5）")
    p.add_argument("--min-medal-level", type=int, default=None,
                   help="粉丝牌最低等级才送礼（默认：关注模式15，分区模式不过滤）")
    p.add_argument("--only-no-medal", action="store_true",
                   help="只给没有粉丝牌的主播送礼（与 --min-medal-level 互斥）")
    p.add_argument("--all-area", nargs="?", const=9, type=int, default=None,
                   metavar="PARENT_ID",
                   help="遍历指定父分区全部在播主播送礼（默认值 9=虚拟主播；"
                        "非预演会要求输入 yes 确认花费）")
    return p.parse_args()


def save_env(cookies: dict) -> None:
    """把 cookie 写入 .env 文件（KEY=VALUE 格式，仅存白名单字段）。"""
    lines = ["# B 站直播 cookie（扫码登录自动生成，勿提交）"]
    for key in ENV_COOKIE_FIELDS:
        val = cookies.get(key)
        if val:
            lines.append(f"{key}={val}")
    tmp = ENV_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, ENV_FILE)


def login_flow() -> dict:
    """命令行扫码登录，成功后写入 .env，返回 cookie dict。"""
    print("启动扫码登录...")
    login = QrLogin()
    try:
        login.generate()
        cookies = login.wait_for_login(timeout=180)
        save_env(cookies)
        print(f"\n登录成功，cookie 已写入 .env（DedeUserID={extract_dede_uid(cookies)}）")
        return cookies
    finally:
        login.close()


def load_cookies(force_login: bool = False) -> dict:
    base = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base, ".env")
    if not force_login and os.path.exists(env_path):
        cookies = {k: v for k, v in dotenv_values(env_path).items()
                   if v and not k.startswith("__")}
        missing = [k for k in ("SESSDATA", "bili_jct", "DedeUserID") if not cookies.get(k)]
        if not missing:
            return cookies
        print(f".env 缺少 {' / '.join(missing)}，转入扫码登录")
    return login_flow()


def main():
    args = parse_args()
    cookies = load_cookies(force_login=args.login)
    dede_uid = int(cookies.get("DedeUserID", 0) or 0)
    if not dede_uid:
        print("错误：登录后未获取到 DedeUserID")
        sys.exit(1)

    # 参数互斥校验；仅无牌模式下忽略等级阈值
    if args.only_no_medal and args.min_medal_level is not None:
        print("错误：--only-no-medal 与 --min-medal-level 互斥，请只传一个")
        sys.exit(1)

    # 粉丝牌等级阈值默认值：分区模式不过滤（0），关注模式 15
    min_level = 0 if args.only_no_medal else (
        args.min_medal_level if args.min_medal_level is not None
        else (0 if args.all_area is not None else 15))

    with BiliClient(cookies=cookies) as client:
        # 1. 取在播列表（关注列表 或 指定分区）
        if args.all_area is not None:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                  f"正在获取分区 {args.all_area} 全部在播主播（翻页较慢）...")
            try:
                live_list = get_area_live_rooms(client, parent_id=args.all_area)
            except (BiliApiError, BiliNetworkError) as e:
                print(f"获取分区列表失败: {e}")
                return
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 正在获取关注在播主播列表...")
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

        # 3. 粉丝牌过滤：仅无牌优先于等级阈值；两者皆无则不拉取
        if args.only_no_medal or min_level > 0:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 正在获取粉丝牌数据...")
            try:
                medal_levels = get_medal_levels(client)
            except (BiliApiError, BiliNetworkError) as e:
                print(f"获取粉丝牌等级失败: {e}")
                return
            if args.only_no_medal:
                to_send, filtered_out = filter_no_medal(to_send, medal_levels)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                      f"无粉丝牌 {len(to_send)} 个，跳过已有牌 {len(filtered_out)} 个")
            else:
                to_send, filtered_out = filter_by_min_level(
                    to_send, medal_levels, min_level)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                      f"等级达标 {len(to_send)} 个，过滤 {len(filtered_out)} 个")
            for h in filtered_out[:50]:
                print(f"  [跳过] {h['uname']} (room {h['room_id']}) — {h['reason']}")
            if len(filtered_out) > 50:
                print(f"  [跳过] ... 其余 {len(filtered_out) - 50} 个省略")

        # 4. 预演模式
        if args.dry_run:
            for h in to_send:
                print(f"  [预演] 将送：{h['uname']} (room {h['room_id']})")
            print("==== 预演结束（未实际送礼）====")
            return

        # 5. 取灯牌价格
        try:
            price = get_medal_gift_price(client)
            print(f"灯牌价格: {price} 金瓜子")
        except BiliApiError as e:
            print(f"获取灯牌价格失败: {e}")
            return

        # 5.5 分区模式大额花费确认（1 元 = 1000 金瓜子）
        if args.all_area is not None and not args.dry_run:
            est_yuan = price * len(to_send) / 1000
            print(f"⚠️  即将向分区 {args.all_area} 的 {len(to_send)} 个在播主播"
                  f"各送 1 个灯牌")
            print(f"    预计花费约 {est_yuan:.1f} 元（{price * len(to_send)} 金瓜子），"
                  f"不可撤销。输入 yes 继续：")
            ans = input().strip().lower()
            if ans != "yes":
                print("已取消，未送出任何礼物")
                return

        # 6. 逐个送礼
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

        # 7. 汇总
        remaining = len(to_send) - success - fail
        print("==== 汇总 ====")
        print(f"成功: {success}  失败: {fail}  跳过(今日已送): {len(skipped)}"
              f"  因余额不足停止: {1 if stopped_for_balance else 0}"
              f"  剩余未送: {remaining}")


if __name__ == "__main__":
    main()