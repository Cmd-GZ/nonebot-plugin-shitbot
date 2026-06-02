# /perm

**管理 bot 的权限系统**

## 使用方式

### 普通用户自查

```bash
/perm check
```

### 查看列表

```bash
/perm list -t <user|group|entry> [--all]
```

### 查看信息

```bash
/perm info [-U <组名> ...] [-G <组名> ...] [-E <条目名> ...]
```

### 增减权限组

```bash
/perm create [-U <组名> ...] [-G <组名> ...]
/perm delete [-U <组名> ...] [-G <组名> ...]
```

### 添加 / 移除成员

```bash
/perm add    [-U <组名> ...] [-G <组名> ...] [-u <用户ID> ...] [-g <群组ID> ...]
/perm remove [-U <组名> ...] [-G <组名> ...] [-u <用户ID> ...] [-g <群组ID> ...]
```

第 i 个出现的 `-U`/`-G` 对应第 i 个出现的 `-u`/`-g`。

### 管理权限条目

**开关白名单模式：**
```bash
/perm entry -t <user|group> whitelist -s <on|off> <条目名...>
```

**增减白名单/黑名单权限组：**
```bash
/perm entry -t <user|group> whites [-A <权限组名> ...] [-R <权限组名> ...] <条目名...>
/perm entry -t <user|group> blacks [-A <权限组名> ...] [-R <权限组名> ...] <条目名...>
```

## 选项与参数

| 选项 / 参数 | 说明 |
|---|---|
| `check` | 查看当前用户的权限状态 |
| `list` | 列出指定类型的所有项 |
| `info` | 查看指定项的详细信息 |
| `create` / `delete` | 创建 / 删除权限组 |
| `add` / `remove` | 向权限组添加 / 移除成员 |
| `entry` | 管理权限条目 |
| `whitelist` | 开关白名单模式 |
| `whites` / `blacks` | 增减白名单 / 黑名单权限组 |
| `-t <类型>` | `user`（用户权限组）、`group`（群组权限组）、`entry`（权限条目） |
| `-U <组名>` | 用户权限组名称（可多次出现） |
| `-G <组名>` | 群组权限组名称（可多次出现） |
| `-E <条目名>` | 权限条目名称（可多次出现） |
| `-u <用户ID>` | 用户 ID（可多次出现） |
| `-g <群组ID>` | 群组 ID（可多次出现） |
| `-s <on\|off>` | 开关状态 |
| `-A <权限组名>` | 将被添加的权限组（可多次出现） |
| `-R <权限组名>` | 将被移除的权限组（可多次出现） |
| `--all` | 输出详细信息 |

## 示例

```bash
# 查看自己的权限
/perm check

# 查看所有用户权限组
/perm list -t user

# 查看用户权限组 nsfw 和群组权限组 setu 的详细信息
/perm info -U nsfw -G setu

# 创建用户权限组 nsfw 和群组权限组 vip_groups
/perm create -U nsfw -G vip_groups

# 将用户 123456 添加到 nsfw 和 convert 组
/perm add -U nsfw -U convert -u 123456 -u 123456

# 将群组 789012 添加到 setu 组
/perm add -G setu -g 789012

# 关闭 setu 条目的用户白名单模式
/perm entry -t user whitelist -s off setu

# 向 setu 条目的用户白名单中添加 nsfw 组
/perm entry -t user whites -A nsfw setu
```

## 注意

- `/perm check` 仅需 `perm` 条目权限
- 除 `check` 外的所有子命令需要 `permmanager` 条目权限，或用户在 `owners` 组中
- 非 `owners` 组用户无法修改 `admins` 和 `owners` 用户权限组
- 删除 `owners` 组后原 `owners` 用户将失去对应权限，且不能再通过 `/perm` 恢复，需手动编辑 `config.yaml` 恢复