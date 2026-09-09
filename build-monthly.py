#!/usr/bin/env python3
"""
Assemble the monthly balance-sheet scaffold.

    python3 build-monthly.py

Inputs   anchors.csv               (fetch-xbrl-anchors.py)
         credit-metrics-tidy.csv   (parse-credit-metrics.py)
Outputs  monthly-balance-sheet.csv
         monthly-coverage.csv

DESIGN, so the output isn't mistaken for more than it is:

  * Lines disclosed monthly are populated from the 8-K exhibits.
  * Lines disclosed only quarterly are populated ONLY at quarter-ends, from
    XBRL. Intra-quarter cells are LEFT BLANK, by choice -- no interpolation.
  * Therefore the sheet does NOT articulate monthly: assets will not tie to
    liabilities plus equity except at quarter-ends. That is expected. You
    supply the funding-side assumptions; this file supplies only facts.

Every value carries a `*_src` column: `monthly_8k`, `xbrl_10q`, `xbrl_10k`,
or blank. Nothing is imputed without being labelled.

ON THE DISCOVER SPLICE -- read this before using pre-May-2025 figures.
Discover's standalone monthly exhibit reported RATES ONLY (net principal
charge-off rate, 30+ day delinquency rate). It carried no period-end dollar
balances. So a pre-close monthly *dollar* splice cannot be built from monthly
disclosure; it would require interpolating Discover's quarterly balances,
which contradicts the no-interpolation choice above. This script therefore:
  - reports combined as-reported figures from 2025-06 onward,
  - flags 2025-05 as a partial merger month (closed 2025-05-18),
  - leaves pre-close combined dollars BLANK and carries Discover's rates in
    their own columns, with splice_status saying why.
If you want interpolated pre-close dollars, that's a deliberate modelling
decision -- add it explicitly rather than letting it appear here silently.
"""
import argparse, csv, os, sys
from collections import defaultdict

MERGER_CLOSE   = "2025-05-18"
MERGER_MONTH   = "2025-05"
FIRST_COMBINED = "2025-06"

# Purchase-accounting distortions to surface on affected rows. Both figures
# came from secondary sources and MUST be checked against the filings --
# two searches disagreed ($18.0bn vs $19.4bn).
PA_NOTES = {
    MERGER_MONTH: "merger closed 2025-05-18; partial-month contribution",
    "2025-06": ("pre-Legal-Day-1 accelerated charge-off unwind reduced NCOs "
                "~$39mm (~47bp Discover, ~19bp total) -- VERIFY in filing"),
}
GLOBAL_NOTE = ("acquired Discover loans that were fully charged off are excluded "
               "from charge-offs (~$18.0bn or ~$19.4bn per source -- VERIFY); "
               "expected recoveries ~$3.3bn benefit the allowance")

# Monthly series to lift out of the tidy CSV: (segment, metric) -> column.
MONTHLY_COLS = {
    ("domestic_card", "period_end_loans"):          "card_loans_eop",
    ("domestic_card", "net_charge_offs"):           "card_nco",
    ("domestic_card", "net_charge_off_rate"):       "card_nco_rate",
    ("domestic_card", "delinquencies_30plus"):      "card_dq30",
    ("domestic_card", "delinquency_rate_30plus"):   "card_dq30_rate",
    ("discover_domestic_card", "period_end_loans"): "disc_loans_eop",
    ("discover_domestic_card", "net_charge_offs"):  "disc_nco",
    ("discover_domestic_card", "net_charge_off_rate"): "disc_nco_rate",
    ("discover_domestic_card", "delinquency_rate_30plus"): "disc_dq30_rate",
    ("auto", "period_end_loans"):                   "auto_loans_eop",
    ("auto", "net_charge_offs"):                    "auto_nco",
    ("auto", "net_charge_off_rate"):                "auto_nco_rate",
    ("auto", "delinquencies_30plus"):               "auto_dq30",
}

