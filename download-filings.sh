#!/usr/bin/env bash
# Downloads Schwab & Capital One filings + Capital One monthly credit metrics 8-Ks.
# Run from your own terminal (not inside Cowork -- Cowork's network blocks sec.gov).
#
#   chmod +x download-filings.sh && ./download-filings.sh
#
# Env knobs:
#   SEC_UA       User-Agent contact string (SEC requires a real one)
#   MONTHS_BACK  How far back to pull monthly 8-Ks (default 24)
#   SKIP_8K=1    Only fetch the periodic reports
#
UA="${SEC_UA:-CJ cjbox21@gmail.com}"
MONTHS_BACK="${MONTHS_BACK:-24}"

set -euo pipefail

command -v python3 >/dev/null || { echo "python3 required for 8-K discovery"; exit 1; }

BASE="https://www.sec.gov/Archives/edgar/data"

fetch() {
  local out="$1" url="$2"
  echo "--> $out"
  if ! curl -sS --fail -A "$UA" -o "$out" "$url"; then
    echo "    FAILED: $url" >&2
    return 1
  fi
  sleep 0.3
}

# ---------------------------------------------------------------- periodic
# NOT DONE HERE ANY MORE.
#
# This script used to fetch the 10-K/10-Q with hardcoded URLs and hardcoded
# filenames (capitalone-10q-q1-2026.htm), while download-periodic.py derives
# names from the reporting period (capitalone-10q-2026q1.htm). Running both
# therefore downloaded every periodic filing twice under two names -- ~29 MB
# of byte-identical duplicates.
#
# download-periodic.py is now the single source of truth for periodic filings:
# it discovers them from EDGAR rather than relying on accession numbers I'd
# have to hardcode, and there is exactly one naming convention.
mkdir -p filings

echo "== 10-K / 10-Q =="
echo "   skipped -- use download-periodic.py (one naming convention, no dupes):"
echo "     python3 download-periodic.py --since 2024-06-01 --filer all"

# ------------------------------------------------- monthly credit metrics
# Accession numbers for the monthly 8-Ks can't be guessed, so we walk
# EDGAR's submissions index for CIK 927628, look at each 8-K's file list,
# and grab any exhibit whose name matches /creditmet/.
if [[ "${SKIP_8K:-0}" == "1" ]]; then
  echo "SKIP_8K set -- done."
  exit 0
fi

echo
echo "== Capital One monthly credit metrics 8-Ks (last ${MONTHS_BACK} months) =="

MONTHS_BACK="$MONTHS_BACK" SEC_UA="$UA" python3 - <<'PYEOF'
import csv, datetime as dt, json, os, re, sys, time, urllib.error, urllib.request

UA          = os.environ["SEC_UA"]
MONTHS_BACK = int(os.environ["MONTHS_BACK"])
OUTDIR      = "filings/credit-metrics"

# Capital One, plus Discover for the pre-close period. Discover's last monthly
# exhibit covered April 2025 (merger closed 2025-05-18); after that the Discover
# portfolio appears as its own line inside Capital One's exhibit.
#
# NOTE: Discover's monthly exhibit reported RATES ONLY (net principal charge-off
# rate, 30+ day delinquency rate) on a rolling 24-month basis -- no period-end
# dollar balances. Don't expect to splice dollars from these.
FILERS = [
    ("927628",  "cof",      r"creditmet"),
    # Discover named theirs exhibit991<MM>-<DD>x<YY>.htm, e.g. exhibit99105-31x24.htm.
    # Keep this tight or you'll pull every other 99.1 they ever furnished.
    ("1393612", "discover", r"exhibit991\d{2}-\d{2}x\d{2}"),
]

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January","February","March","April","May","June",
     "July","August","September","October","November","December"], start=1)}

def get(url, tries=3):
    # Do NOT advertise gzip unless you decompress it. An earlier version sent
    # "Accept-Encoding: gzip" and then fed raw bytes to json.loads, which threw
    # UnicodeDecodeError, got swallowed, and produced an empty manifest with a
    # zero exit code. Decompress defensively in case a proxy gzips anyway.
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
                if r.headers.get("Content-Encoding", "").lower() == "gzip" or body[:2] == b"\x1f\x8b":
                    import gzip as _gz
                    body = _gz.decompress(body)
                return body
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < tries - 1:
                time.sleep(2 ** attempt); continue
            raise
        finally:
            time.sleep(0.15)   # stay well under SEC's 10 req/sec

