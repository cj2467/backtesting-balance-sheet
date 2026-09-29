#!/usr/bin/env python3
"""
Monthly P&L view for Capital One -- months down rows, lines across columns.

    python3 make-monthly-pl.py                     # -> monthly-pl-cof.csv
    python3 make-monthly-pl.py --since 2024-08

READ THIS FIRST: there is no monthly income statement, and this file does not
pretend to be one.

Exactly ONE income-statement line is disclosed monthly: net charge-offs, in the
Reg FD credit-metrics 8-K. Everything else on the P&L -- interest income,
interest expense, net interest income, non-interest income, non-interest
expense, provision, net income -- exists only quarterly, because an income
statement is a duration and the shortest duration issuers report is a quarter
(and Q4 not even that; it has to be derived as FY minus nine months).

So this table is:

  * MONTHLY, from the 8-K:  net charge-offs, and the credit/balance context
    needed to interpret them (average and period-end loans, delinquencies).
  * QUARTERLY, from the 10-K/10-Q: NII and net income, written ONLY on the
    quarter-end row. Intra-quarter rows are blank. Not interpolated, not
    smoothed, not divided by three.

Dividing a quarter's NII across its months would look like data and be an
assumption. If you want that, do it deliberately in your model where the
assumption is visible.

Inputs: credit-metrics-tidy.csv (parse-credit-metrics.py), flows.csv
        (extract-local-flows.py), anchors.csv (extract-local-anchors.py)
"""
import argparse, csv, os, sys
from collections import defaultdict

# Monthly, from the 8-K exhibits: (segment, metric) -> column
MONTHLY = [
    ("domestic_card", "net_charge_offs",          "card_nco"),
    ("domestic_card", "net_charge_off_rate",      "card_nco_rate"),
    ("domestic_card", "average_loans",            "card_avg_loans"),
    ("domestic_card", "period_end_loans",         "card_eop_loans"),
    ("domestic_card", "delinquencies_30plus",     "card_dq30"),
    ("domestic_card", "delinquency_rate_30plus",  "card_dq30_rate"),
    ("auto",          "net_charge_offs",          "auto_nco"),
    ("auto",          "net_charge_off_rate",      "auto_nco_rate"),
    ("auto",          "period_end_loans",         "auto_eop_loans"),
    ("auto",          "delinquencies_30plus",     "auto_dq30"),
    ("discover_domestic_card", "period_end_loans", "disc_eop_loans"),
    ("discover_domestic_card", "net_charge_off_rate", "disc_nco_rate"),
    ("domestic_card_legacy_cof", "period_end_loans", "legacy_cof_eop_loans"),
]

# Quarterly, from flows.csv -- only on quarter-end rows
QUARTERLY = [
    ("net_interest_income", "q_nii"),
    ("int_inc_total",       "q_int_income"),
    ("int_exp_total",       "q_int_expense"),
    ("net_income",          "q_net_income"),
]

MERGER_MONTH = "2025-05"


def month_range(lo, hi):
    y, m = map(int, lo.split("-")); Y, M = map(int, hi.split("-"))
    out = []
    while (y, m) <= (Y, M):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tidy", default="credit-metrics-tidy.csv")
    ap.add_argument("--flows", default="flows.csv")
    ap.add_argument("--filer", default="cof")
    ap.add_argument("--since", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.tidy):
        sys.exit(f"missing {args.tidy} -- run parse-credit-metrics.py")

    mv = defaultdict(dict)
    with open(args.tidy, newline="") as fh:
        for r in csv.DictReader(fh):
            for seg, met, col in MONTHLY:
                if r["segment"] == seg and r["metric"] == met:
                    # prefer Capital One's own filing where both report a month
                    if col in mv[r["period"]] and r["filer"] != args.filer:
                        continue
                    mv[r["period"]][col] = float(r["value"])

    qv = defaultdict(dict)
    if os.path.exists(args.flows):
        with open(args.flows, newline="") as fh:
            for r in csv.DictReader(fh):
                if r["filer"] != args.filer or int(r["months"]) != 3:
                    continue
                for concept, col in QUARTERLY:
                    if r["concept"] == concept:
                        qv[r["period_end"][:7]][col] = float(r["value_usd"]) / 1e6
    else:
        print(f"! {args.flows} missing -- quarterly columns will be blank",
              file=sys.stderr)

    if not mv:
        sys.exit("no monthly facts found")
    months = month_range(min(mv), max(max(mv), max(qv) if qv else min(mv)))
    if args.since:
        months = [m for m in months if m >= args.since]

    mcols = [c for _, _, c in MONTHLY]
    qcols = [c for _, c in QUARTERLY]
    fields = ["period", "flag"] + mcols + qcols

    rows = []
    for p in months:
        row = {f: "" for f in fields}
        row["period"] = p
        if p == MERGER_MONTH:
            row["flag"] = "discover_close_partial_month"
        elif p in qv:
            row["flag"] = "quarter_end"
        for c in mcols:
            if c in mv.get(p, {}):
                row[c] = round(mv[p][c], 2)
        for c in qcols:
            if c in qv.get(p, {}):
                row[c] = round(qv[p][c], 1)
        rows.append(row)

    # ------------------------------------------------------------- render
    show = ["card_eop_loans", "card_nco", "card_nco_rate", "card_dq30_rate",
            "auto_eop_loans", "auto_nco", "q_nii", "q_net_income"]
    hdr = {"card_eop_loans": "card EOP", "card_nco": "card NCO",
           "card_nco_rate": "NCO %", "card_dq30_rate": "DQ30 %",
           "auto_eop_loans": "auto EOP", "auto_nco": "auto NCO",
           "q_nii": "Q NII", "q_net_income": "Q net inc"}
    print(f"\n{args.filer.upper()} -- monthly P&L / credit view  "
          f"($mm, rates in %)")
    print("  monthly columns from the 8-K; Q columns only on quarter-end rows")
    print("=" * 116)
    print(f"{'month':9s}{'':2s}" + "".join(f"{hdr[c]:>13s}" for c in show))
    print("-" * 116)
    for r in rows:
        mark = "*" if r["flag"] == "discover_close_partial_month" else (
               "|" if r["flag"] == "quarter_end" else " ")
        cells = "".join(
            f"{r[c]:>13,.2f}" if isinstance(r[c], float) and c.endswith("rate")
            else (f"{r[c]:>13,.0f}" if isinstance(r[c], float) else f"{'':>13s}")
            for c in show)
        print(f"{r['period']:9s}{mark:2s}" + cells)
    print("=" * 116)

    filled_m = sum(1 for r in rows for c in mcols if r[c] != "")
    filled_q = sum(1 for r in rows for c in qcols if r[c] != "")
    print(f"\n{len(rows)} months. monthly cells {filled_m}, "
          f"quarterly cells {filled_q} (on {len(qv)} quarter-end rows).")
    print("* = Discover close (2025-05-18), partial month")
    print("| = quarter end, carries the quarterly P&L figures")
    gaps = [r["period"] for r in rows if all(r[c] == "" for c in mcols)]
    if gaps:
        print(f"months with NO monthly data ({len(gaps)}): {', '.join(gaps)}")
    print("\nNII, net income and every other P&L line are QUARTERLY. Blank "
          "intra-quarter cells are blank on purpose.")

    out = args.out or f"monthly-pl-{args.filer}.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
