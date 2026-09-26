"""Track and status from source evidence (spec 01 §Track taxonomy; openreview-venueids and track-taxonomy skills).

Only an OpenReview `content.venueid` or a proceedings listing decides track and status, never an invitation
(the scholarmend lesson, forum `zkNCWtw2fd`). A venueid is `<Org>.cc/<YYYY>/<rest>`, parsed exactly:

- The last segment is the status when it is one of `_STATUS_SUFFIX`; any other status-like last segment
  (`Blind_Submission`, `Withdrawn`, `Post_Decision`, …) is status `unknown`, never `accepted`. A suffix
  needs a track in front of it.
- The remaining segments are the track, matched as an exact tuple per organisation (`_TRACKS`): only the
  forms in the skill's table reach a default-filter track. Workshop wins over every other segment (any
  case). A form that parses but isn't in the table is `other`; nothing ever defaults to `main`.
- A `-` segment (an invitation path), a year outside 2013–2099, or anything off the grammar doesn't parse:
  `unknown`/`unknown`, logged at DEBUG per record. The RIS importer then skips the record, as
  `unresolved` when the venueid names one of the three venues, else `out_of_scope`, and counts it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger("openproceedings.ingest.classify")

_VENUEID = re.compile(r"(NeurIPS|ICLR|ICML)\.cc/([0-9]{4})/(.+)")
_YEARS = range(2013, 2100)  # ICLR's first year onward
_STATUS_SUFFIX = {
    "Submission": "unknown",  # under review, or never decided
    "Rejected_Submission": "rejected",
    "Withdrawn_Submission": "withdrawn",
    "Desk_Rejected_Submission": "desk_rejected",
}
# A last segment that names a status but not one we map: its status is unknown (never accepted).
# Whole words only, so a workshop named `SafeSubmission` or `AlignDecision` keeps its status.
_STATUS_LIKE = re.compile(r"(?:\w*_)?(?:Submissions?|Withdrawn|Rejected|Post_Decision)", re.IGNORECASE)
# Exact track paths (segments after the year, status suffix removed), per organisation; None = any.
# Rows follow the openreview-venueids skill's table; add one only for a form seen on a live note.
_TRACKS: dict[tuple[str | None, tuple[str, ...]], str] = {
    (None, ("Conference",)): "main",
    ("NeurIPS", ("Track", "Datasets_and_Benchmarks")): "datasets_benchmarks",
    ("NeurIPS", ("Track", "Datasets_and_Benchmarks_Track")): "datasets_benchmarks",
    ("NeurIPS", ("Datasets_and_Benchmarks_Track",)): "datasets_benchmarks",
    ("NeurIPS", ("Track", "Datasets_and_Benchmarks", "Round1")): "datasets_benchmarks",
    ("NeurIPS", ("Track", "Datasets_and_Benchmarks", "Round2")): "datasets_benchmarks",
    ("NeurIPS", ("Track", "Competition")): "competition",
    ("ICML", ("Position_Paper_Track",)): "position",
    ("ICLR", ("TinyPapers",)): "tiny_papers",
    ("ICLR", ("BlogPosts",)): "blogpost",
}
# Proceedings track tokens (scholarmend's `proceedings_url` claim values). All seen in the Trust-Evals
# corpus except `Datasets_and_Benchmarks`, scholarmend's alias for NeurIPS 2023 and earlier. An unseen
# token is `unknown`, never guessed.
_PROCEEDINGS = {
    "Conference": "main",
    "Datasets_and_Benchmarks_Track": "datasets_benchmarks",
    "Datasets_and_Benchmarks": "datasets_benchmarks",
    "Position_Paper_Track": "position",
    "Creative_AI_Track": "other",
}


@dataclass(frozen=True, slots=True)
class Classification:
    track: str
    status: str
    venue: str | None = None
    year: int | None = None
    venue_id_raw: str | None = None
    parsed: bool = True


def _is_workshop(segment: str) -> bool:
    s = segment.casefold()
    return s == "workshop" or s.startswith("workshop_")


def _unparsed(venueid: str) -> Classification:
    log.debug("venueid_unparsed", extra={"venue_id_raw": venueid})
    return Classification(track="unknown", status="unknown", venue_id_raw=venueid, parsed=False)


def classify_venueid(venueid: str) -> Classification:
    """Track, status, venue and year from an OpenReview venueid; `unknown` if it doesn't parse."""
    m = _VENUEID.fullmatch(venueid)
    segments = m.group(3).split("/") if m else []
    if m is None or not all(segments) or "-" in segments or int(m.group(2)) not in _YEARS:
        return _unparsed(venueid)
    venue, suffix = m.group(1), None
    last = segments[-1]
    workshop_name = len(segments) >= 2 and _is_workshop(segments[-2])  # `Workshop/Rejected` is a name
    if not workshop_name and (last in _STATUS_SUFFIX or _STATUS_LIKE.fullmatch(last)):
        if len(segments) == 1:
            return _unparsed(venueid)  # a status with no track in front of it
        suffix = last
        segments = segments[:-1]
    if any(_is_workshop(s) for s in segments):
        track = "workshop"  # rule 1: workshop wins, whatever follows
    else:
        path = tuple(segments)
        track = _TRACKS.get((venue, path)) or _TRACKS.get((None, path)) or "other"
    if suffix is not None:
        status = _STATUS_SUFFIX.get(suffix, "unknown")
    else:  # the bare path means accepted only for a form we know (skill: rule 2); `other` stays unknown
        status = "accepted" if track != "other" else "unknown"
    return Classification(track=track, status=status, venue=venue, year=int(m.group(2)), venue_id_raw=venueid)


def classify_proceedings(track_token: str) -> Classification:
    """Track from a proceedings listing's track token (scholarmend's `proceedings_url` track claim, e.g.
    `Conference`, `Datasets_and_Benchmarks_Track`). A listing in the proceedings means accepted."""
    if not track_token:
        return Classification(track="unknown", status="accepted", parsed=False)
    if any(_is_workshop(s) for s in track_token.split("/")):
        return Classification(track="workshop", status="accepted")
    track = _PROCEEDINGS.get(track_token, "unknown")
    return Classification(track=track, status="accepted", parsed=track != "unknown")
