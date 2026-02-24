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
    # Test the API
    print("Fetching trending 32B+ SGLang models...")
    models = fetch_trending_models(limit=10)
    for i, m in enumerate(models, 1):
        print(f"{i}. {m['name']} ({m['params_billions']}B) - {m['hf_model_id']}")
        print(f"   GPU: {m['min_gpu_memory_gb']}GB, TP={m['recommended_tp']}, likes={m['likes']}")
