"""
config/registry.py — SourceRegistry for BusinessIntelligence.ai.

Builds a dict of SourceRegistryEntry objects from the validated sources config,
computes freshness status on construction, and exposes update_last_refresh() so
the ETL loader can pin a specific scenario clock (e.g. make marketing stale).

Freshness rules (Requirements 1.5, 1.6):
  - FRESH   : staleness_minutes <= sla_minutes  (within SLA)
  - STALE   : staleness_minutes >  sla_minutes  (exceeded SLA)
  - UNKNOWN : sla_minutes == 0   (SLA undefined — cannot evaluate)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from models import FreshnessStatus, SourceRegistryEntry


# Default offset applied when constructing entries without an explicit
# last_refresh timestamp.  Set conservatively to 5 minutes so that freshly
# constructed entries start as FRESH for sources whose SLA >= 5 min.
_DEFAULT_OFFSET_MINUTES: int = 5


class SourceRegistry:
    """
    In-memory registry of data-source metadata, including freshness state.

    Usage:
        registry = SourceRegistry(sources_config)      # from load_sources()
        entry = registry.get("orders")
        registry.update_last_refresh("marketing", stale_ts)
    """

    def __init__(self, sources_config: list[dict]) -> None:
        """
        Build the registry from the validated list returned by load_sources().

        Each entry's last_refresh defaults to utcnow() minus
        _DEFAULT_OFFSET_MINUTES, making it immediately FRESH for sources with
        a reasonable SLA.  Call update_last_refresh() to override.
        """
        self._entries: dict[str, SourceRegistryEntry] = {}

        default_refresh = datetime.utcnow() - timedelta(minutes=_DEFAULT_OFFSET_MINUTES)

        for src in sources_config:
            entry = SourceRegistryEntry(
                source_id=src["id"],
                name=src.get("name", src["id"]),
                grain=src["grain"],
                cadence_minutes=int(src["cadence_minutes"]),
                last_refresh=default_refresh,
                sla_minutes=int(src["sla_minutes"]),
                freshness_status=FreshnessStatus.UNKNOWN,  # placeholder; set below
                data_quality=float(src["data_quality"]),
                lineage=list(src.get("lineage", [])),
                owner=src.get("owner", ""),
                decay_policy=src.get("decay_policy", "linear"),
                temporal_policy=src.get("temporal_policy", "snapshot"),
            )
            # Compute and store initial freshness
            entry.freshness_status = self.compute_freshness(entry)
            self._entries[entry.source_id] = entry


    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, source_id: str) -> SourceRegistryEntry:
        """
        Return the SourceRegistryEntry for *source_id*.

        Raises KeyError if the source is not registered, with a descriptive
        message so callers can propagate a clear error indication.
        """
        if source_id not in self._entries:
            raise KeyError(
                f"SourceRegistry: unknown source_id '{source_id}'. "
                f"Registered sources: {sorted(self._entries)}"
            )
        return self._entries[source_id]

    def all_entries(self) -> dict[str, SourceRegistryEntry]:
        """Return a shallow copy of the full source map."""
        return dict(self._entries)

    def compute_freshness(self, entry: SourceRegistryEntry) -> FreshnessStatus:
        """
        Derive freshness status from the entry's current last_refresh and SLA.

        - UNKNOWN  : sla_minutes == 0 (SLA undefined)
        - FRESH    : staleness_minutes <= sla_minutes
        - STALE    : staleness_minutes >  sla_minutes
        """
        if entry.sla_minutes == 0:
            return FreshnessStatus.UNKNOWN

        if entry.is_within_sla:
            return FreshnessStatus.FRESH
        else:
            return FreshnessStatus.STALE

    def update_last_refresh(self, source_id: str, ts: datetime) -> None:
        """
        Override the last_refresh timestamp for *source_id* and recompute
        freshness_status.

        Called by the ETL/data-loader layer to install a scenario-specific
        clock.  For INC_001, marketing is made intentionally stale by passing
        a timestamp roughly 5 hours in the past.

        Raises KeyError (from self.get) if *source_id* is not registered.
        """
        entry = self.get(source_id)
        entry.last_refresh = ts
        entry.freshness_status = self.compute_freshness(entry)
