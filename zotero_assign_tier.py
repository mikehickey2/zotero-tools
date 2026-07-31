#!/usr/bin/env python3
"""
Assign `tier: <T1|T2|T3|inbox|archived>` to each Zotero item's Extra field
based on collection membership. Companion to Better Notes ExportMDFileHeader
template which projects Extra-field whitelisted keys into vault frontmatter.

Mapping (substring match on collection names; first-match-wins, T1 first):
    Prior-UAS-Studies, LLM-Applications, Text-Mining,
    RQ1-Extraction, RQ2-Temporal           → T1
    Background-Context                      → T2
    Statistical-Foundations                 → T3
    Inbox (any collection name containing)  → inbox
    Archive (any collection name containing)→ archived

Usage:
    python zotero_assign_tier.py --dry-run                  # preview all items
    python zotero_assign_tier.py --dry-run --items KEY KEY  # preview specific items
    python zotero_assign_tier.py                            # apply to all items
    python zotero_assign_tier.py --verify                   # apply + read-back verify

Multi-library:
    ZOTERO_LIBRARY_ID=6448487 ZOTERO_LIBRARY_TYPE=group python zotero_assign_tier.py --dry-run
"""

import argparse
import re
import sys
import time
from collections import Counter

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

SKIP_ITEM_TYPES = {"attachment", "annotation", "note"}
RATE_LIMIT = 0.3  # seconds between writes to be polite to the API
EXTRA_KEY = "tier"

# Tier mapping (first-match-wins, ordered by priority).
# Extend by adding to the substring tuple of the appropriate tier.
TIER_RULES = [
    ("T1", (
        "Prior-UAS-Studies",        # 04 — direct prior work on FAA UAS data
        "LLM-Applications",         # 04 — LLM in aviation safety
        "Text-Mining",              # 04 — text mining precedents
        "RQ1-Extraction",           # 05 — RQ1 methodology
        "RQ2-Temporal",             # 05 — RQ2 methodology
        "IE papers",                # IE survey/methodology corpus
        "03-Introduction",          # intro lit
        "04-Literature-Review",     # lit-review catch-all
        "05a-Topic-Proposal-Methods",  # proposal methods chapter
    )),
    ("T2", (
        "Background-Context",       # 07 — background framing
        "02-News-and-Web",          # 02 — non-academic background references
    )),
    ("T3", ("Statistical-Foundations",)),  # 06 — statistical methodology
    ("inbox", ("Inbox",)),
    ("archived", ("Archive",)),
]


def compute_tier(collection_names):
    """Return the first matching tier value, or None if no rule matches."""
    for tier_value, substrings in TIER_RULES:
        for col_name in collection_names:
            for substring in substrings:
                if substring in col_name:
                    return tier_value
    return None


def upsert_extra_key(extra_text, key, value):
    """
    Insert or update a `key: value` line in a Zotero Extra-field text block.
    Preserves all other lines. Returns the new extra text.
    """
    pattern = re.compile(rf"^{re.escape(key)}\s*:.*$", re.MULTILINE)
    new_line = f"{key}: {value}"
    if pattern.search(extra_text):
        return pattern.sub(new_line, extra_text, count=1)
    # Append; preserve trailing newline behavior
    if extra_text and not extra_text.endswith("\n"):
        extra_text += "\n"
    return extra_text + new_line


def extract_extra_key(extra_text, key):
    """Return the current value of `key` from Extra, or None if absent."""
    pattern = re.compile(rf"^{re.escape(key)}\s*:\s*(.+)$", re.MULTILINE)
    m = pattern.search(extra_text or "")
    return m.group(1).strip() if m else None


