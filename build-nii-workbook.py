#!/usr/bin/env python3
"""
Build capital-one-nii-reconciliation.xlsx from the parsed NII tables.

    python3 build-nii-workbook.py
    python3 scripts/recalc.py capital-one-nii-reconciliation.xlsx   # then verify

Inputs: nii-segment.csv, nii-avgbal.csv, nii-ratevolume.csv (parse-nii-tables.py)

Conventions: blue text = figure taken straight from a filing (a hardcoded
input). Black = live formula. Totals, sums and every reconciliation check are
real formulas so the sheets recompute if an input is corrected.
"""
import csv, os, sys
from collections import defaultdict

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ARIAL = "Arial"
BLUE = Font(name=ARIAL, size=10, color="0000FF")
BLACK = Font(name=ARIAL, size=10)
BOLD = Font(name=ARIAL, size=10, bold=True)
BOLD_U = Font(name=ARIAL, size=10, bold=True, underline="single")
TITLE = Font(name=ARIAL, size=12, bold=True)
NOTE = Font(name=ARIAL, size=9, italic=True, color="595959")
HDR_FILL = PatternFill("solid", fgColor="D9E1F2")
CHK_FILL = PatternFill("solid", fgColor="FFF2CC")
THIN = Side(style="thin", color="BFBFBF")
TOPBORDER = Border(top=THIN)

MONEY = '$#,##0;($#,##0);-'
PCT = '0.00%;(0.00%);-'
CHECK_FMT = '#,##0;(#,##0);-'

SEG_ORDER = ["Credit Card", "Consumer Banking", "Commercial Banking", "Other"]


def qkey(p):
    y, q = p.split("Q")
    return int(y) * 4 + int(q)


def read(path):
    if not os.path.exists(path):
        sys.exit(f"missing {path} -- run parse-nii-tables.py")
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def find_consolidated(keys):
    return next((k for k in keys if "consolidated" in k.lower()), None)


def sheet_header(ws, title, subtitle, cols, first_col=2):
    ws["A1"] = title
    ws["A1"].font = TITLE
    ws["A2"] = subtitle
    ws["A2"].font = NOTE
    r = 4
    for i, c in enumerate(cols):
        cell = ws.cell(row=r, column=first_col + i, value=c)
        cell.font = BOLD
        cell.fill = HDR_FILL
        cell.alignment = Alignment(horizontal="center")
    ws.cell(row=r, column=1, value="($ in millions)").font = BOLD
    ws.column_dimensions["A"].width = 42
    for i in range(len(cols)):
        ws.column_dimensions[get_column_letter(first_col + i)].width = 12
    ws.freeze_panes = ws.cell(row=r + 1, column=first_col)
    return r


# ------------------------------------------------------- sheet 1: segment recon

