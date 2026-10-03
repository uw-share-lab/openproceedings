# A re-emitted character reference without its `;` garbled titles, and the garbled titles then lost their abstracts

**Key lesson:** When a parser hands references on raw to a later decoder (`convert_charrefs=False`, then `html.unescape`), re-emit each one whole with its `;`, and test it with a hex reference followed by hex-digit letters and an HTML5-only named reference followed by letters: legacy names such as `&amp;`/`&eacute;` decode without `;` and hide the bug.

- **Date:** 2026-09-29 · **Task:** task-128 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/html.py` (`_reference`), `backend/tests/unit/ingest/test_html.py::test_both_parsers_re_emit_each_reference_whole`

## What we set out to do
Find why TASK-072's real-data check saw two NeurIPS proceedings titles that failed to merge with their OpenReview notes (`A ⟊tch`, `Fr\⟬het`).

## What we learned
- CPython's `HTMLParser` reports `&#x27;` as `handle_charref("x27")` and `&rsquo;` as `handle_entityref("rsquo")`, consuming the `;` (Python 3.12.9, probed directly). Both parsers wrote back `&#x27` and `&rsquo`. `html.unescape` then read on greedily: `&#x27Catch` → U+27CA `⟊tch`; `&rsquos` has no legacy form and stayed literal; `&notinx` decoded as `¬inx` through the legacy `&not` prefix.
- Writing the `;` back is exactly faithful here, because `_BARE_AMP` has already escaped every `&` that does not start a complete, `;`-terminated reference. So every reference the handlers see had its `;` on the page.
- Attribute values never had the bug: `HTMLParser` decodes them itself. That covers `citation_title`, which is why only listing-derived titles broke.
- The damage went further than the title. The garbled listing title failed the abstract page's `citation_title` match, so the paper also lost its abstract and page authors. On the 2026-09-29 cache, 11 of 26,019 NeurIPS records changed: 3 titles (each also gaining its abstract and authors) and 8 abstracts with `&mdash;`/`&ndash;`. PMLR (14,281) and the ICLR archive (146) were unchanged.
- In a scratch snapshot rebuilt from the same commit with each version, the fix merged the 2023 and 2025 proceedings-only duplicates into their OpenReview notes (95,940 → 95,938 records). NeurIPS 2023 and 2025 main now match their official counts exactly, and missing abstracts went from 574 to 571.

## Dead ends — don't repeat these
- Checking `unescape()` alone: `unescape('A &#x27;Catch')` is correct. The loss happens where the parser re-emits the reference, so test through `text_of` and `parse` + `node_text`.

## Decisions (and what would change them)
- Named references get their `;` back too. An unknown `&foo;` now stays `&foo;` as the page wrote it, where before it was `&foo`. A page that relied on a semicolon-less legacy reference (`&copy` with no `;`) would reverse this, but `_BARE_AMP` already treats such a reference as text.

## Follow-ups
- none

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/neurips-proceedings/SKILL.md` §Abstract extraction
- Test or hook added? — the parametrised test above (9 of its rows fail on the old handlers) and `test_attribute_values_are_decoded_by_htmlparser_not_the_reference_handlers`
