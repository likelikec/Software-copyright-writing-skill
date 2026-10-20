#!/usr/bin/env python3
"""Capture simple, evidence-based interface illustrations for the user manual."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from capture_screenshots import reserved_names, safe_name, unique_target
from common import ensure_dir, read_json, write_json


def browser_executable(explicit: str) -> str:
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate)
        found = shutil.which(explicit)
        if found:
            return found
        raise RuntimeError(f"找不到浏览器可执行文件：{explicit}")
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            return found
    if platform.system() == "Darwin":
        for candidate in (
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ):
            if candidate.is_file():
                return str(candidate)
    raise RuntimeError("未找到 Chrome/Chromium/Edge；请通过 --browser 指定可执行文件")


def inside(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"{label} 必须位于 {root} 内：{path}")
    return resolved


def validate_plan(plan: dict[str, Any], workdir: Path, project: Path) -> list[dict[str, Any]]:
    raw = plan.get("screenshots")
    if not isinstance(raw, list) or not raw:
        raise ValueError("截图方案须包含非空 screenshots 数组")
    result: list[dict[str, Any]] = []
    html_root = workdir / "草稿" / "界面示意"
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"screenshots[{index}] 须为对象")
        module = str(item.get("module") or "").strip()
        caption = str(item.get("caption") or "").strip()
        html_name = str(item.get("html") or "").strip()
        evidence = item.get("evidence")
        if not module or not html_name or not isinstance(evidence, list) or not evidence:
            raise ValueError(f"screenshots[{index}] 缺少 module、html 或项目证据 evidence")
        html = inside(workdir / html_name, html_root, "HTML")
        if html.suffix.lower() != ".html" or not html.is_file():
            raise ValueError(f"界面示意 HTML 不存在：{html}")
        source = html.read_text(encoding="utf-8")
        if re.search(r"<script\b|https?://|file:|@import\b|<iframe\b|<link\b|<img\b|url\s*\(", source, re.I):
            raise ValueError(f"界面示意只能使用自包含的静态 HTML/CSS，不含脚本或外部资源：{html}")
        evidence_paths: list[str] = []
        for value in evidence:
            relative = Path(str(value))
            path = inside(project / relative, project, "项目证据")
            if not path.is_file():
                raise ValueError(f"项目证据不存在：{path}")
            evidence_paths.append(str(relative))
        if "界面示意" not in caption:
            caption = f"{caption or module + '功能界面'}（界面示意，非实际运行截图）"
        result.append({"module": module, "caption": caption, "html": html, "evidence": evidence_paths})
    return result


def capture_one(browser: str, html: Path, output: Path, width: int, height: int, profile: Path) -> None:
    args = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-background-networking",
        "--no-first-run",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--user-data-dir={profile}",
        f"--window-size={width},{height}",
        f"--screenshot={output}",
        html.as_uri(),
    ]
    if platform.system() == "Linux" and hasattr(os, "geteuid") and os.geteuid() == 0:
        args.insert(1, "--no-sandbox")
    run = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if run.returncode != 0 or not output.is_file() or output.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"浏览器截图失败：{html.name}；{(run.stderr or run.stdout)[-500:]}")


def capture_plan(workdir: Path, project: Path, plan_path: Path, browser: str = "", width: int = 1280, height: int = 900) -> dict[str, Any]:
    if width < 640 or height < 480:
        raise ValueError("截图视口至少为 640×480")
    confirmation = read_json(workdir / "截图方式确认.json")
    if not confirmation.get("screenshot_method_confirmed") or confirmation.get("screenshot_method") != "generated-ui":
        raise RuntimeError("须先由用户确认 generated-ui 截图方式")
    plan_path = inside(plan_path, workdir / "草稿" / "界面示意", "截图方案")
    items = validate_plan(read_json(plan_path), workdir, project)
    out_dir = ensure_dir(workdir / "截图")
    manifest_path = out_dir / "截图清单.json"
    if manifest_path.exists() and read_json(manifest_path).get("screenshots"):
        raise RuntimeError("截图清单已有图片；先核对现有截图，避免用示意图覆盖真实截图")
    executable = browser_executable(browser)
    with tempfile.TemporaryDirectory(prefix="ui-illustration-") as temp:
        temporary = Path(temp)
        for index, item in enumerate(items, start=1):
            image = temporary / f"{index}.png"
            capture_one(executable, item["html"], image, width, height, temporary / f"profile-{index}")
            item["image"] = image
        taken = reserved_names(out_dir, set())
        screenshots = []
        for item in items:
            target = unique_target(out_dir, f"{safe_name(item['module'])}-界面示意", ".png", taken)
            shutil.copy2(item["image"], target)
            screenshots.append({
                "module": item["module"],
                "caption": item["caption"],
                "path": os.path.relpath(target.resolve(), workdir.resolve()),
                "source_html": os.path.relpath(item["html"].resolve(), workdir.resolve()),
                "evidence": item["evidence"],
                "method": "generated-ui",
            })
    manifest = {"status": "ok", "method": "generated-ui", "project_root": os.path.relpath(project.resolve(), workdir.resolve()), "screenshots": screenshots}
    write_json(manifest_path, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--browser", default="")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()
    manifest = capture_plan(Path(args.workdir), Path(args.project), Path(args.plan), args.browser, args.width, args.height)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
