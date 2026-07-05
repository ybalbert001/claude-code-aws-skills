---
name: vram-estimator
description: Estimate GPU memory (VRAM) requirements for deploying any HuggingFace LLM — weights breakdown by component, KV cache, activation workspace — and generate an interactive HTML breakdown diagram. Use this whenever the user asks how much GPU memory / 显存 a model needs, whether a model fits on specific GPUs (e.g. "能跑在 8×H100 上吗"), how large the KV cache grows with context length or concurrency, what a model's weight composition is (MoE experts vs attention vs embeddings), or wants a deployment-capacity/显存拆解 analysis or diagram for a model given its HuggingFace ID. Also use it to compare memory across quantization variants (fp8/fp4/AWQ/GPTQ) of a model.
---

# LLM VRAM Estimator

Estimates the GPU memory needed to deploy an LLM, given only its HuggingFace model ID. Splits memory into **static weights** (per-component: embed, attention, dense FFN, MoE experts, MTP, ...) and **runtime memory** (KV cache scaling with context × concurrent requests, plus activation workspace), and can render a self-contained interactive HTML diagram.

## How to run

The bundled script does all the work. Run it directly — do not re-derive the math by hand:

```bash
python3 scripts/vram_estimate.py <org/model-id> [options]
```

Common invocations:

```bash
# Text report only, all defaults (128K context × 16 requests, kv-dtype auto)
python3 scripts/vram_estimate.py zai-org/GLM-5.2-FP8

# With the interactive HTML diagram
python3 scripts/vram_estimate.py deepseek-ai/DeepSeek-V4-Flash --html dsv4.html

# Custom deployment shape
python3 scripts/vram_estimate.py Qwen/Qwen3-32B --context 32768 --requests 64 --kv-dtype fp8
```

Key options:

| Flag | Default | Meaning |
|---|---|---|
| `--context` | 131072 | context length per request (drives KV cache) |
| `--requests` | 16 | concurrent running requests (KV scales linearly) |
| `--kv-dtype` | auto | `auto`/`bf16`/`fp8`/`fp4`; auto mirrors SGLang (fp8 for DSA/sparse-attention models, else bf16) |
| `--batch-tokens` | 8192 | tokens per forward pass (drives activation estimate) |
| `--html FILE` | — | write interactive diagram (3 dropdowns: context / concurrency / KV dtype, live recompute) |
| `--ctx-options`, `--req-options` | 64K,128K,200K / 8,16,32,64 | dropdown choices in the HTML |
| `--no-exact` | off | skip safetensors headers, formula-only estimate |
| `--overhead` | 0.05 | fragmentation allowance on the total |

Needs network access to huggingface.co. For gated repos, set `HF_TOKEN`. The script only range-requests safetensors JSON headers (a few hundred KB) — it never downloads weights.

## Interpreting and reporting results

When relaying results to the user, lead with the bottom line (total GiB and whether it fits their hardware if they named any), then the composition. Key things to get right:

- **Weights vs runtime are different beasts.** Weights are paid once at load; KV cache grows linearly with `context × concurrent requests` (the report prints the per-request increment — use it to answer "how many concurrent users fit"). Activation is independent of concurrency.
- **The "exact from safetensors" line means the weight numbers are ground truth**, including mixed-precision checkpoints (e.g. fp4 experts + bf16 attention). If the script fell back to formula mode (a `note:` on stderr), say the weight number is an estimate.
- **KV cache dtype is a deployment decision, not a model property.** `auto` mirrors SGLang defaults; other engines differ. If the user cares about the KV number, mention which dtype was assumed. fp4 KV is aggressive/experimental — flag it.
- **Not included in the total**: CUDA context (~0.5–1 GiB per GPU) and multi-GPU communication buffers. Mention this when the fit is tight.
- Models with built-in KV compression configs (`compress_ratios`, `sliding_window` on sparse-attention models) may use less KV than reported — the script computes the no-compression upper bound.

For a fit check ("does it run on N × GPU?"): compare the grand total against N × per-GPU memory, and note that tensor-parallel sharding also needs the weights to divide reasonably across GPUs.

## When something breaks or looks wrong

The script is validated against GLM-5.2 (fp8, MLA+DSA+MTP), DeepSeek-V4-Flash (fp4/fp8 mixed, MQA), NVIDIA NVFP4 repacks, Qwen dense GQA, and AWQ int4. If it crashes or produces numbers that look off on a new model:

1. Fetch the config yourself and look for unusual fields: `curl -sL https://huggingface.co/<id>/raw/main/config.json`
2. Read `references/methodology.md` — it documents the estimation approach (config formulas, safetensors reconciliation for sub-byte packing detection, MLA/GQA/MHA KV rules, SGLang kv-dtype auto logic) and known limitations. Use it to extend the script rather than hand-computing.
3. Cross-check totals against `model.safetensors.index.json` metadata `total_size` (fetch via `resolve/main/`, not `raw/main/` — the latter returns an LFS pointer for large files).

For multimodal models the script analyzes `text_config` only (no vision tower). For models not on HuggingFace, or hypothetical configs, the script can't fetch — offer a formula-based estimate from `references/methodology.md` instead and label it clearly as such.
