---
name: sglang-deploy
description: "在 AWS 上部署 SGLang LLM 推理服务器。支持 3 种部署目标：(1) EC2 实例通过 SSH 部署，(2) SageMaker Endpoint 通过 AWS API 托管部署，(3) SageMaker HyperPod (Coming Soon)。当用户请求 '/deploy-sglang'、需要部署 LLM 模型到 AWS、或设置 SGLang 推理服务时使用。包含模型选择、参数配置、部署执行和可选监控。"
---

# SGLang AWS 部署

在 AWS 上部署 SGLang 推理服务器，支持多种部署目标。

## 部署工作流

### 阶段 1：确定部署 MODEL_ID

如果用户已指定模型，获取模型详细信息（参数量、架构、MoE、推荐实例等）：
```bash
python scripts/hf_api.py --model_id <MODEL_ID>
```

如果用户未指定模型，获取热门模型供选择：
```bash
python scripts/hf_api.py --trending
```

提示用户选择或自己指定 HuggingFace 模型 ID。

### 阶段 2：选择部署目标

使用 AskUserQuestion 让用户选择：

| 部署目标 | 访问方式 | 适用场景 |
|----------|---------|----------|
| **EC2** | SSH | 已有 EC2 GPU 实例，需要完全控制 |
| **SageMaker Endpoint** | boto3 API | 托管推理，自动扩缩，生产环境 |
| **HyperPod** | Coming Soon | 大规模 GPU 集群 |

### 阶段 3：收集部署参数

使用 AskUserQuestion 收集参数。

**通用参数：**

| 参数 | 必需 | 说明 | 默认值 |
|------|------|------|--------|
| MODEL_ID | 是 | HuggingFace 模型 ID | 阶段 1 选择 |
| HF Token | 否 | 受限模型需要 | - |
| TP | 否 | Tensor Parallelism | 自动推导 |

**EC2 额外参数：**

| 参数 | 必需 | 说明 | 默认值 |
|------|------|------|--------|
| EC2 IP | 是 | 实例公网 IP | - |
| SSH 密钥路径 | 是 | 如 `~/.ssh/key.pem` | - |
| SSH 用户名 | 否 | RHEL 用 `ec2-user` | `ubuntu` |
| 服务端口 | 否 | SGLang API 端口 | `30000` |
| 启用监控 | 否 | Prometheus + Grafana | 否 |

**SageMaker Endpoint 额外参数：**

| 参数 | 必需 | 说明 | 默认值 |
|------|------|------|--------|
| Instance Type | 是 | 如 `ml.g6.2xlarge` | - |
| Region | 是 | AWS 部署区域 | 如 `us-east-1` |
| FTP ARN | 否 | Flexible Training Plan 预留容量 ARN | - |

### 阶段 4：验证目标

**EC2：**

```bash
python scripts/instance_checker.py --host <IP> --key_file <KEY> --username <USER> --model_id <MODEL_ID>
```

输出包含 GPU/磁盘/网络状态、模型缓存状态、推荐日志路径。确认正常后继续。

**SageMaker Endpoint：**

验证 IAM Role 是否已创建：
```bash
aws iam get-role --role-name sglang-sagemaker-execution-role --query 'Role.Arn' --output text
aws iam get-role --role-name sglang-ecr-copy-codebuild-role --query 'Role.Arn' --output text
```

如果 Role 不存在，提示用户执行：
```bash
bash scripts/setup_iam_roles.sh
```

### 阶段 5：执行部署

根据目标分支到对应的详细文档：

- **EC2** → 按照 [references/ec2-deploy.md](references/ec2-deploy.md) 执行
- **SageMaker Endpoint** → 按照 [references/sagemaker-endpoint-deploy.md](references/sagemaker-endpoint-deploy.md) 执行

### 阶段 6：等待就绪

**EC2：**

使用 `check_progress.py` 轮询，每 10 秒一次：
```bash
python scripts/check_progress.py --host <IP> --key_file <KEY> --username <USER> --service_port <PORT> \
    --log_path ~/sglang-<model>.log --pretty
```

- `"api_healthy": true` → 部署成功
- `"next_action": "wait"` → 继续等待

**SageMaker Endpoint：**

```bash
python scripts/sagemaker_endpoint.py --action wait --endpoint-name <ENDPOINT_NAME> --region <REGION>
```

每 60 秒轮询，直到 `InService` 或 `Failed`。

### 阶段 7：输出部署摘要

**EC2 摘要：**
```
部署完成!
==========
SGLang API: http://<IP>:<PORT>
模型: <MODEL_ID>
TP: <TP>

测试命令:
curl http://<IP>:<PORT>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "default", "messages": [{"role": "user", "content": "Hello!"}]}'
```

如启用监控，额外输出：
```
监控:
Grafana: http://<IP>:3000 (匿名访问，SGLang Dashboard 已预置)
Prometheus: http://<IP>:9090
```

**SageMaker Endpoint 摘要：**
```
部署完成!
==========
Endpoint Name: <ENDPOINT_NAME>
Instance Type: <INSTANCE_TYPE>
模型: <MODEL_ID>
TP: <TP>

测试命令:
python scripts/sagemaker_endpoint.py --action test --endpoint-name <ENDPOINT_NAME> --region <REGION>

清理命令:
python scripts/sagemaker_endpoint.py --action delete --endpoint-name <ENDPOINT_NAME> --region <REGION>
```

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `scripts/hf_api.py` | 获取模型信息（`--model_id`：参数量、架构、MoE、权重大小、推荐实例）和热门模型列表（`--trending`） |
| `scripts/fetch_deploy_cmd.py` | 通过 Playwright 从 docs.sglang.io 获取部署命令（支持 JS 动态渲染页面） |
| `scripts/instance_checker.py` | EC2: 检测实例配置 (GPU/磁盘/网络) |
| `scripts/check_progress.py` | EC2: 检查部署进度和服务状态 |
| `scripts/cleanup.py` | EC2: 清理已部署的服务 |
| `scripts/ssh_utils.py` | EC2: SSH 工具函数 (内部使用) |
| `scripts/setup_monitor.sh` | EC2: 安装 Prometheus + Grafana 监控 |
| `scripts/sagemaker_endpoint.py` | SageMaker Endpoint: 全生命周期管理（模型从 HuggingFace 直接下载） |
| `scripts/ecr_image_copier.py` | SageMaker Endpoint: 通过 CodeBuild 将 public ECR 镜像复制到私有 ECR |
| `scripts/setup_iam_roles.sh` | SageMaker Endpoint: 创建所需的 IAM Role（SageMaker + CodeBuild） |
