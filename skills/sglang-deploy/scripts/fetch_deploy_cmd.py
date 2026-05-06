#!/usr/bin/env python3
"""
Fetch SGLang deployment commands from docs.sglang.io using Playwright.

Usage:
    python scripts/fetch_deploy_cmd.py --model deepseek-ai/DeepSeek-V4-Flash
    python scripts/fetch_deploy_cmd.py --model Qwen/Qwen3-235B-A22B --provider Qwen --series Qwen3
    python scripts/fetch_deploy_cmd.py --model deepseek-ai/DeepSeek-V4-Flash --hardware H200 --recipe max-throughput
"""

import argparse
import json
import sys


def infer_provider_and_series(model_id: str, provider: str = None, series: str = None):
    """Infer provider and model series from HuggingFace model ID."""
    org, name = model_id.split("/", 1) if "/" in model_id else ("", model_id)

    provider_map = {
        "deepseek-ai": "DeepSeek",
        "Qwen": "Qwen",
        "meta-llama": "Llama",
        "mistralai": "Mistral",
        "THUDM": "GLM",
        "nvidia": "NVIDIA",
        "openbmb": "MiniMax",
        "internlm": "InternLM",
        "stepfun": "StepFun",
        "XiaomiMiMo": "Xiaomi",
    }

    if not provider:
        provider = provider_map.get(org, org)

    if not series:
        # Strip size/quantization suffixes to get series name
        series = name.split("-")[0]
        if name.startswith("DeepSeek"):
            parts = name.split("-")
            if len(parts) >= 2:
                series = f"{parts[0]}-{parts[1]}"  # DeepSeek-V4
        elif name.startswith("Llama"):
            parts = name.split("-")
            if len(parts) >= 1:
                series = parts[0]

    return provider, series


def fetch_with_playwright(provider: str, series: str, hardware: str = None, recipe: str = None) -> dict | None:
    """Fetch deployment commands using Playwright from docs.sglang.io."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium", file=sys.stderr)
        sys.exit(1)

    url = f"https://docs.sglang.io/cookbook/autoregressive/{provider}/{series}"
    results = {"url": url, "commands": [], "default_command": None}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(5000)

            # Get default command
            pre_blocks = page.query_selector_all("pre")
            for block in pre_blocks:
                text = block.inner_text().strip()
                if "sglang" in text and ("--model" in text or "--model-path" in text):
                    results["default_command"] = text
                    results["commands"].append({"config": "default", "command": text})
                    break

            # If hardware/recipe specified, click those options
            if hardware or recipe:
                all_buttons = page.query_selector_all("button, span, label, div[role]")
                targets = []
                if hardware:
                    targets.append(hardware)
                if recipe:
                    targets.append(recipe.replace("-", " ").title().replace(" ", "-"))
                    targets.append(recipe.title())
                    targets.append(recipe.capitalize())

                for target in targets:
                    for el in all_buttons:
                        try:
                            text = el.inner_text().strip()
                            if target.lower() in text.lower():
                                el.click()
                                page.wait_for_timeout(1500)
                                break
                        except Exception:
                            continue

                # Get updated command after clicking
                pre_blocks = page.query_selector_all("pre")
                for block in pre_blocks:
                    text = block.inner_text().strip()
                    if "sglang" in text and ("--model" in text or "--model-path" in text):
                        config_label = f"{hardware or 'default'}/{recipe or 'default'}"
                        results["commands"].append({"config": config_label, "command": text})
                        results["default_command"] = text
                        break

            browser.close()
    except Exception as e:
        print(f"ERROR: Playwright fetch failed: {e}", file=sys.stderr)
        return None

    return results if results["default_command"] else None


def main():
    parser = argparse.ArgumentParser(description="Fetch SGLang deployment commands from docs.sglang.io")
    parser.add_argument("--model", required=True, help="HuggingFace model ID (e.g., deepseek-ai/DeepSeek-V4-Flash)")
    parser.add_argument("--provider", help="Override provider name (e.g., DeepSeek)")
    parser.add_argument("--series", help="Override model series (e.g., DeepSeek-V4)")
    parser.add_argument("--hardware", help="Target hardware platform (e.g., H200, B200)")
    parser.add_argument("--recipe", help="Deployment recipe (e.g., low-latency, balanced, max-throughput)")
    args = parser.parse_args()

    provider, series = infer_provider_and_series(args.model, args.provider, args.series)
    print(f"Provider: {provider}, Series: {series}", file=sys.stderr)

    result = fetch_with_playwright(provider, series, args.hardware, args.recipe)
    if result:
        print(json.dumps({
            "source": "docs.sglang.io",
            "provider": provider,
            "series": series,
            **result
        }, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({
            "source": "none",
            "provider": provider,
            "series": series,
            "error": "Could not fetch deployment commands",
            "suggestion": f"Try WebFetch on https://huggingface.co/{args.model}"
        }, indent=2, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
