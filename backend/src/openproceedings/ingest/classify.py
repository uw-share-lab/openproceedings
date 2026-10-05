"""Track and status from source evidence (spec 01 §Track taxonomy; openreview-venueids and track-taxonomy skills).

Only an OpenReview `content.venueid` (for status in API v1 years, `content.venue`: last bullet) or a proceedings
listing decides track and status, never an invitation (the scholarmend lesson, forum `zkNCWtw2fd`). A venueid
is `<Org>.cc/<YYYY>/<rest>`, parsed exactly:

- The last segment is the status when it is one of `_STATUS_SUFFIX`; any other status-like last segment
  (`Blind_Submission`, `Withdrawn`, `Post_Decision`, …) is status `unknown`, never `accepted`. A suffix
  needs a track in front of it.
- The remaining segments are the track, matched as an exact tuple per organisation (`_TRACKS`): only the
  forms in the skill's table reach a default-filter track. Workshop wins over every other segment (any
  case). A form that parses but isn't in the table is `other`; nothing ever defaults to `main`.
- A `-` segment (an invitation path), a year outside 2013–2099, or anything off the grammar doesn't parse:
  `unknown`/`unknown`, logged at DEBUG per record. The RIS importer then skips the record, as
  `unresolved` when the venueid names one of the three venues, else `out_of_scope`, and counts it.
- **An API v1 venue-year's venueid is never status evidence** (`_V1_YEARS`; TASK-095): v1 puts the bare
  venue path on rejected submissions too (ICLR 2017/2022/2023, NeurIPS 2021–2022, D&B 2021), so there the
  venueid gives venue, year and track, and status `unknown`. A v1 note's status comes from its
  `content.venue` string (`classify_v1_venue`), its decision note, or its withdrawn / desk-rejected
  invitation (decision-012; the v1 adapters, TASK-051).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

_VENUEID = re.compile(r"(NeurIPS|ICLR|ICML)\.cc/([0-9]{4})/(.+)")
_YEARS = range(2013, 2100)  # ICLR's first year onward
# Venue-years OpenReview serves through API v1 (docs/research/2026-09-27-openreview-and-proceedings-facts.md
# §Hosts and API versions): ICLR 2013–2023 and NeurIPS 2021–2022, main and D&B. Their venueid never gives status.
_V1_YEARS: dict[str, range] = {"ICLR": range(2013, 2024), "NeurIPS": range(2021, 2023)}
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
# Each value is (track, valid years); a None range means the path is stable across held years. Rows follow
# the openreview-venueids skill's table; add one only for a form and year range verified on live evidence.
_TRACKS: dict[tuple[str | None, tuple[str, ...]], tuple[str, range | None]] = {
    (None, ("Conference",)): ("main", None),
    ("NeurIPS", ("Track", "Datasets_and_Benchmarks")): ("datasets_benchmarks", range(2022, 2025)),
    ("NeurIPS", ("Track", "Datasets_and_Benchmarks_Track")): ("datasets_benchmarks", range(2022, 2025)),
    ("NeurIPS", ("Datasets_and_Benchmarks_Track",)): ("datasets_benchmarks", range(2024, 2026)),
    ("NeurIPS", ("Track", "Datasets_and_Benchmarks", "Round1")): ("datasets_benchmarks", range(2021, 2022)),
    ("NeurIPS", ("Track", "Datasets_and_Benchmarks", "Round2")): ("datasets_benchmarks", range(2021, 2022)),
    # NeurIPS renamed D&B for 2026 (a live group, no public notes on 2026-09-27; TASK-094)
    ("NeurIPS", ("Evaluations_and_Datasets_Track",)): ("datasets_benchmarks", range(2026, 2100)),
    ("NeurIPS", ("Track", "Competition")): ("competition", range(2022, 2100)),
    ("NeurIPS", ("Competition_Track",)): ("competition", range(2024, 2100)),
    ("ICML", ("Position_Paper_Track",)): ("position", range(2025, 2100)),
    ("NeurIPS", ("Position_Paper_Track",)): ("position", range(2025, 2100)),
    ("ICLR", ("TinyPapers",)): ("tiny_papers", range(2023, 2025)),
    ("ICLR", ("BlogPosts",)): ("blogpost", range(2023, 2100)),
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
# NeurIPS's Creative AI track: the one `other` form both OpenReview (`NeurIPS.cc/<Y>/Creative_AI_Track`) and the
# NeurIPS proceedings (`-Abstract-Creative_AI_Track.html`) name, so dedup may merge a Creative AI note with its
# listing (TASK-137). Every other `other` form is OpenReview's alone.
CREATIVE_AI = "Creative_AI_Track"


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


def _track(venue: str, year: int, path: tuple[str, ...]) -> str:
    """The exact track path when its evidence-backed year window includes `year`."""
    for key in ((venue, path), (None, path)):
        if (rule := _TRACKS.get(key)) is not None:
            track, years = rule
            return track if years is None or year in years else "other"
    return "other"


def classify_venueid(venueid: str) -> Classification:
    """Track, status, venue and year from an OpenReview venueid; `unknown` if it doesn't parse."""
    m = _VENUEID.fullmatch(venueid)
    segments = m.group(3).split("/") if m else []
    if m is None or not all(segments) or "-" in segments or int(m.group(2)) not in _YEARS:
        return _unparsed(venueid)
    venue, year, suffix = m.group(1), int(m.group(2)), None
    last = segments[-1]
    workshop_name = len(segments) >= 2 and _is_workshop(segments[-2])  # `Workshop/Rejected` is a name
    if not workshop_name and (last in _STATUS_SUFFIX or _STATUS_LIKE.fullmatch(last)):
        if len(segments) == 1:
            return _unparsed(venueid)  # a status with no track in front of it
        suffix = last
        segments = segments[:-1]
    # Rule 1: workshop wins, whatever follows.
    track = "workshop" if any(_is_workshop(s) for s in segments) else _track(venue, year, tuple(segments))
    if is_v1(venue, year):
        status = "unknown"  # v1 puts the bare path on rejected papers too: status comes from elsewhere
    elif suffix is not None:
        status = _STATUS_SUFFIX.get(suffix, "unknown")
    else:  # the bare path means accepted only for a form we know (skill: rule 2); `other` stays unknown
        status = "accepted" if track != "other" else "unknown"
    return Classification(track=track, status=status, venue=venue, year=year, venue_id_raw=venueid)


