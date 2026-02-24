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
| `sglang-deploy` | 在 AWS EC2 上部署 SGLang LLM 服务器 | `deploy.py`, `cleanup.py` |

### sglang-deploy

该插件实现的思路：
1. 通过交互式问答获取部署的信息
    1.1 部署计算资源（Ec2 or Hyperpod cluster)
    1.2 部署的模型
    1.3 参数设定
2. 部署计算资源需要人预先提供，插件需要检测该资源的可用性
3. 部署的方式需要以[sglang的官方文档](https://docs.sglang.io/basic_usage/popular_model_usage.html)为标准材料
