#!/usr/bin/env python3
"""
Pull the macro drivers for a bank balance-sheet model from FRED, monthly,
2022 to present.

    python3 fetch-macro.py                      # -> macro-monthly.csv (+ tidy)
    python3 fetch-macro.py --start 2020-01-01
    python3 fetch-macro.py --dry-run            # list series and URLs only

RUN THIS ON YOUR OWN MACHINE. Cowork's network egress is restricted to a single
allowlisted host, so fred.stlouisfed.org is unreachable from inside it.

No API key needed -- uses FRED's public CSV endpoint:
    https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>&cosd=<START>

FREQUENCY, HANDLED HONESTLY. FRED serves each series at its native frequency.
  * Daily and weekly series are averaged within the calendar month, and the
    aggregation method is recorded per series.
  * Monthly series pass through.
  * QUARTERLY series are NOT interpolated. The value lands on the quarter-end
    month and intra-quarter months stay blank. Spreading a quarterly print
    across three months would look like data and be an assumption.

Every series carries a plausibility range. A value outside it means the parse
went wrong (wrong column, missing-value marker read as a number, units
confusion) -- the script flags it rather than writing a silently bad series.
"""
import argparse, csv, datetime as dt, os, sys, time
import urllib.error, urllib.request
from collections import defaultdict

UA = os.environ.get("HTTP_UA", "macro-fetch (contact: cjbox21@gmail.com)")
BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# series_id, column name, group, native frequency, (low, high) plausible range
SERIES = [
    # ---- policy and benchmark interest rates (monthly natively)
    ("FEDFUNDS",        "fed_funds_eff",        "rates",   "M", (0.0, 12.0)),
    ("GS2",             "ust_2y",               "rates",   "M", (0.0, 12.0)),
    ("GS5",             "ust_5y",               "rates",   "M", (0.0, 12.0)),
    ("GS10",            "ust_10y",              "rates",   "M", (0.0, 12.0)),
    ("GS30",            "ust_30y",              "rates",   "M", (0.0, 12.0)),
    ("TB3MS",           "ust_3m",               "rates",   "M", (0.0, 12.0)),

    # ---- prime rate
    ("MPRIME",          "prime_rate",           "prime",   "M", (2.0, 14.0)),

    # ---- home prices (monthly, index level ~ 300 in 2022-26)
    ("CSUSHPISA",       "case_shiller_nsa_adj", "housing", "M", (150.0, 500.0)),
    ("CSUSHPINSA",      "case_shiller_nsa",     "housing", "M", (150.0, 500.0)),
    ("MORTGAGE30US",    "mortgage_30y_fixed",   "housing", "W", (2.0, 12.0)),

    # ---- labour
    ("UNRATE",          "unemployment_rate",    "labor",   "M", (2.0, 16.0)),
    ("U6RATE",          "underemployment_u6",   "labor",   "M", (4.0, 25.0)),
    ("PAYEMS",          "nonfarm_payrolls_k",   "labor",   "M", (120000.0, 200000.0)),

    # ---- credit spreads (daily -> monthly average)
    ("BAMLC0A0CM",      "ig_corp_oas",          "spreads", "D", (0.3, 8.0)),
    ("BAMLC0A4CBBB",    "bbb_corp_oas",         "spreads", "D", (0.5, 10.0)),
    ("BAMLH0A0HYM2",    "hy_corp_oas",          "spreads", "D", (2.0, 25.0)),
    ("T10Y2Y",          "term_spread_10y_2y",   "spreads", "D", (-2.0, 4.0)),
    ("T10Y3M",          "term_spread_10y_3m",   "spreads", "D", (-3.0, 5.0)),

    # ---- consumer credit pricing and performance (QUARTERLY -- not interpolated)
    ("TERMCBCCALLNS",   "cc_rate_all_accounts", "consumer", "Q", (8.0, 30.0)),
    ("TERMCBCCINTNS",   "cc_rate_accts_assessed_interest", "consumer", "Q", (8.0, 35.0)),
    ("DRCCLACBS",       "cc_delinq_rate_banks", "consumer", "Q", (1.0, 10.0)),
    ("CORCCACBS",       "cc_chargeoff_rate_banks", "consumer", "Q", (1.0, 12.0)),
    ("DRALACBN",        "all_loan_delinq_rate",  "consumer", "Q", (0.5, 10.0)),
]


def fetch(series_id, start, tries=3):
    url = f"{BASE}?id={series_id}&cosd={start}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                body = r.read()
                if body[:2] == b"\x1f\x8b":
                    import gzip
                    body = gzip.decompress(body)
                return body.decode("utf-8", "replace"), url
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < tries - 1:
                time.sleep(2 ** attempt); continue
            raise
        finally:
            time.sleep(0.3)
    raise RuntimeError("unreachable")


