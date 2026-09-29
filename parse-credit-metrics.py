#!/usr/bin/env python3
"""
Parse the monthly credit-metrics 8-K exhibits into CSV.

    python3 parse-credit-metrics.py --dump      # inspect raw grids
    python3 parse-credit-metrics.py             # -> credit-metrics-{raw,tidy}.csv

Written against the ACTUAL exhibit layouts (verified on 28 files), which are
nothing like a plain table and differ completely between the two filers.

CAPITAL ONE -- segments down rows, metrics across a two-tier header.

    r1:            [6]Loans Held for Investment  [18]Net Charge-Offs  [30]30+ Day ...
    r2: [0](Dollars in millions) [6]Average [12]Period-End [18]Amount [24]Rate(1) ...
    r3: [0]Credit Card:(4)
    r4: [0]Domestic  [6]$ [7]256,704  [12]$ [13]258,940  [18]$ [19]881  [24]4.12 [26]%

  * The r1 group header spans several columns, so it must be forward-filled
    before combining with the r2 sub-header to identify a metric.
  * "$" and "%" occupy their OWN cells, so the number sits at the metric column
    or one to its right.
  * Rows ending in ":" are group captions (Credit Card:, Consumer Banking:),
    not data. The data row beneath carries the segment name.
  * Values are millions. Rates carry no scale.

DISCOVER -- fully transposed, and in BILLIONS.

    r1: [6]Apr 30, [9]Mar 31, [12]Feb 28, ...      <- month
    r2: [6]2025    [9]2025    [12]2025    ...      <- year
    r3: [0]Ending Loans   [6]$ [7]99.5  [9]$ [10]99.0 ...
    r5: [0]Net Principal Charge-off Rate  [6]5.04 [8]% ...
    r8/r9 + r10-13: a SECOND 12-month block for the prior year

  So one file yields 24 monthly observations, and unit is billions -- mixing
  that with Capital One's millions would understate Discover 1000x.

Everything is normalised to $mm in the tidy output; rates stay in percent.
The raw cell dump is always written as a fallback.

No third-party dependencies.
"""
import argparse, csv, glob, html, os, re, sys
from collections import defaultdict
from html.parser import HTMLParser


# ----------------------------------------------------------------- extraction

