#!/usr/bin/env python3
"""Collect project evidence and write a model-authored business context."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common import ensure_dir, iter_project_files, read_json, read_text, rel, write_json


DOC_EXTS = {".md", ".txt", ".rst", ".adoc"}
MAX_DOC_CHARS = 80_000
MAX_DOCS = 40


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_md(text: str) -> str:
    text = re.sub(r"`{3}.*?`{3}", " ", text, flags=re.S)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"[>#*_`|]", " ", text)
    return normalize_space(text)


def skip_doc(path: Path, project: Path) -> bool:
    r = rel(path, project).lower()
    skip_parts = (
        "node_modules",
        ".git/",
        "dist/",
        "build/",
        ".next/",
        "coverage/",
        "软件著作权申请资料",
    )
    return any(part in r for part in skip_parts)


def extract_headings(text: str, limit: int = 24) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        clean = line.strip()
        if clean.startswith("#"):
            title = clean.lstrip("#").strip()
            if title and title not in headings:
                headings.append(title[:120])
        if len(headings) >= limit:
            break
    return headings


def extract_opening(text: str, limit: int = 900) -> str:
    clean = strip_md(text)
    return clean[:limit].strip()


def collect_documents(project: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for path in iter_project_files(project, DOC_EXTS):
        if skip_doc(path, project):
            continue
        try:
            text = read_text(path, limit=MAX_DOC_CHARS)
        except Exception:
            continue
        if not text.strip():
            continue
        docs.append(
            {
                "path": rel(path, project),
                "size": path.stat().st_size,
                "headings": extract_headings(text),
                "opening": extract_opening(text),
            }
        )
    docs.sort(key=lambda item: (item["path"].count("/"), item["path"]))
    return docs[:MAX_DOCS]


def collect_code_evidence(analysis: dict[str, Any]) -> dict[str, Any]:
    source = analysis.get("source") or {}
    categorized = source.get("categorized_files") or {}
    return {
        "project_name": analysis.get("project_name"),
        "software_name_candidate": analysis.get("software_name_candidate"),
        "frameworks": analysis.get("frameworks") or [],
        "language": analysis.get("language"),
        "routes": analysis.get("routes") or [],
        "feature_name_candidates": analysis.get("feature_candidates") or [],
        "entry_files": categorized.get("entry") or [],
        "page_files": categorized.get("page") or [],
        "component_files": categorized.get("component") or [],
        "api_files": categorized.get("api") or [],
        "run_command_candidates": analysis.get("run_command_candidates") or [],
        "package": analysis.get("package") or {},
    }


def build_evidence(project: Path, analysis: dict[str, Any], software_name: str, web_notes: str) -> dict[str, Any]:
    return {
        "software_name": software_name,
        "project_root": str(project.resolve()),
        "instruction": (
            "本文件仅收集证据，不决定行业、功能或手册结构。"
            "须由模型阅读上述证据及必要的项目源码后，另行编写业务理解模型稿。"
        ),
        "documents": collect_documents(project),
        "code_evidence": collect_code_evidence(analysis),
        "external_research_notes": web_notes,
    }


def write_evidence_md(path: Path, evidence: dict[str, Any]) -> None:
    lines = [
        "# 业务理解证据",
        "",
        f"- 软件名称：{evidence['software_name']}",
        f"- 项目目录：`{evidence['project_root']}`",
        "",
        "本文件仅列出可供研判的项目证据，不代表最终申报口径。",
        "应阅读哪些文档、抽取哪些功能、采用何种用户手册结构，须由模型自行判断。",
        "",
        "## 代码与页面证据",
        "",
    ]
    code = evidence["code_evidence"]
    for key in ("frameworks", "language", "routes", "feature_name_candidates", "entry_files", "page_files", "component_files", "api_files"):
        value = code.get(key)
        if value:
            lines.append(f"- {key}：{value}")
    lines.extend(["", "## 文档证据", ""])
    for doc in evidence["documents"]:
        lines.extend(
            [
                f"### {doc['path']}",
                "",
                f"- 大小：{doc['size']} bytes",
                f"- 标题线索：{'；'.join(doc['headings']) if doc['headings'] else '无'}",
                "",
                doc["opening"],
                "",
            ]
        )
    if evidence.get("external_research_notes"):
        lines.extend(["## 外部调研摘要", "", evidence["external_research_notes"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_model_template(path: Path, evidence: dict[str, Any]) -> None:
    template = {
        "software_name": evidence["software_name"],
        "product_positioning": "",
        "industry": "",
        "target_users": [],
        "core_value": "",
        "business_features": [],
        "business_feature_details": {},
        "operation_flow": [],
        "application_purpose": "",
        "main_functions": "",
        "technical_characteristics": "",
        "software_technical_option": "应用软件",
        "software_category": "应用软件",
        "manual_function_overview": [
            "第1章正文：先总览软件定位、目标用户和业务范围，再按总分关系介绍主要功能。",
        ],
        "manual_installation_config": {
            "paragraphs": [
                "第2章正文：依据真实项目说明安装方式、运行依赖、配置项、启动方式和配置完成后的可见结果。",
            ],
            "requirements": {
                "headers": ["项目", "要求"],
                "rows": [["运行环境", "按项目实际证据填写"]],
            },
        },
        "manual_modules": [
            {
                "title": "真实页面或核心流程名称",
                "body": [
                    "该模块正文第一段，由模型依据真实项目证据撰写，说明功能用途、入口和用户可见内容。",
                    "该模块正文第二段，说明用户动作、规则、反馈和边界，去除空白后通常为 120 至 220 字，复杂模块不超过 400 字。",
                ],
                "evidence": ["页面、路由、组件、README 或需求文档路径"],
                "purpose": "该页面或流程在当前软件中的用途。",
                "usage": "用户在什么业务场景下会使用该页面，正在处理什么具体事务。",
                "entry": "用户从哪里进入该页面或流程。",
                "visible_elements": ["用户实际能看到的输入框、按钮、列表、状态或结果区域"],
                "operation_steps": ["按真实页面顺序描述用户动作，不得写入代码实现。"],
                "validation_rules": ["输入限制、必填项、额度、权限、异常提示等规则。无相应内容时留空数组。"],
                "feedback": ["操作完成后用户能看到的结果、提示或状态变化。"],
                "screenshot": "截图预留说明",
                "boundary": ["可预见的边界情形及软件的实际表现，例如依赖数据缺失时界面的显示内容、前置条件未满足时仍可使用的功能、超出额度时的处置方式。无相应内容时留空数组。"],
            }
        ],
        "operation_flow": ["第4章正文：以一个或多个真实业务流程串起入口、关键操作、结果和产物。"],
        "manual_usage_notes": ["第5章正文：记录真实运行限制、数据边界、依赖问题和可执行的排查步骤。"],
        "faq": [
            {"question": "按当前软件真实使用场景填写常见问题", "answer": "给出面向普通用户的处理方法。"}
        ],
        "design_background": {
            "paragraphs": ["设计说明书第1章正文：说明项目背景、业务痛点、建设目标和适用边界。"]
        },
        "design_architecture": {
            "paragraphs": ["设计说明书第2章总述：说明系统总体架构、组件关系和数据流向。"],
            "subsections": [
                {"title": "架构设计", "paragraphs": ["说明真实模块、部署形态和关键技术边界。"]},
                {"title": "接口设计", "paragraphs": ["说明真实接口、调用方、输入输出和错误处理。"]},
                {"title": "数据库设计", "paragraphs": ["说明真实数据存储、主要实体、字段关系和一致性策略。"]},
            ],
        },
        "design_functions": {
            "paragraphs": ["设计说明书第3章总述：说明系统整体功能链路、主要功能域之间的关系，以及输入如何逐步形成结果。"],
            "subsections": [
                {"title": "真实功能域名称", "paragraphs": [
                    "第1段：交代功能目标、使用者或调用方、入口与前置条件，并点明与上游功能的关系。",
                    "第2段：依据真实代码说明输入数据与校验、关键处理步骤、状态变化和调用的服务或组件。",
                    "第3段：说明输出结果、展示或持久化位置、异常与边界处理，以及与后续功能的衔接；不存在的环节不编造。",
                ]}
            ],
        },
        "design_use_cases": {
            "paragraphs": ["设计说明书第4章总述：选择典型功能说明参与者、前置条件、操作步骤、结果和异常分支。"],
            "subsections": [
                {"title": "典型功能用例名称", "paragraphs": ["说明参与者、前置条件、操作步骤、正常结果和异常分支。"]}
            ],
        },
        "design_flow_scenarios": {
            "paragraphs": ["设计说明书第5章正文：描述一个典型流程及其应用场景，串联入口、处理和结果。"]
        },
        "model_review_notes": [
            "用户手册固定五章，顺序为系统功能概述、软件安装与配置、软件使用说明、典型使用流程总结、使用注意事项与常见问题。",
            "manual_modules 只用于第3章；模块正文由模型依据真实入口、动作、规则、反馈、边界和用户截图撰写，脚本只负责排序、图注、排版和校验。",
            "设计说明书固定包含背景、系统架构设计、系统功能概述、系统关键用例描述、典型流程与应用场景；系统架构设计至少说明架构、接口和数据库。",
            "设计说明书第3章每个功能小节写成有因果关系的具体段落：先写职责与入口，再写输入、规则和处理过程，最后写结果、状态、异常和功能衔接；所有细节要能回溯到源码或项目文档，不用通用套话凑篇幅。",
            "缺少真实证据时保留待补信息并停止，不得用模板事实替代项目事实。",
        ],
    }
    write_json(path, template)


def load_model_context(path: Path) -> dict[str, Any]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise SystemExit(f"Invalid model context JSON: {path}")
    return data


def required_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise SystemExit(f"Model context field must be a list: {field}")
    items = [str(item).strip() for item in value if str(item).strip()]
    if not items:
        raise SystemExit(f"Model context field cannot be empty: {field}")
    return items


def required_text(data: dict[str, Any], field: str) -> str:
    value = str(data.get(field) or "").strip()
    if not value:
        raise SystemExit(f"Model context field cannot be empty: {field}")
    return value


def normalize_model_context(model: dict[str, Any], evidence: dict[str, Any], web_notes: str) -> dict[str, Any]:
    features = required_list(model.get("business_features"), "business_features")
    details = model.get("business_feature_details") or {}
    if not isinstance(details, dict):
        raise SystemExit("Model context field must be an object: business_feature_details")
    missing = [feature for feature in features if not str(details.get(feature) or "").strip()]
    if missing:
        raise SystemExit("Model context missing feature details: " + "、".join(missing[:12]))
    function_overview = model.get("manual_function_overview") or []
    if not isinstance(function_overview, list) or not any(str(item).strip() for item in function_overview):
        raise SystemExit("Model context field cannot be empty: manual_function_overview")
    installation = model.get("manual_installation_config")
    if isinstance(installation, dict):
        installation_paragraphs = installation.get("paragraphs") or installation.get("body") or []
        if not isinstance(installation_paragraphs, list):
            installation_paragraphs = [installation_paragraphs]
    else:
        installation_paragraphs = installation or []
        installation = {"paragraphs": installation_paragraphs}
    if not any(str(item).strip() for item in installation_paragraphs):
        raise SystemExit("Model context field cannot be empty: manual_installation_config")
    manual_modules = model.get("manual_modules") or []
    if manual_modules and not isinstance(manual_modules, list):
        raise SystemExit("Model context field must be a list: manual_modules")
    if not manual_modules:
        raise SystemExit("Model context field cannot be empty: manual_modules")
    for index, module in enumerate(manual_modules, start=1):
        if not isinstance(module, dict):
            raise SystemExit(f"manual_modules item {index} must be an object")
        title = str(module.get("title") or module.get("feature") or "").strip()
        for field in ("purpose", "usage", "entry", "operation_steps", "feedback", "body"):
            value = module.get(field)
            if field == "usage" and not str(value or "").strip():
                value = module.get("usage_scenario")
            if isinstance(value, list):
                missing_value = not any(str(item).strip() for item in value)
            else:
                missing_value = not str(value or "").strip()
            if missing_value:
                raise SystemExit(f"manual_modules item {index} ({title or 'untitled'}) missing field: {field}")
    operation_flow = required_list(model.get("operation_flow"), "operation_flow")
    usage_notes = required_list(model.get("manual_usage_notes"), "manual_usage_notes")
    faq = model.get("faq") or []
    if faq and not isinstance(faq, list):
        raise SystemExit("Model context field must be a list: faq")
    if not faq:
        raise SystemExit("Model context field cannot be empty: faq")
    design_fields = (
        "design_background",
        "design_architecture",
        "design_functions",
        "design_use_cases",
        "design_flow_scenarios",
    )
    for field in design_fields:
        value = model.get(field)
        if not isinstance(value, (dict, list, str)):
            raise SystemExit(f"Model context field has invalid type: {field}")
        if isinstance(value, dict):
            body = value.get("paragraphs") or value.get("body") or value.get("overview")
        else:
            body = value
        if isinstance(body, list):
            present = any(str(item).strip() for item in body)
        else:
            present = bool(str(body or "").strip())
        if not present and not (isinstance(value, dict) and value.get("subsections")):
            raise SystemExit(f"Model context field cannot be empty: {field}")
    context = {
        "software_name": evidence["software_name"],
        "business_understanding_required": True,
        "source_documents": [{"path": doc["path"], "size": doc["size"]} for doc in evidence["documents"]],
        "project_evidence_file": "业务理解证据.md",
        "product_positioning": required_text(model, "product_positioning"),
        "industry": required_text(model, "industry"),
        "target_users": required_list(model.get("target_users"), "target_users"),
        "core_value": required_text(model, "core_value"),
        "business_features": features,
        "business_feature_details": {feature: str(details.get(feature)).strip() for feature in features},
        "application_purpose": required_text(model, "application_purpose"),
        "main_functions": required_text(model, "main_functions"),
        "technical_characteristics": required_text(model, "technical_characteristics"),
        "software_technical_option": str(model.get("software_technical_option") or "应用软件"),
        "software_category": str(model.get("software_category") or "应用软件"),
        "manual_function_overview": [str(paragraph).strip() for paragraph in function_overview if str(paragraph).strip()],
        "manual_installation_config": installation,
        "manual_modules": manual_modules,
        "operation_flow": operation_flow,
        "manual_usage_notes": usage_notes,
        "faq": faq,
        "design_background": model.get("design_background"),
        "design_architecture": model.get("design_architecture"),
        "design_functions": model.get("design_functions"),
        "design_use_cases": model.get("design_use_cases"),
        "design_flow_scenarios": model.get("design_flow_scenarios"),
        "model_authored": True,
        "external_research_notes": web_notes,
        "confirmation_required": True,
        "user_confirmed": False,
        "confirmation_stage": "business",
        "next_action": "须确认 草稿/业务理解.md 中的软件用途、行业、目标用户、核心功能、手册结构与申请口径。确认后运行 confirm_stage.py --stage business。",
        "review_notes": [
            "确认模型判定的行业领域、目标用户与主要功能是否符合实际申报口径。",
            "确认用户手册结构是否按真实页面与流程展开，而非套用抽象功能列表。",
        ],
    }
    return context


def write_context_md(path: Path, context: dict[str, Any]) -> None:
    lines = [
        "# 业务理解",
        "",
        f"- 软件名称：{context['software_name']}",
        f"- 产品定位：{context['product_positioning']}",
        f"- 面向领域 / 行业：{context['industry']}",
        f"- 核心价值：{context['core_value']}",
        f"- 证据文件：`{context['project_evidence_file']}`",
        "",
        "## 目标用户",
        "",
    ]
    lines.extend(f"- {item}" for item in context["target_users"])
    lines.extend(["", "## 主要业务功能", ""])
    lines.extend(f"- {item}" for item in context["business_features"])
    lines.extend(["", "## 功能说明", ""])
    for item in context["business_features"]:
        lines.append(f"- {item}：{context['business_feature_details'].get(item, '')}")
    lines.extend(["", "## 典型操作流程", ""])
    lines.extend(f"{i}. {item}" for i, item in enumerate(context["operation_flow"], start=1))
    lines.extend(
        [
            "",
            "## 用户手册章节构成",
            "",
            "用户手册固定为五章，顺序为：系统功能概述、软件安装与配置、软件使用说明、典型使用流程总结、使用注意事项与常见问题。",
            "",
        ]
    )
    lines.extend(
        f"{index}. {title}"
        for index, title in enumerate(
            ("系统功能概述", "软件安装与配置", "软件使用说明", "典型使用流程总结", "使用注意事项与常见问题"),
            start=1,
        )
    )
    if context.get("manual_modules"):
        lines.extend(["", "## 用户手册页面/流程模块", ""])
        for i, module in enumerate(context["manual_modules"], start=1):
            if not isinstance(module, dict):
                lines.append(f"{i}. {module}")
                continue
            title = module.get("title") or module.get("feature") or f"模块 {i}"
            usage = module.get("usage") or module.get("usage_scenario") or ""
            entry = module.get("entry") or ""
            steps = module.get("operation_steps") or module.get("steps") or []
            lines.append(f"{i}. {title}" + (f"：{entry}" if entry else ""))
            if usage:
                lines.append(f"   - 使用场景：{usage}")
            if steps:
                lines.append(f"   - 操作要点：{'；'.join(str(item) for item in steps)}")
    lines.extend(
        [
            "",
            "## 软件设计说明书结构",
            "",
            "设计说明书固定包含背景、系统架构设计、系统功能概述、系统关键用例描述、典型流程与应用场景。",
            "系统架构设计至少包含架构设计、接口设计和数据库设计，其他小节按项目真实需要补充。",
            "",
            "",
            "## 申请表建议口径",
            "",
            f"- 开发目的：{context['application_purpose']}",
            f"- 软件的主要功能：{context['main_functions']}",
            f"- 技术特点：{context['technical_characteristics']}",
            f"- 软件的技术特点选项：{context['software_technical_option']}",
            f"- 软件分类：{context['software_category']}",
            "",
            "## 证据来源",
            "",
        ]
    )
    lines.extend(f"- `{item['path']}`" for item in context["source_documents"])
    lines.extend(["", "## 待确认", ""])
    lines.extend(f"- {item}" for item in context["review_notes"])
    lines.extend(
        [
            "",
            "```text",
            "STOP_FOR_USER",
            f"NEXT_ACTION: {context['next_action']}",
            "```",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--software-name", required=True)
    parser.add_argument("--out-dir", default="软件著作权申请资料/草稿")
    parser.add_argument("--web-notes", help="Optional plain-text notes from external/competitor research")
    parser.add_argument("--model-context", help="Model-authored business context JSON")
    args = parser.parse_args()

    project = Path(args.project)
    analysis = read_json(Path(args.analysis))
    web_notes = read_text(Path(args.web_notes)) if args.web_notes else ""
    out_dir = ensure_dir(Path(args.out_dir))

    evidence = build_evidence(project, analysis, args.software_name, web_notes)
    write_json(out_dir / "业务理解证据.json", evidence)
    write_evidence_md(out_dir / "业务理解证据.md", evidence)

    if not args.model_context:
        write_model_template(out_dir / "业务理解模型稿模板.json", evidence)
        print(f"OK business evidence: {out_dir / '业务理解证据.md'}")
        print(f"OK model template: {out_dir / '业务理解模型稿模板.json'}")
        print("NEXT_ACTION: 须先阅读业务理解证据与项目源码，自行编写业务理解模型稿 JSON，再以 --model-context 生成 业务理解.md 与 业务理解.json。")
        return

    model = load_model_context(Path(args.model_context))
    context = normalize_model_context(model, evidence, web_notes)
    write_json(out_dir / "业务理解.json", context)
    write_context_md(out_dir / "业务理解.md", context)
    print(f"OK business context: {out_dir / '业务理解.md'}")
    print(f"Features: {len(context['business_features'])}")
    print("STOP_FOR_USER")
    print(f"NEXT_ACTION: {context['next_action']}")


if __name__ == "__main__":
    main()
