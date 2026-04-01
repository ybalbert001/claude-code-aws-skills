# API 配置指南

生成封面图和内容配图统一通过 OpenRouter 调用，支持两个模型。

## 环境变量

只需设置一个环境变量：

```bash
# Linux/Mac
export OPENROUTER_API_KEY="your-api-key"

# 或添加到 ~/.bashrc 或 ~/.zshrc
echo 'export OPENROUTER_API_KEY="your-api-key"' >> ~/.bashrc
source ~/.bashrc
```

获取密钥：访问 [OpenRouter](https://openrouter.ai/keys) 创建 API Key。

---

## 支持的模型

| 模型别名 | 实际模型 | 说明 |
|---------|---------|------|
| `gemini` | google/gemini-3.1-flash-image-preview | 默认模型，中文效果较好 |
| `seedream` | bytedance-seed/seedream-4.5 | 备选模型，画面质感好 |

---

## 使用方式

**⚠️ 生图前必须通过 AskUser 询问用户选择模型（gemini 或 seedream）。**

```bash
cd /root/.claude/skills/wechat-product-manager-writer

# 使用默认 gemini 模型（可省略 --model）
python scripts/generate_image.py \
  --prompt "A test image with Chinese text '测试'" \
  --output test.png

# 使用 seedream 模型
python scripts/generate_image.py \
  --prompt "A test image with Chinese text '测试'" \
  --model seedream \
  --output test.png
```

---

## 常见问题

**API 密钥无效**：检查是否正确设置 `OPENROUTER_API_KEY` 环境变量，重启终端后重试。

**生成失败**：检查网络连接，确认 OpenRouter 账户余额充足。

**中文显示问题**：gemini 模型对中文支持更好，建议优先使用。
