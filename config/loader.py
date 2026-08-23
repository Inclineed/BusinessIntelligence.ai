"""
config/loader.py — Schema-validated config loaders for BusinessIntelligence.ai.

Loads and validates:
  - kpi_contracts.yaml  (KPI Semantic Contracts)
  - entitlements.yaml   (Persona authorization scopes)
  - sources.yaml        (Source Registry definitions)

All loaders are fail-closed: any missing file, missing required key, or invalid
value raises ConfigError with a specific message identifying the artifact and
the offending field.  There is no default-domain fallback — the active domain
is derived exclusively from kpi_contracts.yaml (Requirements 19.1, 19.2, 19.3).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """
    Raised by any config loader when an artifact is missing, unreadable,
    or does not satisfy its schema (Requirement 19.2).
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: str | Path, artifact_name: str) -> Any:
    """
    Read and parse a YAML file.  Raises ConfigError if the file does not
    exist or cannot be parsed.
    """
    p = Path(path)
    if not p.exists():
        raise ConfigError(
            f"[{artifact_name}] Configuration file not found: {p}"
        )
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"[{artifact_name}] YAML parse error in {p}: {exc}"
        ) from exc

    if data is None:
        raise ConfigError(
            f"[{artifact_name}] Configuration file is empty: {p}"
        )
    return data


def _require(obj: dict, key: str, artifact: str, context: str = "") -> Any:
    """
    Assert that *key* is present and non-empty in *obj*.
    Raises ConfigError identifying the artifact, context, and missing key.
    """
    if key not in obj:
        loc = f" (in {context})" if context else ""
        raise ConfigError(
            f"[{artifact}] Required key '{key}' is missing{loc}."
        )
    val = obj[key]
    # Treat empty string, empty list, empty dict, and None as absent.
    if val is None or val == "" or val == [] or val == {}:
        loc = f" (in {context})" if context else ""
        raise ConfigError(
            f"[{artifact}] Required key '{key}' has an empty value{loc}."
        )
    return val


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------

def load_kpi_contract(path: str | Path) -> dict:
    """
    Load and validate kpi_contracts.yaml.

    Top-level required keys: domain, version, kpis
    Per-KPI required keys: id, formula, source, grain, drivers, access
    Additional per-KPI checks:
      - definition must be non-empty
      - calculation must be non-empty
      - lineage must be a non-empty list
      - thresholds must be a non-empty dict

    Returns the raw parsed dict on success.
    Raises ConfigError on any violation (Requirement 19.2).
    The active domain is found at result["domain"] (Requirement 19.1).
    """
    ARTIFACT = "kpi_contracts.yaml"
    data = _load_yaml(path, ARTIFACT)

    if not isinstance(data, dict):
        raise ConfigError(
            f"[{ARTIFACT}] Top level must be a YAML mapping, got {type(data).__name__}."
        )

    # Top-level required keys
    for key in ("domain", "version", "kpis"):
        _require(data, key, ARTIFACT)

    kpis = data["kpis"]
    if not isinstance(kpis, list) or len(kpis) == 0:
        raise ConfigError(
            f"[{ARTIFACT}] 'kpis' must be a non-empty list."
        )

    # Per-KPI validation — all six required elements (Requirement 2.1)
    required_per_kpi = ("id", "formula", "source", "grain", "drivers", "access")
    # These map to the six elements: definition, calculation, drivers, thresholds,
    # lineage, access restrictions.  formula acts as calculation; we also check
    # definition, calculation (alias: formula), thresholds, and lineage explicitly.
    for i, kpi in enumerate(kpis):
        if not isinstance(kpi, dict):
            raise ConfigError(
                f"[{ARTIFACT}] KPI at index {i} must be a YAML mapping."
            )
        ctx = f"kpi[{i}] id={kpi.get('id', '<unknown>')!r}"
        for key in required_per_kpi:
            _require(kpi, key, ARTIFACT, context=ctx)

        # Additional element checks (Requirement 2.1 — six elements)
        for extra in ("definition", "calculation", "lineage", "thresholds"):
            _require(kpi, extra, ARTIFACT, context=ctx)

        # drivers and lineage must be lists
        for list_key in ("drivers", "lineage"):
            val = kpi[list_key]
            if not isinstance(val, list) or len(val) == 0:
                raise ConfigError(
                    f"[{ARTIFACT}] '{list_key}' must be a non-empty list "
                    f"({ctx})."
                )

        # thresholds must be a dict
        if not isinstance(kpi["thresholds"], dict) or len(kpi["thresholds"]) == 0:
            raise ConfigError(
                f"[{ARTIFACT}] 'thresholds' must be a non-empty mapping ({ctx})."
            )

        # access must be a dict
        if not isinstance(kpi["access"], dict) or len(kpi["access"]) == 0:
            raise ConfigError(
                f"[{ARTIFACT}] 'access' must be a non-empty mapping ({ctx})."
            )

    return data


