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

## NII reconciliation workbook

`parse-nii-tables.py` → `nii-segment.csv`, `nii-avgbal.csv`,
`nii-ratevolume.csv` → `build-nii-workbook.py` →
`capital-one-nii-reconciliation.xlsx` (4 sheets).

Three tables, three jobs. **Segment Results and Reconciliation** (note 13.1) is
the reconciliation proper — segment NII summing to the consolidated total.
**Average Balances, NII and Net Interest Margin** decomposes NII by product into
average balance, interest and yield. **Rate/Volume Analysis** splits the change
in NII into volume and rate effects.

None of the MD&A tables are XBRL-tagged — probing six values returned zero
tagged hits, while figures that also appear on the face of the income statement
are tagged. So these are parsed from rendered HTML. The parser maps the ordered
numeric values in each row onto the ordered column headers (because `$` and `%`
occupy their own cells, making column position unreliable) and rejects any row
whose count doesn't match rather than guessing.

Validation: segment NII ties to the consolidated total at zero difference across
all 14 quarters 2023Q1–2026Q2, and every consolidated figure matches the income
statement extracted independently from XBRL. Volume + rate ties to total
variance throughout.

Q4 segment figures are derived as FY − 9M (no 3-month Q4 segment table is
reported). Average balances are NOT derived for Q4 — averages don't subtract
that way — so annual rows are labelled `FY`, not `Q4`.

## There is no monthly income statement

`make-monthly-pl.py` → `monthly-pl-cof.csv`. Read the header before using it.

Exactly **one** income-statement line is disclosed monthly: net charge-offs, in
the Reg FD credit-metrics 8-K. Interest income, interest expense, NII,
non-interest income and expense, provision and net income exist only quarterly —
an income statement is a duration, and the shortest duration issuers report is a
quarter (Q4 not even that; see below). So the monthly file carries monthly
charge-offs plus the credit and balance context needed to read them, and writes
quarterly NII and net income **only on quarter-end rows**. Intra-quarter cells
are blank on purpose. Dividing a quarter's NII by three would look like data and
be an assumption; do that in your model where it's visible.

Coverage: 24 months, 2024-08 to 2026-07, with one structural gap — **Capital One
does not file a September exhibit.** Filing dates run Aug 2024 (filed 9/16)
directly to Oct 2024 (filed 11/15), and Aug 2025 (9/15) directly to Oct 2025
(11/17). Eleven filings a year, September omitted, two years running. The
discovery scans every 8-K in the window, so this is an absence in the
disclosure, not a retrieval failure.

### Exhibit layouts, and why the parser looks the way it does

Both layouts were verified against all 28 downloaded files. Neither resembles a
plain table.

Capital One: segments down rows, metrics across a **two-tier** header. The group
header (`Loans Held for Investment`, `Net Charge-Offs`, ...) spans several
columns and must be forward-filled before combining with the sub-header
(`Average`, `Period-End`, `Amount`, `Rate`). `$` and `%` occupy their own cells,
so the number sits at the metric column or one to the right. Rows ending in `:`
are captions, not data.

Discover: fully transposed — months across columns in **two stacked 12-month
blocks** (24 observations per file), metrics down rows, denominated in
**billions**. Mixing that with Capital One's millions would understate Discover
by 1000x, so everything is normalised to $mm.

Validations that pass: Discover ending loans land at ~99,000 $mm as expected for
a ~$100bn book; monthly period-end loans reconcile to 10-Q gross loans at
70-76% coverage across six quarter-ends; and from June 2025 the exhibit's three
additive card rows check out — `Capital One Domestic` + `Discover Domestic` =
`Domestic Card` (152,772 + 99,709 = 252,481), 4/4 months passing.

That last one caught a real bug. Both `Capital One Domestic` and `Domestic Card`
contain "domestic", so an earlier segment map collapsed the legacy and combined
lines into one, letting whichever came last silently overwrite the other. They
are now separate segments: `domestic_card_legacy_cof`, `discover_domestic_card`
and `domestic_card` (combined).

## Income statement / net interest income

`extract-local-flows.py` → `flows.csv` → `make-nii-table.py` → `nii-cof.csv`.
Ten quarters, 2024Q1 through 2026Q2. Add `--annual` for 12-month columns.

The wrinkle is Q4. A balance sheet is an instant so every quarter-end is
reported directly, but an income statement is a duration and issuers report
3M in Q1, 3M+6M in Q2, 3M+9M in Q3, and **12M only** in the 10-K. There is no
3-month Q4 figure anywhere. So Q4 is derived as FY − 9M, flagged `(D)` in the
table and `derived=Q4=FY-9M` in the CSV. The subtraction is exact, but it spans
two filings, so a restatement between them would land there.

Validation: interest income less interest expense ties to reported NII at 0.0
for all ten quarters, and the four quarters of 2024 and 2025 each sum to the
reported full year at 0.0 — which independently confirms the derived Q4s.

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

python3 download-periodic.py --filer all   # 10-K/10-Q for both companies
./download-filings.sh                      # monthly credit-metrics 8-Ks
python3 extract-local-anchors.py           # balance sheet -> anchors.csv
python3 extract-local-flows.py             # income statement -> flows.csv
python3 make-balance-sheet.py --since 2024-06-30
python3 make-nii-table.py   --since 2024Q3
python3 parse-credit-metrics.py --dump     # LOOK at the tables first
python3 parse-credit-metrics.py            # -> credit-metrics-{raw,tidy}.csv
python3 build-monthly.py                   # -> monthly-balance-sheet.csv
```

`MONTHS_BACK=36 ./download-filings.sh` to reach further back. You need at least
through April 2025 for Discover's final standalone exhibit.

### No duplicate downloads

`download-periodic.py` is the only script that fetches periodic filings.
`download-filings.sh` used to fetch them too, with hardcoded names
(`capitalone-10q-q1-2026.htm`) while the periodic script derives them from the
reporting period (`capitalone-10q-2026q1.htm`), so every filing landed twice —
about 29 MB of byte-identical duplicates. Now:

- `download-filings.sh` no longer downloads periodic filings at all; it prints
  the `download-periodic.py` command instead.
- `download-periodic.py` recognises **both** naming conventions before
  downloading, so a filing already held under a legacy name is skipped and
  reported rather than re-fetched.
- `extract-local-anchors.py` and `extract-local-flows.py` skip byte-identical
  files by SHA-256, so any duplicates still on disk are read only once.

Default `--since` is `2024-06-01`, which covers the 2024-06-30 and 2024-09-30
quarter-ends. Use `--since 2024-01-01` to add 2024-03-31.

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
