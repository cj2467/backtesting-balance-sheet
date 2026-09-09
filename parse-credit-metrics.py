#!/usr/bin/env python3
"""
Turn the downloaded monthly credit-metrics exhibits into CSV.

    python3 parse-credit-metrics.py --dump      # LOOK AT THIS FIRST
    python3 parse-credit-metrics.py             # writes credit-metrics-*.csv

Reads filings/credit-metrics/*.htm (from download-filings.sh).

Two outputs, deliberately:

  credit-metrics-raw.csv    every table cell, as-is, with coordinates.
  credit-metrics-tidy.csv   best-effort (period, segment, metric, value).

The raw dump exists because this parser was written WITHOUT a sample of the
actual exhibit HTML in hand. The extractor mechanics (colspan, entities,
number formats) are tested; the *tidy* layer guesses at layout and is the
part likely to need adjustment. Run --dump, compare against the filing, and
fix SEGMENTS/METRICS below if the mapping is off. If the tidy layer is wrong,
the raw CSV still has everything.

Caveat worth knowing: parenthesised numbers are read as negative. SEC exhibits
also use "(1)" as footnote markers, so a lone parenthesised single digit may be
a footnote rather than a value of -1. Those are flagged in the `note` column.

No third-party dependencies.
"""
import argparse, csv, glob, html, os, re, sys
from html.parser import HTMLParser

# ----------------------------------------------------------------- extraction

class TableExtractor(HTMLParser):
    """Pull tables out as rectangular grids of text, honouring colspan."""

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
                # colspan: pad so column indices stay aligned
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


# ----------------------------------------------------------------- normalising

DASHES = {"—", "–", "-", "—", "–", "n/a", "na", "nm", ""}

def parse_number(s):
    """-> (value, unit, note). unit is 'pct' | 'usd' | None."""
    if s is None:
        return None, None, ""
    t = html.unescape(s).replace("\xa0", " ").strip()
    if t.lower() in DASHES:
        return None, None, ""

    note = ""
    neg = False
    if t.startswith("(") and t.endswith(")"):
        inner = t[1:-1].strip()
        if re.fullmatch(r"\d", inner):
            note = "possible footnote marker, not a value"
        neg, t = True, inner

    pct = t.endswith("%")
    t = t.rstrip("%").replace("$", "").replace(",", "").strip()
    if not re.fullmatch(r"-?\d*\.?\d+", t):
        return None, None, ""

    v = float(t)
    if neg:
        v = -v
    return v, ("pct" if pct else "usd"), note


def detect_scale(doc_text):
    low = doc_text.lower()
    if "in millions" in low:
        return "millions"
    if "in thousands" in low:
        return "thousands"
    if "in billions" in low:
        return "billions"
    return "unknown"


# Row labels -> canonical segment. Longest match wins, so order doesn't matter.
SEGMENTS = {
    "discover domestic":        "discover_domestic_card",
    "domestic card":           "domestic_card",
    "domestic credit card":    "domestic_card",
    "international card":      "international_card",
    "credit card":             "credit_card_total",
    "auto":                    "auto",
    "consumer banking":        "consumer_banking",
    "commercial banking":      "commercial_banking",
    "total company":           "total_company",
    "total":                   "total",
}

# Column headers -> canonical metric.
METRICS = {
    "period-end loans":          "period_end_loans",
    "period end loans":          "period_end_loans",
    "average loans":             "average_loans",
    "net charge-offs":           "net_charge_offs",
    "net charge offs":           "net_charge_offs",
    "net charge-off rate":       "net_charge_off_rate",
    "net principal charge-off":  "net_charge_off_rate",
    "30+ day performing":        "delinquencies_30plus",
    "30+ day delinquency":       "delinquency_rate_30plus",
    "30+ day":                   "delinquencies_30plus",
    "nonperforming":             "nonperforming",
}


