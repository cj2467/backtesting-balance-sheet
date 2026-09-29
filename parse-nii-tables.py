#!/usr/bin/env python3
"""
Parse Capital One's net interest income reconciliation tables out of the
10-K/10-Q HTML. Offline.

    python3 parse-nii-tables.py            # -> nii-segment.csv, nii-avgbal.csv,
                                           #    nii-ratevolume.csv
    python3 parse-nii-tables.py --dump     # inspect what was matched

WHY HTML PARSING AND NOT XBRL: these live in MD&A and the segment note, and the
MD&A ones are NOT XBRL-tagged. Probed six values (average balances, yields,
rate/volume variances) -- zero tagged. Only figures that also appear on the face
of the financial statements carry tags. So the numbers have to come off the
rendered tables.

THREE TABLES, three different jobs:

1. SEGMENT RESULTS AND RECONCILIATION (note 13.1) -- the actual reconciliation.
   Credit Card | Consumer Banking | Commercial Banking | Other | Consolidated
   Segment NII sums to consolidated NII: 9,252 + 2,431 + 585 + 106 = 12,374,
   which matches the consolidated NII on the income statement exactly.

2. AVERAGE BALANCES, NII AND NET INTEREST MARGIN -- decomposition by product.
   Average Balance | Interest Income/Expense | Average Yield/Rate, for the
   current and prior-year period side by side.

3. RATE/VOLUME ANALYSIS -- reconciles the CHANGE in NII.
   Total Variance | Volume | Rate. Year-over-year, not sequential.

PARSING APPROACH: "$" and "%" occupy their own cells in these tables, so column
position is unreliable. Instead the ordered numeric values in a row are mapped
positionally onto the ordered column headers, and any row whose count doesn't
match is rejected rather than guessed at. That count mismatch IS the validation.

Caveats carried into the output: average balances are averages, not period-end,
so they will not tie to the balance sheet; yields are annualised; the
rate/volume table compares against the prior-year period, so it does not chain
across consecutive quarters.
"""
import argparse, csv, glob, html, os, re, sys
from collections import defaultdict
from html.parser import HTMLParser

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


# --------------------------------------------------------------- extraction

class TableExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._st = [], []
        self._row, self._cell, self._cs, self._in = None, None, 1, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._st.append([])
        elif tag == "tr" and self._st:
            self._row = []
        elif tag in ("td", "th") and self._st:
            self._in, self._cell = True, []
            try:
                self._cs = max(1, int(a.get("colspan", 1)))
            except ValueError:
                self._cs = 1
        elif tag == "br" and self._in:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag == "table" and self._st:
            t = self._st.pop()
            if t:
                self.tables.append(t)
        elif tag == "tr" and self._st and self._row is not None:
            self._st[-1].append(self._row); self._row = None
        elif tag in ("td", "th") and self._in:
            txt = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            if self._row is not None:
                self._row.append(txt)
                self._row.extend([""] * (self._cs - 1))
            self._in, self._cell, self._cs = False, None, 1

    def handle_data(self, d):
        if self._in:
            self._cell.append(d)


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
        print(f"  ! {os.path.basename(path)}: {e}", file=sys.stderr)
    out = []
    for t in p.tables:
        w = max((len(r) for r in t), default=0)
        g = [r + [""] * (w - len(r)) for r in t]
        if any(any(c for c in r) for r in g):
            out.append(g)
    return out


# --------------------------------------------------------------- primitives

BLANK = {"", "—", "–", "-", "**", "n/a", "na", "nm", "$", "%"}


def nums_in_row(row):
    """Ordered numeric values in a row, skipping $ / % / footnote-only cells."""
    out = []
    for c in row:
        t = html.unescape(c or "").replace("\xa0", " ").strip()
        if t in BLANK:
            continue
        t = re.sub(r"\(\d\)$", "", t).strip()        # footnote ref like (2)
        neg = t.startswith("(") and t.endswith(")")
        if neg:
            t = t[1:-1].strip()
        t = t.replace(",", "").replace("$", "").replace("%", "").strip()
        if not re.fullmatch(r"-?\d*\.?\d+", t):
            continue
        v = float(t)
        out.append(-v if neg else v)
    return out


def norm(s):
    s = re.sub(r"\(\d+\)", " ", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s).strip()


def label_of(row):
    return norm(row[0]) if row else ""


def caption_of(grid, nrows=3):
    """Caption text from the first few rows. Row 0 is often entirely empty, so
    reading only grid[0] silently yields nothing -- which is exactly what it
    did, producing zero rows from every file."""
    return " ".join(norm(c) for r in grid[:nrows] for c in r if norm(c))


