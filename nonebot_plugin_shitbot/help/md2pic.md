# /md2pic

**将 Markdown 文本转换为图片输出**

## 使用方式

```bash
[回复消息]/md2pic  < -c > [选项] (换行)
         [markdown文本]
```

## 选项

| 选项 | 说明 |
|------|------|
| `-c` | 占位符，用于分割参数项与 Markdown 正文，为必填项 |
| `-s <倍率>` | 设置缩放倍率，可填小数，数值越大生成的图片越清晰，数值应在 1~50 之间，默认为 2 |
| `-t <渲染主题>` | 指定渲染主题，默认为 `github-markdown-dark-dimmed` |
| `--padding <留空像素>` | 设置渲染结果四周留空的宽度像素，默认为 30 |
| `--min_w <宽度像素>` | 设置最小宽度像素，默认为 20 |
| `--max_w <宽度像素>` | 设置最大宽度像素，该值会影响 Markdown 排版，默认为 2000 |
| `--min_h <高度像素>` | 设置最小高度像素，默认为 20 |
| `--max_h <高度像素>` | 设置最大高度像素，默认为无限 |

**注意**：`--padding`、`--min_w`、`--max_w`、`--min_h`、`--max_h` 均只能填入正整数。

## 示例

### 示例 1:

**按默认参数输出 Markdown 文本**

```bash
/md2pic -c
# Title
Hello World
```

> **输出:**
>
> ![img](./imgs/md2picex1.png)

### 示例 2

**按缩放倍率 5.14，用 github-markdown-dark-dimmed 主题输出行间公式**

```bash
/md2pic -s 5.14 -c -t github-markdown-dark-dimmed
$$
天^{-1}\in\R\\
\text{属实逆天}
$$

```
> **输出:**
>
> ![img](./imgs/md2picex2.png)

### 示例 3

###### > 回复一条包含文本的信息或一个文本文件

```bash
/md2pic -c
```

> **输出:**
>
> *被回复的消息被渲染后的图片*
