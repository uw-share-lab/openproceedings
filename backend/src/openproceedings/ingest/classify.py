"""Track and status from source evidence (spec 01 §Track taxonomy; openreview-venueids and track-taxonomy skills).

Only an OpenReview `content.venueid` or a proceedings listing decides track and status, never an invitation
(the scholarmend lesson, forum `zkNCWtw2fd`). A venueid is `<Org>.cc/<YYYY>/<rest>`: a trailing
`*Submission` segment is the status, the remaining segments are the track, matched as whole segments.
Workshop wins over every other segment; nothing ever defaults to `main`; a form that parses but isn't in
the taxonomy is `other`, and anything that doesn't parse is `unknown` (logged at DEBUG, per record; the
importer reports the count).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger("openproceedings.ingest.classify")

_VENUEID = re.compile(r"(NeurIPS|ICLR|ICML)\.cc/([0-9]{4})/(.+)")
_STATUS_SUFFIX = {
    "Submission": "unknown",  # under review, or never decided
    "Rejected_Submission": "rejected",
    "Withdrawn_Submission": "withdrawn",
    "Desk_Rejected_Submission": "desk_rejected",
}
_DATASETS = frozenset({"Datasets_and_Benchmarks", "Datasets_and_Benchmarks_Track"})
_POSITION = frozenset({"Position_Paper_Track", "Position_Paper", "Position"})
_TINY = frozenset({"TinyPapers", "Tiny_Papers"})
_BLOG = frozenset({"BlogPosts", "BlogPost", "Blog_Posts", "Blogposts"})
_COMPETITION = frozenset({"Competition", "Competition_Track"})


@dataclass(frozen=True, slots=True)
class Classification:
    track: str
    status: str
    venue: str | None = None
    year: int | None = None
    venue_id_raw: str | None = None
    parsed: bool = True


def _is_workshop(segment: str) -> bool:
    return segment == "Workshop" or segment.startswith("Workshop_")


def _track(segments: list[str]) -> str:
    """The track of a venueid's path (status suffix already removed), by whole segments."""
    if any(_is_workshop(s) for s in segments):
        return "workshop"  # rule 1: workshop wins, whatever follows
    if segments == ["Conference"]:
        return "main"
    if _DATASETS & set(segments) and set(segments) <= _DATASETS | {"Track", "Round1", "Round2"}:
        return "datasets_benchmarks"
    if _POSITION & set(segments) and set(segments) <= _POSITION | {"Track"}:
        return "position"
    if segments in ([t] for t in _TINY):
        return "tiny_papers"
    if segments in ([b] for b in _BLOG):
        return "blogpost"
    if _COMPETITION & set(segments) and set(segments) <= _COMPETITION | {"Track"}:
        return "competition"
    return "other"  # parses, but isn't a track in the taxonomy: kept, never included by default


def classify_venueid(venueid: str) -> Classification:
    """Track, status, venue and year from an OpenReview venueid; `unknown` if it doesn't parse."""
    m = _VENUEID.fullmatch(venueid)
    segments = m.group(3).split("/") if m else []
    if m is None or not all(segments):
        log.debug("venueid_unparsed", extra={"venue_id_raw": venueid})
        return Classification(track="unknown", status="unknown", venue_id_raw=venueid, parsed=False)
    status = "accepted"  # an accepted paper has the bare venue path (skill: rule 2)
    if len(segments) > 1 and segments[-1] in _STATUS_SUFFIX:
        status = _STATUS_SUFFIX[segments.pop()]
    return Classification(
        track=_track(segments), status=status, venue=m.group(1), year=int(m.group(2)), venue_id_raw=venueid
    )


def classify_proceedings(track_token: str) -> Classification:
    """Track from a proceedings listing's track token (scholarmend's `proceedings_url` track claim, e.g.
    `Conference`, `Datasets_and_Benchmarks_Track`). A listing in the proceedings means accepted."""
    if not track_token:
        return Classification(track="unknown", status="accepted", parsed=False)
    return Classification(track=_track(track_token.split("/")), status="accepted")
