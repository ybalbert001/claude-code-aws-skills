# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此代码库中工作时提供指导。

## 仓库概述

这是一个 Claude Code 插件仓库，包含一系列用于 AWS 工作流、演示文稿、图表和内容生成的技能。技能可通过斜杠命令调用（如 `/slidev-ppt`、`/deploy-sglang`），或根据用户请求匹配技能描述自动触发。

## 架构

```
claude-code-aws-skills/
├── .claude-plugin/
│   └── plugin.json          # 插件元数据（名称、描述、版本）
└── skills/
    └── {skill-name}/
        ├── SKILL.md         # 技能定义（YAML 前置元数据 + 指令）
        ├── scripts/         # Python 功能脚本
        ├── assets/          # 可选：HTML 模板、CSS、JSON 配置
        ├── references/      # 可选：文档、示例
        └── requirements.txt # 可选：Python 依赖
```

## 可用技能

| 技能 | 用途 | 关键脚本 |
|------|------|----------|
| `slidev-ppt` | 使用 AWS 深色主题创建 Slidev 演示文稿 | 使用 npm/npx slidev |
| `agentcore-browser` | AWS AgentCore 浏览器自动化 | `browser_session_manager.py`, `browser_tool.py` |
| `excalidraw` | 图表操作（委托给子代理） | `export_excalidraw.py` |
| `red-card` | 生成小红书风格图片卡片 | `generate_cards.py` |
| `sglang-deploy` | 在 AWS 上部署 SGLang LLM 服务器 (EC2 / SageMaker Endpoint) | `sagemaker_endpoint.py`, `instance_checker.py` |

### sglang-deploy

该插件支持两种部署目标（HyperPod Coming Soon）：

**EC2 部署**：通过 SSH 在 GPU 实例上直接部署，支持 Prometheus+Grafana 监控
**SageMaker Endpoint 部署**：通过 boto3 API 创建托管推理端点，使用预构建公开镜像 `public.ecr.aws/w4r2d0t2/sagemaker_endpoint/sglang:v0.5.9`

实现思路：
1. 通过交互式问答获取部署信息（目标、模型、参数）
2. 部署计算资源需要人预先提供，插件检测其可用性
3. 部署方式以 [sglang 官方文档](https://docs.sglang.io/basic_usage/popular_model_usage.html) 为标准材料
4. 目标特定的部署细节委托到 `references/` 下的文档
