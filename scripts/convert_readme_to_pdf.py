"""
scripts/convert_readme_to_pdf.py — Converts README.md into a high-quality PDF.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
import markdown

PROJECT_ROOT = Path(__file__).resolve().parent.parent
README_PATH = PROJECT_ROOT / "README.md"
HTML_PATH = PROJECT_ROOT / "README.html"
PDF_PATH = PROJECT_ROOT / "README.pdf"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser() -> str:
    for candidate in EDGE_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    raise RuntimeError("No headless browser (Edge/Chrome) found on system.")


def convert() -> None:
    print(f"[1/3] Reading {README_PATH.name}...")
    with open(README_PATH, "r", encoding="utf-8") as f:
        md_text = f.read()

    print("[2/3] Rendering Markdown to Styled HTML...")
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "nl2br", "sane_lists"]
    )

    css = """
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    @page {
        size: A4;
        margin: 18mm 14mm 18mm 14mm;
        @bottom-right {
            content: counter(page);
        }
    }

    * {
        box-sizing: border-box;
    }

    body {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        color: #1e293b;
        background: #ffffff;
        line-height: 1.55;
        font-size: 10pt;
        margin: 0;
        padding: 0;
    }

    h1, h2, h3, h4, h5, h6 {
        color: #0f172a;
        font-weight: 700;
        margin-top: 1.6em;
        margin-bottom: 0.4em;
        page-break-after: avoid;
    }

    h1 {
        font-size: 22pt;
        font-weight: 800;
        color: #0284c7;
        border-bottom: 2px solid #e2e8f0;
        padding-bottom: 6px;
        margin-top: 0;
    }

    h2 {
        font-size: 15pt;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 5px;
        margin-top: 1.8em;
        color: #0369a1;
    }

    h3 {
        font-size: 12pt;
        color: #334155;
        margin-top: 1.4em;
    }

    h4 {
        font-size: 10.5pt;
        color: #475569;
    }

    p, li {
        color: #334155;
        font-size: 9.8pt;
    }

    a {
        color: #0284c7;
        text-decoration: none;
    }

    hr {
        border: 0;
        border-top: 1px solid #cbd5e1;
        margin: 1.5em 0;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        margin: 1.2em 0;
        font-size: 9pt;
        page-break-inside: avoid;
    }

    th, td {
        border: 1px solid #cbd5e1;
        padding: 6px 9px;
        text-align: left;
        vertical-align: top;
    }

    th {
        background-color: #f1f5f9;
        font-weight: 600;
        color: #0f172a;
    }

    tr:nth-child(even) {
        background-color: #f8fafc;
    }

    code {
        font-family: 'JetBrains Mono', Consolas, Monaco, monospace;
        font-size: 8.5pt;
        background-color: #f1f5f9;
        color: #0f172a;
        padding: 2px 4px;
        border-radius: 3px;
        border: 1px solid #e2e8f0;
    }

    pre {
        background-color: #0f172a;
        color: #f8fafc;
        padding: 10px 14px;
        border-radius: 6px;
        overflow-x: auto;
        font-size: 8.5pt;
        line-height: 1.45;
        page-break-inside: avoid;
        margin: 0.9em 0;
    }

    pre code {
        background-color: transparent;
        color: #f8fafc;
        border: 0;
        padding: 0;
        font-size: 8.4pt;
    }

    blockquote {
        border-left: 4px solid #0284c7;
        background-color: #f0f9ff;
        padding: 8px 14px;
        margin: 1em 0;
        color: #0369a1;
        border-radius: 0 4px 4px 0;
        page-break-inside: avoid;
    }

    ul, ol {
        padding-left: 20px;
        margin: 0.4em 0 0.8em 0;
    }

    li {
        margin-bottom: 0.25em;
    }
    """

    doc_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>BusinessIntelligence.ai — Architecture & Framework</title>
    <style>
    {css}
    </style>
</head>
<body>
{html_body}
</body>
</html>
"""

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(doc_html)

    browser_exe = find_browser()
    print(f"[3/3] Printing PDF via Headless Edge ({browser_exe})...")

    abs_html_uri = HTML_PATH.resolve().as_uri()
    cmd = [
        browser_exe,
        "--headless",
        "--disable-gpu",
        "--run-all-compositor-stages-before-draw",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF_PATH}",
        abs_html_uri,
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Warning: browser exited with code {res.returncode}. Stderr: {res.stderr}")

    if PDF_PATH.exists():
        size = PDF_PATH.stat().st_size
        print(f"SUCCESS: Generated {PDF_PATH} ({size:,} bytes)")
        # Clean up temporary HTML
        if HTML_PATH.exists():
            HTML_PATH.unlink()
    else:
        raise RuntimeError("PDF generation failed.")


if __name__ == "__main__":
    convert()
