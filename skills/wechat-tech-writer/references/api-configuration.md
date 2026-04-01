# API配置指南

本文档说明如何配置生图API密钥，以便skill能够直接调用API生成图片。

## 生图方式

统一通过 **OpenRouter API** 调用生图模型。需要设置 `OPENROUTER_API_KEY` 环境变量。

### 可用模型

| 模型 | 别名 | 完整模型ID | 说明 |
|------|------|-----------|------|
| **Gemini生图** | gemini | google/gemini-3.1-flash-image-preview | 默认模型，质量高，中文支持好 |
| **SeedDream** | seedream | bytedance-seed/seedream-4.5 | 字节跳动生图模型，风格多样 |

**⚠️ 生图前必须先通过 AskUser 询问用户选择使用哪个模型**

## 配置步骤

### 1. 获取API密钥

访问 [OpenRouter](https://openrouter.ai/keys) 创建API密钥。

### 2. 设置环境变量

**Linux/Mac**:
```bash
export OPENROUTER_API_KEY="your-openrouter-api-key"
```

**Windows (PowerShell)**:
```powershell
$env:OPENROUTER_API_KEY="your-openrouter-api-key"
```

### 3. 测试配置

```bash
# 默认模型（gemini）
python scripts/generate_image.py \
  --prompt "A simple blue gradient background" \
  --output test.png

# 指定模型
python scripts/generate_image.py \
  --prompt "A simple blue gradient background" \
  --model seedream \
  --output test.png
```

如果看到 `✅ 图片已生成: test.png`，说明配置成功！

## 在Skill中使用

### 模型选择流程

生成图片前，必须通过 AskUser 询问用户选择模型：

```
请选择生图模型：
1. gemini（默认） - Google Gemini生图模型，中文支持好
2. seedream - 字节跳动SeedDream，风格多样
```

用户选择后，在命令中通过 `--model` 参数指定：

```bash
python scripts/generate_image.py \
  --prompt "提示词" \
  --model gemini \
  --output cover.png
```

### 批量生成

```python
import subprocess

prompts = ["提示词1", "提示词2", "提示词3"]
for i, prompt in enumerate(prompts):
    subprocess.run([
        'python', 'scripts/generate_image.py',
        '--prompt', prompt,
        '--model', 'gemini',
        '--output', f'images/img_{i}.png'
    ])
```

## 常见问题

### Q: API调用失败怎么办？

1. **检查API密钥是否正确**
   ```bash
   echo $OPENROUTER_API_KEY
   ```

2. **查看错误信息**
   脚本会显示详细的错误信息，如：
   - `401 Unauthorized` → API密钥无效
   - `429 Too Many Requests` → 超过配额限制
   - `403 Forbidden` → 模型在当前区域不可用，尝试换模型

3. **换模型重试**
   如果 gemini 模型不可用，尝试 seedream，反之亦然。

### Q: 如何查看API配额和用量？

访问 [OpenRouter Dashboard](https://openrouter.ai/activity) 查看用量和余额。

### Q: 可以添加其他生图模型吗？

可以！在 `scripts/generate_image.py` 的 `AVAILABLE_MODELS` 字典中添加新模型别名和完整ID即可。
也可以直接通过 `--model` 传入完整的 OpenRouter 模型ID。

### Q: 生成的图片保存在哪里？

保存在 `--output` 参数指定的路径。

## 安全提醒

⚠️ **不要将API密钥提交到版本控制**

在 `.gitignore` 中添加：
```
.env
*.key
secrets/
```

使用环境变量管理API密钥。

---

配置完成后，skill就能自动调用生图API，为文章生成精美的配图了！
