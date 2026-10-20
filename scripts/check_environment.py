#!/usr/bin/env python3
"""Check runtime capabilities at the beginning of the workflow."""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any

from common import ensure_dir, write_json


def command_version(command: list[str]) -> tuple[bool, str]:
    if not shutil.which(command[0]):
        return False, "not found"
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=20)
        output = (completed.stdout or completed.stderr).strip().splitlines()
        return completed.returncode == 0, output[0] if output else "available"
    except Exception as exc:
        return False, str(exc)


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check_environment(skill_dir: Path) -> dict[str, Any]:
    python_docx = module_available("docx")
    pypdf_available = module_available("pypdf")
    soffice_available = shutil.which("soffice") is not None
    ffmpeg_ok, ffmpeg_version = command_version(["ffmpeg", "-version"])
    ffprobe_ok, ffprobe_version = command_version(["ffprobe", "-version"])

    final_docx_mode = "python-docx" if python_docx else "unavailable"
    requires_user_input = not python_docx
    next_action = (
        "三类 Word 材料需要 python-docx。请安装 python-docx（pip install python-docx），重新运行环境检查，再继续生成材料。"
        if requires_user_input
        else "DOCX 生成环境可用，可进入项目分析。"
    )
    return {
        "output_directory": "当前目录/软件著作权申请资料",
        "capabilities": {
            "markdown_drafts": True,
            "application_txt": True,
            "code_docx": python_docx,
            "user_manual_docx": python_docx,
            "design_docx": python_docx,
            "python_docx": python_docx,
            "manual_toc_auto": pypdf_available and soffice_available,
            "operation_video_frames": ffmpeg_ok and ffprobe_ok,
        },
        "versions": {
            "ffmpeg": ffmpeg_version,
            "ffprobe": ffprobe_version,
        },
        "final_docx_mode": final_docx_mode,
        "recommendation": (
            "python-docx 可用，可生成三类 Word 文档和申请表 TXT。"
            if python_docx
            else "python-docx 不可用，须先安装 python-docx（pip install python-docx）。"
        ),
        "install_prompt": (
            "请安装 python-docx，重新运行环境检查。"
            if not python_docx
            else "无须安装，python-docx 已可用。"
        ),
        "requires_user_input": requires_user_input,
        "confirmation_stage": "environment" if requires_user_input else None,
        "next_action": next_action,
    }


def write_markdown(path: Path, data: dict[str, Any]) -> None:
    caps = data["capabilities"]
    lines = [
        "# 软著申请资料生成环境检查",
        "",
        f"- 输出目录：`{data['output_directory']}`",
        f"- 最终 Word 模式：`{data['final_docx_mode']}`",
        "",
        "## 能力状态",
        "",
        f"- Markdown 草稿：{'可用' if caps['markdown_drafts'] else '不可用'}",
        f"- 申请表 TXT：可用",
        f"- 三类 Word 文档：{'可用' if caps['python_docx'] else '不可用'}",
        f"- python-docx：{'可用' if caps['python_docx'] else '不可用'}",
        f"- 用户手册目录自动核页（soffice + pypdf）：{'可用' if caps['manual_toc_auto'] else '不可用，需在 Word 中更新目录'}",
        f"- 操作视频抽帧（ffmpeg + ffprobe）：{'可用' if caps['operation_video_frames'] else '不可用'}（ffmpeg: {data['versions']['ffmpeg']}；ffprobe: {data['versions']['ffprobe']}）",
        "",
        "代码鉴别材料使用 Courier New 六号字；用户手册目录可借助 soffice 与 pypdf 自动核页，设计说明书目录在 Word 可用时更新。正式资料包含申请表 TXT 和三类 DOCX。",
        "",
        "操作视频抽帧能力仅在用户选择提供操作视频时需要。不提供视频不影响后续流程；用户手册截图只整理用户截图目录的图片。",
        "",
        "## 建议",
        "",
        data["recommendation"],
        "",
        "## 用户选择",
        "",
        data["install_prompt"],
        "",
        "python-docx 不可用时须先安装并重新运行环境检查，不能生成正式资料。",
        "",
        "```text" if data.get("requires_user_input") else "",
        "STOP_FOR_USER" if data.get("requires_user_input") else "",
        f"NEXT_ACTION: {data['next_action']}" if data.get("requires_user_input") else "",
        "```" if data.get("requires_user_input") else "",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="软件著作权申请资料")
    args = parser.parse_args()

    skill_dir = Path(__file__).resolve().parents[1]
    out_dir = ensure_dir(Path(args.out_dir))
    data = check_environment(skill_dir)
    write_json(out_dir / "环境检查.json", data)
    write_markdown(out_dir / "环境检查.md", data)
    print(f"OK environment check: {out_dir}")
    print(f"Final DOCX mode: {data['final_docx_mode']}")
    print(data["recommendation"])
    if data.get("requires_user_input"):
        print("STOP_FOR_USER")
        print(f"NEXT_ACTION: {data['next_action']}")


if __name__ == "__main__":
    main()
