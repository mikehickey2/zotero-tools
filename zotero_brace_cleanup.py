#!/usr/bin/env python3
"""
zotero_brace_cleanup.py

Removes BetterBibTeX {{ }} brace artifacts from Zotero titles and fixes known typos.

Requirements:
    pip install pyzotero python-dotenv

Usage:
    python zotero_brace_cleanup.py --dry-run     # Preview changes
    python zotero_brace_cleanup.py               # Apply changes
"""

import argparse
import re
import sys
import time

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials

# Known typos to fix
TYPO_FIXES = {
    'Flordia': 'Florida',
    'Inititative': 'Initiative',
}

# Fields to clean
TEXT_FIELDS = ['title', 'shortTitle', 'institution', 'publicationTitle']

# Rate limiting
RATE_LIMIT_DELAY = 0.5


def clean_text(text: str) -> str:
    """Remove {{ and }} braces and fix typos."""
    if not text:
        return text

    # Remove braces
    cleaned = re.sub(r'\{\{', '', text)
    cleaned = re.sub(r'\}\}', '', cleaned)

    # Fix typos
    for wrong, correct in TYPO_FIXES.items():
        cleaned = re.sub(rf'\b{wrong}\b', correct, cleaned)

    return cleaned


def main():
    parser = argparse.ArgumentParser(
        description="Remove BetterBibTeX brace artifacts from Zotero titles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run     Preview changes
  %(prog)s               Apply changes
        """
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying'
    )

    args = parser.parse_args()

    # Load credentials
    library_id, library_type, api_key = load_credentials()

    print("Zotero Brace Cleanup Script")
    print("=" * 60)
    print(f"Library ID: {library_id}")
    print(f"Library Type: {library_type}")
    print(f"Dry Run: {args.dry_run}")
    print("=" * 60)

    # Connect to Zotero
    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        zot.key_info()
        print("Connected to Zotero API")
    except HTTPError as e:
        print(f"ERROR: Failed to connect to Zotero API: {e}")
        sys.exit(1)

    # Get all items
    print("\nFetching all items from library...")
    items = zot.everything(zot.items())
    print(f"Found {len(items)} items")

    changes = []
    skipped = 0

    for item in items:
        if item['data'].get('itemType') in ['attachment', 'note', 'annotation']:
            skipped += 1
            continue

        item_key = item['key']
        field_changes = {}

        # Check each text field
        for field in TEXT_FIELDS:
            original = item['data'].get(field, '')
            if original:
                cleaned = clean_text(original)
                if original != cleaned:
                    field_changes[field] = {'original': original, 'cleaned': cleaned}

        if field_changes:
            changes.append({
                'key': item_key,
                'field_changes': field_changes,
                'item': item
            })

            mode_str = "[DRY RUN] " if args.dry_run else ""
            print(f"\n{mode_str}[CHANGE] {item_key}")
            for field, vals in field_changes.items():
                print(f"  {field.upper()}: {vals['original']}")
                print(f"  →        {vals['cleaned']}")

    print(f"\n{'='*60}")
    print(f"Total items reviewed: {len(items)}")
    print(f"Attachments/notes skipped: {skipped}")
    print(f"Items to change: {len(changes)}")
    print(f"{'='*60}")

    if not args.dry_run and changes:
        print("\nApplying changes...")
        success = 0
        errors = 0

        for i, change in enumerate(changes, 1):
            item = change['item']

            # Apply all field changes
            for field in TEXT_FIELDS:
                if item['data'].get(field):
                    item['data'][field] = clean_text(item['data'][field])

            try:
                zot.update_item(item)
                print(f"  [{i}/{len(changes)}] Updated: {change['key']}")
                success += 1

                if i < len(changes):
                    time.sleep(RATE_LIMIT_DELAY)
            except HTTPError as e:
                print(f"  [{i}/{len(changes)}] ERROR: {change['key']} - {e}")
                errors += 1

        print(f"\nDone! {success} items updated, {errors} errors.")
    elif args.dry_run and changes:
        print("\n[DRY RUN] No changes applied. Remove --dry-run to apply.")


if __name__ == '__main__':
    main()
