#!/usr/bin/env python3
"""
YouTube 缩略图/截图获取模块

功能：
1. 搜索关键词，获取热门视频
2. 截取视频播放页面作为封面图素材
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, Page, Browser


async def search_youtube(keyword: str, browser: Browser) -> Optional[str]:
    """
    在 YouTube 搜索关键词，返回第一个视频的 URL

    Args:
        keyword: 搜索关键词
        browser: Playwright browser 实例

    Returns:
        视频 URL 或 None
    """
    page = await browser.new_page()

    try:
        # 构建搜索 URL
        search_url = f"https://www.youtube.com/results?search_query={quote_plus(keyword)}"
        await page.goto(search_url, wait_until="networkidle", timeout=30000)

        # 等待视频列表加载
        await page.wait_for_selector("ytd-video-renderer", timeout=10000)

        # 获取第一个视频链接
        video_link = await page.query_selector("ytd-video-renderer a#video-title")

        if video_link:
            href = await video_link.get_attribute("href")
            if href:
                return f"https://www.youtube.com{href}"

        return None

    except Exception as e:
        print(f"搜索失败: {e}")
        return None

    finally:
        await page.close()


async def capture_video_screenshot(
    video_url: str,
    output_path: str,
    browser: Browser,
    width: int = 1242,
    height: int = 830
) -> bool:
    """
    截取 YouTube 视频页面作为封面素材

    Args:
        video_url: 视频 URL
        output_path: 输出图片路径
        browser: Playwright browser 实例
        width: 截图宽度
        height: 截图高度

    Returns:
        是否成功
    """
    page = await browser.new_page(viewport={"width": width, "height": height})

    try:
        await page.goto(video_url, wait_until="domcontentloaded", timeout=30000)

        # 等待视频播放器加载
        await page.wait_for_selector("video", timeout=15000)

        # 暂停视频（如果自动播放）
        await page.evaluate("""
            const video = document.querySelector('video');
            if (video) {
                video.pause();
                // 跳到视频的1/3位置，通常有更好的画面
                video.currentTime = video.duration / 3;
            }
        """)

        # 等待一下让画面稳定
        await asyncio.sleep(1)

        # 隐藏一些UI元素获得更干净的截图
        await page.evaluate("""
            // 隐藏YouTube的播放控件和其他UI
            const selectors = [
                '.ytp-chrome-bottom',
                '.ytp-chrome-top',
                '.ytp-gradient-bottom',
                '.ytp-gradient-top',
                '.ytp-pause-overlay',
                '#movie_player .ytp-cued-thumbnail-overlay'
            ];
            selectors.forEach(sel => {
                const el = document.querySelector(sel);
                if (el) el.style.display = 'none';
            });
        """)

        # 截取整个视口
        await page.screenshot(path=output_path)
        return True

    except Exception as e:
        print(f"截图失败: {e}")
        return False

    finally:
        await page.close()


async def get_youtube_thumbnail(
    keyword: str,
    output_path: str,
    width: int = 1242,
    height: int = 830
) -> bool:
    """
    主入口函数：搜索关键词并截取热门视频画面

    Args:
        keyword: YouTube 搜索关键词
        output_path: 输出图片路径
        width: 截图宽度
        height: 截图高度

    Returns:
        是否成功
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            print(f"正在搜索: {keyword}")

            # 搜索视频
            video_url = await search_youtube(keyword, browser)

            if not video_url:
                print("未找到相关视频")
                return False

            print(f"找到视频: {video_url}")

            # 截取视频画面
            print(f"正在截取视频画面...")
            success = await capture_video_screenshot(
                video_url, output_path, browser, width, height
            )

            if success:
                print(f"截图已保存: {output_path}")
            return success

        finally:
            await browser.close()


def get_thumbnail_sync(
    keyword: str,
    output_path: str,
    width: int = 1242,
    height: int = 830
) -> bool:
    """
    同步版本的入口函数
    """
    return asyncio.run(get_youtube_thumbnail(keyword, output_path, width, height))


# 命令行接口
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="获取 YouTube 视频截图")
    parser.add_argument("keyword", help="搜索关键词")
    parser.add_argument("-o", "--output", default="youtube_thumbnail.png", help="输出文件路径")
    parser.add_argument("--width", type=int, default=1242, help="截图宽度")
    parser.add_argument("--height", type=int, default=830, help="截图高度")

    args = parser.parse_args()

    success = get_thumbnail_sync(
        args.keyword,
        args.output,
        args.width,
        args.height
    )

    exit(0 if success else 1)
