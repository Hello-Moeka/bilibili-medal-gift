# 粉丝团灯牌自动赠送工具

给 B 站关注列表里正在直播中的主播各送 1 个粉丝团灯牌，当日去重不重送。

## 快速开始

1. 复制 `.env.example` 为 `.env`，填入你的 `SESSDATA`、`bili_jct`、`DedeUserID`
   （从浏览器登录 B 站直播后，开发者工具 → Application → Cookies 获取）
2. 安装依赖：`pip install -r requirements.txt`
3. 预演（不花钱验证）：`python main.py --dry-run`
4. 正式运行：`python main.py`

## 参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--dry-run` | 只列出不实际送礼 | 关 |
| `--min-interval` | 最小送礼间隔秒 | 0.5 |
| `--max-interval` | 最大送礼间隔秒 | 1.5 |

## 本地记录

送礼结果存于 `sent_log.json`，按日期分组。当日已成功赠送的主播不会重送；
失败的主播当日可重试。跨天自动新建当日记录。

## 说明

- 仅送 `live_status==1`（直播中）的主播，轮播跳过
- 余额不足立即停止整轮
- 灯牌为付费礼物（gift_id=31164，约 1 元/个），请知悉