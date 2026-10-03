"""The one timestamp form of the API (spec 04 §Conventions): an RFC 3339 date-time in UTC with a `Z` suffix,
`YYYY-MM-DDTHH:MM:SS[.ffffff]Z` (fractional seconds only when the source had them).

Manifests and cache entries store `isoformat()` text (`…+00:00`); stored search records keep whatever they
were written with. Neither is rewritten on disk: a response model types its timestamps as `Timestamp`,
which renders any offset-aware ISO 8601 value in that one form and is typed `format: date-time` in the
OpenAPI document. A value that isn't offset-aware ISO 8601 is left as it is (a stored body outlives the
code that reads it, so reading it never fails on a timestamp).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, WithJsonSchema

DATE_TIME_SCHEMA = {"type": "string", "format": "date-time"}


def utc_z(value: str) -> str:
    """`value` as a UTC `…Z` date-time, if it is an offset-aware ISO 8601 date-time; else unchanged."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return value
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


Timestamp = Annotated[str, AfterValidator(utc_z), WithJsonSchema(DATE_TIME_SCHEMA)]


class CrawlWindow(BaseModel):
    """When a source (or, under key `*`, the whole corpus) was fetched: the first and the last fetch. The
    shape of `crawl_dates` in a search record and in `GET /coverage`'s `snapshot`."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",  # stored in search records: tolerant, like every stored type
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,  # `from` on the wire and on disk, never the Python name
        json_schema_serialization_defaults_required=True,
    )

    from_: Timestamp = Field(alias="from")
    to: Timestamp