def is_creative_ai_venueid(venueid: str, year: int) -> bool:
    """Whether `venueid` is NeurIPS `year`'s Creative AI track (`CREATIVE_AI`), bare or with a status suffix,
    exactly: no other organisation, year or path (TASK-137)."""
    m = _VENUEID.fullmatch(venueid)
    if m is None or m.group(1) != "NeurIPS" or int(m.group(2)) != year:
        return False
    segments = m.group(3).split("/")
    if len(segments) == 2 and (segments[1] in _STATUS_SUFFIX or _STATUS_LIKE.fullmatch(segments[1])):
        segments = segments[:1]
    return segments == [CREATIVE_AI] and classify_venueid(venueid).track == "other"


def is_v1(venue: str, year: int) -> bool:
    """Whether OpenReview serves this venue-year through API v1, where a venueid is not status evidence."""
    return year in _V1_YEARS.get(venue, range(0))


def _v1(venue: str, year: int, track: str, **by_status: str) -> dict[str, tuple[str, int, str, str]]:
    return {v: (venue, year, track, status) for status, vs in by_status.items() for v in vs.split("|")}


# `content.venue` on an API v1 submission note, exactly as seen live (research doc §How status is
# represented): string → (venue, year, track, status). Only the years whose venue string carries the
# decision; ICLR 2018–2020 and ICLR 2021's rejected notes have none (the decision note decides, TASK-051).
# An unlisted string is `unknown`, never guessed from its wording.
_V1_VENUE: dict[str, tuple[str, int, str, str]] = {
    **_v1("ICLR", 2017, "main", accepted="ICLR 2017 Oral|ICLR 2017 Poster", rejected="Submitted to ICLR 2017"),
    # invited to the workshop track: not a main-track acceptance, and whether it was presented isn't said
    **_v1("ICLR", 2017, "workshop", unknown="ICLR 2017 Invite to Workshop"),
    **_v1("ICLR", 2021, "main", accepted="ICLR 2021 Oral|ICLR 2021 Spotlight|ICLR 2021 Poster"),
    **_v1("ICLR", 2022, "main", accepted="ICLR 2022 Oral|ICLR 2022 Spotlight|ICLR 2022 Poster",
          rejected="ICLR 2022 Submitted"),
    **_v1("ICLR", 2023, "main", accepted="ICLR 2023 notable top 5%|ICLR 2023 notable top 25%|ICLR 2023 poster",
          rejected="Submitted to ICLR 2023"),
    **_v1("ICLR", 2023, "tiny_papers", unknown="Submitted to Tiny Papers @ ICLR 2023"),  # all 219 say this
    **_v1("ICLR", 2023, "blogpost", accepted="Blogposts @ ICLR 2023", rejected="Submitted to Blogposts @ ICLR 2023",
          unknown="Blogposts @ ICLR 2023 Conditional"),
    **_v1("NeurIPS", 2021, "main", accepted="NeurIPS 2021 Oral|NeurIPS 2021 Spotlight|NeurIPS 2021 Poster",
          rejected="NeurIPS 2021 Submitted"),
    **_v1("NeurIPS", 2022, "main", accepted="NeurIPS 2022 Accept", rejected="NeurIPS 2022 Submitted"),
    **_v1("NeurIPS", 2021, "datasets_benchmarks",
          accepted="NeurIPS 2021 Datasets and Benchmarks Track (Round 1)|"
          "NeurIPS 2021 Datasets and Benchmarks Track (Round 2)",
          rejected="Submitted to NeurIPS 2021 Datasets and Benchmarks Track (Round 1)|"
          "Submitted to NeurIPS 2021 Datasets and Benchmarks Track (Round 2)"),
    **_v1("NeurIPS", 2022, "datasets_benchmarks", accepted="NeurIPS 2022 Datasets and Benchmarks "),  # sic: space
}  # fmt: skip


