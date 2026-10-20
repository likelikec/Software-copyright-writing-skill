---
name: software-copyright-materials
description: >
  从真实项目生成并校验中国计算机软件著作权登记材料，包括申请表信息、代码鉴别材料、
  五章用户手册和软件设计说明书。Generate reviewable DOCX materials from a real
  software project. 不适用于专利、商标及非软件类作品著作权登记。
license: MIT
metadata:
  short-description: 生成并校验中国软件著作权申请材料
  author: suling-fun
  maintainer: likelikec
  version: "5.3.0"
  repository: https://github.com/likelikec/Software-copyright-writing-skill
  upstream: https://github.com/Fokkyp/SoftwareCopyright-Skill
  upstream-version: "1.3"
  provenance: 基于上游 Skill 大范围修正、增补与重构
---

# 软著申请资料生成

本 skill 只负责阅读真实项目、生成草稿与正式 DOCX、整理或生成用户手册插图和执行程序化验证。材料生成与验证完成后流程结束。

## 运行环境

- Python 3.10 或更高版本；优先使用当前项目的相对路径 `.venv/bin/python`（若存在），否则使用 `python3`。
- `python-docx` 是代码、用户手册和设计说明书三类 Word 材料生成的必需依赖；申请表信息输出 TXT。
- `soffice` 与 `pypdf` 可自动核准用户手册目录页码；缺失时生成后须在 Word 中更新目录并核对页码。
- 用户手册插图优先使用用户截图及用户文档/PPT 中可核实的界面截图；均无可用图片时，可经用户选择生成简洁静态界面示意图，截图需有真实功能证据。该选项需要 Chrome、Chromium 或 Edge。

所有命令中的 `${SKILL_DIR}` 指本文件所在目录的绝对路径。开始前执行：

```bash
export SKILL_DIR=<本 SKILL.md 所在目录的绝对路径>
test -f "${SKILL_DIR}/scripts/check_environment.py"
```

## 核心原则

- 所有业务事实、按钮文案、操作顺序、状态、数值和错误提示都必须能回溯到源码、项目文档或用户截图。
- 脚本只负责证据收集、字段校验、排版、装配和验证；模型负责行业判断、功能理解和所有叙述性正文。
- 申请表不包含“软件简称”。“开发目的”从宏观真实场景说明用途；“软件的技术特点”在 100 字内尽量具体说明技术机制和差异化特点。
- 申请表的本次默认申报口径详见 [references/application_fields.md](references/application_fields.md)：原创、未发表、著作权人南京大学、全部权利、原始取得及用户指定的硬件和开发环境。编程语言、全量源程序量和额外支持软件仍根据项目证据填写；正式生成前核对固定值是否适用于目标项目。
- 用户手册固定五章：系统功能概述、软件安装与配置、软件使用说明、典型使用流程总结、使用注意事项与常见问题。
- 代码 Word 命名为 `<软件全称>-<版本号>-源程序鉴别材料.docx`；正文使用 Courier New 六号字（7.5 磅），长行在保留源码字符的前提下换行，超出单页容量时停止生成。
- 用户手册第一页为宋体一号居中封面，第二页为五章目录，正文从第三页开始。
- 软件设计说明书使用内置模板的首页、目录和样式，正文由模型依据项目证据撰写，输出完整 DOCX。
- 正式材料统一使用用户已确认的“软件全称”；本次申请表版本号固定为 `V1.0.0`，其余材料与之保持一致。
- 创建任何文件前先读取 [references/output_directory_rules.md](references/output_directory_rules.md)。

## 人工确认闸门

必须停止并等待用户确认的阶段：`environment`（仅在环境不全时）、`project`、`business`、`code-selection`、`screenshot-method`、`application-fields`、`markdown`。用户确认后先记录：

```bash
python3 ${SKILL_DIR}/scripts/confirm_stage.py \
  --workdir 软件著作权申请资料 --stage <阶段名> --note "<用户确认内容>"
```