def period_from_caption(cap):
    """'Three Months Ended June 30, 2026' -> ('2026Q2', 3)
       'Year Ended December 31, 2025'     -> ('2025FY', 12)

    The 10-K uses "Year Ended", not "Twelve Months Ended". Handling only the
    latter made both 10-Ks yield zero rows, which removed every Q4."""
    m = re.search(r"year\s+ended\s+\w+\s+\d{1,2},?\s*(\d{4})", cap, re.I)
    if m:
        return f"{int(m.group(1))}FY", 12
    m = re.search(r"(three|six|nine|twelve)\s+months?\s+ended\s+"
                  r"([a-z]+)\s+(\d{1,2}),?\s*(\d{4})", cap, re.I)
    if not m:
        return None, None
    span = {"three": 3, "six": 6, "nine": 9, "twelve": 12}[m.group(1).lower()]
    mo = MONTHS.get(m.group(2).lower())
    yr = int(m.group(4))
    if not mo:
        return None, None
    return f"{yr}Q{(mo - 1) // 3 + 1}", span


def file_year(path):
    m = re.search(r"(?:fy|10q-)(\d{4})", os.path.basename(path))
    return int(m.group(1)) if m else None


# ----------------------------------------------------- 1. segment reconciliation

SEG_ROWS = {
    "net interest income":              "net_interest_income",
    "non-interest income":              "noninterest_income",
    "total net revenue":                "total_net_revenue",
    "provision for credit losses":      "provision",
    "provision (benefit) for credit losses": "provision",
    "non-interest expense":             "noninterest_expense",
    "income tax provision":             "income_tax",
    "loans held for investment":        "loans_hfi",
    "deposits":                         "deposits",
}
SEG_PRETAX = "income (loss) from continuing operations before income taxes"
SEG_AFTERTAX = "income (loss) from continuing operations"


def seg_row_concept(lbl):
    l = lbl.lower().rstrip(":")
    if l.startswith(SEG_PRETAX[:38]):
        return "pretax_income"
    if l.startswith(SEG_AFTERTAX) and "before" not in l:
        return "income_continuing_ops"
    best = None
    for k, v in SEG_ROWS.items():
        if l.startswith(k) and (best is None or len(k) > len(best[0])):
            best = (k, v)
    return best[1] if best else None


def parse_segment(grid, src):
    caption = caption_of(grid)
    period, span = period_from_caption(caption)
    if not period:
        return []
    hdr = None
    for r in grid[:4]:
        if any("consolidated" in norm(c).lower() for c in r):
            hdr = [norm(c) for c in r if norm(c)
                   and "dollars in" not in norm(c).lower()]
            break
    if not hdr:
        return []
    out = []
    for row in grid:
        concept = seg_row_concept(label_of(row))
        if not concept:
            continue
        vals = nums_in_row(row)
        if len(vals) != len(hdr):
            continue                      # count mismatch -> reject, don't guess
        for seg, v in zip(hdr, vals):
            out.append({"period": period, "months": span, "concept": concept,
                        "segment": seg, "value_mm": v, "source": src})
    return out


# ------------------------------------------------- 2. average balance / yield

def parse_avgbal(grid, src, fallback_year):
    """Header: (AvgBal, Interest, Yield) x 2 years -> 6 numeric columns."""
    cap = caption_of(grid, 4)
    _, span = period_from_caption(cap + " 2000")   # span only; year comes below
    if span is None:
        m = re.search(r"(three|six|nine|twelve)\s+months?", cap, re.I)
        if not m:
            return []
        span = {"three": 3, "six": 6, "nine": 9, "twelve": 12}[m.group(1).lower()]
    mo = None
    mm = re.search(r"([a-z]+)\s+\d{1,2},", cap, re.I)
    if mm:
        mo = MONTHS.get(mm.group(1).lower())
    years = []
    for r in grid[:5]:
        ys = [int(norm(c)) for c in r if re.fullmatch(r"(19|20)\d{2}", norm(c))]
        if len(ys) >= 2:
            years = ys; break
    if not years or mo is None:
        return []
    # A 12-month table is the FULL YEAR, not Q4. Labelling it Q4 would make an
    # annual average balance look like a quarterly one.
    quarter = "FY" if span == 12 else f"Q{(mo - 1) // 3 + 1}"
    cols = [(y, f) for y in years for f in ("avg_balance", "interest", "yield_pct")]
    out = []
    for row in grid:
        lbl = label_of(row)
        if not lbl or lbl.lower().startswith("(dollars"):
            continue
        vals = nums_in_row(row)
        if len(vals) != len(cols):
            continue
        for (y, field), v in zip(cols, vals):
            out.append({"period": f"{y}{quarter}", "months": span,
                        "line_item": lbl, "field": field, "value": v,
                        "source": src})
    return out


# ------------------------------------------------------- 3. rate/volume analysis

def parse_ratevolume(grid, src):
    cap = caption_of(grid, 4)
    spans = [{"three": 3, "six": 6, "nine": 9, "twelve": 12}[m.lower()]
             for m in re.findall(r"(Three|Six|Nine|Twelve)\s+Months?", cap, re.I)]
    mo = None
    mm = re.search(r"([a-z]+)\s+\d{1,2},", cap, re.I)
    if mm:
        mo = MONTHS.get(mm.group(1).lower())
    vs = re.findall(r"(\d{4})\s*vs\.?\s*(\d{4})", " ".join(
        c for r in grid[:4] for c in r if c))
    if not spans or not vs or mo is None:
        return []
    cols = []
    for i, span in enumerate(spans):
        cy, py = vs[i] if i < len(vs) else vs[0]
        q = "FY" if span == 12 else f"Q{(mo - 1) // 3 + 1}"
        for f in ("total_variance", "volume", "rate"):
            cols.append((f"{cy}{q}", span, f"{cy} vs {py}", f))
    out = []
    for row in grid:
        lbl = label_of(row)
        if not lbl or lbl.lower().startswith("(dollars"):
            continue
        vals = nums_in_row(row)
        if len(vals) != len(cols):
            continue
        for (per, span, comp, field), v in zip(cols, vals):
            out.append({"period": per, "months": span, "comparison": comp,
                        "line_item": lbl, "field": field, "value_mm": v,
                        "source": src})
    return out


