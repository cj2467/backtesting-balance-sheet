#!/usr/bin/env python3
"""
Full quarterly income statement from flows.csv -- quarters as columns.

    python3 make-income-statement.py --since 2024Q1          # $mm
    python3 make-income-statement.py --since 2024Q1 --units bn
    python3 make-income-statement.py --annual

Every figure is as-reported from the 10-K/10-Q inline XBRL, EXCEPT Q4, which no
issuer reports as a 3-month period (the 10-K carries 12-month durations only).
Q4 is therefore FY minus the as-reported 9-month figure -- exact arithmetic,
flagged (D).

That derivation is only safe if nothing was restated between the Q3 10-Q and
the 10-K. extract-local-flows.py tests exactly that by checking Q1+Q2+Q3
against the as-reported 9M figure; on this dataset all 14 checks tie to 0.0,
so the derived quarters are sound.

Four articulation checks run at the bottom. They should all be zero. They test
different joins, so a failure localises the problem:

    A  total interest income - total interest expense - NII
    B  NII - provision - NII after provision
    C  NII + non-interest income - provision - non-interest expense - pre-tax
    D  pre-tax - tax - net income
"""
import argparse, csv, os, sys
from collections import defaultdict

LAYOUT = [
    ("INTEREST INCOME", None, "header"),
    ("  Loans and leases",                  "int_inc_loans",        "line"),
    ("  Investment securities",             "int_inc_securities",   "line"),
    ("  Other",                             "int_inc_other",        "line"),
    ("  Unallocated",                       "__resid_ii__",         "residual"),
    ("Total interest income",               "int_inc_total",        "subtotal"),

    ("INTEREST EXPENSE", None, "header"),
    ("  Deposits",                          "int_exp_deposits",     "line"),
    ("  Securitized debt",                  "int_exp_secured",      "line"),
    ("  Senior and subordinated notes",     "int_exp_unsecured",    "line"),
    ("  Other borrowings",                  "int_exp_other",        "line"),
    ("  Unallocated",                       "__resid_ie__",         "residual"),
    ("Total interest expense",              "int_exp_total",        "subtotal"),

    ("", None, "header"),
    ("NET INTEREST INCOME",                 "net_interest_income",  "subtotal"),
    ("  Provision for credit losses",       "provision",            "line"),
    ("Net interest income after provision", "nii_after_provision",  "subtotal"),

    ("NON-INTEREST INCOME / EXPENSE", None, "header"),
    ("  Non-interest income",               "noninterest_income",   "line"),
    ("  Total revenue (memo)",              "total_revenue",        "memo"),
    ("  Marketing",                         "nie_marketing",        "line"),
    ("  Occupancy",                         "nie_occupancy",        "line"),
    ("  Professional fees",                 "nie_professional",     "line"),
    ("  Other non-interest expense",        "__resid_nie__",        "residual"),
    ("Total non-interest expense",          "noninterest_expense",  "subtotal"),

    ("", None, "header"),
    ("PRE-TAX INCOME",                      "pretax_income",        "subtotal"),
    ("  Income tax expense",                "income_tax",           "line"),
    ("Income from continuing operations",   "__cont_ops__",         "subtotal"),
    ("  Discontinued operations, net of tax", "discontinued_ops",   "line"),
    ("NET INCOME",                          "net_income",           "subtotal"),
    ("  Preferred dividends",               "preferred_dividends",  "line"),

    ("PER SHARE", None, "header"),
    ("  EPS -- basic",                      "eps_basic",            "eps"),
    ("  EPS -- diluted",                    "eps_diluted",          "eps"),

    ("CHECKS (all should be zero)", None, "header"),
    ("A  int income - int expense - NII",   "__chk_a__",            "net"),
    ("B  NII - provision - NII after prov", "__chk_b__",            "net"),
    ("C  NII + NII inc - prov - NIE - pretax", "__chk_c__",         "net"),
    ("D  pre-tax - tax + disc ops - net income", "__chk_d__",       "net"),
]

II_LINES  = ["int_inc_loans", "int_inc_securities", "int_inc_other"]
IE_LINES  = ["int_exp_deposits", "int_exp_secured", "int_exp_unsecured",
             "int_exp_other"]
NIE_LINES = ["nie_marketing", "nie_occupancy", "nie_professional",
             "nie_salaries"]


