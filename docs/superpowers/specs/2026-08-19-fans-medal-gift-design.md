# 粉丝团灯牌自动赠送工具 — 设计方案

日期：2026-08-19
项目目录：`E:\OpenCode\擦擦牌子`
参考项目：`E:\OpenCode\B站批量送礼`（仅借鉴网络层思路，不依赖）

## 一、目标

单账号命令行工具，给 B 站关注列表里**正在直播中**（`live_status==1`，轮播跳过）的所有主播各送 1 个粉丝团灯牌。付费灯牌，`gift_id=31164`，走 `sendGold`。当日重复执行不重送（按本地记录去重），余额不足立即停止。

## 二、需求确认

| 项 | 决定 |
|---|---|
| 灯牌 | 付费，`gift_id=31164`，`sendGold`；price 从礼物配置动态取，不硬编码 |
| 在播判定 | `GetWebList` 翻页，只送 `live_status==1`，轮播(2)跳过 |
| 翻页停止 | `page` 从 1 向后翻，`page_size=10`，遇到第一个 `live_status!=1` 的主播停止翻页 |
| 去重 | JSON 按日期分组；执行前查当日已送（仅跳成功的），失败当日可重试 |
| 记录 | 送礼后记录送礼时间 `sent_at` + `status` + 失败原因 |
| 运行 | 纯命令行 Python 脚本；cookie 放项目目录 `.env` |
| 账号 | 单账号 |
| 错误处理 | 余额不足→立即停止整轮；普通失败→记录后继续；连续 3 次鉴权失败→停止防呆 |
| 送礼间隔 | 每个主播之间随机延迟 0.5–1.5 秒，防风控；命令行可调范围 |

## 三、架构与模块

```
擦擦牌子/
├── main.py                  # 入口：编排流程 + 命令行参数
├── .env.example             # cookie 配置模板（.env 被 .gitignore 排除）
├── .gitignore
├── requirements.txt         # httpx, python-dotenv
├── sent_log.json            # 运行时生成，按日期分组
└── src/
    ├── __init__.py
    ├── api/
    │   ├── __init__.py
    │   ├── client.py        # BiliClient：httpx 会话、UA 池、重试、cookie、CSRF
    │   ├── follow.py        # get_live_follows()：GetWebList 翻页，遇未开播停止
    │   └── gift.py          # get_medal_gift_price() + send_medal_gift() 走 sendGold
    └── storage/
        ├── __init__.py
        └── sent_log.py      # load/is_sent_today/mark_sent，原子写
```

每个模块单一职责，通过明确接口通信：`main.py` 调 `follow` 取在播 → 调 `sent_log` 过滤 → 对剩下的逐个调 `gift` → 每个结果调 `sent_log` 记录 → 打印汇总。`client.py` 是底层，不含业务逻辑。

## 四、数据流（主流程）

```
1. 加载 .env cookie → 构建 BiliClient
2. get_live_follows() 翻页取在播主播列表
3. 过滤：is_sent_today(uid) 为真的跳过
4. 对每个待送主播：
   a. get_medal_gift_price() 动态取灯牌 price
   b. send_medal_gift(uid, ruid, room_id, price) 走 sendGold
   c. 判定结果：
      - 成功 → mark_sent(success, sent_at)
      - 余额不足 → mark_sent(fail) + 立即停止整轮
      - 普通失败 → mark_sent(fail) + 继续；累计鉴权失败计数
      - 连续 3 次鉴权失败 → 停止防呆
   d. 随机延迟 0.5–1.5 秒后处理下一个
5. 汇总打印：成功/失败/跳过/因余额停止/剩余未送
```

## 五、本地记录与去重

**文件** — `sent_log.json`，按本地日期分组：

```json
{
  "2026-08-19": {
    "12345": { "uname": "主播A", "room_id": 67890, "sent_at": "2026-08-19 14:32:05", "status": "success" },
    "67890": { "uname": "主播B", "room_id": 11111, "sent_at": "2026-08-19 14:32:08", "status": "fail", "error": "余额不足" }
  }
}
```

