#!/usr/bin/env python3
"""
Extract income-statement flows (net interest income and friends) from the
downloaded 10-K/10-Q files. Offline. Companion to extract-local-anchors.py,
which handles instants; this handles durations.

    python3 extract-local-flows.py                  # -> flows.csv
    python3 extract-local-flows.py --list-tags

THE Q4 PROBLEM, which shapes everything here.

A balance sheet is an instant, so every quarter-end is directly reported. An
income statement is a duration, and issuers report:

    Q1 10-Q  ->  3 months
    Q2 10-Q  ->  3 months and 6 months
    Q3 10-Q  ->  3 months and 9 months
    10-K     ->  12 months ONLY

There is no 3-month Q4 figure anywhere in the filings. Verified on Capital
One's FY2025 10-K: 719 consolidated duration facts at 12 months, none at 3
for the income statement. So Q4 must be derived:

    Q4 = FY(12M) - 9M(from the Q3 10-Q)

That subtraction is exact -- it's not an estimate -- but it depends on having
the Q3 10-Q, and it inherits any restatement between the two filings. Derived
rows are flagged `derived=Q4=FY-9M` in the output. Nothing else is computed.
"""
import argparse, csv, datetime as dt, glob, html, os, re, sys
from collections import defaultdict

# Concepts we care about for a net interest income presentation.
CONCEPTS = {
    "int_inc_loans":       ["InterestAndFeeIncomeLoansAndLeases"],
    "int_inc_securities":  ["InterestAndDividendIncomeSecurities"],
    "int_inc_other":       ["OtherInterestAndDividendIncome"],
    "int_inc_total":       ["InterestAndDividendIncomeOperating"],
    "int_exp_deposits":    ["InterestExpenseDeposits"],
    "int_exp_secured":     ["InterestExpenseSecuredDebt"],
    "int_exp_unsecured":   ["InterestExpenseUnsecuredDebt"],
    "int_exp_other":       ["InterestExpenseOtherBorrowings"],
    "int_exp_total":       ["InterestExpenseOperating"],
    "net_interest_income": ["InterestIncomeExpenseNet"],
    "nii_after_provision": ["InterestIncomeExpenseAfterProvisionForLoanLoss"],
    "noninterest_income":  ["NoninterestIncome"],
    "noninterest_expense": ["NoninterestExpense"],
    "pretax_income":       ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
    "net_income":          ["NetIncomeLoss"],
}
TAG_TO_CONCEPT = {t: c for c, ts in CONCEPTS.items() for t in ts}

FILER_BY_PREFIX = {"capitalone": "cof", "schwab": "schw", "discover": "discover"}

CTX = re.compile(
    r'<xbrli:context[^>]*\bid="(?P<id>[^"]+)"(?P<body>.*?)</xbrli:context>',
    re.I | re.S)
CTX_ALT = re.compile(
    r'<context[^>]*\bid="(?P<id>[^"]+)"(?P<body>.*?)</context>', re.I | re.S)
SD  = re.compile(r'<(?:xbrli:)?startDate>\s*([0-9]{4}-[0-9]{2}-[0-9]{2})', re.I)
ED  = re.compile(r'<(?:xbrli:)?endDate>\s*([0-9]{4}-[0-9]{2}-[0-9]{2})', re.I)
DIM = re.compile(r'explicitMember|typedMember', re.I)
FACT = re.compile(r'<ix:nonfraction(?P<attrs>[^>]*)>(?P<inner>.*?)</ix:nonfraction>',
                  re.I | re.S)
ATTR = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')


def parse_contexts(text):
    """id -> (start, end, months, has_dims) for duration contexts only."""
    out = {}
    for rx in (CTX, CTX_ALT):
        for m in rx.finditer(text):
            cid, body = m.group("id"), m.group("body")
            if cid in out:
                continue
            s, e = SD.search(body), ED.search(body)
            if not (s and e):
                continue
            d = (dt.date.fromisoformat(e.group(1))
                 - dt.date.fromisoformat(s.group(1))).days
            months = round(d / 30.4)
            out[cid] = (s.group(1), e.group(1), months, bool(DIM.search(body)))
        if out:
            break
    return out


def clean_value(inner, attrs):
    txt = re.sub(r"<[^>]+>", "", inner)
    txt = html.unescape(txt).replace("\xa0", " ").strip()
    txt = txt.replace(",", "").replace("$", "").strip()
    if txt in ("", "—", "–", "-"):
        return None
    neg = False
    if txt.startswith("(") and txt.endswith(")"):
        neg, txt = True, txt[1:-1].strip()
    if not re.fullmatch(r"-?\d*\.?\d+", txt):
        return None
    v = float(txt)
    try:
        v *= 10 ** int(attrs.get("scale", "0") or 0)
    except ValueError:
        pass
    if attrs.get("sign") == "-":
        v = -v
    if neg:
        v = -v
    return v


def filer_of(path):
    b = os.path.basename(path).lower()
    for pre, f in FILER_BY_PREFIX.items():
        if b.startswith(pre):
            return f
    return "unknown"


def form_of(path):
    b = os.path.basename(path).lower()
    return "10-K" if "10k" in b else ("10-Q" if "10q" in b else "")


