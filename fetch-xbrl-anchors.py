#!/usr/bin/env python3
"""
Pull quarterly balance-sheet anchors from SEC XBRL for Capital One (and
pre-close Discover) into anchors.csv.

Why XBRL instead of parsing the 10-Q HTML: the companyconcept API returns the
exact as-reported values the registrant tagged, keyed by period-end date, with
the filing that reported them. No table scraping, no layout drift.

    python3 fetch-xbrl-anchors.py                 # Capital One
    python3 fetch-xbrl-anchors.py --discover      # add pre-close Discover
    python3 fetch-xbrl-anchors.py --since 2022-01-01

Run from your own machine -- Cowork's network can't reach sec.gov.
"""
import argparse, csv, json, os, sys, time, urllib.error, urllib.request
from collections import defaultdict

UA = os.environ.get("SEC_UA", "CJ cjbox21@gmail.com")

FILERS = {"cof": "0000927628", "discover": "0001393612"}

# Banks don't all tag the same way, and tags drift across years. For each
# concept we try candidates in order and keep the first that returns facts.
# The chosen tag is recorded in the output so you can see what actually fed
# each line rather than trusting a label.
CONCEPTS = {
    "total_assets":        ["Assets"],
    "total_liabilities":   ["Liabilities"],
    "total_equity":        ["StockholdersEquity",
                            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "deposits":            ["Deposits",
                            "InterestBearingDepositLiabilities"],
    "deposits_interest_bearing": ["InterestBearingDepositLiabilities"],
    "deposits_noninterest":      ["NoninterestBearingDepositLiabilities"],
    "loans_hfi":           ["LoansAndLeasesReceivableNetReportedAmount",
                            "LoansAndLeasesReceivableGrossCarryingAmount",
                            "NotesReceivableGross",
                            "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss"],
    "allowance_credit_loss": ["FinancingReceivableAllowanceForCreditLosses",
                              "FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest",
                              "LoansAndLeasesReceivableAllowance"],
    "securities_afs":      ["DebtSecuritiesAvailableForSaleExcludingAccruedInterest",
                            "AvailableForSaleSecuritiesDebtSecurities",
                            "AvailableForSaleSecurities"],
    "securities_htm":      ["DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss",
                            "HeldToMaturitySecurities"],
    "cash_and_equivalents": ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                             "CashAndCashEquivalentsAtCarryingValue",
                             "CashAndDueFromBanks"],
    "long_term_debt":      ["LongTermDebt", "LongTermDebtNoncurrent"],
}


def get(url, tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None                      # tag not used by this filer
            if e.code in (429, 503) and attempt < tries - 1:
                time.sleep(2 ** attempt); continue
            raise
        finally:
            time.sleep(0.15)
    return None


def concept_facts(cik, tag):
    url = (f"https://data.sec.gov/api/xbrl/companyconcept/"
           f"CIK{cik}/us-gaap/{tag}.json")
    return get(url)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true",
                    help="also pull Discover (CIK 1393612) pre-close anchors")
    ap.add_argument("--since", default="2022-01-01",
                    help="earliest period-end date to keep (YYYY-MM-DD)")
    ap.add_argument("--out", default="anchors.csv")
    args = ap.parse_args()

    if UA.startswith("Your Name"):
        sys.exit("Set SEC_UA to your name and email first.")

    filers = ["cof"] + (["discover"] if args.discover else [])
    rows, tag_used, missing = [], {}, defaultdict(list)

    for filer in filers:
        cik = FILERS[filer]
        print(f"\n[{filer}] CIK {cik}")
        for concept, candidates in CONCEPTS.items():
            picked = None
            for tag in candidates:
                data = concept_facts(cik, tag)
                if not data or "units" not in data:
                    continue
                usd = data["units"].get("USD") or []
                if not usd:
                    continue
                picked = (tag, usd)
                break

            if not picked:
                missing[filer].append(concept)
                print(f"   -- {concept:26s} no tag matched")
                continue

            tag, usd = picked
            tag_used[(filer, concept)] = tag

            # Instant facts from periodic reports only. Multiple filings report
            # the same period-end (restatements, comparatives) -- keep the most
            # recently filed value per end date.
            best = {}
            for f in usd:
                if f.get("form") not in ("10-K", "10-Q"):
                    continue
                end = f.get("end")
                if not end or end < args.since:
                    continue
                prev = best.get(end)
                if prev is None or f.get("filed", "") > prev.get("filed", ""):
                    best[end] = f

            for end, f in sorted(best.items()):
                rows.append({
                    "filer": filer, "period_end": end, "concept": concept,
                    "xbrl_tag": tag, "value_usd": f["val"],
                    "form": f.get("form", ""), "filed": f.get("filed", ""),
                    "fy": f.get("fy", ""), "fp": f.get("fp", ""),
                    "accession": f.get("accn", ""),
                })
            print(f"   ok {concept:26s} {tag:58s} {len(best):3d} periods")

    if not rows:
        sys.exit("No facts retrieved -- check network and SEC_UA.")

    rows.sort(key=lambda r: (r["filer"], r["period_end"], r["concept"]))
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    print(f"\n{len(rows)} facts -> {args.out}")

    # Sanity check: does the balance sheet actually balance at each anchor?
    # A mismatch means the tags above aren't capturing what you think.
    by_period = defaultdict(dict)
    for r in rows:
        by_period[(r["filer"], r["period_end"])][r["concept"]] = r["value_usd"]
    print("\nArticulation check (assets vs liabilities + equity):")
    for (filer, end), vals in sorted(by_period.items()):
        a, l, e = (vals.get("total_assets"), vals.get("total_liabilities"),
                   vals.get("total_equity"))
        if a and l and e:
            diff = a - (l + e)
            tol = abs(a) * 0.005
            mark = "ok" if abs(diff) <= tol else "MISMATCH"
            print(f"   {mark:8s} {filer:8s} {end}  diff {diff/1e6:>12,.1f}mm")
        else:
            have = [k for k in ("total_assets","total_liabilities","total_equity") if vals.get(k)]
            print(f"   partial  {filer:8s} {end}  have {have or 'none'}")

    for filer, cs in missing.items():
        if cs:
            print(f"\n[{filer}] concepts with no matching tag: {', '.join(cs)}")
            print("   Add candidates to CONCEPTS, or find the tag via:")
            print(f"   https://data.sec.gov/api/xbrl/companyfacts/CIK{FILERS[filer]}.json")


if __name__ == "__main__":
    main()
