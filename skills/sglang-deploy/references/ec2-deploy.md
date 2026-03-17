# EC2 部署详细步骤

通过 SSH 在 EC2 GPU 实例上部署 SGLang 推理服务器。

使用 Bash 工具 + `run_in_background: true` 异步执行以下 SSH 命令。

## Step 1: 安装依赖和 SGLang (10-20分钟)

```bash
ssh -i <KEY> -o StrictHostKeyChecking=no <USER>@<IP> 'bash -s' << 'INSTALL_EOF'
set -ex
export PATH="$HOME/.local/bin:$PATH"
export HF_TOKEN="<HF_TOKEN>"  # 如果有

# 安装 pip
command -v pip3 || (sudo apt-get update && sudo apt-get install -y python3-pip)

# 安装 uv
command -v uv || pip3 install --break-system-packages uv || pip3 install --user uv

# 安装 CUDA Toolkit (如果没有 nvcc)
command -v nvcc || sudo apt-get install -y cuda-toolkit-12-8 || sudo apt-get install -y cuda-toolkit

# 使用 uv 安装 SGLang (更快)
if command -v uv &> /dev/null; then
    sudo $(which uv) pip install "sglang[all]" --system --break-system-packages
else
    sudo pip3 install --break-system-packages "sglang[all]"
fi

# 修复 PyTorch 2.9.x 与 CuDNN 兼容性
PYTORCH_VERSION=$(python3 -c "import torch; print(torch.__version__)" 2>/dev/null || echo "unknown")
if [[ "$PYTORCH_VERSION" == 2.9.* ]]; then
    echo "Upgrading CuDNN for PyTorch 2.9.x compatibility..."
    sudo pip3 install --break-system-packages nvidia-cudnn-cu12==9.16.0.29
fi
INSTALL_EOF
```

注意以上脚本中的步骤都不可省略。需要检查确认都安装成功后才进入下一步 Step 2。

## Step 2: 启动服务 (15-30分钟) - 最耗时

**重要**：不同模型可能需要不同的启动参数。启动前必须先查看模型页面获取推荐配置，如果用户要求安装监控，请务必添加 `--enable-metrics` 参数。

```
使用 WebFetch 访问: https://huggingface.co/<MODEL_ID>
提取: SGLang 启动命令和参数 (如 --tp, --chat-template, --trust-remote-code 等)
```

默认启动命令（根据模型页面信息调整）：

```bash
ssh -i <KEY> -o StrictHostKeyChecking=no <USER>@<IP> 'bash -s' << 'START_EOF'
export HF_TOKEN="<HF_TOKEN>"  # 如果有
pkill -f "sglang.launch_server" 2>/dev/null || true
sleep 2

# 生成日志文件名 (如 sglang-qwen3.5-397b-a17b-fp8.log)
MODEL_ID="<MODEL_ID>"
LOG_FILE="$HOME/sglang-$(echo "$MODEL_ID" | awk -F'/' '{print tolower($NF)}').log"

nohup python3 -m sglang.launch_server \
    --model-path $MODEL_ID \
    --host 0.0.0.0 \
    --port <SERVICE_PORT> \
    --tp <TP> \
    --enable-metrics \
    > "$LOG_FILE" 2>&1 &

echo "Started with PID: $!"
echo "Log file: $LOG_FILE"
START_EOF
```

## Step 3: 等待服务就绪

使用 `check_progress.py` 轮询，每 10 秒一次：
```bash
python scripts/check_progress.py --host <IP> --key_file <KEY> --username <USER> --service_port <PORT> \
    --log_path ~/sglang-<model>.log --pretty
```

日志路径格式：`~/sglang-{model_name}.log`，如 `~/sglang-qwen3.5-397b-a17b-fp8.log`

- `"api_healthy": true` → 部署成功
- `"next_action": "wait"` → 继续等待（模型加载中）
- 超过 10 分钟仍未就绪 → 检查日志

## Step 4: 安装监控 (可选, 3-5分钟)

仅当用户选择启用监控时执行。参考 [SGLang Production Metrics](https://docs.sglang.io/references/production_metrics.html)。

使用 `scripts/setup_monitor.sh` 脚本，该脚本会从 [sglang 官方仓库](https://github.com/sgl-project/sglang/tree/main/examples/monitoring) 拉取最新的监控配置（Prometheus + Grafana）。

```bash
ssh -i <KEY> -o StrictHostKeyChecking=no <USER>@<IP> 'bash -s' < scripts/setup_monitor.sh
```

**注意**：
- 官方配置启用了 Grafana 匿名访问，无需密码
- 预置的 SGLang Dashboard 会自动加载，包含 E2E Latency、TTFT、Cache Hit Rate、Throughput 等指标

## 故障排除

查看日志（日志路径格式：`~/sglang-{model_name}.log`）：
```bash
ssh -i <KEY> <USER>@<IP> 'tail -100 ~/sglang-<model>.log'
```

停止服务：
```bash
ssh -i <KEY> <USER>@<IP> 'pkill -f sglang.launch_server'
```

| 问题 | 解决方案 |
|------|----------|
| SSH 连接失败 | 检查安全组 22 端口，密钥权限 |
| GPU 未检测到 | 确认实例类型，NVIDIA 驱动 |
| 内存不足 | 增加 TP 或使用更大实例 |
| 服务启动超时 | 大模型加载慢，继续等待或检查日志 |
