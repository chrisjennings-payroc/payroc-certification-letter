#!/usr/bin/env python3
"""Regenerate the certification-letter endpoint catalogue from the Payroc OpenAPI spec.

  python3 scripts/sync_catalogue.py          # rewrite catalogue.json + the copy embedded in the letter
  python3 scripts/sync_catalogue.py --check  # report drift, exit 1 if the committed catalogue is stale

Display names come from the spec's operation summaries. Grouping lives in TAG_MAP below,
so a spec tag we have not mapped is reported (and placed under "Other") instead of silently dropped.
"""
import datetime, json, re, sys, urllib.request
from pathlib import Path

SPEC_URL = "https://docs.payroc.com/openapi.json"
ROOT = Path(__file__).resolve().parent.parent
LETTER = ROOT / "Payroc-Integration-Certification-Letter-Template.html"
CATALOGUE = ROOT / "catalogue.json"
START, END = "/*CATALOGUE:START*/", "/*CATALOGUE:END*/"
DATE_START, DATE_END = "/*CATALOGUE_DATE:START*/", "/*CATALOGUE_DATE:END*/"
METHODS = ("get", "post", "put", "patch", "delete")

# spec tag -> (letter group, letter sub-group). Order here is display order.
TAG_MAP = {
    "Pricing intents": ("Boarding", "Pricing Intents"),
    "Merchant platforms": ("Boarding", "Merchant Platforms"),
    "Processing accounts": ("Boarding", "Processing Accounts"),
    "Processing terminals": ("Boarding", "Processing Terminals"),
    "Terminal orders": ("Boarding", "Terminal Orders"),
    "Payment intents": ("Boarding", "Payment Intents"),
    "Attachments": ("Boarding", "Attachments"),
    "Contacts": ("Boarding", "Contacts"),
    "Owners": ("Boarding", "Owners"),
    "Funding accounts": ("Funding", "Funding Accounts"),
    "Funding activity": ("Funding", "Funding Activity"),
    "Funding instructions": ("Funding", "Funding Instructions"),
    "Funding recipients": ("Funding", "Funding Recipients"),
    "Payment links": ("Transactions", "Payment Links"),
    "Payments": ("Transactions", "Payments (card)"),
    "Refunds": ("Transactions", "Unreferenced Refunds (card)"),
    "Cards": ("Transactions", "Cards"),
    "Bank transfer payments": ("Transactions", "Bank Transfer Payments (ACH / PAD)"),
    "Bank transfer refunds": ("Transactions", "Bank Transfer Unreferenced Refunds"),
    "Bank accounts": ("Transactions", "Bank Accounts"),
    "Currency conversion": ("Transactions", "Currency Conversion"),
    "Payment plans": ("Transactions", "Payment Plans"),
    "Subscriptions": ("Transactions", "Subscriptions"),
    "Secure tokens": ("Transactions", "Secure Tokens"),
    "Single use tokens": ("Transactions", "Single-Use Tokens"),
    "Hosted Fields": ("Transactions", "Hosted Fields"),
    "Apple Pay session": ("Transactions", "Apple Pay"),
    "Devices": ("Transactions", "Payroc Cloud"),
    "Payment instructions": ("Transactions", "Payroc Cloud"),
    "Refund instructions": ("Transactions", "Payroc Cloud"),
    "Signature instructions": ("Transactions", "Payroc Cloud"),
    "Signatures": ("Transactions", "Payroc Cloud"),
    "Closed-loop reads": ("Transactions", "Payroc Cloud"),
}
# The spec lumps all reporting under one "Settlement" tag; split it by path.
SETTLEMENT_SPLIT = [
    ("/ach-deposit", "ACH Deposits"),
    ("/disputes", "Disputes"),
]
SETTLEMENT_DEFAULT = "Settlement & Authorizations"
TAG_MAP["Event Subscriptions"] = ("Reporting", "Event Subscriptions")
GROUP_ORDER = ["Boarding", "Funding", "Transactions", "Reporting", "Other"]


def place(tag, path):
    if tag == "Settlement":
        for prefix, sub in SETTLEMENT_SPLIT:
            if path.startswith(prefix):
                return "Reporting", sub
        return "Reporting", SETTLEMENT_DEFAULT
    return TAG_MAP.get(tag, ("Other", tag or "Untagged"))


def build(spec):
    subs = {}  # (group, sub) -> [items]
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method not in METHODS:
                continue
            tag = (op.get("tags") or [""])[0]
            subs.setdefault(place(tag, path), []).append(
                {"key": f"{method.upper()} {path}", "name": op.get("summary") or op.get("operationId") or path})
    sub_order = list(dict.fromkeys(TAG_MAP.values()))
    sub_order = [s for s in sub_order if s[1] != "Event Subscriptions"] +[("Reporting", s) for s in
                 [x[1] for x in SETTLEMENT_SPLIT] + [SETTLEMENT_DEFAULT]] + [("Reporting", "Event Subscriptions")]
    def sort_key(gs):
        g, s = gs
        return (GROUP_ORDER.index(g), sub_order.index(gs) if gs in sub_order else 999, s)
    groups = []
    for (g, s) in sorted(subs, key=sort_key):
        if not groups or groups[-1]["g"] != g:
            groups.append({"g": g, "sub": []})
        groups[-1]["sub"].append({"name": s, "items": subs[(g, s)]})
    return {"source": SPEC_URL, "groups": groups}


def keys(cat):
    return {i["key"]: i["name"] for g in cat["groups"] for s in g["sub"] for i in s["items"]}


def embed(html, cat):
    html = re.sub(re.escape(DATE_START) + r".*?" + re.escape(DATE_END),
                  lambda _: DATE_START + cat["generated"] + DATE_END, html, count=1, flags=re.S)
    blob = json.dumps(cat["groups"], separators=(",", ":"), ensure_ascii=False)
    pat = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    return pat.sub(lambda _: f"{START}{blob}{END}", html, count=1)


def main():
    check = "--check" in sys.argv
    req = urllib.request.Request(SPEC_URL, headers={"User-Agent": "Mozilla/5.0 (catalogue-sync)"})
    spec = json.load(urllib.request.urlopen(req, timeout=60))
    new = build(spec)
    old = json.loads(CATALOGUE.read_text()) if CATALOGUE.exists() else {"groups": []}
    ok, nk = keys(old), keys(new)
    added, removed = sorted(set(nk) - set(ok)), sorted(set(ok) - set(nk))
    renamed = sorted(k for k in set(nk) & set(ok) if nk[k] != ok[k])
    other = [s["name"] for g in new["groups"] if g["g"] == "Other" for s in g["sub"]]
    for label, ks, src in (("NEW", added, nk), ("REMOVED", removed, ok), ("RENAMED", renamed, nk)):
        for k in ks:
            print(f"{label:8} {k}  ({src[k]})")
    if other:
        print("UNMAPPED spec tags (add to TAG_MAP):", ", ".join(other))
    print(f"{len(nk)} operations; {len(added)} new, {len(removed)} removed, {len(renamed)} renamed")
    drift = bool(added or removed or renamed or other)
    if check:
        sys.exit(1 if drift else 0)
    # keep the date stable when nothing changed, so refreshes don't create noise
    new["generated"] = old.get("generated") if not drift and old.get("generated") else datetime.date.today().isoformat()
    CATALOGUE.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n")
    html = LETTER.read_text()
    if START in html:
        LETTER.write_text(embed(html, new))


if __name__ == "__main__":
    main()
