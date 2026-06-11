# Shitbot

这项目目前是我自用的基于Napcat端的QQ机器人插件，正在逐步完善中

## 已实现的功能

- 调用ffmpeg将图片转成视频或者添加黑框，使得某些由于各种原因在群里发不出去的图片可以被转换后发送

- 随机二次元图片

- 给定 PID 获取P站图片

- 半自动搬史

- Markdown渲染

- 用户多命令管理

- 权限管理系统(见docs/权限系统.md)

## TODO List（大致按优先级排序 但随缘想先解决哪个就解决哪个）

- B站视频解析并下载（支持链接块或者BV号）

- 添加单元测试

- 实现 /stop 用于终止当前会话

- 为代码添加更多注释 并按照nonebot所说的插件规范修改代码（？）

- 手搓数据库 用于自动回复系统以及搬史系统
  - 数据库由两部分组成: messages以及medias
  - messages用于存储信息 通过将 Message 转化为 DumpedMsg 后以 yaml 格式存储
    -  文件名为该文件的sha256sum值 通过比较文件名去重
    -  维护一个映射表（的yaml文件） 用于记录信息的引用数（由数据库用户维护） 通常若元信息的引用数为0 则删除元信息
  - medias用于messages中信息中可能存在的多媒体文件
    -  文件名为该文件的sha256sum值 通过比较文件名去重
    -  维护一个映射表（的yaml文件） 用于记录文件的引用数（只会被messages中的信息引用 因此仅由数据库本身维护） 通常若元信息的引用数为0 则删除元信息

- 基于上一点重构 /autoreply

- 智能化/shitpost
  - 使用用上面提到的数据库 
  - 添加一个元信息映射表（yaml） 类型大概是Dict[str, Dict[str, Any]] 键是史的文件名 也就是哈希值 值中保存着史的：real_id列表 时间戳 好评数 发送失败次数 存储着已经发送过该史的群号的列表

  - 维护一个yaml文件用于记录各个real_id对应的史的哈希值

  - 根据以上信息我瞎编了一个可能有用的发史优先级公式：

    $$
    \begin{aligned}
    \small{50 - \frac{100}{\pi}\arctan\left(c_1时间戳 - f(好评数) + c_2 e^{c_3发送失败次数} + \infty\mathbb1_{已经发送过该史的群号}(将要发送史的群号) + \text{random}(0, 最新的史的时间戳与最旧的史的时间戳之差)\right)}
    \end{aligned}
    $$

- 暂时想到这些 哪天我又有什么点子也说不定

## 配置

插件启动时会自动从插件目录下的 `default_config.yaml` 复制默认配置到 `config.yaml`，
之后编辑 `config.yaml` 即可。

### 安装

```bash
nb plugin install nonebot-plugin-shitbot
```

### 首次部署必填项

| 配置项 | 类型 | 说明 |
|---|---|---|
| `bot_base` | 路径 | 插件的持久存储根目录（cache / data / config / 均存放于此） |
| `client_base` | 路径 | 客户端侧的持久存储根目录（用于兼容容器部署） |
| `owners` | 字符串列表 | 机器人所有者 QQ 号列表 |
| `pixiv_access_token` | 字符串 | Pixiv API 访问令牌（可选填，使用 `/pixiv` 时必填） |

### 触发规则

| 命令 | 说明 |
|---|---|
| `/session` | 会话管理 |
| `/perm` | 权限管理 |
| `/help` | 查看帮助 |
| `/randpic` | 随机二次元图片 |
| `/advrandpic` | 高级随机图片 |
| `/pixiv` | P站图片检索 |
| `/convert` | 图片格式转换 |
| `/shitpost` | 搬史 |
| `/md2pic` | Markdown 渲染为图片 |
| `/autoreply` | 自动回复管理 |

## 鸣谢

- [ManyACG](https://manyacg.top): 为 /randpic ~~*以及下面的彩蛋*~~ 提供了API
- [Lolicon APP](https://lolicon.app): 为 /advrandpic 提供了API
- [github-markdown-css](https://github.com/sindresorhus/github-markdown-css): 为markdown渲染提供了CSS主题

###### 彩蛋: 千人千面(据说每个人看到的图都不一样): 
![pic](https://manyacg.top/setu)