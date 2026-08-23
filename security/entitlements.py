"""
security/entitlements.py — Backend entitlement boundary (Security_Engine).

Resolves a persona to an AuthorizationScope and filters evidence so that
unauthorized data NEVER reaches any LLM prompt.

This is the single chokepoint: all evidence passes through filter_evidence()
before any LLM call.  Fail-closed: if entitlements.yaml is missing/invalid
the scope resolves to empty (Requirement 5.8).

Requirements: 5.1, 5.3, 5.5, 5.6, 5.8, 5.9, 8.7
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from models import Evidence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class EntitlementError(Exception):
    """
    Raised only when the authorization scope cannot be resolved at all —
    e.g. a YAML parse failure that prevents loading the configuration.
    In the normal fail-closed path (missing file, invalid schema) the engine
    swallows the error, logs a warning, and returns an empty scope instead
    of raising (Requirement 5.8).
    """


# ---------------------------------------------------------------------------
# AuthorizationScope
# ---------------------------------------------------------------------------

@dataclass
class AuthorizationScope:
    """
    The resolved entitlement set for a single persona + optional region.

    authorized_sources      — frozenset of source_id strings the persona may access
    authorized_fields       — source_id -> frozenset of allowed field names
    authorized_regions      — "all" or "own_only"
    region_filter           — the specific region string when authorized_regions == "own_only"
    is_empty                — True when the scope was produced by the fail-closed path
    """

    persona: str
    authorized_sources: frozenset[str] = field(default_factory=frozenset)
    authorized_fields: dict[str, frozenset[str]] = field(default_factory=dict)
    authorized_regions: str = "all"          # "all" | "own_only"
    region_filter: Optional[str] = None      # set when authorized_regions == "own_only"
    is_empty: bool = False                   # True ⟹ fail-closed; no evidence allowed


# ---------------------------------------------------------------------------
# SecurityEngine
# ---------------------------------------------------------------------------

class SecurityEngine:
    """
    Backend entitlement enforcement engine.

    Usage:
        engine = SecurityEngine.from_yaml("config/entitlements.yaml")
        scope  = engine.authorize("analyst")
        auth_evidence, denied = engine.filter_evidence(scope, candidates)
    """

    # -----------------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------------

    def __init__(self, entitlements_config: dict) -> None:
        """
        Parameters
        ----------
        entitlements_config:
            The parsed result of load_entitlements() — a dict containing a
            top-level "personas" key whose value is a dict of persona configs.
        """
        raw_personas: dict = entitlements_config.get("personas", {}) or {}
        self._personas: dict[str, dict] = raw_personas

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def authorize(
        self,
        persona: str,
        region: Optional[str] = None,
    ) -> AuthorizationScope:
        """
        Resolve *persona* to an AuthorizationScope.

        Behaviour
        ---------
        - If persona is not in the config: return an empty scope (is_empty=True).
        - If authorized_regions == "own_only" and region is None: raise ValueError
          because the caller must supply the region for region-filtered personas.
        - authorized_sources is a frozenset of source id strings.
        - authorized_fields maps source_id -> frozenset of allowed field names.

        Requirements: 5.1
        """
        persona_key = persona.lower()
        config = self._personas.get(persona_key)

        if config is None:
            logger.warning(
                "SecurityEngine.authorize: persona %r not found in entitlements; "
                "returning empty scope (fail-closed).",
                persona,
            )
            return AuthorizationScope(
                persona=persona,
                authorized_sources=frozenset(),
                authorized_fields={},
                authorized_regions="all",
                region_filter=None,
                is_empty=True,
            )

        authorized_regions: str = config.get("authorized_regions", "all")

        if authorized_regions == "own_only" and region is None:
            raise ValueError(
                f"Persona {persona!r} has authorized_regions='own_only' but no "
                "region was supplied to SecurityEngine.authorize()."
            )

        raw_sources: list[str] = config.get("authorized_sources", []) or []
        authorized_sources: frozenset[str] = frozenset(raw_sources)

        raw_fields: dict[str, list[str]] = (
            config.get("authorized_fields", {}) or {}
        )
        authorized_fields: dict[str, frozenset[str]] = {
            source_id: frozenset(fields)
            for source_id, fields in raw_fields.items()
        }

        return AuthorizationScope(
            persona=persona,
            authorized_sources=authorized_sources,
            authorized_fields=authorized_fields,
            authorized_regions=authorized_regions,
            region_filter=region if authorized_regions == "own_only" else None,
            is_empty=False,
        )

    def filter_evidence(
        self,
        scope: AuthorizationScope,
        candidates: list[Evidence],
    ) -> tuple[list[Evidence], list[str]]:
        """
        Filter *candidates* to only those evidence items whose source_id is in
        the persona's authorized scope.

        The function is:
        - **Idempotent**: re-filtering an already-filtered set returns an identical
          result (the same subset — same objects, same order).
        - **Never widens scope**: no source_id or field outside the authorization
          scope is ever added.

        Field-level filtering (removing individual fields from an Evidence object)
        is handled by the Evidence_Engine before Evidence objects are created, so
        this method only enforces the source-level boundary.

        Returns
        -------
        authorized_evidence : list[Evidence]
            Evidence items whose source_id ∈ scope.authorized_sources.
        access_denied_source_ids : list[str]
            Distinct source_ids that were present in *candidates* but were
            removed by the filter.  Sorted for determinism.

        Requirements: 5.3, 5.4, 5.5, 5.9
        """
        authorized: list[Evidence] = []
        denied_ids: set[str] = set()

        for item in candidates:
            if item.source_id in scope.authorized_sources:
                authorized.append(item)
            else:
                denied_ids.add(item.source_id)

        return authorized, sorted(denied_ids)

    def get_access_denied_result(
        self,
        scope: AuthorizationScope,
        denied_sources: list[str],
    ) -> dict:
        """
        Build an access-denied result dict that lists excluded source_ids
        WITHOUT including any evidence content.

        The returned dict is safe to return from the API and surface in the UI:
        it carries enough information to display the access-denied panel while
        guaranteeing no evidence content leaks.

        Returns
        -------
        dict with keys:
            access_denied      : True
            excluded_sources   : sorted list of excluded source_id strings
            persona            : the persona string from *scope*

        Requirements: 5.6, 5.7
        """
        return {
            "access_denied": True,
            "excluded_sources": sorted(set(denied_sources)),
            "persona": scope.persona,
        }

    # -----------------------------------------------------------------------
    # Factory methods
    # -----------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, entitlements_path: "str | Path") -> "SecurityEngine":
        """
        Factory: load entitlements.yaml and return a SecurityEngine.

        On missing file, unreadable file, or YAML parse failure:
          - log a warning (never raise)
          - return a fail-closed SecurityEngine (every authorize() → empty scope)

        Requirement 5.8
        """
        path = Path(entitlements_path)

        if not path.exists():
            warnings.warn(
                f"SecurityEngine.from_yaml: entitlements file not found at "
                f"{path!s}; using fail-closed engine (empty scope for all personas).",
                stacklevel=2,
            )
            logger.warning(
                "entitlements.yaml not found at %s; fail-closed engine active.",
                path,
            )
            return cls.fail_closed()

        try:
            with path.open("r", encoding="utf-8") as fh:
                config = yaml.safe_load(fh)
        except Exception as exc:  # noqa: BLE001 — intentional broad catch for fail-closed
            warnings.warn(
                f"SecurityEngine.from_yaml: failed to load/parse {path!s}: {exc!s}; "
                "using fail-closed engine.",
                stacklevel=2,
            )
            logger.warning(
                "Failed to load entitlements from %s: %s; fail-closed engine active.",
                path,
                exc,
            )
            return cls.fail_closed()

        if not isinstance(config, dict) or "personas" not in config:
            warnings.warn(
                f"SecurityEngine.from_yaml: {path!s} is missing the top-level "
                "'personas' key; using fail-closed engine.",
                stacklevel=2,
            )
            logger.warning(
                "entitlements.yaml at %s is invalid (missing 'personas'); "
                "fail-closed engine active.",
                path,
            )
            return cls.fail_closed()

        return cls(config)

    @classmethod
    def fail_closed(cls) -> "SecurityEngine":
        """
        Return a SecurityEngine where every authorize() call returns an empty
        scope (is_empty=True).  Used when entitlements.yaml cannot be resolved.

        Requirement 5.8
        """
        return cls({"personas": {}})


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def authorize_and_filter(
    persona: str,
    region: Optional[str],
    entitlements_config: dict,
    candidates: list[Evidence],
) -> tuple[list[Evidence], AuthorizationScope, list[str]]:
    """
    Convenience wrapper used by the Orchestrator.

    Creates a SecurityEngine from *entitlements_config*, resolves the
    AuthorizationScope for *persona* / *region*, filters *candidates*, and
    returns all three artefacts together.

    Parameters
    ----------
    persona             : persona string (e.g. "analyst", "cfo")
    region              : region string or None (required for "own_only" personas)
    entitlements_config : parsed entitlements dict (from load_entitlements())
    candidates          : full candidate evidence list before filtering

    Returns
    -------
    authorized_evidence : list[Evidence]  — only authorized items
    scope               : AuthorizationScope  — the resolved scope
    denied_source_ids   : list[str]  — sorted list of denied source ids

    Requirements: 5.1, 5.3, 5.4, 5.5, 5.6, 5.8, 5.9, 8.7
    """
    engine = SecurityEngine(entitlements_config)
    scope = engine.authorize(persona, region=region)
    authorized, denied = engine.filter_evidence(scope, candidates)
    return authorized, scope, denied