def canon(label, mapping):
    l = re.sub(r"\s+", " ", html.unescape(label or "")).strip().lower()
    l = re.sub(r"\(\d+\)", "", l).strip()          # drop footnote refs
    if not l:
        return None
    best = None
    for k, v in mapping.items():
        if k in l and (best is None or len(k) > len(best[0])):
            best = (k, v)
    return best[1] if best else None


MONTH_NAMES = {m.lower(): i for i, m in enumerate(
    ["January","February","March","April","May","June",
     "July","August","September","October","November","December"], start=1)}
MONTH_ABBR = {m[:3].lower(): i for m, i in
              [(k.capitalize(), v) for k, v in MONTH_NAMES.items()]}

def parse_row_month(label):
    """Discover's exhibit is a rolling 24-month table -- rows are months, not
    segments. Recognise those so one file yields many periods.

    'October 31, 2023' / 'Oct-23' / '10/31/2023' -> '2023-10'
    """
    if not label:
        return None
    l = re.sub(r"\s+", " ", html.unescape(label)).strip().lower().strip("*: ")

    # "October 31, 2023" / "October 2023" / "Oct. 31, 2023"
    m = re.search(r"\b([a-z]{3,9})\b\.?,?\s*(?:\d{1,2}\s*(?:st|nd|rd|th)?\s*,?\s*)?(\d{4})\b", l)
    if m and m.group(1)[:3] in MONTH_ABBR:
        return f"{int(m.group(2))}-{MONTH_ABBR[m.group(1)[:3]]:02d}"

    # "Oct-23" / "Oct 23" / "Oct/23"  (2-digit year, at end of label)
    m = re.search(r"\b([a-z]{3,9})\b[\s.\-/]+(\d{2})$", l)
    if m and m.group(1)[:3] in MONTH_ABBR:
        return f"{2000 + int(m.group(2))}-{MONTH_ABBR[m.group(1)[:3]]:02d}"

    # "10/31/2023" / "10-31-23"
    m = re.fullmatch(r"(\d{1,2})[/-]\d{1,2}[/-](\d{2,4})", l)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        y += 2000 if y < 100 else 0
        if 1 <= mo <= 12:
            return f"{y}-{mo:02d}"
    return None


