"""Shared chapter contracts and Markdown rendering for the two 60-page documents."""

from __future__ import annotations

from typing import Any

DOCUMENT_TARGET_PAGES = 60  # Includes one cover page and one contents page.
MANUAL_CHAPTERS = (
    ("manual_function_overview", "系统功能概述", 4),
    ("manual_installation_config", "软件安装与配置", 6),
    ("manual_basics", "基础操作与使用准备", 5),
    ("manual_modules", "软件功能使用说明", 24),
    ("manual_data_management", "数据与结果管理", 6),
    ("operation_flow", "典型使用流程", 6),
    ("manual_usage_notes", "使用注意事项", 3),
    ("faq", "常见问题与故障排查", 4),
)
DESIGN_CHAPTERS = (
    ("design_background", "项目背景与设计目标", 3),
    ("design_requirements", "系统需求分析", 4),
    ("design_architecture", "系统总体架构设计", 7),
    ("design_functions", "系统功能与模块详细设计", 12),
    ("design_interfaces", "接口设计", 6),
    ("design_data", "数据与存储设计", 6),
    ("design_processing", "核心处理流程与算法设计", 6),
    ("design_reliability", "安全性与可靠性设计", 4),
    ("design_deployment", "系统部署与运行设计", 4),
    ("design_use_cases", "系统关键用例与典型应用场景", 6),
)


def prose(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("paragraphs") or value.get("body") or value.get("overview")
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if value is not None and str(value).strip() else []


def section_markdown(value: Any, prefix: str, level: int = 2) -> list[str]:
    """Render model-authored prose, tables and nested subheadings without writing prose."""
    lines = [line for paragraph in prose(value) for line in (paragraph, "")]
    if not isinstance(value, dict):
        return lines
    tables = value.get("tables") or ([value["table"]] if value.get("table") else [])
    if value.get("requirements"):
        tables = [*tables, value["requirements"]]
    for table in tables:
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        if not headers:
            continue
        clean = lambda text: str(text).replace("|", "\\|").replace("\n", "<br>")
        lines.extend(["| " + " | ".join(map(clean, headers)) + " |", "| " + " | ".join("---" for _ in headers) + " |"])
        for row in rows:
            padded = list(row) + [""] * len(headers)
            lines.append("| " + " | ".join(map(clean, padded[:len(headers)])) + " |")
        lines.append("")
    for index, child in enumerate(value.get("subsections") or [], start=1):
        number = f"{prefix}.{index}"
        lines.extend([f"{'#' * min(level + 1, 6)} {number} {child['title']}", ""])
        lines.extend(section_markdown(child, number, level + 1))
    return lines
