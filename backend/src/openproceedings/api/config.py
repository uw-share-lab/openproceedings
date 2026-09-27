"""The API's configuration (spec 04 §Conventions, fastapi-conventions skill): one frozen model, built by
`op serve` from its flags and passed to `create_app`. Nothing reads the environment here.

The query-length cap is deliberately *not* configurable: it is the parser's `MAX_QUERY_LENGTH` (spec 02),
so the API refuses exactly what `op search` refuses (the API adds transport, not behaviour).
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, IPvAnyNetwork, field_validator, model_validator

# An index to serve: the `current` symlink, or an index_version (hex; `-` allowed for hand-named copies).
# Nothing else — no `/`, no `..` — so a name can never leave `<data_dir>/indexes/` (task-034 notes).
INDEX_NAME = re.compile(r"current|[0-9a-f][0-9a-f-]{0,63}")
# An exact origin: scheme, host, optional port; no path, no wildcard (fastapi-conventions §Rate limit and CORS).
ORIGIN = re.compile(r"https?://(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)(:[0-9]{1,5})?")


class RateLimit(BaseModel):
    """A per-client token bucket: `capacity` tokens, refilled at `refill_per_second`. A request costs one
    token; an export costs `export_weight` (it touches the whole matched set). `/healthz` is free."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = True
    capacity: float = Field(default=60.0, gt=0)
    refill_per_second: float = Field(default=1.0, gt=0)
    export_weight: float = Field(default=10.0, ge=1)
    max_clients: int = Field(default=100_000, ge=1)  # buckets held in memory; the least recent is dropped

    @model_validator(mode="after")
    def _export_fits(self) -> RateLimit:
        if self.export_weight > self.capacity:
            raise ValueError("export_weight must not exceed capacity, or no export could ever run")
        return self


class ApiConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    data_dir: Path
    index: str = "current"  # a name under <data_dir>/indexes (INDEX_NAME)
    rate_limit: RateLimit = RateLimit()
    cors_origins: tuple[str, ...] = ()  # exact origins; empty means no cross-origin access
    trusted_proxies: tuple[IPvAnyNetwork, ...] = ()  # peers whose X-Forwarded-For is believed
    # local dev only: lets the log formatter keep query-text fields (spec 04). No log call passes one today
    # (the access line never carries q), so it changes nothing until one does.
    log_query_text: bool = False
    # pinned index_versions (an export's `index_version`, a record's replay): engines held open besides the
    # served one, least recently used dropped first; size it to the versions the instance holds
    pinned_indexes: int = Field(default=4, ge=1)
    # how long a refused pin (absent, unloadable, tampered) is remembered before it is checked again; a
    # SIGHUP reload forgets every refusal at once
    pinned_refusal_seconds: float = Field(default=300.0, gt=0)
    load_in_background: bool = True  # /healthz answers (index_loaded false) while the index loads
    handle_sighup: bool = True  # SIGHUP reloads `index` and swaps it in (main thread only)

    @field_validator("index")
    @classmethod
    def _index_name(cls, v: str) -> str:
        if not INDEX_NAME.fullmatch(v):
            raise ValueError("index must be `current` or an index_version (0-9, a-f, -)")
        return v

    @field_validator("cors_origins")
    @classmethod
    def _origins(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for origin in v:
            if not ORIGIN.fullmatch(origin):
                raise ValueError(
                    f"CORS origin {origin!r} must be an exact scheme://host[:port], with no `*` and no path"
                )
        return v