- 键 = 主播 `uid`（字符串，JSON 键限制）；值含 `uname`、`room_id`、`sent_at`（本地 `YYYY-MM-DD HH:MM:SS`）、`status`、失败附 `error`。
- 跨天自动新建当日组，旧记录保留作历史，不清理。
- 原子写：写 `.tmp` 再 `os.replace`，防中途崩溃损坏。
- `is_sent_today(uid)`：当日组存在该 uid 且 `status==success` 才跳过；失败当日可重试。

## 六、错误处理

| 情形 | 判定 | 处理 |
|---|---|---|
| 余额不足 | code 命中已知余额码（如 `-403`）**或** message 含关键词（"余额不足"/"电池不足"等），命中任一 | **立即停止整轮**，跳出循环，该主播记 `fail`+`error=余额不足` |
| 普通失败 | 网络错误、礼物不可送、风控、房间异常等 | 记 `fail`+原因，继续下一个 |
| 鉴权失败 | `code=-101` 未登录等 | 记 `fail`，继续；**连续 3 次**则停止防呆，提示检查 cookie |
| 成功 | `code==0` | 记 `success`+`sent_at`，继续 |

余额不足识别用「code 命中已知余额码 **或** message 含关键词」双重判断，命中任一即判为余额不足并停止。已知余额关键词集合写在常量里，便于扩展。

停止后仍进入汇总打印，让用户知道停在哪个主播、还剩多少没送。

## 七、关键 API

**取在播列表** — `GET /xlive/web-ucenter/v1/xfetter/GetWebList?page={n}`，Cookie 鉴权。返回 `data.rooms[]`，每项含 `room_id`、`uid`、`uname`、`live_status`。从 page=1 起翻，遇首个 `live_status!=1` 停止。

**取灯牌价格** — 优先用全局礼物配置接口 `GET /xlive/web-room/v1/giftPanel/giftConfig?platform=pc&source=live`（不依赖房间），在 `data.list` 里按 `gift_id=31164` 找到 `price`，动态取值不硬编码。若全局接口未返回该礼物（少数房间禁用灯牌），回退用房间礼物列表 `roomGiftList?room_id={id}` 再找；都找不到则记 `fail`+`error=未找到灯牌礼物` 跳过该主播。

**送礼** — `POST /xlive/revenue/v1/gift/sendGold`，表单字段：`uid`(自己)、`gift_id=31164`、`gift_num=1`、`price`(动态取)、`coin_type=gold`、`ruid`(主播uid)、`biz_code=live`、`biz_id`(room_id)、`platform=pc`、`bag_id=0`、`storm_beat_id=0`、`send_ruid=0`、`rnd`(时间戳)、`visit_id=""`、`csrf`=`csrf_token`=`bili_jct`。参考项目 `send.py` 已验证此结构。

## 八、配置（`.env`）

```env
SESSDATA=你的SESSDATA
bili_jct=你的bili_jct
DedeUserID=你的UID
```

`.env.example` 提供模板，真实 `.env` 被 `.gitignore` 排除。`SESSDATA` 用于会话鉴权，`bili_jct` 做 CSRF，`DedeUserID` 是发送者 uid（送礼表单的 `uid` 字段）。

## 九、命令行与输出

```bash
python main.py                                       # 默认随机 0.5-1.5s 间隔
python main.py --dry-run                             # 预演，只列出会送的主播，不实际送礼
python main.py --min-interval 1 --max-interval 3     # 自定义随机延迟范围
```

运行时逐行打印进度，如：
```
[2026-08-19 14:32:05] 在播主播共 25 个，今日已送 8 个，待送 17 个（间隔 0.5-1.5s）
[14:32:06] ✓ 主播A (room 67890) 送灯牌成功
[14:32:09] ✗ 主播B (room 11111) 失败: 该礼物仅限从包裹中送出
[14:32:12] ⛔ 主播C (room 22222) 余额不足，停止整轮
==== 汇总 ====
成功: 3  失败: 2  跳过(今日已送): 8  因余额不足停止: 1  剩余未送: 14
```

`--dry-run` 模式用于真实 cookie 下的安全预演（不花钱验证流程）。

## 十、依赖

```
httpx>=0.27.0
python-dotenv>=1.0.0
```

## 十一、测试

- 网络层用 mock（mock httpx 响应）测：翻页停止逻辑、余额不足识别、去重过滤。
- 记录层测：原子写、跨天分组、只跳成功不跳失败。
- `--dry-run` 模式用于真实 cookie 下的安全预演（不花钱验证流程）。