#!/usr/bin/env python3
"""Collect project evidence and write a model-authored business context."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common import ensure_dir, iter_project_files, read_json, read_text, rel, write_json
from document_structure import DESIGN_CHAPTERS, MANUAL_CHAPTERS, prose, section_markdown


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
        "document_page_plan": {
            "target_pages_each": 60,
            "front_matter_pages_each": 2,
            "manual": [{"field": field, "title": title, "planned_pages": pages} for field, title, pages in MANUAL_CHAPTERS],
            "design": [{"field": field, "title": title, "planned_pages": pages} for field, title, pages in DESIGN_CHAPTERS],
            "note": "分章预算可按证据调整，正文合计各58页；最终页数必须重新排版核验。",
        },
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
        "manual_basics": {"paragraphs": ["第3章：说明界面布局、导航、术语、数据准备、通用操作和使用前检查。"], "subsections": []},
        "manual_data_management": {"paragraphs": ["第5章：依据实际能力说明数据导入、查看、筛选、编辑、导出、保存和历史记录；无某项能力时说明真实数据处理边界。"], "subsections": []},
        "manual_modules": [
            {
                "title": "真实页面或核心流程名称",
                "body": [
                    "该模块正文第一段，由模型依据真实项目证据撰写，说明功能用途、入口和用户可见内容。",
                    "该模块正文说明使用场景、前置条件、输入示例、操作步骤、结果解读、异常与限制；依据功能复杂度设置以下子节，无400字上限。",
                ],
                "subsections": [
                    {"title": "使用准备与输入要求", "paragraphs": ["说明有证据的前置条件、关键字段、必填项、格式约束及具体输入示例。"]},
                    {"title": "操作过程与结果", "paragraphs": ["按真实界面解释每步操作、状态变化、成功判据和结果解读，避免重复模块总览。"]},
                    {"title": "异常处理与功能衔接", "paragraphs": ["说明真实错误提示、排查方法、恢复操作、边界，以及后续功能入口。"]},
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
        "operation_flow": {"paragraphs": ["第6章：按真实任务组织多个完整案例，串联准备材料、入口、操作、阶段结果和最终产物。"], "subsections": []},
        "manual_usage_notes": {"paragraphs": ["第7章：说明真实限制、依赖条件、数据要求、操作风险与恢复方法。"], "subsections": []},
        "faq": [
            {"question": "按当前软件真实使用场景填写常见问题", "answer": "给出面向普通用户的处理方法。"}
        ],
        "design_background": {
            "paragraphs": ["第1章项目背景与设计目标：说明应用背景、实际问题、建设目标、范围和约束。"]
        },
        "design_requirements": {"paragraphs": ["第2章：根据源码和需求证据说明参与者、业务需求、功能需求、输入输出要求和运行条件。"], "subsections": []},
        "design_architecture": {
            "paragraphs": ["第3章总述：说明系统分层、组件协作、部署关系和整体数据流。"],
            "subsections": [
                {"title": "架构设计", "paragraphs": ["说明真实模块、部署形态和关键技术边界。"]},
                {"title": "组件协作与数据流", "paragraphs": ["说明任务经过各组件的路径、依赖关系和数据去向；详细接口和存储分别写入第5、6章。"]},
            ],
        },
        "design_functions": {
            "paragraphs": ["第4章总述：说明系统整体功能链路、功能域关系及输入如何逐步形成结果，再逐模块写详细设计。"],
            "subsections": [
                {"title": "真实功能域名称", "paragraphs": [
                    "第1段：依据项目证据说明功能职责、使用者或调用方、入口、前置条件，以及与上游功能的关系。",
                    "第2段：具体说明输入对象和来源、关键字段、校验规则、权限或配置约束；未实现的约束不编造。",
                    "第3段：按实际执行顺序解释核心处理、条件分支、调用的组件或接口、数据转换与状态变化。",
                    "第4段：说明输出结果、界面反馈、持久化或导出产物、数据去向，以及下游功能如何使用它们。",
                    "第5段：说明源码中可核实的异常、空数据、重复操作、失败恢复和适用边界；不存在的机制不补写。",
                    "第6段（按需）：用项目具体场景解释机制协同，复杂模块继续拆分子节；用例步骤放第10章。",
                ]}
            ],
        },
        "design_interfaces": {"paragraphs": ["第5章：列出真实外部接口、模块调用、调用方、参数、返回值、错误处理和交互时序；没有网络API时说明内部函数或命令行接口。"], "subsections": []},
        "design_data": {"paragraphs": ["第6章：说明真实数据对象、实体关系、字段、约束、文件组织、读写路径和生命周期；没有数据库时写实际文件或内存存储。"], "subsections": []},
        "design_processing": {"paragraphs": ["第7章：解释源码中的核心算法、处理步骤、条件分支、状态转换及任务调度；没有自定义算法时写真实处理流程。"], "subsections": []},
        "design_reliability": {"paragraphs": ["第8章：说明有实现证据的输入校验、权限、异常、日志、重试与恢复；明确未实现部分的边界。"], "subsections": []},
        "design_deployment": {"paragraphs": ["第9章：说明运行组件、环境配置、启动顺序、资源依赖及维护机制。"], "subsections": []},
        "design_use_cases": {
            "paragraphs": ["第10章：选择真实关键功能用例，最后用跨模块典型流程与应用场景串联系统协作。"],
            "subsections": [
                {"title": "典型功能用例名称", "paragraphs": ["说明参与者、触发条件、前置条件、正常流程、备选与异常分支、后置条件及数据对象。"]},
                {"title": "典型流程与应用场景", "paragraphs": ["串联多个模块的入口、输入、处理、阶段产物和最终结果，解释协作关系。"]},
            ],
        },
        "model_review_notes": [
            "用户手册固定八章，manual_modules用于第4章，图号为图4-x；按使用者完成任务的路径展开子节、字段表、步骤、截图及结果解读。",
            "优先使用真实截图，缺图时询问用户是否生成有证据的简洁界面；图注只写功能或页面名称，生成方式保留在截图清单。",
            "设计说明书固定十章；接口、数据与存储、核心处理、安全可靠性、部署运行独立成章，关键用例与典型场景放最后。",
            "第4章各模块通常至少展开4–6段，复杂模块设子节，说明职责、输入约束、顺序处理、状态、输出与数据去向、异常边界和协作关系，逐项对照真实实现。",
            "两份文档各60页，含封面与单页目录；章节预算见document_structure.py和撰写规则。先按证据规划58页正文，再按排版结果补写或压缩。禁止空白页、重复段落、放大字号行距或拉伸图片凑页。",
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
    if not prose(function_overview) and not (isinstance(function_overview, dict) and function_overview.get("subsections")):
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
    for field in ("manual_basics", "manual_data_management", "operation_flow", "manual_usage_notes"):
        value = model.get(field)
        if not prose(value) and not (isinstance(value, dict) and value.get("subsections")):
            raise SystemExit(f"Model context field cannot be empty: {field}; 请按八章用户手册补全")
    operation_flow = model["operation_flow"]
    usage_notes = model["manual_usage_notes"]
    faq = model.get("faq") or []
    if faq and not isinstance(faq, list):
        raise SystemExit("Model context field must be a list: faq")
    if not faq:
        raise SystemExit("Model context field cannot be empty: faq")
    design_fields = tuple(field for field, _title, _pages in DESIGN_CHAPTERS)
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
        "manual_function_overview": function_overview,
        "manual_installation_config": installation,
        "manual_modules": manual_modules,
        "manual_basics": model["manual_basics"],
        "manual_data_management": model["manual_data_management"],
        "operation_flow": operation_flow,
        "manual_usage_notes": usage_notes,
        "faq": faq,
        **{field: model[field] for field in design_fields},
        "document_schema_version": 6,
        "document_page_plan": model.get("document_page_plan") or {},
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
    lines.extend(section_markdown(context["operation_flow"], "6"))
    lines.extend(
        [
            "",
            "## 用户手册章节构成",
            "",
            "用户手册固定八章，按用户操作组织内容；与设计说明书各须排版为60页（含封面与目录）。",
            "",
        ]
    )
    lines.extend(
        f"{index}. {title}"
        for index, title in enumerate(
            tuple(title for _field, title, _pages in MANUAL_CHAPTERS),
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
            "设计说明书固定十章：" + "、".join(title for _field, title, _pages in DESIGN_CHAPTERS) + "。",
            "正文规划58页；实际页数须通过Word或LibreOffice重新排版核验。",
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