def load_entitlements(path: str | Path) -> dict:
    """
    Load and validate entitlements.yaml.

    Top-level required key: personas
    Per-persona required keys: authorized_sources, authorized_fields

    Returns the raw parsed dict on success.
    Raises ConfigError on any violation (Requirement 19.2).
    """
    ARTIFACT = "entitlements.yaml"
    data = _load_yaml(path, ARTIFACT)

    if not isinstance(data, dict):
        raise ConfigError(
            f"[{ARTIFACT}] Top level must be a YAML mapping."
        )

    _require(data, "personas", ARTIFACT)
    personas = data["personas"]

    if not isinstance(personas, dict) or len(personas) == 0:
        raise ConfigError(
            f"[{ARTIFACT}] 'personas' must be a non-empty mapping."
        )

    required_per_persona = ("authorized_sources", "authorized_fields")
    for persona_name, persona_cfg in personas.items():
        if not isinstance(persona_cfg, dict):
            raise ConfigError(
                f"[{ARTIFACT}] Persona '{persona_name}' must be a YAML mapping."
            )
        ctx = f"persona '{persona_name}'"
        for key in required_per_persona:
            _require(persona_cfg, key, ARTIFACT, context=ctx)

        # authorized_sources must be a list
        sources = persona_cfg["authorized_sources"]
        if not isinstance(sources, list) or len(sources) == 0:
            raise ConfigError(
                f"[{ARTIFACT}] 'authorized_sources' must be a non-empty list "
                f"({ctx})."
            )

        # authorized_fields must be a dict
        fields = persona_cfg["authorized_fields"]
        if not isinstance(fields, dict) or len(fields) == 0:
            raise ConfigError(
                f"[{ARTIFACT}] 'authorized_fields' must be a non-empty mapping "
                f"({ctx})."
            )

    return data


def load_sources(path: str | Path) -> list[dict]:
    """
    Load and validate sources.yaml.

    Top-level required key: sources (a non-empty list)
    Per-source required keys: id, grain, cadence_minutes, sla_minutes, data_quality

    Returns the validated list of source dicts on success.
    Raises ConfigError on any violation (Requirement 19.2).
    """
    ARTIFACT = "sources.yaml"
    data = _load_yaml(path, ARTIFACT)

    if not isinstance(data, dict):
        raise ConfigError(
            f"[{ARTIFACT}] Top level must be a YAML mapping."
        )

    _require(data, "sources", ARTIFACT)
    sources = data["sources"]

    if not isinstance(sources, list) or len(sources) == 0:
        raise ConfigError(
            f"[{ARTIFACT}] 'sources' must be a non-empty list."
        )

    required_per_source = (
        "id", "grain", "cadence_minutes", "sla_minutes", "data_quality"
    )
    for i, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ConfigError(
                f"[{ARTIFACT}] Source at index {i} must be a YAML mapping."
            )
        ctx = f"source[{i}] id={source.get('id', '<unknown>')!r}"
        for key in required_per_source:
            _require(source, key, ARTIFACT, context=ctx)

        # Numeric range checks
        dq = source["data_quality"]
        if not isinstance(dq, (int, float)) or not (0.0 <= float(dq) <= 1.0):
            raise ConfigError(
                f"[{ARTIFACT}] 'data_quality' must be a float in [0, 1] ({ctx}); "
                f"got {dq!r}."
            )

        for int_key in ("cadence_minutes", "sla_minutes"):
            v = source[int_key]
            if not isinstance(v, (int, float)) or int(v) < 0:
                raise ConfigError(
                    f"[{ARTIFACT}] '{int_key}' must be a non-negative integer "
                    f"({ctx}); got {v!r}."
                )

    return sources


def load_memory_retention(path: str | Path) -> dict:
    """
    Load and validate memory_retention.yaml (ISSUE-002 Phase 4).

    Top-level required key: retention (a mapping)
    Required sub-key: default_ttl_days (positive integer)
    Optional sub-key: by_source (list of {source_id, ttl_days} mappings)

    Returns a flattened lookup dict::

        {
            "default_ttl_days": int,
            "by_source": { source_id: ttl_days, ... }
        }

    Raises ConfigError on any violation.
    """
    ARTIFACT = "memory_retention.yaml"
    data = _load_yaml(path, ARTIFACT)

    if not isinstance(data, dict):
        raise ConfigError(
            f"[{ARTIFACT}] Top level must be a YAML mapping."
        )

    _require(data, "retention", ARTIFACT)
    retention = data["retention"]

    if not isinstance(retention, dict):
        raise ConfigError(
            f"[{ARTIFACT}] 'retention' must be a YAML mapping."
        )

    _require(retention, "default_ttl_days", ARTIFACT, context="retention")
    default_ttl = retention["default_ttl_days"]
    if not isinstance(default_ttl, (int, float)) or int(default_ttl) <= 0:
        raise ConfigError(
            f"[{ARTIFACT}] 'default_ttl_days' must be a positive integer "
            f"(in retention); got {default_ttl!r}."
        )

    by_source_lookup: dict[str, int] = {}
    by_source_list = retention.get("by_source")
    if by_source_list is not None:
        if not isinstance(by_source_list, list):
            raise ConfigError(
                f"[{ARTIFACT}] 'by_source' must be a list (in retention)."
            )
        for i, entry in enumerate(by_source_list):
            if not isinstance(entry, dict):
                raise ConfigError(
                    f"[{ARTIFACT}] by_source[{i}] must be a YAML mapping."
                )
            ctx = f"by_source[{i}]"
            _require(entry, "source_id", ARTIFACT, context=ctx)
            _require(entry, "ttl_days", ARTIFACT, context=ctx)
            ttl = entry["ttl_days"]
            if not isinstance(ttl, (int, float)) or int(ttl) <= 0:
                raise ConfigError(
                    f"[{ARTIFACT}] 'ttl_days' must be a positive integer "
                    f"({ctx}); got {ttl!r}."
                )
            by_source_lookup[entry["source_id"]] = int(ttl)

    return {
        "default_ttl_days": int(default_ttl),
        "by_source": by_source_lookup,
    }