先检查项目现有截图、用户提供的截图及文档/PPT。无可用截图时，询问用户在 `generated-ui`（生成简单界面示意图）和 `skip`（保留截图预留位）之间选择；有可用截图时记录 `user-supplied`。不得把生成的示意图称为实际运行截图。

## 工作流

### 1. 环境检查

在目标项目根目录运行：

```bash
python3 ${SKILL_DIR}/scripts/check_environment.py --out-dir 软件著作权申请资料
```

若 `python-docx` 不可用，停止正式材料生成，先安装该依赖。其他缺失能力按环境检查结果处理。

### 2. 项目定位与分析

确定唯一项目根目录。存在多个候选目录时停止并询问用户。随后运行：

```bash
python3 ${SKILL_DIR}/scripts/analyze_project.py \
  --project <项目目录> --out 软件著作权申请资料/analysis/project.json
```

### 3. 业务理解

先收集证据：

```bash
python3 ${SKILL_DIR}/scripts/generate_business_context.py \
  --project <项目目录> \
  --analysis 软件著作权申请资料/analysis/project.json \
  --software-name "<软件全称>" \
  --out-dir 软件著作权申请资料/草稿
```

模型阅读证据和必要源码后生成 `草稿/业务理解.json`，至少补全申请表字段、用户手册五章字段和设计说明书五部分字段。字段契约详见 [references/business_understanding_rules.md](references/business_understanding_rules.md)。生成后停止，确认 `business` 后继续。

### 4. 申请表信息

核对软件全称、版本号、日期及本次指定的著作权人和环境字段后运行：

```bash
python3 ${SKILL_DIR}/scripts/generate_application_info.py \
  --analysis 软件著作权申请资料/analysis/project.json \
  --code-manifest 软件著作权申请资料/草稿/代码提取清单.json \
  --business-context 软件著作权申请资料/草稿/业务理解.json \
  --software-name "<软件全称>" --version "V1.0.0" \
  --out-dir 软件著作权申请资料/草稿
```

生成 `草稿/申请表信息.md` 后停止，补全字段并记录 `application-fields`。

### 5. 代码材料

先生成候选清单并由用户确认：

```bash
python3 ${SKILL_DIR}/scripts/propose_code_selection.py \
  --project <项目目录> --analysis 软件著作权申请资料/analysis/project.json \
  --out-dir 软件著作权申请资料/草稿
python3 ${SKILL_DIR}/scripts/confirm_stage.py \
  --workdir 软件著作权申请资料 --stage code-selection --note "<用户确认内容>"
```

确认后运行 `extract_code_material.py` 生成代码 Markdown。代码材料必须来自用户确认的真实源码文件。

### 6. 用户手册插图

先核对项目截图、`用户截图/`，以及用户提供文档/PPT 中是否有可复用的真实界面截图。提取文档/PPT 图片时保留原文件和页码/幻灯片号作为来源。找不到可用图片时，向用户提供“生成简单界面示意图”和“暂不配图”两个选项，并说明示意图依据代码功能制作，不代表软件实际运行界面。记录用户选择：

```bash
python3 ${SKILL_DIR}/scripts/confirm_stage.py \
  --workdir 软件著作权申请资料 --stage screenshot-method \
  --method <user-supplied|generated-ui|skip> --note "<用户选择>"
```

选择 `user-supplied` 时，将用户截图或从文档/PPT 提取并核对的图片放入 `软件著作权申请资料/用户截图/`，再运行：

```bash
python3 ${SKILL_DIR}/scripts/capture_screenshots.py \
  --manual-dir 软件著作权申请资料/用户截图 \
  --out-dir 软件著作权申请资料/截图
```