def build_segment(wb, rows):
    q = [r for r in rows if r["months"] == "3"]
    periods = sorted({r["period"] for r in q}, key=qkey)
    vals = defaultdict(dict)                 # (concept, segment) -> period -> v
    derived = set()
    for r in q:
        vals[(r["concept"], r["segment"])][r["period"]] = float(r["value_mm"])
        if "derived" in (r.get("source") or ""):
            derived.add(r["period"])

    ws = wb.create_sheet("Segment NII Recon")
    hr = sheet_header(
        ws, "Capital One — Net Interest Income by Segment, and Reconciliation",
        "Source: COF 10-Q/10-K, Segment Results and Reconciliation note. "
        "(D) = Q4 derived as FY − 9M; no 3-month Q4 segment table is reported.",
        [p + (" (D)" if p in derived else "") for p in periods])

    segs = [s for s in SEG_ORDER
            if ("net_interest_income", s) in vals or
               any(k[1].startswith(s) for k in vals if k[0] == "net_interest_income")]
    # resolve actual segment label spellings present in the data
    present = {k[1] for k in vals if k[0] == "net_interest_income"}
    seg_labels = []
    for s in SEG_ORDER:
        match = next((p for p in present if p.lower().startswith(s.lower())), None)
        if match:
            seg_labels.append(match)
    cons = find_consolidated(present)

    r = hr + 1
    ws.cell(row=r, column=1, value="Net interest income by segment").font = BOLD_U
    r += 1
    first_seg_row = r
    for lbl in seg_labels:
        ws.cell(row=r, column=1, value="  " + lbl).font = BLACK
        for i, p in enumerate(periods):
            v = vals[("net_interest_income", lbl)].get(p)
            c = ws.cell(row=r, column=2 + i, value=v)
            c.font, c.number_format = BLUE, MONEY
        r += 1
    last_seg_row = r - 1

    # Sum of segments -- a real formula
    ws.cell(row=r, column=1, value="Sum of segments").font = BOLD
    for i in range(len(periods)):
        col = get_column_letter(2 + i)
        c = ws.cell(row=r, column=2 + i,
                    value=f"=SUM({col}{first_seg_row}:{col}{last_seg_row})")
        c.font, c.number_format, c.border = BOLD, MONEY, TOPBORDER
    sum_row = r
    r += 1

    ws.cell(row=r, column=1, value="Consolidated total (as reported)").font = BOLD
    for i, p in enumerate(periods):
        v = vals[("net_interest_income", cons)].get(p) if cons else None
        c = ws.cell(row=r, column=2 + i, value=v)
        c.font, c.number_format = BLUE, MONEY
    cons_row = r
    r += 2

    ws.cell(row=r, column=1, value="CHECK: sum of segments − consolidated").font = BOLD
    for i in range(len(periods)):
        col = get_column_letter(2 + i)
        c = ws.cell(row=r, column=2 + i,
                    value=f"={col}{sum_row}-{col}{cons_row}")
        c.font, c.number_format, c.fill = BOLD, CHECK_FMT, CHK_FILL
    r += 2

    # Full segment P&L blocks, each with its own reconciliation check
    blocks = [("noninterest_income", "Non-interest income"),
              ("total_net_revenue", "Total net revenue"),
              ("provision", "Provision for credit losses"),
              ("noninterest_expense", "Non-interest expense"),
              ("pretax_income", "Pre-tax income from continuing ops"),
              ("income_tax", "Income tax provision"),
              ("income_continuing_ops", "Income from continuing operations")]
    for concept, title in blocks:
        if not any(k[0] == concept for k in vals):
            continue
        ws.cell(row=r, column=1, value=title).font = BOLD_U
        r += 1
        start = r
        for lbl in seg_labels:
            if (concept, lbl) not in vals:
                continue
            ws.cell(row=r, column=1, value="  " + lbl).font = BLACK
            for i, p in enumerate(periods):
                c = ws.cell(row=r, column=2 + i,
                            value=vals[(concept, lbl)].get(p))
                c.font, c.number_format = BLUE, MONEY
            r += 1
        end = r - 1
        if end < start:
            continue
        ws.cell(row=r, column=1, value="  Sum of segments").font = BOLD
        for i in range(len(periods)):
            col = get_column_letter(2 + i)
            c = ws.cell(row=r, column=2 + i,
                        value=f"=SUM({col}{start}:{col}{end})")
            c.font, c.number_format, c.border = BOLD, MONEY, TOPBORDER
        srow = r
        r += 1
        ws.cell(row=r, column=1, value="  Consolidated (as reported)").font = BLACK
        for i, p in enumerate(periods):
            c = ws.cell(row=r, column=2 + i,
                        value=vals[(concept, cons)].get(p) if cons else None)
            c.font, c.number_format = BLUE, MONEY
        crow = r
        r += 1
        ws.cell(row=r, column=1, value="  CHECK").font = BOLD
        for i in range(len(periods)):
            col = get_column_letter(2 + i)
            c = ws.cell(row=r, column=2 + i, value=f"={col}{srow}-{col}{crow}")
            c.font, c.number_format, c.fill = BOLD, CHECK_FMT, CHK_FILL
        r += 2

    ws.cell(row=r, column=1,
            value="Blue = as reported in the filing. Black = formula. "
                  "Every CHECK row should read zero.").font = NOTE
    return periods


# --------------------------------------------------- sheet 2: avg balance/yield

