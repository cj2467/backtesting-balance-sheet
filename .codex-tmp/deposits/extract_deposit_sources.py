#!/usr/bin/env python3
import csv
import json
import re
import runpy
from pathlib import Path


ROOT = Path("/Users/cjwork/holodeck-archive")
PARSER = runpy.run_path(str(ROOT / "parse-nii-tables.py"))
extract_tables = PARSER["extract_tables"]
caption_of = PARSER["caption_of"]
nums_in_row = PARSER["nums_in_row"]
label_of = PARSER["label_of"]


PRODUCT_LABELS = {
    "interest-bearing checking accounts": "Checking",
    "saving deposits": "Savings",
    "time deposits": "Time deposits",
    "total interest-bearing deposits": "Total interest-bearing deposits",
}


def years_from_grid(grid):
    for row in grid[:7]:
        years = [int(c) for c in row if re.fullmatch(r"20\d{2}", (c or "").strip())]
        if len(years) >= 2:
            return years
    return []


def normalize_label(label):
    return re.sub(r"\(\d+\)", "", label).strip().lower()


def find_table(path, span_text, required_text):
    matches = []
    for grid in extract_tables(str(path)):
        caption = caption_of(grid, 7)
        body = " ".join(" ".join(row) for row in grid)
        if span_text.lower() in caption.lower() and required_text.lower() in body.lower():
            matches.append(grid)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {span_text!r}/{required_text!r} table in {path.name}; found {len(matches)}")
    return matches[0]


def parse_product_table(path, span_text, target_year):
    grid = find_table(path, span_text, "Interest-bearing checking accounts")
    years = years_from_grid(grid)
    if target_year not in years:
        raise RuntimeError(f"Year {target_year} not found in deposit table {path.name}")
    year_index = years.index(target_year)
    out = {}
    for row in grid:
        key = normalize_label(label_of(row))
        if key not in PRODUCT_LABELS:
            continue
        values = nums_in_row(row)
        if len(values) != 3 * len(years):
            raise RuntimeError(f"Unexpected numeric count in {path.name}: {label_of(row)} -> {values}")
        balance, interest, rate_pct = values[year_index * 3: year_index * 3 + 3]
        out[PRODUCT_LABELS[key]] = {
            "avg_balance_mm": balance,
            "interest_expense_mm": interest,
            "reported_rate": rate_pct / 100.0,
        }
    if set(out) != set(PRODUCT_LABELS.values()):
        raise RuntimeError(f"Missing product rows in {path.name}: {sorted(set(PRODUCT_LABELS.values()) - set(out))}")
    return out


def parse_noninterest_average(path, span_text, target_year):
    grid = find_table(path, span_text, "Total interest-earning assets")
    years = years_from_grid(grid)
    if target_year not in years:
        raise RuntimeError(f"Year {target_year} not found in average-balance table {path.name}")
    year_index = years.index(target_year)
    for row in grid:
        if normalize_label(label_of(row)) == "non-interest-bearing deposits":
            values = nums_in_row(row)
            if len(values) != len(years):
                raise RuntimeError(f"Unexpected non-interest-bearing row in {path.name}: {values}")
            return values[year_index]
    raise RuntimeError(f"Non-interest-bearing deposits row not found in {path.name}")


def quarter_row(year, quarter, products, noninterest, source_files, method):
    rows = []
    for category in ["Checking", "Savings", "Time deposits", "Total interest-bearing deposits"]:
        item = products[category]
        rows.append({
            "period": f"{year}Q{quarter}",
            "year": year,
            "quarter": quarter,
            "deposit_type": category,
            **item,
            "effective_rate": item["interest_expense_mm"] * 4.0 / item["avg_balance_mm"],
            "source_files": source_files,
            "method": method,
        })
    rows.append({
        "period": f"{year}Q{quarter}",
        "year": year,
        "quarter": quarter,
        "deposit_type": "Non-interest-bearing deposits",
        "avg_balance_mm": noninterest,
        "interest_expense_mm": 0.0,
        "reported_rate": 0.0,
        "effective_rate": 0.0,
        "source_files": source_files,
        "method": method,
    })
    return rows