def assign_tier(zot, item, collection_name_map, *, dry_run=False, verify=False):
    """
    Compute and write tier for a single item.

    Returns: (action, message) where action ∈ {'updated', 'skipped', 'no-rule', 'error'}
    """
    item_key = item["key"]
    data = item["data"]
    item_type = data.get("itemType", "")
    if item_type in SKIP_ITEM_TYPES:
        return "skipped", f"{item_key} is a {item_type} (skipping)"

    title = data.get("title", "(no title)")[:50]
    coll_keys = data.get("collections", [])
    coll_names = [collection_name_map.get(k, f"<{k}>") for k in coll_keys]

    new_tier = compute_tier(coll_names)
    if new_tier is None:
        return "no-rule", (f"{item_key} [{title}] — no collection matched "
                           f"({coll_names if coll_names else 'no collections'})")

    extra = data.get("extra", "") or ""
    current_tier = extract_extra_key(extra, EXTRA_KEY)

    if current_tier == new_tier:
        return "skipped", f"{item_key} [{title}] already tier={new_tier}"

    new_extra = upsert_extra_key(extra, EXTRA_KEY, new_tier)
    diff = f"tier: {current_tier or '(none)'} → {new_tier}"

    if dry_run:
        return "updated", f"{item_key} [{title}]  {diff}  [collections: {','.join(coll_names) or '-'}]"

    # Write
    data["extra"] = new_extra
    try:
        zot.update_item(item)
    except HTTPError as e:
        return "error", f"{item_key} [{title}]  API error: {e}"

    msg = f"{item_key} [{title}]  {diff}"

    if verify:
        time.sleep(0.1)
        try:
            fresh = zot.item(item_key)
            verified = extract_extra_key(fresh["data"].get("extra", ""), EXTRA_KEY)
            if verified != new_tier:
                return "error", f"{msg}  VERIFY FAILED: expected '{new_tier}' got '{verified}'"
            msg += "  ✓ verified"
        except Exception as e:
            return "error", f"{msg}  VERIFY ERROR: {e}"

    return "updated", msg


def build_collection_name_map(zot):
    """Return {collection_key: name} for all collections in the library."""
    all_colls = zot.everything(zot.collections())
    return {c["key"]: c["data"].get("name", f"<{c['key']}>") for c in all_colls}


def get_items(zot, item_keys=None):
    """Fetch all non-skipped items, or specific keys if provided."""
    if item_keys:
        items = []
        for k in item_keys:
            try:
                items.append(zot.item(k))
            except Exception as e:
                print(f"WARN: could not fetch {k}: {e}", file=sys.stderr)
        return items
    raw = zot.everything(zot.items())
    return [i for i in raw if i["data"].get("itemType", "") not in SKIP_ITEM_TYPES]


def main():
    parser = argparse.ArgumentParser(
        description="Assign tier to Zotero items based on collection membership.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--items", nargs="+", default=None,
                        help="Specific item keys to process. Default: all items in library.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing.")
    parser.add_argument("--verify", action="store_true",
                        help="Read back each item after write to confirm tier persisted.")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print each action; default is summary only.")
    args = parser.parse_args()

    library_id, library_type, api_key = load_credentials()
    zot = zotero.Zotero(library_id, library_type, api_key)

    print(f"Library: {library_type}/{library_id}")
    print("Building collection name map...")
    coll_map = build_collection_name_map(zot)
    print(f"  {len(coll_map)} collections loaded")

    print(f"Fetching {'specific' if args.items else 'all'} items...")
    items = get_items(zot, args.items)
    print(f"  {len(items)} items to process")
    print()

    counts = Counter()
    for i, item in enumerate(items, 1):
        action, msg = assign_tier(zot, item, coll_map,
                                   dry_run=args.dry_run, verify=args.verify)
        counts[action] += 1
        if args.verbose or action in ("error", "no-rule"):
            prefix = {
                "updated": "→",
                "skipped": " ",
                "no-rule": "?",
                "error":   "✗",
            }.get(action, "?")
            print(f"  {prefix} {msg}")
        if not args.dry_run and action == "updated":
            time.sleep(RATE_LIMIT)

    print()
    print("=" * 60)
    print("Summary:")
    for action in ("updated", "skipped", "no-rule", "error"):
        if counts[action]:
            print(f"  {action:10} {counts[action]}")
    if args.dry_run:
        print("\n[DRY RUN] No changes written. Re-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