# ------------------------------------------------------------------- driver

def classify(grid):
    flat = " ".join(c.lower() for r in grid for c in r if c)
    if "consolidated total" in flat and "net interest income" in flat \
            and "credit card" in flat and len(grid) <= 20:
        return "segment"
    if "average yield/rate" in flat and "interest-earning" in flat:
        return "avgbal"
    if "total variance" in flat and "volume" in flat and "net interest income" in flat:
        return "ratevolume"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="filings")
    ap.add_argument("--glob", default="capitalone-10*.htm*")
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, args.glob)))
    if not files:
        sys.exit(f"no files matching {args.glob} in {args.dir}/")

    seg, avg, rv = [], [], []
    counts = defaultdict(int)
    for path in files:
        src = os.path.basename(path)
        grids = extract_tables(path)
        per_file = defaultdict(int)
        for g in grids:
            kind = classify(g)
            if not kind:
                continue
            if kind == "segment":
                rows = parse_segment(g, src)
                seg += rows
            elif kind == "avgbal":
                rows = parse_avgbal(g, src, file_year(path))
                avg += rows
            else:
                rows = parse_ratevolume(g, src)
                rv += rows
            counts[kind] += 1
            per_file[kind] += len(rows)
        print(f"  {src:28s} segment={per_file['segment']:4d} "
              f"avgbal={per_file['avgbal']:4d} ratevol={per_file['ratevolume']:4d}")

    if args.dump:
        return

    def write(rows, path, key):
        if not rows:
            print(f"! nothing for {path}"); return
        # dedupe: the same period appears in consecutive filings
        best = {}
        for r in rows:
            best[tuple(r[k] for k in key)] = r
        rows = [best[k] for k in sorted(best)]
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"{len(rows):6d} rows -> {path}")
        return rows

    # Q4 segment figures are not reported: the 10-K segment table is annual and
    # the 10-Q ones are 3M/6M/9M. Derive Q4 = FY - 9M, same approach (and same
    # caveat) as the income statement.
    idx = {(r["period"], r["months"], r["concept"], r["segment"]): r["value_mm"]
           for r in seg}
    derived_rows = []
    for (per, mo, concept, segment), val in list(idx.items()):
        if mo != 12 or not per.endswith("FY"):
            continue
        yr = per[:4]
        nine = idx.get((f"{yr}Q3", 9, concept, segment))
        if nine is None:
            continue
        if (f"{yr}Q4", 3, concept, segment) in idx:
            continue
        derived_rows.append({"period": f"{yr}Q4", "months": 3,
                             "concept": concept, "segment": segment,
                             "value_mm": round(val - nine, 1),
                             "source": "derived Q4=FY-9M"})
    seg += derived_rows
    print(f"\n  derived {len(derived_rows)} Q4 segment figures (FY - 9M)")

    seg = write(seg, "nii-segment.csv",
                ("period", "months", "concept", "segment")) or []
    avg = write(avg, "nii-avgbal.csv",
                ("period", "months", "line_item", "field")) or []
    rv = write(rv, "nii-ratevolume.csv",
               ("period", "months", "line_item", "field")) or []

    # ---- validation: segment NII must sum to the consolidated column
    print("\nsegment NII reconciliation (sum of segments vs consolidated):")
    by = defaultdict(dict)
    for r in seg:
        if r["concept"] == "net_interest_income" and r["months"] == 3:
            by[r["period"]][r["segment"]] = r["value_mm"]
    okn = badn = 0
    for per in sorted(by):
        segs = by[per]
        cons = next((v for k, v in segs.items() if "consolidated" in k.lower()), None)
        parts = {k: v for k, v in segs.items() if "consolidated" not in k.lower()}
        if cons is None or not parts:
            continue
        diff = sum(parts.values()) - cons
        ok = abs(diff) < 1.0
        okn, badn = okn + ok, badn + (not ok)
        print(f"   {per}  {'ok' if ok else 'MISMATCH':9s} "
              f"sum {sum(parts.values()):>10,.0f}  consolidated {cons:>10,.0f}"
              f"  diff {diff:>7,.0f}")
    print(f"   {okn}/{okn + badn} periods reconcile")

    if seg:
        print(f"\nsegment periods: "
              f"{sorted({r['period'] for r in seg if r['months'] == 3})}")
    if avg:
        print(f"avgbal periods:  {sorted({r['period'] for r in avg})}")
    if rv:
        print(f"ratevol periods: {sorted({r['period'] for r in rv})}")


if __name__ == "__main__":
    main()
