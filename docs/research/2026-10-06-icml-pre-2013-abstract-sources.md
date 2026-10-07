# Official ICML pages with per-paper abstracts, 1988–2012

Status: verified live 2026-10-06 (TASK-206, decision-047) · read by `backend/src/openproceedings/ingest/icml_sites.toml`

The dblp release that gives ICML 1988–2012 (TASK-205, `2026-10-06-pre-2013-neurips-icml-sources.md`) has no
abstracts. This survey asked, for every year, which **official** ICML or IMLS conference pages still hold
per-paper abstracts, live or as an Internet Archive capture. Allowed: official ICML/IMLS pages (icml.cc, each
year's own conference site), live or a pinned `web.archive.org` capture of one. Not used: ACM DL (2004–2008;
scraping forbidden), Google Scholar, Semantic Scholar, author pages, arXiv, dblp.org (robots forbids crawling).
About 80 survey requests were made, at least 3 s apart on web.archive.org (the CDX API found the captures).

## The main finding

icml.cc still serves copies of the old conference sites under `https://icml.cc/Conferences/<year>/<original
file name>` (sometimes with `.html` appended); only the directory index pages answer 404. machinelearning.org
(IMLS) now redirects to icml.cc, so its old proceedings pages exist only as captures. Every page here is served
as bare `text/html` with no charset. Most pages from 2001 to 2011 are cp1252 (curly quotes and accented names in
the 0x80–0x9F range); 2009 is ASCII, 2012 is UTF-8, and so are five 2007 captures (papers 148, 225, 245, 260 and
326). Each page's charset is a column of `backend/src/openproceedings/ingest/icml_sites.toml`.

## Per year

| Year | Source used (live, or pinned capture) | Format | Entries | Left out |
|---|---|---|---|---|
| 2012 | live `https://icml.cc/2012/papers/` | one page: `div.paper#paper-N` with `h2` title, `p.type`, `p.abstract` (`<p>` never closed) | 243 | 4 typed "Not for proceedings" (247 on the page) |
| 2011 | live `https://icml.cc/Conferences/2011/papers.php.html` (copy of icml-2011.org, now a spam site) | one page: `<a name='N'><h3>` title, `Abstract:</span>` text | 152 | 8 Invited Cross-Conference Track papers (other venues', no abstracts) |
| 2010 | live `https://icml.cc/Conferences/2010/abstracts.html` (copy of icml2010.org, now a spam site) | one page: `<a name="N">`, `<h3>` title, `p.abstracts` | 159 (7 invited application papers, IDs 901–907, included) | none |
| 2009 | live `https://icml.cc/Conferences/2009/abstracts.html` | one page: `<h3><a name="N">` title, `paper ID: N`, a `<p>` abstract | 160 | the sidebar's "For Participants" heading (reuses `name="10"`, no paper ID) |
| 2008 | live `https://icml.cc/Conferences/2008/abstracts.shtml.html` (copy of the Helsinki site, also live) | one page: `<a name="N">`, `paper ID`, `<h3>` title, `<p><i>` authors, `<p>` abstract | 158 | none |
| 2007 | titles: live `https://icml.cc/Conferences/2007/paperlist.html`; abstracts: 150 per-paper captures of `http://oregonstate.edu:80/conferences/icml2007/abstracts/N.htm` (the earliest 200 capture of each; 146 from 2007-11) | list `<a name="N"> title</a>`; per-paper CyberChair table | 150 titles + 150 abstracts, joined by paper number | the per-paper pages' own titles, which PDF extraction broke ("Unsup ervised"); the abstracts keep such breaks ("Ma jor"), which is the source's text |
| 2006 | none | — | 0 | icml2006.org's `technical/accepted.html`, icml.cc's `proceedings.html` and IMLS's proceedings directory list titles and PDFs only |
| 2005 | none | — | 0 | icml.cc's `accepted_papers.php.html` and `proceedings.html`, and icml.ais.fraunhofer.de's captures: titles and PDFs only |
| 2004 | capture `20040907123036` of `http://www.aicml.cs.ualberta.ca:80/banff04/icml/pages/abstracts/allAbstracts.html` (the Banff site's camera-ready abstracts) | one CyberChair page: per paper a `<table>`, `<th>` title, `<td>` authors, `<td><pre>` abstract | 118 | icml.cc's live per-paper copies (`Conferences/2004/proceedings/abstracts/N.htm`) glue words at line breaks ("set offeatures"); the `<pre>` copy keeps them |
| 2003 | capture `20030628150843` of `http://www.hpl.hp.com:80/conferences/icml2003/allAbstracts.html` (the conference site at HP Labs) | one CyberChair page | 118 | not on icml.cc |
| 2002 | none | — | 0 | icml.cc's `paper_list.txt` and `ICML_program.html`: titles and authors only; no abstracts page among the UNSW site's captures |
| 2001 | capture `20010708012312` of `http://www.ecn.purdue.edu:80/ICML2001/accepted-papers.html` (the site was at Purdue; icml.cc's 2007 "past conferences" page names it) | one CyberChair page, alphabetical by first author | 79 | `student-abstracts.html`, a separate page of student posters |
| 2000 | none | — | 0 | `www-csli.stanford.edu/icml2k/` `schedule.html` and `posters.html`: titles only |
| 1999 | none | — | 0 | icml.cc's `Conferences/1999/accepted.html` and the Bled site: titles only |
| 1998 | **not used**: per-paper captures of `cs.wisc.edu/icml98/papers/paperN.html` (66) | free-text `<PRE>`: title, authors with addresses, e-mails and phone numbers, abstract, keywords | — | submission abstracts, with contact details; titles may differ from the published papers (an owner question) |
| 1997 | **not used**: capture `19970619200718` of `cswww.vuse.vanderbilt.edu/~icml97/program.html` | one page of free-text `<pre>` blocks, layout varying by paper | — | as 1998 (an owner question) |
| 1996 | none | — | 0 | icml.cc's `Conferences/1996/Sched.html` and the di.unito.it site: titles only |
| 1988–1995 | none | — | 0 | icml.cc has no pages for these years and both official "past ICMLs" lists give no website; other hosts were not guessed |

**Years with an official abstract source used:** 2001, 2003, 2004, 2007, 2008, 2009, 2010, 2011, 2012.
**Years with none:** 1988–1996, 1999, 2000, 2002, 2005, 2006. **Found but not used:** 1997, 1998 (submission
abstracts with personal contact details; whether to use their abstract text, never the contact details, is an owner
question, not filed as a task).

## How the table uses it

`ingest/icml_sites.toml` names each page above (159 rows: one per year, plus 2007's 150 captures), its parser,
charset and the entry count verified here; a page that now gives another count stops the crawl. An abstract is
attached to a dblp record only when exactly one page entry and exactly one dblp paper of the year share the
title key (spec 01 §Sources, ICML sites row). What attached, per year, is in the dblp crawl reports and in
`2026-10-06-pre-2013-neurips-icml-sources.md`.