# v1 venueids that name no track (openreview-venueids table): ICLR 2013's and 2017's lower-case `conference`, which
# 2017 puts on workshop invitations too. They classify as `other`; in the RIS importer a note's `content.venue` gives
# its track as well as its status (TASK-142), and another `other` venueid's track is never taken from the string (the
# v1 crawler, scoped by its listings, uses `openreview_v1._NOT_A_TRACK` instead). 2013 is listed to match the table:
# no 2013 string is in `_V1_VENUE`, so a 2013 record stays `other`/`unknown`.
V1_TRACK_FROM_VENUE = frozenset({"ICLR.cc/2013/conference", "ICLR.cc/2017/conference"})


def classify_v1_venue(venue_string: str) -> Classification:
    """Venue, year, track and status from an API v1 submission note's `content.venue`, matched exactly: a v1
    year's status evidence, with the decision note and the withdrawn / desk-rejected invitations. An unlisted
    string is `unknown`/`unknown`, unparsed. The caller checks venue and year against the note's venueid."""
    hit = _V1_VENUE.get(venue_string)
    if hit is None:
        log.debug("v1_venue_unparsed")  # the string itself can be free text (scrubbed fixtures show emails)
        return Classification(track="unknown", status="unknown", parsed=False)
    venue, year, track, status = hit
    return Classification(track=track, status=status, venue=venue, year=year)


def classify_proceedings(track_token: str) -> Classification:
    """Track from a proceedings listing's track token (scholarmend's `proceedings_url` track claim, e.g.
    `Conference`, `Datasets_and_Benchmarks_Track`). A listing in the proceedings means accepted."""
    if not track_token:
        return Classification(track="unknown", status="accepted", parsed=False)
    if any(_is_workshop(s) for s in track_token.split("/")):
        return Classification(track="workshop", status="accepted")
    track = _PROCEEDINGS.get(track_token, "unknown")
    return Classification(track=track, status="accepted", parsed=track != "unknown")


