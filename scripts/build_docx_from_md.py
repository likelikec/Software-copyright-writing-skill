#!/usr/bin/env python3
"""Build the final application TXT and three DOCX files from confirmed drafts."""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import struct
import subprocess
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

from common import CODE_LAYOUT, ensure_dir, read_json, safe_filename
from document_structure import DESIGN_CHAPTERS, MANUAL_CHAPTERS

try:
    from generate_design_spec import generate_design_docx
except Exception:  # pragma: no cover - surfaced by the preflight check below
    generate_design_docx = None  # type: ignore[assignment]

try:
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.enum.style import WD_STYLE_TYPE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Inches, Pt, RGBColor

    DOCX_AVAILABLE = True
except Exception:
    DOCX_AVAILABLE = False


BLACK_RGB = "000000"


def strip_markdown_links(text: str) -> str:
    text = re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    return text


def parse_application_lines(md_path: Path) -> tuple[list[str], list[str]]:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    fields = [line.strip() for line in lines if line.strip().startswith("➤")]
    warnings = [line for line in fields if "待用户确认" in line]
    return fields, warnings


def parse_application_field(md_path: Path, field_name: str) -> str:
    if not md_path.exists():
        return ""
    prefix = f"➤{field_name}："
    for line in md_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return ""


def application_version(draft_dir: Path) -> str:
    version = parse_application_field(draft_dir / "申请表信息.md", "版本号")
    if "待用户确认" in version:
        return ""
    return version


def application_software_name(draft_dir: Path) -> str:
    name = parse_application_field(draft_dir / "申请表信息.md", "软件全称")
    if "待用户确认" in name:
        return ""
    return name


def write_application_txt(draft_dir: Path, out_dir: Path) -> tuple[Path | None, list[str]]:
    md_path = draft_dir / "申请表信息.md"
    if not md_path.exists():
        return None, ["缺少草稿/申请表信息.md"]
    fields, warnings = parse_application_lines(md_path)
    if not fields:
        raise RuntimeError("申请表草稿缺少 ➤字段：无法生成申请表信息.txt")
    out_path = ensure_dir(out_dir) / "申请表信息.txt"
    out_path.write_text("\n".join(fields) + "\n", encoding="utf-8")
    return out_path, warnings


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return read_json(path)


def confirmation_issues(workdir: Path) -> list[str]:
    draft_dir = workdir / "草稿"
    issues: list[str] = []
    if generate_design_docx is None:
        issues.append("无法加载软件设计说明书生成器；请安装 python-docx 并检查脚本依赖")
    if not (Path(__file__).resolve().parent.parent / "assets" / "design_spec_template.docx").exists():
        issues.append("缺少软件设计说明书模板 assets/design_spec_template.docx")

    business = read_json_if_exists(draft_dir / "业务理解.json")
    if not business or not business.get("user_confirmed"):
        issues.append("业务理解尚未确认：须确认 草稿/业务理解.md 后记录 `business` 确认点")
    design_fields = tuple(field for field, _title, _pages in DESIGN_CHAPTERS)
    if business and not all(business.get(field) for field in design_fields):
        issues.append("业务理解缺少十章软件设计说明书字段；须按 business_understanding_rules.md 补全并重新确认")
    if business and not all(business.get(field) for field, _title, _pages in MANUAL_CHAPTERS):
        issues.append("业务理解缺少八章用户手册字段；须按 business_understanding_rules.md 补全并重新确认")

    selection = read_json_if_exists(draft_dir / "代码文件选择.json")
    if not selection or not selection.get("user_confirmed"):
        issues.append("代码文件选择尚未确认：须确认 草稿/代码文件选择.json 后记录 `code-selection` 确认点")

    screenshot = read_json_if_exists(workdir / "截图方式确认.json")
    if not screenshot.get("screenshot_method_confirmed"):
        issues.append("截图方式尚未确认：须先选定截图方式，再记录 `screenshot-method` 确认点")
    elif screenshot.get("screenshot_method") == "generated-ui":
        manifest = read_json_if_exists(workdir / "截图" / "截图清单.json")
        if manifest.get("method") != "generated-ui" or not manifest.get("screenshots"):
            issues.append("已选择生成界面示意图，但截图清单缺失或为空；须先运行 capture_generated_ui.py")

    app_md = draft_dir / "申请表信息.md"
    if app_md.exists():
        _, warnings = parse_application_lines(app_md)
        if warnings:
            issues.append("申请表信息仍包含「待用户确认」字段")
    else:
        issues.append("缺少 草稿/申请表信息.md")

    app_confirmation = read_json_if_exists(draft_dir / "申请表字段确认.json")
    if not app_confirmation.get("application_fields_confirmed"):
        issues.append("申请表字段尚未确认：须补全字段后记录 `application-fields` 确认点")

    markdown_confirmation = read_json_if_exists(draft_dir / "最终生成确认.json")
    if not markdown_confirmation.get("markdown_confirmed"):
        issues.append("Markdown 草稿尚未最终确认：须确认全部草稿后记录 `markdown` 确认点")

    return issues


def parse_code_pages(md_path: Path) -> list[tuple[int, list[str]]]:
    pages: list[tuple[int, list[str]]] = []
    current_no: int | None = None
    current_lines: list[str] = []
    in_fence = False

    for raw in md_path.read_text(encoding="utf-8").splitlines():
        page_match = re.match(r"^##\s+第\s*(\d+)\s*页", raw.strip())
        if page_match:
            if current_no is not None:
                pages.append((current_no, current_lines))
            current_no = int(page_match.group(1))
            current_lines = []
            in_fence = False
            continue
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if current_no is not None and in_fence:
            current_lines.append(raw)

    if current_no is not None:
        pages.append((current_no, current_lines))
    return pages


def wrap_code_line(line: str, max_columns: int = 98) -> list[str]:
    """Split a source line into visual rows without dropping source characters."""
    if not line:
        return [" "]
    rows: list[str] = []
    current: list[str] = []
    width = 0
    for char in line:
        char_width = (4 - width % 4) if char == "\t" else (2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1)
        if current and width + char_width > max_columns:
            rows.append("".join(current))
            current = []
            width = 0
            char_width = 4 if char == "\t" else char_width
        current.append(char)
        width += char_width
    if current:
        rows.append("".join(current))
    return rows


def set_run_font(run: Any, name: str, size_pt: float) -> None:
    run.font.name = name
    run.font.size = Pt(size_pt)
    try:
        run.font.color.rgb = RGBColor(0, 0, 0)
    except Exception:
        pass
    try:
        run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    except Exception:
        pass


def set_normal_font(document: Any, name: str = "SimSun", size_pt: float = 10.5) -> None:
    style = document.styles["Normal"]
    style.font.name = name
    style.font.size = Pt(size_pt)
    try:
        style.font.color.rgb = RGBColor(0, 0, 0)
    except Exception:
        pass
    try:
        style._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    except Exception:
        pass


def set_style_black(document: Any) -> None:
    for style_name in ("Normal", "Heading 1", "Heading 2", "Heading 3", "List Bullet", "List Number"):
        try:
            document.styles[style_name].font.color.rgb = RGBColor(0, 0, 0)
        except Exception:
            pass


