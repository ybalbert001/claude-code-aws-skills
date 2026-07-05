# LLM 显存估算工具（vram_estimate.py）

输入一个 HuggingFace 模型 ID，自动拆解该模型部署所需的 GPU 显存：静态权重（逐部件）+ 运行时内存（KV cache、activation），输出终端报告和一张可交互的单文件 HTML 拆解图。

```bash
python3 vram_estimate.py zai-org/GLM-5.2-FP8 --html glm.html
python3 vram_estimate.py deepseek-ai/DeepSeek-V4-Flash --context 131072 --requests 16 --html dsv4.html
python3 vram_estimate.py Qwen/Qwen3-32B --kv-dtype fp8 --no-exact
```

仅依赖 Python 标准库。gated 模型设置 `HF_TOKEN` 环境变量。

## 文件结构

| 文件 | 作用 |
|---|---|
| `vram_estimate.py` | 主脚本：拉取配置、计算、渲染 |
| `template.html` | HTML 模板（样式 + 页面骨架 + 交互 JS），与计算逻辑分离，用 `string.Template` 占位符填充 |
| `*.html`（生成物） | 单文件、无外部依赖、离线可交互、自动适配深色模式 |

---

## 一、技术思路

### 1. 两级数据来源：config 公式 + safetensors 精确值

**第一级（公式估算）**：拉取 `config.json`，按 Transformer 结构逐部件数参数：

- embed / lm_head：`vocab_size × hidden_size`（`tie_word_embeddings` 时只算一份）
- Attention：区分三种结构（见下）
- FFN：dense 层 `3 × hidden × intermediate_size`；MoE 层 `3 × hidden × moe_intermediate_size × n_routed_experts`，另加 shared experts 与 router/gate
- 特殊部件：DSA indexer（`index_n_heads` 存在时）、MTP 预测层（`num_nextn_predict_layers`）、norms
- 字节数 = 参数量 × dtype 字节（从 `quantization_config` / `torch_dtype` 判定）

**第二级（精确模式，默认开启）**：用 HTTP Range 请求只读取每个 safetensors 分片的 **JSON 头**（几百 KB，不下载权重），得到每个张量的真实 dtype、shape、字节数，按张量名正则归类到部件。这是混合精度 checkpoint 的唯一可靠来源。失败时自动回退公式估算（`--no-exact` 可强制跳过）。

> 注意：`model.safetensors.index.json` 必须用 `resolve/main/` URL 拉取——大文件在 `raw/main/` 下返回的是 git-lfs 指针而非 JSON（GLM-5.2 踩过此坑）。

### 2. 混合精度与 sub-byte 打包的自动识别（无需厂商提示）

**问题**：DeepSeek-V4-Flash 的 config 只声明 `quant_method: fp8`，但实际 MoE experts 是 **fp4**。若按「单一字节数 × 参数量」计算会高估 82%（271 vs 真实 148.6 GiB）。

**更隐蔽的问题**：fp4 权重在 safetensors 里不是以 4-bit dtype 存的，而是**两个 fp4 打包进一个 int8 字节**——header 里 dtype 显示 `I8`，shape 维度砍半（如 expert w1 存储 `I8 [2048, 2048]`，逻辑形状是 `2048 × 4096`）。直接读 dtype 会误标为 int8。

**解法——公式对账（reconciliation）**：手里有两个独立的参数量来源：

1. config 公式算出的「应有参数量」（与 dtype 无关的逻辑值）
2. safetensors shape 乘积的「表观参数量」

未打包时两者相等（偏差 <1%）；打包时表观值**恰好是公式值的 1/2、1/4 或 1/8**。检测规则：

```
部件含整数 dtype（I8/U8/I32...）张量，且 公式值/表观值 ≈ 2/4/8（±6% 容差）
→ 判定打包，参数量 × 倍数，位宽 = 存储位宽 ÷ 倍数
```

该方法不依赖任何厂商特定字段。实测：DeepSeek fp4-in-int8（2×）、AWQ int4-in-int32（8×，无任何 config 提示字段）均正确识别；GLM 纯 fp8 无误报。

