---
name: sglang-deploy
description: 在预先存在的 EC2 实例上部署 SGLang LLM 推理服务器。当用户请求 "/deploy-sglang"、需要部署 LLM 模型到 AWS、或设置 SGLang 推理服务时使用。支持通过 SSH 远程部署，包含模型选择、参数配置和可选的 Prometheus+Grafana 监控。
---

# SGLang AWS 部署

通过 SSH 在预先存在的 EC2 GPU 实例上部署 SGLang 大语言模型推理服务器。

## 核心思路

1. **通过交互式问答获取部署信息**
   - 1.1 部署计算资源 (EC2 实例，Hyperpod 集群规划中)
   - 1.2 部署的模型
   - 1.3 参数设定

2. **计算资源需要预先提供**
   - 用户需要提前准备好带 GPU 的 EC2 实例
   - 插件检测实例的可用性 (GPU、磁盘、Python 环境、网络)

3. **部署方式参考 SGLang 官方文档**
   - 安装方法: uv 安装 sglang (系统级)
   - 启动参数: 参考 `references/sglang-docs.md` 或者 https://huggingface.co/{huggingface_model_id}
   - 服务管理: nohup 后台进程

4. **EC2 前置环境准备 (自动执行)**
   - 安装 python3-pip
   - 安装 uv 包管理器
   - 安装 CUDA Toolkit (nvcc，deep_gemm 等组件依赖)
   - 系统级安装 sglang

## 快速开始

### 1. 准备工作

确保你有:
- 一台带 GPU 的 EC2 实例 (已运行)
- SSH 密钥文件
- 实例的 IP 地址或域名

### 2. 安装依赖

```bash
cd skills/sglang-deploy/scripts
pip install -r requirements.txt
```

### 3. 检查实例

```bash
python instance_checker.py --host <IP> --username ec2-user --key-file ~/.ssh/my-key.pem
```

### 4. 部署

```bash
python deploy.py --host <IP> --username ec2-user --key-file ~/.ssh/my-key.pem
```

### 5. 清理

```bash
python cleanup.py --host <IP> --username ec2-user --key-file ~/.ssh/my-key.pem
```

## 部署流程

```
/deploy-sglang
    │
    ├─→ 1. 选择计算资源类型
    │      ├─ EC2 实例 (当前支持)
    │      └─ Hyperpod 集群 (规划中)
    │
    ├─→ 2. 获取 SSH 连接信息
    │      ├─ 主机地址 (IP 或域名)
    │      ├─ SSH 用户名
    │      ├─ SSH 密钥文件
    │      └─ SSH 端口
    │
    ├─→ 3. 检测实例可用性
    │      ├─ SSH 连接测试
    │      ├─ GPU 配置检测 (nvidia-smi)
    │      ├─ 磁盘空间检测
    │      └─ Python 环境检测
    │
    ├─→ 4. 选择部署模型
    │      └─ 从 HuggingFace API 获取 trending 32B+ 模型
    │
    ├─→ 5. 配置参数
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

## 部署后端点

| 端口 | 服务 | URL |
|------|------|-----|
| 30000 | SGLang API | `http://<IP>:30000` |
| 3000 | Grafana | `http://<IP>:3000` (可选) |
| 9090 | Prometheus | `http://<IP>:9090` (可选) |

## 测试 API

```bash
curl http://<IP>:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## 动态模型获取

模型列表从 HuggingFace API 实时获取:
- **过滤条件**: 支持 SGLang (`apps=sglang`)、32B+ 参数量
- **排序方式**: 按 trending score 排序
- **自定义模型**: 支持输入任意 HuggingFace 模型 ID

GPU 需求根据模型参数量自动估算。

## 监控

Grafana 仪表板 (`:3000`) 显示:
- 运行中/等待中请求数
- Token 吞吐量
- 首 Token 时间 (TTFT)
- 端到端延迟
- Cache 命中率

默认凭据: `admin/admin`

## 故障排除

### 检查 SGLang 服务状态

```bash
# SSH 到实例后
# 查看进程
ps aux | grep sglang

# 查看日志
tail -f /tmp/sglang.log

# 停止服务
pkill -f "sglang.launch_server"
```

### 常见问题

| 问题 | 解决方案 |
|------|----------|
| SSH 连接失败 | 检查安全组是否开放 22 端口，密钥文件权限是否正确 |
| GPU 未检测到 | 确认实例类型支持 GPU，NVIDIA 驱动已安装 |
| 内存不足 | 使用更大实例或启用 tensor parallelism |
| 模型下载慢 | 检查网络连通性，或使用 HuggingFace 镜像 |
| pip 未安装 | 部署脚本会自动安装 `sudo apt-get install -y python3-pip` |
| CUDA Toolkit 未安装 | 部署脚本会自动安装 `sudo apt-get install -y cuda-toolkit-12-8` |
| deep_gemm 报错 | 检查 CUDA_HOME 环境变量，确保 nvcc 可用 |
| 服务启动失败 | 查看日志 `tail -f /tmp/sglang.log` |

## 参考文档

- **SGLang 官方文档**: https://docs.sglang.io/
- **安装和参数参考**: `references/sglang-docs.md`

## 未来扩展 (Hyperpod)

Hyperpod 集群支持将在 EC2 验证完成后实现，预计包括:
- 集群发现和节点选择
- 多节点部署支持
- 与 Slurm 调度器集成
