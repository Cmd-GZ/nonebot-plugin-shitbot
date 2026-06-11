# /autoreply

**管理自动回复规则**

## 使用方式

### 开关自动回复

```bash
/autoreply start   开启自动回复
/autoreply stop    关闭自动回复
```

### 创建 / 删除

```bash
/autoreply create [选项...]
    创建关键词和消息文件。

/autoreply delete [选项...]
    删除关键词和消息文件。
```

### 管理消息内容

```bash
/autoreply value [选项...] <消息名>
    若指定 --start：开始为指定消息收集内容，之后发送的文字和图片都会被保存。
    若指定 --stop： 停止收集，将所有已收集的内容保存为一条消息。
    否则：修改已有消息中图片的 summary 和 sub_type。
```

### 编辑匹配规则

```bash
/autoreply key [选项...] <关键词>
    编辑指定关键词的匹配规则。未指定的选项将保持原值，指定空列表的选项
    将被清空。
```

## 选项

### value

| 选项 | 说明 |
|------|------|
| `--start` | 开始收集 |
| `--stop` | 停止收集 |
| `-l <数量>` | 所需收集的最大消息条数，达到后将自动 stop，默认为 1 |
| `--sum <摘要>` | 为消息中的图片设置 summary 字段。每张图片依次对应一个值；若指定数量少于图片数，剩余图片取最后一个值（可多次出现） |
| `--st <类型>` | 为消息中的图片设置 sub_type 字段。每张图片依次对应一个值；若指定数量少于图片数，剩余图片取最后一个值（可多次出现） |

### key

| 选项 | 说明 |
|------|------|
| `--tm <变换>` | 文本变换方式（可多次出现），可选值见下方 |
| `-d <子串>` | 从待检测文本中去除的子串（可多次出现） |
| `-m <模式>` | 匹配模式，可选值见下方，默认为 `equal` |
| `-v <消息名>` | 绑定的消息文件名称（可多次出现） |

### create / delete

| 选项 | 说明 |
|------|------|
| `-k <关键词>` | 关键词，操作规则（可多次出现） |
| `-v <消息名>` | 消息文件，操作消息（可多次出现） |

### 变换方式 (`--tm`)

| 值 | 说明 |
|------|------|
| `delspace` | 去除文本中的所有空格 |
| `delmarks` | 去除文本中的所有标点符号 |
| `uppercase` | 将文本转为大写 |
| `lowercase` | 将文本转为小写 |

变换将按选项出现的顺序依次执行。

### 匹配模式 (`-m`)

| 值 | 说明 |
|------|------|
| `equal` | 文本与关键词完全相等时匹配（默认） |
| `contain` | 关键词存在于文本中时匹配（子串匹配） |

## 示例

```bash
# 开启自动回复
/autoreply start

# 创建关键词和消息文件
/autoreply create -k 你好 -k 再见 -v greeting -v goodbye

# 为 greeting 消息收集内容（最多 3 条，含图片和文字）
/autoreply value --start -l 3 greeting
(发送文字和图片...)
/autoreply value --stop --sum "喵呜~" --st 1 greeting

# 为「你好」绑定 greeting：contain 模式，去除空格和标点
/autoreply key --tm delspace --tm delmarks -m contain -v greeting 你好

# 修改 goodbye 消息中图片的摘要
/autoreply value --sum "拜拜~" goodbye

# 清空「再见」关键词的去子串列表
/autoreply key -d 再见

# 关闭自动回复
/autoreply stop
```

## 注意

- 所有子命令均需要 `autoreplymanager` 条目权限
- `value` 收集与存储的消息仅支持文字和图片
- `value --start` 需要在目标消息文件存在时使用（即先通过 `create -v` 创建）
- 规则修改后会自动刷新运行中的匹配引擎