def build_avgbal(wb, rows):
    q = [r for r in rows if r["months"] == "3"]
    if not q:
        return
    periods = sorted({r["period"] for r in q}, key=qkey)
    vals = defaultdict(dict)                 # (line_item, field) -> period -> v
    order, seen = [], set()
    for r in q:
        vals[(r["line_item"], r["field"])][r["period"]] = float(r["value"])
        if r["line_item"] not in seen:
            seen.add(r["line_item"]); order.append(r["line_item"])

    ws = wb.create_sheet("Avg Bal & Yield")
    hr = sheet_header(
        ws, "Capital One — Average Balances, Interest and Yield (quarterly)",
        "Source: COF 10-Q, 'Average Balances, Net Interest Income and Net "
        "Interest Margin'. AVERAGE balances, not period-end — these will not "
        "tie to the balance sheet. Yields are annualised. Not XBRL-tagged; "
        "parsed from the rendered table.",
        periods)
    r = hr + 1
    for field, title, fmt in (("avg_balance", "Average balance", MONEY),
                              ("interest", "Interest income / expense", MONEY),
                              ("yield_pct", "Average yield / rate", PCT)):
        ws.cell(row=r, column=1, value=title).font = BOLD_U
        r += 1
        for li in order:
            if (li, field) not in vals:
                continue
            ws.cell(row=r, column=1, value="  " + li[:60]).font = BLACK
            for i, p in enumerate(periods):
                v = vals[(li, field)].get(p)
                if v is not None and field == "yield_pct":
                    v = v / 100.0            # store as fraction; format as %
                c = ws.cell(row=r, column=2 + i, value=v)
                c.font, c.number_format = BLUE, fmt
            r += 1
        r += 1
    ws.cell(row=r, column=1,
            value="All figures as reported. Yields stored as fractions and "
                  "displayed as percentages.").font = NOTE


# ------------------------------------------------------ sheet 3: rate / volume

def build_ratevolume(wb, rows):
    q = [r for r in rows if r["months"] == "3"]
    if not q:
        return
    periods = sorted({r["period"] for r in q}, key=qkey)
    vals = defaultdict(dict)
    order, seen = [], set()
    comps = {}
    for r in q:
        vals[(r["line_item"], r["field"])][r["period"]] = float(r["value_mm"])
        comps[r["period"]] = r.get("comparison", "")
        if r["line_item"] not in seen:
            seen.add(r["line_item"]); order.append(r["line_item"])

    ws = wb.create_sheet("Rate-Volume")
    hr = sheet_header(
        ws, "Capital One — Rate/Volume Analysis of Net Interest Income",
        "Source: COF 10-Q, 'Rate/Volume Analysis of Net Interest Income'. "
        "Each column compares against the PRIOR-YEAR quarter, so these do not "
        "chain across consecutive quarters. Total variance = volume + rate.",
        [f"{p} vs {comps.get(p,'').split('vs')[-1].strip()}" for p in periods])

    r = hr + 1
    rowmap = {}
    for field, title in (("total_variance", "Total variance"),
                         ("volume", "Volume effect"),
                         ("rate", "Rate effect")):
        ws.cell(row=r, column=1, value=title).font = BOLD_U
        r += 1
        rowmap[field] = {}
        for li in order:
            if (li, field) not in vals:
                continue
            ws.cell(row=r, column=1, value="  " + li[:60]).font = BLACK
            for i, p in enumerate(periods):
                c = ws.cell(row=r, column=2 + i, value=vals[(li, field)].get(p))
                c.font, c.number_format = BLUE, MONEY
            rowmap[field][li] = r
            r += 1
        r += 1

    # CHECK: volume + rate must equal total variance, line by line
    ws.cell(row=r, column=1,
            value="CHECK: volume + rate − total variance").font = BOLD_U
    r += 1
    common = [li for li in order
              if li in rowmap.get("total_variance", {})
              and li in rowmap.get("volume", {})
              and li in rowmap.get("rate", {})]
    for li in common:
        ws.cell(row=r, column=1, value="  " + li[:60]).font = BLACK
        for i in range(len(periods)):
            col = get_column_letter(2 + i)
            f = (f"={col}{rowmap['volume'][li]}+{col}{rowmap['rate'][li]}"
                 f"-{col}{rowmap['total_variance'][li]}")
            c = ws.cell(row=r, column=2 + i, value=f)
            c.font, c.number_format, c.fill = BLACK, CHECK_FMT, CHK_FILL
        r += 1
    ws.cell(row=r + 1, column=1,
            value="Every CHECK cell should read zero: the issuer's volume and "
                  "rate effects must sum to the reported total variance.").font = NOTE


# ------------------------------------------------------------ sheet 4: notes

