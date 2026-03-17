# SageMaker Endpoint 部署详细步骤

通过 SageMaker 托管推理部署 SGLang 服务。SGLang 0.2.13+ 内置 `/ping` 和 `/invocations` 端点，原生兼容 SageMaker。

## 前置条件

- AWS CLI 已配置
- Python 依赖：`boto3`, `sagemaker`, `huggingface_hub`
- IAM Role 和 S3 Bucket 可自动检测（在 SageMaker 环境中），也可手动指定

## Step 1: 上传模型到 S3 (耗时取决于模型大小)

```bash
python scripts/sagemaker_endpoint.py --action upload-model \
    --model-id <MODEL_ID> \
    --region <REGION> \
    --hf-token <HF_TOKEN>  # 可选，gated 模型需要
```

该命令会：
1. 从 HuggingFace 下载模型（safetensors + config）
2. `aws s3 sync` 上传到 `s3://<bucket>/models/<model-name>/`

**注意**：如果模型已在 S3 上，可跳过此步。

## Step 2: 获取模型推荐参数

**重要**：不同模型可能需要不同的启动参数。部署前必须先查看模型页面获取推荐配置。

```
使用 WebFetch 访问: https://huggingface.co/<MODEL_ID>
提取: SGLang 启动命令和参数
```

从官方推荐命令中提取模型相关参数，**去掉** `--host`、`--port`、`--model-path`（SageMaker 会自动设置），将剩余参数作为 `--sglang-args` 的值。

例如官方推荐：
```
python3 -m sglang.launch_server --model-path xxx --tp-size 4 --tool-call-parser glm47 --mem-fraction-static 0.8 --host 0.0.0.0 --port 8000
```

则 `--sglang-args` 应为：`"--tp 4 --tool-call-parser glm47 --mem-fraction-static 0.8"`

**注意**：如果模型页面没有 SGLang 特殊参数，可跳过此步，脚本会使用默认值 `--tp <auto> --trust-remote-code --mem-fraction-static 0.85`。

## Step 3: 部署 Endpoint (10-20分钟)

```bash
python scripts/sagemaker_endpoint.py --action deploy \
    --model-id <MODEL_ID> \
    --instance-type <INSTANCE_TYPE> \
    --region <REGION> \
    --sglang-args "<SGLANG_ARGS>"  # 可选，Step 2 中获取的模型特定参数
    --capacity-reservation-arn <FTP_ARN>  # 可选，Flexible Training Plan 预留容量
```

- IAM Role 和 S3 Bucket 自动检测，也可通过 `--role-arn` / `--s3-bucket` 手动指定
- 默认使用预构建公开镜像：`public.ecr.aws/w4r2d0t2/sagemaker_endpoint/sglang:v0.5.9`
- 指定 FTP ARN 时会在 ProductionVariant 中添加 `CapacityReservationConfig`

该命令会：
1. 动态生成 `start.sh`（包含 `s5cmd sync` 模型下载 + `sglang.launch_server` 启动参数）
2. 打包为 tar.gz 上传到 S3 作为 `ModelDataUrl`
3. 创建 SageMaker Model → EndpointConfig → Endpoint

输出 JSON 包含 `endpoint_name`，用于后续步骤。

### 关键 EndpointConfig 参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `ContainerStartupHealthCheckTimeoutInSeconds` | 1000 | 大模型需要长启动时间 |
| `InferenceAmiVersion` | `al2-ami-sagemaker-inference-gpu-3-1` | GPU 推理 AMI |

### Instance Type 推荐

| Instance Type | GPU | GPU Memory | 适合模型 |
|--------------|-----|------------|----------|
| ml.g6.2xlarge | 1x L4 | 24GB | 7B-14B |
| ml.g6.12xlarge | 4x L4 | 96GB | 14B-70B |
| ml.g5.12xlarge | 4x A10G | 96GB | 14B-70B |
| ml.p4d.24xlarge | 8x A100 | 320GB | 70B-180B |
| ml.p5.48xlarge | 8x H100 | 640GB | 180B+ |

## Step 4: 等待就绪

```bash
python scripts/sagemaker_endpoint.py --action wait \
    --endpoint-name <ENDPOINT_NAME> \
    --region <REGION>
```

每 60 秒轮询 `DescribeEndpoint`，直到状态变为 `InService` 或 `Failed`。

## 测试

```bash
python scripts/sagemaker_endpoint.py --action test \
    --endpoint-name <ENDPOINT_NAME> \
    --region <REGION>
```

或使用 Python 代码测试（非流式）：

```python
import boto3, json

runtime = boto3.client('runtime.sagemaker')
response = runtime.invoke_endpoint(
    EndpointName="<ENDPOINT_NAME>",
    ContentType='application/json',
    Body=json.dumps({
        "messages": [{"role": "user", "content": "Hello!"}],
        "max_tokens": 256,
        "stream": False
    })
)
print(json.loads(response['Body'].read())["choices"][0]["message"]["content"])
```

流式测试：

```python
response = runtime.invoke_endpoint_with_response_stream(
    EndpointName="<ENDPOINT_NAME>",
    ContentType='application/json',
    Body=json.dumps({
        "messages": [{"role": "user", "content": "Hello!"}],
        "max_tokens": 256,
        "stream": True
    })
)

import re
buffer = ""
for t in response['Body']:
    buffer += t["PayloadPart"]["Bytes"].decode()
    last_idx = 0
    for match in re.finditer(r'^data:\s*(.+?)(\n\n)', buffer):
        try:
            data = json.loads(match.group(1).strip())
            last_idx = match.span()[1]
            print(data["choices"][0]["delta"]["content"], end="")
        except (json.JSONDecodeError, KeyError, IndexError):
            pass
    buffer = buffer[last_idx:]
print()
```

## 清理

```bash
python scripts/sagemaker_endpoint.py --action delete \
    --endpoint-name <ENDPOINT_NAME> \
    --region <REGION>
```

会依次删除 Endpoint → EndpointConfig → Model。