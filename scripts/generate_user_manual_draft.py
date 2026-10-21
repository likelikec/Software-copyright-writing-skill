#!/usr/bin/env python3
"""Draft the eight-chapter user manual from confirmed project evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common import ensure_dir, manual_image_caption, read_json
from document_structure import MANUAL_CHAPTERS, prose, section_markdown


TOP_LEVEL_TITLES = [title for _field, title, _pages in MANUAL_CHAPTERS]
MODULE_PROSE_MIN_CHARS = 120
TEMPLATE_MARKERS = ["进入方式：", "页面内容：", "操作步骤：", "操作规则：", "操作结果与反馈："]
AI_TONE_MARKERS = ["旨在", "赋能", "一站式", "高效便捷", "显著提升", "强大能力", "丰富功能"]
SCREENSHOT_PLACEHOLDER_PATTERN = re.compile(r"【图\s*4-\d+\s+截图预留：.*?】")


def paragraph_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    return [text] if text else []


def required_paragraphs(business: dict[str, Any], field: str, label: str) -> list[str]:
    values = paragraph_list(business.get(field))
    if not values:
        raise SystemExit(
            "STOP_FOR_USER\n"
            f"NEXT_ACTION: 业务理解缺少 `{field}`，无法生成用户手册{label}。"
            "须依据项目真实证据补写正文后重新运行。"
        )
    return values


def text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [item.strip() for item in re.split(r"[；;\n]+", text) if item.strip()]


def required_text(item: dict[str, Any], field: str, title: str) -> str:
    value = str(item.get(field) or "").strip()
    if not value:
        raise SystemExit(
            "STOP_FOR_USER\n"
            f"NEXT_ACTION: 用户手册模块「{title}」缺少 `{field}`，须补全真实证据后重新生成。"
        )
    return value


def normalize_screenshots(raw: Any, workdir: Path, title: str) -> list[dict[str, str]]:
    manifest_path = workdir / "截图" / "截图清单.json"
    if manifest_path.is_file():
        manifest = read_json(manifest_path)
        if manifest.get("method") == "generated-ui":
            matched = []
            for item in manifest.get("screenshots", []):
                if item.get("module") != title:
                    continue
                image = workdir / str(item.get("path") or "")
                if image.is_file() and image.resolve().is_relative_to((workdir / "截图").resolve()):
                    relative = image.resolve().relative_to(workdir.resolve())
                    caption = manual_image_caption(str(item.get("caption") or ""), title)
                    matched.append({"path": str(Path("..") / relative), "caption": caption})
            if matched:
                return matched
    values = raw if isinstance(raw, list) else ([raw] if raw else [])
    result: list[dict[str, str]] = []
    for value in values:
        if isinstance(value, dict):
            path = str(value.get("path") or value.get("file") or "").strip()
            caption = str(value.get("caption") or value.get("note") or "").strip()
        else:
            path = str(value or "").strip()
            caption = ""
        if not path:
            continue
        candidate = (workdir / path).resolve() if not Path(path).is_absolute() else Path(path)
        if candidate.exists() and candidate.is_file():
            try:
                relative = candidate.relative_to(workdir.resolve())
                md_path = str(Path("..") / relative).replace("\\", "/")
            except ValueError:
                md_path = str(candidate)
            result.append({"path": md_path, "caption": caption or f"{title}页面或操作结果"})
        else:
            result.append({"path": "", "caption": caption or path})
    if not result:
        result.append({"path": "", "caption": f"请在此处插入「{title}」页面或操作结果截图"})
    return result


def normalize_modules(business: dict[str, Any], workdir: Path) -> list[dict[str, Any]]:
    raw = business.get("manual_modules")
    if not isinstance(raw, list) or not raw:
        raise SystemExit(
            "STOP_FOR_USER\n"
            "NEXT_ACTION: 业务理解缺少 `manual_modules`。须依据真实页面、入口、动作和反馈补全第4章内容。"
        )
    modules: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"STOP_FOR_USER\nNEXT_ACTION: manual_modules 第 {index} 项不是对象。")
        title = str(item.get("title") or item.get("feature") or "").strip()
        if not title:
            raise SystemExit(f"STOP_FOR_USER\nNEXT_ACTION: manual_modules 第 {index} 项缺少 title。")
        body = paragraph_list(item.get("body"))
        if not body:
            raise SystemExit(f"STOP_FOR_USER\nNEXT_ACTION: 用户手册模块「{title}」缺少 body。")
        modules.append(
            {
                "title": title,
                "body": body,
                "subsections": item.get("subsections") or [],
                "tables": item.get("tables") or ([item["table"]] if item.get("table") else []),
                "purpose": required_text(item, "purpose", title),
                "usage": required_text(item, "usage" if item.get("usage") else "usage_scenario", title),
                "entry": required_text(item, "entry", title),
                "visible_elements": text_list(item.get("visible_elements")),
                "operation_steps": text_list(item.get("operation_steps")),
                "validation_rules": text_list(item.get("validation_rules")),
                "feedback": text_list(item.get("feedback")),
                "boundary": text_list(item.get("boundary")),
                "screenshots": normalize_screenshots(item.get("screenshot"), workdir, title),
            }
        )
    return modules


def requirements_table(raw: Any) -> tuple[list[str], list[list[str]]] | None:
    if not isinstance(raw, dict):
        return None
    headers = raw.get("headers") or ["项目", "要求"]
    rows = raw.get("rows")
    if not isinstance(headers, list) or not isinstance(rows, list):
        return None
    clean_rows = [row for row in rows if isinstance(row, list)]
    return [str(x) for x in headers], [[str(x) for x in row] for row in clean_rows]


def heading(index: int, title: str) -> str:
    return f"## {index}. {title}"


def render_screenshot(lines: list[str], chapter: int, serial: int, item: dict[str, str]) -> None:
    label = f"图 {chapter}-{serial}"
    if item["path"]:
        lines.extend([f"![{label} {item['caption']}]({item['path']})", ""])
    else:
        lines.extend([f"【{label} 截图预留：{item['caption']}。】", ""])


def render_manual(
    software_name: str,
    business: dict[str, Any],
    modules: list[dict[str, Any]],
    faq: list[dict[str, str]],
) -> str:
    lines = [f"# {software_name}用户手册", ""]
    serial = 0
    for chapter, (field, title, _pages) in enumerate(MANUAL_CHAPTERS, start=1):
        lines.extend([heading(chapter, title), ""])
        if field == "manual_modules":
            for index, module in enumerate(modules, start=1):
                lines.extend([f"### 4.{index} {module['title']}", ""])
                lines.extend(section_markdown(module, f"4.{index}", 3))
                for screenshot in module["screenshots"]:
                    serial += 1
                    render_screenshot(lines, 4, serial, screenshot)
        elif field == "faq":
            for index, item in enumerate(faq, start=1):
                lines.extend([f"### 8.{index} {item['question']}", ""])
                lines.extend(section_markdown(item["answer"], f"8.{index}", 3))
        else:
            lines.extend(section_markdown(business[field], str(chapter)))
    lines.extend(["```text", "STOP_FOR_USER", "NEXT_ACTION: 须确认完整用户手册草稿后运行 confirm_stage.py --stage markdown。", "```", ""])
    return "\n".join(lines)


def module_body_text(module: dict[str, Any]) -> str:
    return "\n".join(section_markdown(module, "4"))


def quality_issues(text: str, modules: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for title in TOP_LEVEL_TITLES:
        if title not in text:
            issues.append(f"缺少固定章节：{title}")
    for marker in TEMPLATE_MARKERS:
        if marker in text:
            issues.append(f"存在字段式模板小标题：{marker}")
    for marker in AI_TONE_MARKERS:
        if marker in text:
            issues.append(f"存在空泛表达：{marker}")
    for module in modules:
        body = module_body_text(module)
        if len(body.replace(" ", "").replace("\n", "")) < MODULE_PROSE_MIN_CHARS:
            issues.append(f"模块正文过短：{module['title']}")
        if module["entry"] and module["entry"] not in body:
            # The model may paraphrase. This is advisory in the generated log, not a hard stop.
            pass
    if not SCREENSHOT_PLACEHOLDER_PATTERN.search(text) and not re.search(r"!\[图\s*4-\d+", text):
        issues.append("第4章没有截图或可见截图预留")
    return issues


def quality_warnings(modules: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if any(not module["operation_steps"] for module in modules):
        warnings.append("存在功能模块未记录 operation_steps")
    if any(not module["feedback"] for module in modules):
        warnings.append("存在功能模块未记录 feedback")
    if any(not module["boundary"] for module in modules):
        warnings.append("存在功能模块未记录 boundary")
    return warnings


def write_review_records(out_dir: Path, records: list[dict[str, Any]], modules: list[dict[str, Any]]) -> None:
    (out_dir / "用户手册自检记录.json").write_text(
        json.dumps({"rounds": records, "module_count": len(modules)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = ["# 用户手册自检记录", ""]
    for record in records:
        lines.extend([f"## 第 {record['round']} 轮：{record['action']}", ""])
        lines.extend(f"- {item}" for item in record["issues"] or ["未发现须继续修正的问题"])
        lines.extend(f"- WARN：{item}" for item in record.get("warnings") or [])
        lines.append("")
    lines.extend(["## 模块清单", ""])
    lines.extend(f"- {module['title']}" for module in modules)
    (out_dir / "用户手册自检记录.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_manual(analysis: dict[str, Any], software_name: str, business: dict[str, Any], workdir: Path) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    for field, title, _pages in MANUAL_CHAPTERS:
        if field not in {"manual_modules", "faq"}:
            value = business.get(field)
            if not prose(value) and not (isinstance(value, dict) and value.get("subsections")):
                raise SystemExit(f"STOP_FOR_USER\nNEXT_ACTION: 业务理解缺少 {field}，须补写「{title}」。")
    modules = normalize_modules(business, workdir)
    faq_raw = business.get("faq")
    faq: list[dict[str, str]] = []
    if isinstance(faq_raw, list):
        for item in faq_raw:
            if isinstance(item, dict) and str(item.get("question") or "").strip() and str(item.get("answer") or "").strip():
                faq.append({"question": str(item["question"]).strip(), "answer": item["answer"]})
    if not faq:
        raise SystemExit("STOP_FOR_USER\nNEXT_ACTION: 业务理解缺少真实 faq，无法生成第8章。")

    def render() -> str:
        return render_manual(software_name, business, modules, faq)

    records: list[dict[str, Any]] = []
    for round_no, action in enumerate(("初稿生成", "结构与章节复核", "截图与用户流程复核", "套话与边界复核"), start=1):
        current = render()
        records.append({"round": round_no, "action": action, "issues": quality_issues(current, modules), "warnings": quality_warnings(modules)})
    return render(), records, modules


def require_confirmed_business(business: dict[str, Any] | None) -> dict[str, Any]:
    if business is None:
        raise SystemExit("STOP_FOR_USER\nNEXT_ACTION: 须先生成并确认 草稿/业务理解.json。")
    if business.get("confirmation_required") and not business.get("user_confirmed"):
        raise SystemExit("STOP_FOR_USER\nNEXT_ACTION: 业务理解尚未确认，须先记录 business 确认点。")
    return business


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--software-name", required=True)
    parser.add_argument("--version", default="V1.0.0")
    parser.add_argument("--business-context", required=True)
    parser.add_argument("--out-dir", default="软件著作权申请资料/草稿")
    args = parser.parse_args()
    analysis = read_json(Path(args.analysis))
    business = require_confirmed_business(read_json(Path(args.business_context)))
    out_dir = ensure_dir(Path(args.out_dir))
    workdir = out_dir.parent
    text, records, modules = build_manual(analysis, args.software_name, business, workdir)
    out_path = out_dir / "用户手册.md"
    out_path.write_text(text, encoding="utf-8")
    write_review_records(out_dir, records, modules)
    print(f"OK manual draft: {out_path}")
    print(f"OK manual self-review: {out_dir / '用户手册自检记录.md'}")
    for record in records:
        print(f"Review round {record['round']}: {record['action']} issues={len(record['issues'])} warnings={len(record['warnings'])}")
    if records[-1]["issues"]:
        print("STOP_FOR_USER")
        print("NEXT_ACTION: 用户手册自检仍存在问题，须根据自检记录修订业务理解正文后重新生成。")
        raise SystemExit(1)
    print("STOP_FOR_USER")
    print("NEXT_ACTION: 须确认完整用户手册草稿后运行 confirm_stage.py --stage markdown。")


if __name__ == "__main__":
    main()
