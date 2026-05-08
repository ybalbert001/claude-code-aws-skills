---
name: sglang-benchmark
description: "对部署在 AWS (EC2 / HyperPod) 上的 SGLang 推理服务进行系统化 benchmark。基于 spec.yaml 搜索空间规约生成实验计划，长时间运行完成所有实验，汇总benchmark结果。"
---

# SGLang Benchmark

系统化对比 SGLang 在不同部署参数、数据集、并发下的性能表现。

## 设计原则

- **严谨性优先于速度**：每个实验独立启停服务，消除 warmup / KV cache 残留干扰
- **独立于 sglang-deploy**：benchmark 自带启停逻辑，部署命令以结构化字段写入 plan
- **人类可读规约 + 机器可执行清单**：YAML 描述搜索空间，JSONL 展开为实验序列

## 四阶段工作流

### 阶段 1：信息采集

1. **通过 `AskUserQuestion` 工具**依次采集以下字段：
   - **部署目标**：`ec2` / `hyperpod`（单选）
   - **SSH Host**：EC2 / HyperPod 跳板机的 public IP 或 DNS
   - **SSH Private Key**：私钥路径（如 `~/.ssh/id_rsa`）
   - **SSH User**：登录用户名（如 `ubuntu` / `ec2-user`）

   说明：`AskUserQuestion` 每个问题至少需 2 个选项。对 Host / Key / User 这类自由文本字段，给出 1-2 个常见默认值作为选项（如 `ubuntu` / `ec2-user`），用户可点 "Other" 自行输入。
2. 构建benchmark的`spec.yaml`(基于 `assets/spec_template.yaml`)
   - 探测硬件信息并向用户询问部署的模型
   - 通过 `AskUserQuestion` 工具询问用户部署命令或者要求提供部署参考网页
   - 通过 `AskUserQuestion` 工具询问benchmakr的`search.max_candidates`
   - 基于提取的建议和大模型推理知识，提取server运行的base_flags(基线参数)和需要进行search的params
3. **dry run**：
   ```bash
   bash scripts/dry_run.sh --spec spec.yaml --ssh-host <HOST> --ssh-key <KEY>
   ```
   - 用 `spec.yaml.server.base_flags` 启动 server，健康检查通过后 shutdown
   - 失败时把 server 日志尾部返回给用户，用户修正 spec.yaml 后重试，直到通过
   说明：spec.yaml需要有一个本地文件来持久化

4. 向用户展示已采集信息，通过 `AskUserQuestion` 工具提醒用户确认生成的spec.yaml，确认后进入阶段 2

**约束**：`base_flags` 必须覆盖 `search_space` 的所有键（作为 tier 2 的锚点）。

### 阶段 2：benchmark 规划

1. 一键生成 plan.jsonl：
   ```bash
   python scripts/generate_plan.py --spec spec.yaml --out plan.json
   ```
   内部流程：
   - 依据 `search.tier` 展开 `search_space`：tier 1 仅 base；tier 2 逐轴变化；tier 3 笛卡尔积
   - 若展开数量 > `search.max_candidates`，按 `search.priority_axes`（默认覆盖 attention_backend / chunked_prefill_size / max_running_requests / mem_fraction_static / tp_size）排序保留（base 必保留）
   - 与所有 dataset 组合笛卡尔积展开为实验列表
   - 同 `server_config_id` 的实验通过 `dependencies` 链接（预留给未来"同 server 复用"调度；默认 runner 仍按行串行）
   - 每个实验独立启停服务（消除冷启动偏差）

2. 展示 plan 给用户确认。未通过则调整 spec.yaml（改 tier / max_candidates / priority_axes / 搜索维度）重跑。

### 阶段 3：benchmark 执行

主 agent 按 `dependencies` 拓扑序调度：

- 对每个就绪实验启动 subagent：
  ```bash
  bash scripts/run_experiment.sh --plan plan.json --experiment-id N \
      --ssh-host <HOST> --ssh-key <KEY> --ssh-user <USER>
  ```
- subagent 流程：SSH 启动 `serve_cmd` → 健康检查等待就绪 → 执行 `bench_cmd` → 写入 `output_file` → shutdown 服务
- 主 agent 用 TaskUpdate 更新进度
- `search.resume: true` 时跳过已有结果的实验

### 阶段 4：结果汇总

```bash
python scripts/aggregate_results.py --plan plan.json --results-dir results/ --out report.md
```

产出：
- `results/all.jsonl`：所有实验结果合并
- `report.md`：
  - 按 server 配置分组的 markdown 对比表（吞吐 / TTFT p50/p99 / ITL）
  - Mermaid xychart：吞吐 vs 并发、TTFT vs 并发

## 核心数据契约

### spec.yaml

见 `assets/spec_template.yaml`。顶层字段：

| 字段 | 说明 |
|------|------|
| `server.host` / `port` / `env` | 服务运行环境 |
| `server.base_flags` | 基线参数（必须覆盖 search_space 所有键） |
| `server.search_space` | 搜索维度与候选值 |
| `benchmark.backend` | `sglang` / `sglang-oai` / `sglang-oai-chat` |
| `datasets` | 数据集列表（`random` / `generated_shared_prefix`），每个 dataset 内列表字段做笛卡尔积 |
| `search.tier` | 1 / 2 / 3 |
| `search.max_candidates` | server 配置数上限 |
| `search.priority_axes` | 可选。超额时优先保留触发这些轴的配置；不设置则使用内置默认 |
| `search.resume` | 是否跳过已有结果 |

### plan.json schema

见 `scripts/plan_schema.json`。顶层是一个对象：

| 字段 | 说明 |
|------|------|
| `dependencies` | 位置并列的 `list[list[int]]`：`dependencies[i]` 是 `experiment_list[i]` 的前置 experiment_id 列表；generate_plan 按 server_config_id 自动链式生成 |
| `experiment_list` | 实验列表，每项字段见下 |

`experiment_list[i]` 字段：

| 字段 | 说明 |
|------|------|
| `experiment_id` | 整数，唯一 |
| `serve_cmd` | SSH 启动命令（完整字符串） |
| `bench_cmd` | benchmark 命令（完整字符串，未列出的参数用 SGLang 默认值） |
| `output_file` | 本地结果 JSON 落盘路径 |
| `meta` | `{server_config_id, concurrency, dataset_kind}` 用于后续分组聚合 |

完整示例见 `assets/plan_example.json`。

## 脚本说明

| 脚本 | 语言 | 用途 |
|------|------|------|
| `scripts/generate_plan.py` | Python | 阶段 2：读 spec.yaml 一步生成 plan.json（展开 → 按 priority_axes 裁剪到 max_candidates → 交叉 dataset → 同 server_config_id 链式 dependencies） |
| `scripts/aggregate_results.py` | Python | 阶段 4：生成 report.md + 合并 JSONL |
| `scripts/dry_run.sh` | Shell | 阶段 1：用 base_flags SSH 启停验证，失败时返回日志尾部 |
| `scripts/run_experiment.sh` | Shell | 阶段 3：subagent 执行单个实验（启停 + bench + 落盘） |
| `scripts/ssh_utils.sh` | Shell | 内部：SSH 执行、后台启动、健康检查、强制 shutdown（source 使用） |