选择 `generated-ui` 时，只为第 3 章确实需要图示且无真实截图的功能制作简洁静态 HTML。每张图须列出项目源码或配置的证据路径，不编造项目没有的功能、数据、按钮或运行状态。把 HTML 和 `截图方案.json` 放在 `草稿/界面示意/`；方案格式为 `{"screenshots":[{"module":"与 manual_modules.title 完全一致","html":"草稿/界面示意/功能.html","caption":"功能界面示意","evidence":["相对项目根目录的源码路径"]}]}`。运行：

```bash
python3 ${SKILL_DIR}/scripts/capture_generated_ui.py \
  --workdir 软件著作权申请资料 --project <项目目录> \
  --plan 软件著作权申请资料/草稿/界面示意/截图方案.json
```

截图脚本把 PNG 和来源清单写入 `截图/`。手册图注必须保留“界面示意，非实际运行截图”字样。用户选 `skip` 时保留截图预留位。

### 7. 用户手册与设计说明书草稿

生成五章用户手册：

```bash
python3 ${SKILL_DIR}/scripts/generate_user_manual_draft.py \
  --analysis 软件著作权申请资料/analysis/project.json \
  --business-context 软件著作权申请资料/草稿/业务理解.json \
  --software-name "<软件全称>" --version "V1.0.0" \
  --out-dir 软件著作权申请资料/草稿
```

生成设计说明书 Markdown 草稿：

```bash
python3 ${SKILL_DIR}/scripts/generate_design_spec.py \
  --business-context 软件著作权申请资料/草稿/业务理解.json \
  --software-name "<软件全称>" --version "V1.0.0" \
  --out-dir 软件著作权申请资料/草稿 --draft-only
```

设计说明书正文必须包括背景、系统架构设计（含架构、接口、数据库及项目需要的后续小节）、系统功能概述、系统关键用例描述、典型流程与应用场景。系统功能概述先总览功能域和协作链路，再按 [references/business_understanding_rules.md](references/business_understanding_rules.md) 为每个功能域写通常 4–6 段有证据的正文：定位与入口、输入和约束、核心处理与状态变化、输出与下游衔接、异常和边界。复杂度决定篇幅，不用套话凑字数，也不编造未实现的机制。正式 DOCX 由第 9 步在 Markdown 确认后生成，模板为 `assets/design_spec_template.docx`。

### 8. Markdown 草稿确认

检查申请表、代码材料、用户手册和设计说明书草稿：字段、名称、版本、行业、功能、章节、截图引用和设计内容都必须真实一致。确认后运行：

```bash
python3 ${SKILL_DIR}/scripts/confirm_stage.py \
  --workdir 软件著作权申请资料 --stage markdown --note "<用户确认内容>"
```

### 9. 正式 Word 生成

```bash
python3 ${SKILL_DIR}/scripts/build_docx_from_md.py \
  --workdir 软件著作权申请资料 \
  --software-name "<软件全称>" --version "V1.0.0"
```

输出 `正式资料/申请表信息.txt`、`<软件全称>-V1.0.0-源程序鉴别材料.docx`、`<软件全称>_用户手册.docx` 和 `<软件全称>-V1.0.0-软件设计说明书.docx`。用户手册封面、目录与正文由已确认的软件名称和版本号生成；设计说明书首页标题为“<软件全称>软件说明书”（宋体一号），版本号为 Times New Roman 二号。
用户手册目录在 `soffice` 与 `pypdf` 可用时自动核准页码；设计说明书目录在本机 Word 可用时自动更新。未自动更新时须在 Word 中更新目录并核对页码。正式交付包含一份 TXT 和三份 DOCX，不生成 PDF。

### 10. 程序化验证与交付

```bash
python3 ${SKILL_DIR}/scripts/verify_materials.py --workdir 软件著作权申请资料
python3 -m py_compile ${SKILL_DIR}/scripts/*.py
```

任何 `[FAIL]` 都必须修复后重跑。另按 [references/verification_checklist.md](references/verification_checklist.md) 对代码真实性、业务真实性、截图匹配度和设计说明书样例残留进行独立核对。全部通过后报告正式资料路径和关键页数，流程结束。