# Quarterly-only balance sheet lines, from XBRL.
ANCHOR_COLS = ["total_assets", "total_liabilities", "total_equity", "deposits",
               "loans_hfi_gross", "loans_hfi_net", "allowance_credit_loss",
               "securities_afs", "securities_htm", "cash_and_equivalents",
               "long_term_debt"]

# Coverage compares monthly segment loans against the GROSS loan total: the
# monthly 8-K reports loans held for investment before allowance. Using the net
# figure would overstate coverage by the size of the allowance (~$23bn for COF).
COVERAGE_ANCHOR = "loans_hfi_gross"


def read_csv(path):
    if not os.path.exists(path):
        return None
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def month_range(lo, hi):
    y, m = map(int, lo.split("-")); Y, M = map(int, hi.split("-"))
    out = []
    while (y, m) <= (Y, M):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def to_month(period_end):
    return period_end[:7]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchors", default="anchors.csv")
    ap.add_argument("--monthly", default="credit-metrics-tidy.csv")
    ap.add_argument("--out", default="monthly-balance-sheet.csv")
    ap.add_argument("--coverage-out", default="monthly-coverage.csv")
    args = ap.parse_args()

    anchors = read_csv(args.anchors)
    monthly = read_csv(args.monthly)
    if monthly is None:
        sys.exit(f"missing {args.monthly} -- run parse-credit-metrics.py")
    if anchors is None:
        print(f"! missing {args.anchors} -- quarterly columns will be empty",
              file=sys.stderr)
        anchors = []

    # ---- monthly facts, keyed by month. Prefer Capital One's own filings for
    # combined figures; keep Discover standalone separate.
    mvals, msrc = defaultdict(dict), defaultdict(dict)
    for r in monthly:
        col = MONTHLY_COLS.get((r["segment"], r["metric"]))
        if not col:
            continue
        per = r["period"]
        if not per:
            continue
        # A Discover-standalone rate and a COF-reported Discover rate can both
        # exist for the same month; COF's filing wins for the combined view.
        if col in mvals[per] and r["filer"] != "cof":
            continue
        try:
            mvals[per][col] = float(r["value"])
        except (TypeError, ValueError):
            continue
        msrc[per][col] = "monthly_8k"

    # ---- quarterly anchors, keyed by the month the quarter ends in
    avals, asrc = defaultdict(dict), defaultdict(dict)
    for r in anchors:
        if r.get("filer") != "cof":
            continue
        c = r["concept"]
        if c not in ANCHOR_COLS:
            continue
        per = to_month(r["period_end"])
        try:
            avals[per][c] = float(r["value_usd"])
        except (TypeError, ValueError):
            continue
        asrc[per][c] = "xbrl_" + r.get("form", "").lower().replace("-", "")

    all_months = sorted(set(mvals) | set(avals))
    if not all_months:
        sys.exit("no data in either input")
    months = month_range(all_months[0], all_months[-1])

    mcols = list(MONTHLY_COLS.values())
    fields = (["period", "splice_status", "notes"]
              + mcols + [c + "_src" for c in mcols]
              + ANCHOR_COLS + [c + "_src" for c in ANCHOR_COLS]
              + ["monthly_loans_covered", "anchor_loans_hfi",
                 "monthly_coverage_pct", "articulation_diff"])

    rows, coverage = [], []
    for per in months:
        row = {f: "" for f in fields}
        row["period"] = per

        if per < MERGER_MONTH:
            row["splice_status"] = "pre_close_cof_only__combined_dollars_unavailable"
        elif per == MERGER_MONTH:
            row["splice_status"] = "merger_month_partial"
        elif per >= FIRST_COMBINED:
            row["splice_status"] = "as_reported_combined"

        notes = []
        if per in PA_NOTES:
            notes.append(PA_NOTES[per])
        if per >= FIRST_COMBINED:
            notes.append(GLOBAL_NOTE)
        row["notes"] = " | ".join(notes)

        for c in mcols:
            if c in mvals.get(per, {}):
                row[c] = mvals[per][c]
                row[c + "_src"] = msrc[per][c]
        for c in ANCHOR_COLS:
            if c in avals.get(per, {}):
                row[c] = avals[per][c]
                row[c + "_src"] = asrc[per][c]

        # How much of the loan book do the monthly disclosures actually cover?
        # Only meaningful at quarter-ends, where an XBRL total exists.
        # Card is reported combined post-close, so don't double-count Discover.
        parts = [row.get(c) for c in ("card_loans_eop", "auto_loans_eop")]
        if per < MERGER_MONTH:
            pass  # legacy COF card + auto only
        covered = sum(p for p in parts if isinstance(p, float))
        if covered:
            row["monthly_loans_covered"] = covered
        anchor_loans = avals.get(per, {}).get(COVERAGE_ANCHOR)
        if anchor_loans:
            row["anchor_loans_hfi"] = anchor_loans
            if covered:
                # monthly exhibits are in millions; XBRL is in dollars
                pct = (covered * 1e6) / anchor_loans * 100
                row["monthly_coverage_pct"] = round(pct, 1)
                coverage.append({"period": per, "monthly_mm": covered,
                                 "xbrl_usd": anchor_loans,
                                 "coverage_pct": round(pct, 1)})

        a, l, e = (avals.get(per, {}).get(k) for k in
                   ("total_assets", "total_liabilities", "total_equity"))
        if a and l and e:
            row["articulation_diff"] = a - (l + e)

        rows.append(row)

    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(rows)

    if coverage:
        with open(args.coverage_out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(coverage[0].keys()))
            w.writeheader(); w.writerows(coverage)

    # ------------------------------------------------------------- report
    filled  = sum(1 for r in rows for c in mcols if r[c] != "")
    qfilled = sum(1 for r in rows for c in ANCHOR_COLS if r[c] != "")
    print(f"{len(rows)} months ({months[0]} .. {months[-1]}) -> {args.out}")
    print(f"  monthly cells filled   {filled:5d} / {len(rows)*len(mcols)}")
    print(f"  quarterly cells filled {qfilled:5d} / {len(rows)*len(ANCHOR_COLS)}"
          "   (blank intra-quarter by design)")

    qends = [r["period"] for r in rows if r["anchor_loans_hfi"] != ""]
    print(f"  quarter-end anchors: {len(qends)}"
          + (f"  ({', '.join(qends)})" if qends else ""))

    if coverage:
        print("\nloan-book coverage of the monthly data at each anchor:")
        for c in coverage:
            print(f"   {c['period']}  monthly {c['monthly_mm']:>12,.0f}mm  "
                  f"vs XBRL {c['xbrl_usd']/1e6:>12,.0f}mm  = {c['coverage_pct']:5.1f}%")
        avg = sum(c["coverage_pct"] for c in coverage) / len(coverage)
        print(f"   mean coverage {avg:.1f}%  -- the remainder (commercial, other "
              f"consumer, securities, cash) has no monthly signal at all")
    else:
        print("\n! no quarter-end overlap between monthly and XBRL data, so "
              "coverage could not be checked. Widen MONTHS_BACK / --since.")

    bad = [r for r in rows if isinstance(r["articulation_diff"], float)
           and abs(r["articulation_diff"]) > 1e7]
    if bad:
        print(f"\n! {len(bad)} anchor(s) where assets != liabilities + equity by "
              f">$10mm -- check the XBRL tag choices in fetch-xbrl-anchors.py:")
        for r in bad[:6]:
            print(f"   {r['period']}  {r['articulation_diff']/1e6:,.1f}mm")

    print("\nReminder: this scaffold has no deposits/securities values between "
          "quarter-ends. It does not balance monthly, and is not meant to.")


if __name__ == "__main__":
    main()