def force_black_document(document: Any) -> None:
    set_style_black(document)
    containers = [document]
    for section in document.sections:
        containers.extend([section.header, section.footer])
    for container in containers:
        for paragraph in container.paragraphs:
            for run in paragraph.runs:
                try:
                    run.font.color.rgb = RGBColor(0, 0, 0)
                except Exception:
                    pass
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            try:
                                run.font.color.rgb = RGBColor(0, 0, 0)
                            except Exception:
                                pass


def configure_a4(document: Any) -> None:
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.17)
    section.right_margin = Cm(2.54)


def configure_code_a4(document: Any) -> None:
    # 数值一律取自 common.CODE_LAYOUT。
    section = document.sections[0]
    section.page_width = Cm(CODE_LAYOUT.page_width_cm)
    section.page_height = Cm(CODE_LAYOUT.page_height_cm)
    section.top_margin = Cm(CODE_LAYOUT.margin_top_cm)
    section.bottom_margin = Cm(CODE_LAYOUT.margin_bottom_cm)
    section.left_margin = Cm(CODE_LAYOUT.margin_left_cm)
    section.right_margin = Cm(CODE_LAYOUT.margin_right_cm)


def add_page_field(paragraph: Any) -> None:
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    result = OxmlElement("w:t")
    result.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")

    for element in (begin, instr, separate, result, end):
        run = paragraph.add_run()
        run._r.append(element)
        set_run_font(run, "SimSun", CODE_LAYOUT.header_font_size_pt)


def add_total_pages_field(paragraph: Any) -> None:
    """Insert a NUMPAGES field run, mirroring add_page_field()'s PAGE field.

    Used only by the operation manual header (via set_code_header's
    show_total_pages=True) to report the document's total page count.
    """
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instr.text = " NUMPAGES "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    result = OxmlElement("w:t")
    result.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")

    for element in (begin, instr, separate, result, end):
        run = paragraph.add_run()
        run._r.append(element)
        set_run_font(run, "SimSun", CODE_LAYOUT.header_font_size_pt)


def set_code_header(
    document: Any, software_name: str, version: str, show_total_pages: bool = False
) -> None:
    section = document.sections[0]
    section.header.is_linked_to_previous = False
    header = section.header
    header.paragraphs[0].text = "" if header.paragraphs else None

    # Build a two-column header: software name on the left, page number on the right.
    table = header.add_table(rows=1, cols=2, width=Cm(17.5))
    table.autofit = True
    left_cell = table.rows[0].cells[0]
    right_cell = table.rows[0].cells[1]

    left_para = left_cell.paragraphs[0]
    left_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    left_para.paragraph_format.space_before = Pt(0)
    left_para.paragraph_format.space_after = Pt(0)
    left_para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    left_para.paragraph_format.line_spacing = Pt(CODE_LAYOUT.header_line_pt)
    left_run = left_para.add_run(f"{software_name} {version}")
    set_run_font(left_run, "SimSun", CODE_LAYOUT.header_font_size_pt)

    right_para = right_cell.paragraphs[0]
    right_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    right_para.paragraph_format.space_before = Pt(0)
    right_para.paragraph_format.space_after = Pt(0)
    right_para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    right_para.paragraph_format.line_spacing = Pt(CODE_LAYOUT.header_line_pt)
    prefix = right_para.add_run("第 ")
    set_run_font(prefix, "SimSun", CODE_LAYOUT.header_font_size_pt)
    add_page_field(right_para)
    if show_total_pages:
        # Operation manual only (see set_manual_header): "第 X 页 共 Y 页".
        # Code materials keep the plain "第 X 页" format via the default
        # show_total_pages=False, so this branch never touches their output.
        mid = right_para.add_run(" 页 共 ")
        set_run_font(mid, "SimSun", CODE_LAYOUT.header_font_size_pt)
        add_total_pages_field(right_para)
    suffix = right_para.add_run(" 页")
    set_run_font(suffix, "SimSun", CODE_LAYOUT.header_font_size_pt)

    # Remove borders from the header table
    for cell in table.rows[0].cells:
        tc_pr = cell._tc.get_or_add_tcPr()
        tc_borders = OxmlElement("w:tcBorders")
        for border_name in ("top", "left", "bottom", "right"):
            border = OxmlElement(f"w:{border_name}")
            border.set(qn("w:val"), "nil")
            tc_borders.append(border)
        tc_pr.append(tc_borders)


def set_manual_header(document: Any, software_name: str, version: str) -> None:
    """Centered running header matching the supplied cover and contents sample."""
    paragraph = document.sections[0].header.paragraphs[0]
    paragraph.text = ""
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(f"{software_name} {version}")
    set_run_font(run, "SimSun", 9)
    run.font.color.rgb = RGBColor(130, 130, 130)


def add_manual_cover(document: Any, software_name: str, version: str) -> None:
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(210)
    title.paragraph_format.space_after = Pt(0)
    title.paragraph_format.keep_with_next = True
    name_run = title.add_run(software_name)
    set_run_font(name_run, "SimSun", 26)
    name_run.font.bold = True
    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_before = Pt(4)
    subtitle.paragraph_format.space_after = Pt(0)
    subtitle.paragraph_format.keep_with_next = True
    subtitle_run = subtitle.add_run("用户手册")
    set_run_font(subtitle_run, "SimSun", 26)
    subtitle_run.font.bold = True
    version_paragraph = document.add_paragraph()
    version_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    version_paragraph.paragraph_format.space_before = Pt(28)
    version_run = version_paragraph.add_run(version)
    set_run_font(version_run, "SimSun", 16)
    version_run.font.bold = True
    document.add_page_break()


