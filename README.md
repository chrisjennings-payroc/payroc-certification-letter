# Payroc Integration Certification Letter

Single-file HTML template (`Payroc-Integration-Certification-Letter-Template.html`) for the certification letter sent to a partner. Open it in a browser, edit, and use **Save** to download the filled-in copy.

## Endpoint catalogue

The "Certified API methods" list is generated from Payroc's OpenAPI spec (https://docs.payroc.com/openapi.json), not edited by hand.

```bash
python3 scripts/sync_catalogue.py          # refresh catalogue.json and the copy embedded in the letter
python3 scripts/sync_catalogue.py --check  # list new/removed/renamed operations; exit 1 if stale
```

- `catalogue.json` is the generated catalogue, keyed by `METHOD /path`.
- Grouping is controlled by `TAG_MAP` in the script. A spec tag it doesn't know is reported as **UNMAPPED**; add it to `TAG_MAP`.
- The Base URL picker only appears in the Transactions group.