quarterly = []
quarter_map = {}

for year in (2024, 2025):
    for quarter in (1, 2, 3):
        path = ROOT / "filings" / f"capitalone-10q-{year}q{quarter}.htm"
        span_text = {1: "Three Months Ended March 31", 2: "Three Months Ended June 30", 3: "Three Months Ended September 30"}[quarter]
        products = parse_product_table(path, span_text, year)
        noninterest = parse_noninterest_average(path, span_text, year)
        rows = quarter_row(year, quarter, products, noninterest, path.name, "Reported three-month average")
        quarterly.extend(rows)
        quarter_map[(year, quarter)] = {r["deposit_type"]: r for r in rows}

    annual_path = ROOT / "filings" / f"capitalone-10k-fy{year}.htm"
    q3_path = ROOT / "filings" / f"capitalone-10q-{year}q3.htm"
    annual_products = parse_product_table(annual_path, "Year Ended December 31", year)
    nine_month_products = parse_product_table(q3_path, "Nine Months Ended September 30", year)
    annual_noninterest = parse_noninterest_average(annual_path, "Year Ended December 31", year)
    nine_month_noninterest = parse_noninterest_average(q3_path, "Nine Months Ended September 30", year)
    q4_products = {}
    for category in PRODUCT_LABELS.values():
        annual = annual_products[category]
        nine = nine_month_products[category]
        balance = (annual["avg_balance_mm"] * 12.0 - nine["avg_balance_mm"] * 9.0) / 3.0
        interest = annual["interest_expense_mm"] - nine["interest_expense_mm"]
        q4_products[category] = {
            "avg_balance_mm": balance,
            "interest_expense_mm": interest,
            "reported_rate": interest * 4.0 / balance,
        }
    q4_noninterest = (annual_noninterest * 12.0 - nine_month_noninterest * 9.0) / 3.0
    source_files = f"{annual_path.name}; {q3_path.name}"
    rows = quarter_row(year, 4, q4_products, q4_noninterest, source_files, "Derived Q4 = full year less nine months")
    quarterly.extend(rows)
    quarter_map[(year, 4)] = {r["deposit_type"]: r for r in rows}

for year, quarter in ((2026, 1), (2026, 2)):
    path = ROOT / "filings" / f"capitalone-10q-{year}q{quarter}.htm"
    span_text = {1: "Three Months Ended March 31", 2: "Three Months Ended June 30"}[quarter]
    products = parse_product_table(path, span_text, year)
    noninterest = parse_noninterest_average(path, span_text, year)
    rows = quarter_row(year, quarter, products, noninterest, path.name, "Reported three-month average")
    quarterly.extend(rows)
    quarter_map[(year, quarter)] = {r["deposit_type"]: r for r in rows}


anchors = []
with open(ROOT / "anchors.csv", newline="") as handle:
    for row in csv.DictReader(handle):
        if row["concept"] != "deposits_noninterest":
            continue
        date = row["period_end"]
        if "2023-12-31" <= date <= "2026-06-30":
            anchors.append({
                "period_end": date,
                "eop_balance_mm": float(row["value_usd"]) / 1_000_000.0,
                "source_file": row["accession"],
                "source_form": row["form"],
            })


checks = []
for year, quarter in sorted(quarter_map):
    items = quarter_map[(year, quarter)]
    balance_sum = sum(items[name]["avg_balance_mm"] for name in ("Checking", "Savings", "Time deposits"))
    interest_sum = sum(items[name]["interest_expense_mm"] for name in ("Checking", "Savings", "Time deposits"))
    total = items["Total interest-bearing deposits"]
    checks.append({
        "period": f"{year}Q{quarter}",
        "balance_difference_mm": balance_sum - total["avg_balance_mm"],
        "interest_difference_mm": interest_sum - total["interest_expense_mm"],
    })


output = {
    "quarterly": quarterly,
    "noninterest_eop_anchors": anchors,
    "source_checks": checks,
}
output_path = ROOT / ".codex-tmp" / "deposits" / "deposit_sources.json"
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(output, indent=2) + "\n")
print(output_path)
print(json.dumps(checks, indent=2))
