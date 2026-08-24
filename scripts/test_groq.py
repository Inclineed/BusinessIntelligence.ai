"""
scripts/test_groq.py — Live smoke test for Groq LLM provider.

Usage:
    python scripts/test_groq.py
    python scripts/test_groq.py --model llama-3.3-70b-versatile
    python scripts/test_groq.py --json

Verifies GROQ_API_KEY, executes a single live inference against Groq,
and reports latency, token usage, and cost without leaking secrets.
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

# Ensure stdout handles UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from llm.provider import GroqProvider, LLMUnavailableError, GroqAPIError
from llm.cost_estimator import estimate_model_cost


def main() -> int:
    parser = argparse.ArgumentParser(description="Live smoke test for Groq LLM provider")
    parser.add_argument("--model", type=str, default=None, help="Override Groq model")
    parser.add_argument("--json", action="store_true", help="Test structured JSON response")
    args = parser.parse_args()

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        print("[ERROR] GROQ_API_KEY is not set.")
        print("        Set GROQ_API_KEY in your environment or in e:\\accenture\\.env")
        print("        Example (PowerShell): $env:GROQ_API_KEY='gsk_...'")
        return 1

    print("=" * 60)
    print("  BusinessIntelligence.ai — Groq Live Smoke Test")
    print("=" * 60)
    print(f"  Provider:     groq")
    print(f"  Credentials:  [CONFIGURED] ({len(provider._api_keys)} active credential(s) in pool)")

    try:
        provider = GroqProvider(api_key=api_key, model=args.model)
    except Exception as exc:
        print(f"[ERROR] Failed to initialize GroqProvider: {exc}")
        return 1

    target_model = args.model or provider._model
    print(f"  Model:        {target_model}")
    print(f"  Base URL:     {provider._base_url}")
    print(f"  Timeout:      {provider._timeout}s")
    print(f"  Format:       {'JSON' if args.json else 'Text'}")
    print("-" * 60)

    if args.json:
        prompt = (
            "Analyze this event: payment gateway latency increased by 300ms. "
            "Return JSON with keys: hypothesis, confidence (high/medium/low), recommended_action."
        )
        system = "You are a business intelligence diagnostic engine. Respond in valid JSON only."
    else:
        prompt = (
            "Summarize the business impact of a 15% conversion drop during a checkout outage in one sentence."
        )
        system = "You are a concise enterprise diagnostic assistant."

    print("Sending live completion request to Groq...")
    t0 = time.perf_counter()
    try:
        response = provider.complete(
            prompt=prompt,
            system=system,
            temperature=0.0,
            max_tokens=250,
            format_json=args.json,
        )
        latency_s = time.perf_counter() - t0
    except GroqAPIError as exc:
        print(f"\n[ERROR] Groq API Error: {exc}")
        return 1
    except LLMUnavailableError as exc:
        print(f"\n[ERROR] Groq Unavailable: {exc}")
        return 1
    except Exception as exc:
        print(f"\n[ERROR] Unexpected Error: {exc}")
        return 1

    cost = estimate_model_cost(
        model=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        provider="groq",
    )
    cost_str = f"${cost:.6f} USD" if cost is not None else "N/A (unpriced model)"

    print("\n[SUCCESS] Response received successfully!")
    print("-" * 60)
    print(f"  Status:             200 OK")
    print(f"  Roundtrip Latency:  {latency_s*1000:.1f} ms")
    print(f"  Reported Latency:   {response.latency_ms:.1f} ms")
    print(f"  Prompt Tokens:      {response.prompt_tokens}")
    print(f"  Completion Tokens:  {response.completion_tokens}")
    print(f"  Total Tokens:       {response.total_tokens}")
    print(f"  Estimated Cost:     {cost_str}")
    print("-" * 60)
    print("Response Content:")
    print(response.text)
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
