#!/usr/bin/env python3
"""
文案拆分模块 - 将长文案智能拆分为适合小红书图片的多个部分

核心原则：只拆分，不编辑
"""

import re
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class CoverContent:
    """封面图内容"""
    title: str
    intro: str


@dataclass
class PageContent:
    """正文页内容"""
    content: str  # HTML格式的内容


@dataclass
class SplitResult:
    """拆分结果"""
    cover: CoverContent
    pages: List[PageContent]


def extract_title_and_intro(text: str) -> Tuple[str, str, str]:
    """
    从文案中提取标题和引言

    Returns:
        (title, intro, remaining_text)
    """
    lines = text.strip().split('\n')

    title = ""
    intro = ""
    remaining_start = 0

    # 查找标题 (# 开头或第一行)
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # Markdown 标题
        if line.startswith('# '):
            title = line[2:].strip()
            remaining_start = i + 1
            break
        # 如果没有 # 标记，第一个非空行作为标题
        elif not title:
            title = line
            remaining_start = i + 1
            break

    # 查找引言 (标题后的第一段非空内容)
    intro_lines = []
    for i in range(remaining_start, len(lines)):
        line = lines[i].strip()

        # 跳过空行
        if not line:
            if intro_lines:  # 引言结束
                remaining_start = i + 1
                break
            continue

        # 遇到下一个标题，结束引言
        if line.startswith('## ') or line.startswith('# '):
            remaining_start = i
            break

        intro_lines.append(line)

    intro = ' '.join(intro_lines)
    remaining_text = '\n'.join(lines[remaining_start:])

    return title, intro, remaining_text


def split_by_sections(text: str) -> List[dict]:
    """
    按小标题分割正文

    Returns:
        List of {"heading": str or None, "content": str}
    """
    sections = []
    current_heading = None
    current_content = []

    lines = text.split('\n')

    for line in lines:
        stripped = line.strip()

        # 检测二级标题
        if stripped.startswith('## '):
            # 保存之前的section
            if current_content or current_heading:
                sections.append({
                    "heading": current_heading,
                    "content": '\n'.join(current_content).strip()
                })
            current_heading = stripped[3:].strip()
            current_content = []
        else:
            current_content.append(line)

    # 保存最后一个section
    if current_content or current_heading:
        sections.append({
            "heading": current_heading,
            "content": '\n'.join(current_content).strip()
        })

    return sections


def count_chars(text: str) -> int:
    """计算文本字符数（去除空白和标记）"""
    # 移除HTML标签
    clean = re.sub(r'<[^>]+>', '', text)
    # 移除多余空白
    clean = re.sub(r'\s+', '', clean)
    return len(clean)


def split_long_section(section: dict, max_chars: int = 400) -> List[dict]:
    """
    将过长的section拆分为多个
    在句子边界处分割，保持完整性
    """
    heading = section["heading"]
    content = section["content"]

    if count_chars(content) <= max_chars:
        return [section]

    # 按段落分割
    paragraphs = re.split(r'\n\s*\n', content)

    result = []
    current_content = []
    current_chars = 0
    first_section = True

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_chars = count_chars(para)

        # 如果当前段落加入后超过限制
        if current_chars + para_chars > max_chars and current_content:
            result.append({
                "heading": heading if first_section else None,
                "content": '\n\n'.join(current_content)
            })
            first_section = False
            current_content = [para]
            current_chars = para_chars
        else:
            current_content.append(para)
            current_chars += para_chars

    # 保存剩余内容
    if current_content:
        result.append({
            "heading": heading if first_section else None,
            "content": '\n\n'.join(current_content)
        })

    return result


