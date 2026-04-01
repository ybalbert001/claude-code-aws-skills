#!/usr/bin/env python3
"""
HTML 长文章 → 小红书 3:4 图片拆分器

将 HTML 渲染为手机视口长图，在 DOM 块元素边界处智能切割，
输出多张 1242x1660 PNG 图片，适合小红书发布。
"""

import argparse
import asyncio
import io
import os
import sys
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

VIEWPORT_WIDTH = 1080
TARGET_HEIGHT = 1440
MIN_HEIGHT = 1000

BLOCK_SELECTORS = (
    "p,h1,h2,h3,h4,h5,h6,div,li,blockquote,hr,"
    "table,figure,img,pre,ul,ol,section,article,header,footer,tr"
)

JS_GET_BOUNDARIES = """
() => {
    const selectors = '%s';
    const elements = document.querySelectorAll(selectors);
    const boundaries = [];
    for (const el of elements) {
        const rect = el.getBoundingClientRect();
        if (rect.height > 0 && rect.width > 0) {
            boundaries.push({
                top: Math.round(rect.top),
                bottom: Math.round(rect.bottom)
            });
        }
    }
    boundaries.sort((a, b) => a.top - b.top);
    return {
        boundaries: boundaries,
        totalHeight: Math.max(
            document.body.scrollHeight,
            document.documentElement.scrollHeight
        )
    };
}
""" % BLOCK_SELECTORS


def merge_intervals(boundaries):
    """合并重叠的元素区间，返回不重叠的覆盖区域"""
    intervals = [(b["top"], b["bottom"]) for b in boundaries]
    intervals.sort()
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def extract_split_candidates(boundaries):
    """从元素边界中提取候选切割点"""
    merged = merge_intervals(boundaries)
    candidates = set()

    # 元素间的 gap 中点
    for i in range(len(merged) - 1):
        gap_top = merged[i][1]
        gap_bottom = merged[i + 1][0]
        if gap_bottom > gap_top:
            candidates.add((gap_top + gap_bottom) // 2)

    # 所有元素的 bottom 边缘（元素紧邻时的切割点）
    for b in boundaries:
        candidates.add(b["bottom"])

    return sorted(candidates)


def find_split_points(candidates, total_height, target_height, min_height):
    """贪心算法：找最优切割点，使每片接近 target_height"""
    if total_height <= target_height:
        return []

    split_points = []
    current_start = 0

    while current_start + target_height < total_height:
        ideal = current_start + target_height
        best = None
        best_dist = float("inf")

        for c in candidates:
            if c <= current_start + min_height:
                continue
            if c > current_start + target_height * 1.5:
                break
            dist = abs(c - ideal)
            if dist < best_dist:
                best_dist = dist
                best = c

        if best is None:
            best = ideal

        split_points.append(best)
        current_start = best

    # 末尾残片太短则与上一片合并
    remaining = total_height - (split_points[-1] if split_points else 0)
    if remaining < min_height and split_points:
        prev_start = split_points[-2] if len(split_points) >= 2 else 0
        combined = total_height - prev_start
        if combined <= target_height * 1.8:
            split_points.pop()

    return split_points


def crop_and_save(img, split_points, total_height, target_height, viewport_width, output_dir, bg_color):
    """按切割点裁切长图，短图补白"""
    edges = [0] + split_points + [total_height]
    files = []

    for i in range(len(edges) - 1):
        y_start = edges[i]
        y_end = edges[i + 1]
        cropped = img.crop((0, y_start, viewport_width, y_end))

        if cropped.height < target_height:
            padded = Image.new("RGB", (viewport_width, target_height), bg_color)
            padded.paste(cropped, (0, 0))
            cropped = padded

        out_path = output_dir / f"slide-{i + 1}.png"
        cropped.save(str(out_path), "PNG")
        files.append(str(out_path))
        print(f"  slide-{i + 1}.png  ({viewport_width}x{cropped.height})")

    return files


async def split_html_to_images(
    input_html,
    output_dir,
    target_height=TARGET_HEIGHT,
    min_height=MIN_HEIGHT,
    viewport_width=VIEWPORT_WIDTH,
    bg_color=(255, 255, 255),
):
    """主流程：HTML → 渲染 → 获取边界 → 切图"""
    html_path = Path(input_html)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    file_url = html_path.absolute().as_uri()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": viewport_width, "height": target_height}
        )

        try:
            # 用 goto 加载文件 URL，这样相对路径的图片等资源能正常解析
            await page.goto(file_url, wait_until="networkidle")

            # 注入 CSS 放大字体，适配手机截图阅读体验
            # 先给代码块打标记，再用 CSS 排除
            await page.evaluate("""
                () => {
                    document.querySelectorAll('section, div').forEach(el => {
                        const style = el.getAttribute('style') || '';
                        const font = getComputedStyle(el).fontFamily;
                        if (style.match(/background.*#(1e1e2e|282c34|2d2d2d|1a1b26)/i)
                            || font.match(/monospace|Consolas|Monaco|Menlo/i)) {
                            el.classList.add('__code_block__');
                        }
                    });
                }
            """)
            await page.add_style_tag(content="""
                body, body > div {
                    font-size: 30px !important;
                    line-height: 2.0 !important;
                    padding: 30px 50px !important;
                }
                p, li, td, div:not(.__code_block__) {
                    font-size: 30px !important;
                }
                span {
                    font-size: 30px !important;
                }
                h1, h2, h3 {
                    font-size: 40px !important;
                }
                h4, h5, h6 {
                    font-size: 34px !important;
                }
                .__code_block__,
                .__code_block__ *,
                pre, pre *,
                code {
                    font-size: 22px !important;
                    line-height: 1.6 !important;
                }
            """)
            await asyncio.sleep(0.5)

            # 获取元素边界
            result = await page.evaluate(JS_GET_BOUNDARIES)
            boundaries = result["boundaries"]
            total_height = result["totalHeight"]
            print(f"页面总高度: {total_height}px, 检测到 {len(boundaries)} 个块元素")

            # 截全页长图
            screenshot_bytes = await page.screenshot(full_page=True)

        finally:
            await browser.close()

    img = Image.open(io.BytesIO(screenshot_bytes))
    actual_height = img.height
    print(f"截图实际尺寸: {img.width}x{actual_height}")

    # 用截图实际高度（更准确）
    total_height = max(total_height, actual_height)

    candidates = extract_split_candidates(boundaries)
    split_points = find_split_points(candidates, total_height, target_height, min_height)
    print(f"切割为 {len(split_points) + 1} 张图片")

    files = crop_and_save(img, split_points, total_height, target_height, viewport_width, output_dir, bg_color)
    return files


