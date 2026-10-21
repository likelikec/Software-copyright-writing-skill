#!/usr/bin/env python3
"""Measure physical DOCX pages headlessly, never cached app.xml data."""

from __future__ import annotations

import argparse
import hashlib
import json
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
    if not shutil.which("soffice"):
        return {**result, "error": "缺少 soffice；静默页数核验需要 LibreOffice 与 pypdf"}
    try:
        from pypdf import PdfReader
    except ImportError:
        return {**result, "error": "缺少 pypdf；静默页数核验需要 LibreOffice 与 pypdf"}
    with tempfile.TemporaryDirectory(prefix="copyright-pagination-") as temp_name:
        temp = Path(temp_name)
        copy = temp / f"pagination-{temp.name}.docx"
        shutil.copy2(path, copy)
        try:
            subprocess.run(
                ["soffice", f"-env:UserInstallation={(temp / 'profile').as_uri()}",
                 "--headless", "--convert-to", "pdf", "--outdir", str(temp), str(copy)],
                check=True, capture_output=True, text=True, timeout=60,
            )
            count = len(PdfReader(copy.with_suffix(".pdf")).pages)
            if count <= 0:
                raise ValueError("排版结果为空")
            return {**result, "pages": count, "engine": "LibreOffice", "status": "pass" if count == DOCUMENT_TARGET_PAGES else "fail"}
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            return {**result, "error": f"LibreOffice 排版失败：{getattr(exc, 'stderr', '') or exc}"}


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
