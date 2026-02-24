# AWS GPU实例类型说明

## 推荐实例类型

### G5系列 (NVIDIA A10G)
| 实例类型 | GPU数量 | GPU显存 | vCPU | 内存 | 适用模型 |
|----------|---------|---------|------|------|----------|
| g5.xlarge | 1 | 24GB | 4 | 16GB | 7B参数 |
| g5.2xlarge | 1 | 24GB | 8 | 32GB | 7B-14B参数 |
| g5.4xlarge | 1 | 24GB | 16 | 64GB | 7B-14B参数 (更多CPU) |
| g5.12xlarge | 4 | 96GB | 48 | 192GB | 32B参数 |
| g5.24xlarge | 4 | 96GB | 96 | 384GB | 32B参数 (更多CPU) |
| g5.48xlarge | 8 | 192GB | 192 | 768GB | 70B参数 |

### P4d系列 (NVIDIA A100 40GB)
| 实例类型 | GPU数量 | GPU显存 | vCPU | 内存 | 适用模型 |
|----------|---------|---------|------|------|----------|
| p4d.24xlarge | 8 | 320GB | 96 | 1152GB | 70B+ 参数 |

### P5系列 (NVIDIA H100 80GB)
| 实例类型 | GPU数量 | GPU显存 | vCPU | 内存 | 适用模型 |
|----------|---------|---------|------|------|----------|
| p5.48xlarge | 8 | 640GB | 192 | 2048GB | 200B+ 参数/MoE |

## 选择建议

### 按模型大小选择
| 模型参数量 | 推荐实例 | 推荐TP |
|------------|----------|--------|
| 7B | g5.xlarge | 1 |
| 14B | g5.2xlarge | 1 |
| 32B | g5.12xlarge | 4 |
| 70B | p4d.24xlarge 或 g5.48xlarge | 8 |
| 200B+ | p5.48xlarge | 8 |

### 成本vs性能权衡
- **成本优先**: 选择刚好能容纳模型的最小实例
- **性能优先**: 选择显存充裕的实例，启用更大的KV Cache
- **延迟优先**: A100/H100比A10G有更高的显存带宽

## Region可用性

GPU实例并非所有Region都可用，常见可用Region:
- us-east-1 (N. Virginia)
- us-west-2 (Oregon)
- eu-west-1 (Ireland)
- ap-northeast-1 (Tokyo)

部署前请检查目标Region的实例可用性和配额。

## 配额申请

新AWS账户的GPU实例配额通常为0，需要申请:
1. 进入 AWS Service Quotas
2. 选择 Amazon EC2
3. 搜索 "Running On-Demand G instances" 或 "Running On-Demand P instances"
4. 申请增加配额
