"""
frontend/theme.py — Visual system for BusinessIntelligence.ai

A single source of truth for the dark cinematic intelligence-terminal aesthetic:
colour tokens, global CSS, Altair chart theme, and small HTML primitives.

Design constraints
------------------
- Almost-black charcoal base, graphite surfaces, off-white type
- Muted gray-green as the secondary voice
- Semantic accents used sparingly and never neon
- Sharp geometry (2px radii), hairline borders, generous negative space
- Charts: thin luminous strokes, gradient fades, minimal axis decoration
"""
from __future__ import annotations

import altair as alt

# ─────────────────────────────────────────────────────────────────────────────
# Colour tokens
# ─────────────────────────────────────────────────────────────────────────────

BASE        = "#08090A"   # page background — almost-black charcoal
SURFACE     = "#0E1011"   # graphite panel
SURFACE_2   = "#141718"   # raised graphite
SURFACE_3   = "#191D1F"   # hover / active
HAIRLINE    = "#1C2123"   # primary border
HAIRLINE_2  = "#141819"   # faint gridline

TEXT        = "#E8EAE7"   # off-white
TEXT_DIM    = "#9BA5A0"   # muted gray-green
TEXT_MUTE   = "#6B7570"   # secondary gray-green
TEXT_FAINT  = "#454E4A"   # tertiary

# Semantic — restrained, desaturated
CRITICAL    = "#C4643E"   # muted rust — anomaly / fail
WARNING     = "#B4934E"   # muted brass — partial / stale
POSITIVE    = "#6E9B7A"   # muted sage — pass / healthy
NEUTRAL     = "#6B8AA5"   # muted steel — deterministic / info
COGNITIVE   = "#8A8CA8"   # muted slate — LLM (never a purple gradient)
SIMULATED   = "#7E8C93"   # muted slate-gray — simulated data

# Method-tag palette → (foreground, subtle background)
TAG_PALETTE: dict[str, tuple[str, str]] = {
    "SQL":                  (NEUTRAL,   "#12191F"),
    "STATS":                (POSITIVE,  "#101814"),
    "RULES":                (CRITICAL,  "#1A1210"),
    "RETRIEVAL":            (WARNING,   "#191510"),
    "LLM":                  (COGNITIVE, "#15151C"),
    "LLM_NARRATIVE":        (COGNITIVE, "#15151C"),
    "RULES+LLM_NARRATIVE":  (COGNITIVE, "#181418"),
    "SIMULATED":            (SIMULATED, "#141719"),
    "ETL":                  ("#5E9A93", "#101817"),
}

CONFIDENCE_PALETTE: dict[str, str] = {
    "high":    POSITIVE,
    "medium":  WARNING,
    "low":     CRITICAL,
    "abstain": SIMULATED,
}

VERDICT_PALETTE: dict[str, tuple[str, str]] = {
    # verdict → (glyph, colour)
    "pass":    ("✓", POSITIVE),
    "partial": ("◐", WARNING),
    "fail":    ("✕", CRITICAL),
}

MONO = "'JetBrains Mono','SF Mono',ui-monospace,'Cascadia Mono',Menlo,monospace"
SANS = "'Inter',-apple-system,'Segoe UI',system-ui,sans-serif"


# ─────────────────────────────────────────────────────────────────────────────
# Global CSS
# ─────────────────────────────────────────────────────────────────────────────

def global_css() -> str:
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ── Canvas ─────────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
    background: {BASE};
    color: {TEXT};
    font-family: {SANS};
    -webkit-font-smoothing: antialiased;
}}
[data-testid="stAppViewContainer"] > .main {{ background: {BASE}; }}
.block-container {{ padding-top: 2.2rem !important; padding-bottom: 3rem !important; max-width: 1500px; }}

/* ── Strip Streamlit chrome ─────────────────────────────── */
#MainMenu, footer, header, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{
    display: none !important;
}}
[data-testid="stToolbar"] {{ display: none !important; }}

/* ── Sidebar ────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
    background: {SURFACE};
    border-right: 1px solid {HAIRLINE};
    width: 268px !important;
}}
[data-testid="stSidebar"] > div {{ padding-top: 1.4rem; }}
[data-testid="stSidebar"] * {{ color: {TEXT_DIM}; }}

/* ── Typography ─────────────────────────────────────────── */
h1,h2,h3,h4,h5,h6 {{ font-family: {SANS}; letter-spacing: -0.011em; color: {TEXT}; }}
code, kbd, samp, pre {{ font-family: {MONO} !important; font-size: 0.78rem !important; }}
.mono {{ font-family: {MONO}; font-variant-numeric: tabular-nums; }}