class TableExtractor(HTMLParser):
    """Tables as rectangular grids of text, honouring colspan."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._tstack = [], []
        self._row, self._cell, self._colspan = None, None, 1
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._tstack.append([])
        elif tag == "tr" and self._tstack:
            self._row = []
        elif tag in ("td", "th") and self._tstack:
            self._in_cell, self._cell = True, []
            try:
                self._colspan = max(1, int(a.get("colspan", 1)))
            except ValueError:
                self._colspan = 1
        elif tag == "br" and self._in_cell:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag == "table" and self._tstack:
            t = self._tstack.pop()
            if t:
                self.tables.append(t)
        elif tag == "tr" and self._tstack and self._row is not None:
            self._tstack[-1].append(self._row); self._row = None
        elif tag in ("td", "th") and self._in_cell:
            txt = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            if self._row is not None:
                self._row.append(txt)
                self._row.extend([""] * (self._colspan - 1))
            self._in_cell, self._cell, self._colspan = False, None, 1

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)


def extract_tables(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", "replace")

    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    p = TableExtractor()
    try:
        p.feed(text)
    except Exception as e:
        print(f"   ! parse error in {os.path.basename(path)}: {e}", file=sys.stderr)

    grids = []
    for t in p.tables:
        width = max((len(r) for r in t), default=0)
        grid = [r + [""] * (width - len(r)) for r in t]
        if any(any(c for c in r) for r in grid):
            grids.append(grid)
    return grids, text


# ----------------------------------------------------------------- primitives

DASHES = {"—", "–", "-", "n/a", "na", "nm", "", "n/a(6)"}


def to_number(s):
    """Bare numeric parse. '$'/'%' live in their own cells, so not handled here."""
    if s is None:
        return None
    t = html.unescape(s).replace("\xa0", " ").strip()
    t = re.sub(r"\(\d+\)$", "", t).strip()          # trailing footnote ref
    if t.lower() in DASHES or t in ("$", "%"):
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1].strip()
    t = t.replace(",", "").replace("$", "").replace("%", "").strip()
    if not re.fullmatch(r"-?\d*\.?\d+", t):
        return None
    v = float(t)
    return -v if neg else v


def detect_scale(doc_text):
    low = doc_text.lower()
    if "in billions" in low:
        return "billions"
    if "in thousands" in low:
        return "thousands"
    if "in millions" in low:
        return "millions"
    return "unknown"


SCALE_TO_MM = {"billions": 1000.0, "millions": 1.0, "thousands": 0.001}

MONTH_ABBR = {m[:3].lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


def norm(s):
    s = re.sub(r"\(\d+\)", " ", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s).strip().lower()


# ------------------------------------------------------- Capital One layout

# (group header, sub header) -> metric. Matched on substrings.
COF_METRICS = [
    ("loans held for investment", "average",    "average_loans",         "usd"),
    ("loans held for investment", "period-end", "period_end_loans",      "usd"),
    ("net charge-off",            "amount",     "net_charge_offs",       "usd"),
    ("net charge-off",            "rate",       "net_charge_off_rate",   "pct"),
    ("delinquenc",                "amount",     "delinquencies_30plus",  "usd"),
    ("delinquenc",                "rate",       "delinquency_rate_30plus", "pct"),
    ("nonperforming",             "amount",     "nonperforming",         "usd"),
    ("nonperforming",             "rate",       "nonperforming_rate",    "pct"),
]

# Longest label match wins, which matters enormously post-acquisition. From
# June 2025 the exhibit carries THREE additive card rows:
#
#   Capital One Domestic   150,686 avg / 152,772 EOP   <- legacy COF only
#   Discover Domestic       99,436 avg /  99,709 EOP   <- acquired book
#   Domestic Card          250,122 avg / 252,481 EOP   <- combined total
#
# 152,772 + 99,709 = 252,481. An earlier version mapped both "Capital One
# Domestic" and "Domestic Card" to the same segment because each contains
# "domestic", so the combined total silently overwrote the legacy line (or vice
# versa) depending on row order. Before the acquisition the sole row is just
# "Domestic", which is the total for that period.
COF_SEGMENTS = {
    "capital one domestic": "domestic_card_legacy_cof",
    "discover domestic":    "discover_domestic_card",
    "domestic card":        "domestic_card",
    "domestic":             "domestic_card",
    "international":        "international_card",
    "auto":                 "auto",
    "other consumer":       "other_consumer",
    "commercial":           "commercial_banking",
    "total company":        "total_company",
}


def cof_header(grid):
    """Locate the two header rows; return (group_row_i, sub_row_i, col->metric)."""
    for gi in range(min(6, len(grid))):
        if not any("loans held for investment" in norm(c) for c in grid[gi]):
            continue
        for si in range(gi + 1, min(gi + 4, len(grid))):
            sub = grid[si]
            if not any(norm(c) in ("average", "period-end", "amount") for c in sub):
                continue
            # forward-fill the spanning group header across columns
            groups, cur = [], ""
            for c in grid[gi]:
                if norm(c):
                    cur = norm(c)
                groups.append(cur)
            colmap = {}
            for ci, c in enumerate(sub):
                sc = norm(c)
                if not sc:
                    continue
                grp = groups[ci] if ci < len(groups) else ""
                for gpat, spat, metric, unit in COF_METRICS:
                    if gpat in grp and spat in sc:
                        colmap[ci] = (metric, unit)
                        break
            if colmap:
                return gi, si, colmap
    return None, None, {}


def cof_segment(label):
    n = norm(label)
    if not n or n.endswith(":"):
        return None                     # group caption, not a data row
    best = None
    for k, v in COF_SEGMENTS.items():
        if k in n and (best is None or len(k) > len(best[0])):
            best = (k, v)
    return best[1] if best else None


def parse_cof(grid, period, scale):
    """-> list of (period, segment, metric, value, unit)"""
    gi, si, colmap = cof_header(grid)
    if not colmap:
        return []
    mult = SCALE_TO_MM.get(scale, 1.0)
    out, group_ctx = [], ""

    for ri in range(si + 1, len(grid)):
        row = grid[ri]
        label = row[0] if row else ""
        if norm(label).endswith(":"):
            group_ctx = norm(label)
            continue
        seg = cof_segment(label)
        if not seg:
            continue
        # "Domestic" means domestic card only under the Credit Card caption
        if seg == "domestic_card" and "credit card" not in group_ctx:
            continue
        for ci, (metric, unit) in colmap.items():
            v = None
            for probe in (ci, ci + 1, ci + 2):     # skip over "$" cells
                if probe < len(row):
                    v = to_number(row[probe])
                    if v is not None:
                        break
            if v is None:
                continue
            out.append((period, seg, metric,
                        v * mult if unit == "usd" else v, unit))
    return out


# ---------------------------------------------------------- Discover layout

DFS_METRICS = [
    ("ending loans",            "period_end_loans",       "usd"),
    ("average loans",           "average_loans",          "usd"),
    ("net principal charge-off", "net_charge_off_rate",   "pct"),
    ("net charge-off rate",     "net_charge_off_rate",    "pct"),
    ("delinquency rate",        "delinquency_rate_30plus", "pct"),
]


def dfs_metric(label):
    n = norm(label)
    for pat, metric, unit in DFS_METRICS:
        if pat in n:
            return metric, unit
    return None, None


def parse_discover(grid, scale):
    """Transposed layout with stacked 12-month blocks. -> list of tuples."""
    mult = SCALE_TO_MM.get(scale, 1.0)
    out = []
    # Find each (month-row, year-row) pair, then read the metric rows beneath
    # until the next such pair.
    blocks = []
    for ri in range(len(grid) - 1):
        months = {ci: MONTH_ABBR[norm(c)[:3]] for ci, c in enumerate(grid[ri])
                  if norm(c)[:3] in MONTH_ABBR and re.search(r"\d", norm(c))}
        if len(months) < 3:
            continue
        years = {ci: int(norm(c)) for ci, c in enumerate(grid[ri + 1])
                 if re.fullmatch(r"(19|20)\d{2}", norm(c))}
        if len(years) < 3:
            continue
        colper = {}
        for ci, mo in months.items():
            # the year sits in the same column, or very close by
            yr = next((years[cj] for cj in (ci, ci + 1, ci - 1, ci + 2)
                       if cj in years), None)
            if yr:
                colper[ci] = f"{yr}-{mo:02d}"
        if colper:
            blocks.append((ri + 1, colper))

    for bi, (hdr_i, colper) in enumerate(blocks):
        stop = blocks[bi + 1][0] - 1 if bi + 1 < len(blocks) else len(grid)
        for ri in range(hdr_i + 1, stop):
            row = grid[ri]
            metric, unit = dfs_metric(row[0] if row else "")
            if not metric:
                continue
            for ci, per in colper.items():
                v = None
                for probe in (ci, ci + 1, ci + 2):
                    if probe < len(row):
                        v = to_number(row[probe])
                        if v is not None:
                            break
                if v is None:
                    continue
                out.append((per, "discover_domestic_card", metric,
                            v * mult if unit == "usd" else v, unit))
    return out


# ----------------------------------------------------------------- utilities

def period_from_filename(path):
    m = re.search(r"(\d{4})-(\d{2})", os.path.basename(path))
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def filer_from_filename(path):
    b = os.path.basename(path)
    return b.split("-credit-metrics-")[0] if "-credit-metrics-" in b else "unknown"


# ----------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="filings/credit-metrics")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--raw-out", default="credit-metrics-raw.csv")
    ap.add_argument("--tidy-out", default="credit-metrics-tidy.csv")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.htm*")))
    if not files:
        sys.exit(f"No exhibits in {args.dir} -- run download-filings.sh first.")

    if args.dump:
        for path in files:
            grids, doc = extract_tables(path)
            print(f"\n=== {os.path.basename(path)} "
                  f"[{len(grids)} tables, scale={detect_scale(doc)}] ===")
            for gi, g in enumerate(grids):
                print(f"-- table {gi}: {len(g)} rows x {len(g[0])} cols")
                for ri, row in enumerate(g):
                    cells = [(ci, c) for ci, c in enumerate(row) if c.strip()]
                    if cells:
                        print(f"   r{ri}: " +
                              "  ".join(f"[{ci}]{c[:24]}" for ci, c in cells))
        return

    raw_rows, tidy_rows, empty = [], [], []

    for path in files:
        grids, doc = extract_tables(path)
        filer = filer_from_filename(path)
        fileper = period_from_filename(path)
        scale = detect_scale(doc)
        before = len(tidy_rows)

        for gi, g in enumerate(grids):
            for ri, row in enumerate(g):
                for ci, cell in enumerate(row):
                    if cell:
                        raw_rows.append({
                            "filer": filer, "file_period": fileper,
                            "file": os.path.basename(path), "table": gi,
                            "row": ri, "col": ci, "text": cell, "scale": scale})

            facts = (parse_discover(g, scale) if filer == "discover"
                     else parse_cof(g, fileper, scale))
            for per, seg, metric, val, unit in facts:
                tidy_rows.append({
                    "filer": filer, "period": per, "segment": seg,
                    "metric": metric, "value": round(val, 4),
                    "unit": ("usd_mm" if unit == "usd" else "pct"),
                    "source_scale": scale, "file_period": fileper,
                    "file": os.path.basename(path)})

        if len(tidy_rows) == before:
            empty.append((os.path.basename(path), len(grids), scale))

    # Discover's exhibits are rolling 24-month tables, so consecutive filings
    # overlap and report the same month repeatedly. Dedupe on the fact identity,
    # preferring the most recently filed exhibit. Left unhandled this
    # double-counts any month covered by more than one file.
    dedup, conflicts = {}, []
    for r in tidy_rows:
        k = (r["filer"], r["period"], r["segment"], r["metric"])
        prev = dedup.get(k)
        if prev is None:
            dedup[k] = r
            continue
        if abs(prev["value"] - r["value"]) > 0.001:
            conflicts.append((k, prev["value"], r["value"],
                              prev["file"], r["file"]))
        if r["file_period"] > prev["file_period"]:
            dedup[k] = r                       # newest filing wins
    removed = len(tidy_rows) - len(dedup)
    tidy_rows = sorted(dedup.values(),
                       key=lambda r: (r["filer"], r["period"], r["segment"],
                                      r["metric"]))
    if removed:
        print(f"  deduped {removed} overlapping fact(s) across rolling exhibits")
    if conflicts:
        print(f"  !! {len(conflicts)} fact(s) DISAGREE between filings "
              f"(restatement or parse error):")
        for k, a, b, fa, fb in conflicts[:8]:
            print(f"     {k[0]}/{k[1]}/{k[2]}/{k[3]}: {a} ({fa}) vs {b} ({fb})")

    for rows, out, label in ((raw_rows, args.raw_out, "raw cells"),
                             (tidy_rows, args.tidy_out, "tidy facts")):
        if not rows:
            print(f"! no {label} produced"); continue
        with open(out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"{len(rows):6d} {label:12s} -> {out}")

    if empty:
        print(f"\n!! {len(empty)} of {len(files)} file(s) produced NO tidy rows:")
        for name, ntab, sc in empty:
            print(f"   {name}  ({ntab} tables, scale={sc})")
        print("   Run --dump on one and extend the layout maps.")

    if not tidy_rows:
        sys.exit(1)

    # ------------------------------------------------------------- report
    periods = sorted({r["period"] for r in tidy_rows if r["period"]})
    print(f"\nperiods: {len(periods)}  ({periods[0]} .. {periods[-1]})")
    for f in sorted({r["filer"] for r in tidy_rows}):
        ps = sorted({r["period"] for r in tidy_rows if r["filer"] == f})
        segs = sorted({r["segment"] for r in tidy_rows if r["filer"] == f})
        mets = sorted({r["metric"] for r in tidy_rows if r["filer"] == f})
        print(f"  [{f}] {len(ps)} months {ps[0]}..{ps[-1]}")
        print(f"        segments: {', '.join(segs)}")
        print(f"        metrics:  {', '.join(mets)}")

    # gap report
    y0, m0 = map(int, periods[0].split("-"))
    y1, m1 = map(int, periods[-1].split("-"))
    want, y, m = [], y0, m0
    while (y, m) <= (y1, m1):
        want.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    missing = [p for p in want if p not in periods]
    if missing:
        print(f"\nmissing months in range ({len(missing)}): {', '.join(missing)}")

    # additivity: legacy COF + Discover should equal the combined card total in
    # every month where all three are reported. This is the strongest available
    # check that segments haven't been conflated.
    by = defaultdict(dict)
    for r in tidy_rows:
        by[(r["period"], r["metric"])][r["segment"]] = r["value"]
    checked = bad = 0
    for (per, metric), segs in sorted(by.items()):
        need = ("domestic_card_legacy_cof", "discover_domestic_card", "domestic_card")
        if not all(s in segs for s in need):
            continue
        if "rate" in metric:
            continue                       # rates don't add
        checked += 1
        diff = segs[need[0]] + segs[need[1]] - segs[need[2]]
        if abs(diff) > max(1.0, abs(segs[need[2]]) * 0.001):
            bad += 1
            print(f"  !! additivity {per}/{metric}: "
                  f"{segs[need[0]]:,.0f} + {segs[need[1]]:,.0f} != "
                  f"{segs[need[2]]:,.0f}  (off {diff:,.0f})")
    if checked:
        print(f"\nadditivity (legacy COF + Discover = combined card): "
              f"{checked - bad}/{checked} pass")

    # sanity: period-end loans should be in a plausible band once normalised
    pe = [r for r in tidy_rows if r["metric"] == "period_end_loans"]
    if pe:
        lo = min(pe, key=lambda r: r["value"]); hi = max(pe, key=lambda r: r["value"])
        print(f"\nperiod_end_loans range ($mm): "
              f"{lo['value']:,.0f} ({lo['filer']}/{lo['segment']}/{lo['period']})"
              f" .. {hi['value']:,.0f} ({hi['filer']}/{hi['segment']}/{hi['period']})")
        print("   Discover exhibits are in BILLIONS and have been scaled to $mm; "
               "a Discover figure near 100 rather than 100,000 means that failed.")


if __name__ == "__main__":
    main()
