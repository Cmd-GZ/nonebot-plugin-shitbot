# /autoreply

**管理自动回复规则**

## 使用方式

### 开关自动回复

```bash
/autoreply start [--auto]
    开启自动回复。指定 --auto 后，bot 下次启动时将自动开启自动回复。

/autoreply stop [--auto]
    关闭自动回复。同时指定 --auto 将取消自动开启。
```

### 查看信息

```bash
/autoreply list <key|reply>
    列出所有关键词或回复。

/autoreply info <关键词名 ...>
    查看指定关键词的匹配规则详情。

/autoreply print <回复名 ...>
    预览指定回复的内容。
```

### 创建 / 删除

```bash
/autoreply create [--key <关键词名> ...] [--rp <回复名> ...]
    创建关键词和回复占位符。需要后续用 `key`/`reply` 子命令进一步设置。

/autoreply delete [--key <关键词名> ...] [--rp <回复名> ...]
    删除关键词和回复。其中删除回复时会级联移除其所有引用。
```

### 管理回复内容

```bash
/autoreply reply <回复名> start [-l <数量>]
    开始为指定回复收集内容。

/autoreply reply <回复名> stop
    停止收集，将所有已收集的内容保存为该回复。

/autoreply reply <回复名> modify [--sum <摘要> ...] [--st <类型> ...]
    修改已有回复中图片的信息。
```

### 编辑匹配规则

```bash
/autoreply key <关键词名> [选项...]
    编辑指定关键词的匹配规则。
```

## 选项

### start / stop

| 选项 | 说明 |
|------|------|
| `--auto` | 设置 / 取消 bot 启动时自动开启自动回复 |

### create / delete

| 选项 | 说明 |
|------|------|
| `--key <关键词名>` | 关键词 |
| `--rp <回复名>` | 回复名称 |

二者均可以多次出现。

### reply start

| 选项 | 说明 |
|------|------|
| `-l <数量>` | 所需收集的最大消息条数，达到后将自动 stop，默认为 1 |

### reply modify

| 选项 | 说明 |
|------|------|
| `--sum <摘要>` | 为消息中的图片设置 summary 字段。每张图片依次对应一个值；若指定数量少于图片数，剩余图片取最后一个值 |
| `--st <类型>` | 为消息中的图片设置 sub_type 字段。每张图片依次对应一个值；若指定数量少于图片数，剩余图片取最后一个值 |

二者均可以多次出现。前者设置的是图片在聊天界面外显示的文字，后者设置的是图片的子类型（通常0为图片，1为表情）。

### key

| 选项 | 说明 |
|------|------|
| `-T <变换方式>` | 增加变换规则 |
| `-t <变换方式>` | 移除变换规则 |
| `-D <子串>` | 增加去子串 |
| `-d <子串>` | 移除去子串 |
| `-K <关键词>` | 增加关键词 |
| `-k <关键词>` | 移除关键词 |
| `-R <回复名>` | 增加回复引用 |
| `-r <回复名>` | 移除回复引用 |
| `-m <匹配模式>` | 设置匹配模式 |

除 `-m` 外的选项均可多次出现，且大小写分别对应添加与移除

#### 变换方式

| 值 | 说明 |
|------|------|
| `delspace` | 去除文本中的所有空格 |
| `delmark` | 去除文本中的所有标点符号 |
| `upper` | 将文本转为大写 |
| `lower` | 将文本转为小写 |

变换将按选项出现的顺序依次执行。

#### 匹配模式 (`-m`)

| 值 | 说明 |
|------|------|
| `equal` | 文本与任一条关键词完全相等时匹配 |
| `contain` | 任一条关键词存在于文本中时匹配（子串匹配） |

## 示例

```bash
# 开启自动回复并设置为启动时自动开启
/autoreply start --auto

# 创建关键词和回复占位符
/autoreply create --key 你好 --key 再见 --rp greeting --rp goodbye

# 为 greeting 收集内容（最多 3 条）
/autoreply reply greeting start -l 3
(发送文字和图片...)
/autoreply reply greeting stop

# 为「你好」绑定 greeting：contain 模式，去除空格和标点
/autoreply key 你好 -T delspace -T delmark -m contain -R greeting

# 修改 goodbye 中图片的摘要
/autoreply reply goodbye modify --sum "拜拜~"

# 从「再见」的去子串列表中移除 "xxx"
/autoreply key 再见 -d xxx

# 预览 greeting 的内容
/autoreply print greeting

# 查看「你好」的规则详情
/autoreply info 你好

# 关闭自动回复并取消自动开启
/autoreply stop --auto
```

## 注意

- 使用该命令需要 `autoreplymanager` 条目权限
- `reply` 收集与存储的消息仅支持文字、图片和表情
- `reply start` 和 `reply stop` 需要在目标回复已通过 `create` 创建后使用
- `reply modify` 仅在目标回复已被设置内容后可用
- 规则修改后会自动刷新运行中的匹配引擎