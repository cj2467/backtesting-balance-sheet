import csv
from collections import Counter, defaultdict
from pathlib import Path

root = Path("/Users/cjwork/holodeck-archive")

with (root / "credit-metrics-tidy.csv").open(newline="", encoding="utf-8-sig") as f:
    tidy = list(csv.DictReader(f))

print("TIDY_COLUMNS", list(tidy[0]))
print("TIDY_ROWS", len(tidy))
print("FILERS", sorted(Counter(r["filer"] for r in tidy).items()))
print("SEGMENTS_BY_FILER")
for filer in sorted({r["filer"] for r in tidy}):
    print(filer, sorted({r["segment"] for r in tidy if r["filer"] == filer}))
print("PERIODS_BY_FILER")
for filer in sorted({r["filer"] for r in tidy}):
    periods = sorted({r["period"] for r in tidy if r["filer"] == filer})
    print(filer, len(periods), periods[0], periods[-1], periods)
print("METRICS_BY_COF_SEGMENT")
for seg in sorted({r["segment"] for r in tidy if r["filer"] == "cof"}):
    metrics = sorted({r["metric"] for r in tidy if r["filer"] == "cof" and r["segment"] == seg})
    print(seg, metrics)

print("COF_CARD_ROWS")
for r in tidy:
    if r["filer"] == "cof" and "card" in r["segment"]:
        print(r)

with (root / "monthly-pl-cof.csv").open(newline="", encoding="utf-8-sig") as f:
    pl = list(csv.DictReader(f))
print("MONTHLY_PL_COLUMNS", list(pl[0]))
print("MONTHLY_PL_PERIODS", [r["period"] for r in pl])
print("MONTHLY_PL_ROWS")
for r in pl:
    print(r)

with (root / "macro forecast.csv").open(newline="", encoding="utf-8-sig") as f:
    macro = list(csv.reader(f))
print("MACRO_CARD_ROWS")
for row in macro:
    if row and row[0] in {"cc_chargeoff_rate_banks", "cc_delinq_rate_banks"}:
        print(row)

with (root / "credit-metrics-raw.csv").open(newline="", encoding="utf-8-sig") as f:
    raw = list(csv.DictReader(f))
print("RAW_COLUMNS", list(raw[0]))
print("RAW_ROWS", len(raw))
print("RAW_FILERS", sorted(Counter(r["filer"] for r in raw).items()))
print("RAW_COF_FILES", sorted({r["file"] for r in raw if r["filer"] == "cof"}))
print("RAW_SEGMENT_LABELS")
labels = []
for r in raw:
    text = r["text"].strip()
    if any(term in text.lower() for term in ["domestic card", "credit card", "discover"]):
        labels.append((r["file_period"], r["table"], r["row"], r["col"], text))
for item in labels[:100]:
    print(item)
