#!/usr/bin/env python3
"""
zotero_collection_migrate.py

Create Zotero collections and move items between them.

Supports two modes:
  1. --create-collections: Create a collection hierarchy from a JSON spec.
  2. --move-items: Move items between collections using a JSON mapping.

Both modes support --dry-run for safe preview.

Requirements:
    pip install pyzotero python-dotenv

Usage:
    python zotero_collection_migrate.py --create-collections spec.json --dry-run
    python zotero_collection_migrate.py --move-items mapping.json --dry-run
    python zotero_collection_migrate.py --move-items mapping.json --verify
"""

import argparse
import json
import sys
import time
from pathlib import Path

from pyzotero import zotero
from pyzotero.zotero_errors import HTTPError

from zotero_utils import load_credentials


RATE_LIMIT_DELAY = 0.5
SKIP_ITEM_TYPES = {'attachment', 'annotation', 'note'}


# --- Collection Creation ---

def load_collection_spec(spec_path: str) -> list[dict]:
    """
    Load collection hierarchy spec from JSON.

    Expected format:
    [
        {"name": "00-Inbox"},
        {
            "name": "04-Literature-Review",
            "children": [
                {"name": "Prior-UAS-Studies"},
                {"name": "LLM-Applications"}
            ]
        }
    ]

    Returns:
        List of collection spec dicts.
    """
    path = Path(spec_path)
    if not path.exists():
        print(f"ERROR: Spec file not found: {spec_path}")
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        spec = json.load(f)

    if not isinstance(spec, list):
        print("ERROR: Collection spec must be a JSON array")
        sys.exit(1)

    total = sum(1 + len(c.get('children', [])) for c in spec)
    print(f"Loaded collection spec: {len(spec)} top-level, {total} total")
    return spec


def get_existing_collections(zot: zotero.Zotero) -> dict[str, str]:
    """Get map of collection name -> key for all existing collections."""
    result = {}
    for coll in zot.collections():
        name = coll['data'].get('name', '')
        result[name] = coll['key']
    return result


