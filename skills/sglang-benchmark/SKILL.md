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
   - 若展开数量 > `search.max_candidates`，按 `search.priority_axes` 排序保留（base 必保留）
   - 与所有 dataset 组合笛卡尔积展开为实验列表

   注意：执行顺序为一组bench dataset, 需要跑完所有的server_config，然后再跑下一组dataset

2. 展示 plan 给用户确认。未通过则一直提示用户调整 spec.yaml（改 tier / max_candidates / priority_axes / 搜索维度）。

### 阶段 3：benchmark 执行

**执行模式**：主 agent 用**一次 Bash 后台任务**（`run_in_background: true`）跑完所有实验，避免跨几十次 tool call 频繁打断用户。

```bash
# 伪代码模板：外层 shell for 循环串行调用 run_experiment.sh
{
  for eid in $(python3 -c "import json; print(' '.join(str(e['experiment_id']) for e in json.load(open('plan.json'))['experiment_list']))"); do
    echo "=== [$(date +%H:%M:%S)] exp $eid ==="
    bash scripts/run_experiment.sh \
      --plan plan.json --experiment-id $eid \
      --spec spec.yaml --results-dir results/ \
      --ssh-host <HOST> --ssh-key <KEY> --ssh-user <USER> \
      --resume 2>&1 | grep -E "^\[exp|error|FAILED" || true
    # 单实验失败不中止 batch，最后再汇总
  done
  echo "=== BATCH DONE [$(date +%H:%M:%S)] ==="
} > runs/<name>/batch.log 2>&1
# 通过 run_in_background: true 启动；完成后收到 task-notification
```

**单实验流程**（`run_experiment.sh`）：SSH 启动 `serve_cmd` → 健康检查等待就绪 → 清理远程 `--output-file`（防止 bench_serving append 累积）→ 执行 `bench_cmd` → scp 回结果 → shutdown 服务

**要点**：
- `--resume` 跳过已有非空 `output_file`，失败重跑安全
- batch 脚本内 `if ! ...; exit 1` 写法要避免，改为记录失败继续
- 背景任务完成后，主 agent 查 `batch.log` 汇总失败实验并报告给用户

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

见 `assets/plan_schema.json`。顶层对象只有 `experiment_list`；实验独立（每次重启服务），按列表顺序执行。外层按 dataset 分组：同一 dataset 的所有 server_config 跑完后再进入下一个 dataset。

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
| `scripts/generate_plan.py` | Python | 阶段 2：读 spec.yaml 一步生成 plan.json（展开 → 按 priority_axes 裁剪到 max_candidates → 交叉 dataset，外层 dataset 内层 server_config） |
| `scripts/aggregate_results.py` | Python | 阶段 4：生成 report.md + 合并 JSONL |
| `scripts/dry_run.sh` | Shell | 阶段 1：用 base_flags SSH 启停验证，失败时返回日志尾部 |
| `scripts/run_experiment.sh` | Shell | 阶段 3：subagent 执行单个实验（启停 + bench + 落盘） |
| `scripts/ssh_utils.sh` | Shell | 内部：SSH 执行、后台启动、健康检查、强制 shutdown（source 使用） |
