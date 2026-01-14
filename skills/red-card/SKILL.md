---
name: red-card
description: 根据输入文案自动生成小红书风格图片卡片。自动拆分文案(300-400字/页)、搜索YouTube获取热门视频截图作为封面、渲染PNG图片。使用场景：当用户请求"生成小红书图片"、"把文案转成小红书卡片"、"制作红书帖子"或提到"red card"时使用。
---

# Red Card - 小红书图片卡片生成器

将长文案自动转换为小红书风格图片卡片。核心原则：**只拆分，不编辑**。

## 快速开始

```bash
cd red-card/scripts
python generate_cards.py content.md --keyword "AI模型" --output ./output
```

**首次使用需安装依赖：**
```bash
pip install -r requirements.txt
playwright install chromium
```

## 输入输出

**输入：**
1. 文案文件 (Markdown/纯文本)
2. YouTube搜索关键词
3. 输出目录 (可选)

**输出：**
- `cover.png` - 封面图 (YouTube截图 + 标题 + 引言)
- `page-1.png`, `page-2.png`... - 正文页

## 文案格式

```markdown
# 大标题（封面图标题）

引言段落，1-2句概括全文。（封面图引言）

## 小标题一（新页面起点）

正文内容...

## 小标题二

- 列表项一
- 列表项二
```

## 拆分规则

1. `#` 行 → 封面标题
2. 标题后首段 → 封面引言
3. `##` 小标题 → 新页面分割点
4. 每页控制在300-400字
5. 在句子边界处分割，保持完整性

## 图片规格

- 尺寸: 1242 × 1660px (3:4)
- 封面: 上半部YouTube截图 + 下半部标题引言
- 正文: 白底黑字，小标题加粗

## 文件结构

```
red-card/
├── SKILL.md
├── assets/
│   ├── cover.html          # 封面模板
│   ├── content.html        # 正文模板
│   └── xiaohongshu.css     # 样式
└── scripts/
    ├── generate_cards.py   # 主脚本
    ├── text_splitter.py    # 文案拆分
    ├── youtube_thumbnail.py # YouTube截图
    └── requirements.txt
```

## 命令行参数

```
python generate_cards.py <input> -k <keyword> [-o <output>] [--account <id>] [--max-chars <n>]

参数:
  input              输入文案文件
  -k, --keyword      YouTube搜索关键词 (必需)
  -o, --output       输出目录 (默认: ./output)
  --account          小红书账号水印 (默认: 26294572818)
  --max-chars        每页最大字符数 (默认: 400)
```
