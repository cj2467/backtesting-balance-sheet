#!/usr/bin/env python3
"""
Quarterly net interest income table from flows.csv -- quarters as columns.

    python3 make-nii-table.py                          # $mm
    python3 make-nii-table.py --since 2024Q4 --units bn
    python3 make-nii-table.py --annual                  # 12-month columns

Companion to make-balance-sheet.py. Same conventions: reported subtotals are
taken from the filing rather than summed, residuals are shown explicitly, and
the bottom row is an arithmetic check that should be zero.

Columns marked (D) are derived: Q4 = FY - 9M, because issuers never report a
3-month Q4. The subtraction is exact, but it spans two filings, so a
restatement between them would land here.
"""
import argparse, csv, os, sys
from collections import defaultdict

LAYOUT = [
    ("INTEREST INCOME", None, "header"),
    ("  Loans and leases",              "int_inc_loans",      "line"),
    ("  Investment securities",         "int_inc_securities", "line"),
    ("  Other",                         "int_inc_other",      "line"),
    ("  Unallocated",                   "__resid_ii__",       "residual"),
    ("TOTAL INTEREST INCOME",           "int_inc_total",      "reported"),

    ("INTEREST EXPENSE", None, "header"),
    ("  Deposits",                      "int_exp_deposits",   "line"),
    ("  Securitized debt",              "int_exp_secured",    "line"),
    ("  Senior and subordinated notes", "int_exp_unsecured",  "line"),
    ("  Other borrowings",              "int_exp_other",      "line"),
    ("  Unallocated",                   "__resid_ie__",       "residual"),
    ("TOTAL INTEREST EXPENSE",          "int_exp_total",      "reported"),

    ("", None, "header"),
    ("NET INTEREST INCOME",             "net_interest_income", "reported"),
    ("  NII after provision",           "nii_after_provision", "memo"),
    ("  Implied provision for credit losses", "__provision__", "derived_line"),

    ("MEMO", None, "header"),
    ("  Non-interest income",           "noninterest_income",  "memo"),
    ("  Non-interest expense",          "noninterest_expense", "memo"),
    ("  Pre-tax income",                "pretax_income",       "memo"),
    ("  Net income",                    "net_income",          "memo"),

    ("CHECK", None, "header"),
    ("NET: (int income - int expense) - reported NII", "__check__", "net"),
]

II_LINES = ["int_inc_loans", "int_inc_securities", "int_inc_other"]
IE_LINES = ["int_exp_deposits", "int_exp_secured", "int_exp_unsecured",
            "int_exp_other"]


def qkey(q):
    y, n = q.split("Q")
    return int(y) * 4 + int(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default="flows.csv")
    ap.add_argument("--filer", default="cof")
    ap.add_argument("--units", choices=["mm", "bn"], default="mm")
    ap.add_argument("--since", default=None, help="earliest quarter, e.g. 2024Q4")
    ap.add_argument("--annual", action="store_true",
                    help="use 12-month periods instead of quarters")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.flows):
        sys.exit(f"missing {args.flows} -- run extract-local-flows.py")

    div = 1e6 if args.units == "mm" else 1e9
    unit = "$mm" if args.units == "mm" else "$bn"
    months = 12 if args.annual else 3

    vals, derived_cols = defaultdict(dict), set()
    with open(args.flows, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["filer"] != args.filer or int(r["months"]) != months:
                continue
            col = r["quarter"] if months == 3 else r["period_end"][:4]
            if not col:
                continue
            try:
                vals[col][r["concept"]] = float(r["value_usd"])
            except (TypeError, ValueError):
                continue
            if r.get("derived"):
                derived_cols.add(col)

    cols = sorted(vals, key=qkey if months == 3 else str)
    if args.since:
        cols = [c for c in cols
                if (qkey(c) >= qkey(args.since) if months == 3
                    else c >= args.since)]
    if not cols:
        sys.exit("no periods to show")

    # derived lines
    for c in cols:
        v = vals[c]
        if "int_inc_total" in v:
            v["__resid_ii__"] = v["int_inc_total"] - sum(
                v.get(k, 0.0) for k in II_LINES)
        if "int_exp_total" in v:
            v["__resid_ie__"] = v["int_exp_total"] - sum(
                v.get(k, 0.0) for k in IE_LINES)
        if "net_interest_income" in v and "nii_after_provision" in v:
            v["__provision__"] = v["net_interest_income"] - v["nii_after_provision"]
        if all(k in v for k in ("int_inc_total", "int_exp_total",
                                "net_interest_income")):
            v["__check__"] = (v["int_inc_total"] - v["int_exp_total"]
                              - v["net_interest_income"])

    w_lab, w_col = 46, 13
    label_row = "".join(f"{c + (' (D)' if c in derived_cols else ''):>{w_col}}"
                        for c in cols)
    title = (f"{args.filer.upper()} -- "
             f"{'annual' if args.annual else 'quarterly'} net interest income "
             f"({unit})")
    print("\n" + title)
    print("=" * (w_lab + w_col * len(cols)))
    print(" " * w_lab + label_row)
    print("-" * (w_lab + w_col * len(cols)))

    out_rows = []
    for label, concept, kind in LAYOUT:
        if kind == "header":
            print()
            if label:
                print(label)
            out_rows.append({"line": label})
            continue
        if kind in ("reported", "net"):
            print("-" * (w_lab + w_col * len(cols)))

        cells, raw = [], {}
        allmiss = True
        for c in cols:
            v = vals[c].get(concept)
            if v is None or (kind == "residual" and abs(v) < 1e5):
                cells.append(f"{'--':>{w_col}}")
                raw[c] = ""
                continue
            allmiss = False
            raw[c] = round(v / div, 1)
            s = f"{v/div:,.1f}" if v >= 0 else f"({abs(v)/div:,.1f})"
            cells.append(f"{s:>{w_col}}")

        if allmiss and kind == "residual":
            continue          # don't print an all-blank residual row
        print(f"{label:<{w_lab}}" + "".join(cells))
        row = {"line": label, "concept": concept or "", "kind": kind}
        row.update({c: raw[c] for c in cols})
        out_rows.append(row)

    print("=" * (w_lab + w_col * len(cols)))

    print("\nnotes")
    print("  Totals and NII are as reported, not sums of the lines above them.")
    if derived_cols:
        print(f"  (D) = derived as Q4 = FY - 9M, no 3-month Q4 exists in the "
              f"filings: {', '.join(sorted(derived_cols, key=qkey))}")
    print("  'Implied provision' is NII minus NII-after-provision, not a "
          "directly tagged figure.")
    bad = [c for c in cols if isinstance(vals[c].get("__check__"), float)
           and abs(vals[c]["__check__"]) > 1e6]
    if bad:
        print(f"  !! check row non-zero at {', '.join(bad)} -- investigate "
              f"before using")
    else:
        print("  Check row is zero everywhere: interest income less interest "
              "expense ties to reported NII exactly.")

    out = args.out or f"nii-{args.filer}{'-annual' if args.annual else ''}.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["line", "concept", "kind"] + cols)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
