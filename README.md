# 粉丝团灯牌自动赠送工具

给 B 站关注列表里正在直播中的主播各送 1 个粉丝团灯牌，当日去重不重送。
支持按粉丝牌等级过滤，默认仅向粉丝牌 15 级及以上的主播送礼。

## 快速开始

1. 安装依赖：`pip install -r requirements.txt`
2. 首次运行：`python main.py --dry-run`
   - 若没有 `.env`（或 cookie 失效），会自动弹出终端二维码，用哔哩哔哩 APP 扫码登录
   - 登录成功后 cookie 自动写入 `.env`，下次运行直接复用
3. 重新登录：`python main.py --login`（强制重新扫码，覆盖旧 cookie）
4. 预演（不花钱验证）：`python main.py --dry-run`
5. 正式运行：`python main.py`

## 参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--dry-run` | 只列出不实际送礼 | 关 |
| `--login` | 扫码登录重新获取 cookie（覆盖 .env） | 关 |
| `--min-interval` | 最小送礼间隔秒 | 0.5 |
| `--max-interval` | 最大送礼间隔秒 | 1.5 |
| `--min-medal-level` | 粉丝牌最低等级才送礼，设 0 关闭过滤 | 15 |

## 登录说明

- 首次运行或 `.env` 缺失时自动触发扫码登录
- 终端打印 ASCII 二维码，用哔哩哔哩 APP 扫码并确认
- 登录成功后 cookie 存入 `.env`，后续运行自动复用，无需重复扫码
- cookie 失效时重新运行 `--login` 即可

## 本地记录

送礼结果存于 `sent_log.json`，按日期分组。当日已成功赠送的主播不会重送；
失败的主播当日可重试。跨天自动新建当日记录。

## 说明

- 仅送 `live_status==1`（直播中）的主播，轮播跳过
- 粉丝牌等级通过 `fansMedal/panel` 接口翻页获取全部粉丝牌，按 `--min-medal-level` 过滤
- 余额不足立即停止整轮
- 灯牌为付费礼物（gift_id=31164，约 1 元/个），请知悉

## 许可证

本项目基于 [AGPL-3.0](LICENSE) 协议开源。
