# /convert

**收集图片并批量处理后发送**

## 使用方式

```bash
/convert [选项] start   开始批量收集图片
                        之后你发送的所有图片都会被 Bot 保存
/convert stop           停止收集，将图片转为特定形式并发送

/convert [选项] reply   转换被回复消息里的图片
```

## 选项

| 选项 | 说明 |
|------|------|
| `-m <模式>` | 转换模式，默认为 `video` |

### 模式说明

| 模式 | 说明 |
|------|------|
| `video` | 将图片转换为视频发送 |
| `frame` | 为图片添加黑框后发送 |

## 示例

```bash
# 边收边攒，最后一起转换
/convert start
(发送图片...)
/convert stop

# 直接转换被回复的消息
(回复一条带图的消息) /convert reply
(回复一条带图的消息) /convert -m frame reply

# 换模式
/convert -m frame start
(发送图片...)
/convert stop
```

## 注意

- 此命令通常只会在私聊下被使用，但仍可通过`/perm`命令修改权限实现在群聊使用
- 发送视频时，若视频发送失败，Bot 会尝试以文件的形式发送