# When a row is a month rather than a segment, we still need to know which
# portfolio it describes. Keyed by filer.
DEFAULT_SEGMENT = {"discover": "discover_domestic_card", "cof": "domestic_card"}


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
    ap.add_argument("--dump", action="store_true",
                    help="print table structure and exit (do this first)")
    ap.add_argument("--raw-out", default="credit-metrics-raw.csv")
    ap.add_argument("--tidy-out", default="credit-metrics-tidy.csv")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "*.htm*")))
    if not files:
        sys.exit(f"No exhibits in {args.dir} -- run download-filings.sh first.")

    if args.dump:
        for path in files:
            grids, doc = extract_tables(path)
            print(f"\n=== {os.path.basename(path)}  "
                  f"[{len(grids)} tables, scale={detect_scale(doc)}] ===")
            for gi, g in enumerate(grids):
                print(f"\n-- table {gi}: {len(g)} rows x {len(g[0])} cols")
                for r in g[:14]:
                    cells = [c[:20] for c in r[:9]]
                    print("   | " + " | ".join(f"{c:20s}" for c in cells))
                if len(g) > 14:
                    print(f"   ... {len(g)-14} more rows")
        return

    raw_rows, tidy_rows = [], []

    silent_failures = []

    for path in files:
        before = len(tidy_rows)
        grids, doc = extract_tables(path)
        period, filer, scale = (period_from_filename(path),
                                filer_from_filename(path), detect_scale(doc))
        if not period:
            print(f"   ! no period in filename: {os.path.basename(path)}", file=sys.stderr)

        for gi, g in enumerate(grids):
            for ri, row in enumerate(g):
                for ci, cell in enumerate(row):
                    if cell:
                        raw_rows.append({
                            "filer": filer, "period": period, "file": os.path.basename(path),
                            "table": gi, "row": ri, "col": ci, "text": cell, "scale": scale})

            # --- tidy layer: find a header row, then read labelled data rows.
            header_i, header_map = None, {}
            for ri, row in enumerate(g[:6]):
                cand = {ci: canon(c, METRICS) for ci, c in enumerate(row)}
                cand = {ci: m for ci, m in cand.items() if m}
                if len(cand) >= 2:
                    header_i, header_map = ri, cand
                    break
            if header_i is None:
                continue

            for ri in range(header_i + 1, len(g)):
                row = g[ri]
                label = row[0] if row else ""

                # Two shapes in the wild: rows-are-segments (Capital One) and
                # rows-are-months (Discover's rolling 24-month table).
                seg = canon(label, SEGMENTS)
                row_period = None
                if seg:
                    row_period = period
                else:
                    row_period = parse_row_month(label)
                    if row_period:
                        seg = DEFAULT_SEGMENT.get(filer, "unknown")
                if not seg or not row_period:
                    continue

                for ci, metric in header_map.items():
                    if ci >= len(row):
                        continue
                    val, unit, note = parse_number(row[ci])
                    if val is None:
                        continue
                    tidy_rows.append({
                        "filer": filer, "period": row_period, "segment": seg,
                        "metric": metric, "value": val,
                        "unit": unit, "scale": scale if unit == "usd" else "",
                        "row_shape": "month" if label and parse_row_month(label) else "segment",
                        "file_period": period,
                        "table": gi, "row": ri, "col": ci,
                        "source_label": label[:60], "note": note,
                        "file": os.path.basename(path)})

        if len(tidy_rows) == before:
            silent_failures.append((os.path.basename(path), len(grids)))

    if silent_failures:
        print(f"\n!! {len(silent_failures)} file(s) produced NO tidy rows "
              f"(out of {len(files)}). These are in the raw CSV but the tidy "
              f"layer did not understand their layout:")
        for name, ntab in silent_failures:
            print(f"   {name}  ({ntab} tables found)")
        print("   Run --dump on one of these and extend SEGMENTS/METRICS.\n")

    for rows, out, label in ((raw_rows, args.raw_out, "raw cells"),
                             (tidy_rows, args.tidy_out, "tidy facts")):
        if not rows:
            print(f"! no {label} produced"); continue
        with open(out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"{len(rows):6d} {label:12s} -> {out}")

    if tidy_rows:
        periods = sorted({r["period"] for r in tidy_rows if r["period"]})
        print(f"\nperiods: {len(periods)}  ({periods[0]} .. {periods[-1]})")
        segs = sorted({r["segment"] for r in tidy_rows})
        mets = sorted({r["metric"] for r in tidy_rows})
        print(f"segments: {', '.join(segs)}")
        print(f"metrics:  {', '.join(mets)}")
        flagged = [r for r in tidy_rows if r["note"]]
        if flagged:
            print(f"\n{len(flagged)} cells flagged (check these against the filing):")
            for r in flagged[:10]:
                print(f"   {r['period']} {r['segment']}/{r['metric']} = {r['value']} -- {r['note']}")
        # Rate-only rolling tables legitimately carry ~2 facts/month, so only
        # flag segment-shaped periods as thin. A warning that fires on healthy
        # data is a warning people learn to ignore.
        thin = []
        for p in periods:
            facts = [r for r in tidy_rows if r["period"] == p]
            floor = 2 if all(r["row_shape"] == "month" for r in facts) else 4
            if len(facts) < floor:
                thin.append(p)
        if thin:
            print(f"\nthin periods -- likely a layout the tidy layer missed: "
                  f"{', '.join(thin)}")
        print("\nIf segments/metrics look wrong or sparse, run --dump and fix "
              "SEGMENTS/METRICS. credit-metrics-raw.csv has every cell regardless.")


if __name__ == "__main__":
    main()
