"""
frontend/app.py — BusinessIntelligence.ai · operational console

A dark, chart-first intelligence terminal over the FastAPI backend.
Visual system lives in frontend/theme.py. This module owns render logic only.

API-only: imports no pipeline code.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import altair as alt
import httpx
import pandas as pd
import streamlit as st

try:  # Streamlit puts the script's directory on sys.path
    import theme as T
except ModuleNotFoundError:  # invoked as a package module
    from frontend import theme as T  # type: ignore[no-redef]

# ─────────────────────────────────────────────────────────────────────────────
# Page shell
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="BusinessIntelligence.ai",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(T.global_css(), unsafe_allow_html=True)

BASE_URL: str = os.environ.get("API_URL", "http://localhost:8080")
TIMEOUT: float = 600.0

DET_TAGS = {"SQL", "STATS", "RULES", "ETL"}
LLM_ENGINES = {"hypothesis", "decision", "memory", "challenge"}

RULE_ORDER = [
    "timeline",
    "segment_alignment",
    "kpi_corroboration",
    "mechanism_consistency",
    "contradiction",
]
RULE_SHORT = {
    "timeline": "TIME",
    "segment_alignment": "SEGMENT",
    "kpi_corroboration": "CORROB",
    "mechanism_consistency": "MECHANISM",
    "contradiction": "CONTRA",
}


# ─────────────────────────────────────────────────────────────────────────────
# Small formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _f(v: Any, prec: int = 2, signed: bool = False) -> str:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return "—"
    return f"{v:+.{prec}f}" if signed else f"{v:.{prec}f}"


def _short(v: Any, n: int = 12) -> str:
    s = str(v or "—")
    return s if len(s) <= n else s[:n] + "…"


def _clean(text: str) -> str:
    for tagname in ("[LLM_NARRATIVE]", "[LLM]", "[SIMULATED]", "[RULES]"):
        text = text.replace(tagname, "")
    return text.strip()


def _gap(px: int = 26) -> None:
    st.markdown(f'<div style="height:{px}px"></div>', unsafe_allow_html=True)


def _empty(msg: str) -> None:
    st.markdown(
        f'<div style="border-left:1px solid {T.HAIRLINE};padding:16px 0 16px 16px;'
        f'color:{T.TEXT_FAINT};font-size:0.8rem">{msg}</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────────────────────

def _call_investigate(scenario_id: str, persona: str) -> tuple[Optional[dict], Optional[str]]:
    try:
        resp = httpx.post(
            f"{BASE_URL}/investigate",
            json={"scenario_id": scenario_id, "persona": persona},
            timeout=TIMEOUT,
        )
    except httpx.ConnectError:
        return None, f"Cannot reach the API at {BASE_URL}. Is the FastAPI server running?"
    except httpx.TimeoutException:
        return None, f"Request timed out after {TIMEOUT:.0f}s — pipeline may still be running."
    except Exception as exc:  # noqa: BLE001
        return None, f"Unexpected error: {exc}"

    if resp.status_code == 403:
        return resp.json(), None
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:  # noqa: BLE001
            detail = resp.text
        return None, f"API error {resp.status_code}: {detail}"
    return resp.json(), None


def _get_scenarios() -> list[dict]:
    fallback = [{"id": "INC_001", "status": "live", "label": "Checkout / Payment Degradation"}]
    try:
        resp = httpx.get(f"{BASE_URL}/scenarios", timeout=8.0)
        if resp.status_code == 200:
            items = resp.json().get("scenarios", []) or []
            norm: list[dict] = []
            for it in items:
                if isinstance(it, str):
                    norm.append({"id": it, "status": "live", "label": it})
                elif isinstance(it, dict) and it.get("id"):
                    norm.append({
                        "id": it["id"],
                        "status": it.get("status", "live"),
                        "label": it.get("label", it["id"]),
                    })
            return norm or fallback
    except Exception:  # noqa: BLE001
        pass
    return fallback


# ─────────────────────────────────────────────────────────────────────────────
# Charts — the visual identity
# ─────────────────────────────────────────────────────────────────────────────

def _chart_deviation(signals: list[dict]) -> Optional[alt.LayerChart]:
    """Horizontal lollipop of z-scores against the ±3σ decision threshold."""
    rows = [
        {
            "kpi": s.get("kpi_id", "—"),
            "z": float(s.get("z_score") or 0.0),
            "anomaly": bool(s.get("is_anomaly")),
            "delta": float(s.get("delta_pct") or 0.0),
            "observed": s.get("observed"),
            "expected": s.get("expected"),
        }
        for s in signals
        if isinstance(s.get("z_score"), (int, float))
    ]
    if not rows:
        return None

    df = pd.DataFrame(rows).sort_values("z")
    order = df["kpi"].tolist()
    span = max(3.6, df["z"].abs().max() * 1.22)
    dom = [-span, span]
    height = max(96, 34 * len(df))

    base = alt.Chart(df)

    # Confidence corridor: the region where deviation is statistically unremarkable
    corridor = (
        alt.Chart(pd.DataFrame({"lo": [-3.0], "hi": [3.0]}))
        .mark_rect(fill=T.SURFACE_2, opacity=0.5)
        .encode(x=alt.X("lo:Q", scale=alt.Scale(domain=dom)), x2="hi:Q")
    )
    thresholds = (
        alt.Chart(pd.DataFrame({"t": [-3.0, 3.0]}))
        .mark_rule(color=T.HAIRLINE, strokeWidth=1, strokeDash=[3, 4])
        .encode(x="t:Q")
    )
    zero = (
        alt.Chart(pd.DataFrame({"t": [0.0]}))
        .mark_rule(color="#2B3235", strokeWidth=1)
        .encode(x="t:Q")
    )

    stem = base.mark_rule(strokeWidth=1, opacity=0.55).encode(
        x=alt.X("z:Q", scale=alt.Scale(domain=dom), axis=T.axis_x("z-score (σ from expected)", grid=False)),
        x2=alt.datum(0),
        y=alt.Y("kpi:N", sort=order, axis=T.axis_y(None, grid=False)),
        color=alt.Color(
            "anomaly:N",
            scale=alt.Scale(domain=[True, False], range=[T.CRITICAL, T.TEXT_FAINT]),
            legend=None,
        ),
    )
    halo = base.transform_filter(alt.datum.anomaly).mark_point(
        filled=True, size=290, opacity=0.13, color=T.CRITICAL
    ).encode(x="z:Q", y=alt.Y("kpi:N", sort=order))
    halo_inner = base.transform_filter(alt.datum.anomaly).mark_point(
        filled=True, size=120, opacity=0.26, color=T.CRITICAL
    ).encode(x="z:Q", y=alt.Y("kpi:N", sort=order))

    marker = base.mark_point(filled=True, size=46).encode(
        x="z:Q",
        y=alt.Y("kpi:N", sort=order),
        color=alt.Color(
            "anomaly:N",
            scale=alt.Scale(domain=[True, False], range=[T.CRITICAL, T.TEXT_MUTE]),
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("kpi:N", title="KPI"),
            alt.Tooltip("z:Q", title="z-score", format="+.3f"),
            alt.Tooltip("delta:Q", title="delta %", format="+.2f"),
            alt.Tooltip("observed:Q", title="observed", format=".4f"),
            alt.Tooltip("expected:Q", title="expected", format=".4f"),
            alt.Tooltip("anomaly:N", title="anomaly"),
        ],
    )

    layered = alt.layer(
        corridor, thresholds, zero, stem, halo, halo_inner, marker
    ).resolve_scale(color="independent")
    return T.finalize(layered, height=height)


def _chart_contribution(sub: pd.DataFrame) -> alt.LayerChart:
    """Narrow horizontal bars + cumulative concentration trace for one dimension."""
    sub = sub.sort_values("contribution_pct", ascending=False).reset_index(drop=True)
    sub["cum"] = sub["contribution_pct"].cumsum()
    sub["dominant"] = [i == 0 for i in range(len(sub))]
    order = sub["segment"].tolist()
    height = max(88, 30 * len(sub))

    bar = (
        alt.Chart(sub)
        .mark_bar(height=9, cornerRadius=0)
        .encode(
            x=alt.X("contribution_pct:Q", title=None,
                    axis=T.axis_x("share of variance %", grid=True),
                    scale=alt.Scale(domain=[0, max(100.0, float(sub["contribution_pct"].max()) * 1.1)])),
            y=alt.Y("segment:N", sort=order, axis=T.axis_y(None, grid=False)),
            color=alt.Color(
                "dominant:N",
                scale=alt.Scale(domain=[True, False], range=[T.CRITICAL, "#2E3639"]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("segment:N", title="Segment"),
                alt.Tooltip("contribution_pct:Q", title="Contribution %", format=".2f"),
                alt.Tooltip("segment_delta_pct:Q", title="Segment Δ%", format="+.2f"),
                alt.Tooltip("cum:Q", title="Cumulative %", format=".1f"),
            ],
        )
    )
    label = (
        alt.Chart(sub)
        .mark_text(align="left", dx=9, font=T.MONO, fontSize=9, color=T.TEXT_DIM)
        .encode(
            x="contribution_pct:Q",
            y=alt.Y("segment:N", sort=order),
            text=alt.Text("contribution_pct:Q", format=".1f"),
        )
    )
    trace = (
        alt.Chart(sub)
        .mark_line(strokeWidth=1, color=T.NEUTRAL, opacity=0.45, strokeDash=[2, 3],
                   point=alt.OverlayMarkDef(size=18, filled=True, color=T.NEUTRAL, opacity=0.7))
        .encode(x="cum:Q", y=alt.Y("segment:N", sort=order))
    )
    return T.finalize(alt.layer(bar, trace, label), height=height)


def _chart_evidence_field(evidence: list[dict]) -> Optional[alt.LayerChart]:
    """Reliability × relevance field with quadrant guides. Retrieval as intelligence triage."""
    rows = [
        {
            "id": (e.get("evidence_id") or "?")[:14],
            "reliability": float(e.get("reliability_weight") or 0.0),
            "relevance": float(e.get("relevance") or 0.0),
            "source": e.get("source_id", "—"),
            "kind": (e.get("kind") or "—").upper(),
            "method": (e.get("method") or "—").upper(),
            "summary": _short(_clean(str(e.get("summary") or "")), 90),
        }
        for e in evidence
    ]
    if not rows:
        return None
    df = pd.DataFrame(rows)

    guide_v = (
        alt.Chart(pd.DataFrame({"x": [0.85]}))
        .mark_rule(color=T.HAIRLINE, strokeWidth=1, strokeDash=[3, 4])
        .encode(x=alt.X("x:Q", scale=alt.Scale(domain=[0, 1.04])))
    )
    guide_h = (
        alt.Chart(pd.DataFrame({"y": [0.5]}))
        .mark_rule(color=T.HAIRLINE, strokeWidth=1, strokeDash=[3, 4])
        .encode(y=alt.Y("y:Q", scale=alt.Scale(domain=[0, 1.04])))
    )

    base = alt.Chart(df)
    enc = dict(
        x=alt.X("reliability:Q", scale=alt.Scale(domain=[0, 1.04]),
                axis=T.axis_x("source reliability", grid=True)),
        y=alt.Y("relevance:Q", scale=alt.Scale(domain=[0, 1.04]),
                axis=T.axis_y("relevance to signal", grid=True)),
    )
    halo = base.mark_point(filled=True, size=230, opacity=0.10).encode(
        **enc,
        color=alt.Color("method:N",
                        scale=alt.Scale(domain=["SQL", "RETRIEVAL", "LLM"],
                                        range=[T.NEUTRAL, T.WARNING, T.COGNITIVE]),
                        legend=None),
    )
    pts = base.mark_point(filled=True, size=54, strokeWidth=0).encode(
        **enc,
        color=alt.Color("method:N",
                        scale=alt.Scale(domain=["SQL", "RETRIEVAL", "LLM"],
                                        range=[T.NEUTRAL, T.WARNING, T.COGNITIVE]),
                        legend=alt.Legend(title=None)),
        tooltip=[
            alt.Tooltip("id:N", title="Evidence"),
            alt.Tooltip("source:N", title="Source"),
            alt.Tooltip("kind:N", title="Kind"),
            alt.Tooltip("reliability:Q", title="Reliability", format=".3f"),
            alt.Tooltip("relevance:Q", title="Relevance", format=".3f"),
            alt.Tooltip("summary:N", title="Summary"),
        ],
    )
    return T.finalize(alt.layer(guide_v, guide_h, halo, pts), height=272)


def _chart_hypothesis_scores(scored: list[dict], stmt_by_id: dict[str, str]) -> Optional[alt.LayerChart]:
    """Final scores against the deterministic MEDIUM (0.40) / HIGH (0.70) gates."""
    rows = [
        {
            "hid": s.get("hypothesis_id", "?"),
            "score": float(s.get("final_score") or 0.0),
            "support": float(s.get("support_score") or 0.0),
            "penalty": float(s.get("contradiction_penalty") or 0.0),
            "state": (s.get("confidence_state") or "low").lower(),
            "stmt": _short(stmt_by_id.get(s.get("hypothesis_id", ""), ""), 78),
        }
        for s in scored
    ]
    if not rows:
        return None
    df = pd.DataFrame(rows).sort_values("score", ascending=False)
    df["full"] = 1.0
    order = df["hid"].tolist()
    height = max(112, 46 * len(df))

    states = ["high", "medium", "low", "abstain"]
    colors = [T.CONFIDENCE_PALETTE[s] for s in states]
    xs = alt.Scale(domain=[0, 1.0], nice=False, clamp=True)

    # Gate rules only — the labels live in the caption beneath the chart so they
    # can never collide with the top bar.
    gates = (
        alt.Chart(pd.DataFrame({"g": [0.40, 0.70]}))
        .mark_rule(color="#2B3235", strokeWidth=1, strokeDash=[3, 4])
        .encode(x=alt.X("g:Q", scale=xs))
    )
    track = (
        alt.Chart(df)
        .mark_bar(height=7, color=T.HAIRLINE_2)
        .encode(
            x=alt.X("full:Q", scale=xs, axis=T.axis_x("final score", grid=True)),
            y=alt.Y("hid:N", sort=order, axis=T.axis_y(None, grid=False)),
        )
    )
    bar = (
        alt.Chart(df)
        .mark_bar(height=7)
        .encode(
            x=alt.X("score:Q", scale=xs, axis=T.axis_x("final score", grid=True)),
            y=alt.Y("hid:N", sort=order, axis=T.axis_y(None, grid=False)),
            color=alt.Color("state:N", scale=alt.Scale(domain=states, range=colors), legend=None),
            tooltip=[
                alt.Tooltip("hid:N", title="Hypothesis"),
                alt.Tooltip("stmt:N", title="Statement"),
                alt.Tooltip("score:Q", title="Final score", format=".3f"),
                alt.Tooltip("support:Q", title="Support", format=".3f"),
                alt.Tooltip("penalty:Q", title="Penalty", format=".3f"),
                alt.Tooltip("state:N", title="Confidence"),
            ],
        )
    )
    tip = (
        alt.Chart(df)
        .mark_point(filled=True, size=40)
        .encode(
            x=alt.X("score:Q", scale=xs),
            y=alt.Y("hid:N", sort=order),
            color=alt.Color("state:N", scale=alt.Scale(domain=states, range=colors), legend=None),
        )
    )
    val = (
        alt.Chart(df)
        .mark_text(align="left", dx=11, font=T.MONO, fontSize=9, color=T.TEXT_DIM)
        .encode(x=alt.X("score:Q", scale=xs), y=alt.Y("hid:N", sort=order),
                text=alt.Text("score:Q", format=".3f"))
    )
    return T.finalize(alt.layer(track, gates, bar, tip, val), height=height)


def _chart_rule_matrix(scored: list[dict]) -> Optional[alt.LayerChart]:
    """Hypotheses × rules verdict grid — the deterministic audit surface."""
    rows: list[dict] = []
    for s in scored:
        hid = s.get("hypothesis_id", "?")
        by_name = {r.get("rule_name"): r for r in (s.get("rule_results") or [])}
        for rname in RULE_ORDER:
            rr = by_name.get(rname, {})
            verdict = (rr.get("verdict") or "n/a").lower()
            rows.append({
                "hid": hid,
                "rule": RULE_SHORT.get(rname, rname.upper()),
                "verdict": verdict,
                "glyph": T.VERDICT_PALETTE.get(verdict, ("·", T.TEXT_FAINT))[0],
                "rationale": _short(rr.get("rationale") or "—", 110),
            })
    if not rows:
        return None

    df = pd.DataFrame(rows)
    hids = sorted({r["hid"] for r in rows})
    rule_labels = [RULE_SHORT.get(r, r.upper()) for r in RULE_ORDER]
    height = max(70, 40 * len(hids))

    vdom = ["pass", "partial", "fail", "n/a"]
    vfill = ["#101A14", "#1A1610", "#1D1311", T.SURFACE_2]
    vstroke = [T.POSITIVE, T.WARNING, T.CRITICAL, T.HAIRLINE]

    cell = (
        alt.Chart(df)
        .mark_rect(strokeWidth=1, cornerRadius=1)
        .encode(
            x=alt.X("rule:N", sort=rule_labels, axis=T.axis_x(None, grid=False)),
            y=alt.Y("hid:N", sort=hids, axis=T.axis_y(None, grid=False)),
            color=alt.Color("verdict:N", scale=alt.Scale(domain=vdom, range=vfill), legend=None),
            stroke=alt.Stroke("verdict:N", scale=alt.Scale(domain=vdom, range=vstroke), legend=None),
            tooltip=[
                alt.Tooltip("hid:N", title="Hypothesis"),
                alt.Tooltip("rule:N", title="Rule"),
                alt.Tooltip("verdict:N", title="Verdict"),
                alt.Tooltip("rationale:N", title="Rationale"),
            ],
        )
    )
    glyph = (
        alt.Chart(df)
        .mark_text(font=T.MONO, fontSize=12, fontWeight=500)
        .encode(
            x=alt.X("rule:N", sort=rule_labels),
            y=alt.Y("hid:N", sort=hids),
            text="glyph:N",
            color=alt.Color("verdict:N", scale=alt.Scale(domain=vdom, range=vstroke), legend=None),
        )
    )
    return T.finalize(
        alt.layer(cell, glyph).resolve_scale(color="independent"),
        height=height,
    )


def _chart_support_penalty(scored: list[dict]) -> Optional[alt.LayerChart]:
    """Diverging view: evidentiary support against contradiction penalty."""
    rows = [
        {
            "hid": s.get("hypothesis_id", "?"),
            "Support": float(s.get("support_score") or 0.0),
            "Penalty": -abs(float(s.get("contradiction_penalty") or 0.0)),
            "net": float(s.get("final_score") or 0.0),
        }
        for s in scored
    ]
    if not rows:
        return None
    df = pd.DataFrame(rows).sort_values("net", ascending=False)
    order = df["hid"].tolist()
    long = df.melt(id_vars=["hid", "net"], value_vars=["Support", "Penalty"],
                   var_name="component", value_name="value")
    span = max(0.6, long["value"].abs().max() * 1.25)
    height = max(80, 32 * len(df))

    zero = (
        alt.Chart(pd.DataFrame({"t": [0.0]}))
        .mark_rule(color="#2B3235", strokeWidth=1)
        .encode(x=alt.X("t:Q", scale=alt.Scale(domain=[-span, span])))
    )
    bars = (
        alt.Chart(long)
        .mark_bar(height=8)
        .encode(
            x=alt.X("value:Q", scale=alt.Scale(domain=[-span, span]),
                    axis=T.axis_x("contradiction  ←→  support", grid=True)),
            y=alt.Y("hid:N", sort=order, axis=T.axis_y(None, grid=False)),
            color=alt.Color("component:N",
                            scale=alt.Scale(domain=["Support", "Penalty"], range=[T.POSITIVE, T.CRITICAL]),
                            legend=alt.Legend(title=None)),
            tooltip=[
                alt.Tooltip("hid:N", title="Hypothesis"),
                alt.Tooltip("component:N", title="Component"),
                alt.Tooltip("value:Q", title="Value", format="+.3f"),
                alt.Tooltip("net:Q", title="Final score", format=".3f"),
            ],
        )
    )
    return T.finalize(alt.layer(zero, bars), height=height)


def _chart_projection(delta_pct: float, recovery_pct: float, metric: str) -> alt.LayerChart:
    """Recovery projection: observed decline, then simulated recovery with an
    illustrative uncertainty envelope. Explicitly labelled — not causal proof."""
    drop = -abs(float(delta_pct or 8.0))
    rec = max(0.0, min(100.0, float(recovery_pct or 0.0)))
    target = drop * (1.0 - rec / 100.0)

    obs = []
    for i, t in enumerate(range(-6, 1)):
        frac = 0.0 if t < -2 else (t + 2) / 2.0
        obs.append({"t": t, "value": 100.0 + drop * frac, "phase": "OBSERVED",
                    "lo": None, "hi": None})

    proj = []
    for t in range(0, 8):
        k = t / 7.0
        ease = 1 - pow(1 - k, 2.2)
        v = (100.0 + drop) + (target - drop) * ease
        band = abs(target - drop) * 0.34 * k + 0.5
        proj.append({"t": t, "value": v, "phase": "SIMULATED",
                     "lo": v - band, "hi": v + band})

    df_obs = pd.DataFrame(obs)
    df_proj = pd.DataFrame(proj)
    ymin = min(df_obs["value"].min(), df_proj["lo"].min()) - 1.5
    ymax = max(102.5, df_proj["hi"].max() + 1.5)
    yscale = alt.Scale(domain=[ymin, ymax])
    xscale = alt.Scale(domain=[-6, 7])

    baseline = (
        alt.Chart(pd.DataFrame({"b": [100.0]}))
        .mark_rule(color=T.HAIRLINE, strokeWidth=1, strokeDash=[3, 4])
        .encode(y=alt.Y("b:Q", scale=yscale))
    )
    onset = (
        alt.Chart(pd.DataFrame({"x": [0]}))
        .mark_rule(color="#2B3235", strokeWidth=1)
        .encode(x=alt.X("x:Q", scale=xscale))
    )
    onset_label = (
        alt.Chart(pd.DataFrame({"x": [0], "lab": ["ACTION"]}))
        .mark_text(align="left", dx=6, dy=-2, baseline="top", font=T.MONO,
                   fontSize=8, color=T.TEXT_FAINT)
        .encode(x=alt.X("x:Q", scale=xscale), y=alt.value(2), text="lab:N")
    )

    band = (
        alt.Chart(df_proj)
        .mark_area(opacity=0.16, color=T.SIMULATED, line=False)
        .encode(
            x=alt.X("t:Q", scale=xscale, axis=T.axis_x("periods relative to action", grid=False)),
            y=alt.Y("lo:Q", scale=yscale, axis=T.axis_y("index (expected = 100)", grid=True)),
            y2="hi:Q",
        )
    )
    obs_area = (
        alt.Chart(df_obs)
        .mark_area(line=False, color=T.fade("#2A1C16"), opacity=0.9)
        .encode(
            x=alt.X("t:Q", scale=xscale),
            y=alt.Y("value:Q", scale=yscale),
            y2=alt.datum(ymin),
        )
    )
    obs_line = (
        alt.Chart(df_obs)
        .mark_line(strokeWidth=1.6, color=T.CRITICAL, interpolate="monotone")
        .encode(
            x=alt.X("t:Q", scale=xscale),
            y=alt.Y("value:Q", scale=yscale),
            tooltip=[alt.Tooltip("t:Q", title="Period"),
                     alt.Tooltip("value:Q", title="Index", format=".2f"),
                     alt.Tooltip("phase:N", title="Phase")],
        )
    )
    proj_line = (
        alt.Chart(df_proj)
        .mark_line(strokeWidth=1.4, color=T.SIMULATED, strokeDash=[4, 3], interpolate="monotone")
        .encode(
            x=alt.X("t:Q", scale=xscale),
            y=alt.Y("value:Q", scale=yscale),
            tooltip=[alt.Tooltip("t:Q", title="Period"),
                     alt.Tooltip("value:Q", title="Projected index", format=".2f"),
                     alt.Tooltip("lo:Q", title="Envelope low", format=".2f"),
                     alt.Tooltip("hi:Q", title="Envelope high", format=".2f")],
        )
    )
    trough = df_obs.tail(1).copy()
    trough_halo = (
        alt.Chart(trough).mark_point(filled=True, size=250, opacity=0.14, color=T.CRITICAL)
        .encode(x=alt.X("t:Q", scale=xscale), y=alt.Y("value:Q", scale=yscale))
    )
    trough_pt = (
        alt.Chart(trough).mark_point(filled=True, size=52, color=T.CRITICAL)
        .encode(x=alt.X("t:Q", scale=xscale), y=alt.Y("value:Q", scale=yscale),
                tooltip=[alt.Tooltip("value:Q", title="Observed trough", format=".2f")])
    )
    end = df_proj.tail(1).copy()
    end_pt = (
        alt.Chart(end).mark_point(filled=True, size=46, color=T.SIMULATED)
        .encode(x=alt.X("t:Q", scale=xscale), y=alt.Y("value:Q", scale=yscale),
                tooltip=[alt.Tooltip("value:Q", title="Projected index", format=".2f")])
    )
    end_label = (
        alt.Chart(end)
        .mark_text(align="right", dx=-4, dy=-12, font=T.MONO, fontSize=9, color=T.TEXT_DIM)
        .encode(x=alt.X("t:Q", scale=xscale), y=alt.Y("value:Q", scale=yscale),
                text=alt.Text("value:Q", format=".1f"))
    )

    layered = alt.layer(
        baseline, band, obs_area, obs_line, proj_line,
        onset, onset_label, trough_halo, trough_pt, end_pt, end_label,
    )
    return T.finalize(layered, height=278)


def _chart_engine_latency(latency: dict) -> Optional[alt.LayerChart]:
    rows = [
        {"engine": k, "ms": float(v), "lane": "COGNITIVE" if k in LLM_ENGINES else "DETERMINISTIC"}
        for k, v in latency.items()
        if isinstance(v, (int, float))
    ]
    if not rows:
        return None
    df = pd.DataFrame(rows).sort_values("ms", ascending=False)
    order = df["engine"].tolist()
    height = max(84, 26 * len(df))

    bar = (
        alt.Chart(df)
        .mark_bar(height=7)
        .encode(
            x=alt.X("ms:Q", axis=T.axis_x("latency ms", grid=True)),
            y=alt.Y("engine:N", sort=order, axis=T.axis_y(None, grid=False)),
            color=alt.Color(
                "lane:N",
                scale=alt.Scale(domain=["DETERMINISTIC", "COGNITIVE"], range=[T.NEUTRAL, T.COGNITIVE]),
                legend=alt.Legend(title=None),
            ),
            tooltip=[alt.Tooltip("engine:N", title="Engine"),
                     alt.Tooltip("ms:Q", title="Latency ms", format=",.0f"),
                     alt.Tooltip("lane:N", title="Lane")],
        )
    )
    val = (
        alt.Chart(df)
        .mark_text(align="left", dx=9, font=T.MONO, fontSize=9, color=T.TEXT_MUTE)
        .encode(x="ms:Q", y=alt.Y("engine:N", sort=order), text=alt.Text("ms:Q", format=",.0f"))
    )
    return T.finalize(alt.layer(bar, val), height=height)


def _chart_source_reliability(evidence: list[dict]) -> Optional[alt.LayerChart]:
    agg: dict[str, dict] = {}
    for e in evidence:
        src = e.get("source_id", "unknown")
        rel = float(e.get("reliability_weight") or 0.0)
        a = agg.setdefault(src, {"n": 0, "sum": 0.0, "min": 1.0})
        a["n"] += 1
        a["sum"] += rel
        a["min"] = min(a["min"], rel)
    if not agg:
        return None

    rows = [
        {"source": s, "avg": a["sum"] / a["n"], "min": a["min"], "n": a["n"],
         "state": "fresh" if a["sum"] / a["n"] >= 0.85 else ("stale" if a["sum"] / a["n"] >= 0.3 else "low")}
        for s, a in agg.items()
    ]
    df = pd.DataFrame(rows).sort_values("avg", ascending=False)
    order = df["source"].tolist()
    height = max(84, 30 * len(df))

    gate = (
        alt.Chart(pd.DataFrame({"g": [0.85]}))
        .mark_rule(color=T.HAIRLINE, strokeWidth=1, strokeDash=[3, 4])
        .encode(x=alt.X("g:Q", scale=alt.Scale(domain=[0, 1.04])))
    )
    span = (
        alt.Chart(df)
        .mark_rule(strokeWidth=1, color=T.HAIRLINE, opacity=0.9)
        .encode(
            x=alt.X("min:Q", scale=alt.Scale(domain=[0, 1.04]),
                    axis=T.axis_x("reliability weight", grid=True)),
            x2="avg:Q",
            y=alt.Y("source:N", sort=order, axis=T.axis_y(None, grid=False)),
        )
    )
    dom = ["fresh", "stale", "low"]
    rng = [T.POSITIVE, T.WARNING, T.CRITICAL]
    pt = (
        alt.Chart(df)
        .mark_point(filled=True, size=52)
        .encode(
            x=alt.X("avg:Q", scale=alt.Scale(domain=[0, 1.04])),
            y=alt.Y("source:N", sort=order),
            color=alt.Color("state:N", scale=alt.Scale(domain=dom, range=rng), legend=None),
            tooltip=[
                alt.Tooltip("source:N", title="Source"),
                alt.Tooltip("n:Q", title="Evidence items"),
                alt.Tooltip("avg:Q", title="Avg reliability", format=".3f"),
                alt.Tooltip("min:Q", title="Min reliability", format=".3f"),
                alt.Tooltip("state:N", title="Freshness"),
            ],
        )
    )
    lo = (
        alt.Chart(df)
        .mark_point(filled=True, size=20, color=T.TEXT_FAINT)
        .encode(x=alt.X("min:Q", scale=alt.Scale(domain=[0, 1.04])), y=alt.Y("source:N", sort=order))
    )
    val = (
        alt.Chart(df)
        .mark_text(align="left", dx=11, font=T.MONO, fontSize=9, color=T.TEXT_DIM)
        .encode(x="avg:Q", y=alt.Y("source:N", sort=order), text=alt.Text("avg:Q", format=".3f"))
    )
    return T.finalize(alt.layer(gate, span, lo, pt, val), height=height)


def _chart_ownership(method_ownership: dict) -> Optional[alt.Chart]:
    """Which engines own quantitative truth vs language."""
    rows: list[dict] = []
    for engine, tags in method_ownership.items():
        if isinstance(tags, str):
            tags = [tags]
        for t in tags:
            up = str(t).upper()
            rows.append({
                "engine": engine,
                "tag": up,
                "lane": "DETERMINISTIC" if up in DET_TAGS else "LANGUAGE / SIMULATED",
                "weight": 1,
            })
    if not rows:
        return None
    df = pd.DataFrame(rows)
    order = list(dict.fromkeys(df["engine"].tolist()))
    height = max(90, 28 * len(order))

    chart = (
        alt.Chart(df)
        .mark_bar(height=9, stroke=T.BASE, strokeWidth=1)
        .encode(
            x=alt.X("sum(weight):Q", axis=T.axis_x("method tags", grid=True), stack="zero"),
            y=alt.Y("engine:N", sort=order, axis=T.axis_y(None, grid=False)),
            color=alt.Color(
                "lane:N",
                scale=alt.Scale(domain=["DETERMINISTIC", "LANGUAGE / SIMULATED"],
                                range=[T.NEUTRAL, T.COGNITIVE]),
                legend=alt.Legend(title=None),
            ),
            tooltip=[alt.Tooltip("engine:N", title="Engine"),
                     alt.Tooltip("tag:N", title="Method tag"),
                     alt.Tooltip("lane:N", title="Lane")],
        )
    )
    return T.finalize(chart, height=height)


# ─────────────────────────────────────────────────────────────────────────────
# Section renderers
# ─────────────────────────────────────────────────────────────────────────────

def _render_signals(result: dict) -> None:
    signals: list[dict] = result.get("signals") or []
    st.markdown(
        T.section(
            "Signal Detection",
            "Deviation of each connected KPI from its own expected baseline, measured in "
            "standard deviations. The shaded corridor is the ±3σ band where variance is "
            "statistically unremarkable; markers outside it are flagged anomalies.",
            index="01",
        ),
        unsafe_allow_html=True,
    )
    if not signals:
        _empty("No signals returned for this scenario.")
        return

    anomalies = [s for s in signals if s.get("is_anomaly")]
    sparse = [s for s in signals if s.get("sparse_history")]
    suspect = [s for s in signals if s.get("data_quality_suspect")]
    peak = max((abs(float(s.get("z_score") or 0)) for s in signals), default=0.0)

    cols = st.columns(4)
    cols[0].metric("KPIs monitored", f"{len(signals)}")
    cols[1].metric("Anomalies", f"{len(anomalies)}")
    cols[2].metric("Peak |z|", f"{peak:.2f}")
    cols[3].metric("Flagged inputs", f"{len(sparse) + len(suspect)}")

    _gap(28)
    chart = _chart_deviation(signals)
    if chart is not None:
        st.altair_chart(chart, use_container_width=True)
    else:
        _empty("No z-scores available to plot.")

    _gap(18)
    st.markdown(T.eyebrow("Per-signal readout"), unsafe_allow_html=True)

    for s in sorted(signals, key=lambda x: abs(float(x.get("z_score") or 0)), reverse=True):
        kpi = s.get("kpi_id", "—")
        z = s.get("z_score")
        delta = s.get("delta_pct")
        anomaly = bool(s.get("is_anomaly"))
        flags: list[str] = []
        if s.get("sparse_history"):
            flags.append("sparse history")
        if s.get("data_quality_suspect"):
            flags.append("data-quality suspect")

        accent = T.CRITICAL if anomaly else (T.WARNING if flags else T.HAIRLINE)
        state = "ANOMALY" if anomaly else ("REVIEW" if flags else "NOMINAL")
        state_col = T.CRITICAL if anomaly else (T.WARNING if flags else T.TEXT_MUTE)
        corrob = s.get("corroborated_by") or []
        if isinstance(corrob, str):
            corrob = [corrob]

        mag = min(100.0, abs(float(z or 0)) / 6.0 * 100.0)

        st.markdown(
            f'<div style="border-left:2px solid {accent};background:{T.SURFACE};'
            f'padding:13px 18px;margin-bottom:6px">'
            f'<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">'
            f'<div style="flex:0 0 250px">'
            f'<div style="color:{T.TEXT};font-size:0.85rem;font-weight:500;'
            f'font-family:{T.MONO}">{kpi}</div>'
            f'<div style="margin-top:5px">{T.tag(s.get("method","STATS"))}</div>'
            f'</div>'
            f'<div style="flex:0 0 auto;display:flex;gap:30px">'
            f'<div><div style="color:{T.TEXT_MUTE};font-size:0.6rem;letter-spacing:0.1em;'
            f'text-transform:uppercase;margin-bottom:3px">Observed</div>'
            f'{T.num(_f(s.get("observed"), 4), size="0.92rem")}</div>'
            f'<div><div style="color:{T.TEXT_MUTE};font-size:0.6rem;letter-spacing:0.1em;'
            f'text-transform:uppercase;margin-bottom:3px">Expected</div>'
            f'{T.num(_f(s.get("expected"), 4), T.TEXT_DIM, "0.92rem")}</div>'
            f'<div><div style="color:{T.TEXT_MUTE};font-size:0.6rem;letter-spacing:0.1em;'
            f'text-transform:uppercase;margin-bottom:3px">Delta</div>'
            f'{T.num(_f(delta, 2, signed=True) + "%", T.CRITICAL if anomaly else T.TEXT, "0.92rem")}</div>'
            f'<div><div style="color:{T.TEXT_MUTE};font-size:0.6rem;letter-spacing:0.1em;'
            f'text-transform:uppercase;margin-bottom:3px">z-score</div>'
            f'{T.num(_f(z, 3, signed=True), T.CRITICAL if anomaly else T.TEXT, "0.92rem")}</div>'
            f'</div>'
            f'<div style="flex:1;min-width:120px">{T.meter(mag, accent if anomaly else "#2E3639")}'
            f'<div style="color:{T.TEXT_FAINT};font-size:0.58rem;font-family:{T.MONO};'
            f'margin-top:5px">|z| RELATIVE TO 6σ</div></div>'
            f'<div style="flex:0 0 96px;text-align:right">'
            f'{T.dot(state_col, glow=anomaly)}'
            f'<span style="color:{state_col};font-size:0.62rem;font-weight:600;'
            f'letter-spacing:0.1em;margin-left:6px">{state}</span></div>'
            f'</div>'
            + (
                f'<div style="margin-top:9px;padding-top:8px;border-top:1px solid {T.HAIRLINE_2};'
                f'display:flex;gap:20px;flex-wrap:wrap">'
                + (
                    f'<span style="color:{T.TEXT_MUTE};font-size:0.68rem">corroborated by '
                    f'<span style="font-family:{T.MONO};color:{T.NEUTRAL}">'
                    f'{", ".join(str(c) for c in corrob)}</span></span>' if corrob else ""
                )
                + (
                    f'<span style="color:{T.WARNING};font-size:0.68rem">◐ '
                    f'{" · ".join(flags)}</span>' if flags else ""
                )
                + '</div>'
                if (corrob or flags) else ""
            )
            + '</div>',
            unsafe_allow_html=True,
        )


def _suppression_reason(signals: list[dict]) -> tuple[str, str, str]:
    """Return (tone, headline, cause) describing why the pipeline stopped short."""
    # Anomaly presence is checked FIRST. A guard flag on some unrelated KPI must
    # not be reported as the reason when a real anomaly was in fact detected.
    if any(s.get("is_anomaly") for s in signals):
        return (
            T.NEUTRAL,
            "UPSTREAM DATA UNAVAILABLE",
            "an anomaly was established, but the inputs this stage needs were not present "
            "in the authorised scope for this scenario",
        )
    if any(s.get("data_quality_suspect") for s in signals):
        return (
            T.WARNING,
            "SUPPRESSED BY DATA-QUALITY GUARD",
            "the data-quality score for this window fell below the 0.80 gate, so the movement "
            "in the data is treated as an artefact rather than a business event",
        )
    if any(s.get("sparse_history") for s in signals):
        return (
            T.WARNING,
            "SUPPRESSED BY SPARSE-HISTORY GUARD",
            "the baseline has too few samples to support a statistical claim, so detection was "
            "withheld rather than run on thin history",
        )
    return (
        T.TEXT_MUTE,
        "NO ANOMALY ESTABLISHED",
        "every KPI stayed inside the ±3σ corridor and below the 10% delta threshold",
    )


def _render_suppression_notice(signals: list[dict], headline: str, body: str) -> None:
    tone, tag_text, cause = _suppression_reason(signals)
    st.markdown(
        f'<div style="border-left:2px solid {tone};background:{T.SURFACE};'
        f'padding:20px 24px;max-width:840px">'
        f'<div style="display:flex;align-items:center;gap:11px;margin-bottom:12px">'
        f'{T.dot(tone)}'
        f'<span style="color:{tone};font-size:0.64rem;font-weight:600;'
        f'letter-spacing:0.13em">{tag_text}</span></div>'
        f'<p style="color:{T.TEXT};font-size:0.86rem;line-height:1.72;margin:0 0 10px">'
        f'{headline}.</p>'
        f'<p style="color:{T.TEXT_DIM};font-size:0.82rem;line-height:1.72;margin:0 0 14px">'
        f'{body}</p>'
        f'<p style="color:{T.TEXT_MUTE};font-size:0.77rem;line-height:1.7;margin:0;'
        f'padding-top:13px;border-top:1px solid {T.HAIRLINE}">'
        f'Cause: {cause}. This is a designed outcome, not a failure.</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_no_decomposition(signals: list[dict]) -> None:
    """Explain *why* there is nothing to decompose. The reason is diagnostic,
    not an error: a suppressed anomaly is a correct outcome, and saying so
    plainly is the difference between a trustworthy panel and a broken-looking
    one."""
    dq = [s for s in signals if s.get("data_quality_suspect")]
    sparse = [s for s in signals if s.get("sparse_history")]
    anomalous = [s for s in signals if s.get("is_anomaly")]

    if anomalous:
        tone, head = T.NEUTRAL, "NO SEGMENTABLE DIMENSIONS"
        body = (
            "An anomaly was established, but the driving KPI has no dimensional breakdown "
            "loaded for this scenario, so device, region and channel could not be apportioned."
        )
        foot = (
            "The signal is real; only its localisation is unavailable. The challenge stage will "
            "record segment alignment as PARTIAL rather than asserting a segment it cannot show."
        )
    elif dq:
        tone, head = T.WARNING, "SUPPRESSED BY DATA-QUALITY GUARD"
        body = (
            f"The data-quality score for this window fell below the 0.80 gate, so the "
            f"Signal Engine flagged {len(dq)} KPI"
            f"{'s' if len(dq) != 1 else ''} as <span style='color:{T.TEXT_DIM}'>"
            f"data_quality_suspect</span> and deliberately did <em>not</em> raise a business "
            f"anomaly. With no anomaly to attribute, there is nothing to decompose."
        )
        foot = (
            "This is the designed outcome for a false-anomaly scenario: the apparent movement "
            "is a data artefact, not a business event. Decomposing it would manufacture a "
            "cause for something that never happened."
        )
    elif sparse:
        tone, head = T.WARNING, "SUPPRESSED BY SPARSE-HISTORY GUARD"
        body = (
            f"{len(sparse)} KPI{'s' if len(sparse) != 1 else ''} lack enough baseline samples "
            f"to support a statistical claim, so anomaly detection was withheld rather than "
            f"run on thin history."
        )
        foot = (
            "Decomposition needs a confirmed anomaly to attribute. Without a trustworthy "
            "baseline there is no deviation to apportion."
        )
    elif not anomalous:
        tone, head = T.TEXT_MUTE, "NO ANOMALY TO DECOMPOSE"
        body = (
            "Every KPI stayed inside the ±3σ corridor and below the 10% delta threshold. "
            "No deviation cleared the bar for attribution."
        )
        foot = "Nominal state. Nothing to explain."
    else:
        tone, head = T.NEUTRAL, "NO SEGMENTABLE DIMENSIONS"
        body = (
            "An anomaly was detected, but the driving KPI has no dimensional breakdown loaded "
            "for this scenario, so device, region and channel could not be apportioned."
        )
        foot = (
            "The signal is real; only its localisation is unavailable. Downstream rules will "
            "record segment alignment as PARTIAL rather than asserting a segment."
        )

    st.markdown(
        f'<div style="border-left:2px solid {tone};background:{T.SURFACE};'
        f'padding:20px 24px;max-width:840px">'
        f'<div style="display:flex;align-items:center;gap:11px;margin-bottom:12px">'
        f'{T.dot(tone)}'
        f'<span style="color:{tone};font-size:0.64rem;font-weight:600;'
        f'letter-spacing:0.13em">{head}</span></div>'
        f'<p style="color:{T.TEXT};font-size:0.84rem;line-height:1.72;margin:0 0 14px">'
        f'{body}</p>'
        f'<p style="color:{T.TEXT_MUTE};font-size:0.77rem;line-height:1.7;margin:0;'
        f'padding-top:13px;border-top:1px solid {T.HAIRLINE}">{foot}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_decomposition(result: dict) -> None:
    contributions: list[dict] = result.get("contributions") or []
    st.markdown(
        T.section(
            "Dimensional Decomposition",
            "Where the variance actually lives. Bars show each segment's share of the total "
            "deviation; the dashed trace is the cumulative share, so a trace that saturates "
            "early means the problem is concentrated rather than systemic.",
            index="02",
        ),
        unsafe_allow_html=True,
    )
    if not contributions:
        _render_no_decomposition(result.get("signals") or [])
        return

    df = pd.DataFrame(contributions)
    if "contribution_pct" not in df.columns:
        _empty("Contribution payload missing expected fields.")
        return
    if "segment_delta_pct" not in df.columns:
        df["segment_delta_pct"] = 0.0

    for dim in df["dimension"].unique().tolist():
        sub = df[df["dimension"] == dim].copy()
        if sub.empty:
            continue
        sub = sub.sort_values("contribution_pct", ascending=False)
        top = sub.iloc[0]
        share = float(top["contribution_pct"])
        concentrated = share >= 50.0

        st.markdown(
            f'<div style="display:flex;align-items:baseline;gap:14px;'
            f'padding-bottom:11px;border-bottom:1px solid {T.HAIRLINE};margin-bottom:18px">'
            f'<span style="color:{T.TEXT_MUTE};font-size:0.62rem;font-weight:600;'
            f'letter-spacing:0.13em;text-transform:uppercase">Dimension</span>'
            f'<span style="color:{T.TEXT};font-size:0.88rem;font-family:{T.MONO}">{dim}</span>'
            f'<span style="flex:1"></span>'
            f'<span style="color:{T.TEXT_MUTE};font-size:0.72rem">dominant</span>'
            f'<span style="color:{T.CRITICAL if concentrated else T.TEXT};font-size:0.8rem;'
            f'font-family:{T.MONO}">{top["segment"]}</span>'
            f'{T.num(f"{share:.1f}%", T.CRITICAL if concentrated else T.TEXT, "0.82rem")}'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.altair_chart(_chart_contribution(sub), use_container_width=True)
        st.markdown(
            f'<p style="color:{T.TEXT_MUTE};font-size:0.75rem;margin:2px 0 0;line-height:1.6">'
            + (
                f'<span style="color:{T.CRITICAL}">Concentrated.</span> '
                f'<span style="font-family:{T.MONO};color:{T.TEXT_DIM}">{top["segment"]}</span> '
                f'alone accounts for {share:.1f}% of the deviation — consistent with a '
                f'segment-specific fault rather than a platform-wide one.'
                if concentrated else
                f'<span style="color:{T.TEXT_DIM}">Distributed.</span> No single segment exceeds '
                f'50% of the deviation ({top["segment"]} leads at {share:.1f}%), which points '
                f'away from a segment-specific cause.'
            )
            + f'  <span style="color:{T.TEXT_FAINT}">Method: '
            f'{top.get("method", "SQL")}</span></p>',
            unsafe_allow_html=True,
        )
        _gap(34)


def _render_evidence(result: dict) -> None:
    evidence: list[dict] = result.get("evidence") or []
    st.markdown(
        T.section(
            "Evidence Field",
            "Every retrieved item positioned by how much the source can be trusted and how "
            "closely it bears on the signal. Items to the right of the 0.85 guide are fresh; "
            "items above the 0.5 guide are materially relevant. The upper-right quadrant is "
            "what the challenge engine weighs most heavily.",
            index="03",
        ),
        unsafe_allow_html=True,
    )
    if not evidence:
        _empty("No evidence assembled within the persona's authorised scope.")
        return

    by_method: dict[str, int] = {}
    for e in evidence:
        by_method[(e.get("method") or "—").upper()] = by_method.get((e.get("method") or "—").upper(), 0) + 1
    stale = [e for e in evidence if float(e.get("reliability_weight") or 0) < 0.85]
    sources = {e.get("source_id") for e in evidence}

    cols = st.columns(4)
    cols[0].metric("Evidence items", f"{len(evidence)}")
    cols[1].metric("Distinct sources", f"{len(sources)}")
    cols[2].metric("Stale / down-weighted", f"{len(stale)}")
    cols[3].metric(
        "Mean relevance",
        f"{sum(float(e.get('relevance') or 0) for e in evidence) / max(1, len(evidence)):.2f}",
    )

    _gap(24)
    chart = _chart_evidence_field(evidence)
    if chart is not None:
        st.altair_chart(chart, use_container_width=True)

    _gap(10)
    st.markdown(
        T.eyebrow("Item detail  ·  " + "   ".join(f"{k} {v}" for k, v in sorted(by_method.items()))),
        unsafe_allow_html=True,
    )

    for e in sorted(evidence, key=lambda x: float(x.get("relevance") or 0), reverse=True):
        eid = (e.get("evidence_id") or "?")[:14]
        rel = float(e.get("relevance") or 0.0)
        wgt = float(e.get("reliability_weight") or 0.0)
        src = e.get("source_id", "—")
        kind = (e.get("kind") or "—").upper()
        is_stale = wgt < 0.85

        label = f"{eid}   ·   {src}   ·   {kind}   ·   rel {rel:.2f}  wgt {wgt:.2f}"
        if is_stale:
            label += "   ◐ down-weighted"

        with st.expander(label, expanded=False):
            c_txt, c_num = st.columns([3, 1.35])
            with c_txt:
                st.markdown(
                    f'<p style="color:{T.TEXT};font-size:0.83rem;line-height:1.7;margin:0 0 10px">'
                    f'{_clean(str(e.get("summary") or "—"))}</p>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
                    f'{T.tag(e.get("method", "—"))}'
                    f'<span style="font-family:{T.MONO};color:{T.TEXT_FAINT};font-size:0.68rem">'
                    f'{e.get("raw_ref") or ""}</span></div>',
                    unsafe_allow_html=True,
                )
            with c_num:
                st.markdown(
                    T.kv_row("relevance", f"{rel:.3f}")
                    + T.kv_row("reliability", f"{wgt:.3f}", T.WARNING if is_stale else T.POSITIVE)
                    + T.kv_row("weighted", f"{rel * wgt:.3f}", T.TEXT_DIM),
                    unsafe_allow_html=True,
                )


def _render_hypotheses(result: dict) -> None:
    hypotheses: list[dict] = result.get("hypotheses") or []
    scored: list[dict] = result.get("scored") or []
    st.markdown(
        T.section(
            "Hypothesis Space",
            "Candidate explanations proposed by the language model, then scored entirely by "
            "deterministic rules. The model contributes wording and evidence linkage only — "
            "every number on this screen comes from the RULES engine.",
            index="04",
        ),
        unsafe_allow_html=True,
    )
    if not hypotheses:
        _render_suppression_notice(
            result.get("signals") or [],
            "Hypothesis generation was withheld",
            "No hypothesis was proposed, because no anomaly was established. The engine will "
            "not speculate about a cause for an event it cannot confirm occurred.",
        )
        return

    stmt_by_id = {h.get("hypothesis_id"): h.get("statement", "") for h in hypotheses}
    scored_by_id = {s.get("hypothesis_id"): s for s in scored}

    chart = _chart_hypothesis_scores(scored, stmt_by_id)
    if chart is not None:
        st.altair_chart(chart, use_container_width=True)
        st.markdown(
            f'<p style="color:{T.TEXT_FAINT};font-size:0.7rem;margin:-6px 0 0;'
            f'font-family:{T.MONO};letter-spacing:0.04em">'
            f'DASHED GATES &nbsp;·&nbsp; 0.40 MEDIUM &nbsp;·&nbsp; 0.70 HIGH'
            f'</p>',
            unsafe_allow_html=True,
        )
        _gap(22)

    ranked = sorted(
        hypotheses,
        key=lambda h: float(scored_by_id.get(h.get("hypothesis_id"), {}).get("final_score") or 0),
        reverse=True,
    )
    lead_id = ranked[0].get("hypothesis_id") if ranked else None

    for h in ranked:
        hid = h.get("hypothesis_id", "?")
        sh = scored_by_id.get(hid, {})
        score = float(sh.get("final_score") or 0.0)
        state = (sh.get("confidence_state") or "low").lower()
        col = T.CONFIDENCE_PALETTE.get(state, T.TEXT_MUTE)
        stmt = h.get("statement", "")
        support = h.get("supporting_evidence_ids") or []
        contra = h.get("contradictory_evidence_ids") or []

        label = f"{hid}   ·   {state.upper()}  {score:.3f}   ·   {_short(stmt, 84)}"
        with st.expander(label, expanded=(hid == lead_id)):
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">'
                f'{T.dot(col, glow=(state == "high"))}'
                f'<span style="color:{col};font-size:0.65rem;font-weight:600;letter-spacing:0.12em">'
                f'{state.upper()}</span>'
                f'<div style="flex:1">{T.meter(score * 100, col)}</div>'
                f'{T.num(f"{score:.3f}", col, "0.86rem")}'
                f'{T.tag("LLM")}</div>'
                f'<p style="color:{T.TEXT};font-size:0.87rem;line-height:1.72;margin:0 0 12px">'
                f'{_clean(stmt)}</p>'
                + (
                    f'<p style="color:{T.TEXT_DIM};font-size:0.81rem;line-height:1.7;'
                    f'margin:0 0 14px;padding-left:13px;border-left:1px solid {T.HAIRLINE}">'
                    f'{_clean(str(h.get("reasoning") or ""))}</p>'
                    if h.get("reasoning") else ""
                ),
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            for col_obj, title, ids, tone in (
                (c1, "Supporting evidence", support, T.POSITIVE),
                (c2, "Contradictory evidence", contra, T.CRITICAL),
            ):
                chips = "".join(
                    f'<span style="display:inline-block;background:{T.SURFACE_2};'
                    f'border:1px solid {T.HAIRLINE};border-left:2px solid {tone};'
                    f'padding:2px 8px;margin:0 5px 5px 0;font-family:{T.MONO};'
                    f'font-size:0.66rem;color:{T.TEXT_DIM}">{str(i)[:14]}</span>'
                    for i in ids
                ) or f'<span style="color:{T.TEXT_FAINT};font-size:0.72rem">none</span>'
                col_obj.markdown(
                    T.eyebrow(f"{title}  ({len(ids)})", tone) + chips,
                    unsafe_allow_html=True,
                )


def _render_challenge(result: dict) -> None:
    scored: list[dict] = result.get("scored") or []
    hypotheses: list[dict] = result.get("hypotheses") or []
    st.markdown(
        T.section(
            "Adversarial Challenge",
            "Five deterministic falsification rules run against every hypothesis. Verdicts and "
            "scores are produced by code, not by the model; the narrative underneath is written "
            "by the model after scoring and can never move a score.",
            index="05",
        ),
        unsafe_allow_html=True,
    )
    if not scored:
        _render_suppression_notice(
            result.get("signals") or [],
            "No hypothesis reached the challenge stage",
            "The falsification rules had nothing to test. With no candidate explanation, there "
            "is no score to defend and the pipeline abstains rather than asserting a cause.",
        )
        return

    stmt_by_id = {h.get("hypothesis_id"): h.get("statement", "") for h in hypotheses}

    verdicts = [
        (r.get("verdict") or "").lower()
        for s in scored for r in (s.get("rule_results") or [])
    ]
    cols = st.columns(4)
    cols[0].metric("Hypotheses tested", f"{len(scored)}")
    cols[1].metric("Rules passed", f"{verdicts.count('pass')}")
    cols[2].metric("Partial", f"{verdicts.count('partial')}")
    cols[3].metric("Failed", f"{verdicts.count('fail')}")

    _gap(28)
    st.markdown(T.eyebrow("Verdict matrix  ·  hypotheses × falsification rules"), unsafe_allow_html=True)
    m = _chart_rule_matrix(scored)
    if m is not None:
        st.altair_chart(m, use_container_width=True)

    _gap(24)
    st.markdown(T.eyebrow("Support against contradiction"), unsafe_allow_html=True)
    sp = _chart_support_penalty(scored)
    if sp is not None:
        st.altair_chart(sp, use_container_width=True)

    _gap(20)
    st.markdown(T.eyebrow("Rule rationale and narrative"), unsafe_allow_html=True)

    ranked = sorted(scored, key=lambda s: float(s.get("final_score") or 0), reverse=True)
    lead_id = ranked[0].get("hypothesis_id") if ranked else None

    for s in ranked:
        hid = s.get("hypothesis_id", "?")
        score = float(s.get("final_score") or 0.0)
        state = (s.get("confidence_state") or "low").lower()
        col = T.CONFIDENCE_PALETTE.get(state, T.TEXT_MUTE)
        support = float(s.get("support_score") or 0.0)
        penalty = float(s.get("contradiction_penalty") or 0.0)

        label = f"{hid}   ·   {state.upper()}  {score:.3f}   ·   {_short(stmt_by_id.get(hid, ''), 74)}"
        with st.expander(label, expanded=(hid == lead_id)):
            st.markdown(
                T.kv_block(
                    T.kv_row("support score", f"{support:.3f}", T.POSITIVE)
                    + T.kv_row("contradiction penalty", f"{penalty:.3f}",
                               T.CRITICAL if penalty else T.TEXT_DIM)
                    + T.kv_row("final score", f"{score:.3f}", col)
                    + T.kv_row("confidence state", state.upper(), col)
                ),
                unsafe_allow_html=True,
            )
            _gap(20)

            by_name = {r.get("rule_name"): r for r in (s.get("rule_results") or [])}
            for rname in RULE_ORDER:
                rr = by_name.get(rname)
                if not rr:
                    continue
                verdict = (rr.get("verdict") or "n/a").lower()
                glyph, vcol = T.VERDICT_PALETTE.get(verdict, ("·", T.TEXT_FAINT))
                st.markdown(
                    f'<div style="display:flex;gap:14px;align-items:flex-start;'
                    f'padding:9px 0;border-top:1px solid {T.HAIRLINE_2}">'
                    f'<span style="color:{vcol};font-family:{T.MONO};font-size:0.86rem;'
                    f'flex:0 0 14px;line-height:1.5">{glyph}</span>'
                    f'<div style="flex:0 0 168px">'
                    f'<div style="color:{T.TEXT};font-size:0.75rem;font-family:{T.MONO}">'
                    f'{RULE_SHORT.get(rname, rname)}</div>'
                    f'<div style="color:{vcol};font-size:0.6rem;font-weight:600;'
                    f'letter-spacing:0.1em;margin-top:3px">{verdict.upper()}</div></div>'
                    f'<p style="color:{T.TEXT_DIM};font-size:0.77rem;line-height:1.65;'
                    f'margin:0;flex:1">{_clean(str(rr.get("rationale") or "—"))}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            narrative = _clean(str(s.get("narrative") or ""))
            if narrative:
                _gap(16)
                st.markdown(
                    f'<div style="border-left:2px solid {T.COGNITIVE};background:{T.SURFACE};'
                    f'padding:14px 18px">'
                    f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:9px">'
                    f'{T.tag("LLM_NARRATIVE")}'
                    f'<span style="color:{T.TEXT_FAINT};font-size:0.68rem">'
                    f'written after scoring · cannot alter the score</span></div>'
                    f'<p style="color:{T.TEXT_DIM};font-size:0.81rem;line-height:1.72;margin:0">'
                    f'{narrative}</p></div>',
                    unsafe_allow_html=True,
                )


def _render_decision(result: dict) -> None:
    decision: Optional[dict] = result.get("decision")
    persona: str = result.get("persona") or "analyst"
    scored: list[dict] = result.get("scored") or []
    st.markdown(
        T.section(
            "Decision",
            "The action recommendation, or an explicit abstention. The system only acts when "
            "deterministic confidence clears the gate; the narrative is framed for the "
            "selected persona.",
            index="06",
        ),
        unsafe_allow_html=True,
    )
    if decision is None:
        _empty("No decision produced.")
        return

    abstained = bool(decision.get("abstained"))
    action = decision.get("recommended_action")
    verification = decision.get("verification_metric")
    winner = decision.get("winning_hypothesis_id")
    narrative = _clean(str(decision.get("persona_narrative") or ""))
    reason = decision.get("abstention_reason")

    win = next((s for s in scored if s.get("hypothesis_id") == winner), {})
    score = float(win.get("final_score") or 0.0)
    state = (win.get("confidence_state") or ("abstain" if abstained else "low")).lower()
    col = T.CONFIDENCE_PALETTE.get(state, T.TEXT_MUTE)

    if abstained:
        st.markdown(
            f'<div style="border-left:2px solid {T.WARNING};background:{T.SURFACE};'
            f'padding:20px 24px;margin-bottom:22px">'
            f'<div style="display:flex;align-items:center;gap:11px;margin-bottom:10px">'
            f'{T.dot(T.WARNING, glow=True)}'
            f'<span style="color:{T.WARNING};font-size:0.72rem;font-weight:600;'
            f'letter-spacing:0.14em">ABSTAINED</span></div>'
            f'<p style="color:{T.TEXT};font-size:0.87rem;line-height:1.7;margin:0 0 12px;'
            f'max-width:760px">No action recommended. Deterministic confidence did not clear '
            f'the threshold required to act, so the system withheld a recommendation rather '
            f'than guessing.</p>'
            + (
                f'<div style="color:{T.TEXT_MUTE};font-size:0.78rem;line-height:1.65">'
                f'<span style="color:{T.TEXT_FAINT}">Reason  </span>{reason}</div>'
                if reason else ""
            )
            + '</div>',
            unsafe_allow_html=True,
        )
        if verification:
            st.markdown(
                T.eyebrow("Verification guidance")
                + f'<p style="color:{T.TEXT_DIM};font-size:0.83rem;line-height:1.7;'
                f'margin:0;max-width:820px">{verification}</p>',
                unsafe_allow_html=True,
            )
        return

    c_main, c_side = st.columns([3, 1.15])
    with c_main:
        st.markdown(
            f'<div style="border-left:2px solid {T.POSITIVE};background:{T.SURFACE};'
            f'padding:20px 24px">'
            f'<div style="display:flex;align-items:center;gap:11px;margin-bottom:13px">'
            f'{T.dot(T.POSITIVE, glow=True)}'
            f'<span style="color:{T.POSITIVE};font-size:0.66rem;font-weight:600;'
            f'letter-spacing:0.14em">RECOMMENDED ACTION</span></div>'
            f'<p style="color:{T.TEXT};font-size:0.95rem;line-height:1.72;margin:0">'
            f'{_clean(str(action or "—"))}</p></div>',
            unsafe_allow_html=True,
        )
    with c_side:
        st.markdown(
            f'<div style="background:{T.SURFACE};border:1px solid {T.HAIRLINE};padding:18px 20px">'
            + T.eyebrow("Winning hypothesis")
            + f'<div style="margin-bottom:14px">{T.num(str(winner or "—"), T.TEXT, "1.5rem")}</div>'
            + T.kv_row("final score", f"{score:.3f}", col)
            + T.kv_row("confidence", state.upper(), col)
            + f'<div style="margin-top:12px">{T.meter(score * 100, col)}</div>'
            + '</div>',
            unsafe_allow_html=True,
        )

    if verification:
        _gap(22)
        st.markdown(
            f'<div style="border-top:1px solid {T.HAIRLINE};padding-top:16px">'
            + T.eyebrow("Verification metric", T.NEUTRAL)
            + f'<p style="color:{T.TEXT_DIM};font-size:0.83rem;line-height:1.7;margin:0;'
            f'max-width:860px">{verification}</p></div>',
            unsafe_allow_html=True,
        )

    if narrative:
        _gap(22)
        st.markdown(
            f'<div style="border-left:2px solid {T.COGNITIVE};background:{T.SURFACE};'
            f'padding:18px 22px">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:11px">'
            f'{T.tag("LLM")}'
            f'<span style="color:{T.TEXT_FAINT};font-size:0.68rem">'
            f'framed for {persona.upper()}</span></div>'
            f'<p style="color:{T.TEXT_DIM};font-size:0.84rem;line-height:1.78;margin:0;'
            f'max-width:900px">{narrative}</p></div>',
            unsafe_allow_html=True,
        )


def _render_architecture(result: dict) -> None:
    method_ownership: dict = result.get("method_ownership") or {}
    st.markdown(
        T.section(
            "Method Ownership",
            "The separation the whole system rests on: quantitative truth is owned by SQL, "
            "STATS and RULES engines. The language model writes statements, summaries and "
            "narrative — it never produces a number that reaches a score.",
            index="07",
        ),
        unsafe_allow_html=True,
    )
    if not method_ownership:
        _empty("No method ownership metadata returned.")
        return

    chart = _chart_ownership(method_ownership)
    if chart is not None:
        st.altair_chart(chart, use_container_width=True)
        _gap(22)

    det_rows: list[tuple[str, list[str]]] = []
    llm_rows: list[tuple[str, list[str]]] = []
    for engine, tags in method_ownership.items():
        if isinstance(tags, str):
            tags = [tags]
        det = [t for t in tags if str(t).upper() in DET_TAGS]
        llm = [t for t in tags if str(t).upper() not in DET_TAGS]
        if det:
            det_rows.append((engine, det))
        if llm:
            llm_rows.append((engine, llm))

    c1, c2 = st.columns(2)
    for col_obj, title, rows, tone, note in (
        (c1, "Deterministic  ·  quantitative truth", det_rows, T.NEUTRAL,
         "Values here are reproducible: same inputs, same outputs, every run."),
        (c2, "Cognitive  ·  language and simulation", llm_rows, T.COGNITIVE,
         "Wording may vary between runs. No value here feeds a confidence score."),
    ):
        body = "".join(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:9px 0;border-top:1px solid {T.HAIRLINE_2}">'
            f'<span style="color:{T.TEXT_DIM};font-size:0.78rem;font-family:{T.MONO}">{eng}</span>'
            f'<span>{"".join(T.tag(str(t)) + " " for t in tags)}</span></div>'
            for eng, tags in rows
        ) or f'<div style="color:{T.TEXT_FAINT};font-size:0.75rem;padding:9px 0">none</div>'
        col_obj.markdown(
            f'<div style="border-left:2px solid {tone};padding-left:16px">'
            + T.eyebrow(title, tone) + body
            + f'<p style="color:{T.TEXT_FAINT};font-size:0.71rem;line-height:1.6;'
            f'margin:12px 0 0">{note}</p></div>',
            unsafe_allow_html=True,
        )


def _render_provenance(result: dict) -> None:
    evidence: list[dict] = result.get("evidence") or []
    contributions: list[dict] = result.get("contributions") or []
    st.markdown(
        T.section(
            "Provenance & Freshness",
            "Reliability per source. The marker is the mean weight, the faint point is the "
            "worst item from that source, and the dashed guide is the 0.85 freshness gate. "
            "Anything left of the gate is down-weighted in the confidence math.",
            index="08",
        ),
        unsafe_allow_html=True,
    )
    if not evidence:
        _empty("No evidence to trace.")
        return

    chart = _chart_source_reliability(evidence)
    if chart is not None:
        st.altair_chart(chart, use_container_width=True)

    agg: dict[str, dict] = {}
    for e in evidence:
        src = e.get("source_id", "unknown")
        a = agg.setdefault(src, {"n": 0, "sum": 0.0, "min": 1.0, "methods": set()})
        rel = float(e.get("reliability_weight") or 0.0)
        a["n"] += 1
        a["sum"] += rel
        a["min"] = min(a["min"], rel)
        a["methods"].add((e.get("method") or "—").upper())

    degraded = [s for s, a in agg.items() if a["sum"] / a["n"] < 0.85]
    if degraded:
        _gap(16)
        st.markdown(
            f'<div style="border-left:2px solid {T.WARNING};background:{T.SURFACE};'
            f'padding:13px 18px">'
            f'<span style="color:{T.WARNING};font-size:0.72rem;font-weight:600;'
            f'letter-spacing:0.1em">◐ DOWN-WEIGHTED SOURCES</span>'
            f'<p style="color:{T.TEXT_DIM};font-size:0.78rem;line-height:1.65;margin:7px 0 0">'
            f'<span style="font-family:{T.MONO};color:{T.TEXT}">{", ".join(degraded)}</span> '
            f'fall below the 0.85 freshness gate. Their evidence still appears, but contributes '
            f'proportionally less to hypothesis support.</p></div>',
            unsafe_allow_html=True,
        )

    _gap(24)
    st.markdown(T.eyebrow("Source ledger"), unsafe_allow_html=True)
    for src, a in sorted(agg.items(), key=lambda kv: kv[1]["sum"] / kv[1]["n"], reverse=True):
        avg = a["sum"] / a["n"]
        tone = T.POSITIVE if avg >= 0.85 else (T.WARNING if avg >= 0.3 else T.CRITICAL)
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:18px;padding:11px 0;'
            f'border-top:1px solid {T.HAIRLINE_2}">'
            f'<span style="flex:0 0 190px;color:{T.TEXT};font-size:0.78rem;'
            f'font-family:{T.MONO}">{src}</span>'
            f'<span style="flex:0 0 62px;color:{T.TEXT_MUTE};font-size:0.72rem">'
            f'{a["n"]} item{"s" if a["n"] != 1 else ""}</span>'
            f'<div style="flex:1;min-width:90px">{T.meter(avg * 100, tone)}</div>'
            f'<span style="flex:0 0 118px;text-align:right">'
            f'{T.num(f"{avg:.3f}", tone, "0.8rem")}'
            f'<span style="color:{T.TEXT_FAINT};font-size:0.66rem;font-family:{T.MONO}">'
            f' / min {a["min"]:.2f}</span></span>'
            f'<span style="flex:0 0 auto">'
            f'{"".join(T.tag(m) + " " for m in sorted(a["methods"]))}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if contributions:
        _gap(30)
        st.markdown(T.eyebrow("Decomposition lineage"), unsafe_allow_html=True)
        rows = [
            {
                "Dimension": c.get("dimension"),
                "Segment": c.get("segment"),
                "Contribution %": round(float(c.get("contribution_pct") or 0), 2),
                "Segment Δ%": round(float(c.get("segment_delta_pct") or 0), 2),
                "Method": c.get("method", "SQL"),
            }
            for c in contributions
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_outcome(result: dict) -> None:
    outcome: Optional[dict] = result.get("outcome")
    signals: list[dict] = result.get("signals") or []
    st.markdown(
        T.section(
            "Outcome Projection",
            "A forward view of the recovery the recommended action is expected to produce. "
            "The solid stroke is observed history; the dashed stroke and shaded envelope are "
            "simulated and widen with horizon to reflect growing uncertainty.",
            index="09",
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div style="border-left:2px solid {T.SIMULATED};background:{T.SURFACE};'
        f'padding:12px 18px;margin-bottom:24px">'
        f'<span style="color:{T.SIMULATED};font-size:0.66rem;font-weight:600;'
        f'letter-spacing:0.13em">SIMULATED</span>'
        f'<span style="color:{T.TEXT_MUTE};font-size:0.78rem;line-height:1.6"> — '
        f'projection only, not causal proof. The envelope is illustrative of uncertainty '
        f'growth, not a calibrated confidence interval.</span></div>',
        unsafe_allow_html=True,
    )

    if outcome is None:
        _empty("No outcome projection available.")
        return

    method = str(outcome.get("method") or "")
    otype = str(outcome.get("outcome_type") or "")
    if method.upper() != "SIMULATED" or otype.lower() != "simulated":
        st.markdown(
            f'<div style="border-left:2px solid {T.CRITICAL};background:{T.SURFACE};'
            f'padding:14px 18px">'
            f'<span style="color:{T.CRITICAL};font-size:0.8rem">Projection is missing its '
            f'SIMULATED tag and has been withheld from display.</span></div>',
            unsafe_allow_html=True,
        )
        return

    recovery = float(outcome.get("projected_recovery_pct") or 0.0)
    metric = str(outcome.get("projected_metric") or "—")
    disclaimer = str(outcome.get("disclaimer") or "")

    primary = next((s for s in signals if s.get("is_anomaly")), signals[0] if signals else {})
    delta = float(primary.get("delta_pct") or 0.0) or -8.0

    c_chart, c_meta = st.columns([3, 1.15])
    with c_chart:
        st.altair_chart(_chart_projection(delta, recovery, metric), use_container_width=True)
    with c_meta:
        residual = abs(delta) * (1 - recovery / 100.0)
        st.markdown(
            f'<div style="background:{T.SURFACE};border:1px solid {T.HAIRLINE};padding:18px 20px">'
            + T.eyebrow("Projected recovery")
            + f'<div style="margin-bottom:14px">{T.num(f"{recovery:.0f}%", T.SIMULATED, "1.9rem")}</div>'
            + T.kv_row("observed delta", f"{delta:+.2f}%", T.CRITICAL)
            + T.kv_row("residual after action", f"{-residual:+.2f}%", T.WARNING)
            + T.kv_row("outcome type", otype.upper(), T.SIMULATED)
            + f'<div style="margin-top:14px">{T.meter(recovery, T.SIMULATED)}</div>'
            + f'<div style="margin-top:16px">' + T.eyebrow("Projected metric") + '</div>'
            + f'<code style="color:{T.NEUTRAL};font-size:0.72rem;word-break:break-all">{metric}</code>'
            + '</div>',
            unsafe_allow_html=True,
        )

    if disclaimer:
        _gap(18)
        st.markdown(
            f'<p style="color:{T.TEXT_MUTE};font-size:0.76rem;line-height:1.7;margin:0;'
            f'padding-left:14px;border-left:1px solid {T.HAIRLINE};max-width:900px">'
            f'{disclaimer}</p>',
            unsafe_allow_html=True,
        )


def _render_access_denied(payload: dict, persona: str) -> None:
    excluded = payload.get("excluded_sources", []) or []
    reason = payload.get("reason", "")
    chips = "".join(
        f'<span style="display:inline-block;background:{T.SURFACE_2};'
        f'border:1px solid {T.HAIRLINE};border-left:2px solid {T.CRITICAL};'
        f'padding:3px 10px;margin:0 6px 6px 0;font-family:{T.MONO};'
        f'font-size:0.72rem;color:{T.TEXT}">{s}</span>'
        for s in excluded
    )
    st.markdown(
        f'<div style="border-left:2px solid {T.CRITICAL};background:{T.SURFACE};'
        f'padding:26px 28px;margin-top:22px;max-width:880px">'
        f'<div style="display:flex;align-items:center;gap:11px;margin-bottom:13px">'
        f'{T.dot(T.CRITICAL, glow=True)}'
        f'<span style="color:{T.CRITICAL};font-size:0.7rem;font-weight:600;'
        f'letter-spacing:0.14em">ACCESS DENIED</span></div>'
        f'<p style="color:{T.TEXT};font-size:0.9rem;line-height:1.7;margin:0 0 16px">'
        f'Persona <span style="font-family:{T.MONO};color:{T.WARNING}">{persona.upper()}</span> '
        f'is not entitled to one or more sources this investigation requires.</p>'
        + (
            f'<p style="color:{T.TEXT_MUTE};font-size:0.79rem;line-height:1.65;'
            f'margin:0 0 18px">{reason}</p>' if reason else ""
        )
        + (T.eyebrow("Excluded sources") + chips if excluded else "")
        + f'<p style="color:{T.TEXT_MUTE};font-size:0.76rem;line-height:1.7;'
        f'margin:18px 0 0;padding-top:14px;border-top:1px solid {T.HAIRLINE}">'
        f'Excluded content is never displayed and never transmitted to the language model. '
        f'Switch to the <span style="color:{T.TEXT_DIM}">Analyst</span> persona for full scope.'
        f'</p></div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def _render_telemetry(result: dict) -> None:
    t: dict = result.get("telemetry", {}) or {}
    if not t:
        return

    latency: dict = t.get("latency_ms_by_engine", {}) or {}
    total_ms = sum(v for v in latency.values() if isinstance(v, (int, float)))
    llm_ms = sum(v for k, v in latency.items() if k in LLM_ENGINES and isinstance(v, (int, float)))
    det_ms = total_ms - llm_ms
    llm_share = (llm_ms / total_ms * 100.0) if total_ms else 0.0

    ext = float(t.get("external_cost_usd") or 0.0)
    equiv = t.get("equivalent_cloud_cost_usd")

    st.sidebar.markdown(
        f'<div style="border-top:1px solid {T.HAIRLINE};padding-top:15px;margin-top:6px">'
        + T.eyebrow("Telemetry")
        + T.kv_row("wall clock", f"{total_ms / 1000:.1f}s")
        + T.kv_row("llm calls", f"{t.get('llm_calls', 0)}", T.COGNITIVE)
        + T.kv_row("tokens in", f"{t.get('llm_tokens_in', 0):,}", T.TEXT_DIM)
        + T.kv_row("tokens out", f"{t.get('llm_tokens_out', 0):,}", T.TEXT_DIM)
        + T.kv_row("external cost", f"${ext:.2f}", T.POSITIVE if ext == 0 else T.TEXT)
        + (T.kv_row("cloud equivalent", f"${float(equiv):.4f}", T.TEXT_MUTE)
           if isinstance(equiv, (int, float)) else "")
        + f'<div style="margin-top:15px">' + T.eyebrow("Compute split") + '</div>'
        + f'<div style="display:flex;height:3px;border-radius:1px;overflow:hidden;'
        f'background:{T.HAIRLINE}">'
        f'<div style="width:{100 - llm_share:.1f}%;background:{T.NEUTRAL}"></div>'
        f'<div style="width:{llm_share:.1f}%;background:{T.COGNITIVE};'
        f'box-shadow:0 0 8px {T.COGNITIVE}66"></div></div>'
        f'<div style="display:flex;justify-content:space-between;margin-top:7px">'
        f'<span style="color:{T.NEUTRAL};font-size:0.66rem;font-family:{T.MONO}">'
        f'DET {det_ms / 1000:.1f}s</span>'
        f'<span style="color:{T.COGNITIVE};font-size:0.66rem;font-family:{T.MONO}">'
        f'LLM {llm_ms / 1000:.1f}s</span></div>'
        + '</div>',
        unsafe_allow_html=True,
    )

    if latency:
        with st.sidebar.expander("Engine latency", expanded=False):
            for k, v in sorted(latency.items(), key=lambda kv: kv[1] if isinstance(kv[1], (int, float)) else 0,
                               reverse=True):
                if not isinstance(v, (int, float)):
                    continue
                tone = T.COGNITIVE if k in LLM_ENGINES else T.NEUTRAL
                pct = (v / max(latency.values()) * 100.0) if latency else 0.0
                st.markdown(
                    f'<div style="margin-bottom:9px">'
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
                    f'<span style="color:{tone};font-size:0.68rem;font-family:{T.MONO}">{k}</span>'
                    f'<span style="color:{T.TEXT_MUTE};font-size:0.66rem;font-family:{T.MONO}">'
                    f'{v:,.0f}ms</span></div>{T.meter(pct, tone, height=2)}</div>',
                    unsafe_allow_html=True,
                )


def _build_sidebar() -> tuple[str, str, str]:
    st.sidebar.markdown(
        f'<div style="padding:0 0 16px">'
        f'<div style="display:flex;align-items:center;gap:9px">'
        f'<span style="color:{T.TEXT};font-size:0.9rem">◈</span>'
        f'<span style="color:{T.TEXT};font-size:0.86rem;font-weight:600;'
        f'letter-spacing:-0.005em">BusinessIntelligence.ai</span></div>'
        f'<div style="color:{T.TEXT_FAINT};font-size:0.66rem;font-family:{T.MONO};'
        f'letter-spacing:0.06em;margin-top:5px;padding-left:19px">'
        f'EVIDENCE-BACKED KPI ENGINE</div></div>'
        f'<div style="border-top:1px solid {T.HAIRLINE};margin-bottom:16px"></div>',
        unsafe_allow_html=True,
    )

    st.sidebar.markdown(T.eyebrow("Persona"), unsafe_allow_html=True)
    persona = st.sidebar.radio(
        "persona",
        options=["analyst", "cfo", "manager"],
        format_func=lambda p: {
            "analyst": "Analyst — full scope",
            "cfo": "CFO — aggregate only",
            "manager": "Manager — own region",
        }[p],
        key="persona_radio",
        label_visibility="collapsed",
    )
    scope_note = {
        "analyst": (T.POSITIVE, "Full source scope. Baseline for comparison."),
        "cfo": (T.NEUTRAL, "Aggregate-only scope. Narrative compressed for executive reading."),
        "manager": (T.WARNING, "Regional scope. Cannot reach payment_gateway — exercises the access-denied path."),
    }[persona]
    st.sidebar.markdown(
        f'<div style="border-left:2px solid {scope_note[0]};padding:2px 0 2px 12px;'
        f'margin:11px 0 18px">'
        f'<p style="color:{T.TEXT_MUTE};font-size:0.72rem;line-height:1.6;margin:0">'
        f'{scope_note[1]}</p></div>',
        unsafe_allow_html=True,
    )

    st.sidebar.markdown(
        f'<div style="border-top:1px solid {T.HAIRLINE};margin-bottom:16px"></div>'
        + T.eyebrow("Scenario"),
        unsafe_allow_html=True,
    )
    scenarios = _get_scenarios()
    by_id = {s["id"]: s for s in scenarios}
    ids = [s["id"] for s in scenarios]

    def _fmt(sid: str) -> str:
        s = by_id.get(sid, {})
        mark = "●" if s.get("status") == "live" else "◌"
        return f"{mark}  {sid}"

    scenario_id = st.sidebar.selectbox(
        "scenario", options=ids, format_func=_fmt, key="scenario_sel",
        label_visibility="collapsed",
    )
    meta = by_id.get(scenario_id, {})
    status = meta.get("status", "live")
    label = meta.get("label", scenario_id)

    st.sidebar.markdown(
        f'<p style="color:{T.TEXT_MUTE};font-size:0.72rem;line-height:1.6;'
        f'margin:9px 0 0">{label}</p>',
        unsafe_allow_html=True,
    )
    if status == "evaluation_only":
        st.sidebar.markdown(
            f'<div style="border-left:2px solid {T.SIMULATED};padding:2px 0 2px 12px;margin:11px 0 0">'
            f'<p style="color:{T.TEXT_MUTE};font-size:0.71rem;line-height:1.6;margin:0">'
            f'Evaluation-only — validated through the evaluation harness, not the live '
            f'pipeline.</p></div>',
            unsafe_allow_html=True,
        )

    return scenario_id, persona, status


# ─────────────────────────────────────────────────────────────────────────────
# Header status strip
# ─────────────────────────────────────────────────────────────────────────────

def _status_strip(scenario_id: str, persona: str, status: str, result: Optional[dict]) -> None:
    if result and not result.get("access_denied"):
        decision = result.get("decision") or {}
        scored = result.get("scored") or []
        winner = decision.get("winning_hypothesis_id")
        win = next((s for s in scored if s.get("hypothesis_id") == winner), {})
        state = (win.get("confidence_state") or "").lower()
        abstained = bool(decision.get("abstained"))
        anomalies = sum(1 for s in (result.get("signals") or []) if s.get("is_anomaly"))
        tel = result.get("telemetry", {}) or {}
        lat = tel.get("latency_ms_by_engine", {}) or {}
        wall = sum(v for v in lat.values() if isinstance(v, (int, float))) / 1000.0

        if abstained:
            run_state, run_col = "ABSTAINED", T.WARNING
        elif state == "high":
            run_state, run_col = "RESOLVED", T.POSITIVE
        elif state:
            run_state, run_col = f"{state.upper()} CONFIDENCE", T.CONFIDENCE_PALETTE.get(state, T.TEXT_MUTE)
        else:
            run_state, run_col = "COMPLETE", T.TEXT_MUTE

        cells = [
            ("scenario", scenario_id, T.TEXT),
            ("persona", persona.upper(), T.TEXT_DIM),
            ("anomalies", str(anomalies), T.CRITICAL if anomalies else T.TEXT_DIM),
            ("hypotheses", str(len(scored)), T.TEXT_DIM),
            ("winner", str(winner or "—"), T.TEXT),
            ("wall clock", f"{wall:.1f}s", T.TEXT_DIM),
        ]
    else:
        run_state, run_col = ("STANDBY" if not result else "BLOCKED",
                              T.TEXT_MUTE if not result else T.CRITICAL)
        cells = [
            ("scenario", scenario_id, T.TEXT),
            ("persona", persona.upper(), T.TEXT_DIM),
            ("mode", status.replace("_", " ").upper(), T.TEXT_DIM),
        ]

    body = "".join(
        f'<div style="padding:0 24px 0 0;margin-right:24px;'
        f'border-right:1px solid {T.HAIRLINE}">'
        f'<div style="color:{T.TEXT_MUTE};font-size:0.58rem;font-weight:600;'
        f'letter-spacing:0.13em;text-transform:uppercase;margin-bottom:5px">{k}</div>'
        f'{T.num(v, c, "0.86rem")}</div>'
        for k, v, c in cells
    )

    st.markdown(
        f'<div style="display:flex;align-items:flex-end;justify-content:space-between;'
        f'padding-bottom:15px;border-bottom:1px solid {T.HAIRLINE};margin-bottom:8px">'
        f'<div style="display:flex;align-items:flex-end;flex-wrap:wrap">{body}'
        f'<div><div style="color:{T.TEXT_MUTE};font-size:0.58rem;font-weight:600;'
        f'letter-spacing:0.13em;text-transform:uppercase;margin-bottom:5px">state</div>'
        f'<div style="display:flex;align-items:center;gap:8px">'
        f'{T.dot(run_col, glow=True)}'
        f'<span style="color:{run_col};font-size:0.74rem;font-family:{T.MONO};'
        f'letter-spacing:0.04em">{run_state}</span></div></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _render_feedback(investigation_id: Optional[str]) -> None:
    with st.expander("Submit analyst feedback", expanded=False):
        if not investigation_id:
            _empty("No investigation ID — run an investigation first.")
            return
        st.markdown(
            f'<p style="color:{T.TEXT_MUTE};font-size:0.76rem;line-height:1.65;'
            f'margin:0 0 12px;max-width:720px">Feedback is written to the memory store and '
            f'becomes retrievable precedent for future investigations of the same signal '
            f'shape.</p>'
            f'<p style="color:{T.TEXT_FAINT};font-size:0.68rem;font-family:{T.MONO};'
            f'margin:0 0 10px">INVESTIGATION {investigation_id}</p>',
            unsafe_allow_html=True,
        )
        text = st.text_area(
            "Feedback",
            max_chars=5000,
            placeholder="Was the winning hypothesis correct? Was the action appropriate?",
            key="feedback_ta",
            label_visibility="collapsed",
        )
        if st.button("Submit", key="feedback_btn", type="secondary"):
            if not text or not text.strip():
                st.warning("Enter some feedback before submitting.")
                return
            try:
                r = httpx.post(
                    f"{BASE_URL}/feedback",
                    json={"investigation_id": investigation_id, "content": text},
                    timeout=30.0,
                )
                if r.status_code == 200:
                    st.success(f"Recorded — {r.json().get('feedback_id')}")
                elif r.status_code == 404:
                    st.error(f"Investigation not found: {r.json().get('error', '')}")
                elif r.status_code == 422:
                    st.error(f"Invalid content: {r.json().get('error', '')}")
                else:
                    st.error(f"Error {r.status_code}: {r.text}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not reach API: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    scenario_id, persona, scenario_status = _build_sidebar()

    cached_result: Optional[dict] = st.session_state.get("last_result")
    strip_result = cached_result if st.session_state.get("last_scenario") == scenario_id else None

    c_strip, c_run = st.columns([6, 1.1])
    with c_strip:
        _status_strip(scenario_id, persona, scenario_status, strip_result)
    with c_run:
        run_clicked = st.button(
            "Run", type="primary", use_container_width=True,
            disabled=(scenario_status == "evaluation_only"),
        )

    if scenario_status == "evaluation_only":
        _gap(30)
        st.markdown(
            f'<div style="border-left:2px solid {T.SIMULATED};background:{T.SURFACE};'
            f'padding:26px 28px;max-width:820px">'
            f'<div style="display:flex;align-items:center;gap:11px;margin-bottom:13px">'
            f'{T.dot(T.SIMULATED)}'
            f'<span style="color:{T.SIMULATED};font-size:0.68rem;font-weight:600;'
            f'letter-spacing:0.14em">EVALUATION-ONLY SCENARIO</span></div>'
            f'<p style="color:{T.TEXT};font-size:0.88rem;line-height:1.72;margin:0 0 18px">'
            f'<span style="font-family:{T.MONO}">{scenario_id}</span> is validated through the '
            f'evaluation harness rather than the live pipeline. Its expected behaviour is '
            f'asserted by the 15-dimension scorecard.</p>'
            f'<code style="background:{T.SURFACE_2};border:1px solid {T.HAIRLINE};'
            f'color:{T.POSITIVE};padding:7px 13px;display:inline-block">python run_demo.py</code>'
            f'<p style="color:{T.TEXT_MUTE};font-size:0.78rem;line-height:1.65;margin:18px 0 0">'
            f'Select a live scenario (marked ●) to run an interactive investigation.</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    if run_clicked:
        with st.spinner(f"Running {scenario_id} · nine engines · local inference"):
            result, error = _call_investigate(scenario_id, persona)
        if error:
            _gap(24)
            st.markdown(
                f'<div style="border-left:2px solid {T.CRITICAL};background:{T.SURFACE};'
                f'padding:18px 22px;max-width:820px">'
                f'<div style="color:{T.CRITICAL};font-size:0.68rem;font-weight:600;'
                f'letter-spacing:0.13em;margin-bottom:9px">INVESTIGATION FAILED</div>'
                f'<p style="color:{T.TEXT_DIM};font-size:0.82rem;line-height:1.7;margin:0">'
                f'{error}</p></div>',
                unsafe_allow_html=True,
            )
            st.stop()
        st.session_state["last_result"] = result
        st.session_state["last_scenario"] = scenario_id
        st.session_state["last_persona"] = persona
        cached_result = result

    result: Optional[dict] = st.session_state.get("last_result")
    if result is None:
        _gap(70)
        st.markdown(
            f'<div style="text-align:center;padding:20px">'
            f'<div style="color:{T.HAIRLINE};font-size:2.6rem;line-height:1;'
            f'margin-bottom:22px">◈</div>'
            f'<div style="color:{T.TEXT_DIM};font-size:0.88rem;margin-bottom:9px">'
            f'Standing by</div>'
            f'<div style="color:{T.TEXT_FAINT};font-size:0.77rem;line-height:1.8;'
            f'max-width:560px;margin:0 auto">Select a scenario and persona, then run. '
            f'The pipeline sequences anomaly detection, dimensional decomposition, evidence '
            f'retrieval, hypothesis generation, adversarial challenge, decision and '
            f'projection.</div></div>',
            unsafe_allow_html=True,
        )
        return

    if result.get("access_denied"):
        _render_access_denied(result, st.session_state.get("last_persona", persona))
        return

    _render_telemetry(result)

    precedents = result.get("precedents", []) or []
    if precedents:
        st.sidebar.markdown(
            f'<div style="border-top:1px solid {T.HAIRLINE};padding-top:15px;margin-top:16px">'
            + T.eyebrow("Memory precedents")
            + "".join(
                f'<div style="display:flex;gap:8px;padding:4px 0">'
                f'<span style="color:{T.TEXT_FAINT};font-family:{T.MONO};'
                f'font-size:0.66rem">{i + 1:02d}</span>'
                f'<span style="color:{T.TEXT_MUTE};font-size:0.7rem;line-height:1.5">'
                f'{_short(str(p), 46)}</span></div>'
                for i, p in enumerate(precedents[:6])
            )
            + '</div>',
            unsafe_allow_html=True,
        )

    tabs = st.tabs([
        "Signals", "Decomposition", "Evidence", "Hypotheses", "Challenge",
        "Decision", "Method", "Provenance", "Projection",
    ])
    with tabs[0]:
        _render_signals(result)
    with tabs[1]:
        _render_decomposition(result)
    with tabs[2]:
        _render_evidence(result)
    with tabs[3]:
        _render_hypotheses(result)
    with tabs[4]:
        _render_challenge(result)
    with tabs[5]:
        _render_decision(result)
    with tabs[6]:
        _render_architecture(result)
    with tabs[7]:
        _render_provenance(result)
    with tabs[8]:
        _render_outcome(result)

    _gap(34)
    st.markdown(f'<div style="border-top:1px solid {T.HAIRLINE}"></div>', unsafe_allow_html=True)
    _render_feedback(result.get("investigation_id"))


if __name__ == "__main__":
    main()
