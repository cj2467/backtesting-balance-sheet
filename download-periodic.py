#!/usr/bin/env python3
"""
Download every 10-K / 10-Q for a filer since a given period, discovered from
EDGAR rather than hardcoded.

    export SEC_UA="CJ cjbox21@gmail.com"
    python3 download-periodic.py --since 2024-12-01              # Capital One
    python3 download-periodic.py --since 2024-12-01 --filer schw
    python3 download-periodic.py --since 2024-12-01 --filer all

Run from your own machine -- Cowork's network can't reach sec.gov.

Why this exists: the balance sheet at 2025-03-31, 2025-06-30 and 2025-09-30 is
not recoverable from the FY2025 10-K plus the 2026 10-Qs. A 10-Q balance sheet
shows only the current quarter-end and the prior year-end, so those three dates
appear nowhere. 2025-09-30 has zero tagged facts in the files on hand. They come
from the 2025 10-Qs, which this fetches.

Files are named to match what extract-local-anchors.py expects:
    capitalone-10q-2025q1.htm, capitalone-10k-fy2024.htm, ...
"""
import argparse, json, os, sys, time, urllib.error, urllib.request

UA = os.environ.get("SEC_UA", "CJ cjbox21@gmail.com")

FILERS = {
    "cof":  ("927628",  "capitalone"),
    "schw": ("316709",  "schwab"),
}


def get(url, tries=3):
    # No Accept-Encoding unless we decompress it -- that bug cost us a run
    # already. Decompress defensively in case something gzips anyway.
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                if (r.headers.get("Content-Encoding", "").lower() == "gzip"
                        or body[:2] == b"\x1f\x8b"):
                    import gzip
                    body = gzip.decompress(body)
                return body
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < tries - 1:
                time.sleep(2 ** attempt); continue
            raise
        finally:
            time.sleep(0.2)
    raise RuntimeError("unreachable")


def label(form, report_date):
    """10-Q + 2025-03-31 -> 10q-2025q1 ; 10-K + 2024-12-31 -> 10k-fy2024"""
    y, m = int(report_date[:4]), int(report_date[5:7])
    if form == "10-K":
        return f"10k-fy{y}"
    return f"10q-{y}q{(m - 1) // 3 + 1}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2024-12-01",
                    help="earliest period-of-report to fetch (YYYY-MM-DD)")
    ap.add_argument("--filer", default="cof", choices=["cof", "schw", "all"])
    ap.add_argument("--dir", default="filings")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if UA.startswith("Your Name"):
        sys.exit("Set SEC_UA to your name and email first.")

    targets = ["cof", "schw"] if args.filer == "all" else [args.filer]
    os.makedirs(args.dir, exist_ok=True)
    got, failed = [], []

    for key in targets:
        cik, prefix = FILERS[key]
        print(f"\n[{key}] CIK {cik} -- submissions index")
        try:
            subs = json.loads(get(
                f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))
        except Exception as e:
            print(f"  !!! submissions index FAILED: {type(e).__name__}: {e}",
                  file=sys.stderr)
            failed.append(f"{key}: submissions index")
            continue

        rec = subs["filings"]["recent"]
        rows = list(zip(rec["form"], rec["accessionNumber"], rec["reportDate"],
                        rec["primaryDocument"], rec["filingDate"]))
        want = [r for r in rows
                if r[0] in ("10-K", "10-Q") and r[2] and r[2] >= args.since]
        want.sort(key=lambda r: r[2])

        if not want:
            print(f"  no 10-K/10-Q with period >= {args.since}")
            continue
        print(f"  {len(want)} periodic filings since {args.since}:")

        for form, acc, rpt, prim, filed in want:
            nod = acc.replace("-", "")
            ext = os.path.splitext(prim)[1] or ".htm"
            out = os.path.join(args.dir, f"{prefix}-{label(form, rpt)}{ext}")
            url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/{nod}/{prim}")
            tag = f"{form} period {rpt} filed {filed}"

            if os.path.exists(out) and os.path.getsize(out) > 0:
                print(f"    = {os.path.basename(out):34s} {tag}  (cached)")
                got.append(out); continue
            if args.dry_run:
                print(f"    ? {os.path.basename(out):34s} {tag}\n        {url}")
                continue
            try:
                body = get(url)
            except Exception as e:
                print(f"    ! {os.path.basename(out):34s} FAILED: {e}",
                      file=sys.stderr)
                failed.append(f"{key} {form} {rpt}")
                continue
            with open(out, "wb") as fh:
                fh.write(body)
            print(f"    + {os.path.basename(out):34s} {tag}  "
                  f"({len(body)/1e6:.1f} MB)")
            got.append(out)

    print(f"\n{len(got)} file(s) available in {args.dir}/")
    if failed:
        print("FAILURES:", file=sys.stderr)
        for f in failed:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(2)
    if not got and not args.dry_run:
        print("!!! nothing retrieved -- do not treat this run as successful",
              file=sys.stderr)
        sys.exit(3)
    print("\nNext:  python3 extract-local-anchors.py && python3 make-balance-sheet.py")


if __name__ == "__main__":
    main()
