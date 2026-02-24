---
name: sglang-deploy
description: 在预先存在的 EC2 实例上部署 SGLang LLM 推理服务器。当用户请求 "/deploy-sglang"、需要部署 LLM 模型到 AWS、或设置 SGLang 推理服务时使用。支持通过 SSH 远程部署，包含模型选择、参数配置和可选的 Prometheus+Grafana 监控。
---

# SGLang AWS 部署

通过 SSH 在预先存在的 EC2 GPU 实例上部署 SGLang 推理服务器。模型列表从 HuggingFace API 实时获取 (trending 32B+)，也支持输入任意 HuggingFace 模型 ID。

## 部署流程

```
/deploy-sglang
    │
    ├─→ 1. 选择部署模型
    │      └─ 从 HuggingFace API 获取 trending 32B+ 模型，或输入自定义模型 ID
    │
    ├─→ 2. 选择计算资源类型
    │      ├─ EC2 实例 (当前支持)
    │      └─ Hyperpod 集群 (规划中)
    │
    ├─→ 3. 获取 SSH 连接信息
    │      ├─ 主机地址 (IP 或域名)
    │      ├─ SSH 用户名
    │      ├─ SSH 密钥文件
    │      └─ SSH 端口
    │
    ├─→ 4. 检测实例可用性
    │      ├─ SSH 连接测试
    │      ├─ GPU 配置检测 (nvidia-smi)
    │      ├─ 磁盘空间检测
    │      └─ Python 环境检测
    │
    ├─→ 5. 交互确认模型部署参数
    │      ├─ 端口 (默认 30000)
    │      ├─ Tensor Parallelism
    │      ├─ 是否安装监控 [可选]
    │      └─ HuggingFace Token
    │
    ├─→ 6. 准备环境 (自动)
    │      ├─ 安装 python3-pip
    │      ├─ 安装 uv 包管理器
    │      ├─ 安装 CUDA Toolkit (nvcc)
    │      └─ 系统级安装 sglang
    │
    └─→ 7. 启动服务
           ├─ 使用 nohup 后台启动
           ├─ [可选] 安装监控组件
           └─ 验证服务状态
```

## 脚本说明

| 脚本 | 用途 | 调用方式 |
|------|------|----------|
| `deploy.py` | 主部署脚本，执行完整部署流程 | `python scripts/deploy.py --host <IP> --key-file <KEY>` |
| `cleanup.py` | 清理已部署的服务 | `python scripts/cleanup.py --host <IP> --key-file <KEY>` |
| `instance_checker.py` | 检测实例配置 | `python scripts/instance_checker.py --host <IP> --key-file <KEY>` |

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
