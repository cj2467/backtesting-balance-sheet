# Capital One / Schwab monthly balance-sheet scaffold

Builds a monthly time series for Capital One out of SEC disclosure, on top of
the Schwab and Capital One periodic filings in `filings/`.

## Current state

Done: the six periodic filings are downloaded and confirmed genuine (titles
`cof-20251231`, `schw-20260630`, etc., 3-9 MB each). `anchors.csv` holds real
quarterly balance-sheet data for Capital One at four period-ends, extracted
offline from those files, and it articulates to the dollar.
`balance-sheet-cof.csv` renders that as a quarterly statement.

Outstanding, two things:

1. The monthly 8-K exhibits have not been retrieved. The first run hit a gzip
   bug (below) and produced an empty manifest. Re-run `./download-filings.sh`.
2. Three quarter-ends are missing — see below. Run `download-periodic.py`.

## RESOLVED: all seven quarter-ends are now available

`download-periodic.py` fetched the 2025 10-Qs and FY2024 10-Ks. Capital One now
has complete, articulating balance sheets at 2023-12-31, 2024-12-31, 2025-03-31,
2025-06-30, 2025-09-30, 2025-12-31, 2026-03-31 and 2026-06-30 — seven
consecutive quarters from the requested 2024-12-31 start, plus one earlier.
`make-balance-sheet.py --since 2024-12-31` renders it. The section below records
why the original four-quarter set was limited, for reference.

## Why only four quarters, and how to get seven

A 10-Q balance sheet shows the current quarter-end and the prior year-end, and
nothing else. So the FY2025 10-K plus the two 2026 10-Qs yield exactly four
dates: 2024-12-31, 2025-12-31, 2026-03-31, 2026-06-30.

For a series starting 2024-12-31 you also want 2025-03-31, 2025-06-30 and
2025-09-30. Those are **not recoverable from the files on hand.** Measured by
counting consolidated tagged facts per period-end:

| period-end | tagged facts | balance sheet lines present |
|---|---|---|
| 2024-12-31 | 145 | full |
| 2025-03-31 | 4 | equity, deposits, cash only |
| 2025-06-30 | 5 | equity, deposits, cash only |
| 2025-09-30 | 0 | none at all |
| 2025-12-31 | 177 | full |
| 2026-03-31 | 150 | full |
| 2026-06-30 | 150 | full |

The handful at 2025-03-31 and 2025-06-30 are comparatives from the statement of
changes in equity and the cash flow statement, not a balance sheet. 2025-09-30
is absent outright.

The 10-K is not an alternative source: it carries no "Selected Quarterly
Financial Data" table (the SEC eliminated that Item 302(a) requirement in 2021),
and its "Average Balances" tables are annual averages, not quarter-end
positions.

The missing dates come from the 2025 10-Qs:

```bash
python3 download-periodic.py --since 2024-12-01        # discovers + fetches
python3 extract-local-anchors.py
python3 make-balance-sheet.py
```

That should produce all seven quarter-ends with no further changes.

## Order of operations

```bash
export SEC_UA="CJ cjbox21@gmail.com"      # SEC requires a real contact string

./download-filings.sh                      # periodic filings + monthly 8-Ks
python3 extract-local-anchors.py           # quarterly anchors, OFFLINE -> anchors.csv
python3 parse-credit-metrics.py --dump     # LOOK at the tables first
python3 parse-credit-metrics.py            # -> credit-metrics-{raw,tidy}.csv
python3 build-monthly.py                   # -> monthly-balance-sheet.csv
```

`MONTHS_BACK=36 ./download-filings.sh` to reach further back. You need at least
through April 2025 for Discover's final standalone exhibit.

## The scripts

`download-filings.sh` — the periodic filings, then walks EDGAR's submissions
index for CIK 927628 (Capital One) and 1393612 (Discover) looking for monthly
credit-metrics exhibits. Accession numbers aren't predictable, so they're
discovered rather than hardcoded. Caches, reports missing months, and now exits
non-zero if it retrieves nothing.

`extract-local-anchors.py` — **preferred.** Reads the quarterly balance sheet
straight out of the downloaded 10-K/10-Q files, which are inline XBRL. No
network. Keeps only consolidated facts (a context carrying `explicitMember` is a
segment breakdown, not a group total — that filter is why one document holds 38
differently-scoped "Assets" facts but few real balance-sheet values). Enforces
one XBRL tag per concept across the whole series and reports what it rejected.

