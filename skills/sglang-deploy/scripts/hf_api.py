#!/usr/bin/env python3
"""
Hugging Face API Client for fetching SGLang-compatible models
"""

import re
import time
from typing import Optional, List, Dict, Any

import requests

# Cache configuration
_cache: Dict[str, Any] = {}
_cache_ttl: int = 300  # 5 minutes

HF_API_BASE = "https://huggingface.co/api"


def _get_cached(key: str) -> Optional[Any]:
    """Get value from cache if not expired"""
    if key in _cache:
        entry = _cache[key]
        if time.time() - entry["timestamp"] < _cache_ttl:
            return entry["data"]
    return None


def _set_cache(key: str, data: Any) -> None:
    """Set value in cache with timestamp"""
    _cache[key] = {"data": data, "timestamp": time.time()}


def clear_cache():
    """Clear all cached data"""
    global _cache
    _cache = {}


def fetch_model_config(model_id: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """
    Fetch config.json from a HuggingFace model repo.

    This is useful when the HF API doesn't return parameter counts (e.g. for
    newer or community models). The config.json contains architecture details
    that can be used to estimate parameter counts.

    Args:
        model_id: HuggingFace model ID (e.g., "zai-org/GLM-4.7-Flash")
        timeout: Request timeout in seconds

    Returns:
        Parsed config.json dict or None if unavailable
    """
    cache_key = f"model_config:{model_id}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        url = f"https://huggingface.co/{model_id}/raw/main/config.json"
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        _set_cache(cache_key, data)
        return data
    except Exception:
        return None


def estimate_params_from_config(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Estimate parameter count from model config.json.

    Supports:
    - Standard dense transformers (Llama, Qwen, Mistral, etc.)
    - MoE models (Mixtral, DeepSeek-MoE, GLM-4-MoE, Qwen-MoE, etc.)
    - MLA attention (DeepSeek-V2/V3, GLM-4.7-Flash)

    Returns:
        {
            "total_params_billions": float,
            "active_params_billions": float or None (for MoE),
            "model_weight_size_gb": float (BF16),
            "is_moe": bool,
            "architecture": str,
            "details": dict  (breakdown)
        }
        or None if config is insufficient
    """
    hidden_size = config.get("hidden_size")
    num_layers = config.get("num_hidden_layers")
    vocab_size = config.get("vocab_size")

    if not all([hidden_size, num_layers, vocab_size]):
        return None

    num_attention_heads = config.get("num_attention_heads", 32)
    num_kv_heads = config.get("num_key_value_heads", num_attention_heads)
    intermediate_size = config.get("intermediate_size", hidden_size * 4)
    architecture = config.get("architectures", ["unknown"])[0] if config.get("architectures") else "unknown"

    # Detect MLA (Multi-head Latent Attention)
    q_lora_rank = config.get("q_lora_rank")
    kv_lora_rank = config.get("kv_lora_rank")
    qk_nope_head_dim = config.get("qk_nope_head_dim")
    qk_rope_head_dim = config.get("qk_rope_head_dim")
    v_head_dim = config.get("v_head_dim")
    use_mla = all([kv_lora_rank, qk_nope_head_dim, qk_rope_head_dim, v_head_dim])

    # Detect MoE
    n_routed_experts = config.get("n_routed_experts") or config.get("num_local_experts", 0)
    num_experts_per_tok = config.get("num_experts_per_tok") or config.get("num_experts_per_token", 0)
    moe_intermediate_size = config.get("moe_intermediate_size", 0)
    n_shared_experts = config.get("n_shared_experts", 0)
    is_moe = n_routed_experts > 0

    # --- Embedding ---
    embed_params = vocab_size * hidden_size

    # --- Attention per layer ---
    if use_mla:
        # MLA-style attention
        attn_params = (
            hidden_size * (q_lora_rank or 0) +  # q_down
            (q_lora_rank or 0) * num_attention_heads * (qk_nope_head_dim + qk_rope_head_dim) +  # q_up
            hidden_size * (kv_lora_rank + qk_rope_head_dim) +  # kv_down
            kv_lora_rank * num_attention_heads * (qk_nope_head_dim + v_head_dim) +  # kv_up
            num_attention_heads * v_head_dim * hidden_size  # output
        )
    else:
        # Standard GQA/MHA attention
        head_dim = hidden_size // num_attention_heads
        attn_params = (
            hidden_size * num_attention_heads * head_dim +  # Q
            hidden_size * num_kv_heads * head_dim +  # K
            hidden_size * num_kv_heads * head_dim +  # V
            num_attention_heads * head_dim * hidden_size  # O
        )

    # --- FFN per layer ---
    if is_moe:
        # Shared experts
        shared_ffn = n_shared_experts * (3 * hidden_size * intermediate_size) if n_shared_experts else 0
        # Routed experts
        routed_ffn = n_routed_experts * (3 * hidden_size * moe_intermediate_size) if moe_intermediate_size else 0
        # Router gate
        router_params = hidden_size * n_routed_experts
        total_ffn = shared_ffn + routed_ffn + router_params
        # Active FFN (only topk experts active)
        active_ffn = (
            (n_shared_experts * (3 * hidden_size * intermediate_size) if n_shared_experts else 0) +
            num_experts_per_tok * (3 * hidden_size * moe_intermediate_size) if moe_intermediate_size else 0
        ) + router_params
    else:
        # Dense FFN (gate_proj + up_proj + down_proj for SwiGLU, or 2 projections)
        # Detect SwiGLU/GeGLU (3 projections) vs standard (2 projections)
        hidden_act = config.get("hidden_act", "")
        if hidden_act in ("silu", "swiglu", "gelu_new", "gelu"):
            total_ffn = 3 * hidden_size * intermediate_size
        else:
            total_ffn = 2 * hidden_size * intermediate_size
        active_ffn = total_ffn
        router_params = 0

    # --- Layer norm (2 per layer: pre-attn + pre-ffn) ---
    norm_params = 2 * hidden_size

    # --- Per layer total ---
    per_layer_total = attn_params + total_ffn + norm_params
    per_layer_active = attn_params + active_ffn + norm_params

    # --- Total model ---
    # embedding + layers + final norm + lm_head
    tie_word_embeddings = config.get("tie_word_embeddings", False)
    lm_head_params = 0 if tie_word_embeddings else vocab_size * hidden_size
    final_norm = hidden_size

    total_params = embed_params + per_layer_total * num_layers + final_norm + lm_head_params
    active_params = embed_params + per_layer_active * num_layers + final_norm + lm_head_params

    total_b = total_params / 1e9
    active_b = active_params / 1e9
    weight_size_gb = total_params * 2 / 1e9  # BF16

    result = {
        "total_params_billions": round(total_b, 1),
        "active_params_billions": round(active_b, 1) if is_moe else None,
        "model_weight_size_gb": round(weight_size_gb, 1),
        "is_moe": is_moe,
        "architecture": architecture,
        "details": {
            "hidden_size": hidden_size,
            "num_hidden_layers": num_layers,
            "vocab_size": vocab_size,
            "num_attention_heads": num_attention_heads,
            "num_key_value_heads": num_kv_heads,
            "use_mla": use_mla,
        }
    }

    if is_moe:
        result["details"].update({
            "n_routed_experts": n_routed_experts,
            "num_experts_per_tok": num_experts_per_tok,
            "n_shared_experts": n_shared_experts,
            "moe_intermediate_size": moe_intermediate_size,
        })

    return result


def fetch_model_info(model_id: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """
    Fetch comprehensive model information including parameter estimation.

    Combines HF API metadata with config.json-based parameter estimation.

    Args:
        model_id: HuggingFace model ID
        timeout: Request timeout in seconds

    Returns:
        {
            "model_id": str,
            "params_billions": float,
            "active_params_billions": float or None,
            "model_weight_size_gb": float,
            "is_moe": bool,
            "architecture": str,
            "param_source": "safetensors" | "config_estimate" | "name_parse",
            "requirements": dict,
            "details": dict,
        }
        or None if model info cannot be determined
    """
    info: Dict[str, Any] = {"model_id": model_id}

    # 1. Try safetensors.total from HF API
    params_total = fetch_model_params(model_id, timeout=timeout)
    if params_total:
        params_b = params_total / 1e9
        info["params_billions"] = round(params_b, 1)
        info["param_source"] = "safetensors"
    else:
        params_b = None

    # 2. Fetch config.json for architecture details and param estimation
    config = fetch_model_config(model_id, timeout=timeout)
    config_estimate = None
    if config:
        config_estimate = estimate_params_from_config(config)

    if config_estimate:
        info["architecture"] = config_estimate["architecture"]
        info["is_moe"] = config_estimate["is_moe"]
        info["active_params_billions"] = config_estimate["active_params_billions"]
        info["model_weight_size_gb"] = config_estimate["model_weight_size_gb"]
        info["details"] = config_estimate["details"]

        if params_b is None:
            # Use config-based estimate
            params_b = config_estimate["total_params_billions"]
            info["params_billions"] = params_b
            info["param_source"] = "config_estimate"
    else:
        info["is_moe"] = False
        info["active_params_billions"] = None

    # 3. Fallback: parse from model name
    if params_b is None:
        params_b = parse_params_from_name(model_id)
        if params_b:
            info["params_billions"] = params_b
            info["param_source"] = "name_parse"
            info["model_weight_size_gb"] = round(params_b * 2, 1)

    if params_b is None:
        return None

    # 4. Estimate GPU requirements
    info["requirements"] = estimate_model_requirements(params_b, model_id)

    return info


def estimate_model_requirements(params_billions: float, model_id: str = "") -> dict:
    """
    Estimate GPU requirements based on parameter count

    Args:
        params_billions: Number of parameters in billions
        model_id: Model ID (used for MoE detection)

    Returns:
        {
            "min_gpu_memory_gb": int,
            "recommended_tp": int,
            "recommended_instance": str
        }
    """
    # Check if MoE model (needs more memory due to sparse architecture)
    is_moe = any(x in model_id.lower() for x in ["moe", "mixture", "a17b", "a22b"])

    # Base memory estimate: params * 2 bytes (FP16) + 20% overhead
    base_memory_gb = params_billions * 2 * 1.2

    # MoE models need additional memory for expert routing
    if is_moe:
        base_memory_gb *= 1.5

    if base_memory_gb <= 24:
        return {"min_gpu_memory_gb": 24, "recommended_tp": 1, "recommended_instance": "g5.xlarge"}
    elif base_memory_gb <= 48:
        return {"min_gpu_memory_gb": 48, "recommended_tp": 1, "recommended_instance": "g5.2xlarge"}
    elif base_memory_gb <= 96:
        return {"min_gpu_memory_gb": 96, "recommended_tp": 4, "recommended_instance": "g5.12xlarge"}
    elif base_memory_gb <= 192:
        return {"min_gpu_memory_gb": 192, "recommended_tp": 8, "recommended_instance": "g5.48xlarge"}
    elif base_memory_gb <= 320:
        return {"min_gpu_memory_gb": 320, "recommended_tp": 8, "recommended_instance": "p4d.24xlarge"}
    else:
        return {"min_gpu_memory_gb": 640, "recommended_tp": 8, "recommended_instance": "p5.48xlarge"}


def parse_params_from_name(model_id: str) -> Optional[float]:
    """
    Try to parse parameter count from model name

    Examples:
        "Qwen/Qwen2.5-7B-Instruct" -> 7.0
        "meta-llama/Llama-3.1-70B-Instruct" -> 70.0
        "Qwen/Qwen3.5-397B-A17B" -> 397.0 (total params, A17B is active)
    """
    # Match patterns like "7B", "70B", "397B", "1.5B", "0.5B"
    match = re.search(r'(\d+\.?\d*)[Bb](?:-|$|[^a-zA-Z])', model_id)
    if match:
        return float(match.group(1))
    return None


def fetch_model_params(model_id: str, timeout: int = 10) -> Optional[int]:
    """
    Fetch parameter count from individual model API

    Args:
        model_id: HuggingFace model ID (e.g., "Qwen/Qwen2.5-7B-Instruct")
        timeout: Request timeout in seconds

    Returns:
        Total parameter count or None if unavailable
    """
    cache_key = f"model_params:{model_id}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        url = f"{HF_API_BASE}/models/{model_id}"
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        # Try to get from safetensors.total
        safetensors = data.get("safetensors", {})
        if safetensors:
            total = safetensors.get("total")
            if total:
                _set_cache(cache_key, total)
                return total

        return None
    except Exception:
        return None


def fetch_trending_models(
    limit: int = 15,
    min_params_billions: float = 32,
    timeout: int = 15
) -> List[dict]:
    """
    Fetch trending SGLang-compatible models from Hugging Face (32B+ by default)

    Args:
        limit: Maximum number of models to fetch
        min_params_billions: Minimum parameter count filter (default: 32 for 32B+)
        timeout: Request timeout in seconds

    Returns:
        List of model configs:
        [
            {
                "id": "qwen2.5-72b-instruct",
                "name": "Qwen2.5-72B-Instruct",
                "hf_model_id": "Qwen/Qwen2.5-72B-Instruct",
                "min_gpu_memory_gb": 160,
                "recommended_instance": "p4d.24xlarge",
                "recommended_tp": 8,
                "params_billions": 72.0,
                "likes": 1234,
                "downloads": 567890,
                "trending_score": 45.6,
                "source": "huggingface"
            }
        ]
    """
    cache_key = f"trending:{limit}:{min_params_billions}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        params = {
            "apps": "sglang",
            "sort": "trendingScore",
            "limit": limit * 2,  # Fetch extra in case some fail enrichment
            "full": "true"
        }

        if min_params_billions:
            # API uses raw parameter count
            params["num_parameters"] = f"min:{int(min_params_billions * 1e9)}"

        url = f"{HF_API_BASE}/models"
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        models = response.json()

        result = []
        for model in models:
            model_id = model.get("id", "")
            if not model_id:
                continue

            # Skip GGUF quantized models (they're not directly usable with SGLang)
            if "GGUF" in model_id.upper():
                continue

            # Try to get parameter count
            params_total = fetch_model_params(model_id, timeout=5)
            params_billions = None

            if params_total:
                params_billions = params_total / 1e9
            else:
                # Fallback: parse from name
                params_billions = parse_params_from_name(model_id)

            # If we still don't have params, use model name hint or skip
            if params_billions is None:
                params_billions = 32.0  # Default to minimum threshold

            # Estimate requirements
            requirements = estimate_model_requirements(params_billions, model_id)

            # Generate short ID from model_id
            short_id = model_id.split("/")[-1].lower()
            short_id = re.sub(r'[^a-z0-9]', '-', short_id)
            short_id = re.sub(r'-+', '-', short_id).strip('-')

            # Get display name
            name = model_id.split("/")[-1]

            config = {
                "id": short_id,
                "name": name,
                "hf_model_id": model_id,
                "min_gpu_memory_gb": requirements["min_gpu_memory_gb"],
                "recommended_instance": requirements["recommended_instance"],
                "recommended_tp": requirements["recommended_tp"],
                "params_billions": round(params_billions, 1),
                "likes": model.get("likes", 0),
                "downloads": model.get("downloads", 0),
                "trending_score": model.get("trendingScore", 0),
                "source": "huggingface"
            }

            # Check for gated models
            if model.get("gated"):
                config["gated"] = True
                config["note"] = "Requires HF token with access"

            result.append(config)

            if len(result) >= limit:
                break

        _set_cache(cache_key, result)
        return result

    except requests.exceptions.RequestException as e:
        print(f"Warning: Failed to fetch models from HuggingFace: {e}")
        return []
    except Exception as e:
        print(f"Warning: Error processing HuggingFace response: {e}")
        return []


if __name__ == "__main__":
    import argparse
    import json as json_mod

    parser = argparse.ArgumentParser(description="HuggingFace model info & trending models")
    parser.add_argument("--model_id", type=str, help="Fetch detailed info for a specific model")
    parser.add_argument("--trending", action="store_true", help="Fetch trending 32B+ SGLang models")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--limit", type=int, default=10, help="Limit for trending models")
    args = parser.parse_args()

    if args.model_id:
        info = fetch_model_info(args.model_id)
        if info is None:
            print(f"Error: Could not fetch info for model '{args.model_id}'")
            exit(1)
        if args.json:
            print(json_mod.dumps(info, indent=2))
        else:
            print(f"Model: {info['model_id']}")
            print(f"Architecture: {info.get('architecture', 'unknown')}")
            print(f"Total Parameters: {info['params_billions']}B")
            if info.get('active_params_billions'):
                print(f"Active Parameters: {info['active_params_billions']}B (MoE)")
            print(f"Model Weight Size (BF16): {info.get('model_weight_size_gb', 'N/A')} GB")
            print(f"MoE: {'Yes' if info.get('is_moe') else 'No'}")
            print(f"Param Source: {info.get('param_source', 'unknown')}")
            req = info.get("requirements", {})
            if req:
                print(f"Recommended Instance: {req.get('recommended_instance')}")
                print(f"Recommended TP: {req.get('recommended_tp')}")
                print(f"Min GPU Memory: {req.get('min_gpu_memory_gb')} GB")
            details = info.get("details", {})
            if details:
                print(f"--- Architecture Details ---")
                for k, v in details.items():
                    print(f"  {k}: {v}")
    elif args.trending:
        models = fetch_trending_models(limit=args.limit)
        if args.json:
            print(json_mod.dumps(models, indent=2))
        else:
            print(f"Trending 32B+ SGLang models:")
            for i, m in enumerate(models, 1):
                print(f"{i}. {m['name']} ({m['params_billions']}B) - {m['hf_model_id']}")
                print(f"   GPU: {m['min_gpu_memory_gb']}GB, TP={m['recommended_tp']}, likes={m['likes']}")
    else:
        parser.print_help()
