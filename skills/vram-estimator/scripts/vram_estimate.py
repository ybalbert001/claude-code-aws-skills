#!/usr/bin/env python3
"""
Estimate GPU memory footprint of an LLM from its HuggingFace config.json,
and optionally render a breakdown diagram as a self-contained HTML page
(template lives in template.html next to this script).

Memory is split into two groups:
  * static  — model weights: paid once at load time, independent of traffic
  * runtime — KV cache (grows with context_length x running_requests) and
              activation workspace (grows with tokens in flight per forward pass)

Usage:
    python3 vram_estimate.py zai-org/GLM-5.2-FP8
    python3 vram_estimate.py zai-org/GLM-5.2-FP8 --context 120000 --requests 8 --html glm.html
    python3 vram_estimate.py Qwen/Qwen3-32B --context 32768 --requests 16 --kv-dtype fp8

Only stdlib is used. For gated repos set HF_TOKEN env var.
"""

import argparse
import json
import math
import os
import re
import string
import struct
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

GIB = 1024 ** 3
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")

# categorical slots in fixed order (dataviz reference palette; values live in template.html)
COMP_SLOT = {"embed": 0, "lm_head": 0, "attention": 1, "dense_ffn": 2,
             "moe_routed": 3, "moe_shared": 3, "moe_gate": 3,
             "mtp": 4, "indexer": 7, "norms": 7,
             "kv": 5, "act": 6}


# ---------------------------------------------------------------- fetch