def period_from_name(name):
    """Both naming conventions -> (year, month), or None.

    ex991february2026creditmet.htm -> (2026, 2)     [Capital One]
    exhibit99105-31x24.htm         -> (2024, 5)     [Discover]
    """
    m = re.search(r"(" + "|".join(MONTHS) + r")\s*(\d{4})", name, re.I)
    if m:
        return int(m.group(2)), MONTHS[m.group(1).lower()]
    m = re.search(r"exhibit991(\d{2})-\d{2}x(\d{2})", name, re.I)
    if m:
        return 2000 + int(m.group(2)), int(m.group(1))
    return None

os.makedirs(OUTDIR, exist_ok=True)
cutoff = dt.date.today() - dt.timedelta(days=int(MONTHS_BACK * 30.5))

found, manifest, errors = 0, [], []

for cik, tag, pattern in FILERS:
    print(f"\n   [{tag}] CIK {cik} -- fetching submissions index...")
    try:
        subs = json.loads(get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))
    except Exception as e:
        # Loud, not swallowed -- this is the failure that produced an empty
        # manifest once already.
        print(f"\n   !!! submissions index FAILED for {tag}: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        errors.append(f"{tag}: submissions index ({type(e).__name__})")
        continue

    rec  = subs["filings"]["recent"]
    rows = list(zip(rec["form"], rec["accessionNumber"], rec["filingDate"]))
    eights = [(a, d) for f, a, d in rows
              if f == "8-K" and dt.date.fromisoformat(d) >= cutoff]
    print(f"   [{tag}] {len(eights)} 8-Ks since {cutoff}; scanning exhibits")

    if not eights and tag == "discover":
        print("   [discover] nothing in range -- their last monthly exhibit was "
              "April 2025, so increase MONTHS_BACK to reach it.")

    hits = 0
    for acc, filed in eights:
        nod = acc.replace("-", "")
        try:
            idx = json.loads(get(
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{nod}/index.json"))
        except Exception as e:
            print(f"   ! index failed {acc}: {e}", file=sys.stderr); continue

        for item in idx.get("directory", {}).get("item", []):
            name = item.get("name", "")
            if not re.search(pattern, name, re.I):
                continue
            per   = period_from_name(name)
            label = f"{per[0]}-{per[1]:02d}" if per else f"filed{filed}"
            out   = os.path.join(OUTDIR, f"{tag}-credit-metrics-{label}.htm")
            url   = f"https://www.sec.gov/Archives/edgar/data/{cik}/{nod}/{name}"
            if os.path.exists(out):
                print(f"   = {os.path.basename(out)} (cached)")
            else:
                try:
                    open(out, "wb").write(get(url))
                    print(f"   + {os.path.basename(out)}")
                except Exception as e:
                    print(f"   ! download failed {name}: {e}", file=sys.stderr); continue
            found += 1; hits += 1
            manifest.append({"filer": tag, "period": label, "filed": filed,
                             "accession": acc, "file": out, "url": url})

    print(f"   [{tag}] {hits} exhibits matched")

manifest.sort(key=lambda r: (r["filer"], r["period"]))
with open(os.path.join(OUTDIR, "manifest.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["filer", "period", "filed", "accession", "file", "url"])
    w.writeheader(); w.writerows(manifest)

print(f"\n   {found} credit-metrics exhibits -> {OUTDIR}/")
print(f"   manifest: {OUTDIR}/manifest.csv")

# Coverage / gap report per filer -- worth reading before you build any series.
for cik, tag, _ in FILERS:
    periods = sorted({m["period"] for m in manifest
                      if m["filer"] == tag and re.fullmatch(r"\d{4}-\d{2}", m["period"])})
    if not periods:
        print(f"   [{tag}] no dated exhibits found")
        continue
    print(f"   [{tag}] {len(periods)} months: {periods[0]} .. {periods[-1]}")
    # enumerate calendar months in range and report any missing
    y0, m0 = map(int, periods[0].split("-"))
    y1, m1 = map(int, periods[-1].split("-"))
    want, y, m = [], y0, m0
    while (y, m) <= (y1, m1):
        want.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    missing = [p for p in want if p not in periods]
    if missing:
        print(f"   [{tag}] MISSING {len(missing)}: {', '.join(missing)}")

# Zero exhibits is a failure, not a quiet success. Exit non-zero so it can't
# slide past unnoticed the way it did before.
if errors:
    print("\n   ERRORS:", file=sys.stderr)
    for e in errors:
        print(f"     - {e}", file=sys.stderr)
if found == 0:
    print("\n   !!! NO credit-metrics exhibits retrieved. The manifest is empty. "
          "Check the errors above; do not treat this run as successful.",
          file=sys.stderr)
    sys.exit(3)
PYEOF

echo
echo "Done."
find filings -type f | sort