/* ── Tab navigation → thin instrument nav ───────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    gap: 0;
    background: transparent;
    border-bottom: 1px solid {HAIRLINE};
    padding: 0;
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
    background: transparent !important;
    border: none !important;
    color: {TEXT_MUTE} !important;
    font-size: 0.68rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.11em;
    text-transform: uppercase;
    padding: 11px 17px !important;
    transition: color .16s ease;
}}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {{ color: {TEXT_DIM} !important; }}
[data-testid="stTabs"] [aria-selected="true"] {{
    color: {TEXT} !important;
    box-shadow: inset 0 -1px 0 0 {TEXT};
}}
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] {{ display: none !important; }}
[data-testid="stTabs"] [data-baseweb="tab-panel"] {{ padding-top: 30px; }}

/* ── Buttons ────────────────────────────────────────────── */
[data-testid="stButton"] button {{
    border-radius: 2px !important;
    font-family: {SANS} !important;
    font-size: 0.73rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    padding: 9px 18px !important;
    transition: all .16s ease;
}}
[data-testid="stButton"] button[kind="primary"] {{
    background: {SURFACE_2} !important;
    color: {TEXT} !important;
    border: 1px solid #2E3538 !important;
}}
[data-testid="stButton"] button[kind="primary"]:hover {{
    background: {SURFACE_3} !important;
    border-color: {TEXT_MUTE} !important;
}}
[data-testid="stButton"] button[kind="secondary"] {{
    background: transparent !important;
    color: {TEXT_MUTE} !important;
    border: 1px solid {HAIRLINE} !important;
}}

/* ── Expanders → padded hairline data regions ───────────── */
[data-testid="stExpander"] {{
    background: transparent !important;
    border: none !important;
    margin-bottom: 7px !important;
}}
[data-testid="stExpander"] details {{
    background: {SURFACE} !important;
    border: 1px solid {HAIRLINE} !important;
    border-radius: 2px !important;
}}
[data-testid="stExpander"] details[open] {{ background: {SURFACE} !important; }}
[data-testid="stExpander"] details > summary {{
    padding: 14px 22px !important;
    font-size: 0.81rem !important;
    color: {TEXT_DIM} !important;
    font-family: {MONO} !important;
    letter-spacing: 0.01em;
    transition: color .15s ease, background .15s ease;
}}
[data-testid="stExpander"] details > summary:hover {{
    color: {TEXT} !important;
    background: {SURFACE_2} !important;
}}
[data-testid="stExpander"] details[open] > summary {{
    border-bottom: 1px solid {HAIRLINE} !important;
}}
[data-testid="stExpander"] summary p {{
    font-size: 0.81rem !important;
    font-family: {MONO} !important;
}}
[data-testid="stExpander"] svg {{ fill: {TEXT_FAINT} !important; }}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
    padding: 20px 22px 22px !important;
}}
/* Sidebar expanders sit in a narrower rail — tighten to match */
[data-testid="stSidebar"] [data-testid="stExpander"] details > summary {{
    padding: 11px 14px !important;
}}
[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
    padding: 14px 14px 16px !important;
}}

/* ── Metrics → bare instrument readouts ─────────────────── */
[data-testid="stMetric"] {{
    background: transparent;
    border: none;
    border-left: 1px solid {HAIRLINE};
    padding: 2px 0 2px 14px;
}}
[data-testid="stMetricLabel"] {{
    color: {TEXT_MUTE} !important;
    font-size: 0.63rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}}
[data-testid="stMetricLabel"] p {{ font-size: 0.63rem !important; }}
[data-testid="stMetricValue"] {{
    color: {TEXT} !important;
    font-family: {MONO} !important;
    font-size: 1.22rem !important;
    font-weight: 500 !important;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.01em;
}}

/* ── Inputs ─────────────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stTextArea"] textarea {{
    background: {SURFACE_2} !important;
    border: 1px solid {HAIRLINE} !important;
    border-radius: 2px !important;
    color: {TEXT} !important;
    font-size: 0.81rem !important;
}}
[data-testid="stTextArea"] textarea:focus,
[data-testid="stSelectbox"] > div > div:focus-within {{
    border-color: {TEXT_MUTE} !important;
    box-shadow: none !important;
}}
[data-testid="stRadio"] label {{ font-size: 0.79rem !important; color: {TEXT_DIM} !important; }}
[data-testid="stRadio"] [data-baseweb="radio"] div:first-child {{
    background: {SURFACE_2} !important;
    border-color: {HAIRLINE} !important;
}}

/* ── Tables → dense terminal grid ───────────────────────── */
[data-testid="stDataFrame"] {{
    background: transparent;
    border: 1px solid {HAIRLINE};
    border-radius: 2px;
}}
[data-testid="stDataFrame"] [role="columnheader"] {{
    background: {SURFACE} !important;
    color: {TEXT_MUTE} !important;
    font-size: 0.63rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    border-color: {HAIRLINE} !important;
}}
[data-testid="stDataFrame"] [role="gridcell"] {{
    background: transparent !important;
    color: {TEXT_DIM} !important;
    font-family: {MONO} !important;
    font-size: 0.76rem !important;
    border-color: {HAIRLINE_2} !important;
}}

