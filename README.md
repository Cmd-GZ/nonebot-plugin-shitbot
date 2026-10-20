# Shitbot

这项目目前是我自用的基于Napcat端的QQ机器人插件，正在逐步完善中

该插件依赖于Napcat端，目前暂不对其他端进行适配

## 已实现的功能

- 调用ffmpeg将图片转成视频或者添加黑框，使得某些由于各种原因在群里发不出去的图片可以被转换后发送

- 随机二次元图片

- 给定 PID 获取P站图片

- B站视频解析与下载

- 全自动搬史

- Markdown渲染

- 用户多命令管理

- 参数解析(见docs/参数解析.md)

- 权限管理系统(见docs/权限系统.md)

- 信息处理函数库(msgutils) 涵盖对信息对象的转换、处理、发送 运用函数式方案处理信息

- 手搓信息管理数据库
  - 数据库由两部分组成: msgs以及medias
  - msgs用于存储信息 通过将 Message 转化为 DumpedMsg 后以 yaml 格式存储
    -  文件名为该文件的sha256sum值 通过比较文件名去重
    -  维护一个映射表（的yaml文件） 用于记录信息的引用数（由数据库用户维护） 通常若信息的引用数为0 则删除信息
  - medias用于msgs中信息中可能存在的多媒体文件
    -  文件名为该文件的sha256sum值 通过比较文件名去重
    -  维护一个映射表（的yaml文件） 用于记录文件的引用数（只会被msgs中的信息引用 因此仅由数据库本身维护） 通常若文件的引用数为0 则删除文件

- 自动回复系统

## TODO List（大致按优先级排序 但随缘想先解决哪个就解决哪个）

- 添加单元测试 （技术债务这块 最讨厌的一集 想写哪个就写哪个）

- 为代码添加更多注释和写文档 （依旧技术债务 依旧最烦 依旧随缘）

- 错误处理（同上）

- 暂时想到这些 哪天我又有什么点子也说不定（6.12更新：一个月下来能看到 TODO List 越来越少还是挺感慨的 为什么补上这条括号内容？因为上面的项我都加了 这条不加我会犯强迫症）

## 配置

插件配置通过 NoneBot 标准的 dotenv / 环境变量读取。

### 安装

#### 本体

```bash
nb plugin install nonebot-plugin-shitbot
```

#### 依赖

##### ffmpeg

`/convert`、`/bilibili`、`/au2rc` 等命令依赖其进行媒体处理

```bash
# Arch系
pacman -S ffmpeg
# Debian系
apt install ffmpeg
# macOS
brew install ffmpeg
# RedHat系（需先启用 RPM Fusion；ffmpeg-free 缺少 libx264，/convert 用不了）
dnf install ffmpeg
# Windows
# 从 https://ffmpeg.org/download.html 下载后加入 PATH
```

##### libmagic

`/convert`, `/md2pic` 等命令依赖其进行文件类型识别

```bash
# Arch系
pacman -S file
# Debian系
apt install libmagic1
# macOS
brew install libmagic
# RedHat系
dnf install file-libs
# Windows
# 无需安装
```

##### Playwright

`/help`, `/md2pic` 等命令依赖其进行浏览器渲染

```bash
playwright install chromium
# 若下载速度过慢可考虑指定镜像源
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright playwright install chromium
```

### 环境变量

在 NoneBot 项目的 `.env` 文件中配置，变量如下：

| 配置项 | 类型 | 默认值 | 是否必填 | 说明 |
|---|---|---|---|---|
| `SHITBOT__OWNERS` | JSON 字符串列表 | None | **是** | 机器人所有者 QQ 号列表，如 `'["114514"]'`。未配置时 owners 组为空且无法正常使用bot |
| `SHITBOT__CLIENT_CACHE` | 路径 | 本地缓存路径 | 否 | 容器端缓存路径。本地缓存路径为 `$LOCALSTORE_CACHE_DIR/nonebot_plugin_shitbot`，容器端需对应挂载 |
| `SHITBOT__CLIENT_DATA` | 路径 | 本地数据路径 | 否 | 容器端数据路径。本地数据路径为 `$LOCALSTORE_DATA_DIR/nonebot_plugin_shitbot`，容器端需对应挂载 |
| `SHITBOT__CLIENT_QQ_ROOT` | 路径 | 原路径（不映射） | 否 | 容器端 QQ 数据根目录，如 `/app/.config/QQ`。需与 `SHITBOT__QQ_ROOT` 成对配置 |
| `SHITBOT__QQ_ROOT` | 路径 | 原路径（不映射） | 否 | 宿主机端 QQ 数据根目录，如 `/home/user/docker/QQ`。用于读取协议端报告的本地路径（如 `get_record` 返回的语音文件） |
| `SHITBOT__MAX_MESSAGE_DEPTH` | 整数 | `16` | 否 | 消息解析最大递归深度 |
| `SHITBOT__PIXIV_ACCESS_TOKEN` | 字符串 | "" | 部分必填 | Pixiv API 访问令牌（使用 `/pixiv` 时必填） |
| `SHITBOT__BILIBILI_COOKIE` | 字符串 | "" | 否 | B站登录 Cookie，形如 `SESSDATA=xxx%2Cyyy; bili_jct=zzz`。带上可显著降低 `/bilibili` 被风控的概率且允许下载1080p视频 |

### 触发规则

| 命令 | 说明 |
|---|---|
| `/session` | 会话管理 |
| `/perm` | 权限管理 |
| `/help` | 查看帮助 |
| `/randpic` | 随机二次元图片 |
| `/涩图` | `/randpic` 的别名 |
| `/pixiv` | P站图片检索 |
| `/bilibili` | B站视频解析与下载 |
| `/convert` | 图片格式转换 |
| `/au2rc` | 音频文件转语音发送 |
| `/shitpost` | 全自动搬史服务与数据库(~~化粪池~~)管理 |
| `/md2pic` | Markdown 渲染为图片 |
| `/autoreply` | 自动回复服务与数据库管理 |

## 鸣谢

- [ManyACG](https://manyacg.top): 为 /randpic ~~*以及下面的彩蛋*~~ 提供了API
- [Lolicon APP](https://lolicon.app): 为 /randpic 提供了API
- [yt-dlp](https://github.com/yt-dlp/yt-dlp): 为 /bilibili 提供视频解析与下载
- [katex](https://katex.org/): 为 /md2pic 提供了数学公式渲染
- [github-markdown-css](https://github.com/sindresorhus/github-markdown-css): 为markdown渲染提供了CSS主题

###### 彩蛋: 千人千面(据说每个人看到的图都不一样):
![pic](https://manyacg.top/setu)