4bit 的**名称**（fp4 vs int4）无法从字节判断，用 config 语义区分：`quant_method` 为 gptq/awq → int4；含 fp4/mxfp4/nvfp4 → fp4。只影响显示，不影响计算。

量化 scale 张量（`scales/scales_inv/qzeros/g_idx` 等）计入字节但不计入参数量，单独归为「量化scale」类（DeepSeek-V4-Flash 中占 6%）。

### 3. KV cache：结构判定 + 精度选择

**每 token 存储形态由 config 自动判定**（`kv_per_token_elems()`）：

| 判定 | 条件 | 每 token/层元素数 |
|---|---|---|
| MLA | 存在 `kv_lora_rank` | `kv_lora_rank + qk_rope_head_dim`（压缩 latent，全 head 共享） |
| GQA | `num_key_value_heads < num_attention_heads` | `2 × kv_heads × head_dim` |
| MHA | 两者相等 | `2 × heads × head_dim` |

实例：GLM-5.2 是 MLA（512+64=576）；Qwen3-32B 是 GQA 8 kv heads（2048）；DeepSeek-V4-Flash 是 GQA 1 kv head（=MQA，1024）——MQA 是 GQA 的极端形态，KV 节省效果与 MLA 同量级，但机制不同（结构上只留一份 vs 数学上压缩成 latent）。只有 MLA 分支才有「假如用 MHA 全存」的对比行。

**KV 精度（`--kv-dtype`，默认 auto）**——KV 精度不是模型属性，config 里没有字段声明它，是推理引擎的运行时决策。auto 的解析逻辑对齐 SGLang 源码：

- 一般模型：auto → 模型 dtype（bf16）（`model_runner.py: configure_kv_cache_dtype`；除非权重 quant_config 带 `kv_cache_quant_algo: FP8`）
- DSA/稀疏注意力模型（有 `index_topk`，或架构为 DeepseekV4/V32）：auto → **fp8_e4m3**（`deepseek_v4_hook.py` 甚至 assert 只允许 fp8）
- SGLang 还支持 `fp4_e2m1`（mxfp4，CUDA 12.8+）：有效字节 = **0.5 + 1/16 ≈ 0.5625**/元素——`memory_pool.py` 中数据按 uint8 半宽存储，另配每 16 元素 1 字节的 scale buffer。因约束多（特定后端组合），永不进入 auto，需显式选择。

**KV 总量 = 每 token 字节 × context × 并发请求数**，随两者线性增长。

### 4. Activation 工作区

与 KV 不同，activation 与并发请求数无关，只与**单次 forward 的 token 数**（`--batch-tokens`，默认 8192，对应 vLLM chunked prefill 上限）有关——逐层执行时只有当前层的中间结果存活。

估算式（bf16）：`每 token ≈ 2B × (8 × hidden + 2 × inter_eff)`，其中 MoE 模型的 `inter_eff = (top_k + n_shared) × moe_intermediate_size`。这是工作区量级估算（与 vLLM profile 保留值同量级），非精确值。

### 5. HTML 拆解图

- **布局**：左栏层结构示意（embed → dense 层 → MoE 层 → MTP → lm_head，颜色点对应右侧）；右栏分「静态·模型权重」和「动态·运行时内存」两组卡片；底部权重堆叠条 + 总占用堆叠条 + 可折叠表格视图
- **交互**：顶部筛选行三个下拉框——context（64K/128K/200K）、并发数（8/16/32/64）、KV 精度（auto/bf16/fp8/fp4）。Python 把不变量（每 token KV 元素数、权重字节、auto 解析结果等）以 JSON 嵌入页面，JS 在 change 事件里重算并更新所有带 id 的节点：KV 卡片推导链、标题、总占用条、表格行。静态权重部分不参与联动
- **精度标注**：每张卡片标题旁有统一样式的精度徽章（如 `fp4`、`fp8 90% + bf16 10%`），数据来自 safetensors 真实 dtype 按字节占比汇总（忽略 scale）；KV 卡片徽章动态显示当前选择（如 `fp8（auto）`）；表格视图有独立精度列
- 下拉框选项可用 `--ctx-options` / `--req-options` 自定义；CLI 当前值自动并入选项