def add_manual_toc(document: Any, chapter_titles: list[str]) -> None:
    """Make page two a real Word TOC with eight chapter entries."""
    expected = [f"{index}. {title}" for index, (_field, title, _pages) in enumerate(MANUAL_CHAPTERS, start=1)]
    if chapter_titles != expected:
        raise RuntimeError("用户手册须按八章结构生成；请重新生成用户手册 Markdown")
    style = document.styles["TOC 1"] if "TOC 1" in document.styles else document.styles.add_style("TOC 1", WD_STYLE_TYPE.PARAGRAPH)
    style.font.name = "SimSun"
    style.font.size = Pt(12)
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.paragraph_format.space_after = Pt(18)
    style.paragraph_format.tab_stops.add_tab_stop(Cm(14.8), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    heading.paragraph_format.space_before = Pt(4)
    heading.paragraph_format.space_after = Pt(12)
    heading_run = heading.add_run("目录")
    set_run_font(heading_run, "SimSun", 14)
    for index, title in enumerate(chapter_titles, start=1):
        paragraph = document.add_paragraph(style="TOC 1")
        if index == 1:
            begin = OxmlElement("w:fldChar")
            begin.set(qn("w:fldCharType"), "begin")
            begin.set(qn("w:dirty"), "false")
            paragraph.add_run()._r.append(begin)
            instruction = OxmlElement("w:instrText")
            instruction.text = ' TOC \\o "2-2" \\h \\z '
            paragraph.add_run()._r.append(instruction)
            separate = OxmlElement("w:fldChar")
            separate.set(qn("w:fldCharType"), "separate")
            paragraph.add_run()._r.append(separate)
        label = paragraph.add_run(title)
        set_run_font(label, "SimSun", 12)
        paragraph.add_run("\t")
        field_begin = OxmlElement("w:fldChar")
        field_begin.set(qn("w:fldCharType"), "begin")
        paragraph.add_run()._r.append(field_begin)
        field_instruction = OxmlElement("w:instrText")
        field_instruction.text = f" PAGEREF _UserManualChapter{index} \\h "
        paragraph.add_run()._r.append(field_instruction)
        field_separate = OxmlElement("w:fldChar")
        field_separate.set(qn("w:fldCharType"), "separate")
        paragraph.add_run()._r.append(field_separate)
        page_run = paragraph.add_run(str(index))
        set_run_font(page_run, "SimSun", 12)
        field_end = OxmlElement("w:fldChar")
        field_end.set(qn("w:fldCharType"), "end")
        paragraph.add_run()._r.append(field_end)
        if index == len(chapter_titles):
            toc_end = OxmlElement("w:fldChar")
            toc_end.set(qn("w:fldCharType"), "end")
            paragraph.add_run()._r.append(toc_end)
    body_section = document.add_section(WD_SECTION.NEW_PAGE)
    page_numbering = OxmlElement("w:pgNumType")
    page_numbering.set(qn("w:start"), "1")
    body_section._sectPr.append(page_numbering)


def add_toc_field(document: Any) -> None:
    """Insert a Word-native, clickable table of contents after the manual's
    main title.

    python-docx has no built-in TOC helper, so the field is built by hand
    from the same fldChar begin/separate/end + instrText primitives that
    add_page_field() uses for the PAGE field. The ``\\o "2-2"`` switch
    restricts the TOC to Heading 2 paragraphs only (the fifteen "一、xxx"
    ... "十五、xxx" chapter headings produced by build_manual_docx_python
    for markdown "## " lines); the level-1 document title itself uses
    Heading 1 and is therefore excluded. ``\\h`` makes entries clickable
    hyperlinks, ``\\z`` hides tab leaders/page numbers in web layout, and
    ``\\u`` builds entries from paragraph outline level as a fallback.

    The field's cached result is left as placeholder text instructing the
    reader to update it; enable_auto_update_fields() (called by
    build_manual_docx_python) additionally sets the document to refresh
    all fields automatically when opened in Word, so in practice the
    reader does not need to do this manually.
    """
    label = document.add_paragraph()
    label_run = label.add_run("目录")
    set_run_font(label_run, "SimHei", 14)
    label_run.font.bold = True
    label.paragraph_format.space_before = Pt(12)
    label.paragraph_format.space_after = Pt(6)

    toc_paragraph = document.add_paragraph()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin.set(qn("w:dirty"), "false")
    instr = OxmlElement("w:instrText")
    instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instr.text = ' TOC \\o "2-2" \\h \\z \\u '
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    placeholder = OxmlElement("w:t")
    placeholder.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    placeholder.text = "请在 Word 中右键选择「更新域」以生成目录"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")

    for element in (begin, instr, separate, placeholder, end):
        run = toc_paragraph.add_run()
        run._r.append(element)
        set_run_font(run, "SimSun", 10.5)

    # Give the table of contents its own page so chapter one still opens
    # cleanly on a fresh page once the TOC expands to its real length.
    break_run = document.add_paragraph().add_run()
    page_break = OxmlElement("w:br")
    page_break.set(qn("w:type"), "page")
    break_run._r.append(page_break)


def disable_auto_update_fields(document: Any) -> None:
    """Keep Word from prompting to refresh fields when a generated DOCX opens."""
    settings_root = document.settings.element
    update_fields = settings_root.find(qn("w:updateFields"))
    if update_fields is None:
        update_fields = OxmlElement("w:updateFields")
        compat = settings_root.find(qn("w:compat"))
        if compat is not None:
            compat.addprevious(update_fields)
        else:
            settings_root.append(update_fields)
    update_fields.set(qn("w:val"), "false")


def build_code_docx_python(md_path: Path, out_path: Path, software_name: str, version: str) -> None:
    pages = parse_code_pages(md_path)
    if not pages:
        raise RuntimeError(f"No code pages parsed from {md_path}")

    document = Document()
    configure_code_a4(document)
    set_normal_font(document, "Courier New", CODE_LAYOUT.body_font_size_pt)
    set_style_black(document)
    set_code_header(document, software_name, version)

    # 后30页文档页码从31开始，实现前后文档连续编号1-60
    start_page_no = pages[0][0] if pages else 1
    if start_page_no != 1:
        pg_num_type = OxmlElement("w:pgNumType")
        pg_num_type.set(qn("w:start"), str(start_page_no))
        document.sections[0]._sectPr.append(pg_num_type)

    for index, (page_no, lines) in enumerate(pages):
        visual_line_count = sum(len(wrap_code_line(line)) for line in lines)
        if visual_line_count > 75:
            raise RuntimeError(
                f"代码材料第 {page_no} 页换行后达到 {visual_line_count} 行，超过单页容纳量；"
                "请调整代码选择，避免 Word 自动溢出导致页数不一致"
            )
        for line in lines:
            p = document.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            p.paragraph_format.line_spacing = Pt(CODE_LAYOUT.body_line_pt)
            for segment_index, segment in enumerate(wrap_code_line(line)):
                if segment_index:
                    p.add_run().add_break()
                run = p.add_run(segment)
                set_run_font(run, "Courier New", CODE_LAYOUT.body_font_size_pt)
        if index != len(pages) - 1:
            # 嵌入式分页符：避免 add_page_break() 产生多余空段落导致空白页
            run = p.add_run()
            br = OxmlElement('w:br')
            br.set(qn('w:type'), 'page')
            run._r.append(br)

    force_black_document(document)
    document.save(out_path)


def paragraph_xml(text: str, font: str = "SimSun", size_half_points: int = 21, align: str | None = None, line_twips: int = 240) -> str:
    align_xml = f'<w:jc w:val="{align}"/>' if align else ""
    escaped = html.escape(text)
    return (
        "<w:p>"
        f"<w:pPr>{align_xml}<w:spacing w:after=\"0\" w:line=\"{line_twips}\" w:lineRule=\"exact\"/></w:pPr>"
        "<w:r>"
        f"<w:rPr><w:rFonts w:ascii=\"{font}\" w:hAnsi=\"{font}\" w:eastAsia=\"{font}\"/>"
        f"<w:color w:val=\"{BLACK_RGB}\"/>"
        f"<w:sz w:val=\"{size_half_points}\"/><w:szCs w:val=\"{size_half_points}\"/></w:rPr>"
        f"<w:t xml:space=\"preserve\">{escaped}</w:t>"
        "</w:r>"
        "</w:p>"
    )


def page_break_xml() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def page_field_runs_xml() -> str:
    return (
        '<w:r><w:rPr><w:rFonts w:ascii="SimSun" w:hAnsi="SimSun" w:eastAsia="SimSun"/>'
        f'<w:color w:val="{BLACK_RGB}"/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr>'
        '<w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:rPr><w:rFonts w:ascii="SimSun" w:hAnsi="SimSun" w:eastAsia="SimSun"/>'
        f'<w:color w:val="{BLACK_RGB}"/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr>'
        '<w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r><w:rPr><w:rFonts w:ascii="SimSun" w:hAnsi="SimSun" w:eastAsia="SimSun"/>'
        f'<w:color w:val="{BLACK_RGB}"/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr>'
        '<w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:rPr><w:rFonts w:ascii="SimSun" w:hAnsi="SimSun" w:eastAsia="SimSun"/>'
        f'<w:color w:val="{BLACK_RGB}"/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr>'
        '<w:t>1</w:t></w:r>'
        '<w:r><w:rPr><w:rFonts w:ascii="SimSun" w:hAnsi="SimSun" w:eastAsia="SimSun"/>'
        f'<w:color w:val="{BLACK_RGB}"/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr>'
        '<w:fldChar w:fldCharType="end"/></w:r>'
    )


def header_xml(header_text: str) -> str:
    """Build a two-column header: software name left, page number right."""
    escaped = html.escape(header_text)
    # Use a borderless table for left/right alignment in header
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:tbl>
    <w:tblPr>
      <w:tblW w:w="5000" w:type="pct"/>
      <w:tblBorders>
        <w:top w:val="nil"/><w:left w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/><w:insideH w:val="nil"/><w:insideV w:val="nil"/>
      </w:tblBorders>
    </w:tblPr>
    <w:tr>
      <w:tc>
        <w:p>
          <w:pPr><w:jc w:val="left"/><w:spacing w:after="0" w:line="240" w:lineRule="exact"/></w:pPr>
          <w:r><w:rPr><w:rFonts w:ascii="SimSun" w:hAnsi="SimSun" w:eastAsia="SimSun"/><w:color w:val="{BLACK_RGB}"/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr><w:t xml:space="preserve">{escaped}</w:t></w:r>
        </w:p>
      </w:tc>
      <w:tc>
        <w:p>
          <w:pPr><w:jc w:val="right"/><w:spacing w:after="0" w:line="240" w:lineRule="exact"/></w:pPr>
          <w:r><w:rPr><w:rFonts w:ascii="SimSun" w:hAnsi="SimSun" w:eastAsia="SimSun"/><w:color w:val="{BLACK_RGB}"/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr><w:t xml:space="preserve">第 </w:t></w:r>
          {page_field_runs_xml()}
          <w:r><w:rPr><w:rFonts w:ascii="SimSun" w:hAnsi="SimSun" w:eastAsia="SimSun"/><w:color w:val="{BLACK_RGB}"/><w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr><w:t xml:space="preserve"> 页</w:t></w:r>
        </w:p>
      </w:tc>
    </w:tr>
  </w:tbl>
</w:hdr>"""


def minimal_docx(out_path: Path, body_xml: str, header_text: str | None = None, start_page: int = 1) -> None:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    header_rel = (
        '<Relationship Id="rIdHeader1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
        if header_text
        else ""
    )
    doc_rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{header_rel}</Relationships>"""
    styles = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:rPr><w:rFonts w:ascii="SimSun" w:hAnsi="SimSun" w:eastAsia="SimSun"/><w:color w:val="{BLACK_RGB}"/><w:sz w:val="21"/></w:rPr>
  </w:style>
</w:styles>"""
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>
    {body_xml}
      <w:sectPr>
        {'<w:headerReference w:type="default" r:id="rIdHeader1"/>' if header_text else ''}
        {'<w:pgNumType w:start="' + str(start_page) + '"/>' if start_page != 1 else ''}
        <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1418" w:header="283" w:footer="283" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>"""
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
        zf.writestr("word/styles.xml", styles)
        zf.writestr("word/document.xml", document)
        if header_text:
            zf.writestr("word/header1.xml", header_xml(header_text))


def force_black_xml(xml: str) -> str:
    xml = re.sub(r"<w:hyperlink\b[^>]*>", "", xml)
    xml = xml.replace("</w:hyperlink>", "")
    xml = re.sub(r"<w:color\b[^>]*/>", f'<w:color w:val="{BLACK_RGB}"/>', xml)

    def ensure_rpr_color(match: re.Match[str]) -> str:
        value = match.group(0)
        if "<w:color" in value:
            return value
        return value.replace("</w:rPr>", f'<w:color w:val="{BLACK_RGB}"/></w:rPr>')

    xml = re.sub(r"<w:rPr\b[^>]*>.*?</w:rPr>", ensure_rpr_color, xml, flags=re.S)
    xml = re.sub(r"<w:r>(?!<w:rPr>)", f'<w:r><w:rPr><w:color w:val="{BLACK_RGB}"/></w:rPr>', xml)
    return xml


def normalize_docx_text_color(docx_path: Path) -> None:
    tmp_path = docx_path.with_suffix(docx_path.suffix + ".tmp")
    color_xml_parts = (
        "word/document.xml",
        "word/styles.xml",
        "word/numbering.xml",
        "word/header",
        "word/footer",
    )
    with zipfile.ZipFile(docx_path, "r") as src, zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.endswith(".xml") and item.filename.startswith(color_xml_parts):
                text = data.decode("utf-8")
                data = force_black_xml(text).encode("utf-8")
            elif item.filename.endswith(".rels"):
                text = data.decode("utf-8", errors="ignore")
                if "hyperlink" in text:
                    text = re.sub(r'\s*<Relationship\b[^>]*Type="[^"]*/hyperlink"[^>]*/>', "", text)
                    data = text.encode("utf-8")
            dst.writestr(item, data)
    tmp_path.replace(docx_path)


def next_header_part(names: set[str]) -> tuple[str, str]:
    index = 1
    while f"word/header{index}.xml" in names:
        index += 1
    return f"word/header{index}.xml", f"header{index}.xml"


def unique_relationship_id(rels_xml: str, base: str = "rIdManualHeader") -> str:
    if f'Id="{base}"' not in rels_xml:
        return base
    index = 2
    while f'Id="{base}{index}"' in rels_xml:
        index += 1
    return f"{base}{index}"


def add_header_to_existing_docx(docx_path: Path, header_text: str) -> None:
    """Add the same two-column header used by code materials to an existing DOCX."""
    tmp_path = docx_path.with_suffix(docx_path.suffix + ".tmp")
    with zipfile.ZipFile(docx_path, "r") as src:
        names = set(src.namelist())
        header_part, header_target = next_header_part(names)
        rels_xml = src.read("word/_rels/document.xml.rels").decode("utf-8")
        rel_id = unique_relationship_id(rels_xml)

        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "[Content_Types].xml":
                    text = data.decode("utf-8")
                    override = (
                        f'<Override PartName="/{header_part}" '
                        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
                    )
                    if f'PartName="/{header_part}"' not in text:
                        text = text.replace("</Types>", f"{override}</Types>")
                    data = text.encode("utf-8")
                elif item.filename == "word/_rels/document.xml.rels":
                    text = data.decode("utf-8")
                    relationship = (
                        f'<Relationship Id="{rel_id}" '
                        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
                        f'Target="{header_target}"/>'
                    )
                    text = text.replace("</Relationships>", f"{relationship}</Relationships>")
                    data = text.encode("utf-8")
                elif item.filename == "word/document.xml":
                    text = data.decode("utf-8")
                    if "xmlns:r=" not in text:
                        text = text.replace(
                            "<w:document ",
                            '<w:document xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ',
                            1,
                        )
                    header_ref = f'<w:headerReference w:type="default" r:id="{rel_id}"/>'
                    if "<w:headerReference" in text:
                        text = re.sub(r"<w:headerReference\b[^>]*/>", header_ref, text, count=1)
                    else:
                        text = re.sub(r"(<w:sectPr\b[^>]*>)", rf"\1{header_ref}", text, count=1)
                    data = text.encode("utf-8")
                dst.writestr(item, data)
            dst.writestr(header_part, header_xml(header_text))
    tmp_path.replace(docx_path)


def build_code_docx_ooxml(md_path: Path, out_path: Path, software_name: str, version: str) -> None:
    pages = parse_code_pages(md_path)
    if not pages:
        raise RuntimeError(f"No code pages parsed from {md_path}")
    start_page_no = pages[0][0] if pages else 1
    body: list[str] = []
    for index, (page_no, lines) in enumerate(pages):
        for line in lines:
            body.append(paragraph_xml(line if line else " ", font="Courier New", size_half_points=15, line_twips=190))
        if index != len(pages) - 1:
            # 嵌入式分页符：嵌入最后一段的 run 避免多余空段落
            last = body.pop()
            last = last.replace('</w:r></w:p>', '<w:br w:type="page"/></w:r></w:p>')
            body.append(last)
    minimal_docx(out_path, "\n".join(body), header_text=f"{software_name} {version}", start_page=start_page_no)


def add_markdown_table(document: Any, rows: list[list[str]]) -> None:
    if not rows:
        return
    table = document.add_table(rows=1, cols=len(rows[0]))
    table.style = "Table Grid"
    for idx, text in enumerate(rows[0]):
        cell = table.rows[0].cells[idx]
        cell.text = strip_markdown_links(text)
        try:
            run = cell.paragraphs[0].runs[0]
            run.font.bold = True
            run.font.name = "SimSun"
            run.font.color.rgb = RGBColor(0, 0, 0)
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "SimSun")
        except Exception:
            pass
    for row in rows[1:]:
        cells = table.add_row().cells
        for idx, text in enumerate(row[: len(cells)]):
            cells[idx].text = strip_markdown_links(text)


