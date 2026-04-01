#!/usr/bin/env python3
"""
图片生成API调用脚本

通过 OpenRouter API 调用支持生图的模型生成图片。

可用模型:
- google/gemini-3.1-flash-image-preview (默认，Gemini生图模型)
- bytedance-seed/seedream-4.5 (字节跳动SeedDream生图模型)

使用方法:
    python generate_image.py --prompt "图片描述" --output output.png
    python generate_image.py --prompt "图片描述" --model bytedance-seed/seedream-4.5 --output output.png

环境变量:
    OPENROUTER_API_KEY - OpenRouter API密钥（必须）
"""

import os
import sys
import argparse
import base64
import requests
from pathlib import Path
from typing import Optional, Dict

# 可用的生图模型
AVAILABLE_MODELS = {
    "gemini": "google/gemini-3.1-flash-image-preview",
    "seedream": "bytedance-seed/seedream-4.5",
}

# 默认模型
DEFAULT_MODEL = "google/gemini-3.1-flash-image-preview"


class OpenRouterImageGenerator:
    """OpenRouter API图片生成器 - 通过chat completions接口调用支持生图的模型"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or self._get_api_key()

    def _get_api_key(self) -> str:
        api_key = os.environ.get('OPENROUTER_API_KEY')
        if not api_key:
            raise ValueError("请设置环境变量 OPENROUTER_API_KEY")
        return api_key

    def _get_proxies(self, proxy: Optional[str] = None) -> Optional[Dict[str, str]]:
        """获取代理配置"""
        if proxy:
            return {'http': proxy, 'https': proxy}

        http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
        https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')

        if http_proxy or https_proxy:
            return {
                'http': http_proxy or https_proxy,
                'https': https_proxy or http_proxy
            }
        return None

    def generate(self, prompt: str, output_path: str, **kwargs) -> str:
        """
        通过OpenRouter的chat completions接口生成图片

        需要设置 modalities: ["image", "text"]，图片数据在响应的
        message.images 数组中，格式为 {type: "image_url", image_url: {url: "data:image/png;base64,..."}}.

        参考: https://openrouter.ai/docs
        """
        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        model = kwargs.get("model", DEFAULT_MODEL)

        data = {
            "model": model,
            "modalities": ["image", "text"],
            "messages": [
                {
                    "role": "user",
                    "content": f"Generate an image based on the following description. "
                               f"Return ONLY the image, no text explanation.\n\n{prompt}"
                }
            ],
        }

        proxies = self._get_proxies(kwargs.get("proxy"))

        try:
            response = requests.post(url, json=data, headers=headers, proxies=proxies, timeout=180)
            response.raise_for_status()

            result = response.json()

            # 从chat completions响应中提取图片
            choices = result.get("choices", [])
            if not choices:
                raise ValueError(f"API响应中无choices: {result}")

            message = choices[0].get("message", {})

            # 方式1: 从 message.images 数组提取 (OpenRouter 返回格式)
            images = message.get("images", [])
            for img in images:
                if isinstance(img, dict) and img.get("type") == "image_url":
                    url_str = img.get("image_url", {}).get("url", "")
                    if url_str.startswith("data:image"):
                        b64_str = url_str.split(",", 1)[1]
                        image_bytes = base64.b64decode(b64_str)
                        with open(output_path, 'wb') as f:
                            f.write(image_bytes)
                        return output_path

            # 方式2: multipart content (备用)
            content = message.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        inline_data = part.get("inline_data")
                        if inline_data and inline_data.get("data"):
                            image_bytes = base64.b64decode(inline_data["data"])
                            with open(output_path, 'wb') as f:
                                f.write(image_bytes)
                            return output_path
                        image_url = part.get("image_url", {})
                        url_str = image_url.get("url", "")
                        if url_str.startswith("data:image"):
                            b64_str = url_str.split(",", 1)[1]
                            image_bytes = base64.b64decode(b64_str)
                            with open(output_path, 'wb') as f:
                                f.write(image_bytes)
                            return output_path

            raise ValueError(
                f"无法从模型 {model} 的响应中提取图片数据。"
                f"响应内容: {str(content)[:500]}"
            )

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"OpenRouter API调用失败: {str(e)}")


def main():
    model_list = "\n".join(f"  - {alias}: {full}" for alias, full in AVAILABLE_MODELS.items())

    parser = argparse.ArgumentParser(
        description="通过OpenRouter API调用生图模型生成图片",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"可用模型别名:\n{model_list}"
    )

    parser.add_argument(
        "--prompt",
        required=True,
        help="图片生成提示词"
    )

    parser.add_argument(
        "--model",
        default=None,
        help=f"生图模型 (可用别名: {', '.join(AVAILABLE_MODELS.keys())}，或完整模型ID。默认: gemini)"
    )

    parser.add_argument(
        "--output",
        required=True,
        help="输出图片路径"
    )

    parser.add_argument(
        "--proxy",
        help="代理地址 (如: http://127.0.0.1:7890)"
    )

    args = parser.parse_args()

    # 解析模型：支持别名或完整模型ID
    if args.model is None:
        model = DEFAULT_MODEL
    elif args.model in AVAILABLE_MODELS:
        model = AVAILABLE_MODELS[args.model]
    else:
        model = args.model

    # 创建输出目录
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        generator = OpenRouterImageGenerator()

        kwargs = {"model": model}
        if args.proxy:
            kwargs["proxy"] = args.proxy

        print(f"🎨 使用 OpenRouter API 生成图片...")
        print(f"📦 模型: {model}")
        print(f"📝 提示词: {args.prompt}")

        result_path = generator.generate(
            prompt=args.prompt,
            output_path=str(output_path),
            **kwargs
        )

        print(f"✅ 图片已生成: {result_path}")
        return 0

    except Exception as e:
        print(f"❌ 生成失败: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