`download-periodic.py` — discovers and downloads every 10-K/10-Q for a filer
since a given period, from EDGAR's submissions index. Names files to the
convention the extractor expects. Use this to fill quarter-end gaps.

`make-balance-sheet.py` — quarterly balance sheet from `anchors.csv`, dates as
columns, with reported subtotals, an explicit residual line, and a Net row
(assets − liabilities − equity) as an articulation check.

`fetch-xbrl-anchors.py` — same output schema via the companyconcept API. Needs
network; useful for periods beyond the filings you've downloaded.

`parse-credit-metrics.py` — 8-K exhibit tables into CSV. Emits a raw cell dump
alongside the tidy layer, because the tidy layer guesses at layout.

`build-monthly.py` — the monthly grid. Monthly-disclosed lines from the 8-Ks;
quarterly-only lines at quarter-ends from `anchors.csv`; intra-quarter cells
blank. Every value carries a `*_src` column.

## Limitations, in order of how much they matter

**The sheet does not balance monthly, by design.** Deposits (~$484bn as of
2026-06-30), securities, cash and equity have no monthly disclosure and appear
only at quarter-ends. Assets will not tie to liabilities plus equity
intra-quarter. You supply those assumptions; this supplies only facts.

**Monthly data covers roughly 77% of the loan book** and nothing else on the
balance sheet. `monthly-coverage.csv` computes it exactly at each quarter-end.
The remainder — commercial banking, other consumer, securities, cash — has no
monthly signal at all.

**The pre-close Discover splice cannot be done in dollars.** Discover's
standalone monthly exhibit reported *rates only* (net principal charge-off rate,
30+ day delinquency rate), with no period-end balances. Combined monthly dollars
before May 2025 would require interpolating Discover's quarterly balances, which
contradicts the no-interpolation choice. Those cells are left blank with
`splice_status = pre_close_cof_only__combined_dollars_unavailable`. If you want
interpolated pre-close dollars, add it as an explicit modelling step.

**Gross vs net loans are separate columns and must not be conflated.** Capital
One tags both: `loans_hfi_gross` was $457.2bn at 2026-06-30 while
`loans_hfi_net` was $434.2bn — the $23.0bn allowance. The monthly 8-K reports
gross loans held for investment, so coverage uses the gross basis. An earlier
version picked whichever tag appeared first and silently mixed the two.

**Purchase-accounting distortions are flagged, not corrected.** The merger
closed 2025-05-18, so May 2025 is a partial month. Acquired Discover loans
already fully charged off are excluded from charge-offs, and a pre-Legal Day 1
accelerated charge-off unwind reduced June 2025 NCOs by roughly $39mm.

**Some figures came from search summaries, not filings.** Two searches disagreed
on the excluded fully-charged-off balance — $18.0bn versus $19.4bn (the latter
with ~$3.3bn expected recoveries). Anything marked VERIFY needs checking against
the financial supplement.

## Bugs found and fixed

**Empty manifest (fixed).** `download-filings.sh` sent
`Accept-Encoding: gzip` but never decompressed, so every JSON parse threw
`UnicodeDecodeError`, got swallowed by a broad `except`, and the run exited 0
with an empty manifest. Now decompresses (including when a proxy gzips without
setting the header) and exits 3 on zero exhibits.

**Mixed XBRL tags (fixed).** Cash was drawn from
`CashCashEquivalentsRestricted...` in some years and `CashAndDueFromBanks` in
others, making Capital One's cash look like it fell from $43.7bn to $3.0bn.
Tag selection is now global per concept with conflicts reported.

**Silent parser failure (fixed).** The tidy layer produced zero rows for
Discover's rolling-month layout and said nothing. It now reports any file
yielding no tidy rows.

## Testing status

Verified against real data: the six filing URLs resolve to the correct
documents; inline-XBRL extraction across all six, with assets tying to
liabilities plus equity to the dollar at eight period-ends; tag-conflict
detection; gross-vs-net loan reconciliation via the allowance.

Verified offline only: filename→period parsing across all 13 real exhibit
naming patterns from both filers; download filters not cross-matching; XBRL fact
selection (restatement precedence, form filtering, date cutoffs); HTML table
extraction including colspan, entities, `$`/`%`, parenthesised negatives,
em-dash blanks, footnote rows; month-label parsing across 15 formats; gzip
handling on three encoding paths.

Not verified: the monthly 8-K discovery has never successfully run, and no
script has seen a real exhibit. **The tidy layer of the parser is the most
likely thing to need adjustment** — run `--dump`, compare against the filing,
and extend `SEGMENTS`/`METRICS`.