/* ── Charts blend into the canvas ───────────────────────── */
.vega-embed, .vega-embed canvas, [data-testid="stVegaLiteChart"] {{
    background: transparent !important;
}}
.vega-embed summary {{ display: none !important; }}
.vega-embed .vega-actions {{ display: none !important; }}
/* Fullscreen affordance intrudes on the plot — keep it, but only on hover */
[data-testid="stElementToolbar"], [data-testid="StyledFullScreenButton"] {{
    opacity: 0 !important;
    transition: opacity .18s ease;
}}
[data-testid="stVegaLiteChart"]:hover ~ [data-testid="stElementToolbar"],
[data-testid="stElementToolbar"]:hover,
[data-testid="StyledFullScreenButton"]:hover {{ opacity: .8 !important; }}
[data-testid="stElementToolbar"] {{
    background: {SURFACE_2} !important;
    border: 1px solid {HAIRLINE} !important;
    border-radius: 2px !important;
}}

/* ── Spinner / alerts ───────────────────────────────────── */
[data-testid="stSpinner"] > div {{ border-top-color: {TEXT_MUTE} !important; }}
[data-testid="stSpinner"] p {{ color: {TEXT_MUTE} !important; font-size: 0.79rem !important; }}
[data-testid="stAlert"] {{
    background: {SURFACE_2} !important;
    border: 1px solid {HAIRLINE} !important;
    border-radius: 2px !important;
    color: {TEXT_DIM} !important;
    font-size: 0.81rem !important;
}}

/* ── Scrollbars ─────────────────────────────────────────── */
::-webkit-scrollbar {{ width: 3px; height: 3px; }}
::-webkit-scrollbar-track {{ background: {BASE}; }}
::-webkit-scrollbar-thumb {{ background: #262D30; }}
::-webkit-scrollbar-thumb:hover {{ background: {TEXT_FAINT}; }}

/* ── Dividers ───────────────────────────────────────────── */
hr {{ border: none !important; border-top: 1px solid {HAIRLINE} !important; margin: 22px 0 !important; }}

/* ── Tooltip (Vega) ─────────────────────────────────────── */
#vg-tooltip-element {{
    background: {SURFACE_2} !important;
    border: 1px solid #2A3134 !important;
    border-radius: 2px !important;
    color: {TEXT} !important;
    font-family: {MONO} !important;
    font-size: 0.71rem !important;
    padding: 8px 11px !important;
    box-shadow: 0 8px 28px rgba(0,0,0,.6) !important;
}}
#vg-tooltip-element td.key {{ color: {TEXT_MUTE} !important; padding-right: 10px !important; }}
#vg-tooltip-element td.value {{ color: {TEXT} !important; }}
#vg-tooltip-element h2 {{
    color: {TEXT} !important; font-size: 0.74rem !important;
    margin: 0 0 5px !important; font-family: {SANS} !important;
}}
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Altair theme
# ─────────────────────────────────────────────────────────────────────────────

def axis_x(title: str | None = None, labels: bool = True, grid: bool = False) -> alt.Axis:
    return alt.Axis(
        title=title,
        labels=labels,
        grid=grid,
        gridColor=HAIRLINE_2,
        gridWidth=1,
        gridDash=[2, 4],
        domain=False,
        ticks=False,
        labelColor=TEXT_MUTE,
        labelFontSize=9,
        labelFont=MONO,
        labelPadding=8,
        titleColor=TEXT_FAINT,
        titleFontSize=9,
        titleFont=SANS,
        titleFontWeight=500,
        titlePadding=14,
        labelAngle=0,
    )


def axis_y(title: str | None = None, labels: bool = True, grid: bool = True) -> alt.Axis:
    return alt.Axis(
        title=title,
        labels=labels,
        grid=grid,
        gridColor=HAIRLINE_2,
        gridWidth=1,
        gridDash=[2, 4],
        domain=False,
        ticks=False,
        labelColor=TEXT_MUTE,
        labelFontSize=9,
        labelFont=MONO,
        labelPadding=10,
        titleColor=TEXT_FAINT,
        titleFontSize=9,
        titleFont=SANS,
        titleFontWeight=500,
        titlePadding=16,
    )


