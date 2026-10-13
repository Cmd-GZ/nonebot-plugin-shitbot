# /bilibili

**解析并下载 B 站视频**

## 使用方式

```bash
/bilibili [链接或 av 号或 BV 号 ...]
```

### 支持的输入

| 形式 | 示例 |
|------|------|
| BV 号 | `BV1GJ411x7h7` |
| av 号 | `av170001` |
| 视频链接 | `https://www.bilibili.com/video/XXXXXX` |
| 短链 | `https://b23.tv/xxxxxxx` |

可以一次给出多个，Bot 会按顺序逐个处理。

也可以回复一条包含 B 站链接或分享卡片的消息，再发送 `/bilibili`，Bot 会自动从被回复的消息中提取链接。

收到链接后，Bot 会先发送视频信息（标题、UP主、BV 号、封面），再发送视频本体。

## 示例

```bash
/bilibili BV1GJ411x7h7
/bilibili https://www.bilibili.com/video/BV1GJ411x7h7
/bilibili BV1GJ411x7h7 BV1uv411q7Mv

# 回复一条含 B 站链接的消息
/bilibili
```

## 注意

- 使用该命令需要 `bilibili` 权限条目通过