def fetch_config(model_id: str) -> dict:
    url = f"https://huggingface.co/{model_id}/raw/main/config.json"
    req = urllib.request.Request(url, headers={"User-Agent": "vram-estimate/1.0"})
    token = os.environ.get("HF_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


# ---------------------------------------------------------------- exact sizes from safetensors

def _fetch_range(url: str, start: int, length: int) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "vram-estimate/1.0",
        "Range": f"bytes={start}-{start + length - 1}",
    })
    token = os.environ.get("HF_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def fetch_safetensors_catalog(model_id: str) -> tuple[dict, int | None]:
    """Per-tensor {name: {dtype, shape, bytes}} from safetensors headers.

    Only range-requests each shard's JSON header (a few hundred KB), never the
    weights. This is the ground truth for mixed-precision checkpoints where a
    single bytes-per-param number is wrong.
    """
    base = f"https://huggingface.co/{model_id}/resolve/main"
    declared = None
    try:
        # resolve/ follows git-lfs; raw/ would return the LFS pointer for big indexes
        req = urllib.request.Request(
            f"{base}/model.safetensors.index.json",
            headers={"User-Agent": "vram-estimate/1.0"})
        token = os.environ.get("HF_TOKEN")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            idx = json.load(resp)
        files = sorted(set(idx["weight_map"].values()))
        declared = (idx.get("metadata") or {}).get("total_size")
    except urllib.error.HTTPError:
        files = ["model.safetensors"]  # single-file checkpoint

    def header(fname):
        url = f"{base}/{fname}"
        n = struct.unpack("<Q", _fetch_range(url, 0, 8))[0]
        h = json.loads(_fetch_range(url, 8, n))
        h.pop("__metadata__", None)
        return h

    catalog = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for h in ex.map(header, files):
            for name, meta in h.items():
                b = meta["data_offsets"][1] - meta["data_offsets"][0]
                catalog[name] = {"dtype": meta["dtype"], "shape": meta["shape"], "bytes": b}
    return catalog, declared


def classify_tensor(name: str, num_layers: int) -> str:
    """Map a tensor name to a component key. Handles HF-standard naming
    (model.layers.N.self_attn...) and DeepSeek-style (layers.N.attn.wkv...)."""
    n = name.lower()
    m = re.search(r"(?:^|\.)(?:mtp|nextn)\.", n)
    if m:
        return "mtp"
    lm = re.search(r"layers\.(\d+)\.", n)
    if lm and int(lm.group(1)) >= num_layers:   # extra layers beyond L are MTP
        return "mtp"
    if re.search(r"(?:^|\.)hc_", n):            # hyper-connection / highway params
        return "norms"
    if "layernorm" in n or re.search(r"(?:^|[._])norm\b", n) or n.endswith("norm.weight"):
        return "norms"
    if "embed" in n:
        return "embed"
    if "lm_head" in n or re.match(r"(?:model\.)?head\.", n):
        return "lm_head"
    if "indexer" in n:
        return "indexer"
    if "shared_expert" in n:
        return "moe_shared"
    if re.search(r"\.experts\.", n):
        return "moe_routed"
    if re.search(r"\.(?:mlp|ffn)\.gate\.", n):  # router (gate_proj is dense FFN)
        return "moe_gate"
    if re.search(r"\.(?:mlp|ffn)\.", n):
        return "dense_ffn"
    if "attn" in n or "attention" in n:
        return "attention"
    return "norms"


# quantization metadata tensors: storage overhead, not model parameters
QUANT_META = re.compile(r"(?:^|\.|_)(scales?(?:_inv)?|qzeros|zeros|g_idx|zero_point)(?:$|\.)")
INT_DTYPES = {"I8": 8, "U8": 8, "I16": 16, "U16": 16, "I32": 32, "U32": 32}


def _sub_byte_name(cfg: dict, bits: int) -> str:
    """fp4 vs int4 for packed weights, from config conventions."""
    qc = cfg.get("quantization_config") or {}
    text = (json.dumps(qc) + " " + str(cfg.get("expert_dtype", ""))).lower()
    if bits == 4:
        if "fp4" in text or "mxfp4" in text or "nvfp4" in text:
            return "fp4"
        if qc.get("quant_method") in ("gptq", "awq") or "int" in text:
            return "int4"
        return "4bit"
    return f"{bits}bit"


def exact_components(catalog: dict, cfg: dict) -> tuple[dict, dict, dict]:
    """Aggregate the tensor catalog into per-component bytes/params/dtypes.

    Sub-byte packing (e.g. two fp4 values per int8 byte, or eight int4 per
    int32 word) is detected WITHOUT any model-specific config hint: for each
    component, the shape-derived param count is reconciled against the
    config-formula count. An integer-dtype component whose apparent count is
    1/2, 1/4 or 1/8 of the formula is unpacked by that factor.
    """
    L = cfg["num_hidden_layers"]
    p = count_params(cfg)
    # components whose closed-form param count is reliable enough to reconcile
    formula = {"embed": p["embed"], "lm_head": p["lm_head"], "attention": p["attention"],
               "dense_ffn": p["dense_ffn"], "moe_routed": p["moe_routed"],
               "moe_shared": p["moe_shared"], "mtp": p["mtp"]}

    groups = {}
    for name, t in catalog.items():
        groups.setdefault(classify_tensor(name, L), []).append((name, t))

    # config-declared hint (e.g. DeepSeek expert_dtype) as fallback confirmation
    hint_fp4 = str(cfg.get("expert_dtype", "")).lower() in ("fp4", "mxfp4", "nvfp4")

    by_key, dtype_hist, comp_dtypes = {}, {}, {}
    for key, tensors in groups.items():
        apparent = 0
        has_int_weight = False
        for name, t in tensors:
            if QUANT_META.search(name):
                continue
            apparent += math.prod(t["shape"]) if t["shape"] else 1
            if t["dtype"] in INT_DTYPES:
                has_int_weight = True

        # ---- packing factor: formula/apparent ≈ 2, 4 or 8 (±6%)
        pack = 1
        expected = formula.get(key)
        if has_int_weight and expected and apparent:
            ratio = expected / apparent
            for cand in (2, 4, 8):
                if abs(ratio - cand) <= 0.06 * cand:
                    pack = cand
                    break
        if pack == 1 and has_int_weight and hint_fp4 \
                and key in ("moe_routed", "moe_shared", "mtp"):
            pack = 2

        d = {"bytes": 0, "params": 0}
        dts = {}
        for name, t in tensors:
            is_meta = bool(QUANT_META.search(name))
            if is_meta:
                dt = "QSCALE"
            elif pack > 1 and t["dtype"] in INT_DTYPES:
                dt = _sub_byte_name(cfg, INT_DTYPES[t["dtype"]] // pack)
            else:
                dt = t["dtype"]
            d["bytes"] += t["bytes"]
            dts[dt] = dts.get(dt, 0) + t["bytes"]
            dtype_hist[dt] = dtype_hist.get(dt, 0) + t["bytes"]
            if not is_meta:
                params = math.prod(t["shape"]) if t["shape"] else 1
                if pack > 1 and t["dtype"] in INT_DTYPES:
                    params *= pack
                d["params"] += params
        by_key[key] = d
        comp_dtypes[key] = dts
    return by_key, dtype_hist, comp_dtypes


def dtype_label(dtype_hist: dict) -> str:
    """Human name for the weight storage: 'fp8' or 'mixed: I8(fp4) 87% + ...'."""
    nice = {"F8_E4M3": "fp8", "F8_E5M2": "fp8", "BF16": "bf16", "F16": "fp16",
            "F32": "fp32", "I8": "int8", "U8": "uint8", "I64": "int64",
            "F8_E8M0": "量化scale", "QSCALE": "量化scale", "F4": "fp4", "U4": "fp4"}
    total = sum(dtype_hist.values())
    ranked = sorted(dtype_hist.items(), key=lambda kv: -kv[1])
    if ranked[0][1] / total >= 0.97:
        return nice.get(ranked[0][0], ranked[0][0])
    parts = [f"{nice.get(dt, dt)} {b / total:.0%}"
             for dt, b in ranked if b / total >= 0.02][:4]
    return "混合精度: " + " + ".join(parts)


# ---------------------------------------------------------------- dtype

def weight_bytes_per_param(cfg: dict) -> tuple[float, str]:
    qc = cfg.get("quantization_config") or {}
    method = (qc.get("quant_method") or "").lower()
    if method == "fp8":
        return 1.0, "fp8"
    if method in ("awq", "gptq"):
        bits = qc.get("bits", 4)
        return bits / 8, f"{method}-int{bits}"
    if method == "compressed-tensors":
        for g in (qc.get("config_groups") or {}).values():
            w = g.get("weights") or {}
            if w.get("num_bits"):
                return w["num_bits"] / 8, f"ct-int{w['num_bits']}"
        return 1.0, "compressed-tensors"
    dtype = (cfg.get("dtype") or cfg.get("torch_dtype") or "bfloat16").lower()
    if "float32" in dtype:
        return 4.0, "fp32"
    if "float16" in dtype or "bfloat16" in dtype:
        return 2.0, dtype.replace("torch.", "")
    return 2.0, dtype


# ---------------------------------------------------------------- params

def count_params(cfg: dict) -> dict:
    """Return per-component parameter counts (not bytes)."""
    H = cfg["hidden_size"]
    L = cfg["num_hidden_layers"]
    V = cfg["vocab_size"]
    n_heads = cfg["num_attention_heads"]
    p = {}

    # ---- embeddings
    p["embed"] = V * H
    p["lm_head"] = 0 if cfg.get("tie_word_embeddings") else V * H

    # ---- attention: MLA vs GQA/MHA
    is_mla = bool(cfg.get("kv_lora_rank"))
    if is_mla:
        q_lora = cfg.get("q_lora_rank")
        qk_nope = cfg["qk_nope_head_dim"]
        qk_rope = cfg["qk_rope_head_dim"]
        v_dim = cfg["v_head_dim"]
        kv_lora = cfg["kv_lora_rank"]
        qk_head = qk_nope + qk_rope
        if q_lora:  # low-rank Q: q_a + q_b
            attn = H * q_lora + q_lora * n_heads * qk_head
        else:
            attn = H * n_heads * qk_head
        attn += H * (kv_lora + qk_rope)                # kv_a (+ decoupled rope k)
        attn += kv_lora * n_heads * (qk_nope + v_dim)  # kv_b
        attn += n_heads * v_dim * H                    # o_proj
    else:
        head_dim = cfg.get("head_dim") or H // n_heads
        n_kv = cfg.get("num_key_value_heads", n_heads)
        attn = (H * n_heads * head_dim             # q
                + 2 * H * n_kv * head_dim          # k, v
                + n_heads * head_dim * H)          # o
        if cfg.get("attention_bias"):
            attn += (n_heads + 2 * n_kv) * head_dim
    p["attention"] = attn * L
    p["attention_per_layer"] = attn
    p["is_mla"] = is_mla

    # ---- DSA/NSA indexer (lightning indexer, e.g. GLM-5.x / DeepSeek-V3.2)
    idx = 0
    if cfg.get("index_n_heads"):
        d_i = cfg.get("index_head_dim", 128)
        n_i = cfg["index_n_heads"]
        idx = (H * n_i * d_i + H * d_i + H * n_i) * L
    p["indexer"] = idx

    # ---- FFN: dense layers vs MoE layers
    inter = cfg.get("intermediate_size") or 4 * H  # some configs omit it (all-MoE nets)
    n_routed = cfg.get("n_routed_experts") or cfg.get("num_experts") or cfg.get("num_local_experts") or 0
    if n_routed:
        first_dense = cfg.get("first_k_dense_replace", 0)
        moe_layers = L - first_dense
        moe_inter = cfg.get("moe_intermediate_size", inter)
        n_shared = cfg.get("n_shared_experts", 0) or 0
        expert = 3 * H * moe_inter                 # gate/up/down
        p["dense_ffn"] = 3 * H * inter * first_dense
        p["moe_routed"] = expert * n_routed * moe_layers
        p["moe_shared"] = expert * n_shared * moe_layers
        p["moe_gate"] = (H * n_routed + n_routed) * moe_layers  # router + e_score bias
        p["moe_layers"] = moe_layers
        p["dense_layers"] = first_dense
    else:
        p["dense_ffn"] = 3 * H * inter * L
        p["moe_routed"] = p["moe_shared"] = p["moe_gate"] = 0
        p["moe_layers"] = 0
        p["dense_layers"] = L

    # ---- norms & misc
    p["norms"] = (2 * H) * L + H

    # ---- MTP (multi-token prediction) extra layer(s)
    n_mtp = cfg.get("num_nextn_predict_layers", 0) or 0
    if n_mtp:
        moe_inter = cfg.get("moe_intermediate_size", inter)
        n_shared = cfg.get("n_shared_experts", 0) or 0
        mtp_ffn = 3 * H * moe_inter * (n_routed + n_shared) if n_routed else 3 * H * inter
        mtp = attn + (idx // L if idx else 0) + mtp_ffn + 2 * H * H
        p["mtp"] = mtp * n_mtp
    else:
        p["mtp"] = 0

    return p


# ---------------------------------------------------------------- runtime memory

def kv_per_token_elems(cfg: dict) -> tuple[int, str]:
    """Elements stored per token per layer, and a description."""
    if cfg.get("kv_lora_rank"):
        elems = cfg["kv_lora_rank"] + cfg["qk_rope_head_dim"]
        return elems, f"MLA latent: kv_lora {cfg['kv_lora_rank']} + rope {cfg['qk_rope_head_dim']} = {elems}/token/layer"
    n_heads = cfg["num_attention_heads"]
    n_kv = cfg.get("num_key_value_heads", n_heads)
    head_dim = cfg.get("head_dim") or cfg["hidden_size"] // n_heads
    elems = 2 * n_kv * head_dim
    kind = "MHA" if n_kv == n_heads else f"GQA ({n_kv} kv heads)"
    return elems, f"{kind}: 2 x {n_kv} x {head_dim} = {elems}/token/layer"


def activation_bytes(cfg: dict, p: dict, batch_tokens: int) -> tuple[int, str]:
    """Peak activation workspace for one forward pass over `batch_tokens` tokens.

    Layers execute sequentially, so only one layer's intermediates are live at a
    time (plus residual/hidden buffers and the logits for the sampled positions).
    Per token, in bf16 (2 bytes): a few hidden-sized buffers (residual, attn in/out,
    double-buffering) + the FFN up/gate intermediate. MoE: each token runs top-k
    experts, so the intermediate is top_k x moe_intermediate. This matches the
    order of what vLLM's memory profiler reserves; it is a workspace estimate,
    not an exact number.
    """
    H = cfg["hidden_size"]
    inter = cfg.get("intermediate_size") or 4 * H
    if p["moe_layers"]:
        topk = cfg.get("num_experts_per_tok", 1)
        n_shared = cfg.get("n_shared_experts", 0) or 0
        inter_eff = (topk + n_shared) * cfg.get("moe_intermediate_size", inter)
    else:
        inter_eff = inter
    per_token = 2 * (8 * H + 2 * inter_eff)   # bf16: ~8 hidden-size buffers + gate/up
    total = batch_tokens * per_token
    desc = (f"每 token ≈ 2B × (8×{H} + 2×{inter_eff:,}) = {per_token / 1024:,.0f} KiB"
            f"（残差/attn 缓冲 + FFN 中间层{'，MoE 按 top-k 有效宽度' if p['moe_layers'] else ''}）")
    return total, desc


# ---------------------------------------------------------------- analyze

def analyze(model_id: str, cfg: dict, ctx: int, requests: int, kv_dtype: str,
            batch_tokens: int, overhead: float, catalog: dict | None = None) -> dict:
    """All numbers the text report and the HTML diagram share.

    With a safetensors `catalog`, component bytes come from the real tensor
    sizes (exact, handles mixed precision); otherwise from formula x dtype.
    """
    wbytes, wname = weight_bytes_per_param(cfg)
    p = count_params(cfg)
    L = cfg["num_hidden_layers"]

    names = {
        "embed": "embed", "lm_head": "lm_head",
        "attention": "attention" + (" (MLA)" if p["is_mla"] else ""),
        "indexer": "attn indexer (DSA)",
        "dense_ffn": f"dense FFN ({p['dense_layers']} layers)",
        "moe_routed": f"MoE routed experts ({p['moe_layers']} layers)",
        "moe_shared": "MoE shared experts", "moe_gate": "MoE router/gate",
        "norms": "norms & misc", "mtp": "MTP layer(s)",
    }
    order = ["embed", "lm_head", "attention", "indexer", "dense_ffn",
             "moe_routed", "moe_shared", "moe_gate", "norms", "mtp"]

    exact = comp_dtypes = None
    if catalog:
        exact, dtype_hist, comp_dtypes = exact_components(catalog, cfg)
        wname = dtype_label(dtype_hist)

    comps = []
    for key in order:
        if exact is not None:
            if key not in exact:
                continue
            comps.append({"key": key, "name": names[key],
                          "params": exact[key]["params"], "bytes": exact[key]["bytes"]})
        else:
            params = p.get(key, 0)
            if key in ("indexer", "mtp") and not params:
                continue
            if key in ("moe_routed", "moe_shared", "moe_gate") and not p["moe_layers"]:
                continue
            comps.append({"key": key, "name": names[key],
                          "params": params, "bytes": params * wbytes})

    total_params = sum(c["params"] for c in comps)
    total_bytes = sum(c["bytes"] for c in comps)
    for c in comps:
        c["share"] = c["bytes"] / total_bytes

    # active params (MoE)
    active = None
    if p["moe_layers"]:
        topk = cfg.get("num_experts_per_tok", 0)
        H = cfg["hidden_size"]
        moe_inter = cfg.get("moe_intermediate_size")
        moe_routed_params = next((c["params"] for c in comps if c["key"] == "moe_routed"), 0)
        mtp_params = next((c["params"] for c in comps if c["key"] == "mtp"), 0)
        active = (total_params - moe_routed_params - mtp_params
                  + 3 * H * moe_inter * topk * p["moe_layers"])

    # ---- runtime: KV cache scales with context x running requests
    elems, kv_desc = kv_per_token_elems(cfg)
    # fp4 (mxfp4/e2m1): 0.5 B data + 1 uint8 scale per 16 elements (SGLang memory_pool)
    kvb = {"fp16": 2, "bf16": 2, "fp8": 1, "fp4": 0.5 + 1 / 16}[kv_dtype]
    kv_per_tok = elems * L * kvb
    kv_per_req = kv_per_tok * ctx
    kv_total = kv_per_req * requests
    mha_total = mha_ratio = None
    if p["is_mla"]:
        n_heads = cfg["num_attention_heads"]
        mha_elems = n_heads * (cfg["qk_nope_head_dim"] + cfg["qk_rope_head_dim"] + cfg["v_head_dim"])
        mha_total = mha_elems * L * kvb * ctx * requests
        mha_ratio = mha_elems / elems

    # ---- runtime: activation workspace scales with tokens in flight
    act_total, act_desc = activation_bytes(cfg, p, batch_tokens)

    runtime_total = kv_total + act_total
    grand = (total_bytes + runtime_total) * (1 + overhead)

    return {
        "model_id": model_id, "cfg": cfg, "arch": (cfg.get("architectures") or ["?"])[0],
        "wbytes": wbytes, "wname": wname, "p": p, "comps": comps,
        "total_params": total_params, "total_bytes": total_bytes, "active": active,
        "ctx": ctx, "requests": requests, "kv_dtype": kv_dtype, "kv_desc": kv_desc,
        "kv_elems_total": elems * L,  # dtype-independent: elements per token, all layers
        "kv_per_tok": kv_per_tok, "kv_per_req": kv_per_req, "kv_total": kv_total,
        "mha_total": mha_total, "mha_ratio": mha_ratio,
        "batch_tokens": batch_tokens, "act_total": act_total, "act_desc": act_desc,
        "runtime_total": runtime_total, "overhead": overhead, "grand": grand,
        "exact": exact is not None, "comp_dtypes": comp_dtypes,
    }


# ---------------------------------------------------------------- text report

def human(nbytes: float) -> str:
    return f"{nbytes / GIB:,.1f} GiB"


def report(a: dict):
    cfg, p = a["cfg"], a["p"]
    L = cfg["num_hidden_layers"]
    print(f"\n{'=' * 68}")
    print(f"Model     : {a['model_id']}  ({a['arch']})")
    print(f"Layers    : {L}  hidden={cfg['hidden_size']}  heads={cfg['num_attention_heads']}  vocab={cfg['vocab_size']}")
    if p["moe_layers"]:
        n_routed = cfg.get("n_routed_experts") or cfg.get("num_experts") or cfg.get("num_local_experts")
        print(f"MoE       : {n_routed} experts, top-{cfg.get('num_experts_per_tok', '?')}, "
              f"moe_inter={cfg.get('moe_intermediate_size')}, first {p['dense_layers']} layers dense")
    eff = a["total_bytes"] / a["total_params"]
    print(f"Weights   : {a['wname']} ({eff:.2f} byte/param effective"
          f"{', exact from safetensors' if a.get('exact') else ''})")
    print(f"{'=' * 68}")
    print(f"\n-- STATIC: weights {a['total_params'] / 1e9:,.1f} B params -> {human(a['total_bytes'])} --\n")
    print(f"  {'component':<38}{'params':>12}{'memory':>12}{'share':>7}")
    for c in sorted(a["comps"], key=lambda x: -x["params"]):
        if c["params"] == 0:
            continue
        print(f"  {c['name']:<38}{c['params'] / 1e9:>10.2f}B{c['bytes'] / GIB:>10.1f}G{c['share']:>6.1%}")
    if a["active"]:
        print(f"\n  active params per token ~ {a['active'] / 1e9:,.0f}B "
              f"(top-{cfg.get('num_experts_per_tok')} + {cfg.get('n_shared_experts', 0)} shared)")
    print(f"\n-- RUNTIME: context {a['ctx']:,} x {a['requests']} running requests --\n")
    print(f"  KV cache ({a['kv_dtype']}): {a['kv_desc']}")
    print(f"    per token (all {L} layers) {a['kv_per_tok'] / 1024:,.1f} KiB"
          f" -> per request {human(a['kv_per_req'])} -> x{a['requests']} = {human(a['kv_total'])}")
    if a["mha_total"]:
        print(f"    (uncompressed MHA equivalent {human(a['mha_total'])}, MLA saves {a['mha_ratio']:,.0f}x)")
    print(f"  Activation workspace ({a['batch_tokens']:,} tokens/forward): {human(a['act_total'])}")
    print(f"    {a['act_desc']}")
    print(f"  runtime total: {human(a['runtime_total'])}")
    print(f"\n-- TOTAL --\n")
    print(f"  weights {human(a['total_bytes'])} + runtime {human(a['runtime_total'])} "
          f"+ fragmentation ~{a['overhead']:.0%} = ~{human(a['grand'])}")
    print()


# ---------------------------------------------------------------- html diagram

def _gib(nbytes: float) -> str:
    v = nbytes / GIB
    return f"{v:,.1f}" if v >= 0.95 else f"{v:.2f}"


def _b(params: float) -> str:
    v = params / 1e9
    return f"{v:,.1f}B" if v >= 10 else f"{v:.2f}B"


def _var(i: int) -> str:
    return f"var(--s{i + 1})"


def _card(slot, title, value, share, lines, dtype=None):
    rows = "".join(f"<div class='cl'>{ln}</div>" for ln in lines)
    pct = f"<span class='pct'>{share:.1%}</span>" if share is not None else ""
    dt = f"<span class='dt'>{dtype}</span>" if dtype else ""
    return f"""<div class='card' style='border-left-color:{_var(slot)}'>
      <div class='ch'><i class='dot' style='background:{_var(slot)}'></i><span class='ct'>{title}</span>{dt}
      <span class='cv'>{value}</span>{pct}</div>{rows}</div>"""


def _stacked_bar(segs):
    """segs: list of {label, bytes, share, slot} -> (bar_html, legend_html)."""
    bar = ""
    for s in segs:
        pct = s["share"] * 100
        inner = ""
        if pct >= 30:  # label inside only when it comfortably fits
            inner = f"<span class='seg-label'>{s['label'].split('（')[0].split('(')[0].strip()} {_gib(s['bytes'])} GiB（{pct:.0f}%）</span>"
        bar += (f"<div class='seg' style='flex:{s['share']:.6f};"
                f"background:{_var(s['slot'])}' title='{s['label']}: {_gib(s['bytes'])} GiB'>{inner}</div>")
    legend = "".join(
        f"<span class='lg'><i style='background:{_var(s['slot'])}'></i>"
        f"{s['label']}&ensp;<b>{_gib(s['bytes'])}</b></span>"
        for s in segs)
    return bar, legend


def render_html(a: dict, out_path: str, ctx_options: list, req_options: list):
    cfg, p = a["cfg"], a["p"]
    L = cfg["num_hidden_layers"]
    is_moe = bool(p["moe_layers"])
    short = a["model_id"].split("/")[-1]
    n_routed = cfg.get("n_routed_experts") or cfg.get("num_experts") or cfg.get("num_local_experts")

    # ---- left structure column
    dense_n, moe_n = p["dense_layers"], p["moe_layers"]
    attn_label = "① Attention (MLA)" if p["is_mla"] else "① Attention (GQA)" if \
        cfg.get("num_key_value_heads", cfg["num_attention_heads"]) < cfg["num_attention_heads"] else "① Attention (MHA)"

    def layer_block(ffn_label, ffn_slot, tag):
        return f"""<div class='layer'><span class='ltag'>{tag}</span>
          <div class='sub' style='border-color:{_var(1)}'><i class='dot' style='background:{_var(1)}'></i>{attn_label}</div>
          <div class='sub' style='border-color:{_var(ffn_slot)}'><i class='dot' style='background:{_var(ffn_slot)}'></i>② {ffn_label}</div>
        </div>"""

    struct = f"<div class='io' style='border-color:{_var(0)}'><i class='dot' style='background:{_var(0)}'></i>embed（入口）</div>"
    if is_moe:
        if dense_n:
            struct += layer_block("Dense FFN", 2, "L0")
            if dense_n > 1:
                struct += f"<div class='ell'>⋮ 前 {dense_n} 层：FFN 是 Dense（L0–L{dense_n - 1}）</div>"
        struct += layer_block("MoE FFN", 3, f"L{dense_n}")
        struct += (f"<div class='ell'>⋮ {'后' if dense_n else '全部'} {moe_n} 层：FFN 是 MoE，"
                   f"{n_routed} 专家（L{dense_n}–L{L - 1}）</div>")
        struct += layer_block("MoE FFN", 3, f"L{L - 1}")
    else:
        struct += layer_block("FFN", 2, "L0")
        struct += f"<div class='ell'>⋮ 共 {L} 层（每层结构相同）</div>"
        struct += layer_block("FFN", 2, f"L{L - 1}")
    if p["mtp"]:
        struct += f"<div class='io' style='border-color:{_var(4)}'><i class='dot' style='background:{_var(4)}'></i>MTP 预测层 ×{cfg.get('num_nextn_predict_layers')}</div>"
    head_note = "lm_head（出口）" if p["lm_head"] else "lm_head（与 embed 共享）"
    struct += f"<div class='io' style='border-color:{_var(0)}'><i class='dot' style='background:{_var(0)}'></i>{head_note}</div>"

    # ---- static cards (weights); bytes come from comps (exact when available)
    cb = {c["key"]: c for c in a["comps"]}

    def cbytes(*keys):
        return sum(cb[k]["bytes"] for k in keys if k in cb)

    def cshare(*keys):
        return cbytes(*keys) / a["total_bytes"]

    def cdtype(*keys):
        """dominant storage dtype label for one or more components, e.g. 'fp4'
        or 'fp8 + bf16'; None when exact dtypes are unavailable."""
        cd = a.get("comp_dtypes") or {}
        merged = {}
        for k in keys:
            for dt, b in (cd.get(k) or {}).items():
                if dt in ("QSCALE", "F8_E8M0"):   # scales are overhead, not identity
                    continue
                merged[dt] = merged.get(dt, 0) + b
        if not merged:
            return None if a.get("exact") else a["wname"]
        label = dtype_label(merged)
        return label.replace("混合精度: ", "")

    def cdt(key):
        """inline note like '（fp4 存储）' for card body lines."""
        label = cdtype(key)
        return f"（{label} 存储）" if label and "+" not in label and "%" not in label else ""

    cards = ""
    cards += _card(0, "embed + lm_head", f"{_gib(cbytes('embed', 'lm_head'))} GiB", cshare("embed", "lm_head"),
                   [f"{'2 ×' if p['lm_head'] else '1 ×（共享）'} {cfg['vocab_size']:,}（词表）× {cfg['hidden_size']}"],
                   dtype=cdtype("embed", "lm_head"))

    attn_lines = []
    if "attention" in cb:
        attn_lines.append(f"共 {_b(cb['attention']['params'])} 参数 × {L} 层{cdt('attention')}")
    if p["is_mla"]:
        attn_lines.append(
            f"MLA 低秩：q_lora={cfg.get('q_lora_rank')}, kv_lora={cfg['kv_lora_rank']}, "
            f"{cfg['num_attention_heads']} head（qk {cfg['qk_nope_head_dim']}+{cfg['qk_rope_head_dim']} / v {cfg['v_head_dim']}）")
    else:
        n_kv = cfg.get("num_key_value_heads", cfg["num_attention_heads"])
        hd = cfg.get("head_dim") or cfg["hidden_size"] // cfg["num_attention_heads"]
        extra = "，q/o 低秩分解" if cfg.get("q_lora_rank") or cfg.get("o_lora_rank") else ""
        attn_lines.append(f"{cfg['num_attention_heads']} q head / {n_kv} kv head，head_dim {hd}{extra}")
    cards += _card(1, f"① Attention 子层 — {L} 层每层都有",
                   f"{_gib(cbytes('attention'))} GiB", cshare("attention"), attn_lines,
                   dtype=cdtype("attention"))

    if "indexer" in cb:
        cards += _card(7, "attn indexer（DSA 稀疏注意力索引）",
                       f"{_gib(cbytes('indexer'))} GiB", cshare("indexer"),
                       [f"index_n_heads={cfg['index_n_heads']}, index_head_dim={cfg.get('index_head_dim')}，省的是计算，非存储"],
                       dtype=cdtype("indexer"))

    inter = cfg.get("intermediate_size")
    if is_moe:
        if dense_n and "dense_ffn" in cb:
            cards += _card(2, f"② Dense FFN（前 {dense_n} 层）",
                           f"{_gib(cbytes('dense_ffn'))} GiB", cshare("dense_ffn"),
                           [f"3 矩阵 × {cfg['hidden_size']} × {inter}（胖）× {dense_n} 层"],
                           dtype=cdtype("dense_ffn"))
        moe_lines = [
            f"routed experts：{n_routed} × 3 矩阵 × {cfg['hidden_size']} × "
            f"{cfg.get('moe_intermediate_size')}（瘦）× {moe_n} 层 = <b>{_gib(cbytes('moe_routed'))} GiB</b>{cdt('moe_routed')}",
        ]
        if cbytes("moe_shared"):
            moe_lines.append(f"shared expert（每层 {cfg.get('n_shared_experts')} 个 × {moe_n}）"
                             f"= {_gib(cbytes('moe_shared'))} GiB{cdt('moe_shared')}")
        if a["active"]:
            moe_lines.append(f"每 token 只激活 top-{cfg.get('num_experts_per_tok')}（~{a['active'] / 1e9:,.0f}B 计算）"
                             f"—— 显存按 {n_routed} 存（大），计算按 {cfg.get('num_experts_per_tok')} 跑（省）")
        cards += _card(3, f"② MoE FFN（{'后 ' + str(moe_n) + ' 层' if dense_n else '全部 ' + str(moe_n) + ' 层'}）★ 绝对大头",
                       f"{_gib(cbytes('moe_routed', 'moe_shared', 'moe_gate'))} GiB",
                       cshare("moe_routed", "moe_shared", "moe_gate"), moe_lines,
                       dtype=cdtype("moe_routed"))
    else:
        cards += _card(2, f"② FFN（{L} 层）★ 大头",
                       f"{_gib(cbytes('dense_ffn'))} GiB", cshare("dense_ffn"),
                       [f"3 矩阵 × {cfg['hidden_size']} × {inter} × {L} 层"],
                       dtype=cdtype("dense_ffn"))

    if "mtp" in cb and cbytes("mtp"):
        cards += _card(4, f"MTP（multi-token prediction）×{cfg.get('num_nextn_predict_layers')}",
                       f"{_gib(cbytes('mtp'))} GiB", cshare("mtp"),
                       ["一整套额外的 Attention + FFN，投机解码用；不需要可不加载"],
                       dtype=cdtype("mtp"))

    if a.get("exact") and cbytes("norms") / a["total_bytes"] >= 0.005:
        cards += _card(7, "norms & 其他（layernorm、hyper-connection、量化 scale 等）",
                       f"{_gib(cbytes('norms'))} GiB", cshare("norms"), [],
                       dtype=cdtype("norms"))

    # ---- runtime cards (dynamic values wrapped in id'd spans; JS rewrites them)
    kv_lines = [a["kv_desc"],
                f"每 token（全 {L} 层）= <span id='d-kv-per-tok'>…</span> KiB → "
                f"单请求（context <span id='d-ctx2'>…</span>）"
                f"= <b><span id='d-kv-per-req'>…</span> GiB</b> → "
                f"× <span id='d-req2'>…</span> 并发 "
                f"= <b><span id='d-kv-total2'>…</span> GiB</b>"]
    if a["mha_total"]:
        kv_lines.append(f"假如用 MHA 全存：<b><span id='d-mha'>…</span> GiB</b> —— "
                        f"MLA 压成 {cfg['kv_lora_rank']} 维共享 latent，省 <b>{a['mha_ratio']:.0f}×</b>")
    runtime_cards = _card(5, "KV Cache — context <span id='d-ctx'>…</span> × <span id='d-req'>…</span> 并发请求",
                          "<span id='d-kv-total'>…</span> GiB", None, kv_lines,
                          dtype="<span id='d-kv-dtype'>…</span>")

    act_lines = [a["act_desc"],
                 f"一次 forward 最多 {a['batch_tokens']:,} tokens（chunked prefill 上限），逐层执行，只有当前层的中间结果存活",
                 "工作区估算（vLLM profile 的量级），与请求数无关、与单次批处理 token 数有关"]
    runtime_cards += _card(6, f"Activation 工作区 — {a['batch_tokens']:,} tokens/forward",
                           f"{_gib(a['act_total'])} GiB", None, act_lines, dtype="bf16")

    # ---- stacked bars
    ranked = sorted((c for c in a["comps"] if c["bytes"] > 0), key=lambda c: -c["bytes"])
    big = [c for c in ranked if c["share"] >= 0.015][:5]
    tail = [c for c in ranked if c not in big]
    wsegs = [{"label": c["name"], "bytes": c["bytes"], "share": c["share"],
              "slot": COMP_SLOT.get(c["key"], 7)} for c in big]
    if tail:
        tb = sum(c["bytes"] for c in tail)
        wsegs.append({"label": "other", "bytes": tb, "share": tb / a["total_bytes"], "slot": 7})
    weights_segs, weights_legend = _stacked_bar(wsegs)

    tot = a["total_bytes"] + a["runtime_total"]
    tsegs = [{"label": "权重（静态）", "bytes": a["total_bytes"], "share": a["total_bytes"] / tot, "slot": 3 if is_moe else 2},
             {"label": "KV Cache", "bytes": a["kv_total"], "share": a["kv_total"] / tot, "slot": 5},
             {"label": "Activation", "bytes": a["act_total"], "share": a["act_total"] / tot, "slot": 6}]
    total_segs, total_legend = _stacked_bar(tsegs)

    total_line = (f"权重 {_gib(a['total_bytes'])}（静态） + KV {_gib(a['kv_total'])} + "
                  f"Activation {_gib(a['act_total'])}（动态） + 碎片 ~{a['overhead']:.0%} "
                  f"≈ <b>{_gib(a['grand'])} GiB</b>"
                  f"<span class='pct'>　·　KV 随 context × 并发线性增长：每并发 +{_gib(a['kv_per_req'])} GiB</span>")

    # ---- table view
    trows = "".join(
        f"<tr><td><i class='dot' style='background:{_var(COMP_SLOT.get(c['key'], 7))}'></i>{c['name']}</td>"
        f"<td>{cdtype(c['key']) or '—'}</td>"
        f"<td class='num'>{_b(c['params'])}</td><td class='num'>{_gib(c['bytes'])}</td>"
        f"<td class='num'>{c['share']:.1%}</td></tr>"
        for c in sorted(a["comps"], key=lambda x: -x["params"]) if c["params"] > 0)
    trows += (f"<tr class='sep'><td><i class='dot' style='background:{_var(5)}'></i>"
              f"<span id='d-tbl-kv-label'>KV cache</span></td>"
              f"<td><span id='d-tbl-kv-dtype'>—</span></td>"
              f"<td class='num'>—</td><td class='num'><span id='d-tbl-kv-val'>—</span></td><td class='num'>—</td></tr>"
              f"<tr><td><i class='dot' style='background:{_var(6)}'></i>"
              f"activation（{a['batch_tokens']:,} tokens/forward）</td><td>bf16</td>"
              f"<td class='num'>—</td><td class='num'>{_gib(a['act_total'])}</td><td class='num'>—</td></tr>")

    if is_moe:
        subtitle = (f"每层 = ① Attention + ② FFN；前 {dense_n} 层 Dense、后 {moe_n} 层 MoE —— "
                    f"{(p['moe_routed'] / a['total_params']):.0%} 的权重压在 MoE 专家上")
    else:
        subtitle = f"每层 = ① Attention + ② FFN，共 {L} 层"

    # ---- filter options; ensure current CLI values are selectable
    ctx_opts = sorted(set(ctx_options) | {a["ctx"]})
    req_opts = sorted(set(req_options) | {a["requests"]})

    def _ctx_label(v):
        return f"{v // 1024}K" if v % 1024 == 0 else f"{v:,}"

    ctx_options_html = "".join(
        f"<option value='{v}'{' selected' if v == a['ctx'] else ''}>{_ctx_label(v)}</option>"
        for v in ctx_opts)
    req_options_html = "".join(
        f"<option value='{v}'{' selected' if v == a['requests'] else ''}>{v}</option>"
        for v in req_opts)
    kv_auto = a.get("kv_auto", a["kv_dtype"])
    kv_choice = a.get("kv_choice", a["kv_dtype"])
    kv_options_html = "".join(
        f"<option value='{v}'{' selected' if v == kv_choice else ''}>{lbl}</option>"
        for v, lbl in [("auto", f"auto（{kv_auto}）"), ("bf16", "bf16"), ("fp8", "fp8"),
                       ("fp4", "fp4 (mxfp4)")])

    # data the in-page JS needs to recompute the runtime side
    viz_json = json.dumps({
        "weightsBytes": a["total_bytes"],
        "weightsSlot": 3 if is_moe else 2,
        "kvElems": a["kv_elems_total"],   # elements per token across all layers
        "kvAuto": kv_auto,                # what "auto" resolves to for this model
        "actBytes": a["act_total"],
        "mhaRatio": a["mha_ratio"],
        "overhead": a["overhead"],
    })

    fields = {
        "page_title": f"{short} 显存拆解",
        "title": (f"{short}（{a['total_params'] / 1e9:,.0f}B{' MoE' if is_moe else ''}）：显存拆解 —— "
                  f"权重 {_gib(a['total_bytes'])} GiB + 运行时 <span id='d-runtime'>…</span> GiB"),
        "subtitle": subtitle,
        "meta": (f"{a['model_id']} · {a['arch']} · hidden {cfg['hidden_size']} · "
                 f"{cfg['num_attention_heads']} heads · vocab {cfg['vocab_size']:,} · "
                 f"activation 按 {a['batch_tokens']:,} tokens/forward · "
                 + ("权重为 safetensors 精确值" if a.get("exact") else "由 config.json 解析式估算")),
        "ctx_options": ctx_options_html,
        "req_options": req_options_html,
        "kv_options": kv_options_html,
        "struct_title": f"{L} 层 Transformer（每层：上 Attention + 下 FFN）",
        "struct": struct,
        "static_cards": cards,
        "runtime_cards": runtime_cards,
        "weights_bar_head": (f"静态 · 权重合计 ≈ {_gib(a['total_bytes'])} GiB"
                             f"（{a['wname']}，{a['total_bytes'] / a['total_params']:.2f} 字节/参数"
                             f"{'，safetensors 精确值' if a.get('exact') else ''}）"),
        "weights_segs": weights_segs,
        "weights_legend": weights_legend,
        "total_bar_head": (f"静态 + 动态 · 部署总占用 ≈ {_gib(tot)} GiB"
                           f"（context {a['ctx']:,} × {a['requests']} 并发）"),
        "total_segs": total_segs,
        "total_legend": total_legend,
        "total_line": total_line,
        "table_rows": trows,
        "viz_json": viz_json,
    }

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        tpl = string.Template(f.read())
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(tpl.substitute(fields))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Estimate LLM VRAM from HF config.json")
    ap.add_argument("model_id", help="HuggingFace model ID, e.g. zai-org/GLM-5.2-FP8")
    ap.add_argument("--context", type=int, default=131_072,
                    help="context length per request (default 128K)")
    ap.add_argument("--requests", "--batch", type=int, default=16, dest="requests",
                    help="concurrent running requests (default 16)")
    ap.add_argument("--ctx-options", default="65536,131072,204800",
                    help="comma-separated context choices for the HTML dropdown (default 64K,128K,200K)")
    ap.add_argument("--req-options", default="8,16,32,64",
                    help="comma-separated concurrency choices for the HTML dropdown (default 8,16,32,64)")
    ap.add_argument("--kv-dtype", choices=["auto", "bf16", "fp16", "fp8", "fp4"], default="auto",
                    help="KV cache dtype; auto mirrors SGLang: fp8 for DSA/V4-style "
                         "sparse-attention models on new GPUs, else bf16. fp4 = mxfp4 "
                         "(SGLang --kv-cache-dtype fp4_e2m1, CUDA 12.8+, incl. block-16 scale overhead)")
    ap.add_argument("--batch-tokens", type=int, default=8192,
                    help="max tokens per forward pass, for activation estimate (default 8192, ~vLLM chunked prefill)")
    ap.add_argument("--overhead", type=float, default=0.05,
                    help="extra fraction for fragmentation/CUDA context (default 5%%)")
    ap.add_argument("--html", metavar="FILE", help="also write a breakdown diagram to this HTML file")
    ap.add_argument("--no-exact", action="store_true",
                    help="skip reading safetensors headers; use formula estimate only")
    args = ap.parse_args()

    try:
        cfg = fetch_config(args.model_id)
    except Exception as e:
        sys.exit(f"failed to fetch config for {args.model_id}: {e}")

    # multimodal configs nest the LLM under text_config
    if "num_hidden_layers" not in cfg and "text_config" in cfg:
        qc = cfg.get("quantization_config")
        cfg = cfg["text_config"]
        if qc and "quantization_config" not in cfg:
            cfg["quantization_config"] = qc

    # resolve kv-dtype "auto" the way SGLang does (server_args + deepseek_v4_hook):
    # DSA/V4 sparse-attention models default to fp8_e4m3 KV, everything else
    # keeps KV in the activation dtype (bf16)
    arch = (cfg.get("architectures") or [""])[0]
    is_dsa = cfg.get("index_topk") is not None or arch in (
        "DeepseekV4ForCausalLM", "DeepseekV32ForCausalLM")
    kv_auto = "fp8" if is_dsa else "bf16"
    kv_choice = args.kv_dtype                    # what the user picked (may be "auto")
    if args.kv_dtype == "auto":
        args.kv_dtype = kv_auto
        print(f"kv-dtype auto -> {args.kv_dtype}"
              f"{'（DSA/稀疏注意力模型，对齐 SGLang 默认 fp8_e4m3）' if is_dsa else ''}",
              file=sys.stderr)

    catalog = None
    if not args.no_exact:
        try:
            catalog, declared = fetch_safetensors_catalog(args.model_id)
            got = sum(t["bytes"] for t in catalog.values())
            if declared and abs(got - declared) / declared > 0.01:
                print(f"warning: safetensors headers sum to {got / GIB:,.1f} GiB "
                      f"but index declares {declared / GIB:,.1f} GiB", file=sys.stderr)
        except Exception as e:
            print(f"note: could not read safetensors headers ({e}); "
                  f"falling back to formula estimate", file=sys.stderr)

    a = analyze(args.model_id, cfg, args.context, args.requests, args.kv_dtype,
                args.batch_tokens, args.overhead, catalog=catalog)
    a["kv_auto"] = kv_auto
    a["kv_choice"] = kv_choice
    report(a)
    if args.html:
        ctx_options = [int(v) for v in args.ctx_options.split(",")]
        req_options = [int(v) for v in args.req_options.split(",")]
        render_html(a, args.html, ctx_options, req_options)
        print(f"diagram written to {args.html}")


if __name__ == "__main__":
    main()
