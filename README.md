# Claude Code AWS Skills

Claude Code 插件仓库，包含 AWS 工作流、演示文稿、图表和内容生成等技能。

## 本仓库技能

| 技能 | 用途 |
|------|------|
| `slidev-ppt` | 使用 AWS 深色主题创建 Slidev 演示文稿 |
| `agentcore-browser` | AWS AgentCore 浏览器自动化 |
| `excalidraw` | Excalidraw 图表操作（委托给子代理） |
| `red-card` | 生成小红书风格图片卡片 |
| `sglang-deploy` | 在 AWS 上部署 SGLang LLM 服务器（EC2 / SageMaker Endpoint） |
| `rednote-publish` | 小红书内容发布 |
| `sglang-hyperpod-deploy` | SGLang HyperPod 部署（WIP） |

## SGLang 上游 Skills

来自 [sgl-project/sglang/.claude/skills](https://github.com/sgl-project/sglang/tree/main/.claude/skills)，在开发和调试 SGLang 时可参考：

| Skill | 用途 |
|-------|------|
| [`add-jit-kernel`](https://github.com/sgl-project/sglang/tree/main/.claude/skills/add-jit-kernel) | 添加轻量级 JIT CUDA kernel 到 `jit_kernel` 模块的教程 |
| [`add-sgl-kernel`](https://github.com/sgl-project/sglang/tree/main/.claude/skills/add-sgl-kernel) | 添加重量级 AOT CUDA/C++ kernel 到 `sgl-kernel` 的教程（含测试和 benchmark） |
| [`ci-workflow-guide`](https://github.com/sgl-project/sglang/tree/main/.claude/skills/ci-workflow-guide) | CI 流水线指南：stage 排序、快速失败、门控、分区、执行模式、CI 失败调试 |
| [`clean-startup-log`](https://github.com/sgl-project/sglang/tree/main/.claude/skills/clean-startup-log) | 清理服务器启动日志中的噪音警告和第三方输出 |
| [`debug-cuda-crash`](https://github.com/sgl-project/sglang/tree/main/.claude/skills/debug-cuda-crash) | 使用 `@debug_kernel_api` 日志装饰器调试 CUDA 崩溃 |
| [`debug-distributed-hang`](https://github.com/sgl-project/sglang/tree/main/.claude/skills/debug-distributed-hang) | 调试分布式推理（TP/PP/DP/EP）挂起：py-spy/watchdog 定位、per-rank 日志、二分法 |
| [`generate-profile`](https://github.com/sgl-project/sglang/tree/main/.claude/skills/generate-profile) | 生成端到端 profiling trace（Chrome 兼容格式） |
| [`llm-torch-profiler-analysis`](https://github.com/sgl-project/sglang/tree/main/.claude/skills/llm-torch-profiler-analysis) | 统一 torch profiler 分析（sglang/vllm/TensorRT-LLM），输出 kernel/overlap/fuse 三表报告 |
| [`sglang-auto-benchmark`](https://github.com/sgl-project/sglang/tree/main/.claude/skills/sglang-auto-benchmark) | AI 驱动自动化 benchmark：分层 server-flag 搜索、SLA/固定 QPS、CSV 导出、EAGLE 调优 |
| [`sglang-bisect-ci-regression`](https://github.com/sgl-project/sglang/tree/main/.claude/skills/sglang-bisect-ci-regression) | CI 回归二分定位：提取失败签名、二分 commit 窗口、硬件特异性检查、远程复现 |
| [`write-sglang-test`](https://github.com/sgl-project/sglang/tree/main/.claude/skills/write-sglang-test) | 编写测试指南：CustomTestCase、CI 注册、server fixture、model 选择、mock 测试 |
