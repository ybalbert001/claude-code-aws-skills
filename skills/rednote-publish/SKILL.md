---
name: rednote-publish
description: 将HTML文章渲染为手机视口长图，智能拆分为小红书3:4比例图片(1080x1440)，并通过xiaohongshu-mcp发布。在DOM块元素边界处拆分避免截断文字。当用户说"发小红书"、"转小红书图片"、"发布到小红书"、"rednote publish"、"把文章发到红书"时使用。
---

# RedNote Publish - HTML 文章转小红书图片 & 发布

将 HTML 长文章渲染为手机视口长图，在 DOM 块元素边界智能切割为多张 1080x1440 图片，经用户审核后通过 xiaohongshu-mcp 发布。

## 工作流程

### Step 1: 生成切图

```bash
cd skills/rednote-publish/scripts
python split_html_to_images.py <input.html> -o <output_dir>
```

首次使用需安装依赖：
```bash
pip install -r ../requirements.txt
playwright install chromium
```

### Step 2: 通过 xiaohongshu-mcp 发布

#### 2a. 启动 MCP 服务（如未运行）

MCP 服务不一定在运行，发布前需先确认。尝试调用 `check_login_status`，如果连接失败则需要启动服务：

```bash
cd skills/rednote-publish/xiaohongshu
./start_mcp.sh
```

启动后等待几秒，再调用 `check_login_status` 确认登录状态。如未登录，调用 `get_login_qrcode` 获取二维码让用户扫码。

#### 2b. 从 HTML 自动提取发布参数

从原始 HTML 内容中提取以下信息：

- **title**: 取 HTML 的 `<title>` 或第一个 `<h1>`/`<h2>` 的文本，精简到 20 字以内
- **content**: 提炼文章核心摘要，不超过 1000 字。不要包含 # 标签，标签通过 tags 参数传递
- **tags**: 从文章关键词中提取 3-5 个话题标签，如 `["Claude Code", "AI", "开源模型"]`

#### 2c. 调用 `publish_content` 发布

参数：
   - title: 自动提取的标题
   - content: 自动提取的摘要
   - images: 切图的本地绝对路径数组
   - tags: 自动提取的话题标签
   - visibility: **默认 `"仅自己可见"`**，相当于草稿，用户在 App 审核后手动改为公开
   - is_original: **默认 true**
   - schedule_at: 定时发布时间，ISO8601 格式如 `2024-01-20T10:30:00+08:00`（可选）

**可见范围说明：**

| visibility 值 | 效果 |
|---|---|
| `仅自己可见` | **默认**，相当于草稿，用户在 App 审核后手动改为公开 |
| `公开可见` | 直接公开发布 |
| `仅互关好友可见` | 仅互相关注的好友可见 |

默认 `仅自己可见` 是为了安全起见，用户审核满意后可在小红书 App 中修改可见范围为公开。如果用户明确要求直接公开发布，可将 visibility 设为 `公开可见`。

## 输入输出

| | 说明 |
|---|---|
| **输入** | HTML 文件（任意来源） |
| **输出** | `slide-1.png`, `slide-2.png`, ... 每张 1080x1440 |

## CLI 参数

```
python split_html_to_images.py <input> [-o output] [--target-height 1440] [--min-height 1000] [--viewport-width 1080] [--bg-color #ffffff]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input` | - | 输入 HTML 文件路径 |
| `-o` | ./output | 输出目录 |
| `--target-height` | 1440 | 每张图目标高度 |
| `--min-height` | 1000 | 最小切片高度（防止碎片） |
| `--viewport-width` | 1080 | 渲染视口宽度 |
| `--bg-color` | #ffffff | 短图补白背景色 |

## 切割逻辑

- 渲染完整长图后，获取所有块级元素（p, h1-h6, div, li, blockquote 等）的位置
- 在元素间隙处寻找切割点，目标每片 ~1440px
- 末尾短图自动补白到 1440px 保持一致
- 超长单一元素（如大代码块）保持完整不切割
