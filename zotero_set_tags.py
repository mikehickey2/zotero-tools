#!/usr/bin/env python3
"""
Set or remove tags on specific Zotero items by item key.

Uses direct pyzotero API calls (zot.item → modify → zot.update_item) which
are more reliable than the Zotero MCP's batch_update_tags tool. Supports
read-after-write verification to confirm tags were applied.

Usage:
    python zotero_set_tags.py --add "#Sec-LitReview" "#RQ-General" --items 7VLH3GJK --dry-run
    python zotero_set_tags.py --add "#Sec-LitReview" --items 7VLH3GJK --verify
    python zotero_set_tags.py --remove "#Status-Unread" --items 7VLH3GJK
    python zotero_set_tags.py --add "#Status-Read" --remove "#Status-Unread" --items 7VLH3GJK
"""

import argparse
import sys
import time

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

SKIP_ITEM_TYPES = {"attachment", "annotation", "note"}
RATE_LIMIT = 0.5


def set_tags(zot, item_key, tags_to_add, tags_to_remove, dry_run=False, verify=False):
    """
    Add and/or remove tags on a single Zotero item.

    Returns:
        Tuple of (action, message) where action is 'updated', 'skipped', or 'error'.
    """
    try:
        item = zot.item(item_key)
    except Exception as e:
        return "error", f"Could not fetch {item_key}: {e}"

    item_type = item["data"].get("itemType", "")
    if item_type in SKIP_ITEM_TYPES:
        return "skipped", f"{item_key} is a {item_type} (skipping non-content type)"

    title = item["data"].get("title", "(no title)")[:60]
    current_tags = {t["tag"] for t in item["data"].get("tags", [])}

    # Compute changes
    actually_adding = tags_to_add - current_tags
    actually_removing = tags_to_remove & current_tags

    if not actually_adding and not actually_removing:
        return "skipped", f"{item_key} [{title}] — no changes needed"

    # Build new tag set
    new_tags = (current_tags | tags_to_add) - tags_to_remove

    if dry_run:
        parts = []
        if actually_adding:
            parts.append(f"+ {', '.join(sorted(actually_adding))}")
        if actually_removing:
            parts.append(f"- {', '.join(sorted(actually_removing))}")
        return "updated", f"{item_key} [{title}]  {' | '.join(parts)}"

    # Write
    item["data"]["tags"] = [{"tag": t} for t in sorted(new_tags)]
    try:
        zot.update_item(item)
    except HTTPError as e:
        return "error", f"API error updating {item_key}: {e}"

    parts = []
    if actually_adding:
        parts.append(f"+ {', '.join(sorted(actually_adding))}")
    if actually_removing:
        parts.append(f"- {', '.join(sorted(actually_removing))}")
    msg = f"{item_key} [{title}]  {' | '.join(parts)}"

    # Verify read-back
    if verify:
        try:
            updated = zot.item(item_key)
            actual_tags = {t["tag"] for t in updated["data"].get("tags", [])}
            missing = tags_to_add - actual_tags
            still_present = tags_to_remove & actual_tags
            if missing or still_present:
                failures = []
                if missing:
                    failures.append(f"missing: {', '.join(sorted(missing))}")
                if still_present:
                    failures.append(f"not removed: {', '.join(sorted(still_present))}")
                return "error", f"{msg}  VERIFY FAILED: {'; '.join(failures)}"
            msg += "  ✓ verified"
        except Exception as e:
            return "error", f"{msg}  VERIFY ERROR: {e}"

    return "updated", msg


def main():
    parser = argparse.ArgumentParser(
        description="Add or remove tags on specific Zotero items by key.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --add "#Sec-LitReview" "#RQ-General" --items 7VLH3GJK --dry-run
  %(prog)s --add "#Sec-LitReview" --items 7VLH3GJK --verify
  %(prog)s --remove "#Status-Unread" --items 7VLH3GJK
  %(prog)s --add "#Status-Read" --remove "#Status-Unread" --items 7VLH3GJK

Environment variables (or .env file):
  ZOTERO_LIBRARY_ID     Your Zotero library ID
  ZOTERO_LIBRARY_TYPE   'group' (default) or 'user'
  ZOTERO_API_KEY        Your Zotero API key
        """,
    )
    parser.add_argument(
        "--add",
        nargs="+",
        default=[],
        metavar="TAG",
        help='Tags to add (e.g., "#Sec-LitReview" "#RQ-General")',
    )
    parser.add_argument(
        "--remove",
        nargs="+",
        default=[],
        metavar="TAG",
        help='Tags to remove (e.g., "#Status-Unread")',
    )
    parser.add_argument(
        "--items",
        nargs="+",
        required=True,
        metavar="KEY",
        help="Zotero item keys to modify",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read-after-write verification (confirms tags were applied)",
    )
    args = parser.parse_args()

    if not args.add and not args.remove:
        parser.error("At least one of --add or --remove is required")

    tags_to_add = set(args.add)
    tags_to_remove = set(args.remove)

    # Sanity check: adding and removing the same tag
    overlap = tags_to_add & tags_to_remove
    if overlap:
        print(f"WARNING: Tags in both --add and --remove (remove wins): {', '.join(sorted(overlap))}")
        tags_to_add -= overlap

    library_id, library_type, api_key = load_credentials()
    zot = zotero.Zotero(library_id, library_type, api_key)

    updated = 0
    skipped = 0
    errors = 0

    mode = "DRY RUN" if args.dry_run else "APPLY"
    print(f"\n{mode}: Processing {len(args.items)} item(s)")
    if tags_to_add:
        print(f"  Add:    {', '.join(sorted(tags_to_add))}")
    if tags_to_remove:
        print(f"  Remove: {', '.join(sorted(tags_to_remove))}")
    print()

    for i, item_key in enumerate(args.items):
        action, message = set_tags(
            zot, item_key, tags_to_add, tags_to_remove,
            dry_run=args.dry_run, verify=args.verify,
        )
        prefix = {"updated": "  SET", "skipped": "  SKIP", "error": "  ERROR"}[action]
        print(f"{prefix}: {message}")

        if action == "updated":
            updated += 1
        elif action == "skipped":
            skipped += 1
        else:
            errors += 1

        # Rate limit between writes (not on dry run, not on last item)
        if not args.dry_run and i < len(args.items) - 1:
            time.sleep(RATE_LIMIT)

    print(f"\n{mode}: {updated} updated, {skipped} skipped, {errors} errors")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
