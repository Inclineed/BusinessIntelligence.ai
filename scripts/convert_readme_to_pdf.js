/**
 * scripts/convert_readme_to_pdf.js
 * Converts README.md into an executive-grade PDF with server-side KaTeX math rendering.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const katex = require('./katex/katex.min.js');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const README_PATH = path.join(PROJECT_ROOT, 'README.md');
const HTML_PATH = path.join(PROJECT_ROOT, 'README.html');
const PDF_PATH = path.join(PROJECT_ROOT, 'README.pdf');
const KATEX_CSS_PATH = path.join(__dirname, 'katex', 'katex.min.css');

const EDGE_CANDIDATES = [
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
];

function findBrowser() {
    for (const candidate of EDGE_CANDIDATES) {
        if (fs.existsSync(candidate)) {
            return candidate;
        }
    }
    throw new Error('No Chromium-based headless browser (Edge/Chrome) found on system.');
}

function renderMath(formula, displayMode) {
    try {
        return katex.renderToString(formula.trim(), {
            displayMode: displayMode,
            throwOnError: false,
            strict: false
        });
    } catch (err) {
        console.warn('KaTeX render warning for:', formula, err.message);
        return `<span class="math-fallback">${formula}</span>`;
    }
}

function convertMarkdownToHtml(rawMd) {
    const mathPlaceholders = [];

    // 1. Extract Display Math $$...$$
    let protectedMd = rawMd.replace(/\$\$([\s\S]*?)\$\$/g, (match, formula) => {
        const idx = mathPlaceholders.length;
        const rendered = renderMath(formula, true);
        mathPlaceholders.push(`<div class="math-display">${rendered}</div>`);
        return `@@@MATH_PLACEHOLDER_${idx}@@@`;
    });

    // 2. Extract Inline Math $...$ (ensuring not currency $100)
    // Matches $...$ where opening $ is not followed by space/digit/dollar, and closing $ is not preceded by space
    protectedMd = protectedMd.replace(/(?<!\$)\$(?!\$)([\S](?:[\s\S]*?[\S])?)\$(?!\$)/g, (match, formula) => {
        // Skip pure currency like $10 or $2,005 or $0.59
        if (/^[\d,.]+(?:\/1[MK]|\s*USD|\s*k)?$/i.test(formula.trim())) {
            return match;
        }
        const idx = mathPlaceholders.length;
        const rendered = renderMath(formula, false);
        mathPlaceholders.push(`<span class="math-inline">${rendered}</span>`);
        return `@@@MATH_PLACEHOLDER_${idx}@@@`;
    });

    // 3. Convert markdown via Python markdown with tables, fenced code, and codehilite
    const tempMdPath = path.join(__dirname, '_temp_protected.md');
    const tempHtmlBodyPath = path.join(__dirname, '_temp_body.html');
    fs.writeFileSync(tempMdPath, protectedMd, 'utf8');

    execSync(`python -c "import markdown; text = open(r'${tempMdPath}', encoding='utf-8').read(); html = markdown.markdown(text, extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists']); open(r'${tempHtmlBodyPath}', 'w', encoding='utf-8').write(html)"`, { stdio: 'inherit' });

    let htmlBody = fs.readFileSync(tempHtmlBodyPath, 'utf8');

    // Clean up temp files
    if (fs.existsSync(tempMdPath)) fs.unlinkSync(tempMdPath);
    if (fs.existsSync(tempHtmlBodyPath)) fs.unlinkSync(tempHtmlBodyPath);

    // 4. Restore rendered KaTeX math blocks
    htmlBody = htmlBody.replace(/@@@MATH_PLACEHOLDER_(\d+)@@@/g, (match, idxStr) => {
        const idx = parseInt(idxStr, 10);
        return mathPlaceholders[idx] || match;
    });

    return htmlBody;
}

function main() {
    console.log('[1/4] Reading README.md...');
    const rawMd = fs.readFileSync(README_PATH, 'utf8');

    console.log('[2/4] Pre-rendering LaTeX equations via KaTeX and compiling Markdown...');
    const htmlBody = convertMarkdownToHtml(rawMd);

    const katexCss = fs.readFileSync(KATEX_CSS_PATH, 'utf8');

    const cssStyles = `
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    ${katexCss}

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
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        color: #1e293b;
        background: #ffffff;
        line-height: 1.55;
        font-size: 9.8pt;
        margin: 0;
        padding: 0;
    }

    h1, h2, h3, h4, h5, h6 {
        color: #0f172a;
        font-weight: 700;
        margin-top: 1.5em;
        margin-bottom: 0.4em;
        page-break-after: avoid;
    }

    h1 {
        font-size: 21pt;
        font-weight: 800;
        color: #0284c7;
        border-bottom: 2px solid #e2e8f0;
        padding-bottom: 6px;
        margin-top: 0;
    }

    h2 {
        font-size: 14.5pt;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 5px;
        margin-top: 1.7em;
        color: #0369a1;
    }

    h3 {
        font-size: 11.5pt;
        color: #334155;
        margin-top: 1.3em;
    }

    h4 {
        font-size: 10.2pt;
        color: #475569;
    }

    p, li {
        color: #334155;
        font-size: 9.5pt;
    }

    a {
        color: #0284c7;
        text-decoration: none;
    }

    hr {
        border: 0;
        border-top: 1px solid #cbd5e1;
        margin: 1.4em 0;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        margin: 1.1em 0;
        font-size: 8.8pt;
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
        font-size: 8.4pt;
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
        font-size: 8.4pt;
        line-height: 1.45;
        page-break-inside: avoid;
        margin: 0.9em 0;
    }

    pre code {
        background-color: transparent;
        color: #f8fafc;
        border: 0;
        padding: 0;
        font-size: 8.3pt;
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

    .math-display {
        margin: 0.9em 0;
        text-align: center;
        page-break-inside: avoid;
    }

    .katex {
        font-size: 1.05em !important;
        font-family: KaTeX_Main, 'Times New Roman', serif;
    }
    .katex-display {
        margin: 0.5em 0 !important;
    }
    `;

    const fullHtml = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>BusinessIntelligence.ai — Architecture & Framework</title>
    <style>
    ${cssStyles}
    </style>
</head>
<body>
${htmlBody}
</body>
</html>`;

    console.log('[3/4] Writing HTML with static KaTeX formulas...');
    fs.writeFileSync(HTML_PATH, fullHtml, 'utf8');

    const browserExe = findBrowser();
    console.log(`[4/4] Printing PDF via Headless Browser (${browserExe})...`);

    const absHtmlUri = 'file:///' + HTML_PATH.replace(/\\/g, '/');
    const cmd = `"${browserExe}" --headless --disable-gpu --run-all-compositor-stages-before-draw --no-pdf-header-footer --print-to-pdf="${PDF_PATH}" "${absHtmlUri}"`;

    execSync(cmd, { stdio: 'inherit' });

    if (fs.existsSync(PDF_PATH)) {
        const size = fs.statSync(PDF_PATH).size;
        console.log(`\nSUCCESS: Generated ${PDF_PATH} (${size.toLocaleString()} bytes) with rendered LaTeX formulas!`);
        if (fs.existsSync(HTML_PATH)) fs.unlinkSync(HTML_PATH);
    } else {
        throw new Error('PDF output file was not created.');
    }
}

main();