def parse_table_line(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def add_image(document: Any, image_path: Path, caption: str | None = None) -> None:
    if not image_path.exists():
        p = document.add_paragraph()
        run = p.add_run(f"[截图缺失：{image_path}]")
        set_run_font(run, "SimSun", 10.5)
        return
    try:
        size = probe_image_size(image_path)
        if size is not None:
            width_px, height_px = size
            width_in, height_in = fit_image_size(width_px, height_px)
            document.add_picture(str(image_path), width=Inches(width_in), height=Inches(height_in))
            document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        else:
            # Real pixel size could not be determined (unsupported format,
            # corrupted file, etc.): fall back to width-only, matching the
            # previous behaviour and letting python-docx infer the height.
            document.add_picture(str(image_path), width=Inches(5.8))
            document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        if caption:
            caption_p = document.add_paragraph()
            caption_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            caption_run = caption_p.add_run(caption)
            set_run_font(caption_run, "SimSun", 9)
    except Exception:
        p = document.add_paragraph()
        run = p.add_run(f"[截图无法插入：{image_path}]")
        set_run_font(run, "SimSun", 10.5)


def set_heading_font(paragraph: Any, level: int) -> None:
    """Apply the manual's Chinese heading convention: bold 黑体 (SimHei).

    Level 1 (document title, `#`) is centered and larger (三号/16pt); level 2
    and below (chapter/section headings) stay left-aligned and slightly
    smaller (四号/14pt, 小四/12pt for level 3+). Word's built-in Heading
    styles default to an English sans-serif for the Latin run, which reads
    inconsistently next to the SimSun body text, so every run's font is set
    explicitly here.
    """
    if level <= 1:
        size_pt = 16.0
        alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif level == 2:
        size_pt = 14.0
        alignment = WD_ALIGN_PARAGRAPH.LEFT
    else:
        size_pt = 12.0
        alignment = WD_ALIGN_PARAGRAPH.LEFT

    paragraph.alignment = alignment
    paragraph.paragraph_format.space_before = Pt(12)
    paragraph.paragraph_format.space_after = Pt(6)
    for run in paragraph.runs:
        run.font.name = "SimHei"
        run.font.size = Pt(size_pt)
        run.font.bold = True
        try:
            run.font.color.rgb = RGBColor(0, 0, 0)
        except Exception:
            pass
        try:
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "SimHei")
        except Exception:
            pass