---

## 二、验证结果

| 模型 | 特点 | 权重结果 | 对照 |
|---|---|---|---|
| GLM-5.2-FP8 | 755B MoE、MLA、DSA、MTP、fp8 | 703.7 GiB | 与手工推导图一致（MoE 675 GiB 占 96%） |
| DeepSeek-V4-Flash | 291B MoE、MQA、fp4+fp8 混合精度 | 148.6 GiB | 与 index 声明的 148.65 GiB 完全一致 |
| Qwen3-32B | 稠密、GQA、bf16 | 61.0 GiB | 与官方参数量一致 |
| Qwen2.5-7B-AWQ | int4 AWQ（int32 打包） | 5.2 GiB | config-only 估算会低估至 3.5 GiB（embed/norm 仍 fp16 + scale 开销） |

---

## 三、注意事项与已知局限

1. **KV cache 精度是部署决策不是模型属性**。auto 只是对齐 SGLang 当前默认；vLLM/TensorRT-LLM 规则不同。fp4 KV 较激进，长上下文精度影响未被广泛验证，生产前需自行评测。
2. **DeepSeek-V4-Flash 的 KV 是保守上界**。config 里的 `sliding_window: 128`、`compress_ratios`（4×/128× 交替）、`num_hash_layers` 表明有内建 KV 压缩机制，真实占用可能显著小于图中「全量 GQA」口径；等推理框架落地后可把 `compress_ratios` 语义编入。
3. **Activation 是量级估算**，真实值受 CUDA graph、attention kernel 实现影响。KV cache 部分是精确公式。
4. **MHA 对比口径**：MLA 卡片的「假如用 MHA」按 K+V 全存计算（`heads × (qk_head_dim + v_head_dim)`）；有些资料只算 K 或用对称口径，数值会差 2×。
5. **总占用 = 权重 + KV + activation + 碎片 5%**（`--overhead` 可调），未含 CUDA context（每卡 ~0.5-1 GiB）和多卡并行的通信 buffer。
6. **精确模式的网络依赖**：需能访问 huggingface.co；每个分片一次小的 Range 请求（46 分片模型约几秒）。失败自动回退公式。
7. **多模态模型**取 `text_config` 子树计算（未含视觉塔）。
8. **公式覆盖范围**：MLA/GQA/MHA、MoE（含 shared/gate/first_k_dense_replace）、DSA indexer、MTP、q/o 低秩分解。全新结构（如 V4 的 hyper-connection `hc_*` 参数）在精确模式下会被归入 norms & misc 兜底类——字节数不丢，只是分类粗。

---

## 四、Session 中确认过的关键细节

- **GLM-5.2 图中 285.6 vs 本工具 571.3 GiB 的 MHA 对比差异**：口径问题（只算 K vs K+V 全存），MLA 实际占用 10 GiB 两边一致。
- **`intermediate_size` 可以缺失**（V4-Flash 全 MoE 无 dense 层），需容错。
- **`first_k_dense_replace` 为 0** 时左栏不画 Dense 层。
- **fp4 打包证据**：expert `w1.weight I8 [2048,2048]` vs 逻辑 `2048×4096` = 0.5 字节/参数；scale `F8_E8M0 [2048,128]` = 每 32 元素一个（MXFP4 block-32）；shared expert 对照组 `F8_E4M3 [2048,4096]` 全形状。
- **SGLang `--kv-cache-dtype` 默认 `auto`**；DSA 模型按 GPU 代际（SM≥10 → fp8）；V4 钩子强制 fp8；一般模型 → 模型 dtype。
- **SGLang fp4 KV 池布局**：`k/v_buffer` 半宽 uint8 + `k/v_scale_buffer` 每 16 元素 1 字节（`scale_block_size = 16`），故有效 0.5625 字节/元素，相对 fp8 实际省 1.78× 而非 2×。
