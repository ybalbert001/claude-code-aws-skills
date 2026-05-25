# EC2 部署详细步骤

通过 SSH 在 EC2 GPU 实例上部署 SGLang 推理服务器。

使用 Bash 工具 + `run_in_background: true` 异步执行以下 SSH 命令。

## Step 1: 启动服务 (Docker)

**重要**：不同模型可能需要不同的启动参数。如果用户要求安装监控，请务必添加 `--enable-metrics` 参数。

**获取部署命令：**

先询问用户是否已有部署命令（如 docker run 命令或 sglang 启动参数）：
- **用户提供命令** → 直接使用用户提供的命令，适配为下方 Docker 格式
- **自动获取** → 使用 `fetch_deploy_cmd.py` 从 docs.sglang.io 获取推荐配置

自动获取方式：

```bash
python scripts/fetch_deploy_cmd.py --model <MODEL_ID> [--series <SERIES>] [--hardware <HW>] [--recipe <RECIPE>]
```

示例：
```bash
python scripts/fetch_deploy_cmd.py --model Qwen/Qwen3-235B-A22B
python scripts/fetch_deploy_cmd.py --model deepseek-ai/DeepSeek-V4-Flash --series DeepSeek-V4 --hardware H200 --recipe max-throughput
```

如果脚本失败（网络问题/Playwright 未安装），fallback 到 WebFetch 访问 `https://huggingface.co/<MODEL_ID>`

默认启动命令（通过 Docker 运行，默认镜像 `lmsysorg/sglang:latest`）：

```bash
ssh -i <KEY> -o StrictHostKeyChecking=no <USER>@<IP> 'bash -s' << 'START_EOF'
set -ex
MODEL_ID="<MODEL_ID>"
CONTAINER_NAME="sglang-$(echo "$MODEL_ID" | awk -F'/' '{print tolower($NF)}')"

# 停止已有容器
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

docker run -d \
    --name "$CONTAINER_NAME" \
    --gpus all \
    --ipc=host \
    --network=host \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    -e HF_TOKEN="<HF_TOKEN>" \
    lmsysorg/sglang:latest \
    python3 -m sglang.launch_server \
        --model-path $MODEL_ID \
        --host 0.0.0.0 \
        --port <SERVICE_PORT> \
        --tp <TP> \
        --enable-metrics

echo "Container started: $CONTAINER_NAME"
START_EOF
```

查看容器日志：`docker logs -f <CONTAINER_NAME>`

## Step 2: 等待服务就绪

使用 `check_progress.py` 轮询，每 10 秒一次：
```bash
python scripts/check_progress.py --host <IP> --key_file <KEY> --username <USER> --service_port <PORT> \
    --container_name <CONTAINER_NAME> --pretty
```

- `"api_healthy": true` → 部署成功
- `"next_action": "wait"` → 继续等待（模型加载中）
- 超过 10 分钟仍未就绪 → 检查日志

## Step 3: 安装监控 (可选, 3-5分钟)

仅当用户选择启用监控时执行。参考 [SGLang Production Metrics](https://docs.sglang.io/references/production_metrics.html)。

使用 `scripts/setup_monitor.sh` 脚本，该脚本会从 [sglang-aws-kit](https://github.com/ybalbert001/sglang-aws-kit/tree/main/monitoring) 拉取监控配置（Prometheus + Grafana）。

```bash
ssh -i <KEY> -o StrictHostKeyChecking=no <USER>@<IP> 'bash -s' < scripts/setup_monitor.sh
```

**注意**：
- Grafana 匿名访问，无需密码
- 预置的 SGLang Dashboard 会自动加载，包含 E2E Latency、TTFT、Cache Hit Rate、Throughput 等指标

## 故障排除

查看日志：
```bash
ssh -i <KEY> <USER>@<IP> 'docker logs --tail 100 <CONTAINER_NAME>'
```

停止服务：
```bash
ssh -i <KEY> <USER>@<IP> 'docker rm -f <CONTAINER_NAME>'
```

| 问题 | 解决方案 |
|------|----------|
| SSH 连接失败 | 检查安全组 22 端口，密钥权限 |
| GPU 未检测到 | 确认实例类型，NVIDIA 驱动 |
| 内存不足 | 增加 TP 或使用更大实例 |
| 服务启动超时 | 大模型加载慢，继续等待或检查日志 |

## 访问 Grafana 监控面板

通过 AWS SSM 端口转发在本地访问 Grafana：

```bash
aws ssm start-session --target <INSTANCE_ID> \
    --document-name AWS-StartPortForwardingSession \
    --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}' \
    --region <REGION>
```

然后浏览器打开 `http://localhost:3000` 即可访问 Grafana。
