#!/usr/bin/env python3
"""
Extract quarterly balance-sheet anchors from the ALREADY-DOWNLOADED 10-K/10-Q
files. No network required.

    python3 extract-local-anchors.py                    # -> anchors.csv
    python3 extract-local-anchors.py --list-tags        # what's actually tagged

The 10-K/10-Q primary documents are inline XBRL, so the numbers are embedded
as <ix:nonFraction> elements with a contextRef pointing at a period. This reads
them directly, which makes it a drop-in offline replacement for
fetch-xbrl-anchors.py -- same output schema, so build-monthly.py is unchanged.

Only CONSOLIDATED facts are kept: a fact whose context carries dimensions
(explicitMember) is a segment/subsidiary breakdown, not the group total. That
filter is why one document can hold 38 differently-scoped "Assets" facts but
only a couple of real balance-sheet values.
"""
import argparse, csv, glob, html, os, re, sys
from collections import defaultdict

CONCEPTS = {
    "total_assets":          ["Assets"],
    "total_liabilities":     ["Liabilities"],
    "total_equity":          ["StockholdersEquity",
                              "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "deposits":              ["Deposits"],
    "deposits_interest_bearing": ["InterestBearingDepositLiabilities"],
    "deposits_noninterest":  ["NoninterestBearingDepositLiabilities"],
    # Gross vs net of allowance are DIFFERENT LINES and must not be conflated.
    # Observed on Capital One: NotesReceivableNet = $434.2bn at 2026-06-30 while
    # FinancingReceivable...BeforeAllowance = $457.2bn, the difference being the
    # $23.0bn allowance. The monthly 8-K reports GROSS loans held for
    # investment, so loans_hfi_gross is the right basis for coverage checks.
    "loans_hfi_gross":       ["FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss",
                              "LoansAndLeasesReceivableGrossCarryingAmount"],
    "loans_hfi_net":         ["LoansAndLeasesReceivableNetReportedAmount",
                              "NotesReceivableNet"],
    "allowance_credit_loss": ["FinancingReceivableAllowanceForCreditLosses",
                              "FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest"],
    "securities_afs":        ["DebtSecuritiesAvailableForSaleExcludingAccruedInterest",
                              "AvailableForSaleSecuritiesDebtSecurities"],
    "securities_htm":        ["DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss",
                              "HeldToMaturitySecurities"],
    "cash_and_equivalents":  ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                              "CashAndCashEquivalentsAtCarryingValue",
                              "CashAndDueFromBanks"],
    "long_term_debt":        ["LongTermDebt"],
}
TAG_TO_CONCEPT = {t: c for c, ts in CONCEPTS.items() for t in ts}

FILER_BY_PREFIX = {"capitalone": "cof", "schwab": "schw", "discover": "discover"}

CTX_RE = re.compile(
    r'<xbrli:context[^>]*\bid="(?P<id>[^"]+)"(?P<body>.*?)</xbrli:context>',
    re.I | re.S)
# Some filers emit un-prefixed <context> elements.
CTX_RE_ALT = re.compile(
    r'<context[^>]*\bid="(?P<id>[^"]+)"(?P<body>.*?)</context>', re.I | re.S)
INSTANT_RE = re.compile(r'<(?:xbrli:)?instant>\s*([0-9]{4}-[0-9]{2}-[0-9]{2})', re.I)
ENDDATE_RE = re.compile(r'<(?:xbrli:)?endDate>\s*([0-9]{4}-[0-9]{2}-[0-9]{2})', re.I)
DIM_RE     = re.compile(r'explicitMember|typedMember', re.I)

FACT_RE = re.compile(
    r'<ix:nonfraction(?P<attrs>[^>]*)>(?P<inner>.*?)</ix:nonfraction>',
    re.I | re.S)
ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')