def parse_color(color_str):
    """解析颜色字符串 #rrggbb → (r, g, b)"""
    color_str = color_str.lstrip("#")
    return tuple(int(color_str[i : i + 2], 16) for i in (0, 2, 4))


def main():
    parser = argparse.ArgumentParser(
        description="将 HTML 长文章拆分为小红书 3:4 比例图片",
        epilog="示例: python split_html_to_images.py article.html -o ./output",
    )
    parser.add_argument("input", help="输入 HTML 文件路径")
    parser.add_argument("-o", "--output", default="./output", help="输出目录 (默认: ./output)")
    parser.add_argument("--target-height", type=int, default=TARGET_HEIGHT, help=f"目标切片高度 (默认: {TARGET_HEIGHT})")
    parser.add_argument("--min-height", type=int, default=MIN_HEIGHT, help=f"最小切片高度 (默认: {MIN_HEIGHT})")
    parser.add_argument("--viewport-width", type=int, default=VIEWPORT_WIDTH, help=f"视口宽度 (默认: {VIEWPORT_WIDTH})")
    parser.add_argument("--bg-color", default="#ffffff", help="填充背景色 (默认: #ffffff)")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"错误: 文件不存在 - {args.input}")
        sys.exit(1)

    bg_color = parse_color(args.bg_color)

    files = asyncio.run(
        split_html_to_images(
            args.input,
            args.output,
            args.target_height,
            args.min_height,
            args.viewport_width,
            bg_color,
        )
    )

    print(f"\n完成! 共生成 {len(files)} 张图片")
    for f in files:
        print(f"  {f}")


if __name__ == "__main__":
    main()
