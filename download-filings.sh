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
mkdir -p filings
pushd filings >/dev/null

echo "== 10-K / 10-Q =="
fetch schwab-10k-fy2025.htm      "$BASE/316709/000031670926000009/schw-20251231.htm" || true
fetch schwab-10q-q1-2026.htm     "$BASE/316709/000031670926000019/schw-20260331.htm" || true
fetch schwab-10q-q2-2026.htm     "$BASE/316709/000031670926000031/schw-20260630.htm" || true
fetch capitalone-10k-fy2025.htm  "$BASE/927628/000092762826000024/cof-20251231.htm" || true
fetch capitalone-10q-q1-2026.htm "$BASE/927628/000092762826000048/cof-20260331.htm" || true
fetch capitalone-10q-q2-2026.htm "$BASE/927628/000092762826000089/cof-20260630.htm" || true

popd >/dev/null

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
CIK         = "927628"
OUTDIR      = "filings/credit-metrics"

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January","February","March","April","May","June",
     "July","August","September","October","November","December"], start=1)}

def get(url, tries=3):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Encoding": "gzip, deflate", "Host": url.split("/")[2]})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < tries - 1:
                time.sleep(2 ** attempt); continue
            raise
        finally:
            time.sleep(0.15)   # stay well under SEC's 10 req/sec

def period_from_name(name):
    """ex991february2026creditmet.htm -> (2026, 2)"""
    m = re.search(r"(" + "|".join(MONTHS) + r")\s*(\d{4})", name, re.I)
    if m:
        return int(m.group(2)), MONTHS[m.group(1).lower()]
    return None

os.makedirs(OUTDIR, exist_ok=True)
cutoff = dt.date.today() - dt.timedelta(days=int(MONTHS_BACK * 30.5))

print("   fetching submissions index...")
subs = json.loads(get(f"https://data.sec.gov/submissions/CIK{int(CIK):010d}.json"))
rec  = subs["filings"]["recent"]
rows = list(zip(rec["form"], rec["accessionNumber"], rec["filingDate"]))
eights = [(a, d) for f, a, d in rows
          if f == "8-K" and dt.date.fromisoformat(d) >= cutoff]

print(f"   {len(eights)} 8-K filings since {cutoff}; scanning for credit metrics exhibits")

found, manifest = 0, []
for acc, filed in eights:
    nod = acc.replace("-", "")
    try:
        idx = json.loads(get(f"https://www.sec.gov/Archives/edgar/data/{CIK}/{nod}/index.json"))
    except Exception as e:
        print(f"   ! index failed {acc}: {e}", file=sys.stderr); continue

    for item in idx.get("directory", {}).get("item", []):
        name = item.get("name", "")
        if not re.search(r"creditmet", name, re.I):
            continue
        per = period_from_name(name)
        label = f"{per[0]}-{per[1]:02d}" if per else f"filed{filed}"
        out = os.path.join(OUTDIR, f"cof-credit-metrics-{label}.htm")
        url = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{nod}/{name}"
        if os.path.exists(out):
            print(f"   = {os.path.basename(out)} (cached)")
        else:
            try:
                open(out, "wb").write(get(url))
                print(f"   + {os.path.basename(out)}")
            except Exception as e:
                print(f"   ! download failed {name}: {e}", file=sys.stderr); continue
        found += 1
        manifest.append({"period": label, "filed": filed,
                         "accession": acc, "file": out, "url": url})

manifest.sort(key=lambda r: r["period"])
with open(os.path.join(OUTDIR, "manifest.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["period", "filed", "accession", "file", "url"])
    w.writeheader(); w.writerows(manifest)

print(f"\n   {found} credit-metrics exhibits -> {OUTDIR}/")
print(f"   manifest: {OUTDIR}/manifest.csv")
if manifest:
    print(f"   coverage: {manifest[0]['period']} .. {manifest[-1]['period']}")
gaps = len({m["period"] for m in manifest})
if gaps < MONTHS_BACK * 0.8:
    print("   NOTE: fewer months than expected -- check for gaps before building a series.")
PYEOF

echo
echo "Done."
find filings -type f | sort