def build_manual_docx_python(md_path: Path, out_path: Path, base_dir: Path, software_name: str, version: str) -> None:
    document = Document()
    configure_a4(document)
    set_normal_font(document, "SimSun", 10.5)
    set_style_black(document)
    lines = md_path.read_text(encoding="utf-8").splitlines()
    chapter_titles = [line.strip()[3:].strip() for line in lines if line.strip().startswith("## ")]
    add_manual_cover(document, software_name, version)
    add_manual_toc(document, chapter_titles)
    table_buf: list[list[str]] = []
    in_fence = False
    chapter_index = 0

    def flush_table() -> None:
        nonlocal table_buf
        if table_buf:
            data = [row for row in table_buf if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)]
            add_markdown_table(document, data)
            table_buf = []

    for line in lines:
        stripped = line.strip()
        stripped = strip_markdown_links(stripped)
        if stripped.startswith("```"):
            flush_table()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("<!--") and "截图" in stripped:
            stripped = "【截图预留：请在此处插入当前功能页面或操作结果截图。】"
        if stripped.startswith("|") and stripped.endswith("|"):
            table_buf.append(parse_table_line(stripped))
            continue
        flush_table()
        if not stripped:
            continue
        image_match = re.search(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            add_image(
                document,
                (base_dir / image_match.group(2)).resolve(),
                caption=image_match.group(1) or None,
            )
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            if level == 1:
                continue  # 第一页封面已写入用户手册标题。
            p = document.add_heading(heading.group(2), level=level)
            set_heading_font(p, level)
            if level == 2:
                chapter_index += 1
                marker = OxmlElement("w:bookmarkStart")
                marker.set(qn("w:id"), str(20000 + chapter_index))
                marker.set(qn("w:name"), f"_UserManualChapter{chapter_index}")
                p._p.insert(1 if p._p.find(qn("w:pPr")) is not None else 0, marker)
                marker_end = OxmlElement("w:bookmarkEnd")
                marker_end.set(qn("w:id"), str(20000 + chapter_index))
                p._p.append(marker_end)
            continue
        if re.match(r"^[-*+]\s+", stripped):
            p = document.add_paragraph(style="List Bullet")
            p.paragraph_format.line_spacing = 1.5
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(re.sub(r"^[-*+]\s+", "", stripped))
            set_run_font(run, "SimSun", 10.5)
            continue
        if re.match(r"^\d+\.\s+", stripped):
            p = document.add_paragraph(style="List Number")
            p.paragraph_format.line_spacing = 1.5
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(re.sub(r"^\d+\.\s+", "", stripped))
            set_run_font(run, "SimSun", 10.5)
            continue
        p = document.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(21)
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run(stripped)
        set_run_font(run, "SimSun", 10.5)
    flush_table()
    force_black_document(document)
    set_manual_header(document, software_name, version)
    disable_auto_update_fields(document)
    document.save(out_path)


def pandoc_available() -> bool:
    return shutil.which("pandoc") is not None


def probe_image_size(path: Path) -> tuple[int, int] | None:
    """Read the true pixel width/height of a JPEG or PNG file using only stdlib.

    pandoc 3.7.0.2 has been observed to silently fail to detect the real
    dimensions of certain baseline JPEGs and fall back to its built-in
    default box (3810000 x 2540000 EMU, i.e. an aspect ratio of 1.5),
    stretching portrait screenshots into a landscape box. Reading the
    dimensions ourselves lets us hand pandoc an explicit, correct
    width/height so it never needs to probe the file itself.

    Returns (width, height) in pixels, or None if the file could not be
    read or its format is not recognised (callers must gracefully fall
    back to the old "let pandoc figure it out" behaviour in that case).
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None

    try:
        # PNG: signature, then an IHDR chunk whose first 8 bytes (after the
        # 4-byte length + 4-byte "IHDR" tag) are big-endian width/height.
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            if len(data) < 24 or data[12:16] != b"IHDR":
                return None
            width, height = struct.unpack(">II", data[16:24])
            if width <= 0 or height <= 0:
                return None
            return width, height

        # JPEG: walk the marker segments looking for a SOFn (start of frame)
        # marker; its payload begins with 1 byte precision, then 2 bytes
        # height, then 2 bytes width, all big-endian.
        if data[:2] == b"\xff\xd8":
            sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
            no_length_markers = {0xD8, 0xD9, 0x01} | set(range(0xD0, 0xD8))
            length = len(data)
            idx = 2
            while idx < length:
                if data[idx] != 0xFF:
                    idx += 1
                    continue
                # skip any 0xFF padding bytes before the real marker byte
                marker_idx = idx + 1
                while marker_idx < length and data[marker_idx] == 0xFF:
                    marker_idx += 1
                if marker_idx >= length:
                    return None
                marker = data[marker_idx]
                idx = marker_idx + 1
                if marker == 0xD9:  # EOI
                    return None
                if marker in no_length_markers:
                    continue
                if idx + 2 > length:
                    return None
                seg_len = struct.unpack(">H", data[idx : idx + 2])[0]
                if seg_len < 2:
                    return None
                if marker in sof_markers:
                    if idx + 7 > length:
                        return None
                    height, width = struct.unpack(">HH", data[idx + 3 : idx + 7])
                    if width <= 0 or height <= 0:
                        return None
                    return width, height
                idx += seg_len
            return None
    except (struct.error, IndexError):
        return None

    return None


IMAGE_REF_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)(\{[^}]*\})?")

# Shared box constraints used by both the pandoc branch (rewrite_image_dimensions)
# and the python-docx branch (add_image), so a portrait screenshot is capped the
# same way regardless of which rendering path is active.
IMAGE_MAX_WIDTH_IN = 5.8
IMAGE_MAX_HEIGHT_IN = 8.8


def fit_image_size(
    width_px: int,
    height_px: int,
    max_width_in: float = IMAGE_MAX_WIDTH_IN,
    max_height_in: float = IMAGE_MAX_HEIGHT_IN,
) -> tuple[float, float]:
    """Fit a width_px x height_px image into a max_width_in x max_height_in box.

    Width is first set to max_width_in and height derived from the true
    aspect ratio (binding constraint for landscape-ish images, e.g. web page
    captures). If that derived height would exceed max_height_in (tall,
    narrow portrait phone screenshots), the box is recomputed the other way
    around: height is capped at max_height_in and width is derived from the
    aspect ratio instead, so the image never grows taller than a single page
    allows. Returns (width_in, height_in).
    """
    width_in = max_width_in
    height_in = width_in * height_px / width_px
    if height_in > max_height_in:
        height_in = max_height_in
        width_in = height_in * width_px / height_px
    return width_in, height_in


def rewrite_image_dimensions(
    text: str,
    base_dir: Path,
    max_width_in: float = IMAGE_MAX_WIDTH_IN,
    max_height_in: float = IMAGE_MAX_HEIGHT_IN,
) -> str:
    """Add explicit {width=..in height=..in} attributes to markdown image refs.

    Only touches `![alt](path)` references that do not already carry a
    `{width=...}` attribute. When the referenced file's real pixel size
    can be read (see probe_image_size), the box is capped by both
    max_width_in (matching the python-docx branch's Inches(5.8) rule) and
    max_height_in, and the true aspect ratio is preserved:

    - width is first set to max_width_in and height derived from the real
      aspect ratio (this matches landscape-ish screenshots, e.g. web page
      captures, where the width cap is the binding constraint);
    - if that derived height would exceed max_height_in (this is what
      happens with tall, narrow portrait phone screenshots), the box is
      recomputed the other way around: height is capped at max_height_in
      and width is derived from the aspect ratio instead, so the image
      never gets taller than a single page allows.

    max_height_in defaults to 8.8in. Derivation: an A4 page is 11.69in
    tall; with ~1in top+bottom margins the usable height is ~9.69in.
    Reserving roughly 0.7-1in for the figure's caption/heading and the
    surrounding paragraph spacing (so the caption doesn't get pushed onto
    the next page as an orphan) leaves about 8.8in for the image itself.

    When the size cannot be determined the line is left untouched.
    """

    def replace(match: re.Match[str]) -> str:
        alt, ref_path, existing_attrs = match.group(1), match.group(2), match.group(3)
        if existing_attrs and "width=" in existing_attrs:
            return match.group(0)

        image_path = (base_dir / ref_path).resolve()
        size = probe_image_size(image_path)
        if size is None:
            return match.group(0)
        width_px, height_px = size

        width_in, height_in = fit_image_size(width_px, height_px, max_width_in, max_height_in)
        return f"![{alt}]({ref_path}){{width={width_in:.2f}in height={height_in:.2f}in}}"

    return IMAGE_REF_RE.sub(replace, text)


def build_with_pandoc(md_path: Path, out_path: Path, base_dir: Path | None = None, code_mode: bool = False) -> None:
    if not pandoc_available():
        raise RuntimeError("python-docx is unavailable and pandoc is not installed")
    source = md_path
    tmp_name: str | None = None
    original_text = md_path.read_text(encoding="utf-8")
    text = original_text
    text = re.sub(r"```text\s*\nSTOP_FOR_USER\n.*?```", "", text, flags=re.S)
    text = re.sub(r"<!--[^>]*截图[^>]*-->", "【截图预留：请在此处插入当前功能页面或操作结果截图。】", text)
    text = strip_markdown_links(text)
    if code_mode:
        text = re.sub(r"(?=^##\s+第\s*\d+\s*页)", r"\n\\newpage\n", text, flags=re.M)
    elif base_dir is not None:
        # Only the manual (non-code) path carries screenshots; pre-compute
        # each image's real aspect ratio so pandoc never has to guess it.
        text = rewrite_image_dimensions(text, base_dir)
    if text != original_text:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tmp:
            tmp.write(text)
            tmp_name = tmp.name
        source = Path(tmp_name)
    try:
        subprocess.run(["pandoc", "-f", "markdown", "-t", "docx", str(source), "-o", str(out_path)], check=True)
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)


def build_code_docx(md_path: Path, out_path: Path, software_name: str, version: str) -> None:
    if not DOCX_AVAILABLE:
        raise RuntimeError("代码材料六号字排版与长行换行需要 python-docx")
    build_code_docx_python(md_path, out_path, software_name, version)
    normalize_docx_text_color(out_path)


def refresh_manual_toc_with_layout(out_path: Path, chapter_titles: list[str]) -> bool:
    """Cache real chapter pages from a temporary layout render when available."""
    if not shutil.which("soffice"):
        return False
    try:
        from pypdf import PdfReader
    except ImportError:
        return False
    with tempfile.TemporaryDirectory(prefix="user-manual-toc-") as temp_name:
        temp_dir = Path(temp_name)
        env = os.environ.copy()
        font_dir = Path("/Applications/Microsoft Word.app/Contents/Resources/DFonts")
        if font_dir.is_dir() and not env.get("FONTCONFIG_FILE"):
            font_config = temp_dir / "fonts.conf"
            font_config.write_text(
                '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
                f'<fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
                f'<dir>{font_dir}</dir><cachedir>{temp_dir / "font-cache"}</cachedir></fontconfig>',
                encoding="utf-8",
            )
            env["FONTCONFIG_FILE"] = str(font_config)
        try:
            subprocess.run(
                [
                    "soffice", f"-env:UserInstallation={(temp_dir / 'profile').as_uri()}",
                    "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir), str(out_path),
                ],
                check=True, capture_output=True, text=True, timeout=90, env=env,
            )
            pdf_path = temp_dir / f"{out_path.stem}.pdf"
            reader = PdfReader(pdf_path)
            page_numbers: dict[int, int] = {}
            for physical_index, page in enumerate(reader.pages):
                if physical_index < 2:
                    continue
                page_lines = {re.sub(r"\s+", "", line) for line in (page.extract_text() or "").splitlines()}
                for chapter_index, title in enumerate(chapter_titles, start=1):
                    if chapter_index not in page_numbers and re.sub(r"\s+", "", title) in page_lines:
                        page_numbers[chapter_index] = physical_index - 1
            if len(page_numbers) != len(chapter_titles):
                return False
            document = Document(out_path)
            for paragraph in document.paragraphs:
                if not paragraph.style.name.lower().startswith("toc"):
                    continue
                match = re.match(r"^(\d+)\.", paragraph.text)
                if not match:
                    continue
                chapter_index = int(match.group(1))
                if chapter_index not in page_numbers:
                    continue
                for run in reversed(paragraph.runs):
                    if run.text.strip().isdigit():
                        run.text = str(page_numbers[chapter_index])
                        break
            document.save(out_path)
            return True
        except Exception:
            return False


def build_manual_docx(md_path: Path, out_path: Path, base_dir: Path, software_name: str, version: str) -> bool:
    if not DOCX_AVAILABLE:
        raise RuntimeError("用户手册封面和目录生成需要 python-docx")
    build_manual_docx_python(md_path, out_path, base_dir, software_name, version)
    chapter_titles = [line.strip()[3:].strip() for line in md_path.read_text(encoding="utf-8").splitlines() if line.strip().startswith("## ")]
    return refresh_manual_toc_with_layout(out_path, chapter_titles)


CODE_SPEC_FALLBACK = ["代码-前后各30页.md", "代码-全部.md"]


def resolve_code_specs(draft_dir: Path, safe_name: str, safe_version: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Return [(markdown 文件名, docx 文件名)] plus any warnings.

    以 草稿/代码提取清单.json 的 outputs 字段定位源 Markdown。正式 Word
    始终采用 `<软件全称>-<版本号>-源程序鉴别材料.docx`，页数模式留在提取清单中。
    """
    warnings: list[str] = []
    manifest_path = draft_dir / "代码提取清单.json"
    manifest: dict[str, Any] = {}
    if not manifest_path.exists():
        warnings.append(
            "缺少 草稿/代码提取清单.json，代码材料已回退至固定文件名映射"
            f"（{'、'.join(CODE_SPEC_FALLBACK)}），"
            "如抽取环节输出的是降级文件名，须重新运行 extract_code_material.py 生成清单"
        )
    else:
        try:
            loaded = read_json(manifest_path)
            manifest = loaded if isinstance(loaded, dict) else {}
            if not isinstance(loaded, dict):
                warnings.append("草稿/代码提取清单.json 的顶层不是对象，代码材料已回退至固定文件名映射")
        except Exception as exc:
            warnings.append(f"草稿/代码提取清单.json 无法解析（{exc}），代码材料已回退至固定文件名映射")

    raw_outputs = manifest.get("outputs")
    outputs = (
        [name.strip() for name in raw_outputs if isinstance(name, str) and name.strip()]
        if isinstance(raw_outputs, list)
        else []
    )
    if not outputs:
        if manifest:
            warnings.append(
                "草稿/代码提取清单.json 未记录可用的 outputs 字段，代码材料已回退至固定文件名映射"
            )
        outputs = CODE_SPEC_FALLBACK

    if manifest.get("mode") == "selected_under_60_pages":
        warnings.append("代码材料仅覆盖已选部分源码；请核对提取清单中的覆盖范围与实际页数")
    docx_name = f"{safe_name}-{safe_version}-源程序鉴别材料.docx"
    specs = [(md_name, docx_name) for md_name in outputs]

    # 页数未精确对齐时必须在生成报告中留痕：此时代码材料不足 30+30 共 60 页，
    # 申请表「页数」字段须按实际渲染页数填写，否则最终校验会判页数不一致。
    if manifest.get("pagination_exact") is False:
        rendered = manifest.get("rendered_pages")
        warnings.append(
            f"代码材料页数未精确对齐：清单记录实际渲染前 {manifest.get('front_pages')} 页 + 后 "
            f"{manifest.get('back_pages')} 页，共 {rendered} 页，未达到 30+30 共 60 页。"
            f"申请表「页数」字段须按 {rendered} 填写；如须精确 60 页，"
            "应在 草稿/代码文件选择.json 中增删文件后重新运行 extract_code_material.py"
        )
    pagination_warning = manifest.get("pagination_warning")
    if isinstance(pagination_warning, str) and pagination_warning.strip():
        warnings.append(f"代码抽取环节的分页提示：{pagination_warning.strip()}")

    return specs, warnings


def build_all(workdir: Path, software_name: str, version: str) -> dict[str, Any]:
    workdir = ensure_dir(workdir)
    draft_dir = workdir / "草稿"
    final_dir = ensure_dir(workdir / "正式资料")
    app_name = application_software_name(draft_dir)
    app_version = application_version(draft_dir)
    if app_version != "V1.0.0":
        raise RuntimeError("申请表草稿的版本号必须为 V1.0.0；请重新生成并确认申请表信息")
    final_software_name = app_name or software_name
    final_version = app_version or version
    safe_name = safe_filename(final_software_name)
    outputs: list[Path] = []
    warnings: list[str] = []
    if app_name and app_name != software_name:
        warnings.append(f"命令参数软件名称为 {software_name}，正式资料已按申请表信息软件名称 {app_name} 生成")
    if app_version and app_version != version:
        warnings.append(f"命令参数版本号为 {version}，正式资料已按申请表信息版本号 {app_version} 生成")
    screenshot_confirmation = read_json_if_exists(workdir / "截图方式确认.json")
    screenshot_method = screenshot_confirmation.get("screenshot_method")
    screenshot_manifest = workdir / "截图/截图清单.json"
    if screenshot_method == "skip":
        warnings.append("用户选择暂不截图，用户手册已保留截图预留位置")
    elif screenshot_method == "generated-ui":
        warnings.append("用户手册采用依据真实功能证据生成的界面图片；生成方式、HTML 与证据见截图清单，图注仅写功能或页面名称")
    elif screenshot_method and not screenshot_manifest.exists():
        warnings.append("用户手册截图未生成或未插入，用户手册应保留截图预留位置")
    elif screenshot_manifest.exists():
        screenshots = read_json_if_exists(screenshot_manifest).get("screenshots") or []
        if not screenshots:
            warnings.append("用户手册截图清单为空，用户手册应保留截图预留位置")

    app_txt, app_warnings = write_application_txt(draft_dir, final_dir)
    if app_txt:
        outputs.append(app_txt)
    warnings.extend(app_warnings)

    code_specs, code_spec_warnings = resolve_code_specs(draft_dir, safe_name, safe_filename(final_version))
    warnings.extend(code_spec_warnings)
    if sum((draft_dir / md_name).exists() for md_name, _ in code_specs) > 1:
        raise RuntimeError("发现多份代码材料 Markdown；请在代码提取清单的 outputs 中只保留一份正式材料")
    code_outputs: list[Path] = []
    missing_code_md: list[str] = []
    for md_name, docx_name in code_specs:
        md_path = draft_dir / md_name
        if md_path.exists():
            out_path = final_dir / docx_name
            build_code_docx(md_path, out_path, final_software_name, final_version)
            outputs.append(out_path)
            code_outputs.append(out_path)
        else:
            missing_code_md.append(md_name)
    if not code_outputs:
        warnings.append(
            "未生成任何代码鉴别材料 Word：以下 Markdown 源在 草稿/ 下均不存在（"
            + "、".join(missing_code_md or [md for md, _ in code_specs])
            + "）。须先运行 extract_code_material.py 生成代码材料 Markdown 后重新生成正式资料"
        )
    elif missing_code_md:
        warnings.append(
            "部分代码材料 Markdown 缺失，对应 Word 未生成：" + "、".join(missing_code_md)
        )

    manual_md = draft_dir / "用户手册.md"
    if manual_md.exists():
        manual_out = final_dir / f"{safe_name}_用户手册.docx"
        manual_source = manual_md
        tmp_manual: Path | None = None
        if app_name and app_name != software_name:
            text = manual_md.read_text(encoding="utf-8").replace(software_name, app_name)
            with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tmp:
                tmp.write(text)
                tmp_manual = Path(tmp.name)
            manual_source = tmp_manual
        try:
            toc_refreshed = build_manual_docx(manual_source, manual_out, draft_dir, final_software_name, final_version)
        finally:
            if tmp_manual:
                tmp_manual.unlink(missing_ok=True)
        outputs.append(manual_out)
        if not toc_refreshed:
            warnings.append("用户手册目录页码未自动核准；请配置 soffice 与 pypdf 后重新生成")
    else:
        warnings.append("缺少草稿/用户手册.md")

    design_context = read_json_if_exists(draft_dir / "业务理解.json")
    design_fields = tuple(field for field, _title, _pages in DESIGN_CHAPTERS)
    if generate_design_docx is None or not all(design_context.get(field) for field in design_fields):
        raise RuntimeError("软件设计说明书生成前置条件不满足；请检查 python-docx 和业务理解必备字段")
    template = Path(__file__).resolve().parent.parent / "assets" / "design_spec_template.docx"
    try:
        _draft_design, design_out = generate_design_docx(
            design_context,
            final_software_name,
            final_version,
            template,
            draft_dir,
        )
        outputs.append(design_out)
    except Exception as exc:
        raise RuntimeError(f"软件设计说明书生成失败：{exc}") from exc

    warnings.append("用户手册与设计说明书须分别核实排版后恰好 60 页（含封面、目录）；运行 measure_document_pages.py 与 verify_materials.py 后方可交付")
    report = write_report(final_dir, outputs, warnings, [])
    return {"outputs": [str(p) for p in outputs], "warnings": warnings, "report": str(report)}


def write_report(workdir: Path, outputs: list[Path], warnings: list[str], notes: list[str]) -> Path:
    report = workdir / "生成报告.md"
    lines = ["# 生成报告", "", "## 输出文件", ""]
    for path in outputs:
        size = path.stat().st_size if path.exists() else 0
        lines.append(f"- `{path.name}` ({size} bytes)")
    lines.extend(["", "## 警告", ""])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- 无")
    lines.extend(["", "## DOCX 校验", ""])
    if notes:
        lines.extend(notes)
    else:
        lines.append("- 已跳过预览校验")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default="软件著作权申请资料")
    parser.add_argument("--software-name", required=True)
    parser.add_argument("--version", default="V1.0.0")
    args = parser.parse_args()

    workdir = Path(args.workdir)
    issues = confirmation_issues(workdir)
    if issues:
        print("STOP_FOR_USER")
        print("NEXT_ACTION: 正式 Word/TXT 生成前须完成以下确认：")
        for issue in issues:
            print(f"- {issue}")
        raise SystemExit(2)

    result = build_all(workdir, args.software_name, args.version)
    print(f"OK final materials: {Path(args.workdir) / '正式资料'}")
    for output in result["outputs"]:
        print(output)
    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"- {warning}")
    print(f"Report: {result['report']}")


if __name__ == "__main__":
    main()