def markdown_to_html(text: str) -> str:
    """
    将Markdown格式转换为HTML（简单实现）
    """
    html = text

    # 处理粗体 **text** 或 __text__
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'__(.+?)__', r'<strong>\1</strong>', html)

    # 处理斜体 *text* 或 _text_
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'(?<![_])_(.+?)_(?![_])', r'<em>\1</em>', html)

    # 处理无序列表
    lines = html.split('\n')
    result_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # 检测列表项
        if stripped.startswith('- ') or stripped.startswith('* '):
            if not in_list:
                result_lines.append('<ul>')
                in_list = True
            result_lines.append(f'<li>{stripped[2:]}</li>')
        else:
            if in_list:
                result_lines.append('</ul>')
                in_list = False

            # 非列表项，包装为段落
            if stripped:
                result_lines.append(f'<p>{stripped}</p>')
            else:
                result_lines.append('')

    if in_list:
        result_lines.append('</ul>')

    return '\n'.join(result_lines)


def section_to_html(section: dict) -> str:
    """将section转换为HTML格式"""
    html_parts = []

    if section["heading"]:
        html_parts.append(f'<h2>{section["heading"]}</h2>')

    if section["content"]:
        html_parts.append(markdown_to_html(section["content"]))

    return '\n'.join(html_parts)


def split_content(text: str, max_chars_per_page: int = 400) -> SplitResult:
    """
    主入口函数：智能拆分文案

    Args:
        text: 原始文案内容（支持Markdown格式）
        max_chars_per_page: 每页最大字符数

    Returns:
        SplitResult 包含封面内容和正文页列表
    """
    # 1. 提取标题和引言
    title, intro, remaining = extract_title_and_intro(text)

    cover = CoverContent(title=title, intro=intro)

    # 2. 按小标题分割
    sections = split_by_sections(remaining)

    # 3. 处理过长的section
    all_sections = []
    for section in sections:
        split_sections = split_long_section(section, max_chars_per_page)
        all_sections.extend(split_sections)

    # 4. 合并较短的相邻section（可选优化）
    merged_sections = merge_short_sections(all_sections, max_chars_per_page)

    # 5. 转换为HTML格式
    pages = []
    for section in merged_sections:
        html_content = section_to_html(section)
        if html_content.strip():
            pages.append(PageContent(content=html_content))

    return SplitResult(cover=cover, pages=pages)


def merge_short_sections(sections: List[dict], max_chars: int) -> List[dict]:
    """合并过短的相邻section以优化页面利用"""
    if not sections:
        return sections

    result = []
    current = None

    for section in sections:
        if current is None:
            current = section.copy()
            continue

        # 计算合并后的字符数
        combined_chars = count_chars(current["content"]) + count_chars(section["content"])

        # 如果合并后不超过限制，且下一个section没有标题，则合并
        if combined_chars <= max_chars and not section["heading"]:
            current["content"] = current["content"] + '\n\n' + section["content"]
        else:
            result.append(current)
            current = section.copy()

    if current:
        result.append(current)

    return result


# 测试代码
if __name__ == "__main__":
    sample_text = """# AI模型迭代为什么越来越快了

Anthropic快速迭代模型，用户反馈驱动研发，运营与评估体系革新推动行业标准升级。

## 用户反馈正在重塑研发节奏

最近Anthropic发布了Sonnet 4.5，距离Claude 4系列发布才几个月时间。这种"狗年式"的发展速度（一个月像一年）背后，是整个AI行业运作方式的根本转变。

作为一个AI从业者，我从Anthropic产品负责人Mike Krieger最近的分享中，看到了几个关键变化。

传统的AI模型开发像是闭门造车——研究团队埋头训练，发布后才知道效果。现在完全不同了。

## 运营能力成了新的竞争力

技术突破固然重要，但运营效率同样关键。Anthropic从去年5月的Sonnet 3.5到现在，整个模型发布流程已经完全工业化：

- 建立了早期用户测试机制
- 设计了客户共同发布计划
- 优化了发布日的推送流程

有个客户评价说，这是他见过最流畅的模型发布。这种运营能力的提升，让模型更新从"大事件"变成了"常规动作"。
"""

    result = split_content(sample_text)

    print("=== 封面内容 ===")
    print(f"标题: {result.cover.title}")
    print(f"引言: {result.cover.intro}")
    print()

    print(f"=== 正文页 ({len(result.pages)}页) ===")
    for i, page in enumerate(result.pages, 1):
        print(f"\n--- 第{i}页 ---")
        print(page.content[:200] + "..." if len(page.content) > 200 else page.content)