def create_collections(
    zot: zotero.Zotero,
    spec: list[dict],
    dry_run: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Create collections from a hierarchy spec.

    Creates top-level collections first, then subcollections.
    Skips collections that already exist (by name).

    Returns:
        Stats dict with counts.
    """
    mode = "[DRY RUN] " if dry_run else ""
    existing = get_existing_collections(zot)
    stats = {'created': 0, 'skipped': 0, 'errors': 0}
    created_keys = {}  # name -> key for newly created collections

    # Pass 1: Top-level collections
    print(f"\n{mode}Creating top-level collections...")
    for item in spec:
        name = item['name']
        if name in existing:
            print(f"  SKIP (exists): {name} ({existing[name]})")
            stats['skipped'] += 1
            created_keys[name] = existing[name]
            continue

        print(f"  {mode}CREATE: {name}")
        stats['created'] += 1

        if not dry_run:
            try:
                payload = [{'name': name}]
                resp = zot.create_collections(payload)
                if resp.get('success'):
                    key = list(resp['success'].values())[0]
                    created_keys[name] = key
                    print(f"    -> key: {key}")
                else:
                    print(f"    ERROR: {resp.get('failed', 'unknown error')}")
                    stats['errors'] += 1
                time.sleep(RATE_LIMIT_DELAY)
            except HTTPError as e:
                print(f"    ERROR: {e}")
                stats['errors'] += 1

    # Pass 2: Subcollections
    print(f"\n{mode}Creating subcollections...")
    for item in spec:
        children = item.get('children', [])
        if not children:
            continue

        parent_name = item['name']
        parent_key = created_keys.get(parent_name) or existing.get(parent_name)

        if not parent_key:
            print(f"  SKIP children of {parent_name}: parent not found")
            stats['errors'] += len(children)
            continue

        for child in children:
            child_name = child['name']
            # Check if subcollection already exists
            if child_name in existing:
                print(f"  SKIP (exists): {parent_name}/{child_name}")
                stats['skipped'] += 1
                continue

            print(f"  {mode}CREATE: {parent_name}/{child_name}")
            stats['created'] += 1

            if not dry_run:
                try:
                    payload = [{'name': child_name, 'parentCollection': parent_key}]
                    resp = zot.create_collections(payload)
                    if resp.get('success'):
                        key = list(resp['success'].values())[0]
                        print(f"    -> key: {key}")
                    else:
                        print(f"    ERROR: {resp.get('failed', 'unknown error')}")
                        stats['errors'] += 1
                    time.sleep(RATE_LIMIT_DELAY)
                except HTTPError as e:
                    print(f"    ERROR: {e}")
                    stats['errors'] += 1

    return stats


# --- Item Moves ---

def load_move_mapping(mapping_path: str) -> list[dict]:
    """
    Load item move mapping from JSON.

    Expected format:
    [
        {
            "item_key": "ABC12345",
            "from_collection": "OLD_COLL_KEY",
            "to_collection": "NEW_COLL_KEY"
        }
    ]

    'from_collection' is optional. If omitted, item is only added to
    'to_collection' without removal from any collection.

    Returns:
        List of move instruction dicts.
    """
    path = Path(mapping_path)
    if not path.exists():
        print(f"ERROR: Mapping file not found: {mapping_path}")
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        mapping = json.load(f)

    if not isinstance(mapping, list):
        print("ERROR: Move mapping must be a JSON array")
        sys.exit(1)

    for i, m in enumerate(mapping):
        if 'item_key' not in m or 'to_collection' not in m:
            print(f"ERROR: Entry {i} missing 'item_key' or 'to_collection'")
            sys.exit(1)

    print(f"Loaded move mapping: {len(mapping)} item moves")
    return mapping


def verify_item_in_collection(
    zot: zotero.Zotero,
    item_key: str,
    collection_key: str,
) -> bool:
    """Check whether an item belongs to a specific collection."""
    try:
        items = zot.collection_items(collection_key, limit=100)
        return any(item['key'] == item_key for item in items)
    except HTTPError:
        return False


def move_items(
    zot: zotero.Zotero,
    mapping: list[dict],
    dry_run: bool = True,
    verify: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Move items between collections using copy-then-remove safety.

    Steps for each item:
    1. Add to new collection
    2. Verify item appears in new collection (if --verify)
    3. Remove from old collection (only after verification)

    Returns:
        Stats dict with counts.
    """
    mode = "[DRY RUN] " if dry_run else ""
    stats = {
        'moved': 0,
        'add_only': 0,
        'verify_failed': 0,
        'errors': 0,
    }

    for i, entry in enumerate(mapping, 1):
        item_key = entry['item_key']
        to_coll = entry['to_collection']
        from_coll = entry.get('from_collection')
        label = entry.get('title', item_key)

        title_display = label[:55] + "..." if len(label) > 55 else label
        action = f"{from_coll} -> {to_coll}" if from_coll else f"-> {to_coll}"
        print(f"{mode}[{i}/{len(mapping)}] {title_display}")
        print(f"  {action}")

        if dry_run:
            if from_coll:
                stats['moved'] += 1
            else:
                stats['add_only'] += 1
            continue

        # Step 1: Add to new collection
        try:
            item = zot.item(item_key)
            zot.addto_collection(to_coll, item)
            print(f"  + Added to {to_coll}")
        except HTTPError as e:
            print(f"  ERROR adding to {to_coll}: {e}")
            stats['errors'] += 1
            continue

        time.sleep(RATE_LIMIT_DELAY)

        # Step 2: Verify (if requested and moving from another collection)
        if from_coll and verify:
            if verify_item_in_collection(zot, item_key, to_coll):
                print(f"  ✓ Verified in {to_coll}")
            else:
                print(f"  ✗ VERIFICATION FAILED — skipping removal from {from_coll}")
                stats['verify_failed'] += 1
                continue

        # Step 3: Remove from old collection
        if from_coll:
            try:
                zot.deletefrom_collection(from_coll, item)
                print(f"  - Removed from {from_coll}")
                stats['moved'] += 1
            except HTTPError as e:
                print(f"  ERROR removing from {from_coll}: {e}")
                stats['errors'] += 1
        else:
            stats['add_only'] += 1

        time.sleep(RATE_LIMIT_DELAY)

    return stats


def print_create_summary(stats: dict, dry_run: bool):
    """Print collection creation summary."""
    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{'='*60}")
    print(f"{mode}COLLECTION CREATION SUMMARY")
    print(f"{'='*60}")
    print(f"Collections created:   {stats['created']}")
    print(f"Already existed:       {stats['skipped']}")
    if stats['errors']:
        print(f"Errors:                {stats['errors']}")
    print(f"{'='*60}")


def print_move_summary(stats: dict, dry_run: bool):
    """Print item move summary."""
    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{'='*60}")
    print(f"{mode}ITEM MOVE SUMMARY")
    print(f"{'='*60}")
    print(f"Items moved:           {stats['moved']}")
    print(f"Items added only:      {stats['add_only']}")
    if stats['verify_failed']:
        print(f"Verification failures: {stats['verify_failed']}")
    if stats['errors']:
        print(f"Errors:                {stats['errors']}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Create Zotero collections and move items between them.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  --create-collections SPEC.json   Create collection hierarchy from spec
  --move-items MAPPING.json        Move items between collections

Collection spec format:
  [
    {"name": "00-Inbox"},
    {"name": "04-Lit-Review", "children": [
      {"name": "Prior-UAS-Studies"},
      {"name": "LLM-Applications"}
    ]}
  ]

Move mapping format:
  [
    {
      "item_key": "ABC12345",
      "to_collection": "NEW_KEY",
      "from_collection": "OLD_KEY",
      "title": "Optional label for output"
    }
  ]

Examples:
  %(prog)s --create-collections spec.json --dry-run
  %(prog)s --move-items mapping.json --dry-run --verify
  %(prog)s --move-items mapping.json --verify

Environment variables (or .env file):
  ZOTERO_LIBRARY_ID     Your Zotero library ID
  ZOTERO_LIBRARY_TYPE   'group' (default) or 'user'
  ZOTERO_API_KEY        Your Zotero API key
        """
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--create-collections', metavar='SPEC',
        help='Create collections from a JSON hierarchy spec'
    )
    group.add_argument(
        '--move-items', metavar='MAPPING',
        help='Move items between collections using a JSON mapping'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Preview changes without modifying (recommended first run)'
    )
    parser.add_argument(
        '--verify', action='store_true', default=True,
        help='Verify item in new collection before removing from old (default: True)'
    )
    parser.add_argument(
        '--no-verify', action='store_false', dest='verify',
        help='Skip verification step (not recommended)'
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    # Load credentials and connect
    library_id, library_type, api_key = load_credentials()

    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        zot.key_info()
        print(f"Connected to Zotero ({library_type} library: {library_id})")
    except HTTPError as e:
        print(f"ERROR: Failed to connect to Zotero API: {e}")
        sys.exit(1)

    if args.dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN MODE — No changes will be made")
        print(f"{'='*60}")

    # Dispatch to mode
    if args.create_collections:
        spec = load_collection_spec(args.create_collections)
        stats = create_collections(zot, spec, dry_run=args.dry_run, verbose=args.verbose)
        print_create_summary(stats, args.dry_run)
    else:
        mapping = load_move_mapping(args.move_items)
        stats = move_items(
            zot, mapping,
            dry_run=args.dry_run,
            verify=args.verify,
            verbose=args.verbose,
        )
        print_move_summary(stats, args.dry_run)

    errors = stats.get('errors', 0) + stats.get('verify_failed', 0)
    if errors:
        sys.exit(1)


if __name__ == '__main__':
    main()