def parse_csv(text, series_id):
    """-> [(date, value)] ; handles both header spellings and '.' for missing."""
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        return []
    hdr = [h.strip().lower() for h in rows[0]]
    # FRED has used both "DATE" and "observation_date" over time
    date_i = 0
    for cand in ("observation_date", "date"):
        if cand in hdr:
            date_i = hdr.index(cand); break
    val_i = next((i for i, h in enumerate(hdr)
                  if h not in ("observation_date", "date")), 1)
    out = []
    for r in rows[1:]:
        if len(r) <= max(date_i, val_i):
            continue
        d, v = r[date_i].strip(), r[val_i].strip()
        if not d or v in (".", "", "NA", "null"):
            continue          # FRED marks missing as "."
        try:
            out.append((dt.date.fromisoformat(d), float(v)))
        except ValueError:
            continue
    return out


def to_monthly(obs, freq):
    """Collapse to {YYYY-MM: value}. Daily/weekly averaged; Q on quarter-end."""
    buckets = defaultdict(list)
    for d, v in obs:
        buckets[f"{d.year}-{d.month:02d}"].append(v)
    if freq in ("D", "W"):
        return {k: sum(vs) / len(vs) for k, vs in buckets.items()}, "mean of period"
    # monthly and quarterly: FRED stamps the period start; keep as-is.
    # Quarterly values are left on their own month -- no spreading.
    return {k: vs[-1] for k, vs in buckets.items()}, (
        "as reported" if freq == "M" else "as reported (quarterly; intra-quarter blank)")


def month_range(lo, hi):
    y, m = map(int, lo.split("-")); Y, M = map(int, hi.split("-"))
    out = []
    while (y, m) <= (Y, M):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--out", default="macro-monthly.csv")
    ap.add_argument("--tidy-out", default="macro-tidy.csv")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        print(f"{len(SERIES)} series, start {args.start}:")
        for sid, col, grp, fq, rng in SERIES:
            print(f"  {grp:9s} {fq}  {sid:16s} -> {col:34s} "
                  f"expect {rng[0]}..{rng[1]}")
            print(f"            {BASE}?id={sid}&cosd={args.start}")
        return

    data, meta, problems = {}, {}, []
    for sid, col, grp, fq, (lo, hi) in SERIES:
        try:
            text, url = fetch(sid, args.start)
        except Exception as e:
            print(f"  ! {sid:16s} FETCH FAILED: {type(e).__name__}: {e}",
                  file=sys.stderr)
            problems.append(f"{sid}: fetch failed")
            continue
        obs = parse_csv(text, sid)
        if not obs:
            print(f"  ! {sid:16s} no observations parsed", file=sys.stderr)
            problems.append(f"{sid}: no observations")
            continue
        monthly, method = to_monthly(obs, fq)

        out_of_range = {k: v for k, v in monthly.items() if not (lo <= v <= hi)}
        if out_of_range:
            sample = list(out_of_range.items())[:3]
            print(f"  ! {sid:16s} {len(out_of_range)} value(s) OUTSIDE "
                  f"{lo}..{hi}: {sample} -- check units/parsing", file=sys.stderr)
            problems.append(f"{sid}: {len(out_of_range)} out-of-range")

        data[col] = monthly
        meta[col] = {"series_id": sid, "group": grp, "native_freq": fq,
                     "aggregation": method, "url": url,
                     "n_obs": len(obs), "n_months": len(monthly),
                     "expect_low": lo, "expect_high": hi}
        print(f"  ok {sid:16s} -> {col:34s} {len(monthly):3d} months  "
              f"({fq}, {method})")

    if not data:
        sys.exit("nothing retrieved -- check network and try --dry-run")

    allm = sorted({m for d in data.values() for m in d})
    months = month_range(allm[0], allm[-1])
    cols = [c for _, c, _, _, _ in SERIES if c in data]

    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["month"] + cols)
        for m in months:
            w.writerow([m] + [
                ("" if m not in data[c] else round(data[c][m], 4)) for c in cols])
    print(f"\n-> {args.out}  ({len(months)} months x {len(cols)} series)")

    with open(args.tidy_out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "month", "column", "value", "series_id", "group", "native_freq",
            "aggregation", "url"])
        w.writeheader()
        for c in cols:
            for m in months:
                if m in data[c]:
                    w.writerow({"month": m, "column": c,
                                "value": round(data[c][m], 4),
                                **{k: meta[c][k] for k in
                                   ("series_id", "group", "native_freq",
                                    "aggregation", "url")}})
    print(f"-> {args.tidy_out}")

    with open("macro-metadata.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["column"] + list(
            next(iter(meta.values())).keys()))
        w.writeheader()
        for c, mv in meta.items():
            w.writerow({"column": c, **mv})
    print("-> macro-metadata.csv")

    # ---- coverage report
    print("\ncoverage (months with a value, out of "
          f"{len(months)} in range {months[0]}..{months[-1]}):")
    for c in cols:
        n = sum(1 for m in months if m in data[c])
        fq = meta[c]["native_freq"]
        note = "" if fq != "Q" else "  <- quarterly, intra-quarter blank by design"
        bar = "#" * int(round(n / len(months) * 28))
        print(f"  {c:34s} {n:3d}/{len(months)} {bar}{note}")

    if problems:
        print("\nPROBLEMS -- resolve before using:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(2)
    print("\nAll series within expected ranges.")


if __name__ == "__main__":
    main()