def parse_contexts(text):
    """id -> (date, is_instant, has_dims)"""
    out = {}
    for rx in (CTX_RE, CTX_RE_ALT):
        for m in rx.finditer(text):
            cid, body = m.group("id"), m.group("body")
            if cid in out:
                continue
            inst = INSTANT_RE.search(body)
            end  = ENDDATE_RE.search(body)
            date = inst.group(1) if inst else (end.group(1) if end else None)
            if not date:
                continue
            out[cid] = (date, bool(inst), bool(DIM_RE.search(body)))
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="filings")
    ap.add_argument("--out", default="anchors.csv")
    ap.add_argument("--list-tags", action="store_true",
                    help="show the most common consolidated instant tags and exit")
    ap.add_argument("--filer", default="cof",
                    help="which filer to write (cof|schw|all). default cof")
    args = ap.parse_args()

    files = [p for p in sorted(glob.glob(os.path.join(args.dir, "*.htm*")))
             if form_of(p)]
    if not files:
        sys.exit(f"no 10-K/10-Q files in {args.dir}/ -- run download-filings.sh")

    # (filer, concept, tag) -> {date: value}. Tag selection happens AFTER all
    # files are read: a concept must use ONE tag across the whole series, or
    # you get apples-to-oranges. Capital One tags cash as
    # CashCashEquivalentsRestricted... in some years and CashAndDueFromBanks in
    # others -- mixing them made cash look like it fell from $43.7bn to $3.0bn.
    collected = defaultdict(dict)
    seen_tags = defaultdict(int)
    rows = []

    # The same filing can sit on disk under two names (download-filings.sh uses
    # hardcoded names, download-periodic.py derives them from the period). Skip
    # byte-identical repeats: harmless for results, but halves the runtime.
    import hashlib
    seen_hashes = {}

    for path in files:
        raw = open(path, "rb").read()
        h = hashlib.sha256(raw).hexdigest()
        if h in seen_hashes:
            print(f"{os.path.basename(path):32s} duplicate of "
                  f"{os.path.basename(seen_hashes[h])} -- skipped")
            continue
        seen_hashes[h] = path
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc); break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", "replace")

        ctx = parse_contexts(text)
        filer, form = filer_of(path), form_of(path)
        kept, skipped_dim = 0, 0
        concepts_here = set()

        for m in FACT_RE.finditer(text):
            attrs = dict(ATTR_RE.findall(m.group("attrs")))
            name = (attrs.get("name") or "").strip()
            if not name.lower().startswith("us-gaap:"):
                continue
            tag = name.split(":", 1)[1]
            cref = attrs.get("contextref") or attrs.get("contextRef")
            c = ctx.get(cref or "")
            if not c:
                continue
            date, is_instant, has_dims = c
            if not is_instant:
                continue
            if has_dims:
                skipped_dim += 1
                continue
            seen_tags[tag] += 1
            concept = TAG_TO_CONCEPT.get(tag)
            if not concept:
                continue
            v = clean_value(m.group("inner"), attrs)
            if v is None:
                continue
            slot = collected[(filer, concept, tag)]
            if date not in slot:
                slot[date] = (v, form, os.path.basename(path))
            concepts_here.add(concept)
            kept += 1

        print(f"{os.path.basename(path):32s} {filer:9s} {form:5s} "
              f"contexts={len(ctx):5d} consolidated_facts={kept:4d} "
              f"dim_skipped={skipped_dim:5d} concepts={len(concepts_here)}")

    # ---- one tag per (filer, concept): widest date coverage wins, ties broken
    # by the order in CONCEPTS. Rejected alternatives are reported, not hidden.
    rejected = []
    for filer in sorted({k[0] for k in collected}):
        for concept, candidates in CONCEPTS.items():
            avail = [(t, collected[(filer, concept, t)])
                     for t in candidates if (filer, concept, t) in collected]
            if not avail:
                continue
            best_tag, best_dates = max(
                avail, key=lambda kv: (len(kv[1]), -candidates.index(kv[0])))
            for t, dates in avail:
                if t != best_tag:
                    rejected.append((filer, concept, t, len(dates),
                                     best_tag, len(best_dates)))
            for date, (v, form, src) in best_dates.items():
                rows.append({"filer": filer, "period_end": date, "concept": concept,
                             "xbrl_tag": best_tag, "value_usd": v, "form": form,
                             "filed": "", "fy": "", "fp": "", "accession": src})

    if rejected:
        print("\ntag conflicts resolved (one tag per concept, to keep the "
              "series comparable):")
        for filer, concept, drop, ndrop, keep, nkeep in rejected:
            print(f"   {filer:6s} {concept:22s} using {keep} ({nkeep} periods), "
                  f"dropped {drop} ({ndrop})")

    if args.list_tags:
        print("\nmost common consolidated instant us-gaap tags:")
        for tag, n in sorted(seen_tags.items(), key=lambda kv: -kv[1])[:60]:
            mark = "*" if tag in TAG_TO_CONCEPT else " "
            print(f"  {mark} {n:5d}  {tag}")
        print("\n(* = mapped to a concept)")
        return

    if args.filer != "all":
        rows = [r for r in rows if r["filer"] == args.filer]
    if not rows:
        sys.exit(f"no facts for filer={args.filer}")

    rows.sort(key=lambda r: (r["filer"], r["period_end"], r["concept"]))
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"\n{len(rows)} facts -> {args.out}")

    by = defaultdict(dict)
    for r in rows:
        by[(r["filer"], r["period_end"])][r["concept"]] = r["value_usd"]
    print("\nperiod-ends found, and articulation check:")
    for (filer, end), vals in sorted(by.items()):
        a, l, e = (vals.get(k) for k in
                   ("total_assets", "total_liabilities", "total_equity"))
        if a and l and e:
            d = a - (l + e)
            ok = "ok" if abs(d) <= abs(a) * 0.005 else "MISMATCH"
            print(f"   {filer:6s} {end}  {len(vals):2d} concepts  "
                  f"{ok:8s} diff {d/1e6:>10,.1f}mm")
        else:
            print(f"   {filer:6s} {end}  {len(vals):2d} concepts  "
                  f"(incomplete A/L/E)")

    missing = set(CONCEPTS) - {r["concept"] for r in rows}
    if missing:
        print(f"\nconcepts never found: {', '.join(sorted(missing))}")
        print("   run --list-tags to see what this filer actually tags")


if __name__ == "__main__":
    main()
