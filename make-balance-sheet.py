#!/usr/bin/env python3
"""
Quarterly balance sheet from anchors.csv -- dates as columns.

    python3 make-balance-sheet.py                    # Capital One, $mm
    python3 make-balance-sheet.py --filer schw
    python3 make-balance-sheet.py --units bn

Writes balance-sheet-<filer>.csv and prints the same table.

Two things to understand about the subtotals:

  * Total assets / liabilities / equity are the REPORTED figures, taken
    straight from the filing. They are not sums of the lines above them.
  * Only a few balance-sheet lines are tagged with the concepts we extract, so
    the components do not add to the totals. The difference is shown on an
    explicit "other / not separately tagged" line rather than being buried.
    For Capital One that residual is real and large -- goodwill from the
    Discover deal, held-to-maturity securities, premises, other receivables.

The Net line is assets - (liabilities + equity). It should be zero. It is the
articulation check: a non-zero value means the extracted tags are wrong, not
that the balance sheet doesn't balance.
"""
import argparse, csv, os, sys
from collections import defaultdict

# (label, concept, kind)
#   kind: line     = component, counts toward the identified subtotal
#         memo     = shown for information, NOT counted (avoids double-counting)
#         contra   = shown as a negative, not counted
#         reported = the filed subtotal
LAYOUT = [
    ("ASSETS", None, "header"),
    ("  Cash and cash equivalents",            "cash_and_equivalents", "line"),
    ("  Investment securities (AFS)",          "securities_afs",       "line"),
    ("  Investment securities (HTM)",          "securities_htm",       "line"),
    ("  Loans held for investment, gross",     "loans_hfi_gross",      "memo"),
    ("  Less: allowance for credit losses",    "allowance_credit_loss", "contra"),
    ("  Loans held for investment, net",       "loans_hfi_net",        "line"),
    ("  Other assets (not separately tagged)", "__residual_assets__",  "residual"),
    ("TOTAL ASSETS",                           "total_assets",         "reported"),

    ("LIABILITIES", None, "header"),
    ("  Deposits -- interest bearing",         "deposits_interest_bearing", "memo"),
    ("  Deposits -- non-interest bearing",      "deposits_noninterest",     "memo"),
    ("  Deposits, total",                      "deposits",             "line"),
    ("  Long-term debt",                       "long_term_debt",       "line"),
    ("  Other liabilities (not separately tagged)", "__residual_liabs__", "residual"),
    ("TOTAL LIABILITIES",                      "total_liabilities",    "reported"),

    ("EQUITY", None, "header"),
    ("  Total stockholders' equity",           "total_equity",         "reported"),

    ("CHECK", None, "header"),
    ("NET: assets - (liabilities + equity)",   "__net__",              "net"),
]

ASSET_LINES = ["cash_and_equivalents", "securities_afs", "securities_htm",
               "loans_hfi_net"]
