#!/usr/bin/env python3
"""Measure physical DOCX pages using a layout engine, never cached app.xml data."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from common import write_json
from document_structure import DOCUMENT_TARGET_PAGES


def measure_pages(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"file": path.name, "target": DOCUMENT_TARGET_PAGES, "pages": None, "status": "unverified"}
    if not path.is_file():
        return {**result, "error": "DOCX 不存在"}
    result["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    errors = []
    with tempfile.TemporaryDirectory(prefix="copyright-pagination-") as temp_name:
        temp = Path(temp_name)
        copy = temp / f"pagination-{temp.name}.docx"
        shutil.copy2(path, copy)
        # Work on a copy so measuring cannot change the confirmed source DOCX.
        libreoffice_ready = shutil.which("soffice") is not None and importlib.util.find_spec("pypdf") is not None
        if not libreoffice_ready and platform.system() == "Darwin" and Path("/Applications/Microsoft Word.app").is_dir() and shutil.which("osascript"):
            script = '''on run argv
tell application "Microsoft Word"
    set openedDoc to missing value
    try
        open file name (item 1 of argv) add to recent files false
        repeat 40 times
            try
                set candidate to active document
                if name of candidate contains (item 2 of argv) then set openedDoc to candidate
            end try
            if openedDoc is not missing value then exit repeat
            delay 0.25
        end repeat
        if openedDoc is missing value then error "Word has not opened the temporary document"
        update field (every field of text object of openedDoc)
        repaginate openedDoc
        set pageCount to compute statistics openedDoc statistic statistic pages
        close openedDoc saving no
        return pageCount
    on error errMsg number errNum
        if openedDoc is not missing value then close openedDoc saving no
        error errMsg number errNum
    end try
end tell
end run'''
            try:
                run = subprocess.run(["osascript", "-", str(copy), copy.stem], input=script, text=True, capture_output=True, timeout=60, check=True)
                count = int(run.stdout.strip())
                if count <= 0:
                    raise ValueError("Word 返回无效页数")
                return {**result, "pages": count, "engine": "Microsoft Word", "status": "pass" if count == DOCUMENT_TARGET_PAGES else "fail"}
            except (subprocess.SubprocessError, ValueError) as exc:
                errors.append(f"Word: {getattr(exc, 'stderr', '') or exc}")
        if shutil.which("soffice"):
            try:
                from pypdf import PdfReader
                subprocess.run([
                    "soffice", f"-env:UserInstallation={(temp / 'profile').as_uri()}",
                    "--headless", "--convert-to", "pdf", "--outdir", str(temp), str(copy),
                ], check=True, capture_output=True, text=True, timeout=60)
                reader = PdfReader(copy.with_suffix(".pdf"))
                count = len(reader.pages)
                if count <= 0:
                    raise ValueError("排版结果为空")
                return {**result, "pages": count, "engine": "LibreOffice", "status": "pass" if count == DOCUMENT_TARGET_PAGES else "fail", "fallback_notes": errors}
            except (ImportError, OSError, subprocess.SubprocessError, ValueError) as exc:
                errors.append(f"LibreOffice: {getattr(exc, 'stderr', '') or exc}")
    return {**result, "error": "；".join(errors) or "需要 Microsoft Word，或 soffice 与 pypdf；不得用分页符或元数据估算正文页数"}


def measure_documents(workdir: Path, paths: list[Path]) -> list[dict[str, Any]]:
    records = [measure_pages(path) for path in paths]
    write_json(workdir / "草稿" / "文档页数核验.json", {"target_pages_each": DOCUMENT_TARGET_PAGES, "includes_cover_and_contents": True, "documents": records})
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", required=True)
    args = parser.parse_args()
    workdir = Path(args.workdir)
    formal = workdir / "正式资料"
    paths = sorted(formal.glob("*_用户手册.docx")) + sorted(formal.glob("*-软件设计说明书.docx"))
    if len(paths) != 2:
        raise SystemExit("须提供唯一的用户手册和软件设计说明书 DOCX")
    records = measure_documents(workdir, paths)
    print(json.dumps(records, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(item["status"] == "pass" for item in records) else 1)


if __name__ == "__main__":
    main()
