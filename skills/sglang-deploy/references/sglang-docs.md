# SGLang 官方文档参考

> 来源: https://docs.sglang.io/
>
> 本文档整合了 SGLang 官方文档中与部署相关的关键信息，供部署脚本参考。

## 安装方法

### 方法 1: pip/uv 安装 (推荐)

```bash
# 使用 uv (更快)
pip install --upgrade pip
pip install uv
uv pip install sglang

# 或使用 pip
pip install --upgrade pip
pip install "sglang[all]"
```

**注意**: FlashInfer 是默认的 attention kernel 后端，需要 sm75+ GPU (Turing 架构及以上)。

### 方法 2: Docker 安装

```bash
# 标准部署
docker run --gpus all --shm-size 32g -p 30000:30000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --env "HF_TOKEN=<secret>" --ipc=host \
  lmsysorg/sglang:latest

# 生产环境使用更轻量的 runtime 镜像
docker run --gpus all --shm-size 32g -p 30000:30000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --env "HF_TOKEN=<secret>" --ipc=host \
  lmsysorg/sglang:latest-runtime
```

### 方法 3: 源码安装

```bash
git clone https://github.com/sgl-project/sglang.git
cd sglang
pip install --upgrade pip
pip install -e "python"
```

## 服务器启动命令

### 基本启动

```bash
python -m sglang.launch_server --model-path <model> --host 0.0.0.0 --port 30000
```

### 常用参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--model-path` | 模型路径或 HuggingFace repo ID | 必填 |
| `--host` | 服务器监听地址 | 127.0.0.1 |
| `--port` | 服务器端口 | 30000 |
| `--tokenizer-path` | Tokenizer 路径 (默认与 model-path 相同) | - |
| `--trust-remote-code` | 允许加载 Hub 上的自定义代码 | false |

### 并行设置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--tensor-parallel-size` (`--tp`) | GPU 张量并行度 | 1 |
| `--pipeline-parallel-size` (`--pp`) | 流水线并行度 | 1 |
| `--data-parallel-size` (`--dp`) | 数据并行度 | 1 |
| `--expert-parallel-size` (`--ep`) | MoE 模型专家并行度 | 1 |

### 内存管理

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--mem-fraction-static` | KV cache 静态内存分配比例 | 0.9 |
| `--max-total-tokens` | 内存池最大 token 数 | 自动 |
| `--chunked-prefill-size` | 预填充批次的 token 块大小 | - |

### 精度与量化

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--dtype` | 模型精度 (auto, half, bfloat16, float32) | auto |
| `--quantization` | 量化方法 (awq, fp8, gptq, marlin 等) | 无 |
| `--kv-cache-dtype` | KV cache 精度 (fp8_e5m2, fp8_e4m3, bf16) | - |
| `--load-format` | 权重加载格式 (auto, pt, safetensors, gguf) | auto |

### 性能优化

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--enable-cuda-graph` | 启用 CUDA Graph 编译 | false |
| `--attention-backend` | Attention 内核 (flashinfer, triton, fa3) | flashinfer |
| `--sampling-backend` | 采样内核选择 | - |

### 监控与日志

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--enable-metrics` | 启用 Prometheus 指标收集 | false |
| `--log-requests` | 记录请求日志 | false |
| `--log-level` | 日志级别 | info |
| `--enable-trace` | 启用 OpenTelemetry 追踪 | false |

### 高级功能

| 参数 | 说明 |
|------|------|
| `--enable-lora` | 启用 LoRA 适配器支持 |
| `--enable-multimodal` | 启用视觉语言模型支持 |
| `--config` | YAML 配置文件路径 (CLI 参数优先级更高) |

## 常用模型启动示例

### Qwen 系列

```bash
# Qwen2.5-7B
python -m sglang.launch_server \
  --model-path Qwen/Qwen2.5-7B-Instruct \
  --host 0.0.0.0 --port 30000 --tp 1

# Qwen2.5-72B (需要多 GPU)
python -m sglang.launch_server \
  --model-path Qwen/Qwen2.5-72B-Instruct \
  --host 0.0.0.0 --port 30000 --tp 8
```

### Llama 系列

```bash
# Llama-3.1-8B
python -m sglang.launch_server \
  --model-path meta-llama/Llama-3.1-8B-Instruct \
  --host 0.0.0.0 --port 30000 --tp 1

# Llama-3.1-70B
python -m sglang.launch_server \
  --model-path meta-llama/Llama-3.1-70B-Instruct \
  --host 0.0.0.0 --port 30000 --tp 8
```

### DeepSeek 系列

```bash
# DeepSeek-V3 (MoE 模型，需要大实例)
python -m sglang.launch_server \
  --model-path deepseek-ai/DeepSeek-V3 \
  --host 0.0.0.0 --port 30000 --tp 8 --trust-remote-code
```

## API 兼容性

SGLang 服务器提供 OpenAI 兼容的 API：

```bash
# Chat Completions
curl http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Completions
curl http://localhost:30000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "prompt": "Hello, "
  }'
```

## Systemd 服务配置示例

```ini
[Unit]
Description=SGLang LLM Inference Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/sglang
ExecStart=/usr/bin/python -m sglang.launch_server \
  --model-path <MODEL_ID> \
  --host 0.0.0.0 \
  --port 30000 \
  --tp <TP_SIZE> \
  --enable-metrics
Restart=on-failure
RestartSec=10
Environment="HF_TOKEN=<TOKEN>"
Environment="CUDA_VISIBLE_DEVICES=<DEVICES>"

[Install]
WantedBy=multi-user.target
```

## 参考链接

- 官方文档: https://docs.sglang.io/
- GitHub: https://github.com/sgl-project/sglang
- 服务器参数: https://docs.sglang.io/advanced_features/server_arguments.html
- 支持模型: https://docs.sglang.io/supported_models/