def finalize(chart: alt.Chart, height: int = 200) -> alt.Chart:
    """Apply the shared view configuration so charts dissolve into the canvas."""
    return (
        chart.properties(height=height, background="transparent")
        .configure_view(strokeWidth=0, fill="transparent")
        .configure_axis(labelFont=MONO, titleFont=SANS)
        .configure_legend(
            labelColor=TEXT_DIM,
            labelFontSize=9,
            labelFont=MONO,
            titleColor=TEXT_FAINT,
            titleFontSize=9,
            titleFont=SANS,
            titleFontWeight=500,
            symbolStrokeWidth=0,
            symbolSize=52,
            orient="top",
            direction="horizontal",
            offset=6,
            padding=0,
        )
    )


def fade(color: str, to: str = BASE) -> alt.Gradient:
    """Vertical gradient from *color* down into the page background."""
    return alt.Gradient(
        gradient="linear",
        stops=[
            alt.GradientStop(color=color, offset=0),
            alt.GradientStop(color=to, offset=1),
        ],
        x1=1, x2=1, y1=0, y2=1,
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTML primitives
# ─────────────────────────────────────────────────────────────────────────────

def tag(label: str) -> str:
    fg, bg = TAG_PALETTE.get(label.upper(), (TEXT_MUTE, SURFACE_2))
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};'
        f'border:1px solid {fg}28;border-radius:2px;padding:1px 6px;'
        f'font-family:{MONO};font-size:0.62rem;font-weight:500;'
        f'letter-spacing:0.07em;line-height:1.6;white-space:nowrap">{label}</span>'
    )


def eyebrow(text: str, color: str = TEXT_MUTE) -> str:
    return (
        f'<div style="color:{color};font-size:0.62rem;font-weight:600;'
        f'letter-spacing:0.13em;text-transform:uppercase;margin-bottom:9px">{text}</div>'
    )


def num(value: str, color: str = TEXT, size: str = "1.24rem") -> str:
    return (
        f'<span style="font-family:{MONO};font-variant-numeric:tabular-nums;'
        f'color:{color};font-size:{size};font-weight:500;letter-spacing:-0.01em">{value}</span>'
    )


def dot(color: str, glow: bool = False) -> str:
    shadow = f"box-shadow:0 0 7px {color}99;" if glow else ""
    return (
        f'<span style="display:inline-block;width:5px;height:5px;border-radius:50%;'
        f'background:{color};{shadow}vertical-align:middle"></span>'
    )


def section(title: str, note: str = "", index: str = "") -> str:
    idx = (
        f'<span style="font-family:{MONO};color:{TEXT_FAINT};font-size:0.78rem;'
        f'margin-right:11px;font-weight:400">{index}</span>' if index else ""
    )
    sub = (
        f'<p style="color:{TEXT_MUTE};font-size:0.78rem;line-height:1.55;'
        f'margin:5px 0 0;max-width:760px">{note}</p>' if note else ""
    )
    return (
        f'<div style="margin-bottom:26px">'
        f'<div style="display:flex;align-items:baseline">'
        f'{idx}<h2 style="font-size:1.04rem;font-weight:600;margin:0;color:{TEXT}">{title}</h2>'
        f'</div>{sub}</div>'
    )


def panel(inner: str, pad: str = "17px 19px", accent: str | None = None) -> str:
    left = f"border-left:2px solid {accent};" if accent else ""
    return (
        f'<div style="background:{SURFACE};border:1px solid {HAIRLINE};{left}'
        f'border-radius:2px;padding:{pad}">{inner}</div>'
    )


def kv_row(key: str, value: str, value_color: str = TEXT) -> str:
    return (
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
        f'padding:5px 0;border-bottom:1px solid {HAIRLINE_2}">'
        f'<span style="color:{TEXT_MUTE};font-size:0.73rem">{key}</span>'
        f'<span style="font-family:{MONO};font-variant-numeric:tabular-nums;'
        f'color:{value_color};font-size:0.75rem">{value}</span></div>'
    )


def kv_block(rows: str, max_width: int = 440) -> str:
    """Constrain a run of kv_row()s so key and value stay visually paired
    instead of being flung to opposite edges of a wide container."""
    return f'<div style="max-width:{max_width}px">{rows}</div>'


def meter(pct: float, color: str, height: int = 3) -> str:
    w = max(0.0, min(100.0, pct))
    return (
        f'<div style="background:{HAIRLINE};height:{height}px;border-radius:1px;overflow:hidden">'
        f'<div style="width:{w}%;height:100%;background:{color};'
        f'box-shadow:0 0 8px {color}66"></div></div>'
    )
