#!/usr/bin/env python3
"""
小红书图片卡片生成器

主入口脚本：将长文案转换为多张小红书风格图片
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List

from playwright.async_api import async_playwright

# 导入本地模块
from text_splitter import split_content, SplitResult
from youtube_thumbnail import get_thumbnail_sync


# 获取 assets 目录路径
SCRIPT_DIR = Path(__file__).parent.absolute()
ASSETS_DIR = SCRIPT_DIR.parent / "assets"

# 卡片尺寸（小红书推荐 3:4）
CARD_WIDTH = 1242
CARD_HEIGHT = 1660


def load_template(template_name: str) -> str:
    """加载 HTML 模板"""
    template_path = ASSETS_DIR / template_name
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def render_cover_html(
    title: str,
    intro: str,
    youtube_thumbnail_path: str,
    account_id: str = "26294572818"
) -> str:
    """渲染封面图 HTML"""
    template = load_template("cover.html")

    # 将本地图片路径转为 file:// URL
    thumbnail_url = f"file://{os.path.abspath(youtube_thumbnail_path)}"

    html = template.replace("{{TITLE}}", title)
    html = html.replace("{{INTRO}}", intro)
    html = html.replace("{{YOUTUBE_THUMBNAIL}}", thumbnail_url)
    html = html.replace("{{ACCOUNT_ID}}", account_id)

    # 修复 CSS 路径
    css_path = f"file://{ASSETS_DIR}/xiaohongshu.css"
    html = html.replace('href="xiaohongshu.css"', f'href="{css_path}"')

    return html


def render_content_html(content: str, account_id: str = "26294572818") -> str:
    """渲染正文页 HTML"""
    template = load_template("content.html")

    html = template.replace("{{CONTENT}}", content)
    html = html.replace("{{ACCOUNT_ID}}", account_id)

    # 修复 CSS 路径
    css_path = f"file://{ASSETS_DIR}/xiaohongshu.css"
    html = html.replace('href="xiaohongshu.css"', f'href="{css_path}"')

    return html


async def html_to_png(html_content: str, output_path: str) -> bool:
    """使用 Playwright 将 HTML 渲染为 PNG"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": CARD_WIDTH, "height": CARD_HEIGHT}
        )

        try:
            # 设置 HTML 内容
            await page.set_content(html_content, wait_until="networkidle")

            # 等待内容渲染
            await asyncio.sleep(0.5)

            # 截图
            await page.screenshot(path=output_path, full_page=False)
            return True

        except Exception as e:
            print(f"渲染失败: {e}")
            return False

        finally:
            await browser.close()


def html_to_png_sync(html_content: str, output_path: str) -> bool:
    """同步版本"""
    return asyncio.run(html_to_png(html_content, output_path))


def generate_cards(
    input_file: str,
    youtube_keyword: str,
    output_dir: str,
    account_id: str = "26294572818",
    max_chars_per_page: int = 400
) -> List[str]:
    """
    主函数：生成小红书图片卡片

    Args:
        input_file: 输入文案文件路径
        youtube_keyword: YouTube 搜索关键词
        output_dir: 输出目录
        account_id: 小红书账号（用于水印）
        max_chars_per_page: 每页最大字符数

    Returns:
        生成的图片文件路径列表
    """
    # 确保输出目录存在
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 读取文案
    print(f"读取文案: {input_file}")
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 拆分文案
    print("拆分文案...")
    result: SplitResult = split_content(content, max_chars_per_page)

    print(f"  标题: {result.cover.title}")
    print(f"  引言: {result.cover.intro[:50]}...")
    print(f"  正文页数: {len(result.pages)}")

    generated_files = []

    # 1. 获取 YouTube 缩略图
    thumbnail_path = output_path / "youtube_thumbnail.png"
    print(f"\n获取 YouTube 截图: {youtube_keyword}")
    success = get_thumbnail_sync(youtube_keyword, str(thumbnail_path))

    if not success:
        print("警告: YouTube 截图获取失败，将使用空白封面")
        # 创建一个空白占位图
        thumbnail_path = None

    # 2. 生成封面图
    print("\n生成封面图...")
    cover_html = render_cover_html(
        result.cover.title,
        result.cover.intro,
        str(thumbnail_path) if thumbnail_path else "",
        account_id
    )

    cover_output = output_path / "cover.png"
    if html_to_png_sync(cover_html, str(cover_output)):
        print(f"  ✓ {cover_output}")
        generated_files.append(str(cover_output))
    else:
        print(f"  ✗ 封面图生成失败")

    # 3. 生成正文页
    print("\n生成正文页...")
    for i, page in enumerate(result.pages, 1):
        page_html = render_content_html(page.content, account_id)
        page_output = output_path / f"page-{i}.png"

        if html_to_png_sync(page_html, str(page_output)):
            print(f"  ✓ {page_output}")
            generated_files.append(str(page_output))
        else:
            print(f"  ✗ 第{i}页生成失败")

    print(f"\n完成! 共生成 {len(generated_files)} 张图片")
    return generated_files


def main():
    parser = argparse.ArgumentParser(
        description="小红书图片卡片生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python generate_cards.py content.md --keyword "AI模型" --output ./output
  python generate_cards.py article.txt -k "Claude AI" -o ./cards --account 12345678
        """
    )

    parser.add_argument(
        "input",
        help="输入文案文件路径 (支持 .md 或 .txt)"
    )
    parser.add_argument(
        "-k", "--keyword",
        required=True,
        help="YouTube 搜索关键词 (用于封面图)"
    )
    parser.add_argument(
        "-o", "--output",
        default="./output",
        help="输出目录 (默认: ./output)"
    )
    parser.add_argument(
        "--account",
        default="26294572818",
        help="小红书账号 (用于水印)"
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=400,
        help="每页最大字符数 (默认: 400)"
    )

    args = parser.parse_args()

    # 检查输入文件
    if not os.path.exists(args.input):
        print(f"错误: 文件不存在 - {args.input}")
        sys.exit(1)

    # 生成卡片
    try:
        files = generate_cards(
            args.input,
            args.keyword,
            args.output,
            args.account,
            args.max_chars
        )

        if not files:
            print("警告: 没有生成任何图片")
            sys.exit(1)

    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
