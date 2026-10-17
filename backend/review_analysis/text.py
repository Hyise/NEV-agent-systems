"""Deterministic conversion from preserved source objects to analysis text."""

from typing import Any, Mapping


def extract_analysis_text(original_review: Mapping[str, Any]) -> str:
    tabular_full_text = original_review.get("分项评论全文")
    if isinstance(tabular_full_text, str) and tabular_full_text.strip():
        return tabular_full_text

    parts: list[str] = []
    seen_content: set[str] = set()

    summary = original_review.get("feeling_summary")
    if isinstance(summary, str) and summary.strip():
        clean = summary.strip()
        parts.append(clean)
        seen_content.add(clean)

    contents = original_review.get("contents")
    if isinstance(contents, list):
        for section in contents:
            if not isinstance(section, Mapping):
                continue
            content = section.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            clean = content.strip()
            if clean in seen_content:
                continue
            seen_content.add(clean)
            name = section.get("structuredname")
            title = name.strip() if isinstance(name, str) else ""
            parts.append(f"{title}：{clean}" if title else clean)

    if not parts:
        raise ValueError("原始评论没有可分析文本")
    return "\n".join(parts)