# NeurIPS proceedings listings (neurips-proceedings skill §Track vocabulary): the evidence rules that give a
# listing its track from its host, year and path token. Each rule is named in the claim's evidence.
NEURIPS_MAIN_HOSTS = frozenset({"proceedings.neurips.cc", "papers.nips.cc"})
NEURIPS_DB_2021_HOST = "datasets-benchmarks-proceedings.neurips.cc"
_TOKENLESS_LAST_YEAR = 2021  # 1987-2021 abstract links carry no track token; the year page has one track
_DB_ALIAS = "Datasets_and_Benchmarks"
_DB_ALIAS_LAST_YEAR = 2023  # the <=2023 spelling of Datasets_and_Benchmarks_Track (scholarmend's alias)
# The 2021 D&B host numbers each round separately, so a round is part of a paper's identity
# (urls.proceedings_native; record.py's native-id pattern is built from this set).
NEURIPS_DB_2021_ROUNDS = frozenset({"round1", "round2"})


def classify_neurips_listing(host: str, year: int, token: str | None) -> tuple[Classification, str]:
    """Track (and `accepted`) for a paper listed in the NeurIPS proceedings, with the evidence rule that
    gave it. A form no rule covers is `unknown` (counted and flagged), never `main`."""

    def listed(track: str, rule: str) -> tuple[Classification, str]:
        cls = Classification(
            track=track, status="accepted", venue="NeurIPS", year=year, parsed=track != "unknown"
        )
        return cls, rule

    host = host.lower()
    if host == NEURIPS_DB_2021_HOST:
        if year == 2021 and token in NEURIPS_DB_2021_ROUNDS:
            return listed("datasets_benchmarks", f"{host} {token}: NeurIPS 2021 Datasets and Benchmarks")
        return listed("unknown", f"{host} token {token} in {year}: no rule")
    if host not in NEURIPS_MAIN_HOSTS:
        return listed("unknown", f"{host}: not a NeurIPS proceedings host")
    if token is None:
        if year <= _TOKENLESS_LAST_YEAR:
            return listed("main", f"{host} {year}: no track token, so the main track (host and year)")
        return listed("unknown", f"{host} {year}: no track token after {_TOKENLESS_LAST_YEAR}: no rule")
    if token == _DB_ALIAS:
        if year <= _DB_ALIAS_LAST_YEAR:
            return listed("datasets_benchmarks", f"track token {token} (<=2023 alias of {token}_Track)")
        return listed("unknown", f"track token {token} after {_DB_ALIAS_LAST_YEAR}: no rule")
    track = classify_proceedings(token).track
    return listed(track, f"track token {token}" + (": no rule" if track == "unknown" else ""))


# --- presentation from an API v2 `content.venue` (TASK-101) --------------------------------------------------


def _v2p(track: str, **by_presentation: str) -> dict[str, tuple[str, str | None]]:
    """`content.venue` strings (`|`-separated) → (track, presentation); `none=` lists strings that state no
    presentation."""
    return {
        s: (track, None if p == "none" else p)
        for p, strings in by_presentation.items()
        for s in strings.split("|")
    }


