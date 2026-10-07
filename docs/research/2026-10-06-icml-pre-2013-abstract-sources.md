# Official ICML pages with per-paper abstracts, 1988–2012

Status: verified live 2026-10-06 (TASK-206, decision-047); 1997 and 1998 verified 2026-10-07 and used by the owner's
decision of that day (TASK-207) · read by `backend/src/openproceedings/ingest/icml_sites.toml`

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
| 2007 | titles: live `https://icml.cc/Conferences/2007/paperlist.html`; abstracts: 150 per-paper captures of `http://oregonstate.edu:80/conferences/icml2007/abstracts/N.htm` (icml.cc's `Conferences/2008/past_icmls.shtml.html` names the Oregon State site) (the earliest 200 capture of each; 146 from 2007-11) | list `<a name="N"> title</a>`; per-paper CyberChair table | 150 titles + 150 abstracts, joined by paper number | the per-paper pages' own titles, which PDF extraction broke ("Unsup ervised"); the abstracts keep such breaks ("Ma jor"), which is the source's text |
| 2006 | none | — | 0 | icml2006.org's `technical/accepted.html`, icml.cc's `proceedings.html` and IMLS's proceedings directory list titles and PDFs only |
| 2005 | none | — | 0 | icml.cc's `accepted_papers.php.html` and `proceedings.html`, and icml.ais.fraunhofer.de's captures: titles and PDFs only |
| 2004 | capture `20040907123036` of `http://www.aicml.cs.ualberta.ca:80/banff04/icml/pages/abstracts/allAbstracts.html` (the Banff site's camera-ready abstracts; icml.cc's `Conferences/2007/pastconferences.html` names the site, as `/_banff04/icml/`) | one CyberChair page: per paper a `<table>`, `<th>` title, `<td>` authors, `<td><pre>` abstract | 118 | icml.cc's live per-paper copies (`Conferences/2004/proceedings/abstracts/N.htm`) glue words at line breaks ("set offeatures"); the `<pre>` copy keeps them |
| 2003 | capture `20030628150843` of `http://www.hpl.hp.com:80/conferences/icml2003/allAbstracts.html` (the conference site at HP Labs: icml.cc's `Conferences/2007/pastconferences.html` names `/conferences/icml03/`, whose `titlesAndAuthors.html` links each paper to this page) | one CyberChair page | 118 | not on icml.cc |
| 2002 | none | — | 0 | icml.cc's `paper_list.txt` and `ICML_program.html`: titles and authors only; no abstracts page among the UNSW site's captures |
| 2001 | capture `20010708012312` of `http://www.ecn.purdue.edu:80/ICML2001/accepted-papers.html` (the site was at Purdue; icml.cc's 2007 "past conferences" page names it) | one CyberChair page, alphabetical by first author | 79 | `student-abstracts.html`, a separate page of student posters |
| 2000 | none | — | 0 | `www-csli.stanford.edu/icml2k/` `schedule.html` and `posters.html`: titles only |
| 1999 | none | — | 0 | icml.cc's `Conferences/1999/accepted.html` and the Bled site: titles only |
| 1998 | 66 per-submission captures of `http://www.cs.wisc.edu:80/icml98/papers/paperN.html` (the earliest 200 capture of each, 1999–2000; five are under `/ICML98/`, which the site also answered with the same bytes); icml.cc's `Conferences/2007/pastconferences.html` names the site | per page `<H1>ICML-98 Submission #N</H1>`, then the form as filled in, free text in a `<PRE>` or in HTML: title (labelled or not), authors with postal addresses, e-mail and phone, abstract, keywords, contact author's e-mail and phone | 66 (65 with an `Abstract` heading) | everything but the abstract (TASK-207): titles, authors, addresses, e-mails, phone and fax numbers, keywords; the abstract is the one submitted, and some titles differ from the published papers', so those stay unattached |
| 1997 | capture `19970619200718` of `http://cswww.vuse.vanderbilt.edu:80/~icml97/program.html` (the ICML-97/COLT-97 site's joint schedule `~mlccolt/schedule.html`, capture `19980209071717`, links each ICML-97 paper here) | one page: a list `<li><a href="#N"> title</a>`, then per paper `<a name="N"></a>` and the form as filled in, free text in a `<pre>`, layout varying by paper | 49 (46 with an `Abstract` heading) | as 1998; the title is the list's |
| 1996 | none | — | 0 | icml.cc's `Conferences/1996/Sched.html` and the di.unito.it site: titles only |
| 1988–1995 | none | — | 0 | icml.cc has no pages for these years and both official "past ICMLs" lists give no website; other hosts were not guessed |

**Years with an official abstract source used:** 1997, 1998, 2001, 2003, 2004, 2007, 2008, 2009, 2010, 2011, 2012.
**Years with none:** 1988–1996, 1999, 2000, 2002, 2005, 2006. 1997 and 1998 were first left out (submission
abstracts beside personal contact details) as an owner question; on 2026-10-07 the owner decided to use the abstract
text alone, never the contact details (decision-047, TASK-207).

### 1997 and 1998: the abstract only

Each submission is the call for papers' form as its authors filled it in, so the layout varies by paper: `TITLE:`,
`Title:`, `title :` or no label; `ABSTRACT:`, `Abstract (200 word maximum):`, a centred `Abstract`, or `Abstract:`
with the first words after it, sometimes underlined with dashes; then `Keywords`, `Email address of contact author`,
`EMAIL`, `VOICE`, `FAX`, `Phone number`, `Tel`, `Corresponding author` and other spellings. The parsers
(`icml_sites.icml1997`, `icml1998_paper`) keep only the lines after the first `Abstract` heading, up to the first
line that starts one of those later fields (a contact label with any words before its colon; `Topic`, `Area`,
`Category`, `Track` only with the colon right after them, so an abstract line such as `Areas under the ROC curve: …`
stays text); a line of dashes under the heading is dropped, and an abstract that no field ends is withheld, since
whatever follows it is unknown. An entry with no
`Abstract` heading (1997: 3; 1998: 1) gives no abstract: there the authors' block and the abstract run together.
What is kept is checked once more (`icml_sites.contact_detail`): an abstract holding an e-mail address, a
phone-shaped number (7 digits or more, in a row or in groups that are not all years, or a `+` country code), a contact label
(`Phone:`, `Fax.`) or a US state and ZIP code is withheld whole and counted. Read against every 1997 and 1998 page on
2026-10-07: no abstract was withheld, none ran into a later field, and none was cut short. The Internet Archive
answered many requests that day with a dropped connection or a 503; a retry a few seconds later succeeded each time.
26 of the 66 1998 pages and the 1997 page end without `</html>` (the archive serves the original bytes, with their
`Content-Length`), so these captures are judged whole by that length, not by the closing tag the shared HTTP layer
otherwise requires.

## How the table uses it

`ingest/icml_sites.toml` names each page above (226 rows: one per year, plus 2007's 150 captures and 1998's 66), its parser,
charset and the entry count verified here; a page that now gives another count stops the crawl. An abstract is
attached to a dblp record only when exactly one page entry and exactly one dblp paper of the year share the
title key (spec 01 §Sources, ICML sites row). What attached, per year, is in the dblp crawl reports and in
`2026-10-06-pre-2013-neurips-icml-sources.md`.