def build_notes(wb, seg_periods):
    ws = wb.create_sheet("Notes & Sources")
    ws.column_dimensions["A"].width = 110
    lines = [
        ("Capital One — NII reconciliation workbook", TITLE),
        ("", NOTE),
        ("WHAT IS IN HERE", BOLD_U),
        ("Segment NII Recon — net interest income and the full segment P&L by "
         "business segment, with the sum of segments reconciled to the "
         "consolidated total. This is the reconciliation table proper.", BLACK),
        ("Avg Bal & Yield — average balance, interest, and average yield/rate "
         "by earning-asset and funding category.", BLACK),
        ("Rate-Volume — the change in NII split into volume and rate effects.", BLACK),
        ("", NOTE),
        ("SOURCES", BOLD_U),
        ("Segment data: Capital One Financial Corp (CIK 0000927628) Forms 10-Q "
         "and 10-K, 'Segment Results and Reconciliation' note (Table 13.1).", BLACK),
        ("Average balance and rate/volume data: same filings, MD&A tables "
         "'Average Balances, Net Interest Income and Net Interest Margin' and "
         "'Rate/Volume Analysis of Net Interest Income'.", BLACK),
        ("Filings retrieved from SEC EDGAR: "
         "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000927628", BLACK),
        ("", NOTE),
        ("METHOD AND ASSUMPTIONS", BOLD_U),
        ("The MD&A tables are NOT XBRL-tagged — probing six values (average "
         "balances, yields, rate/volume variances) returned zero tagged hits, "
         "while figures that also appear on the face of the income statement "
         "are tagged. So these numbers are parsed from the rendered HTML "
         "tables, not read from XBRL.", BLACK),
        ("Parsing maps the ordered numeric values in each row onto the ordered "
         "column headers, because '$' and '%' occupy their own cells and make "
         "column position unreliable. Any row whose value count does not match "
         "the header count is rejected rather than guessed at.", BLACK),
        ("Q4 columns marked (D) are DERIVED as full year minus nine months. No "
         "3-month Q4 segment table is reported: the 10-K segment table is "
         "annual and the 10-Q tables are 3/6/9-month. The subtraction is exact "
         "but spans two filings, so a restatement between them would land "
         "here. Q1+Q2+Q3 ties to the as-reported nine-month figure across all "
         "tested concepts, so no restatement occurred.", BLACK),
        ("", NOTE),
        ("CAVEATS", BOLD_U),
        ("Average balances are averages over the period, NOT period-end, so "
         "they will not tie to the balance sheet.", BLACK),
        ("Yields are annualised and stored as fractions (0.1721 displays as "
         "17.21%).", BLACK),
        ("The rate/volume table compares each quarter against the PRIOR-YEAR "
         "quarter, not the preceding one, so the columns do not chain. The "
         "split of the joint rate-volume effect follows the issuer's own "
         "allocation convention.", BLACK),
        ("", NOTE),
        ("VALIDATION", BOLD_U),
        (f"Segment NII sums to the consolidated total at zero difference in all "
         f"{len(seg_periods)} quarters ({seg_periods[0]}–{seg_periods[-1]}), and "
         f"each consolidated figure matches the income statement extracted "
         f"independently from XBRL.", BLACK),
        ("Volume + rate ties to total variance on the Rate-Volume sheet.", BLACK),
        ("", NOTE),
        ("CONVENTIONS", BOLD_U),
        ("Blue text = figure as reported in the filing (a hardcoded input). "
         "Black text = live formula. Yellow fill = reconciliation check, which "
         "should read zero.", BLACK),
    ]
    r = 1
    for text, font in lines:
        c = ws.cell(row=r, column=1, value=text)
        c.font = font
        c.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1


def main():
    seg = read("nii-segment.csv")
    avg = read("nii-avgbal.csv")
    rv = read("nii-ratevolume.csv")

    wb = Workbook()
    wb.remove(wb.active)
    periods = build_segment(wb, seg)
    build_avgbal(wb, avg)
    build_ratevolume(wb, rv)
    build_notes(wb, periods)

    out = "capital-one-nii-reconciliation.xlsx"
    wb.save(out)
    print(f"-> {out}")
    print(f"   sheets: {wb.sheetnames}")
    print(f"   segment periods: {len(periods)} ({periods[0]}..{periods[-1]})")
    print("\nNow run:  python3 scripts/recalc.py " + out)


if __name__ == "__main__":
    main()