# `content.venue` on an accepted, non-workshop API v2 submission note, exactly as held in the TASK-054 crawl
# cache (2026: the TASK-178 one; counts in spec 01 §Presentation): (venue, year) → string → (the track its
# venueid must give, presentation). Case and wording drift per year, so it's a table, never a regex. ICML
# 2023's `OralPoster` and ICML 2025's `spotlightposter` are orals and spotlights that also had a poster slot:
# the higher tier is the presentation. A `none` string is known and states no presentation (Tiny Papers'
# Archive/Present/Notable tiers are not presentations). Anything unlisted is unmapped: `null`, counted. ICML
# 2026's other tier, `ICML 2026 regular` (and `ICML 2026 Position Paper Track regular`), is left out on purpose:
# it names no presentation, and nothing recorded says a regular paper was a poster.
V2_PRESENTATION: dict[tuple[str, int], dict[str, tuple[str, str | None]]] = {
    ("ICLR", 2024): {
        **_v2p("main", oral="ICLR 2024 oral", spotlight="ICLR 2024 spotlight", poster="ICLR 2024 poster"),
        **_v2p("blogpost", none="BT@ICLR2024"),
        **_v2p("tiny_papers",
               none="Tiny Papers @ ICLR 2024 Archive|Tiny Papers @ ICLR 2024 Present|Tiny Papers @ ICLR 2024 Notable"),
    },
    ("ICLR", 2025): {
        **_v2p("main", oral="ICLR 2025 Oral", spotlight="ICLR 2025 Spotlight", poster="ICLR 2025 Poster"),
        **_v2p("blogpost", none="ICLR 2025 Blogpost Track"),
    },
    ("ICLR", 2026): _v2p("main", oral="ICLR 2026 Oral", poster="ICLR 2026 Poster"),  # no spotlight tier
    ("ICML", 2023): _v2p("main", oral="ICML 2023 OralPoster", poster="ICML 2023 Poster"),
    ("ICML", 2024): _v2p("main", oral="ICML 2024 Oral", spotlight="ICML 2024 Spotlight", poster="ICML 2024 Poster"),
    ("ICML", 2025): {
        **_v2p("main", oral="ICML 2025 oral", spotlight="ICML 2025 spotlightposter", poster="ICML 2025 poster"),
        **_v2p("position", oral="ICML 2025 Position Paper Track oral",
               spotlight="ICML 2025 Position Paper Track spotlightposter",
               poster="ICML 2025 Position Paper Track poster"),
    },
    ("ICML", 2026): {
        **_v2p("main", spotlight="ICML 2026 spotlight"),
        **_v2p("position", spotlight="ICML 2026 Position Paper Track spotlight"),
    },
    ("NeurIPS", 2023): {
        **_v2p("main", oral="NeurIPS 2023 oral", spotlight="NeurIPS 2023 spotlight", poster="NeurIPS 2023 poster"),
        **_v2p("datasets_benchmarks", oral="NeurIPS 2023 Datasets and Benchmarks Oral",
               spotlight="NeurIPS 2023 Datasets and Benchmarks Spotlight",
               poster="NeurIPS 2023 Datasets and Benchmarks Poster"),
    },
    ("NeurIPS", 2024): {
        **_v2p("main", oral="NeurIPS 2024 oral", spotlight="NeurIPS 2024 spotlight", poster="NeurIPS 2024 poster"),
        **_v2p("datasets_benchmarks", oral="NeurIPS 2024 Track Datasets and Benchmarks Oral",
               spotlight="NeurIPS 2024 Track Datasets and Benchmarks Spotlight",
               poster="NeurIPS 2024 Track Datasets and Benchmarks Poster"),
        **_v2p("competition", none="NeurIPS 2024 Competition Track"),
    },
    ("NeurIPS", 2025): {
        **_v2p("main", oral="NeurIPS 2025 oral", spotlight="NeurIPS 2025 spotlight", poster="NeurIPS 2025 poster"),
        **_v2p("datasets_benchmarks", oral="NeurIPS 2025 Datasets and Benchmarks Track oral",
               spotlight="NeurIPS 2025 Datasets and Benchmarks Track spotlight",
               poster="NeurIPS 2025 Datasets and Benchmarks Track poster"),
        **_v2p("position", oral="NeurIPS 2025 Position Paper Track Oral", none="NeurIPS 2025 Position Paper Track"),
    },
}  # fmt: skip


@dataclass(frozen=True)
class PresentationMatch:
    value: str | None  # `oral` / `spotlight` / `poster`, or None
    mapped: bool  # False: the string (or its track) isn't in the venue-year's table


def classify_v2_presentation(venue: str, year: int, track: str, venue_string: object) -> PresentationMatch:
    """The presentation an accepted, non-workshop API v2 note's `content.venue` states, matched exactly in its
    venue-year's table. A string the table lacks, or lists under another track than the venueid gave, is
    unmapped (`None`); the caller counts it. Workshop sessions are not the conference's presentations and
    are never looked up."""
    hit = V2_PRESENTATION.get((venue, year), {}).get(venue_string) if isinstance(venue_string, str) else None
    if hit is None or hit[0] != track:
        return PresentationMatch(None, mapped=False)
    return PresentationMatch(hit[1], mapped=True)
