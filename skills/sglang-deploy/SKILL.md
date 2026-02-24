---
name: sglang-deploy
description: 在预先存在的 EC2 实例上部署 SGLang LLM 推理服务器。当用户请求 "/deploy-sglang"、需要部署 LLM 模型到 AWS、或设置 SGLang 推理服务时使用。支持通过 SSH 远程部署，包含模型选择、参数配置和可选的 Prometheus+Grafana 监控。
---

# SGLang AWS 部署

通过 SSH 在预先存在的 EC2 GPU 实例上部署 SGLang 推理服务器。

## 部署流程

```
deploy.py
    │
    ├─→ 1. 确定部署模型
    │      ├─ 通过deploy.py脚本获取trending models供参考
    │      └─ 手工填写huggingface model id
    │
    ├─→ 2. 通过AskUserQuestionTool采集信息
    │      ├─ 选择计算资源类型, 选项为[EC2，hyperpod(目前不支持)]
    │      ├─ EC2 IP
    │      ├─ EC2 用户名, 选项为[ubuntu，ec2-user]
    │      ├─ ssh 连接密钥路径
    │      ├─ sglang service port 参数
    │      └─ Tensor Parallelism 参数
    │
    ├─→ 3. 检测实例可用性
    │      ├─ SSH 连接测试
    │      ├─ GPU 配置检测 (nvidia-smi)
    │      ├─ 磁盘空间检测
    │      └─ Python 环境检测
    │
    ├─→ 4. 准备环境 & 部署
    │      ├─ 安装 python3-pip, uv, CUDA Toolkit
    │      ├─ 安装 sglang
    │      ├─ 配置启动脚本
    │      ├─ [可选] 安装监控组件
    │      └─ 启动服务
    │
    └─→ 5. 输出部署摘要
```

## 脚本说明

### deploy.py 命令行参数

**必需参数:**

| 参数 | 说明 | 示例 |
|------|------|------|
| `--host` | EC2 实例 IP 或域名 | `--host 3.148.202.165` |
| `--key_file` | SSH 私钥文件路径 | `--key_file ~/mykey.pem` |
| `--model` | HuggingFace 模型 ID | `--model Qwen/Qwen2.5-72B-Instruct` |

**可选参数:**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--username` | SSH 用户名 | `ubuntu` |
| `--port` | SSH 端口 | `22` |
| `--service_port` | SGLang 服务端口 | `30000` |
| `--tp` | Tensor Parallelism | 自动 (min(推荐值, GPU数)) |
| `--hf_token` | HuggingFace Token | 无 |
| `--enable_monitoring` | 安装监控组件 | 否 |
| `--no_monitoring` | 不安装监控组件 | 默认 |
| `--resource_type` | 计算资源类型 | `ec2` |
| `--trending_models` | 列出热门模型 | - |

### 调用示例

```bash
# 基本部署
python scripts/deploy.py \
  --host 3.148.202.165 \
  --key_file ~/yuanbo.pem \
  --model Qwen/Qwen2.5-72B-Instruct

# 指定 TP 和端口
python scripts/deploy.py \
  --host 3.148.202.165 \
  --key_file ~/yuanbo.pem \
  --model Qwen/Qwen2.5-72B-Instruct \
  --tp 8 \
  --service_port 8080

# 启用监控
python scripts/deploy.py \
  --host 3.148.202.165 \
  --key_file ~/yuanbo.pem \
  --model Qwen/Qwen2.5-72B-Instruct \
  --enable_monitoring

# 列出热门模型
python scripts/deploy.py --trending_models
```

### 其他脚本

| 脚本 | 用途 | 调用方式 |
|------|------|----------|
| `cleanup.py` | 清理已部署的服务 | `python scripts/cleanup.py --host <IP> --key_file <KEY>` |
| `instance_checker.py` | 检测实例配置 | `python scripts/instance_checker.py --host <IP> --key_file <KEY>` |

内部模块（无需直接调用）：`hf_api.py`（HuggingFace API）、`ssh_utils.py`（SSH 工具）

## 部署后使用

| 端口 | 服务 | URL |
|------|------|-----|
| 30000 | SGLang API | `http://<IP>:30000` |
| 3000 | Grafana | `http://<IP>:3000` (可选) |
| 9090 | Prometheus | `http://<IP>:9090` (可选) |

```bash
curl http://<IP>:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "default", "messages": [{"role": "user", "content": "Hello!"}]}'
```

## 监控 (可选)

Grafana 仪表板 (`:3000`) 显示请求数、Token 吞吐量、TTFT、延迟、Cache 命中率。默认凭据: `admin/admin`

## 故障排除

```bash
# 查看日志
tail -f /tmp/sglang.log

# 停止服务
pkill -f "sglang.launch_server"
```

| 问题 | 解决方案 |
|------|----------|
| SSH 连接失败 | 检查安全组是否开放 22 端口，密钥文件权限是否正确 |
| GPU 未检测到 | 确认实例类型支持 GPU，NVIDIA 驱动已安装 |
| 内存不足 | 使用更大实例或启用 tensor parallelism |
| 服务启动失败 | 查看日志 `tail -f /tmp/sglang.log` |