LIAB_LINES  = ["deposits", "long_term_debt"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchors", default="anchors.csv")
    ap.add_argument("--filer", default="cof")
    ap.add_argument("--units", choices=["mm", "bn"], default="mm")
    ap.add_argument("--since", default=None,
                    help="earliest period-end to show (YYYY-MM-DD)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.anchors):
        sys.exit(f"missing {args.anchors} -- run extract-local-anchors.py")

    div = 1e6 if args.units == "mm" else 1e9
    tag = "$mm" if args.units == "mm" else "$bn"

    vals = defaultdict(dict)          # period -> concept -> value (dollars)
    with open(args.anchors, newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("filer") != args.filer:
                continue
            try:
                vals[r["period_end"]][r["concept"]] = float(r["value_usd"])
            except (TypeError, ValueError):
                continue

    # Only periods with a full A/L/E set are real balance sheets. The others are
    # stray comparatives picked up from income-statement contexts.
    periods = sorted(p for p, v in vals.items()
                     if all(k in v for k in
                            ("total_assets", "total_liabilities", "total_equity")))
    if not periods:
        sys.exit(f"no complete balance sheets for filer={args.filer}")

    dropped = sorted(set(vals) - set(periods))
    if args.since:
        before = [p for p in periods if p < args.since]
        periods = [p for p in periods if p >= args.since]
        if not periods:
            sys.exit(f"no complete balance sheets on/after {args.since}")
        if before:
            print(f"(also available before {args.since}: {', '.join(before)})")

    # derived lines
    for p in periods:
        v = vals[p]
        ident_a = sum(v.get(c, 0.0) for c in ASSET_LINES)
        ident_l = sum(v.get(c, 0.0) for c in LIAB_LINES)
        v["__residual_assets__"] = v["total_assets"] - ident_a
        v["__residual_liabs__"]  = v["total_liabilities"] - ident_l
        v["__net__"] = v["total_assets"] - (v["total_liabilities"] + v["total_equity"])

    # ---------------------------------------------------------------- render
    w_lab, w_col = 44, 15
    head = f"{args.filer.upper()} -- quarterly balance sheet ({tag})"
    print("\n" + head)
    print("=" * (w_lab + w_col * len(periods)))
    print(" " * w_lab + "".join(f"{p:>{w_col}}" for p in periods))
    print("-" * (w_lab + w_col * len(periods)))

    out_rows = []
    for label, concept, kind in LAYOUT:
        if kind == "header":
            print()
            print(label)
            out_rows.append({"line": label})
            continue

        cells, raw = [], {}
        for p in periods:
            v = vals[p].get(concept)
            if v is None:
                cells.append(f"{'--':>{w_col}}")
                raw[p] = ""
                continue
            shown = -abs(v) if kind == "contra" else v
            raw[p] = round(shown / div, 1)
            s = f"{shown/div:,.1f}"
            if kind == "contra":
                s = f"({abs(shown)/div:,.1f})"
            cells.append(f"{s:>{w_col}}")

        prefix = ""
        if kind == "memo":
            prefix = ""          # label already indented
        if kind in ("reported", "net"):
            print("-" * (w_lab + w_col * len(periods)))
        print(f"{label:<{w_lab}}" + "".join(cells))

        row = {"line": label, "concept": concept or "", "kind": kind}
        row.update({p: raw[p] for p in periods})
        out_rows.append(row)

    print("=" * (w_lab + w_col * len(periods)))

    # ---------------------------------------------------------------- notes
    print("\nnotes")
    print("  Total assets / liabilities / equity are as reported, not sums of "
          "the lines above.")
    print("  'memo' lines (gross loans, deposit split) are excluded from the "
          "residual maths to avoid double-counting.")
    net_bad = [p for p in periods if abs(vals[p]["__net__"]) > 1e6]
    if net_bad:
        print(f"  !! Net is non-zero at {', '.join(net_bad)} -- the extracted "
              f"tags are inconsistent, investigate before using.")
    else:
        print("  Net is zero at every period: assets tie to liabilities plus "
              "equity exactly.")
    for c in ("securities_htm", "long_term_debt"):
        if all(c not in vals[p] for p in periods):
            print(f"  '{c}' was never tagged with the concepts we search for, "
                  f"so it sits inside the residual.")
    if dropped:
        print(f"  {len(dropped)} period-end(s) excluded for lacking a full "
              f"A/L/E set: {', '.join(dropped)}")
    # Only nag about missing quarters if the sequence actually has holes.
    def qend(p):
        y, m = int(p[:4]), int(p[5:7])
        return y * 4 + (m - 1) // 3
    want = set(range(qend(periods[0]), qend(periods[-1]) + 1))
    gaps = want - {qend(p) for p in periods}
    if gaps:
        names = sorted(f"{q // 4}Q{q % 4 + 1}" for q in gaps)
        print(f"  MISSING {len(gaps)} quarter-end(s) in this range: "
              f"{', '.join(names)} -- fetch the matching 10-Q with "
              f"download-periodic.py")
    else:
        print(f"  Quarter-end sequence is complete: {len(periods)} consecutive "
              f"quarters, no gaps.")

    out = args.out or f"balance-sheet-{args.filer}.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["line", "concept", "kind"] + periods)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
