# /shitpost

**把消息存进「史库」，再自动或手动转发到多个群聊**

## 使用方式

```bash
/shitpost start [选项]                 启动搬运服务
/shitpost stop  [选项]                 停止搬运服务

/shitpost add begin [群号...]          开始收集消息入库
/shitpost add end                      结束收集

/shitpost set   [选项]                 修改目标群列表与转发间隔
/shitpost mark  [选项] [sha256...]     修改某条史的「已发送群组」
/shitpost del   [选项] [sha256...]     删除库中的史
/shitpost send  [选项] [sha256...]     立即把库中的史发出去
/shitpost check [sha256...]            检查库中是否存在这些史
/shitpost status                       查看当前状态
```

带 `sha256` 的命令都可以**回复**一条消息来代替手打哈希。

## 选项

| 选项 | 用于 | 说明 |
|------|------|------|
| `--auto` | `start` / `stop` | 是否在 Bot 启动时自动开启服务 |
| `--min <秒>` | `set` | 转发间隔下限 |
| `--max <秒>` | `set` | 转发间隔上限 |
| `-a <群号>` | `set` / `mark` | 添加群号（可重复出现） |
| `-d <群号>` | `set` / `mark` | 删除群号（可重复出现） |
| `--to <群号>` | `send` | 发送目标群号（可重复出现） |
| `--sent` | `del` | 删除「已经发给所有目标群」的史 |
| `--failed <次数>` | `del` | 删除失败次数大于等于该值的史 |
| `--before <DD:HH:MM:SS>` | `del` | 删除入库时间早于该时长的史 |

## 各命令说明

### start / stop

启动 / 停止搬运服务。**必须先 `start`，Bot 才会开始自动转发。**

启动后，Bot 会为**每个目标群**各自维护一条定时器，每隔 `min~max` 之间的一个随机秒数，挑一条史发到那个群。

不带 `--auto` 时不会改变「开机自启」的设置：

| 命令 | 效果 |
|------|------|
| `/shitpost start --auto` | 启动服务，并设置开机自动启动 |
| `/shitpost start` | 只启动服务 |
| `/shitpost stop --auto` | 停止服务，并取消开机自动启动 |
| `/shitpost stop` | 只停止服务 |

### add begin / add end

`add begin` 之后，你发给 Bot 的消息都会被存进史库；`add end` 结束收集。

`add begin` 后面可以跟群号（可省略）。**这些群号会被标记为「这条史已经发过」，即新入库的史不会立刻转发给它们。**

```bash
/shitpost add begin            开始收集，新史没有已发送记录
/shitpost add begin 123456     开始收集，且新史视为已发给 123456
(发送消息...)
/shitpost add end
```

每条史入库后 Bot 会回复它的 `sha256`（哈希），后续可以用它来查找、发送或删除。

### set

修改目标群列表与转发间隔。三者可以同时改，也可以只改其中一项。

```bash
/shitpost set -a 123456 -a 789012        添加两个群
/shitpost set -d 123456                  移除一个群
/shitpost set --min 60 --max 300         设置转发间隔为 60~300 秒
```

### mark

修改指定史的「已发送群组」列表，用于让某条史重新/停止参与某些群的转发。

```bash
/shitpost mark -a 123456 <sha256>        让这条史视为已发给 123456
/shitpost mark -d 123456 <sha256>        从已发送列表里移除 123456，它会被重新转发
```

### del

删除库中的史。可以同时给多个筛选条件，**满足任意一条就会被删除**。

```bash
/shitpost del <sha256>                   删除指定的一条
/shitpost del --sent                     删除已经发给所有目标群的史
/shitpost del --failed 3                 删除失败 3 次及以上的史
/shitpost del --before 7:0:0:0           删除 7 天前入库的史
```

回复一条消息也能删除：

```bash
(回复某条史) /shitpost del
```

### check

检查库中是否存在对应的史。回复一条消息时，若它在库中会一并回复它的哈希。

```bash
/shitpost check <sha256>
(回复某条史) /shitpost check
```

### send

立即把库中的史发出去，不受转发定时器限制。

```bash
/shitpost send                           随机抽一条发到当前聊天
/shitpost send <sha256>                  把指定的史发到当前聊天
/shitpost send --to 123456               随机抽一条发到指定群
/shitpost send --to 123456 <sha256>      把指定的史发到指定群
```

不写 `sha256` 时，Bot 会从库中随机抽取一条。

| 发送目标 | 行为 |
|------|------|
| 不带 `--to` | 发到当前聊天；发送后视为「已发给该群」（私聊除外） |
| 带 `--to` | 发到 `--to` 指定的每个群（Bot 不在的群会跳过），发送后均视为「已发给这些群」 |

「已发给某群」意味着调度器之后不会再自动把这条史转发给那个群。即使那个群当前不在目标群列表中，这个标记也会被记下——所以手动发过一次的群，将来被加进目标列表时也不会再收到这条史。

### status

查看当前状态：库内存量、目标群列表、转发间隔。

```bash
/shitpost status
```

## 示例

```bash
# 建立两个目标群，每 1~5 分钟转发一条
/shitpost set -a 123456 -a 789012 --min 60 --max 300

# 开始收集，并把这批史视为已发给 123456
/shitpost add begin 123456
(发送若干条消息...)
/shitpost add end

# 启动服务（不改变开机自启设置）
/shitpost start

# 看看当前状态
/shitpost status

# 手动补发一条到 789012
/shitpost send --to 789012 <sha256>

# 停止服务，并让 Bot 开机时不再自动启动
/shitpost stop --auto
```

## 权限

`/shitpost` 分为两档，都需要对应权限条目通过（条目说明见 `/help perm`）：

| 权限条目 | 可用范围 |
|------|------|
| `shitpost` | 只能使用 `/shitpost send`，且只能发给当前聊天 |
| `shitpost` + `shitpostmanager` | 全部子命令；`send` 额外可以用 `--to` 指定群聊 |

`shitpostmanager` 默认为用户/群组白名单，首次使用前需要先把自己加进白名单组。

> 权限不足时 `/shitpost send --to <群号>` **不会报错**：`--to` 会被直接忽略，消息照常发到**当前聊天**。需要指定群聊时请先确认自己有 `shitpostmanager` 权限。

## 注意

- 此命令通常只会在私聊下被使用，但仍可通过`/perm`命令修改权限实现在群聊使用
- **Bot 必须已经在目标群里**；不存在的群号会被自动剔除并提示
- 同一个群号在 `-a` / `-d` / `--to` 中**每次只能跟一个值**，多个群号要重复写选项：
  ```bash
  /shitpost set -a 123456 -a 789012     正确
  /shitpost set -a 123456 789012        错误，789012 会被当成别的参数
  ```
- `sha256` 等自由参数必须写在所有选项**之后**：
  ```bash
  /shitpost del --before 7:0:0:0 <sha256>     正确
  /shitpost del <sha256> --before 7:0:0:0     错误
  ```
- `add begin` 后给出的群号只影响**本次收集的史**，不会改动已在库中的史
- 转发时会**优先挑选较新的史**；转发失败的史被选中的概率会大幅下降，反复失败的会被跳过
- 哈希为 64 位十六进制，不建议手打，用回复的方式指定更方便