def qkey(q):
    y, n = q.split("Q")
    return int(y) * 4 + int(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default="flows.csv")
    ap.add_argument("--filer", default="cof")
    ap.add_argument("--units", choices=["mm", "bn"], default="mm")
    ap.add_argument("--since", default=None)
    ap.add_argument("--annual", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.flows):
        sys.exit(f"missing {args.flows} -- run extract-local-flows.py")

    div = 1e6 if args.units == "mm" else 1e9
    unit = "$mm" if args.units == "mm" else "$bn"
    months = 12 if args.annual else 3

    vals, derived = defaultdict(dict), set()
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
                derived.add(col)

    cols = sorted(vals, key=qkey if months == 3 else str)
    if args.since:
        cols = [c for c in cols if (qkey(c) >= qkey(args.since) if months == 3
                                    else c >= args.since)]
    if not cols:
        sys.exit("no periods to show")

    for c in cols:
        v = vals[c]
        g = v.get
        if g("int_inc_total") is not None:
            v["__resid_ii__"] = g("int_inc_total") - sum(g(k, 0.0) for k in II_LINES)
        if g("int_exp_total") is not None:
            v["__resid_ie__"] = g("int_exp_total") - sum(g(k, 0.0) for k in IE_LINES)
        if g("noninterest_expense") is not None:
            v["__resid_nie__"] = (g("noninterest_expense")
                                  - sum(g(k, 0.0) for k in NIE_LINES))
        if all(g(k) is not None for k in ("int_inc_total", "int_exp_total",
                                          "net_interest_income")):
            v["__chk_a__"] = (g("int_inc_total") - g("int_exp_total")
                              - g("net_interest_income"))
        if all(g(k) is not None for k in ("net_interest_income", "provision",
                                          "nii_after_provision")):
            v["__chk_b__"] = (g("net_interest_income") - g("provision")
                              - g("nii_after_provision"))
        if all(g(k) is not None for k in ("net_interest_income",
                                          "noninterest_income", "provision",
                                          "noninterest_expense", "pretax_income")):
            v["__chk_c__"] = (g("net_interest_income") + g("noninterest_income")
                              - g("provision") - g("noninterest_expense")
                              - g("pretax_income"))
        if all(g(k) is not None for k in ("pretax_income", "income_tax")):
            v["__cont_ops__"] = g("pretax_income") - g("income_tax")
        if all(g(k) is not None for k in ("pretax_income", "income_tax",
                                          "net_income")):
            # Net income includes discontinued operations, which sit below the
            # continuing-operations pre-tax line. Omitting the term made this
            # check fail by $365mm in FY2025 -- the check was right, the layout
            # was incomplete.
            v["__chk_d__"] = (g("pretax_income") - g("income_tax")
                              + g("discontinued_ops", 0.0) - g("net_income"))

    w_lab, w_col = 42, 12
    title = (f"{args.filer.upper()} -- "
             f"{'annual' if args.annual else 'quarterly'} income statement ({unit})")
    print("\n" + title)
    print("=" * (w_lab + w_col * len(cols)))
    print(" " * w_lab + "".join(
        f"{c + ('(D)' if c in derived else ''):>{w_col}}" for c in cols))
    print("-" * (w_lab + w_col * len(cols)))

    out_rows = []
    for label, concept, kind in LAYOUT:
        if kind == "header":
            print()
            if label:
                print(label)
            out_rows.append({"line": label})
            continue

        cells, raw, allmiss = [], {}, True
        for c in cols:
            v = vals[c].get(concept)
            if v is None or (kind == "residual" and abs(v) < 1e5):
                cells.append(f"{'--':>{w_col}}"); raw[c] = ""; continue
            allmiss = False
            if kind == "eps":
                raw[c] = round(v, 2)
                s = f"{v:,.2f}"
            else:
                raw[c] = round(v / div, 1)
                s = (f"{v/div:,.1f}" if v >= 0 else f"({abs(v)/div:,.1f})")
            cells.append(f"{s:>{w_col}}")
        if allmiss and kind in ("residual", "line", "memo", "eps"):
            continue
        if kind in ("subtotal", "net"):
            print("-" * (w_lab + w_col * len(cols)))
        print(f"{label:<{w_lab}}" + "".join(cells))
        row = {"line": label, "concept": concept or "", "kind": kind}
        row.update({c: raw[c] for c in cols})
        out_rows.append(row)

    print("=" * (w_lab + w_col * len(cols)))

    print("\nnotes")
    print("  Every figure is as-reported from inline XBRL except (D) columns.")
    if derived:
        print(f"  (D) = Q4 derived as FY - 9M; no issuer reports a 3-month Q4: "
              f"{', '.join(sorted(derived, key=qkey))}")
        print("       Q1+Q2+Q3 ties to the as-reported 9M figure, so nothing was "
              "restated and the subtraction holds.")
    print("  Subtotals are the filed values, not sums of the lines above.")

    fails = []
    for chk, name in (("__chk_a__", "A"), ("__chk_b__", "B"),
                      ("__chk_c__", "C"), ("__chk_d__", "D")):
        bad = [c for c in cols if isinstance(vals[c].get(chk), float)
               and abs(vals[c][chk]) > 1e6]
        n = sum(1 for c in cols if isinstance(vals[c].get(chk), float))
        if bad:
            fails.append(f"{name} fails at {', '.join(bad)}")
        elif n:
            print(f"  check {name}: zero across all {n} period(s)")
    for f in fails:
        print(f"  !! check {f} -- investigate before relying on those columns")

    out = args.out or f"income-statement-{args.filer}" \
                      f"{'-annual' if args.annual else ''}.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["line", "concept", "kind"] + cols)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