def quarter_of(end):
    y, m = int(end[:4]), int(end[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="filings")
    ap.add_argument("--out", default="flows.csv")
    ap.add_argument("--filer", default="cof")
    ap.add_argument("--list-tags", action="store_true")
    args = ap.parse_args()

    files = [p for p in sorted(glob.glob(os.path.join(args.dir, "*.htm*")))
             if form_of(p)]
    if not files:
        sys.exit(f"no 10-K/10-Q in {args.dir}/")

    import hashlib
    seen, seen_tags = {}, defaultdict(int)
    # (filer, concept, months, end) -> (value, form, src)
    facts = {}

    for path in files:
        raw = open(path, "rb").read()
        h = hashlib.sha256(raw).hexdigest()
        if h in seen:
            print(f"{os.path.basename(path):32s} duplicate -- skipped")
            continue
        seen[h] = path
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc); break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", "replace")

        ctx = parse_contexts(text)
        filer, form = filer_of(path), form_of(path)
        kept = 0
        buckets = defaultdict(int)

        for m in FACT.finditer(text):
            attrs = dict(ATTR.findall(m.group("attrs")))
            name = (attrs.get("name") or "").strip()
            if ":" not in name:
                continue
            ns, tag = name.split(":", 1)
            # Accept company extension tags, not just us-gaap. Capital One
            # tags securitized and unsecured debt interest as cof:... even
            # though the local names look standard. Filtering on the us-gaap
            # prefix silently dropped the entire interest expense breakdown.
            # The namespace is recorded so extension-sourced lines stay visible:
            # they're issuer-defined and not comparable across filers.
            if ns.lower() not in ("us-gaap", "cof", "schw"):
                continue
            cref = attrs.get("contextref") or attrs.get("contextRef")
            c = ctx.get(cref or "")
            if not c:
                continue
            start, end, months, has_dims = c
            if has_dims:
                continue
            buckets[months] += 1
            seen_tags[(f"{ns}:{tag}", months)] += 1
            concept = TAG_TO_CONCEPT.get(tag)
            if not concept:
                continue
            v = clean_value(m.group("inner"), attrs)
            if v is None:
                continue
            key = (filer, concept, months, end)
            if key not in facts:
                facts[key] = (v, form, os.path.basename(path), start, ns)
                kept += 1

        print(f"{os.path.basename(path):32s} {filer:9s} {form:5s} "
              f"durations={dict(sorted(buckets.items()))} kept={kept}")

    if args.list_tags:
        print("\nus-gaap duration tags (tag, months) -> count:")
        for (tag, mo), n in sorted(seen_tags.items(), key=lambda kv: -kv[1])[:70]:
            mark = "*" if tag in TAG_TO_CONCEPT else " "
            print(f"  {mark} {n:5d}  {mo:3d}mo  {tag}")
        return

    rows = []
    for (filer, concept, months, end), (v, form, src, start, ns) in facts.items():
        if filer != args.filer:
            continue
        rows.append({"filer": filer, "concept": concept, "months": months,
                     "period_start": start, "period_end": end,
                     "quarter": quarter_of(end) if months == 3 else "",
                     "value_usd": v, "namespace": ns, "form": form,
                     "source": src, "derived": ""})

    # ---- derive Q4 = FY(12M) - 9M(same fiscal year)
    idx = {(r["concept"], r["months"], r["period_end"]): r for r in rows}
    derived = 0
    for concept in CONCEPTS:
        for r in [x for x in rows if x["concept"] == concept and x["months"] == 12]:
            y = int(r["period_end"][:4])
            nine = idx.get((concept, 9, f"{y}-09-30"))
            if not nine:
                continue
            q4 = r["value_usd"] - nine["value_usd"]
            key = (concept, 3, f"{y}-12-31")
            if key in idx:
                continue            # already reported, don't overwrite
            rows.append({"filer": args.filer, "concept": concept, "months": 3,
                         "period_start": f"{y}-10-01", "period_end": f"{y}-12-31",
                         "quarter": f"{y}Q4", "value_usd": q4,
                         "form": "derived", "source": f"{r['source']} - {nine['source']}",
                         "derived": "Q4=FY-9M"})
            derived += 1

    if not rows:
        sys.exit(f"no flow facts for filer={args.filer}")

    rows.sort(key=lambda r: (r["concept"], r["months"], r["period_end"]))
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"\n{len(rows)} flow facts -> {args.out}  ({derived} derived Q4)")

    # ---- what quarters do we actually have for NII?
    q3 = sorted({r["quarter"] for r in rows
                 if r["months"] == 3 and r["concept"] == "net_interest_income"})
    print(f"\nnet interest income, quarterly coverage: {', '.join(q3) or 'none'}")
    dv = sorted({r["quarter"] for r in rows if r["derived"]
                 and r["concept"] == "net_interest_income"})
    if dv:
        print(f"  of which derived (FY-9M): {', '.join(dv)}")

    # ---- additive check: does II - IE tie to reported NII?
    print("\nadditive check (total interest income - expense vs reported NII):")
    bad = 0
    for r in [x for x in rows if x["concept"] == "net_interest_income"
              and x["months"] == 3]:
        e, mo = r["period_end"], r["months"]
        ii = idx.get(("int_inc_total", mo, e)) or next(
            (x for x in rows if x["concept"] == "int_inc_total"
             and x["months"] == mo and x["period_end"] == e), None)
        ie = next((x for x in rows if x["concept"] == "int_exp_total"
                   and x["months"] == mo and x["period_end"] == e), None)
        if not (ii and ie):
            print(f"   {r['quarter']:8s} components missing, cannot check")
            continue
        diff = ii["value_usd"] - ie["value_usd"] - r["value_usd"]
        ok = "ok" if abs(diff) < 1e6 else "MISMATCH"
        if ok != "ok":
            bad += 1
        print(f"   {r['quarter']:8s} {ok:9s} diff {diff/1e6:>8,.1f}mm"
              f"{'   (derived)' if r['derived'] else ''}")
    if bad:
        print(f"   !! {bad} quarter(s) fail -- check tag mapping before using")


if __name__ == "__main__":
    main()
