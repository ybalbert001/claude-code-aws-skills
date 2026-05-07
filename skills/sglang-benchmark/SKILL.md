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

1. **必须通过 `AskUserQuestion` 工具**依次采集以下字段（不要用纯文本提问）：
   - **部署目标**：`ec2` / `hyperpod`（单选）
   - **SSH Host**：EC2 / HyperPod 跳板机的 public IP 或 DNS
   - **SSH Private Key**：私钥路径（如 `~/.ssh/id_rsa`）
   - **SSH User**：登录用户名（如 `ubuntu` / `ec2-user`）

   说明：`AskUserQuestion` 每个问题至少需 2 个选项。对 Host / Key / User 这类自由文本字段，给出 1-2 个常见默认值作为选项（如 `ubuntu` / `ec2-user`），用户可点 "Other" 自行输入。
2. 采集信息构建benchmark的`spec.yaml`(基于 `assets/spec_template.yaml`)
   - 探测硬件信息并向用户询问部署的模型
   - 向用户询问部署方式（可以直接提供部署命令，也可以参考网页)
   - 基于提取的建议和大模型推理知识，提取server运行的base_flags(基线参数)和需要进行search的params
3. **dry run**：
   ```bash
   bash scripts/dry_run.sh --spec spec.yaml --ssh-host <HOST> --ssh-key <KEY>
   ```
   - 用 `spec.yaml.server.base_flags` 启动 server，健康检查通过后 shutdown
   - 失败时把 server 日志尾部返回给用户，用户修 spec.yaml 后重试，直到通过
4. 向用户展示已采集信息，提取用户确认生成的spec.yaml，确认后进入阶段 2

**约束**：`base_flags` 必须覆盖 `search_space` 的所有键（作为 tier 2 的锚点）。

### 阶段 2：benchmark 规划

1. 机械展开 `search_space`（依据 `search.tier`），落 `expanded.json`：
   ```bash
   python scripts/generate_plan.py --spec spec.yaml --stage expand --out expanded.json
   ```
   - tier 1: 只跑 `base_flags`（1 个 server 配置）
   - tier 2: 逐轴变化（base 为锚点，每维度其他值 × 其他维度保持 base）
   - tier 3: 完整笛卡尔积

2. 若展开数量 > `search.max_candidates`：**Claude 基于 SGLang 先验知识挑选**
   - `max_candidates` 计量单位：**server 配置数**（不含 dataset × concurrency × qps 链展开）
   - 挑选依据：覆盖关键参数维度、优先经验上敏感的轴（如 attention backend、tp、mem_fraction）

3. 将挑选后的 server 配置与所有 dataset 参数组合（每个 dataset 内部字段做笛卡尔积）展开为实验列表，落 `plan.jsonl`：
   ```bash
   python scripts/generate_plan.py --spec spec.yaml --stage finalize \
       --selected selected.json --out plan.jsonl
   ```
   每个实验独立启停一次服务（消除冷启动偏差）。

4. 展示 plan 给用户确认。未通过则交互式调整（改 tier / 改 max_candidates / 手动增删）直到确认。

### 阶段 3：benchmark 执行

主 agent 按 `dependencies` 拓扑序（通常为空，同机串行由 runner 保证）调度：

- 对每个就绪实验启动 subagent：
  ```bash
  bash scripts/run_experiment.sh --plan plan.jsonl --experiment-id N \
      --ssh-host <HOST> --ssh-key <KEY> --ssh-user <USER>
  ```
- subagent 流程：SSH 启动 `serve_cmd` → 健康检查等待就绪 → 执行 `bench_cmd` → 写入 `output_file` → shutdown 服务
- 主 agent 用 TaskUpdate 更新进度
- `search.resume: true` 时跳过已有结果的实验

### 阶段 4：结果汇总

```bash
python scripts/aggregate_results.py --plan plan.jsonl --results-dir results/ --out report.md
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
| `search.resume` | 是否跳过已有结果 |

### plan.jsonl 行 schema

见 `scripts/plan_schema.json`。核心字段：

| 字段 | 说明 |
|------|------|
| `experiment_id` | 整数，唯一 |
| `serve_cmd` | SSH 启动命令（完整字符串） |
| `bench_cmd` | benchmark 命令（完整字符串，未列出的参数用 SGLang 默认值） |
| `dependencies` | 前置 `experiment_id` 列表（通常为空） |
| `deploy_target` | `ec2` / `hyperpod` |
| `output_file` | 结果 JSON 落盘路径 |
| `meta` | `{server_config_id, dataset, concurrency}` 用于后续分组聚合 |

## 脚本说明

| 脚本 | 语言 | 用途 |
|------|------|------|
| `scripts/generate_plan.py` | Python | 阶段 2：`--stage expand` 展开搜索空间；`--stage finalize` 组合生成 plan.jsonl |
| `scripts/aggregate_results.py` | Python | 阶段 4：生成 report.md + 合并 JSONL |
| `scripts/dry_run.sh` | Shell | 阶段 1：用 base_flags SSH 启停验证，失败时返回日志尾部 |
| `scripts/run_experiment.sh` | Shell | 阶段 3：subagent 执行单个实验（启停 + bench + 落盘） |
| `scripts/ssh_utils.sh` | Shell | 内部：SSH 执行、后台启动、健康检查、强制 shutdown（source 使用） |
